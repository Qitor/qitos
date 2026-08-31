from __future__ import annotations

import threading
from typing import Any, Callable

import pytest

from dataclasses import dataclass
from qitos.core.action import Action
from qitos.core.agent_module import AgentModule
from qitos.core.decision import Decision
from qitos.core.state import StateSchema
from qitos.core.session import SessionLifecycle
from qitos.core.tool_registry import ToolRegistry
from qitos.engine.engine import Engine
from qitos.engine.runtime import RuntimeComposition
from qitos.core.work_graph import WorkGraph
from qitos.engine.work_runtime import (
    DurableWorkRuntime,
    SchedulerHandle,
    WorkDispatch,
    WorkRuntimeError,
)
from qitos.kit.tool.agent.durable_adapter import JoinTool, SpawnTool, submit_durable_work


@dataclass
class _State(StateSchema):
    pass


class _Agent(AgentModule[_State, dict[str, Any], Action]):
    def __init__(self) -> None:
        super().__init__(tool_registry=ToolRegistry())
        self.name = "parent"

    def init_state(self, task: str, **kwargs: Any) -> _State:
        return _State(task=task)

    def decide(self, state: _State, observation: dict[str, Any]) -> Decision[Action]:
        return Decision.final(answer="done")

    def reduce(self, state: _State, observation: dict[str, Any], decision: Decision[Action]) -> _State:
        return state


class _FakeHandle:
    def __init__(self, worker_ref: str) -> None:
        self.worker_ref = worker_ref
        self.callback: Callable[[Any, BaseException | None], None] | None = None
        self.cancel_requested = False

    def add_terminal_callback(
        self, callback: Callable[[Any, BaseException | None], None]
    ) -> None:
        self.callback = callback

    def request_cancel(self) -> bool:
        self.cancel_requested = True
        return False

    def finish(self, value: Any = None, error: BaseException | None = None) -> None:
        assert self.callback is not None
        self.callback(value, error)


class IndependentSchedulerFake:
    """Third-party-style fake: no executor/store/Engine knowledge."""

    scheduler_id = "third.party.fake"

    def __init__(self) -> None:
        self.requests: list[WorkDispatch] = []
        self.handles: dict[str, _FakeHandle] = {}
        self.closed = False

    def dispatch(self, request: WorkDispatch, worker: Callable[[], Any]) -> SchedulerHandle:
        del worker
        self.requests.append(request)
        handle = _FakeHandle(f"third-party:{request.operation_id}")
        self.handles[handle.worker_ref] = handle
        return handle

    def reattach(self, request: WorkDispatch, worker_ref: str) -> SchedulerHandle | None:
        del request
        return self.handles.get(worker_ref)

    def close(self) -> None:
        self.closed = True


def test_scheduler_conformance_persists_declaration_before_dispatch() -> None:
    graph = WorkGraph("graph:runtime")
    scheduler = IndependentSchedulerFake()
    runtime = DurableWorkRuntime(scheduler)
    observations: list[tuple[str, int]] = []

    def persist() -> None:
        observations.append((graph.operation_receipts[-1].state, len(scheduler.requests)))

    receipt = runtime.submit(
        graph=graph,
        operation_id="delegate:stable",
        operation="delegate",
        payload={"task": "inspect", "agent": "worker"},
        worker=lambda: "done",
        persist=persist,
    )

    assert observations[0] == ("declared", 0)
    assert receipt.state == "dispatched"
    scheduler.handles[receipt.worker_ref].finish("done")  # type: ignore[index]
    assert graph.operation_receipts[0].state == "completed"
    assert graph.operation_receipts[0].terminal_receipt_ref


def test_same_identity_is_idempotent_and_different_payload_conflicts() -> None:
    graph = WorkGraph("graph:idempotency")
    scheduler = IndependentSchedulerFake()
    runtime = DurableWorkRuntime(scheduler)
    persist = lambda: None
    first = runtime.submit(
        graph=graph,
        operation_id="spawn:stable",
        operation="spawn",
        payload={"task": "one"},
        worker=lambda: None,
        persist=persist,
    )
    duplicate = runtime.submit(
        graph=graph,
        operation_id="spawn:stable",
        operation="spawn",
        payload={"task": "one"},
        worker=lambda: None,
        persist=persist,
    )

    assert duplicate == first
    assert len(scheduler.requests) == 1
    with pytest.raises(WorkRuntimeError) as caught:
        runtime.submit(
            graph=graph,
            operation_id="spawn:stable",
            operation="spawn",
            payload={"task": "different"},
            worker=lambda: None,
            persist=persist,
        )
    assert caught.value.code == "operation_identity_conflict"


def test_clean_runtime_recovery_never_replays_unattachable_work() -> None:
    graph = WorkGraph("graph:recover")
    first_scheduler = IndependentSchedulerFake()
    DurableWorkRuntime(first_scheduler).submit(
        graph=graph,
        operation_id="fanout:child:0",
        operation="fan_out",
        payload={"index": 0},
        worker=lambda: None,
        persist=lambda: None,
    )
    restored = WorkGraph.from_canonical_dict(graph.to_persistence_dict())
    commits = threading.Event()

    unknown = DurableWorkRuntime(IndependentSchedulerFake()).recover(
        restored,
        persist=commits.set,
    )

    assert commits.is_set()
    assert len(unknown) == 1
    assert unknown[0].state == "outcome_unknown"
    assert unknown[0].outcome_unknown is True


