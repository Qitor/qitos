"""Independent review counterexamples and public SQLite handoff remediation."""

from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from qitos.core.session import (
    AgentIdentity,
    RunIdentity,
    SessionIdentity,
    SessionLifecycle,
    WorkItemIdentity,
    AttemptIdentity,
)
from qitos.core.work_graph import WorkDescriptor, WorkGraph, WorkItem, WorkOperationReceipt, WorkOwner
from qitos.engine.session_runtime import Session
from qitos.engine.work_runtime import DurableWorkRuntime, WorkRuntimeError


def descriptor(operation, session, work):
    return WorkDescriptor(
        operation, "handoff", session.value, work.value, [], [], [], {}, [], [], [], [], [], [], 0, 1
    )


@pytest.mark.parametrize("bound", [False, True])
def test_review_same_agent_different_work_and_generation(bound):
    owner, source = AgentIdentity.generate(), AgentIdentity.generate()
    graph = WorkGraph("review-graph")
    works = [WorkItemIdentity.generate(), WorkItemIdentity.generate()]
    sessions = [SessionIdentity.generate(), SessionIdentity.generate()]
    for i, (work, session) in enumerate(zip(works, sessions)):
        graph.add_work_item(WorkItem(work, session, "task", "paused", WorkOwner(source, 0)))
        graph.transfer_owner(
            work,
            expected_generation=0,
            to_agent_id=owner,
            transfer_id=f"ownership:{i}",
            context_transfer_ref=f"context:{i}",
        )
        graph.operation_receipts.append(
            WorkOperationReceipt(
                str(i),
                "handoff",
                "a" * 64,
                "transfer_admitted",
                outcome_unknown=True,
                descriptor=replace(
                    descriptor(str(i), session, work),
                    transfer_receipts=[{"receipt_id": f"context:{i}"}] if bound else [],
                ).to_dict(),
            )
        )
    graph = WorkGraph.from_canonical_dict(graph.to_persistence_dict())
    session = object.__new__(Session)
    session._engine = NS(_qitos_work_graph=graph)
    session._work_item_id, session._session_id = works[0], sessions[0]
    session._agent_id, session._run_id = owner, RunIdentity.generate()
    session._attempt_id = AttemptIdentity.generate()
    unrelated = graph.operation_receipts[1]
    session._reconcile_handoff(SessionLifecycle.COMPLETED)
    assert graph.operation_receipts[1] == unrelated
    assert graph.operation_receipts[0].state == ("completed" if bound else "transfer_admitted")
    terminal = graph.operation_receipts[0]
    session._reconcile_handoff(SessionLifecycle.FAILED)
    assert graph.operation_receipts[0] == terminal
    # Same Agent takes ownership again: old generation cannot acquire a new terminal.
    graph.operation_receipts[0] = replace(terminal, state="transfer_admitted", terminal_receipt_ref=None)
    graph.transfer_owner(works[0], expected_generation=1, to_agent_id=source, transfer_id="away")
    graph.transfer_owner(works[0], expected_generation=2, to_agent_id=owner, transfer_id="back")
    prior = graph.operation_receipts[0]
    session._reconcile_handoff(SessionLifecycle.COMPLETED)
    assert graph.operation_receipts[0] == prior


class RejectedScheduler:
    scheduler_id = "tests.known-rejection"

    def __init__(self, code):
        self.code, self.calls = code, 0

    def dispatch(self, request):
        self.calls += 1
        raise WorkRuntimeError(self.code, "SYNTHETIC_PRIVATE_MARKER")

    def reattach(self, request, worker_ref):
        return None

    def close(self):
        pass


