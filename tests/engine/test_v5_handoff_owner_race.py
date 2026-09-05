"""Real SQLite ownership interleavings; Events order work, never sleeps."""
from __future__ import annotations

import multiprocessing
import threading
from pathlib import Path

import pytest

from qitos.checkpoint.sqlite_store import SqliteCheckpointStore
from qitos.engine import Engine
from qitos.engine.runtime import RuntimeComposition
from qitos.engine.work_runtime import DurableWorkRuntime, LocalWorkScheduler
from qitos.core.work_graph import WorkGraph
from test_session_fork import ForkAgent, PauseOnce


def _destination(db, identity, restore_allowed, restored, run_allowed, results):
    store = SqliteCheckpointStore(db)
    try:
        runtime = RuntimeComposition(checkpoint_store=store)
        runtime.bind_engine_resources(Engine(ForkAgent(), runtime=runtime))
        assert restore_allowed.wait(10)
        session = Engine.restore(identity, runtime=runtime)
        restored.set()
        assert run_allowed.wait(10)
        result = session.run()
        results.put((result.state.final_result, session.lifecycle.value))
    finally:
        store.close()


class _ObservedScheduler(LocalWorkScheduler):
    def __init__(self, resolver, restore_allowed):
        super().__init__(resolver)
        self.restore_allowed = restore_allowed
        self.callback_done = threading.Event()
        self.callback_errors = []
        self.callbacks = []

    def dispatch(self, request):
        handle = super().dispatch(request)
        original = handle.add_terminal_callback

        def add(callback):
            self.callbacks.append(callback)
            def observed(result, error):
                try:
                    callback(result, error)
                except BaseException as exc:
                    self.callback_errors.append(exc)
                finally:
                    self.callback_done.set()
            original(observed)
            # Source has persisted its dispatched receipt on the baseline.
            self.restore_allowed.set()
        handle.add_terminal_callback = add
        return handle


def test_destination_restores_before_source_terminal(tmp_path: Path):
    context = multiprocessing.get_context("spawn")
    restore_allowed, restored, run_allowed = (context.Event() for _ in range(3))
    results = context.Queue()
    db = str(tmp_path / "handoff.sqlite3")
    store = SqliteCheckpointStore(db)
    children = []

    class Resolver:
        resolver_id = "tests.handoff.events"

        def resolve(self, descriptor):
            def execute():
                worker = context.Process(target=_destination, args=(
                    db, descriptor.parent_session_id, restore_allowed,
                    restored, run_allowed, results,
                ))
                children.append(worker)
                worker.start()
                # The source terminal callback cannot happen before restore.
                assert restored.wait(10)
                return None
            return execute

    scheduler = _ObservedScheduler(Resolver(), restore_allowed)
    runtime = RuntimeComposition(checkpoint_store=store,
                                 lifecycle_policy=PauseOnce(),
                                 work_runtime=DurableWorkRuntime(scheduler))
    source = Engine(ForkAgent(), runtime=runtime).session("handoff race")
    source.run()
    assert source.lifecycle.value == "paused"
    try:
        receipt = source.handoff("fork-agent", operation_id="handoff:race")
        assert scheduler.callback_done.wait(15)
        assert not scheduler.callback_errors, scheduler.callback_errors
        graph = WorkGraph.from_canonical_dict(source.inspect().work_graph)
        operation = next(r for r in graph.operation_receipts if r.operation_id == receipt.operation_id)
        # Transfer acknowledgement must not invent destination business success.
        assert operation.state != "completed"
        run_allowed.set()
        assert results.get(timeout=10) == ("done:2", "completed")
        head, completed = _read_graph(store, source.session_id.value)
        assert completed.operation_receipts[0].state == "completed"
        # Duplicate/late callbacks cannot roll back the destination snapshot.
        for callback in scheduler.callbacks:
            callback(None, None)
            callback(None, RuntimeError("late notification"))
        assert store.get_session_head(source.session_id.value) == head
        from qitos.core.session import SessionContractError, SessionErrorCode
        with pytest.raises(SessionContractError) as stale:
            source.run()
        assert stale.value.error_code is SessionErrorCode.SUPERSEDED_OWNER
        retry = source.handoff("fork-agent", operation_id="handoff:race")
        assert retry.state == "completed"
        from qitos.engine.work_runtime import WorkRuntimeError
        with pytest.raises(WorkRuntimeError, match="operation_identity_conflict"):
            source.handoff("fork-agent", rationale="changed", operation_id="handoff:race")
        assert store.get_session_head(source.session_id.value) == head
    finally:
        restore_allowed.set()
        run_allowed.set()
        scheduler.close()
        for worker in children:
            worker.join(5)
            if worker.is_alive():
                worker.kill()
                worker.join(5)
        store.close()


