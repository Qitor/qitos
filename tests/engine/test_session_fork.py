"""Deterministic Session fork, lineage, isolation, and ownership tests."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterator, Optional, Sequence

import pytest

from qitos.checkpoint.memory_store import InMemoryCheckpointStore
from qitos.checkpoint.session import (
    ATOMIC_SESSION_FORK,
    CheckpointPersistenceError,
    SessionForkRequest,
    SessionForkReceipt,
    SessionHeadRecord,
    SessionSnapshotCommit,
)
from qitos.checkpoint.sqlite_store import SqliteCheckpointStore
from qitos.checkpoint.store import (
    Checkpoint,
    CheckpointConfig,
    CheckpointMetadata,
    CheckpointStore,
    CheckpointTuple,
    PendingWrite,
    StateVersions,
)
from qitos.core.action import Action
from qitos.core.agent_module import AgentModule
from qitos.core.decision import Decision
from qitos.core.session import (
    CheckpointIdentity,
    ForkLineageSnapshotComponent,
    SessionContractError,
    SessionErrorCode,
    SessionLifecycle,
    SessionOperation,
    SessionSnapshot,
    SnapshotIdentity,
    lifecycle_allows,
)
from qitos.core.state import StateSchema
from qitos.core.tool import tool
from qitos.core.tool_registry import ToolRegistry
from qitos.engine import Engine
from qitos.engine.runtime import RuntimeComposition


FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "s3" / "lane_a"


@dataclass
class ForkState(StateSchema):
    reductions: int = 0


class ForkAgent(AgentModule[ForkState, dict[str, Any], Action]):
    name = "fork-agent"

    def __init__(self) -> None:
        registry = ToolRegistry()

        @tool(name="noop")
        def noop() -> str:
            return "ok"

        registry.register(noop)
        super().__init__(tool_registry=registry)

    def init_state(self, task: str, **kwargs: Any) -> ForkState:
        return ForkState(task=task, max_steps=4)

    def decide(self, state: ForkState, observation: dict[str, Any]) -> Decision[Action]:
        if state.current_step >= 2:
            return Decision.final(f"done:{state.current_step}")
        return Decision.act([Action(name="noop", args={})])

    def reduce(
        self,
        state: ForkState,
        observation: dict[str, Any],
        decision: Decision[Action],
    ) -> ForkState:
        state.reductions += 1
        if decision.mode == "final":
            state.final_result = decision.final_answer
        return state


@dataclass
class IncompatibleForkState(StateSchema):
    incompatible: bool = True


class IncompatibleForkAgent(ForkAgent):
    name = "fork-agent"

    def init_state(self, task: str, **kwargs: Any) -> IncompatibleForkState:
        return IncompatibleForkState(task=task, max_steps=4)


class PauseOnce:
    policy_id = "tests.fork.pause_once"
    supports_pause = True

    def should_pause(self, context: Any) -> bool:
        return context.step_id == 0

    def pause_safety(self, context: Any):
        from qitos.core.session import PauseSafety, SafeBoundaryKind

        return PauseSafety(boundary=SafeBoundaryKind.AFTER_MODEL_RESULT)


class CommitOnlyStore(InMemoryCheckpointStore):
    def session_capabilities(self) -> frozenset[str]:
        return super().session_capabilities() - {ATOMIC_SESSION_FORK}


class FailForkStore(InMemoryCheckpointStore):
    failed_child_id: Optional[str] = None

    def fork_session_snapshot(self, request: SessionForkRequest):
        self.failed_child_id = request.child_commit.session_id
        raise CheckpointPersistenceError("injected fork transaction failure")


class IndependentCheckpointStore(CheckpointStore):
    """Third-party-style implementation delegating only the public protocol."""

    def __init__(self) -> None:
        self.backend = InMemoryCheckpointStore()

    def put(
        self,
        config: CheckpointConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: StateVersions,
    ) -> CheckpointConfig:
        return self.backend.put(config, checkpoint, metadata, new_versions)

    def get_tuple(self, config: CheckpointConfig) -> Optional[CheckpointTuple]:
        return self.backend.get_tuple(config)

    def list(
        self,
        config: CheckpointConfig,
        *,
        limit: Optional[int] = None,
        before: Optional[CheckpointConfig] = None,
    ) -> Iterator[CheckpointTuple]:
        return self.backend.list(config, limit=limit, before=before)

    def put_writes(
        self,
        config: CheckpointConfig,
        writes: Sequence[PendingWrite],
        task_id: str,
    ) -> None:
        self.backend.put_writes(config, writes, task_id)

    def delete(self, config: CheckpointConfig) -> None:
        self.backend.delete(config)

    def session_capabilities(self) -> frozenset[str]:
        return self.backend.session_capabilities()

    def commit_session_snapshot(self, request):
        return self.backend.commit_session_snapshot(request)

    def get_session_head(self, session_id: str):
        return self.backend.get_session_head(session_id)

    def get_session_snapshot(self, snapshot_id: str):
        return self.backend.get_session_snapshot(snapshot_id)

    def list_session_lineage(self, session_id: str, *, limit: Optional[int] = None):
        return self.backend.list_session_lineage(session_id, limit=limit)

    def fork_session_snapshot(self, request):
        return self.backend.fork_session_snapshot(request)

    def get_session_fork(self, operation_id: str):
        return self.backend.get_session_fork(operation_id)


@pytest.fixture(params=["memory", "sqlite", "independent"])
def fork_store(request: pytest.FixtureRequest, tmp_path: Path):
    if request.param == "memory":
        yield InMemoryCheckpointStore()
    elif request.param == "independent":
        yield IndependentCheckpointStore()
    else:
        store = SqliteCheckpointStore(str(tmp_path / "fork.db"))
        try:
            yield store
        finally:
            store.close()


def _completed(store: CheckpointStore):
    runtime = RuntimeComposition(checkpoint_store=store)
    session = Engine(ForkAgent(), runtime=runtime).session("fork me")
    session.run()
    return session, runtime


def _restore_child_worker(
    db_path: str,
    child_id: str,
    owner_transferred: Any,
    continue_run: Any,
    result_queue: Any,
) -> None:
    store = SqliteCheckpointStore(db_path)
    try:
        runtime = RuntimeComposition(checkpoint_store=store)
        engine = Engine(ForkAgent(), runtime=runtime)
        runtime.bind_engine_resources(engine)
        restored = Engine.restore(child_id, runtime=runtime)
        owner_transferred.set()
        if not continue_run.wait(timeout=10):
            result_queue.put({"error": "release_timeout"})
            return
        result = restored.run()
        result_queue.put(
            {
                "result": result.state.final_result,
                "generation": restored.current_head.generation.value,
            }
        )
    except Exception as exc:  # pragma: no cover - reported across process boundary
        result_queue.put({"error": f"{type(exc).__name__}:{exc}"})
    finally:
        store.close()


def test_current_head_fork_is_distinct_explicit_and_source_immutable(fork_store) -> None:
    source, _ = _completed(fork_store)
    source_head = source.current_head
    source_record = fork_store.get_session_snapshot(source_head.snapshot_id.value)
    assert source_record is not None
    source_bytes = json.dumps(source_record.payload, sort_keys=True)

    child = source.fork()
    receipt = child.fork_receipt

    assert receipt is not None
    assert child.session_id != source.session_id
    assert child.run_id != source.run_id
    assert child.work_item_id != source.work_item_id
    assert child.attempt_id != source.attempt_id
    assert child.current_head.generation.value == 0
    assert child.current_head.owner_run_id == child.run_id
    assert receipt.source_session_id == source.session_id.value
    assert receipt.source_snapshot_id == source_head.snapshot_id.value
    assert receipt.source_checkpoint_id == source_head.checkpoint_id.value
    assert receipt.source_work_item_id == source.work_item_id.value
    assert fork_store.get_session_fork(receipt.operation_id) == receipt
    assert source.current_head == source_head
    after = fork_store.get_session_snapshot(source_head.snapshot_id.value)
    assert after is not None
    assert json.dumps(after.payload, sort_keys=True) == source_bytes


def test_historical_snapshot_fork_and_source_child_continuation_are_isolated() -> None:
    store = InMemoryCheckpointStore()
    runtime = RuntimeComposition(
        checkpoint_store=store,
        lifecycle_policy=PauseOnce(),  # type: ignore[arg-type]
    )
    source = Engine(ForkAgent(), runtime=runtime).session("branch history")
    source.run()
    paused_head = source.current_head
    paused_record = store.get_session_snapshot(paused_head.snapshot_id.value)
    assert paused_record is not None
    explicit = SessionSnapshot.from_dict(
        paused_record.payload, component_registry=runtime.component_registry
    )

    resumed = Engine.restore(source.session_id, runtime=runtime)
    resumed.run()
    completed_head = resumed.current_head
    child = resumed.fork(snapshot=explicit)
    child_result = child.run()

    assert child.fork_receipt is not None
    assert child.fork_receipt.source_snapshot_id == paused_head.snapshot_id.value
    assert child_result.state.current_step == 2
    assert resumed.current_head == completed_head
    assert store.get_session_snapshot(paused_head.snapshot_id.value) == paused_record


def test_duplicate_operation_is_typed_and_does_not_create_second_child() -> None:
    store = InMemoryCheckpointStore()
    source, _ = _completed(store)
    first = source.fork(operation_id="fork_aaaaaaaaaaaaaaaa")
    before = tuple(store._session_heads)  # white-box count proves no half-child
    with pytest.raises(SessionContractError) as duplicate:
        source.fork(operation_id="fork_aaaaaaaaaaaaaaaa")
    assert duplicate.value.error_code is SessionErrorCode.DUPLICATE_FORK_OPERATION
    assert tuple(store._session_heads) == before
    assert store.get_session_fork("fork_aaaaaaaaaaaaaaaa") == first.fork_receipt


def test_invalid_lifecycle_missing_and_session_mismatch_are_typed() -> None:
    store = InMemoryCheckpointStore()
    created = Engine(ForkAgent(), runtime=RuntimeComposition(checkpoint_store=store)).session(
        "not safe"
    )
    with pytest.raises(SessionContractError) as invalid:
        created.fork()
    assert invalid.value.error_code is SessionErrorCode.INVALID_LIFECYCLE_OPERATION

    created.run()
    with pytest.raises(SessionContractError) as missing:
        created.fork(SnapshotIdentity("snapshot_aaaaaaaaaaaaaaaa"))
    assert missing.value.error_code is SessionErrorCode.SNAPSHOT_NOT_FOUND

    other, _ = _completed(store)
    with pytest.raises(SessionContractError) as mismatch:
        created.fork(other.current_head.snapshot_id)
    assert mismatch.value.error_code is SessionErrorCode.SNAPSHOT_SESSION_MISMATCH


def test_corrupt_source_snapshot_and_unsupported_store_are_typed() -> None:
    store = InMemoryCheckpointStore()
    source, _ = _completed(store)
    record = store.get_session_snapshot(source.current_head.snapshot_id.value)
    assert record is not None
    entry = store._store[record.checkpoint_id]  # type: ignore[index]
    entry.checkpoint.state_data["session_snapshot"]["integrity"]["digest"] = "0" * 64
    with pytest.raises(SessionContractError) as corrupt:
        source.fork()
    assert corrupt.value.error_code is SessionErrorCode.CORRUPT_SNAPSHOT

    unsupported, _ = _completed(CommitOnlyStore())
    with pytest.raises(SessionContractError) as capability:
        unsupported.fork()
    assert capability.value.error_code is SessionErrorCode.UNSUPPORTED_CAPABILITY


def test_store_failure_leaves_no_child_head() -> None:
    store = FailForkStore()
    source, _ = _completed(store)
    with pytest.raises(SessionContractError) as failed:
        source.fork()
    assert failed.value.error_code is SessionErrorCode.PERSISTENCE_FAILED
    assert store.failed_child_id is not None
    assert store.get_session_head(store.failed_child_id) is None


def test_source_owner_cannot_advance_child_head() -> None:
    store = InMemoryCheckpointStore()
    source, _ = _completed(store)
    child = source.fork()
    head = child.current_head
    record = store.get_session_snapshot(head.snapshot_id.value)
    assert record is not None
    payload = dict(record.payload)
    payload["head_generation"] = 1
    with pytest.raises(Exception) as stale:
        store.commit_session_snapshot(
            SessionSnapshotCommit(
                session_id=child.session_id.value,
                snapshot_id=SnapshotIdentity.generate().value,
                checkpoint_id=CheckpointIdentity.generate().value,
                owner_run_id=source.run_id.value,
                lifecycle=SessionLifecycle.PAUSED.value,
                payload=payload,
                expected_generation=0,
                expected_checkpoint_id=head.checkpoint_id.value,
                expected_owner_run_id=source.run_id.value,
            )
        )
    assert getattr(stale.value, "error_code", None).value == "owner_conflict"
    assert child.current_head == head


def test_restored_child_supersedes_original_fork_owner() -> None:
    store = InMemoryCheckpointStore()
    source, runtime = _completed(store)
    child = source.fork()
    original_owner = child.run_id

    restored = Engine.restore(child.session_id, runtime=runtime)
    assert restored.run_id != original_owner
    with pytest.raises(SessionContractError) as stale:
        child.run()
    assert stale.value.error_code is SessionErrorCode.SUPERSEDED_OWNER
    assert restored.current_head.owner_run_id == restored.run_id


def test_fork_lifecycle_matrix_is_explicit_for_terminal_and_transient_states() -> None:
    allowed = {
        SessionLifecycle.PAUSED,
        SessionLifecycle.WAITING_INPUT,
        SessionLifecycle.COMPLETED,
        SessionLifecycle.FAILED,
        SessionLifecycle.CANCELLED,
        SessionLifecycle.SUPERSEDED,
    }
    assert {
        lifecycle
        for lifecycle in SessionLifecycle
        if lifecycle_allows(lifecycle, SessionOperation.FORK)
    } == allowed


def test_missing_resolver_keeps_committed_child_inspectable(tmp_path: Path) -> None:
    db = tmp_path / "resolver.db"
    store = SqliteCheckpointStore(str(db))
    source, _ = _completed(store)
    child = source.fork()
    child_id = child.session_id
    head = child.current_head
    store.close()

    reopened = SqliteCheckpointStore(str(db))
    try:
        runtime = RuntimeComposition(checkpoint_store=reopened)
        with pytest.raises(SessionContractError) as missing:
            Engine.restore(child_id, runtime=runtime)
        assert missing.value.error_code is SessionErrorCode.MISSING_RESOLVER
        assert reopened.get_session_head(child_id.value) == head_to_record(head, "paused")
    finally:
        reopened.close()


def test_incompatible_resolved_component_cannot_claim_child() -> None:
    store = InMemoryCheckpointStore()
    source, _ = _completed(store)
    child = source.fork()
    head = child.current_head

    runtime = RuntimeComposition(checkpoint_store=store)
    incompatible_engine = Engine(IncompatibleForkAgent(), runtime=runtime)
    runtime.bind_engine_resources(incompatible_engine)
    with pytest.raises(SessionContractError) as incompatible:
        Engine.restore(child.session_id, runtime=runtime)
    assert incompatible.value.error_code is SessionErrorCode.RESOLVER_TYPE_MISMATCH
    assert child.current_head == head


def head_to_record(head, lifecycle: str):
    from qitos.checkpoint.session import SessionHeadRecord

    return SessionHeadRecord(
        session_id=head.session_id.value,
        snapshot_id=head.snapshot_id.value,
        checkpoint_id=head.checkpoint_id.value,
        generation=head.generation.value,
        owner_run_id=head.owner_run_id.value,
        lifecycle=lifecycle,
    )


def test_clean_process_restores_and_continues_forked_child(tmp_path: Path) -> None:
    db = tmp_path / "clean-process.db"
    store = SqliteCheckpointStore(str(db))
    source, _ = _completed(store)
    source_head = source.current_head
    child = source.fork()
    child_id = child.session_id.value
    store.close()

    code = """
