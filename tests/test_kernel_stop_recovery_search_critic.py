import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from qitos import (
    Action,
    Critic,
    Decision,
    ErrorCategory,
    GreedySearchAdapter,
    MaxRuntimeCriteria,
    MaxStepsCriteria,
    Policy,
    RecoveryPolicy,
    Runtime,
    RuntimeBudget,
    StagnationCriteria,
    StopCriteria,
    ToolRegistry,
    TraceWriter,
)
from qitos.core.errors import RuntimeErrorInfo, classify_exception
from qitos.runtime.stop_criteria import FinalResultCriteria


@dataclass
class State:
    task: str
    current_step: int = 0
    final_result: Optional[str] = None
    stop_reason: Optional[str] = None
    marker: str = "constant"


class EndlessPolicy(Policy[State, Dict[str, Any], Action]):
    def propose(self, state: State, obs: Dict[str, Any]) -> Decision[Action]:
        return Decision.wait()

    def update(self, state: State, obs: Dict[str, Any], decision: Decision[Action], results: list[Any]) -> State:
        return state


class BranchPolicy(Policy[State, Dict[str, Any], Action]):
    def propose(self, state: State, obs: Dict[str, Any]) -> Decision[Action]:
        if state.current_step == 0:
            c1 = Decision.act([Action(name="add", args={"a": 1, "b": 2})], meta={"score": 0.1})
            c2 = Decision.act([Action(name="add", args={"a": 40, "b": 2})], meta={"score": 0.9})
            return Decision.branch([c1, c2])
        return Decision.final(str(state.final_result or ""))

    def update(self, state: State, obs: Dict[str, Any], decision: Decision[Action], results: list[Any]) -> State:
        if results:
            state.final_result = str(results[0])
        return state


class StopCritic(Critic):
    def evaluate(self, state: Any, decision: Decision[Any], results: list[Any]) -> Dict[str, Any]:
        return {"action": "stop", "reason": "critic says stop", "score": 0.0}


class RetryThenPassCritic(Critic):
    def __init__(self):
        self.calls = 0

    def evaluate(self, state: Any, decision: Decision[Any], results: list[Any]) -> Dict[str, Any]:
        self.calls += 1
        if self.calls == 1:
            return {"action": "retry", "reason": "first retry"}
        return {"action": "continue", "reason": "ok"}


class TestTask9StopCriteria:
    def test_stop_criteria_precedence(self):
        state = State(task="done", final_result="42")
        criteria: list[StopCriteria] = [FinalResultCriteria(), MaxStepsCriteria(1)]
        runtime = Runtime(policy=EndlessPolicy(), toolkit=ToolRegistry(), stop_criteria=criteria)
        result = runtime.run(state)
        assert result.state.stop_reason == "final_result"

    def test_max_runtime_stop_reason(self):
        runtime = Runtime(
            policy=EndlessPolicy(),
            toolkit=ToolRegistry(),
            budget=RuntimeBudget(max_steps=100, max_runtime_seconds=0.0),
        )
        result = runtime.run(State(task="timeout"))
        assert result.state.stop_reason == "max_runtime"

    def test_stagnation_stop_reason(self):
        criteria: list[StopCriteria] = [StagnationCriteria(max_stagnant_steps=1), MaxStepsCriteria(10)]
        runtime = Runtime(policy=EndlessPolicy(), toolkit=ToolRegistry(), stop_criteria=criteria)
        result = runtime.run(State(task="stagnate"))
        assert result.state.stop_reason == "stagnation"


class TestTask10RecoveryDiagnostics:
    def test_exception_classifier_categories(self):
        info_model = classify_exception(TimeoutError("model timeout"), "propose", 0)
        assert info_model.category == ErrorCategory.MODEL

        info_tool = classify_exception(RuntimeError("tool failed"), "act", 1)
        assert info_tool.category == ErrorCategory.TOOL

        info_state = classify_exception(TypeError("state mismatch"), "update", 2)
        assert info_state.category == ErrorCategory.STATE

        info_parse = classify_exception(ValueError("xml parse error"), "propose", 3)
        assert info_parse.category == ErrorCategory.PARSE

    def test_failure_report_contains_decision_and_recommendation(self):
        policy = RecoveryPolicy(max_recoveries_per_run=0)
        decision = policy.handle(state={}, phase="act", step_id=1, exc=RuntimeError("tool boom"))
        assert decision.continue_run is False
        report = policy.tracker.summary()
        failure = report["failures"][0]
        assert failure["decision"] == "stop"
        assert "recommendation" in failure


class TestTask11SearchAdapter:
    def test_greedy_search_selects_best_branch(self):
        registry = ToolRegistry()

        def add(a: int, b: int) -> int:
            return a + b

        registry.register(add, name="add")

        runtime = Runtime(
            policy=BranchPolicy(),
            toolkit=registry,
            search_adapter=GreedySearchAdapter(top_k=1),
            budget=RuntimeBudget(max_steps=4),
        )
        result = runtime.run(State(task="branch"))
        assert result.state.final_result == "42"


class TestTask12CriticIntegration:
    def test_critic_stop_controls_runtime(self, tmp_path: Path):
        registry = ToolRegistry()

        def add(a: int, b: int) -> int:
            return a + b

        registry.register(add, name="add")

        writer = TraceWriter(output_dir=str(tmp_path), run_id="critic-stop")
        runtime = Runtime(
            policy=BranchPolicy(),
            toolkit=registry,
            critics=[StopCritic()],
            budget=RuntimeBudget(max_steps=4),
            trace_writer=writer,
        )
        result = runtime.run(State(task="critic"))
        assert result.state.stop_reason == "critic_stop"

        step_lines = (tmp_path / "critic-stop" / "steps.jsonl").read_text(encoding="utf-8").splitlines()
        first_step = json.loads(step_lines[0])
        assert first_step["critic_outputs"][0]["action"] == "stop"

    def test_critic_retry_then_continue(self):
        registry = ToolRegistry()

        def add(a: int, b: int) -> int:
            return a + b

        registry.register(add, name="add")

        critic = RetryThenPassCritic()
        runtime = Runtime(
            policy=BranchPolicy(),
            toolkit=registry,
            critics=[critic],
            budget=RuntimeBudget(max_steps=5),
            search_adapter=GreedySearchAdapter(top_k=1),
        )
        result = runtime.run(State(task="retry"))
        assert critic.calls >= 2
        assert result.state.final_result == "42"