def _crash_source(db, point, reached, release, identities):
    class BarrierStore(SqliteCheckpointStore):
        def commit_session_snapshot(self, request):
            graph = next((c["payload"]["graph"] for c in request.payload["components"]
                          if c["slot"] == "work_graph"), None)
            transfers = graph and graph["transfers"]
            if transfers and point == "before_commit":
                reached.set()
                assert release.wait(20)
            result = super().commit_session_snapshot(request)
            if transfers and point == "after_commit":
                reached.set()
                assert release.wait(20)
            return result

    class Scheduler:
        scheduler_id = "tests.crash.before_dispatch"

        def dispatch(self, request):
            reached.set()
            assert release.wait(20)
            raise AssertionError("test must kill source before external dispatch")

        def reattach(self, request, worker_ref):
            return None

        def close(self):
            pass

    store = BarrierStore(db)
    runtime = RuntimeComposition(checkpoint_store=store, lifecycle_policy=PauseOnce(),
                                 work_runtime=DurableWorkRuntime(Scheduler()))
    source = Engine(ForkAgent(), runtime=runtime).session("crash handoff")
    source.run()
    identities.put(source.session_id.value)
    source.handoff("fork-agent", operation_id="handoff:crash")


def _read_graph(store, identity):
    head = store.get_session_head(identity)
    snapshot = store.get_session_snapshot(head.snapshot_id)
    graph = next(c["payload"]["graph"] for c in snapshot.payload["components"]
                 if c["slot"] == "work_graph")
    return head, WorkGraph.from_canonical_dict(graph)


@pytest.mark.parametrize("point", ["before_commit", "after_commit", "before_dispatch"])
def test_source_sigkill_at_transfer_boundaries(tmp_path, point):
    context = multiprocessing.get_context("spawn")
    reached, release = context.Event(), context.Event()
    identities = context.Queue()
    db = str(tmp_path / "crash.sqlite3")
    source = context.Process(target=_crash_source, args=(db, point, reached, release, identities))
    source.start()
    try:
        identity = identities.get(timeout=10)
        assert reached.wait(10)
        source.kill()
        source.join(5)
        assert source.exitcode != 0
        store = SqliteCheckpointStore(db)
        try:
            _, graph = _read_graph(store, identity)
            receipt = graph.operation_receipts[0]
            if point == "before_commit":
                assert graph.transfers == []
                assert receipt.state == "declared"
            else:
                assert len(graph.transfers) == 1
                assert receipt.state == ("dispatchable" if point == "after_commit" else "transfer_admitted")
                # A new process can claim and execute from durable facts alone.
                allowed, restored, run_allowed = (context.Event() for _ in range(3))
                results = context.Queue()
                allowed.set()
                run_allowed.set()
                destination = context.Process(target=_destination, args=(
                    db, identity, allowed, restored, run_allowed, results))
                destination.start()
                try:
                    assert results.get(timeout=10) == ("done:2", "completed")
                    destination.join(5)
                    assert destination.exitcode == 0
                    _, completed = _read_graph(store, identity)
                    assert completed.operation_receipts[0].state == "completed"
                finally:
                    if destination.is_alive():
                        destination.kill()
                        destination.join(5)
        finally:
            store.close()
    finally:
        if source.is_alive():
            source.kill()
            source.join(5)


