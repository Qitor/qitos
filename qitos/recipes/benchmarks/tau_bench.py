"""Canonical Tau-Bench recipe for QitOS."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from qitos.core.action import Action
from qitos.core.agent_module import AgentModule
from qitos.core.decision import Decision
from qitos.core.state import StateSchema
from qitos.core.task import Task, TaskBudget
from qitos.core.tool_registry import ToolRegistry
from qitos.benchmark.tau_bench.adapter import TauBenchAdapter
from qitos.benchmark.tau_bench.port.types import Action as TauAction
from qitos.benchmark.tau_bench.runtime import get_tau_runtime_env
from qitos.core.spec import BenchmarkRunResult, ExperimentSpec, RunSpec
from qitos.evaluate import EvaluationContext, EvaluationSuite
from qitos.kit import ReActTextParser, format_action, render_prompt
from qitos.kit.evaluate import DSLEvaluator, ModelBasedEvaluator, RuleBasedEvaluator
from qitos.kit.metric import (
    MeanStepsMetric,
    RewardAverageMetric,
    RewardPassHatMetric,
    RewardSuccessRateMetric,
    StopReasonDistributionMetric,
    is_successful_reward,
)
from qitos.metric import MetricInput, MetricRegistry
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

SYSTEM_PROMPT = """You are a Tau-Bench task-solving agent.

Domain Wiki:
{wiki}

Policy Rules:
{rules}

Available tools:
{tool_schema}

Rules:
- Exactly one action per step.
- Use function-style action syntax.
- Use respond(content=...) when you want to talk to the user.
- Be concise and policy-compliant.

