"""Canonical OpenDeepResearch-style GAIA benchmark recipe for QitOS."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from qitos.core.action import Action
from qitos.core.agent_module import AgentModule
from qitos.core.decision import Decision
from qitos.core.env import EnvSpec
from qitos.core.state import StateSchema
from qitos.core.task import Task, TaskBudget
from qitos.core.tool_registry import ToolRegistry
from qitos.benchmark.gaia.adapter import GaiaAdapter
from qitos.core.spec import BenchmarkRunResult, ExperimentSpec, RunSpec
from qitos.kit import (
    CodingToolSet,
    ReActTextParser,
    TextWebEnv,
    format_action,
    render_prompt,
)
from qitos.kit.tool.browser import (
    ArchiveSearch,
    FindInPage,
    FindNext,
    PageDown,
    PageUp,
    VisitURL,
    WebSearch,
)
from qitos.models import OpenAICompatibleModel
from qitos.render import ClaudeStyleHook
from qitos.trace import TraceWriter

from ._shared import (
    build_example_specs,
    execute_example_jobs,
    print_benchmark_summary,
    print_single_result,
)

DEFAULT_MODEL_BASE_URL = "https://api.siliconflow.cn/v1/"
DEFAULT_MODEL_NAME = "Qwen/Qwen3-8B"
DEFAULT_THEME = "research"

SYSTEM_PROMPT = """You are an OpenDeepResearch benchmark agent.

Rules:
- Use tool calls with function syntax only, exactly one tool call per step.
- Prefer this loop: web_search -> visit_url -> page_down/find_in_page -> find_next.
- Keep evidence snippets in your scratchpad and verify before final answer.
- If attachments are provided, inspect them before concluding.

Tool schema:
{tool_schema}

