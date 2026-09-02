"""Architecture gates for the S2 G3 runtime convergence."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Any

import pytest

from qitos.core.action import Action, ActionExecutionPolicy
from qitos.core.agent_module import AgentModule
from qitos.core.artifact import ArtifactRef as CoreArtifactRef
from qitos.core.decision import Decision
from qitos.core.state import StateSchema
from qitos.core.session import SessionContractError, SessionErrorCode
from qitos.core.tool import tool
from qitos.core.tool_registry import ToolRegistry
from qitos.engine import Engine
from qitos.engine.runtime import RuntimeComposition
from qitos.tracing.sinks import (
    DurabilityReceipt,
    DurabilityStatus,
    SinkCapabilities,
)
from qitos.tracing.trajectory import ArtifactRef as TrajectoryArtifactRef


ROOT = Path(__file__).resolve().parents[1]


def test_framework_has_one_artifact_ref_implementation() -> None:
    definitions: list[str] = []
    for path in (ROOT / "qitos").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if any(
            isinstance(node, (ast.ClassDef, ast.AsyncFunctionDef))
            and node.name == "ArtifactRef"
            for node in ast.walk(tree)
        ):
            definitions.append(str(path.relative_to(ROOT)))

    assert definitions == ["qitos/core/artifact.py"]


def test_trajectory_uses_canonical_artifact_identity() -> None:
    assert TrajectoryArtifactRef is CoreArtifactRef


@dataclass
class _RecoveryState(StateSchema):
    reduced_batches: int = 0


class _RecoveryAgent(AgentModule[_RecoveryState, dict[str, Any], Action]):
    name = "s2_g3_recovery"

    def __init__(
        self,
        *,
        barrier_entered: threading.Event,
        barrier_release: threading.Event,
        counts: dict[str, int],
    ) -> None:
        registry = ToolRegistry()

        @tool(name="committed_effect", concurrency_safe=True)
        def committed_effect() -> str:
            assert barrier_entered.wait(timeout=5)
            counts["committed_effect"] += 1
            return "committed"

        @tool(name="barrier", concurrency_safe=True)
        def barrier() -> str:
            barrier_entered.set()
            assert barrier_release.wait(timeout=5)
            counts["barrier"] += 1
            return "released"

        @tool(name="eligible_missing", concurrency_safe=True)
        def eligible_missing() -> str:
            counts["eligible_missing"] += 1
            return "recovered"

        registry.register(committed_effect)
        registry.register(barrier)
        registry.register(eligible_missing)
        super().__init__(tool_registry=registry)

    def init_state(self, task: str, **kwargs: Any) -> _RecoveryState:
        return _RecoveryState(task=task, max_steps=3)

    def decide(self, state, observation):
        if state.current_step == 0:
            return Decision.act(
                [
                    Action("committed_effect", action_id="call_effect"),
                    Action("barrier", action_id="call_barrier"),
                    Action("eligible_missing", action_id="call_missing"),
                ]
            )
        return Decision.final("complete")

    def reduce(self, state, observation, decision):
        if decision.mode == "act":
            state.reduced_batches += 1
        else:
            state.final_result = decision.final_answer
        return state


class _PauseOnCommittedSlotSink:
    def __init__(self, barrier_release: threading.Event) -> None:
        self.capabilities = SinkCapabilities(sink_id="tests.s2-g3-control")
        self.session = None
        self.barrier_release = barrier_release
        self.triggered = False
        self.pause_was_non_migratable = False
        self.head_was_running = False

    def receive(self, record):
        payload = record.payload.get("payload", {})
        if (
            not self.triggered
            and payload.get("stage") == "tool_slot_terminal"
            and payload.get("slot_id") == "call_effect"
        ):
            self.triggered = True
            steering = self.session.steer("new constraint")
            assert steering.disposition in {"applied", "queued"}
            accepted = self.session.pause()
            assert accepted.status.value == "accepted"
            self.head_was_running = self.session.lifecycle.value == "running"
            self.pause_was_non_migratable = not (
                self.session._quiescence_receipt.migratable
            )
            self.barrier_release.set()
        return DurabilityReceipt(DurabilityStatus.ACCEPTED, accepted_count=1)

    def flush(self):
        return DurabilityReceipt(DurabilityStatus.PERSISTED)

    def close(self):
        return DurabilityReceipt(DurabilityStatus.PERSISTED)


def test_session_head_recovers_only_safe_missing_slot() -> None:
    entered = threading.Event()
    release = threading.Event()
    counts = {"committed_effect": 0, "barrier": 0, "eligible_missing": 0}
    agent = _RecoveryAgent(
        barrier_entered=entered,
        barrier_release=release,
        counts=counts,
    )
    sink = _PauseOnCommittedSlotSink(release)
    runtime = RuntimeComposition(
        event_sink=sink,
        tool_execution_policy=ActionExecutionPolicy(
            mode="parallel",
            max_concurrency=2,
        ),
    )
    session = Engine(agent, runtime=runtime).session("recover the batch")
    sink.session = session

    parent = session.run()

    assert entered.is_set()
    assert sink.pause_was_non_migratable is True
    assert sink.head_was_running is True
    assert session.lifecycle.value == "paused"
    assert parent.state.reduced_batches == 0
    assert counts == {"committed_effect": 1, "barrier": 1, "eligible_missing": 0}
    partial = session.inspect().tool_batch
    assert partial is not None
    assert partial.closed is False
    assert [slot.slot_id for slot in partial.missing_slots] == ["call_missing"]
    assert all(
        slot.durability_status == "persisted"
        for slot in partial.slots
        if slot.terminal
    )

    restored = Engine.restore(session.session_id, runtime=runtime)
    sink.session = restored
    with pytest.raises(SessionContractError) as stale:
        session._persist_tool_batch(
            partial,
            state=parent.state,
            task="recover the batch",
            step_id=0,
        )
    assert stale.value.error_code is SessionErrorCode.SUPERSEDED_OWNER
    result = restored.run()

    assert result.state.final_result == "complete"
    assert result.state.reduced_batches == 1
    assert counts == {"committed_effect": 1, "barrier": 1, "eligible_missing": 1}
    assert restored.lifecycle.value == "completed"