def test_cancellation_does_not_claim_running_fake_stopped() -> None:
    graph = WorkGraph("graph:cancel")
    scheduler = IndependentSchedulerFake()
    runtime = DurableWorkRuntime(scheduler)
    runtime.submit(
        graph=graph,
        operation_id="delegate:cancel",
        operation="delegate",
        payload={"task": "wait"},
        worker=lambda: None,
        persist=lambda: None,
    )

    receipt = runtime.request_cancel(
        graph,
        "delegate:cancel",
        persist=lambda: None,
    )

    assert receipt.state == "cancellation_requested_worker_still_running"
    assert receipt.outcome_unknown is True


def test_session_direct_and_tool_adapter_share_operation_receipt() -> None:
    scheduler = IndependentSchedulerFake()
    work_runtime = DurableWorkRuntime(
        scheduler,
        child_runner=lambda operation, payload: {"operation": operation, **payload},
    )
    session = Engine(
        _Agent(), runtime=RuntimeComposition(work_runtime=work_runtime)
    ).session("parent task")
    direct = session.submit_work(
        "delegate",
        {"agent": "worker", "task": "inspect"},
        operation_id="delegate:slot-1",
    )

    adapted = submit_durable_work(
        "delegate",
        {"agent": "worker", "task": "inspect"},
        {
            "work_runtime": work_runtime,
            "session": session,
            "work_graph": session._engine._qitos_work_graph,
            "slot_id": "slot-1",
        },
    )

    assert adapted is not None
    assert adapted["operation_id"] == direct.operation_id
    assert adapted["payload_digest"] == direct.payload_digest
    assert len(scheduler.requests) == 1


def test_session_snapshot_restores_logical_graph_without_live_handle() -> None:
    scheduler = IndependentSchedulerFake()
    runtime = RuntimeComposition(
        work_runtime=DurableWorkRuntime(
            scheduler,
            child_runner=lambda operation, payload: None,
        )
    )
    session = Engine(_Agent(), runtime=runtime).session("restore graph")
    session.spawn("worker", task="background", operation_id="spawn:restore")
    head = session._require_head()
    state, task, step_id = session._restore_core_state(session._load_snapshot(head))
    session._commit_snapshot(
        state=state,
        task=task,
        lifecycle=SessionLifecycle.PAUSED,
        step_id=step_id,
        expected_head=head,
    )

    clean_runtime = RuntimeComposition(
        checkpoint_store=runtime.checkpoint_store,
        resolvers=runtime.resolvers.copy(),
        work_runtime=DurableWorkRuntime(IndependentSchedulerFake()),
    )
    restored = Engine.restore(session.session_id, runtime=clean_runtime)
    graph = restored._engine._qitos_work_graph

    assert graph.operation_receipts[0].operation_id == "spawn:restore"
    unknown = clean_runtime.work_runtime.recover(
        graph,
        persist=restored._commit_work_graph,
    )
    assert unknown[0].outcome_unknown is True


def test_store_failure_after_dispatch_is_typed_unknown_not_replayed() -> None:
    graph = WorkGraph("graph:store-failure")
    scheduler = IndependentSchedulerFake()
    runtime = DurableWorkRuntime(scheduler)
    commits = 0

    def persist() -> None:
        nonlocal commits
        commits += 1
        if commits > 1:
            raise OSError("store unavailable")

    with pytest.raises(WorkRuntimeError) as caught:
        runtime.submit(
            graph=graph,
            operation_id="delegate:store-failure",
            operation="delegate",
            payload={"task": "effect"},
            worker=lambda: None,
            persist=persist,
        )

    assert caught.value.code == "store_commit_failed_after_dispatch"
    assert scheduler.requests[0].operation_id == "delegate:store-failure"
    assert graph.operation_receipts[0].state == "outcome_unknown"
    assert graph.operation_receipts[0].outcome_unknown is True


def test_spawn_and_join_model_adapters_use_session_runtime() -> None:
    scheduler = IndependentSchedulerFake()
    work_runtime = DurableWorkRuntime(
        scheduler, child_runner=lambda operation, payload: None
    )
    session = Engine(
        _Agent(), runtime=RuntimeComposition(work_runtime=work_runtime)
    ).session("adapter parity")
    context = {
        "work_runtime": work_runtime,
        "session": session,
        "work_graph": session._engine._qitos_work_graph,
        "slot_id": "adapter-slot",
    }

    spawn = SpawnTool().execute(
        {"agent": "worker", "task": "background"}, context
    )
    context["slot_id"] = "join-slot"
    join = JoinTool().execute(
        {"children": [spawn["operation_id"]], "policy": "all"}, context
    )

    assert spawn["operation"] == "spawn"
    assert join["operation"] == "join"
    assert [request.operation_id for request in scheduler.requests] == [
        "spawn:adapter-slot",
        "join:join-slot",
    ]
