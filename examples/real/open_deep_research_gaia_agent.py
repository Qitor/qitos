"""OpenDeepResearch-style GAIA agent built with QitOS.

This example shows:
1) converting GAIA samples -> QitOS Task (qitos.benchmark),
2) using a dedicated deep-research toolset (qitos.kit.tool),
3) running one benchmark task through AgentModule + Engine.
"""

from __future__ import annotations

import argparse
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from qitos import Action, AgentModule, Decision, EnvSpec, StateSchema, Task, TaskBudget, ToolRegistry
from qitos.benchmark import GaiaAdapter
from qitos.kit.env import HostEnv
from qitos.kit.parser import ReActTextParser
from qitos.kit.planning import format_action
from qitos.kit.prompts import render_prompt
from qitos.kit.tool import ListFiles, OpenDeepResearchToolSet, ReadFile, RunCommand, WriteFile
from qitos.render import ClaudeStyleHook

from examples.common import add_common_args, build_model_from_args, make_trace_writer, setup_workspace

SYSTEM_PROMPT = """You are an OpenDeepResearch benchmark agent.

Rules:
- Use tool calls with function syntax only, exactly one tool call per step.
- Prefer this loop: web_search -> visit_url -> page_down/find_in_page -> inspect_file_as_text (if needed).
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


@dataclass
class ODRGaiaState(StateSchema):
    scratchpad: List[str] = field(default_factory=list)
    task_payload: Dict[str, Any] = field(default_factory=dict)


class OpenDeepResearchGaiaAgent(AgentModule[ODRGaiaState, Dict[str, Any], Action]):
    name = "open_deep_research_gaia"

    def __init__(self, llm: Any, workspace_root: str):
        registry = ToolRegistry()
        registry.include(OpenDeepResearchToolSet(workspace_root=workspace_root))
        registry.register(ReadFile(root_dir=workspace_root))
        registry.register(ListFiles(root_dir=workspace_root))
        registry.register(WriteFile(root_dir=workspace_root))
        registry.register(RunCommand(cwd=workspace_root))
        super().__init__(tool_registry=registry, llm=llm, model_parser=ReActTextParser())

    def init_state(self, task: str, **kwargs: Any) -> ODRGaiaState:
        return ODRGaiaState(
            task=task,
            max_steps=int(kwargs.get("max_steps", 16)),
            task_payload=dict(kwargs.get("task_payload", {}) or {}),
        )

    def observe(self, state: ODRGaiaState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(getattr(state, "task_payload", {}) or {})
        return {
            "task": state.task,
            "question": payload.get("question", state.task),
            "attachments": payload.get("attachments", []),
            "scratchpad": state.scratchpad[-10:],
            "workspace_files": env_view.get("env", {}).get("files", [])[:20],
        }

    def build_system_prompt(self, state: ODRGaiaState) -> str | None:
        return render_prompt(SYSTEM_PROMPT, {"tool_schema": self.tool_registry.get_tool_descriptions()})

    def prepare(self, state: ODRGaiaState, observation: Dict[str, Any]) -> str:
        lines = [
            f"Task: {observation['question']}",
            f"Step: {state.current_step}/{state.max_steps}",
        ]
        attachments = observation.get("attachments") or []
        if attachments:
            lines.append("Attachments:")
            lines.extend([f"- {x}" for x in attachments])
        if observation.get("scratchpad"):
            lines.append("Recent Evidence:")
            lines.extend(observation["scratchpad"][-8:])
        return "\n".join(lines)

    def reduce(self, state: ODRGaiaState, observation: Dict[str, Any], decision: Decision[Action], action_results: List[Any]) -> ODRGaiaState:
        if decision.rationale:
            state.scratchpad.append(f"Thought: {decision.rationale}")
        if decision.actions:
            state.scratchpad.append(f"Action: {format_action(decision.actions[0])}")
        if action_results:
            state.scratchpad.append(f"Observation: {action_results[0]}")
        state.scratchpad = state.scratchpad[-40:]
        return state


def _materialize_attachments(task: Task, workspace_root: Path) -> None:
    copied: list[str] = []
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


def _load_one_gaia_task(args: argparse.Namespace, workspace_root: Path) -> Task:
    adapter = GaiaAdapter(local_dir=args.gaia_local_dir)
    if args.gaia_download_snapshot:
        adapter.snapshot_dataset(
            use_raw_dataset=bool(args.gaia_use_raw_dataset),
            local_dir=args.gaia_local_dir,
            hf_token=os.getenv("HF_TOKEN", "").strip() or None,
        )
    if args.gaia_from_local:
        records = adapter.load_local_records(split=args.gaia_split, local_dir=args.gaia_local_dir)
    else:
        records = adapter.load_huggingface_records(
            split=args.gaia_split,
            subset=args.gaia_subset or None,
            use_annotated_dataset=bool(args.gaia_use_annotated),
        )
    if not records:
        raise RuntimeError("No GAIA records loaded.")
    idx = max(0, min(int(args.gaia_index), len(records) - 1))
    task = adapter.to_task(records[idx], split=args.gaia_split, idx=idx)
    task.env_spec = EnvSpec(type="host", config={"workspace_root": str(workspace_root)})
    task.budget = TaskBudget(max_steps=int(args.max_steps))
    _materialize_attachments(task, workspace_root)
    return task


def main() -> None:
    ap = argparse.ArgumentParser()
    add_common_args(ap)
    ap.add_argument("--gaia-split", default="validation")
    ap.add_argument("--gaia-index", type=int, default=0)
    ap.add_argument("--gaia-subset", default="")
    ap.add_argument("--gaia-local-dir", default="data/gaia")
    ap.add_argument("--gaia-from-local", action="store_true")
    ap.add_argument("--gaia-download-snapshot", action="store_true")
    ap.add_argument("--gaia-use-raw-dataset", action="store_true")
    ap.add_argument("--gaia-use-annotated", action="store_true")
    ap.add_argument("--max-steps", type=int, default=16)
    args = ap.parse_args()

    root, temp_ctx = setup_workspace(args.workspace)
    model = build_model_from_args(args)
    gaia_task = _load_one_gaia_task(args, workspace_root=root)

    agent = OpenDeepResearchGaiaAgent(llm=model, workspace_root=str(root))
    trace_writer = make_trace_writer(args, "gaia_odr")
    hooks = [] if args.disable_render else [ClaudeStyleHook(output_jsonl=str(root / "render_events.jsonl"), theme=args.theme)]

    engine_kwargs: dict[str, Any] = {"env": HostEnv(workspace_root=str(root))}
    if trace_writer is not None:
        engine_kwargs["trace_writer"] = trace_writer

    result = agent.run(
        task=gaia_task,
        return_state=True,
        hooks=hooks,
        max_steps=args.max_steps,
        task_payload=gaia_task.inputs,
        engine_kwargs=engine_kwargs,
    )
    answer_path = root / "gaia_answer.txt"
    answer_text = str(result.state.final_result or "")
    answer_path.write_text(answer_text, encoding="utf-8")

    print("workspace:", root)
    print("task_id:", gaia_task.id)
    print("final_result:", result.state.final_result)
    print("stop_reason:", result.state.stop_reason)
    print("answer_file:", answer_path)
    if trace_writer is not None:
        print("trace_run_dir:", trace_writer.run_dir)
    if temp_ctx is not None:
        temp_ctx.cleanup()


if __name__ == "__main__":
    main()
