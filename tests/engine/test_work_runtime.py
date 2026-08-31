from __future__ import annotations

import hashlib
import threading
from typing import Any, Callable

import pytest

from dataclasses import dataclass
from qitos.core.action import Action
from qitos.core.agent_module import AgentModule
from qitos.core.decision import Decision
from qitos.core.state import StateSchema
from qitos.core.session import SessionLifecycle, SessionSnapshot
from qitos.core.session import PauseSafety, SafeBoundaryKind
from qitos.core.tool_registry import ToolRegistry
from qitos.core.tool import tool
from qitos.engine.engine import Engine
from qitos.engine.runtime import RuntimeComposition
from qitos.core.work_graph import WorkDescriptor, WorkGraph
from qitos.checkpoint.session import SessionForkReceipt
from qitos.core.context_transfer import ContextTransferReceipt
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
        registry = ToolRegistry()

        @tool(name="noop")
        def noop() -> str:
            return "ok"

        registry.register(noop)
        super().__init__(tool_registry=registry)
        self.name = "parent"

    def init_state(self, task: str, **kwargs: Any) -> _State:
        return _State(task=task)

    def decide(self, state: _State, observation: dict[str, Any]) -> Decision[Action]:
        if state.current_step == 0:
            return Decision.act([Action(name="noop", args={})])
        return Decision.final(answer="done")

    def reduce(self, state: _State, observation: dict[str, Any], decision: Decision[Action]) -> _State:
        return state


class _PauseAtFirstBoundary:
    policy_id = "tests.work_runtime.pause_first"
    supports_pause = True

    def should_pause(self, context: Any) -> bool:
        return context.step_id == 0

    def pause_safety(self, context: Any) -> PauseSafety:
        return PauseSafety(boundary=SafeBoundaryKind.AFTER_MODEL_RESULT)


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

    def dispatch(self, request: WorkDispatch) -> SchedulerHandle:
        self.requests.append(request)
        handle = _FakeHandle(f"third-party:{request.operation_id}")
        self.handles[handle.worker_ref] = handle
        return handle

    def reattach(self, request: WorkDispatch, worker_ref: str) -> SchedulerHandle | None:
        del request
        return self.handles.get(worker_ref)

    def close(self) -> None:
        self.closed = True


class QueueOnceScheduler(IndependentSchedulerFake):
    def __init__(self) -> None:
        super().__init__()
        self.admit = False

    def dispatch(self, request: WorkDispatch) -> SchedulerHandle:
        if not self.admit:
            raise WorkRuntimeError(
                "queue_capacity_exceeded",
                "injected durable admission backpressure",
                operation_id=request.operation_id,
            )
        return super().dispatch(request)


def _descriptor(
    operation_id: str,
    operation: str,
    payload: dict[str, Any],
) -> WorkDescriptor:
    return WorkDescriptor(
        operation_id=operation_id,
        operation=operation,
        parent_session_id="session:parent",
        parent_work_item_id="work:parent",
        child_session_ids=[],
        child_work_item_ids=[],
        agent_refs=[],
        task_input=payload,
        fork_receipts=[],
        transfer_receipts=[],
        budget_allocations=[],
        capability_allocations=[],
        artifact_refs=[],
        resolver_requirements=[],
        graph_depth=0,
        fan_out_width=1,
    )


def _paused_session(work_runtime: DurableWorkRuntime):
    runtime = RuntimeComposition(
        lifecycle_policy=_PauseAtFirstBoundary(),  # type: ignore[arg-type]
        work_runtime=work_runtime,
    )
    session = Engine(_Agent(), runtime=runtime).session("parent task")
    session.run()
    assert session.lifecycle is SessionLifecycle.PAUSED
    return session, runtime


def test_scheduler_conformance_persists_declaration_before_dispatch() -> None:
    graph = WorkGraph("graph:runtime")
    scheduler = IndependentSchedulerFake()
    runtime = DurableWorkRuntime(scheduler)
    observations: list[tuple[str, int]] = []

    def persist() -> None:
        observations.append((graph.operation_receipts[-1].state, len(scheduler.requests)))

    receipt = runtime.submit(
        graph=graph,
        descriptor=_descriptor(
            "delegate:stable", "delegate", {"task": "inspect", "agent": "worker"}
        ),
        persist=persist,
    )

    assert observations[0] == ("declared", 0)
    assert receipt.state == "dispatched"
    scheduler.handles[receipt.worker_ref].finish("done")  # type: ignore[index]
    assert graph.operation_receipts[0].state == "completed"
    assert graph.operation_receipts[0].terminal_receipt_ref