def _competing_restore(db, identity, barrier, results):
    class SameHeadStore(SqliteCheckpointStore):
        armed = False

        def get_session_head(self, session_id):
            head = super().get_session_head(session_id)
            if self.armed:
                self.armed = False
                barrier.wait(10)
            return head

    store = SameHeadStore(db)
    class PauseEveryBoundary(PauseOnce):
        def should_pause(self, context):
            return True

    runtime = RuntimeComposition(checkpoint_store=store, lifecycle_policy=PauseEveryBoundary())
    runtime.bind_engine_resources(Engine(ForkAgent(), runtime=runtime))
    store.armed = True
    try:
        session = Engine.restore(identity, runtime=runtime)
        session.run()
        assert session.lifecycle.value == "paused"
        results.put(("owner", session.current_head.generation.value))
    except Exception as error:
        results.put((type(error).__name__, str(error)))
    finally:
        store.close()


def test_same_expected_head_has_one_winner_then_explicit_restore(tmp_path):
    from test_work_runtime import IndependentSchedulerFake

    db = str(tmp_path / "compete.sqlite3")
    store = SqliteCheckpointStore(db)
    runtime = RuntimeComposition(checkpoint_store=store, lifecycle_policy=PauseOnce(),
                                 work_runtime=DurableWorkRuntime(IndependentSchedulerFake()))
    source = Engine(ForkAgent(), runtime=runtime).session("compete")
    source.run()
    source.handoff("fork-agent")
    context = multiprocessing.get_context("spawn")
    barrier, results = context.Barrier(2), context.Queue()
    workers = [context.Process(target=_competing_restore,
                               args=(db, source.session_id.value, barrier, results)) for _ in range(2)]
    try:
        for worker in workers:
            worker.start()
        outcomes = [results.get(timeout=15) for _ in workers]
        assert sorted(item[0] for item in outcomes) == ["CheckpointConflictError", "owner"]
        fresh = RuntimeComposition(checkpoint_store=store)
        fresh.bind_engine_resources(Engine(ForkAgent(), runtime=fresh))
        restored = Engine.restore(source.session_id, runtime=fresh)
        assert restored.current_head.generation.value > next(x[1] for x in outcomes if x[0] == "owner")
    finally:
        for worker in workers:
            worker.join(5)
            if worker.is_alive():
                worker.kill()
                worker.join(5)
        store.close()


def test_destination_finishes_after_source_sigkill(tmp_path):
    context = multiprocessing.get_context("spawn")
    reached, release = context.Event(), context.Event()
    identities = context.Queue()
    db = str(tmp_path / "kill-after-restore.sqlite3")
    source = context.Process(target=_crash_source, args=(
        db, "before_dispatch", reached, release, identities))
    source.start()
    destination = None
    try:
        identity = identities.get(timeout=10)
        assert reached.wait(10)
        allowed, restored, run_allowed = (context.Event() for _ in range(3))
        results = context.Queue()
        allowed.set()
        destination = context.Process(target=_destination, args=(
            db, identity, allowed, restored, run_allowed, results))
        destination.start()
        assert restored.wait(10)
        source.kill()
        source.join(5)
        run_allowed.set()
        assert results.get(timeout=10) == ("done:2", "completed")
        destination.join(5)
        assert destination.exitcode == 0
        store = SqliteCheckpointStore(db)
        try:
            head, graph = _read_graph(store, identity)
            assert head.lifecycle == "completed"
            assert graph.operation_receipts[0].state == "completed"
        finally:
            store.close()
    finally:
        for worker in (source, destination):
            if worker is not None and worker.is_alive():
                worker.kill()
                worker.join(5)
