"""Session facade tests over the one canonical Engine loop."""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Any

import pytest

from qitos.checkpoint import CheckpointPersistenceError, InMemoryCheckpointStore
from qitos.core.action import Action
from qitos.core.agent_module import AgentModule
from qitos.core.decision import Decision
from qitos.core.session import SessionContractError, SessionErrorCode, SessionLifecycle
from qitos.core.state import StateSchema
from qitos.core.tool import tool
from qitos.core.tool_registry import ToolRegistry
from qitos.engine import Engine
from qitos.engine.runtime import LifecyclePolicy, RuntimeComposition
from qitos.tracing.sinks import (
    DurabilityReceipt,
    DurabilityStatus,
    SinkCapabilities,
)


@dataclass
class CounterState(StateSchema):
    effects: int = 0


class CounterAgent(AgentModule[CounterState, dict[str, Any], Action]):
    name = "counter"

    def __init__(self) -> None:
        registry = ToolRegistry()
        self.calls = 0

        @tool(name="increment")
        def increment() -> int:
            self.calls += 1
            return self.calls

        registry.register(increment)
        super().__init__(tool_registry=registry)

    def init_state(self, task: str, **kwargs: Any) -> CounterState:
        return CounterState(task=task, max_steps=3)

    def decide(
        self, state: CounterState, observation: dict[str, Any]
    ) -> Decision[Action]:
        if state.current_step == 0:
            return Decision.act([Action(name="increment", args={})])
        return Decision.final("done")

    def reduce(
        self,
        state: CounterState,
        observation: dict[str, Any],
        decision: Decision[Action],
    ) -> CounterState:
        if decision.mode == "act":
            state.effects += 1
        elif decision.mode == "final":
            state.final_result = decision.final_answer
        return state


class PauseAfterFirstStep(LifecyclePolicy):
    policy_id = "tests.pause_after_first_step"

    def should_pause(self, context) -> bool:
        return context.step_id == 0


class UnsupportedPausePolicy(LifecyclePolicy):
    policy_id = "tests.no_pause"
    supports_pause = False


class FailPausedCommitStore(InMemoryCheckpointStore):
    def commit_session_snapshot(self, request):
        if request.lifecycle == SessionLifecycle.PAUSED.value:
            raise CheckpointPersistenceError("Injected persistence failure.")
        return super().commit_session_snapshot(request)


class CollectingEventSink:
    def __init__(self) -> None:
        self.events = []
        self.capabilities = SinkCapabilities(sink_id="tests.session-events")

    def receive(self, record):
        self.events.append(record)
        return DurabilityReceipt(DurabilityStatus.ACCEPTED, accepted_count=1)

    def flush(self):
        return DurabilityReceipt(DurabilityStatus.PERSISTED)

    def close(self):
        return DurabilityReceipt(DurabilityStatus.PERSISTED)


def test_beginner_session_path_delegates_to_engine_and_completes() -> None:
    agent = CounterAgent()
    session = Engine(agent).session("count once")

    assert session.inspect().lifecycle is SessionLifecycle.CREATED
    result = session.run()

    assert result.state.final_result == "done"
    assert result.state.effects == 1
    assert agent.calls == 1
    assert session.inspect().lifecycle is SessionLifecycle.COMPLETED
    with pytest.raises(SessionContractError) as terminal:
        session.pause()
    assert terminal.value.error_code is SessionErrorCode.INVALID_LIFECYCLE_OPERATION


def test_cooperative_pause_is_durable_and_restore_gets_new_run() -> None:
    runtime = RuntimeComposition(lifecycle_policy=PauseAfterFirstStep())
    agent = CounterAgent()
    session = Engine(agent, runtime=runtime).session("count once")
    first_run = session.run()

    assert first_run.state.effects == 1
    assert first_run.state.current_step == 1
    assert session.inspect().lifecycle is SessionLifecycle.PAUSED
    assert session._pause_receipt is not None
    session._pause_receipt.require_persisted()
    old_run = session.run_id

    restored = Engine.restore(session.session_id, runtime=runtime)
    assert restored.run_id != old_run
    assert restored.inspect().lifecycle is SessionLifecycle.RESTORING
    result = restored.run(steering="finish")

    assert result.state.effects == 1
    assert result.state.final_result == "done"
    assert agent.calls == 1
    assert restored.inspect().lifecycle is SessionLifecycle.COMPLETED