def test_declared_preparation_requires_composition_and_never_dispatches_raw() -> None:
    graph = WorkGraph("graph:declared")
    runtime = DurableWorkRuntime(IndependentSchedulerFake())
    receipt = runtime.declare(
        graph=graph,
        descriptor=_descriptor("delegate:declared", "delegate", {"task": "safe"}),
        persist=lambda: None,
    )
    restored = WorkGraph.from_canonical_dict(graph.to_persistence_dict())
    scheduler = IndependentSchedulerFake()

    recovered = DurableWorkRuntime(scheduler).recover(
        restored,
        persist=lambda: None,
    )

    assert receipt.state == "declared"
    assert recovered == ()
    assert restored.operation_receipts[0].state == "declared"
    assert scheduler.requests == []


def test_same_identity_is_idempotent_and_different_payload_conflicts() -> None:
    graph = WorkGraph("graph:idempotency")
    scheduler = IndependentSchedulerFake()
    runtime = DurableWorkRuntime(scheduler)

    def persist() -> None:
        return None

    first = runtime.submit(
        graph=graph,
        descriptor=_descriptor("spawn:stable", "spawn", {"task": "one"}),
        persist=persist,
    )
    duplicate = runtime.submit(
        graph=graph,
        descriptor=_descriptor("spawn:stable", "spawn", {"task": "one"}),
        persist=persist,
    )

    assert duplicate == first
    assert len(scheduler.requests) == 1
    with pytest.raises(WorkRuntimeError) as caught:
        runtime.submit(
            graph=graph,
            descriptor=_descriptor("spawn:stable", "spawn", {"task": "different"}),
            persist=persist,
        )
    assert caught.value.code == "operation_identity_conflict"