Output format:
Thought: <one-line reasoning>
Action: <tool_name>(arg=value, ...)
or
Final Answer: <very short>
"""

_APPEND_LOCK = threading.Lock()


@dataclass
class TauState(StateSchema):
    current_observation: str = ""
    scratchpad: List[str] = field(default_factory=list)
    reward: float = 0.0
    done: bool = False


class TauActionTool:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        required: List[str],
        runner: Any,
    ):
        from qitos.core.tool import BaseTool, ToolPermission, ToolSpec

        class _Impl(BaseTool):
            def __init__(self):
                super().__init__(
                    ToolSpec(
                        name=name,
                        description=description,
                        parameters={k: v for k, v in (parameters or {}).items()},
                        required=list(required or []),
                        permissions=ToolPermission(),
                    )
                )

            def run(
                self, runtime_context: Optional[Dict[str, Any]] = None, **kwargs: Any
            ) -> Dict[str, Any]:
                return runner(name, kwargs)

        self.impl = _Impl()


class TauBenchAgent(AgentModule[TauState, Dict[str, Any], Action]):
    def __init__(self, llm: Any, tau_env: Any):
        self.tau_env = tau_env
        registry = ToolRegistry()

        for item in list(getattr(tau_env, "tools_info", []) or []):
            fn = dict(item.get("function", {}) or {})
            name = str(fn.get("name", "")).strip()
            if not name:
                continue
            desc = str(fn.get("description", ""))
            params = dict((fn.get("parameters") or {}).get("properties", {}) or {})
            req = list((fn.get("parameters") or {}).get("required", []) or [])
            wrapper = TauActionTool(name, desc, params, req, self._step_tool)
            registry.register(wrapper.impl)

        if "respond" not in registry.list_tools():
            wrapper = TauActionTool(
                "respond",
                "Respond to user with plain text content",
                {"content": {"type": "string", "description": "response text"}},
                ["content"],
                self._step_tool,
            )
            registry.register(wrapper.impl)

        super().__init__(
            tool_registry=registry, llm=llm, model_parser=ReActTextParser()
        )

    def init_state(self, task: str, **kwargs: Any) -> TauState:
        task_index = int(kwargs.get("task_index", 0))
        reset = self.tau_env.reset(task_index=task_index)
        obs = str(getattr(reset, "observation", ""))
        return TauState(
            task=task,
            max_steps=int(kwargs.get("max_steps", 30)),
            current_observation=obs,
        )

    def build_system_prompt(self, state: TauState) -> str | None:
        wiki = str(getattr(self.tau_env, "wiki", ""))
        rules = "\n".join(
            f"- {r}" for r in list(getattr(self.tau_env, "rules", []) or [])
        )
        return render_prompt(
            SYSTEM_PROMPT,
            {
                "wiki": wiki,
                "rules": rules,
                "tool_schema": (
                    self.tool_registry.get_tool_descriptions()
                    if self.tool_registry
                    else ""
                ),
            },
        )

    def prepare(self, state: TauState) -> str:
        lines = [
            f"Task: {state.task}",
            f"Step: {state.current_step}/{state.max_steps}",
            f"Current observation: {state.current_observation}",
            f"Reward so far: {state.reward}",
        ]
        if state.scratchpad:
            lines.append("Recent trajectory:")
            lines.extend(state.scratchpad[-8:])
        return "\n".join(lines)

    def reduce(
        self, state: TauState, observation: Dict[str, Any], decision: Decision[Action]
    ) -> TauState:
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
            first = (
                action_results[0]
                if isinstance(action_results[0], dict)
                else {"observation": str(action_results[0])}
            )
            state.scratchpad.append(f"Observation: {first.get('observation', first)}")
            state.current_observation = str(
                first.get("observation", state.current_observation)
            )
            state.reward = float(first.get("reward", state.reward or 0.0))
            state.done = bool(first.get("done", False))
            if state.done:
                state.final_result = str(first.get("observation", ""))
                state.metadata["tau_reward"] = state.reward
                state.metadata["tau_info"] = first.get("info", {})
        state.scratchpad = state.scratchpad[-40:]
        return state

    def _step_tool(self, action_name: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        response = self.tau_env.step(TauAction(name=action_name, kwargs=kwargs))
        info = (
            response.info.model_dump()
            if hasattr(response.info, "model_dump")
            else dict(getattr(response, "info", {}) or {})
        )
        return {
            "status": "success",
            "action": action_name,
            "kwargs": kwargs,
            "observation": str(getattr(response, "observation", "")),
            "reward": float(getattr(response, "reward", 0.0)),
            "done": bool(getattr(response, "done", False)),
            "info": info,
        }


@dataclass
class TauRecipeExecution:
    task: Task
    run_spec: RunSpec
    experiment_spec: ExperimentSpec | None
    result: Any = None
    elapsed_seconds: float = 0.0
    reward: float = 0.0
    eval_score: float = 0.0
    eval_details: List[Dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    trace_run_dir: str | None = None
    env_name: str = "retail"
    trial: int = 0
    idx: int = 0


def _add_common_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--workspace", default="./qitos_tau_workspace")
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


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _APPEND_LOCK, path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    done = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        tid = str(obj.get("task_id", "")).strip()
        job_key = str(obj.get("_job_key", "")).strip()
        if job_key:
            done.add(job_key)
        elif tid:
            done.add(tid)
    return done


def build_tau_env(args: argparse.Namespace, task_index: int | None = None) -> Any:
    return get_tau_runtime_env(
        env_name=args.tau_env, task_split=args.tau_split, task_index=task_index
    )


def evaluate_tau_result(
    task: Task, result: Any, include_model_judge: bool = False, llm: Any = None
) -> Dict[str, Any]:
    manifest = {
        "summary": {
            "stop_reason": result.state.stop_reason,
            "final_result": result.state.final_result,
            "steps": result.step_count,
        }
    }
    extras = {
        "reward": float(result.state.metadata.get("tau_reward", 0.0)),
        "tau_info": result.state.metadata.get("tau_info", {}),
    }

    evaluators = [
        RuleBasedEvaluator(name="tau_reward_rule", min_reward=1.0),
        DSLEvaluator(name="tau_done_dsl", expression="extras['reward'] >= 1.0"),
    ]
    if include_model_judge:
        evaluators.append(ModelBasedEvaluator(name="tau_model_judge", llm=llm))

    suite = EvaluationSuite(evaluators=evaluators, mode="all")
    suite_res = suite.evaluate(
        EvaluationContext(task=task, run=result, manifest=manifest, extras=extras)
    )
    return {
        "success": suite_res.success,
        "score": suite_res.score,
        "results": [
            {
                "name": r.name,
                "success": r.success,
                "score": r.score,
                "reasons": r.reasons,
            }
            for r in suite_res.results
        ],
    }


def execute_tau_task(
    *,
    args: argparse.Namespace,
    adapter: TauBenchAdapter,
    idx: int,
    record: Dict[str, Any],
    root: Path,
    trial: int = 0,
    run_spec: RunSpec | None = None,
    experiment_spec: ExperimentSpec | None = None,
) -> TauRecipeExecution:
    started = time.time()
    task = adapter.to_task(record, split=args.tau_split, idx=idx)
    task.budget = TaskBudget(max_steps=int(args.max_steps))

    effective_spec = RunSpec.from_value(run_spec)
    if not effective_spec.model_name:
        effective_spec.model_name = str(args.model_name)
    effective_spec.benchmark_name = effective_spec.benchmark_name or "tau-bench"
    effective_spec.benchmark_split = effective_spec.benchmark_split or str(args.tau_split)
    effective_spec.toolset_name = effective_spec.toolset_name or "tau_bench"
    effective_spec.environment = {
        **dict(effective_spec.environment or {}),
        "workspace": str(root),
        "tau_env": str(args.tau_env),
    }
    effective_spec.metadata = {
        **dict(effective_spec.metadata or {}),
        "recipe": "tau_bench_react",
    }

    tau_env = build_tau_env(args, task_index=idx)
    model = _build_model(args)
    agent = TauBenchAgent(llm=model, tau_env=tau_env)

    trace_writer = _make_trace_writer(
        args, f"tau_{args.tau_env}_{idx:05d}_trial{trial}"
    )
    render = (
        None
        if args.disable_render
        else ClaudeStyleHook(
            output_jsonl=str(root / f"render_events_{idx:05d}_trial{trial}.jsonl"),
            theme=args.theme,
        )
    )

    error_msg = None
    eval_out = {"success": False, "score": 0.0, "results": []}
    reward = 0.0
    result = None
    try:
        result = agent.run(
            task=task,
            return_state=True,
            max_steps=int(args.max_steps),
            task_index=idx,
            trace=trace_writer,
            render=render,
            run_spec=effective_spec,
            experiment_spec=experiment_spec,
        )
        eval_out = evaluate_tau_result(
            task=task,
            result=result,
            include_model_judge=bool(args.enable_model_judge),
            llm=model,
        )
        reward = float(result.state.metadata.get("tau_reward", 0.0))
    except Exception as exc:
        error_msg = str(exc)

    return TauRecipeExecution(
        task=task,
        run_spec=effective_spec,
        experiment_spec=experiment_spec,
        result=result,
        elapsed_seconds=time.time() - started,
        reward=reward,
        eval_score=float(eval_out.get("score", 0.0)),
        eval_details=list(eval_out.get("results", [])),
        error=error_msg,
        trace_run_dir=(str(trace_writer.run_dir) if trace_writer is not None else None),
        env_name=str(args.tau_env),
        trial=int(trial),
        idx=int(idx),
    )


def build_tau_benchmark_result(execution: TauRecipeExecution) -> BenchmarkRunResult:
    stop_reason = "exception" if execution.error else str(
        getattr(getattr(execution.result, "state", None), "stop_reason", None) or "unknown"
    )
    task_result = getattr(execution.result, "task_result", None) if execution.result is not None else None
    return BenchmarkRunResult(
        task_id=str(execution.task.id),
        benchmark="tau-bench",
        split=str(
            (execution.experiment_spec.benchmark_split if execution.experiment_spec else None)
            or execution.run_spec.benchmark_split
            or "test"
        ),
        prediction=getattr(getattr(execution.result, "state", None), "final_result", None),
        success=not bool(execution.error) and bool(execution.eval_score >= 1.0),
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
            "reward": execution.reward,
            "eval_score": execution.eval_score,
            "eval_details": execution.eval_details,
            "env": execution.env_name,
            "trial": execution.trial,
            "idx": execution.idx,
            "recipe": "tau_bench_react",
            "error": execution.error,
        },
    )


def run_tau_recipe_task(
    *,
    task: Task,
    record: Dict[str, Any],
    idx: int,
    trial: int,
    root: Path,
    args: argparse.Namespace,
    run_spec: RunSpec,
    experiment_spec: ExperimentSpec,
    **_: Any,
) -> BenchmarkRunResult:
    execution = execute_tau_task(
        args=args,
        adapter=TauBenchAdapter(env_name=args.tau_env, task_split=args.tau_split),
        idx=idx,
        record=record,
        root=root,
        trial=trial,
        run_spec=run_spec,
        experiment_spec=experiment_spec,
    )
    return build_tau_benchmark_result(execution)


def _print_metrics(rows: List[Dict[str, Any]]) -> None:
    metric_inputs = [
        MetricInput(
            task_id=str(r.get("task_id", "")),
            trial=int(r.get("trial", 0)),
            success=is_successful_reward(float(r.get("reward", 0.0))),
            reward=float(r.get("reward", 0.0)),
            steps=int(r.get("steps", 0)),
            latency_seconds=float(r.get("latency_seconds", 0.0)),
            stop_reason=str(r.get("stop_reason", "")),
            payload=r,
        )
        for r in rows
    ]
    registry = MetricRegistry(
        [
            RewardAverageMetric(),
            RewardSuccessRateMetric(),
            RewardPassHatMetric(),
            MeanStepsMetric(),
            StopReasonDistributionMetric(),
        ]
    )
    reports = {r.name: r for r in registry.compute_all(metric_inputs)}
    pass_hat_ks = (
        reports["reward_pass_hat"].value if "reward_pass_hat" in reports else {}
    )

    print("[Tau-Bench] Metrics (aligned with tau-bench run.py)")
    print(
        f"- avg_reward: {reports['avg_reward'].value if 'avg_reward' in reports else 0.0}"
    )
    print("- pass^k:")
    for k in sorted(pass_hat_ks.keys()):
        print(f"  - k={k}: {pass_hat_ks[k]}")
    for rep in reports.values():
        print(f"- {rep.name}: {rep.value}")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QitOS Tau-Bench recipe")
    parser.add_argument("--workspace", default="./qitos_tau_workspace")
    parser.add_argument("--output-jsonl", default="")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--tau-env", default="retail")
    parser.add_argument("--tau-split", default="test")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--single-index", type=int, default=-1)
    parser.add_argument("--enable-model-judge", action="store_true")
    _add_common_args(parser)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _build_arg_parser().parse_args(argv or [])
    root, tmp_ctx = _setup_workspace(str(args.workspace))
    try:
        adapter = TauBenchAdapter(env_name=args.tau_env, task_split=args.tau_split)
        records = adapter.load_records()
        if int(args.single_index) >= 0:
            idx = int(args.single_index)
            if idx >= len(records):
                raise IndexError(f"single index out of range: {idx}")
            run_spec, experiment_spec = build_example_specs(
                benchmark="tau-bench",
                split=args.tau_split,
                model_name=str(args.model_name),
                trace_logdir=str(args.trace_logdir),
                parser_name="ReActTextParser",
                toolset_name="tau_bench",
                subset=args.tau_env,
                limit=1,
                workspace=str(root),
                metadata={"recipe": "tau_bench_react"},
            )
            execution = execute_tau_task(
                args=args,
                adapter=adapter,
                idx=idx,
                record=records[idx],
                root=root,
                trial=0,
                run_spec=run_spec,
                experiment_spec=experiment_spec,
            )
            row = build_tau_benchmark_result(execution)
            print_single_result(row)
            if args.output_jsonl:
                _append_jsonl(Path(args.output_jsonl).expanduser().resolve(), row.to_dict())
            return

        selected = list(enumerate(records))[int(args.start_index) :]
        if int(args.limit) > 0:
            selected = selected[: int(args.limit)]
        jobs: list[dict[str, Any]] = []
        for idx, row in selected:
            for trial in range(max(1, int(args.trials))):
                task = adapter.to_task(row, split=args.tau_split, idx=idx)
                jobs.append(
                    {
                        "task": task,
                        "record": row,
                        "idx": idx,
                        "trial": trial,
                        "root": root,
                        "args": args,
                        "job_key": f"{task.id}:trial{trial}",
                    }
                )
        output_path = Path(args.output_jsonl).expanduser().resolve() if args.output_jsonl else root / "tau_bench_results.jsonl"
        run_spec, experiment_spec = build_example_specs(
            benchmark="tau-bench",
            split=args.tau_split,
            model_name=str(args.model_name),
            trace_logdir=str(args.trace_logdir),
            parser_name="ReActTextParser",
            toolset_name="tau_bench",
            subset=args.tau_env,
            limit=len(jobs),
            workspace=str(root),
            metadata={"recipe": "tau_bench_react"},
        )
        rows = execute_example_jobs(
            jobs=jobs,
            runner=run_tau_recipe_task,
            output_path=output_path,
            run_spec=run_spec,
            experiment_spec=experiment_spec,
            concurrency=max(1, int(args.concurrency)),
            resume=bool(args.resume),
        )
        print_benchmark_summary(rows)
        _print_metrics([row.to_dict() for row in rows])
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()


__all__ = [
    "DEFAULT_MODEL_BASE_URL",
    "DEFAULT_MODEL_NAME",
    "DEFAULT_THEME",
    "TauActionTool",
    "TauBenchAgent",
    "TauRecipeExecution",
    "TauState",
    "build_tau_benchmark_result",
    "build_tau_env",
    "evaluate_tau_result",
    "execute_tau_task",
    "main",
    "run_tau_recipe_task",
]


if __name__ == "__main__":
    main()
