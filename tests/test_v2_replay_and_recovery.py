import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from qitos.core.action import Action
from qitos import AgentModule, Decision
from qitos.core.errors import StopReason
from qitos.core.state import StateSchema
from qitos.engine.fsm_engine import FSMEngine
from qitos.engine.recovery import RecoveryPolicy
from qitos.trace import TraceWriter
from qitos.debug import Breakpoint, ReplaySession


@dataclass
class RecoveryState(StateSchema):
    pass


class RecoverableActErrorAgent(AgentModule[RecoveryState, Dict[str, Any], Action]):
    def init_state(self, task: str, **kwargs: Any) -> RecoveryState:
        return RecoveryState(task=task, max_steps=3)

    def observe(self, state: RecoveryState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        return {"step": state.current_step}

    def decide(self, state: RecoveryState, observation: Dict[str, Any]) -> Decision[Action]:
        if state.current_step == 0:
            # no toolkit configured -> ACT error -> recoverable
            return Decision.act(actions=[Action(name="missing_tool", args={})])
        return Decision.final("done")

    def reduce(
        self,
        state: RecoveryState,
        observation: Dict[str, Any],
        decision: Decision[Action],
        action_results: List[Any],
    ) -> RecoveryState:
        return state


class UnrecoverableObserveErrorAgent(AgentModule[RecoveryState, Dict[str, Any], Action]):
    def init_state(self, task: str, **kwargs: Any) -> RecoveryState:
        return RecoveryState(task=task, max_steps=3)

    def observe(self, state: RecoveryState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        raise RuntimeError("observe crashed")

    def decide(self, state: RecoveryState, observation: Dict[str, Any]) -> Decision[Action]:
        return Decision.wait()

    def reduce(
        self,
        state: RecoveryState,
        observation: Dict[str, Any],
        decision: Decision[Action],
        action_results: List[Any],
    ) -> RecoveryState:
        return state


class TestRecoveryPolicy:
    def test_recoverable_act_error_continues(self):
        policy = RecoveryPolicy(max_recoveries_per_run=2)
        engine = FSMEngine(agent=RecoverableActErrorAgent(), recovery_policy=policy)

        result = engine.run("task")

        assert result.state.stop_reason == StopReason.FINAL.value
        report = policy.tracker.summary()
        assert report["failure_count"] == 1
        assert report["failures"][0]["category"] == "tool_error"

    def test_unrecoverable_error_stops(self, tmp_path: Path):
        writer = TraceWriter(output_dir=str(tmp_path), run_id="failed-run")
        policy = RecoveryPolicy(max_recoveries_per_run=2)
        engine = FSMEngine(agent=UnrecoverableObserveErrorAgent(), recovery_policy=policy, trace_writer=writer)

        result = engine.run("task")

        assert result.state.stop_reason == StopReason.UNRECOVERABLE_ERROR.value
        manifest = json.loads((tmp_path / "failed-run" / "manifest.json").read_text())
        assert manifest["status"] == "failed"


class TestReplaySession:
    def test_replay_step_and_breakpoint(self, tmp_path: Path):
        writer = TraceWriter(output_dir=str(tmp_path), run_id="replay-run")
        engine = FSMEngine(agent=RecoverableActErrorAgent(), trace_writer=writer)
        engine.run("task")

        session = ReplaySession(str(tmp_path / "replay-run"))
        assert session.has_next() is True

        snap1 = session.step_into()
        assert snap1.current_event is not None

        bp = Breakpoint(phase="RECOVER")
        snap_bp = session.run_until_breakpoint([bp])
        assert snap_bp.current_event is None or snap_bp.current_event.get("phase") == "RECOVER"

        fork = session.fork_with_step_override(1, {"mode": "final", "final_answer": "override"})
        assert "steps" in fork