Output format:
Thought: <short reasoning>
Action: <tool_name>(arg=value, ...)
or
Final Answer: <answer only>
"""

_APPEND_LOCK = threading.Lock()


@dataclass
class ODRGaiaState(StateSchema):
    scratchpad: List[str] = field(default_factory=list)
    task_payload: Dict[str, Any] = field(default_factory=dict)


class OpenDeepResearchGaiaAgent(AgentModule[ODRGaiaState, Dict[str, Any], Action]):
    name = "open_deep_research_gaia"

    def __init__(self, llm: Any, workspace_root: str):
        registry = ToolRegistry()
        registry.register(WebSearch())
        registry.register(VisitURL())
        registry.register(PageUp())
        registry.register(PageDown())
        registry.register(FindInPage())
        registry.register(FindNext())
        registry.register(ArchiveSearch())
        registry.include(
            CodingToolSet(
                workspace_root=workspace_root,
                include_notebook=False,
                enable_lsp=False,
                enable_tasks=False,
                enable_web=False,
                expose_modern_names=False,
            )
        )
        super().__init__(
            tool_registry=registry, llm=llm, model_parser=ReActTextParser()
        )

    def init_state(self, task: str, **kwargs: Any) -> ODRGaiaState:
        return ODRGaiaState(
            task=task,
            max_steps=int(kwargs.get("max_steps", 16)),
            task_payload=dict(kwargs.get("task_payload", {}) or {}),
        )

    def build_system_prompt(self, state: ODRGaiaState) -> str | None:
        return render_prompt(
            SYSTEM_PROMPT, {"tool_schema": self.tool_registry.get_tool_descriptions()}
        )

    def prepare(self, state: ODRGaiaState) -> str:
        payload = dict(getattr(state, "task_payload", {}) or {})
        lines = [
            f"Task: {payload.get('question', state.task)}",
            f"Step: {state.current_step}/{state.max_steps}",
        ]
        rationales = _recent_rationales_from_scratchpad(state.scratchpad, max_items=6)
        if rationales:
            lines.append("Recent rationale:")
            lines.extend(f"- {x}" for x in rationales)
        attachments = payload.get("attachments") or []
        if attachments:
            lines.append("Attachments:")
            lines.extend(f"- {x}" for x in attachments)
        if state.scratchpad:
            lines.append("Recent Evidence:")
            lines.extend(state.scratchpad[-8:])
        return "\n".join(lines)

    def reduce(
        self,
        state: ODRGaiaState,
        observation: Dict[str, Any],
        decision: Decision[Action],
    ) -> ODRGaiaState:
        action_results = (
            observation.get("action_results", [])
            if isinstance(observation, dict)
            else []
        )
        if decision.rationale:
            state.scratchpad.append(f"Thought: {decision.rationale}")
        if decision.actions:
            state.scratchpad.append(f"Action: {format_action(decision.actions[0])}")
        if action_results:
            state.scratchpad.append(f"Observation: {action_results[0]}")
        state.scratchpad = state.scratchpad[-40:]
        return state


@dataclass
class GaiaRecipeExecution:
    task: Task
    run_spec: RunSpec
    experiment_spec: ExperimentSpec | None
    result: Any = None
    elapsed_seconds: float = 0.0
    prediction: Any = None
    reference_answer: Any = None
    question: Any = None
    error: str | None = None
    answer_file: str | None = None
    workspace: str | None = None
    trace_run_dir: str | None = None


def _add_common_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--workspace", default="./qitos_gaia_workspace")
    ap.add_argument(
        "--model-base-url", default=os.getenv("OPENAI_BASE_URL", DEFAULT_MODEL_BASE_URL)
    )
    ap.add_argument("--api-key", default="")
    ap.add_argument(
        "--model-name", default=os.getenv("QITOS_MODEL", DEFAULT_MODEL_NAME)
    )
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--theme", default=DEFAULT_THEME)
    ap.add_argument("--trace-logdir", default="./runs")
    ap.add_argument("--trace-prefix", default="qitos")
    ap.add_argument("--disable-trace", action="store_true")
    ap.add_argument("--disable-render", action="store_true")


def _build_model(args: argparse.Namespace) -> OpenAICompatibleModel:
    api_key = (
        str(args.api_key).strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
        or os.getenv("QITOS_API_KEY", "").strip()
    )
    if not api_key:
        raise ValueError(
            "Missing API key. Set --api-key or OPENAI_API_KEY/QITOS_API_KEY."
        )
    return OpenAICompatibleModel(
        model=str(args.model_name),
        api_key=api_key,
        base_url=str(args.model_base_url) or None,
        temperature=float(args.temperature),
        max_tokens=int(args.max_tokens),
    )


def _setup_workspace(
    path: str,
) -> tuple[Path, Optional[tempfile.TemporaryDirectory[str]]]:
    if path:
        root = Path(path).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root, None
    temp_ctx: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
    return Path(temp_ctx.name), temp_ctx


def _make_trace_writer(args: argparse.Namespace, case_name: str) -> TraceWriter | None:
    if bool(args.disable_trace):
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    run_id = f"{args.trace_prefix}_{case_name}_{stamp}"
    return TraceWriter(
        output_dir=str(Path(args.trace_logdir).expanduser().resolve()),
        run_id=run_id,
        strict_validate=True,
        metadata={"model_id": str(args.model_name)},
    )


def _recent_rationales_from_scratchpad(
    scratchpad: List[str], max_items: int = 6
) -> List[str]:
    out: List[str] = []
    for item in reversed(scratchpad or []):
        text = str(item).strip()
        if not text:
            continue
        low = text.lower()
        if low.startswith("thought:"):
            out.append(text.split(":", 1)[1].strip())
        elif low.startswith("rationale:"):
            out.append(text.split(":", 1)[1].strip())
        if len(out) >= max(1, int(max_items)):
            break
    out.reverse()
    return out


def _first_non_empty(record: Mapping[str, Any], keys: Sequence[str]) -> Optional[Any]:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _normalize_filename(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value.strip())
    return clean.strip("_") or "task"


def _materialize_attachments(task: Task, workspace_root: Path) -> None:
    copied: List[str] = []
    for res in task.resources:
        if res.kind != "file" or not res.path:
            continue
        src = Path(res.path)
        if not src.exists() or src.is_dir():
            continue
        dst = workspace_root / "attachments" / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        rel = str(dst.relative_to(workspace_root))
        res.path = rel
        copied.append(rel)
    task.inputs["attachments"] = copied


def _load_gaia_records(
    args: argparse.Namespace,
) -> tuple[GaiaAdapter, list[dict[str, Any]]]:
    adapter = GaiaAdapter(local_dir=args.gaia_local_dir)
    if args.gaia_download_snapshot:
        adapter.snapshot_dataset(
            use_raw_dataset=bool(args.gaia_use_raw_dataset),
            local_dir=args.gaia_local_dir,
            hf_token=os.getenv("HF_TOKEN", "").strip() or None,
        )

    if args.gaia_from_local:
        records = adapter.load_local_records(
            split=args.gaia_split, local_dir=args.gaia_local_dir
        )
    else:
        records = adapter.load_huggingface_records(
            split=args.gaia_split,
            subset=args.gaia_subset or None,
            use_annotated_dataset=bool(args.gaia_use_annotated),
        )
    return adapter, records


def build_gaia_task(
    *,
    adapter: GaiaAdapter,
    record: Mapping[str, Any],
    split: str,
    idx: int,
    workspace_root: Path,
    max_steps: int,
) -> Task:
    task = adapter.to_task(record, split=split, idx=idx)
    task.env_spec = EnvSpec(
        type="text_web_env", config={"workspace_root": str(workspace_root)}
    )
    task.budget = TaskBudget(max_steps=max_steps)
    _materialize_attachments(task, workspace_root)
    return task


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _APPEND_LOCK, path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_done_task_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    done: set[str] = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            task_id = str(row.get("task_id", "")).strip()
            if task_id:
                done.add(task_id)
    return done


def execute_gaia_task(
    *,
    adapter: GaiaAdapter,
    record: Mapping[str, Any],
    split: str,
    idx: int,
    root: Path,
    args: argparse.Namespace,
    run_spec: RunSpec | None = None,
    experiment_spec: ExperimentSpec | None = None,
) -> GaiaRecipeExecution:
    started = time.time()
    raw_id = _first_non_empty(record, ["task_id", "id", "sample_id", "qid"])
    task_id_seed = str(raw_id) if raw_id is not None else f"{split}_{idx:05d}"
    task_workspace = root / "tasks" / f"{idx:05d}_{_normalize_filename(task_id_seed)}"
    task_workspace.mkdir(parents=True, exist_ok=True)

    effective_spec = RunSpec.from_value(run_spec)
    if not effective_spec.model_name:
        effective_spec.model_name = str(args.model_name)
    if not effective_spec.benchmark_name:
        effective_spec.benchmark_name = "gaia"
    if not effective_spec.benchmark_split:
        effective_spec.benchmark_split = split
    effective_spec.toolset_name = effective_spec.toolset_name or "gaia_open_deep_research"
    effective_spec.environment = {
        **dict(effective_spec.environment or {}),
        "workspace": str(task_workspace),
        "lane": "gaia",
    }
    effective_spec.metadata = {
        **dict(effective_spec.metadata or {}),
        "recipe": "gaia_open_deep_research",
    }

    task = build_gaia_task(
        adapter=adapter,
        record=record,
        split=split,
        idx=idx,
        workspace_root=task_workspace,
        max_steps=int(args.max_steps),
    )

    model = _build_model(args)
    agent = OpenDeepResearchGaiaAgent(llm=model, workspace_root=str(task_workspace))
    trace_writer = _make_trace_writer(args, f"gaia_odr_{_normalize_filename(task.id)}")
    render = (
        None
        if args.disable_render
        else ClaudeStyleHook(
            output_jsonl=str(task_workspace / "render_events.jsonl"),
            theme=args.theme,
        )
    )

    error_msg = None
    result = None
    final_result = None
    try:
        result = agent.run(
            task=task,
            return_state=True,
            max_steps=int(args.max_steps),
            task_payload=task.inputs,
            env=TextWebEnv(workspace_root=str(task_workspace)),
            trace=trace_writer,
            render=render,
            run_spec=effective_spec,
            experiment_spec=experiment_spec,
        )
        final_result = result.state.final_result
    except Exception as exc:
        final_result = None
        error_msg = str(exc)

    answer_path = task_workspace / "gaia_answer.txt"
    answer_path.write_text(str(final_result or ""), encoding="utf-8")

    ref_answer = _first_non_empty(
        record, ["true_answer", "Final answer", "final_answer", "answer", "gold_answer"]
    )
    question = _first_non_empty(
        record, ["question", "Question", "prompt", "problem", "query", "instruction"]
    )

    return GaiaRecipeExecution(
        task=task,
        run_spec=effective_spec,
        experiment_spec=experiment_spec,
        result=result,
        elapsed_seconds=time.time() - started,
        prediction=final_result,
        reference_answer=ref_answer,
        question=question,
        error=error_msg,
        answer_file=str(answer_path),
        workspace=str(task_workspace),
        trace_run_dir=(str(trace_writer.run_dir) if trace_writer is not None else None),
    )


def build_gaia_benchmark_result(execution: GaiaRecipeExecution) -> BenchmarkRunResult:
    stop_reason = "exception" if execution.error else str(
        getattr(getattr(execution.result, "state", None), "stop_reason", None) or "unknown"
    )
    task_result = getattr(execution.result, "task_result", None) if execution.result is not None else None
    return BenchmarkRunResult(
        task_id=str(execution.task.id),
        benchmark="gaia",
        split=str(
            (execution.experiment_spec.benchmark_split if execution.experiment_spec else None)
            or execution.run_spec.benchmark_split
            or "validation"
        ),
        prediction=execution.prediction,
        success=not bool(execution.error) and str(stop_reason) == "final",
        stop_reason=str(stop_reason),
        steps=int(getattr(execution.result, "step_count", 0) if execution.result is not None else 0),
        latency_seconds=float(
            ((task_result.metrics or {}).get("elapsed_seconds") if task_result else execution.elapsed_seconds)
            or execution.elapsed_seconds
        ),
        token_usage=int(
            ((task_result.metrics or {}).get("token_usage") if task_result else 0) or 0
        ),
        cost=float(((task_result.metrics or {}).get("cost") if task_result else 0.0) or 0.0),
        trace_run_dir=execution.trace_run_dir,
        run_spec_ref=execution.run_spec.fingerprint(),
        metadata={
            "question": execution.question,
            "reference_answer": execution.reference_answer,
            "workspace": execution.workspace,
            "answer_file": execution.answer_file,
            "source_task_id": str(_first_non_empty(execution.task.metadata or {}, ["source_task_id", "task_id"]) or ""),
            "recipe": "gaia_open_deep_research",
            "error": execution.error,
        },
    )


def run_gaia_recipe_task(
    *,
    task: Task,
    record: Mapping[str, Any],
    idx: int,
    root: Path,
    args: argparse.Namespace,
    run_spec: RunSpec,
    experiment_spec: ExperimentSpec,
    **_: Any,
) -> BenchmarkRunResult:
    execution = execute_gaia_task(
        args=args,
        adapter=GaiaAdapter(local_dir=args.gaia_local_dir),
        record=record,
        split=args.gaia_split,
        idx=idx,
        root=root,
        run_spec=run_spec,
        experiment_spec=experiment_spec,
    )
    return build_gaia_benchmark_result(execution)


def _run_full_benchmark(
    args: argparse.Namespace,
    adapter: GaiaAdapter,
    records: list[dict[str, Any]],
    root: Path,
) -> None:
    selected: list[tuple[int, dict[str, Any]]] = []
    start_idx = max(0, int(args.start_index))
    for i, row in enumerate(records):
        if i < start_idx:
            continue
        selected.append((i, row))
        if int(args.limit) > 0 and len(selected) >= int(args.limit):
            break

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = (
        Path(args.output_jsonl).expanduser().resolve()
        if args.output_jsonl
        else (root / f"gaia_{args.gaia_split}_{stamp}.jsonl")
    )
    done_ids = _read_done_task_ids(output_path) if args.resume else set()

    jobs: list[tuple[int, dict[str, Any]]] = []
    for idx, row in selected:
        task_id_raw = _first_non_empty(row, ["task_id", "id", "sample_id", "qid"])
        fallback_id = f"gaia_{args.gaia_split}_{idx:05d}"
        task_id = str(task_id_raw).strip() if task_id_raw else fallback_id
        if task_id in done_ids:
            continue
        jobs.append((idx, row))

    print(
        f"[GAIA] split={args.gaia_split} total_loaded={len(records)} selected={len(selected)} to_run={len(jobs)}"
    )
    if not jobs:
        print("[GAIA] no pending tasks.")
        return

    run_spec, experiment_spec = build_example_specs(
        benchmark="gaia",
        split=args.gaia_split,
        model_name=str(args.model_name),
        trace_logdir=str(args.trace_logdir),
        parser_name="ReActTextParser",
        toolset_name="gaia_open_deep_research",
        subset=args.gaia_subset or None,
        limit=len(jobs),
        workspace=str(root),
        metadata={"recipe": "gaia_open_deep_research"},
    )

    work_items = []
    for idx, row in jobs:
        task = build_gaia_task(
            adapter=adapter,
            record=row,
            split=args.gaia_split,
            idx=idx,
            workspace_root=root / "tasks" / f"{idx:05d}_{_normalize_filename(str(_first_non_empty(row, ['task_id', 'id', 'sample_id', 'qid']) or idx))}",
            max_steps=int(args.max_steps),
        )
        work_items.append(
            {
                "task": task,
                "record": row,
                "idx": idx,
                "root": root,
                "args": args,
                "job_key": str(task.id),
            }
        )

    rows = execute_example_jobs(
        jobs=work_items,
        runner=run_gaia_recipe_task,
        output_path=output_path,
        run_spec=run_spec,
        experiment_spec=experiment_spec,
        concurrency=max(1, int(args.concurrency)),
        resume=bool(args.resume),
    )
    print_benchmark_summary(rows)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QitOS GAIA benchmark recipe")
    parser.add_argument("--workspace", default="./qitos_gaia_workspace")
    parser.add_argument("--output-jsonl", default="")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=16)
    parser.add_argument("--gaia-split", default="validation")
    parser.add_argument("--gaia-subset", default="")
    parser.add_argument("--gaia-local-dir", default="data/gaia")
    parser.add_argument("--gaia-from-local", action="store_true")
    parser.add_argument("--gaia-use-annotated", action="store_true")
    parser.add_argument("--gaia-use-raw-dataset", action="store_true")
    parser.add_argument("--gaia-download-snapshot", action="store_true")
    parser.add_argument("--single-index", type=int, default=-1)
    parser.add_argument("--print-single", action="store_true")
    _add_common_args(parser)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _build_arg_parser().parse_args(argv or [])
    root, tmp_ctx = _setup_workspace(str(args.workspace))
    try:
        adapter, records = _load_gaia_records(args)
        if int(args.single_index) >= 0:
            idx = int(args.single_index)
            if idx >= len(records):
                raise IndexError(f"single index out of range: {idx}")
            run_spec, experiment_spec = build_example_specs(
                benchmark="gaia",
                split=args.gaia_split,
                model_name=str(args.model_name),
                trace_logdir=str(args.trace_logdir),
                parser_name="ReActTextParser",
                toolset_name="gaia_open_deep_research",
                subset=args.gaia_subset or None,
                limit=1,
                workspace=str(root),
                metadata={"recipe": "gaia_open_deep_research"},
            )
            execution = execute_gaia_task(
                args=args,
                adapter=adapter,
                record=records[idx],
                split=args.gaia_split,
                idx=idx,
                root=root,
                run_spec=run_spec,
                experiment_spec=experiment_spec,
            )
            row = build_gaia_benchmark_result(execution)
            print_single_result(row)
            if args.output_jsonl:
                _append_jsonl(Path(args.output_jsonl).expanduser().resolve(), row.to_dict())
            return

        _run_full_benchmark(args, adapter, records, root)
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()


__all__ = [
    "DEFAULT_MODEL_BASE_URL",
    "DEFAULT_MODEL_NAME",
    "DEFAULT_THEME",
    "GaiaRecipeExecution",
    "ODRGaiaState",
    "OpenDeepResearchGaiaAgent",
    "build_gaia_benchmark_result",
    "build_gaia_task",
    "execute_gaia_task",
    "main",
    "run_gaia_recipe_task",
]


if __name__ == "__main__":
    main()