import json
import sys
from qitos.checkpoint.sqlite_store import SqliteCheckpointStore
from qitos.engine import Engine
from qitos.engine.runtime import RuntimeComposition
from test_session_fork import ForkAgent

store = SqliteCheckpointStore(sys.argv[1])
runtime = RuntimeComposition(checkpoint_store=store)
engine = Engine(ForkAgent(), runtime=runtime)
runtime.bind_engine_resources(engine)
child = Engine.restore(sys.argv[2], runtime=runtime)
result = child.run()
print(json.dumps({"result": result.state.final_result, "generation": child.current_head.generation.value}))
store.close()
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        (str(Path.cwd() / "tests" / "engine"), str(Path.cwd()))
    )
    completed = subprocess.run(
        [sys.executable, "-c", code, str(db), child_id],
        cwd=Path.cwd(),
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout.strip())
    assert result["result"] == "done:2"
    assert result["generation"] > 0

    verify = SqliteCheckpointStore(str(db))
    try:
        assert verify.get_session_head(source.session_id.value) == head_to_record(
            source_head, "completed"
        )
        assert verify.get_session_head(child_id).generation == result["generation"]
    finally:
        verify.close()


def test_cross_process_restore_fences_original_owner_with_events(tmp_path: Path) -> None:
    db = tmp_path / "owner-fence.db"
    store = SqliteCheckpointStore(str(db))
    source, _ = _completed(store)
    child = source.fork()
    child_id = child.session_id.value

    context = multiprocessing.get_context("spawn")
    owner_transferred = context.Event()
    continue_run = context.Event()
    result_queue = context.Queue()
    worker = context.Process(
        target=_restore_child_worker,
        args=(str(db), child_id, owner_transferred, continue_run, result_queue),
    )
    worker.start()
    try:
        assert owner_transferred.wait(timeout=10)
        with pytest.raises(SessionContractError) as stale:
            child.run()
        assert stale.value.error_code is SessionErrorCode.SUPERSEDED_OWNER
        continue_run.set()
        outcome = result_queue.get(timeout=15)
        worker.join(timeout=15)
        assert not worker.is_alive()
        assert worker.exitcode == 0
        assert outcome.get("error") is None
        assert outcome["result"] == "done:2"
        assert outcome["generation"] > 1
    finally:
        continue_run.set()
        worker.join(timeout=5)
        if worker.is_alive():
            worker.terminate()
            worker.join(timeout=5)
        store.close()