@pytest.mark.parametrize(
    "code", ["queue_capacity_exceeded", "scheduler_unavailable", "descriptor_resolution_failed"]
)
def test_known_non_dispatch_persists_and_retry_does_not_duplicate(code):
    scheduler = RejectedScheduler(code)
    runtime = DurableWorkRuntime(scheduler)
    graph, saved = WorkGraph("known-failure"), []
    work = descriptor("op", SessionIdentity.generate(), WorkItemIdentity.generate())

    def persist():
        saved.append(graph.to_persistence_dict())

    with pytest.raises(WorkRuntimeError):
        runtime.submit(graph=graph, descriptor=work, persist=persist)
    recovered = WorkGraph.from_canonical_dict(saved[-1])
    receipt = recovered.operation_receipts[0]
    assert receipt.state == "dispatch_not_started"
    assert receipt.outcome_unknown is False
    assert receipt.admission_state == "closed"
    assert code in receipt.terminal_receipt_ref
    assert "SYNTHETIC" not in str(saved)
    assert runtime.submit(graph=recovered, descriptor=work, persist=persist) == receipt
    assert runtime.recover(recovered, persist=persist) == (receipt,)
    assert scheduler.calls == 1
    with pytest.raises(WorkRuntimeError, match="operation_identity_conflict"):
        runtime.submit(
            graph=recovered, descriptor=replace(work, task_input={"changed": True}), persist=persist
        )


def test_dispatch_ack_loss_stays_unknown():
    scheduler = RejectedScheduler("acknowledgement_lost")
    runtime, graph = DurableWorkRuntime(scheduler), WorkGraph("unknown")
    work = descriptor("op", SessionIdentity.generate(), WorkItemIdentity.generate())
    saved = []
    with pytest.raises(WorkRuntimeError):
        runtime.submit(
            graph=graph, descriptor=work, persist=lambda: saved.append(graph.to_persistence_dict())
        )
    graph = WorkGraph.from_canonical_dict(saved[-1])
    assert graph.operation_receipts[0].outcome_unknown
    runtime.recover(graph, persist=lambda: None)
    runtime.submit(graph=graph, descriptor=work, persist=lambda: None)
    assert scheduler.calls == 1


@pytest.mark.parametrize(
    "code", ["queue_capacity_exceeded", "scheduler_unavailable", "descriptor_resolution_failed"]
)
def test_public_sqlite_known_failure_destination_recovery(tmp_path, code):
    from qitos.checkpoint.sqlite_store import SqliteCheckpointStore
    from qitos.engine import Engine
    from qitos.engine.runtime import RuntimeComposition
    from test_session_fork import ForkAgent, PauseOnce

    scheduler = RejectedScheduler(code)
    store = SqliteCheckpointStore(str(tmp_path / "sessions.sqlite3"))
    runtime = RuntimeComposition(
        checkpoint_store=store, lifecycle_policy=PauseOnce(), work_runtime=DurableWorkRuntime(scheduler)
    )
    agent = ForkAgent()
    engine = Engine(agent, runtime=runtime)
    source = engine.session("current")
    unrelated = engine.session("same agent different work")
    source.run()
    unrelated.run()
    other_head = unrelated.current_head
    with pytest.raises(WorkRuntimeError):
        source.handoff("fork-agent", operation_id="operation")
    graph = WorkGraph.from_canonical_dict(source.inspect().work_graph)
    assert graph.operation_receipts[0].state == "dispatch_not_started"
    assert source.handoff("fork-agent", operation_id="operation").state == "dispatch_not_started"
    identity = source.session_id
    store.close()
    # New store and composition: no retained source engine, scheduler or callback.
    store = SqliteCheckpointStore(str(tmp_path / "sessions.sqlite3"))
    try:
        restored_runtime = RuntimeComposition(checkpoint_store=store)
        restored_runtime.bind_engine_resources(Engine(ForkAgent(), runtime=restored_runtime))
        destination = Engine.restore(identity, runtime=restored_runtime)
        result = destination.run()
        assert result.state.final_result == "done:2"
        graph = WorkGraph.from_canonical_dict(destination.inspect().work_graph)
        assert graph.operation_receipts[0].state == "completed"
        assert store.get_session_head(other_head.session_id.value).snapshot_id == other_head.snapshot_id.value
        assert scheduler.calls == 1
    finally:
        store.close()


