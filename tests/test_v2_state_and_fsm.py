from dataclasses import dataclass, field
from typing import Any, Dict, List

import pytest

from qitos import AgentModule, Decision
from qitos.core.state import (
    StateMigrationRegistry,
    StateSchema,
    StateValidationError,
)
from qitos.core.state_validators import StateValidationGate
from qitos.core.skill import ToolRegistry
from qitos.engine.fsm_engine import FSMEngine


@dataclass
class DemoState(StateSchema):
    notes: List[str] = field(default_factory=list)


class DemoAgent(AgentModule[DemoState, Dict[str, Any], Dict[str, Any]]):
    def __init__(self):
        super().__init__(toolkit=ToolRegistry())

        def add(a: int, b: int) -> int:
            return a + b

        self.toolkit.register(add)

    def init_state(self, task: str, **kwargs: Any) -> DemoState:
        return DemoState(task=task, max_steps=3)

    def observe(self, state: DemoState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        return {"task": state.task, "step": state.current_step}

    def decide(self, state: DemoState, observation: Dict[str, Any]) -> Decision[Dict[str, Any]]:
        if state.current_step == 0:
            return Decision.act(actions=[{"name": "add", "args": {"a": 20, "b": 22}}])
        return Decision.final("42")

    def reduce(
        self,
        state: DemoState,
        observation: Dict[str, Any],
        decision: Decision[Dict[str, Any]],
        action_results: List[Any],
    ) -> DemoState:
        if action_results:
            state.notes.append(str(action_results[0]))
        return state


class TestStateSchemaV2:
    def test_state_unknown_field_strict(self):
        with pytest.raises(StateValidationError):
            DemoState.from_dict({"task": "x", "unknown": 1}, strict=True)

    def test_state_migration_registry(self):
        registry = StateMigrationRegistry()
        registry.register(1, 2, lambda payload: {**payload, "migrated": True})

        payload = registry.migrate({"schema_version": 1, "task": "a"}, 1, 2)
        assert payload["migrated"] is True

    def test_validation_gate(self):
        state = DemoState(task="x", current_step=2, max_steps=1)
        gate = StateValidationGate()
        with pytest.raises(StateValidationError):
            gate.before_phase(state, "OBSERVE")


class TestFSMEngineV2:
    def test_fsm_happy_path(self):
        agent = DemoAgent()
        engine = FSMEngine(agent=agent)

        result = engine.run("test task")

        assert result.state.final_result == "42"
        assert result.state.stop_reason == "final"
        assert len(result.records) == 2
        assert any(evt.phase.value == "ACT" for evt in result.events)
        assert result.records[0].action_results == [42]

    def test_fsm_step_budget_stop(self):
        agent = DemoAgent()

        # budget smaller than agent max steps
        from qitos.engine.states import RuntimeBudget

        engine = FSMEngine(agent=agent, budget=RuntimeBudget(max_steps=1))
        result = engine.run("task")

        assert result.state.stop_reason in {"final", "budget_steps", "max_steps"}

    def test_agent_run_returns_final_result(self):
        agent = DemoAgent()
        final_result = agent.run("task")
        assert final_result == "42"

    def test_agent_run_return_state(self):
        agent = DemoAgent()
        result = agent.run("task", return_state=True)
        assert result.state.final_result == "42"

    def test_agent_run_matches_explicit_engine(self):
        agent = DemoAgent()
        by_run = agent.run("task", return_state=True)

        engine = FSMEngine(agent=agent)
        by_engine = engine.run("task")

        assert by_run.state.final_result == by_engine.state.final_result
        assert by_run.state.stop_reason == by_engine.state.stop_reason