def test_restore_rejects_a_different_agent_config_digest() -> None:
    runtime = RuntimeComposition(
        lifecycle_policy=PauseAfterFirstStep(),
        launch_metadata={"config_digest": "a" * 64},
    )
    session = Engine(CounterAgent(), runtime=runtime).session("digest-bound")
    session.run()
    mismatched_runtime = RuntimeComposition(
        checkpoint_store=runtime.checkpoint_store,
        resolvers=runtime.resolvers,
        lifecycle_policy=PauseAfterFirstStep(),
        launch_metadata={"config_digest": "b" * 64},
    )

    with pytest.raises(SessionContractError) as mismatch:
        Engine.restore(session.session_id, runtime=mismatched_runtime)

    assert mismatch.value.error_code is SessionErrorCode.CONFIG_DIGEST_MISMATCH
    assert mismatch.value.metadata == {
        "expected_config_digest": "a" * 64,
        "actual_config_digest": "b" * 64,
    }


def test_same_owner_can_continue_a_durably_paused_session() -> None:
    runtime = RuntimeComposition(lifecycle_policy=PauseAfterFirstStep())
    agent = CounterAgent()
    session = Engine(agent, runtime=runtime).session("continue after review")
    session.run()
    owner = session.run_id
    generation = session.current_head.generation.value
    assert session.lifecycle is SessionLifecycle.PAUSED

    result = session.run(steering="review complete; finish")

    assert session.run_id == owner
    assert session.current_head.generation.value > generation
    assert session.lifecycle is SessionLifecycle.COMPLETED
    assert result.state.effects == 1
    assert result.state.final_result == "done"
    assert agent.calls == 1


def test_unsupported_pause_is_typed_and_does_not_start_worker() -> None:
    runtime = RuntimeComposition(lifecycle_policy=UnsupportedPausePolicy())
    session = Engine(CounterAgent(), runtime=runtime).session("count")
    with pytest.raises(SessionContractError) as unsupported:
        session.pause()
    assert unsupported.value.error_code is SessionErrorCode.UNSUPPORTED_CAPABILITY
    assert "session.pause.cooperative" not in session.capabilities()


def test_failed_persistence_never_reports_paused() -> None:
    runtime = RuntimeComposition(
        checkpoint_store=FailPausedCommitStore(),
        lifecycle_policy=PauseAfterFirstStep(),
    )
    session = Engine(CounterAgent(), runtime=runtime).session("count")
    with pytest.raises(SessionContractError) as failed:
        session.run()
    assert failed.value.error_code is SessionErrorCode.PERSISTENCE_FAILED
    assert session.inspect().lifecycle is SessionLifecycle.FAILED
    assert session._pause_receipt is not None
    with pytest.raises(SessionContractError):
        session._pause_receipt.require_persisted()


def test_runtime_event_sink_receives_explicit_session_lineage() -> None:
    sink = CollectingEventSink()
    runtime = RuntimeComposition(event_sink=sink)
    session = Engine(CounterAgent(), runtime=runtime).session("count")
    result = session.run()
    lifecycle_events = [
        event for event in sink.events if event.snapshot_id is not None
    ]
    lifecycles = [event.payload["lifecycle"] for event in lifecycle_events]
    assert lifecycles[0] == "created"
    assert lifecycles[-1] == "completed"
    assert set(lifecycles[1:-1]) == {"running"}
    assert all(event.session_id == session.session_id.value for event in lifecycle_events)
    assert all(event.run_id == result.run_id for event in lifecycle_events)


def test_pause_request_from_caller_is_cooperative_at_next_boundary() -> None:
    entered = threading.Event()
    release = threading.Event()

    class BarrierAgent(CounterAgent):
        name = "barrier"

        def __init__(self) -> None:
            registry = ToolRegistry()

            @tool(name="barrier")
            def barrier() -> str:
                entered.set()
                assert release.wait(timeout=5)
                return "released"

            registry.register(barrier)
            AgentModule.__init__(self, tool_registry=registry)

        def decide(self, state, observation):
            if state.current_step == 0:
                return Decision.act([Action(name="barrier", args={})])
            return Decision.final("done")

    session = Engine(BarrierAgent()).session("wait for pause")
    results = []
    worker = threading.Thread(target=lambda: results.append(session.run()))
    worker.start()
    assert entered.wait(timeout=5)
    accepted = session.pause()
    assert accepted.status.value == "accepted"
    release.set()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert results and results[0].state.current_step == 1
    assert session.inspect().lifecycle is SessionLifecycle.PAUSED
    assert session._pause_receipt is not None
    session._pause_receipt.require_persisted()