def test_producer_bundle_uses_strict_readers_and_bound_digests() -> None:
    manifest = json.loads(
        (FIXTURE_ROOT / "producer-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["implementation_producer_commit"] == (
        "ae62ba1ea5fef7a472609dcb11d23a5f21733410"
    )
    for item in manifest["fixtures"]:
        path = Path(item["path"])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]

    ownership = json.loads(
        (FIXTURE_ROOT / "fork-ownership.json").read_text(encoding="utf-8")
    )
    receipt = SessionForkReceipt.from_dict(ownership["receipt"])
    lineage = ForkLineageSnapshotComponent.from_dict(
        ownership["lineage_component"]
    )
    head = SessionHeadRecord(**ownership["child_head"])
    assert receipt.child_session_id == head.session_id
    assert receipt.child_work_item_id == lineage.work_item_id.value
    assert receipt.source_snapshot_id == lineage.source_snapshot_id.value
    assert receipt.operation_id == lineage.fork_operation_id


def test_failure_fixture_covers_required_typed_cases() -> None:
    matrix = json.loads(
        (FIXTURE_ROOT / "failure-matrix.json").read_text(encoding="utf-8")
    )
    cases = {item["case"]: item["error_code"] for item in matrix["cases"]}
    assert cases == {
        "invalid_lifecycle": "invalid_lifecycle_operation",
        "unsafe_snapshot": "unsafe_pause_boundary",
        "missing_snapshot": "snapshot_not_found",
        "snapshot_session_mismatch": "snapshot_session_mismatch",
        "corrupt_snapshot": "corrupt_snapshot",
        "unsupported_store": "unsupported_capability",
        "persistence_failure": "persistence_failed",
        "generation_conflict": "generation_conflict",
        "superseded_owner": "superseded_owner",
        "missing_resolver": "missing_resolver",
        "incompatible_component": "resolver_type_mismatch",
        "duplicate_fork_operation": "duplicate_fork_operation",
        "unresolved_worker_or_effect": "unresolved_effect",
    }
