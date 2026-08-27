"""StopReason.INFRASTRUCTURE_INVALID and the commit_action_results hook (e9bde23)."""

from __future__ import annotations

from typing import Any

from qitos import Action, AgentModule, Decision, Engine, StateSchema, ToolRegistry, tool
from qitos.core.errors import StopReason
from qitos.core.tool_result import ToolResult
from qitos.engine import RuntimeBudget
from qitos.engine._model_runtime import DecisionContextConfigurationError


def test_infrastructure_invalid_stop_reason_exists() -> None:
    assert StopReason.INFRASTRUCTURE_INVALID.value == "infrastructure_invalid"


def test_decision_context_configuration_error_maps_to_infrastructure_stop() -> None:
    from qitos.engine._control_runtime import _ControlRuntime

    class _State(StateSchema):
        pass

    class _Engine:
        recovery_handler = None
        context_config = None

        def _dispatch_hook(self, *_args, **_kwargs) -> None:
            return None

        def _emit(self, *_args, **_kwargs) -> None:
            return None

        def _history(self):
            class _Empty:
                _messages: list[Any] = []

            return _Empty()

    runtime = _ControlRuntime.__new__(_ControlRuntime)
    runtime.engine = _Engine()
    state = _State(task="t")
    exc = DecisionContextConfigurationError("packet normalization failed")

    recovered = runtime.recover(state, __import__("qitos.engine.states", fromlist=["RuntimePhase"]).RuntimePhase.DECIDE, exc)

    assert recovered is False
    assert state.stop_reason == StopReason.INFRASTRUCTURE_INVALID


class _ReceiptsAgent(AgentModule[StateSchema, dict[str, Any], Action]):
    def __init__(self) -> None:
        registry = ToolRegistry()
        self.receipts: list[tuple[int, list[str], list[str]]] = []

        @tool(name="noop")
        def noop() -> dict[str, str]:
            return {"ok": "1"}

        registry.register(noop)
        super().__init__(tool_registry=registry)

    def init_state(self, task: str, **kwargs: Any) -> StateSchema:
        return StateSchema(task=task, max_steps=2)

    def decide(self, state: StateSchema, observation: dict[str, Any]) -> Decision[Action]:
        _ = observation
        if state.current_step == 0:
            return Decision.act(actions=[Action(name="noop", args={})])
        return Decision.final("done")

    def reduce(self, state: StateSchema, observation: dict[str, Any], decision: Decision[Action]) -> StateSchema:
        return state

    def commit_action_results(
        self,
        state: StateSchema,
        actions: list[Action],
        results: list[ToolResult],
        step_id: int = 0,
    ) -> None:
        _ = state
        self.receipts.append(
            (step_id, [a.name for a in actions], [r.status for r in results])
        )


def test_commit_action_results_hook_runs_before_history() -> None:
    agent = _ReceiptsAgent()
    Engine(agent=agent, budget=RuntimeBudget(max_steps=2)).run("task")

    assert agent.receipts == [(0, ["noop"], ["success"])]