def test_clean_runtime_recovery_never_replays_unattachable_work() -> None:
    graph = WorkGraph("graph:recover")
    first_scheduler = IndependentSchedulerFake()
    DurableWorkRuntime(first_scheduler).submit(
        graph=graph,
        descriptor=_descriptor("fanout:child:0", "fan_out", {"index": 0}),
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
        descriptor=_descriptor("delegate:cancel", "delegate", {"task": "wait"}),
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
    work_runtime = DurableWorkRuntime(scheduler)
    session, _ = _paused_session(work_runtime)
    direct = session.submit_work(
        "delegate",
        {"agent": "parent", "task": "inspect"},
        operation_id="delegate:slot-1",
    )

    adapted = submit_durable_work(
        "delegate",
        {"agent": "parent", "task": "inspect"},
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
    session, runtime = _paused_session(DurableWorkRuntime(scheduler))
    session.spawn("parent", task="background", operation_id="spawn:restore")

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
        if commits > 2:
            raise OSError("store unavailable")

    with pytest.raises(WorkRuntimeError) as caught:
        runtime.submit(
            graph=graph,
            descriptor=_descriptor(
                "delegate:store-failure", "delegate", {"task": "effect"}
            ),
            persist=persist,
        )

    assert caught.value.code == "store_commit_failed_after_dispatch"
    assert scheduler.requests[0].operation_id == "delegate:store-failure"
    assert graph.operation_receipts[0].state == "outcome_unknown"
    assert graph.operation_receipts[0].outcome_unknown is True


def test_spawn_and_join_model_adapters_use_session_runtime() -> None:
    scheduler = IndependentSchedulerFake()
    work_runtime = DurableWorkRuntime(scheduler)
    session, _ = _paused_session(work_runtime)
    context = {
        "work_runtime": work_runtime,
        "session": session,
        "work_graph": session._engine._qitos_work_graph,
        "slot_id": "adapter-slot",
    }

    spawn = SpawnTool().execute(
        {"agent": "parent", "task": "background"}, context
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


def test_default_operation_identity_is_unique_and_retry_is_explicit() -> None:
    scheduler = IndependentSchedulerFake()
    session, _ = _paused_session(DurableWorkRuntime(scheduler))

    first = session.spawn("parent", task="same payload")
    second = session.spawn("parent", task="same payload")
    retry = session.spawn(
        "parent", task="same payload", operation_id=first.operation_id
    )

    assert first.operation_id != second.operation_id
    assert retry == first
    assert len(scheduler.requests) == 2


def test_descriptor_consumes_real_fork_and_context_transfer_receipts() -> None:
    scheduler = IndependentSchedulerFake()
    session, _ = _paused_session(DurableWorkRuntime(scheduler))

    submitted = session.delegate(
        "parent", task="inspect", operation_id="delegate:real-a-b"
    )
    descriptor = WorkDescriptor.from_dict(submitted.descriptor)
    fork = SessionForkReceipt.from_dict(descriptor.fork_receipts[0])
    transfer = ContextTransferReceipt.from_dict(descriptor.transfer_receipts[0])

    assert fork.child_session_id == descriptor.child_session_ids[0]
    assert fork.child_work_item_id == descriptor.child_work_item_ids[0]
    assert transfer.plan.operation_kind == "delegate"
    assert transfer.terminal_disposition == "accepted"
    assert transfer.plan.source_session_id == session.session_id
    assert transfer.plan.source_work_item_id == session.work_item_id
    assert transfer.plan.budget_request.child_work_item_id.value == fork.child_work_item_id


def test_queued_descriptor_is_persisted_and_recovered_without_new_identity() -> None:
    graph = WorkGraph("graph:queued-recovery")
    scheduler = QueueOnceScheduler()
    runtime = DurableWorkRuntime(scheduler)
    commits: list[str] = []

    with pytest.raises(WorkRuntimeError, match="queue_capacity_exceeded"):
        runtime.submit(
            graph=graph,
            descriptor=_descriptor("spawn:queued", "spawn", {"task": "eligible"}),
            persist=lambda: commits.append(graph.operation_receipts[0].state),
        )
    queued = graph.operation_receipts[0]
    assert queued.state == "queued"
    assert queued.admission_state == "queued"
    assert queued.queue_position == 1
    scheduler.admit = True

    recovered = runtime.recover(
        graph,
        persist=lambda: commits.append(graph.operation_receipts[0].state),
    )

    assert recovered[0].operation_id == "spawn:queued"
    assert recovered[0].state == "dispatched"
    assert recovered[0].attempt == 1
    assert len(scheduler.requests) == 1


def test_queue_receipt_commit_failure_rolls_back_to_dispatchable() -> None:
    graph = WorkGraph("graph:queue-commit-failure")
    scheduler = QueueOnceScheduler()
    runtime = DurableWorkRuntime(scheduler)
    commits = 0

    def persist() -> None:
        nonlocal commits
        commits += 1
        if commits == 3:
            raise OSError("injected queue receipt commit failure")

    with pytest.raises(OSError, match="queue receipt"):
        runtime.submit(
            graph=graph,
            descriptor=_descriptor("spawn:queue-commit", "spawn", {"task": "safe"}),
            persist=persist,
        )

    assert graph.operation_receipts[0].state == "dispatchable"
    scheduler.admit = True
    recovered = runtime.recover(graph, persist=lambda: None)
    assert recovered[0].state == "dispatched"
    assert recovered[0].operation_id == "spawn:queue-commit"


def test_handoff_commits_one_owner_and_fences_superseded_source() -> None:
    scheduler = IndependentSchedulerFake()
    session, _ = _paused_session(DurableWorkRuntime(scheduler))

    handoff = session.handoff("parent", operation_id="handoff:owner")
    retry = session.handoff("parent", operation_id="handoff:owner")
    graph = session._engine._qitos_work_graph

    assert retry == handoff
    assert len(graph.transfers) == 1
    assert graph.work_items[session.work_item_id].owner.agent_id != session._agent_id
    with pytest.raises(WorkRuntimeError) as fenced:
        session.spawn("parent", task="late source")
    assert fenced.value.code == "superseded_owner"
    assert len(scheduler.requests) == 1


def test_preparation_crash_reuses_fork_and_original_operation_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = IndependentSchedulerFake()
    session, runtime = _paused_session(DurableWorkRuntime(scheduler))

    def crash_after_fork(**kwargs: Any) -> Any:
        del kwargs
        raise RuntimeError("injected preparation process loss")

    monkeypatch.setattr(session, "_execute_child_transfer", crash_after_fork)
    with pytest.raises(RuntimeError, match="preparation process loss"):
        session.delegate("parent", task="resume prepared child", operation_id="delegate:prepare")

    graph = session._engine._qitos_work_graph
    assert graph.operation_receipts[0].state == "declared"
    assert len(graph.work_items) == 1
    fork_id = "fork_" + hashlib.sha256(b"delegate:prepare:0").hexdigest()[:32]
    first_fork = runtime.checkpoint_store.get_session_fork(fork_id)
    assert first_fork is not None

    clean_scheduler = IndependentSchedulerFake()
    clean_runtime = RuntimeComposition(
        checkpoint_store=runtime.checkpoint_store,
        resolvers=runtime.resolvers.copy(),
        lifecycle_policy=_PauseAtFirstBoundary(),  # type: ignore[arg-type]
        work_runtime=DurableWorkRuntime(clean_scheduler),
    )
    restored = Engine.restore(session.session_id, runtime=clean_runtime)
    recovered = restored.recover_work()
    descriptor = WorkDescriptor.from_dict(recovered[0].descriptor)

    assert recovered[0].operation_id == "delegate:prepare"
    assert recovered[0].state == "dispatched"
    assert clean_scheduler.requests[0].operation_id == "delegate:prepare"
    assert SessionForkReceipt.from_dict(descriptor.fork_receipts[0]) == first_fork
    assert clean_runtime.checkpoint_store.get_session_fork(fork_id) == first_fork


def test_handoff_process_loss_before_and_after_owner_commit_has_one_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = IndependentSchedulerFake()
    session, runtime = _paused_session(DurableWorkRuntime(scheduler))
    original_commit = session._commit_work_graph
    commits = 0

    def fail_before_owner_commit() -> None:
        nonlocal commits
        commits += 1
        if commits == 2:
            raise OSError("injected pre-ownership commit loss")
        original_commit()

    monkeypatch.setattr(session, "_commit_work_graph", fail_before_owner_commit)
    with pytest.raises(OSError, match="pre-ownership"):
        session.handoff("parent", operation_id="handoff:crash-window")
    before = session._engine._qitos_work_graph
    assert before.operation_receipts[0].state == "declared"
    assert before.transfers == []
    assert before.work_items[session.work_item_id].owner.agent_id == session._agent_id

    clean_scheduler = IndependentSchedulerFake()
    clean_runtime = RuntimeComposition(
        checkpoint_store=runtime.checkpoint_store,
        resolvers=runtime.resolvers.copy(),
        lifecycle_policy=_PauseAtFirstBoundary(),  # type: ignore[arg-type]
        work_runtime=DurableWorkRuntime(clean_scheduler),
    )
    restored = Engine.restore(session.session_id, runtime=clean_runtime)
    restored.recover_work()
    committed = restored._engine._qitos_work_graph
    assert len(committed.transfers) == 1
    assert committed.work_items[restored.work_item_id].owner.agent_id != restored._agent_id

    durable_head = clean_runtime.checkpoint_store.get_session_head(
        restored.session_id.value
    )
    assert durable_head is not None
    durable_record = clean_runtime.checkpoint_store.get_session_snapshot(
        durable_head.snapshot_id
    )
    assert durable_record is not None
    durable_snapshot = SessionSnapshot.from_dict(
        durable_record.payload,
        component_registry=clean_runtime.component_registry,
    )
    work_component = next(
        item for item in durable_snapshot.components if item.slot == "work_graph"
    )
    after_graph = WorkGraph.from_canonical_dict(
        work_component.to_dict()["payload"]["graph"]
    )
    assert len(after_graph.transfers) == 1
    assert (
        after_graph.work_items[restored.work_item_id].owner.agent_id
        != restored._agent_id
    )