@pytest.mark.parametrize("result", [None, "raises"])
def test_local_resolver_failure_proves_no_worker(result):
    from qitos.engine.work_runtime import LocalWorkScheduler

    class Resolver:
        resolver_id = "tests.resolver"

        def resolve(self, descriptor):
            if result == "raises":
                raise WorkRuntimeError("private_resolver_code", "SYNTHETIC_PRIVATE_MARKER")
            return result

    scheduler = LocalWorkScheduler(Resolver(), max_workers=1, queue_capacity=1)
    try:
        runtime, graph = DurableWorkRuntime(scheduler), WorkGraph("resolver-failure")
        work = descriptor("resolve", SessionIdentity.generate(), WorkItemIdentity.generate())
        with pytest.raises(WorkRuntimeError) as caught:
            runtime.submit(graph=graph, descriptor=work, persist=lambda: None)
        assert caught.value.code == "descriptor_resolution_failed"
        assert graph.operation_receipts[0].state == "dispatch_not_started"
        assert "SYNTHETIC" not in str(caught.value)
    finally:
        scheduler.close()


def test_rejection_cannot_write_after_destination_claim(tmp_path):
    from qitos.checkpoint.sqlite_store import SqliteCheckpointStore
    from qitos.checkpoint.session import CheckpointConflictError
    from qitos.engine import Engine
    from qitos.engine.runtime import RuntimeComposition
    from test_session_fork import ForkAgent, PauseOnce

    store = SqliteCheckpointStore(str(tmp_path / "claimed.sqlite3"))
    destination_heads = []

    class Claimed(RejectedScheduler):
        def dispatch(self, request):
            fresh = RuntimeComposition(checkpoint_store=store)
            fresh.bind_engine_resources(Engine(ForkAgent(), runtime=fresh))
            destination = Engine.restore(request.descriptor.parent_session_id, runtime=fresh)
            destination.run()
            destination_heads.append(destination.current_head)
            raise WorkRuntimeError("queue_capacity_exceeded", "no local worker")

    runtime = RuntimeComposition(
        checkpoint_store=store,
        lifecycle_policy=PauseOnce(),
        work_runtime=DurableWorkRuntime(Claimed("unused")),
    )
    source = Engine(ForkAgent(), runtime=runtime).session("fenced")
    source.run()
    try:
        with pytest.raises(CheckpointConflictError):
            source.handoff("fork-agent", operation_id="fenced")
        assert source.current_head == destination_heads[0]
        assert (
            WorkGraph.from_canonical_dict(source.inspect().work_graph).operation_receipts[0].state
            == "completed"
        )
    finally:
        store.close()


def test_public_parent_child_and_same_agent_second_handoff(tmp_path):
    from qitos.checkpoint.sqlite_store import SqliteCheckpointStore
    from qitos.engine import Engine
    from qitos.engine.runtime import RuntimeComposition
    from test_session_fork import ForkAgent, PauseOnce
    from test_work_runtime import IndependentSchedulerFake

    store = SqliteCheckpointStore(str(tmp_path / "parent-child.sqlite3"))
    scheduler = IndependentSchedulerFake()
    runtime = RuntimeComposition(
        checkpoint_store=store, lifecycle_policy=PauseOnce(), work_runtime=DurableWorkRuntime(scheduler)
    )
    source = Engine(ForkAgent(), runtime=runtime).session("parent")
    source.run()
    try:
        child_receipt = source.spawn("fork-agent", task="child task", operation_id="child")
        child_id = child_receipt.descriptor["child_session_ids"][0]
        child_head = store.get_session_head(child_id)
        source.handoff("fork-agent", operation_id="first")

        class PauseAgain(PauseOnce):
            def should_pause(self, context):
                return True

        fresh = RuntimeComposition(
            checkpoint_store=store, lifecycle_policy=PauseAgain(), work_runtime=DurableWorkRuntime(scheduler)
        )
        fresh.bind_engine_resources(Engine(ForkAgent(), runtime=fresh))
        destination = Engine.restore(source.session_id, runtime=fresh)
        destination.run()
        assert destination.lifecycle.value == "paused"
        destination.handoff("fork-agent", operation_id="second")
        again = RuntimeComposition(checkpoint_store=store)
        again.bind_engine_resources(Engine(ForkAgent(), runtime=again))
        final = Engine.restore(source.session_id, runtime=again)
        final.run()
        graph = WorkGraph.from_canonical_dict(final.inspect().work_graph)
        receipts = {r.operation_id: r for r in graph.operation_receipts}
        assert receipts["second"].state == "completed"
        assert receipts["first"].state != "completed"
        assert receipts["child"].state != "completed"
        assert store.get_session_head(child_id) == child_head
    finally:
        scheduler.close()
        store.close()
