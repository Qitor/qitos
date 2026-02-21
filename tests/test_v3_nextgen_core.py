import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from qitos import (
    Action,
    Decision,
    FirstCandidateSelector,
    RuntimeBudget,
    Runtime,
    ToolRegistry,
    TraceSchemaValidator,
    TraceWriter,
)
from qitos.core.policy import Policy


@dataclass
class KernelState:
    task: str
    current_step: int = 0
    final_result: Optional[str] = None
    stop_reason: Optional[str] = None
    logs: List[str] = field(default_factory=list)


class ReActLikePolicy(Policy[KernelState, Dict[str, Any], Action]):
    def __init__(self):
        self.prepared = False
        self.finalized = False

    def prepare(self, state: KernelState, context: dict[str, Any] | None = None) -> None:
        self.prepared = True

    def propose(self, state: KernelState, obs: Dict[str, Any]) -> Decision[Action]:
        if state.final_result is not None:
            return Decision.final(state.final_result)

        if state.current_step == 0:
            return Decision.act([Action(name="add", args={"a": 40, "b": 2})], rationale="do math")

        return Decision.final(str(state.final_result or "42"))

    def update(
        self,
        state: KernelState,
        obs: Dict[str, Any],
        decision: Decision[Action],
        results: list[Any],
    ) -> KernelState:
        if results:
            state.final_result = str(results[0])
            state.logs.append(f"result={results[0]}")
        return state

    def finalize(self, state: KernelState) -> None:
        self.finalized = True


class BranchingPolicy(Policy[KernelState, Dict[str, Any], Action]):
    def propose(self, state: KernelState, obs: Dict[str, Any]) -> Decision[Action]:
        if state.final_result:
            return Decision.final(state.final_result)

        if state.current_step == 0:
            c1 = Decision.act([Action(name="add", args={"a": 20, "b": 22})], rationale="candidate1")
            c2 = Decision.act([Action(name="add", args={"a": 1, "b": 2})], rationale="candidate2")
            return Decision.branch([c1, c2], rationale="branching")

        return Decision.final(str(state.final_result or "42"))

    def update(self, state: KernelState, obs: Dict[str, Any], decision: Decision[Action], results: list[Any]) -> KernelState:
        if results:
            state.final_result = str(results[0])
        return state


class TestNextGenKernel:
    def test_runtime_basic(self):
        registry = ToolRegistry()

        def add(a: int, b: int) -> int:
            return a + b

        registry.register(add, name="add")

        runtime = Runtime(
            policy=ReActLikePolicy(),
            toolkit=registry,
            budget=RuntimeBudget(max_steps=4),
        )

        result = runtime.run(KernelState(task="compute"))

        assert result.state.final_result == "42"
        assert result.step_count >= 1
        assert runtime.policy.prepared is True
        assert runtime.policy.finalized is True

    def test_runtime_branch_selector(self):
        registry = ToolRegistry()

        def add(a: int, b: int) -> int:
            return a + b

        registry.register(add, name="add")

        runtime = Runtime(
            policy=BranchingPolicy(),
            toolkit=registry,
            budget=RuntimeBudget(max_steps=4),
            branch_selector=FirstCandidateSelector(),
        )

        result = runtime.run(KernelState(task="branch test"))
        assert result.state.final_result == "42"

    def test_trace_schema_validator(self, tmp_path: Path):
        registry = ToolRegistry()

        def add(a: int, b: int) -> int:
            return a + b

        registry.register(add, name="add")

        writer = TraceWriter(output_dir=str(tmp_path), run_id="kernel-v3")
        runtime = Runtime(
            policy=ReActLikePolicy(),
            toolkit=registry,
            budget=RuntimeBudget(max_steps=4),
            trace_writer=writer,
        )
        runtime.run(KernelState(task="trace"))

        run_dir = tmp_path / "kernel-v3"
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        steps = [json.loads(line) for line in (run_dir / "steps.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

        validator = TraceSchemaValidator()
        validator.validate_manifest(manifest)
        validator.validate_events(events)
        validator.validate_steps(steps)

    def test_invalid_decision_rejected(self):
        class BadPolicy(Policy[KernelState, Dict[str, Any], Action]):
            def propose(self, state: KernelState, obs: Dict[str, Any]) -> Decision[Action]:
                return Decision(mode="act", actions=[], meta="invalid-meta")  # type: ignore[arg-type]

            def update(self, state: KernelState, obs: Dict[str, Any], decision: Decision[Action], results: list[Any]) -> KernelState:
                return state

        registry = ToolRegistry()
        runtime = Runtime(policy=BadPolicy(), toolkit=registry, budget=RuntimeBudget(max_steps=1))

        result = runtime.run(KernelState(task="bad"))
        assert result.state.stop_reason == "unrecoverable_error"
