"""Conformance tests for canonical checkpoint-backed Session heads."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from qitos.checkpoint import (
    CheckpointConflictError,
    CheckpointSessionErrorCode,
    InMemoryCheckpointStore,
    SessionSnapshotCommit,
    SqliteCheckpointStore,
    Checkpoint,
    CheckpointConfig,
    CheckpointId,
    session_snapshot_from_checkpoint,
)


def _commit(
    generation: int,
    *,
    owner: str = "run_aaaaaaaaaaaaaaaa",
    expected_owner: str = "run_aaaaaaaaaaaaaaaa",
) -> SessionSnapshotCommit:
    return SessionSnapshotCommit(
        session_id="session_aaaaaaaaaaaaaaaa",
        snapshot_id=f"snapshot_{generation:016x}",
        checkpoint_id=f"checkpoint_{generation:016x}",
        owner_run_id=owner,
        lifecycle="created" if generation == 0 else "paused",
        payload={
            "head_generation": generation,
            "lifecycle": "created" if generation == 0 else "paused",
            "created_at": "2026-08-31T00:00:00+00:00",
            "nested": {"items": [generation]},
        },
        expected_generation=None if generation == 0 else generation - 1,
        expected_checkpoint_id=(
            None if generation == 0 else f"checkpoint_{generation - 1:016x}"
        ),
        expected_owner_run_id=None if generation == 0 else expected_owner,
    )


@pytest.fixture(params=["memory", "sqlite"])
def store(request: pytest.FixtureRequest, tmp_path) -> Iterator[object]:
    if request.param == "memory":
        yield InMemoryCheckpointStore()
        return
    sqlite = SqliteCheckpointStore(str(tmp_path / "session-head.db"))
    try:
        yield sqlite
    finally:
        sqlite.close()


def test_atomic_commit_reads_head_snapshot_and_lineage(store) -> None:
    receipt0 = store.commit_session_snapshot(_commit(0))
    receipt1 = store.commit_session_snapshot(_commit(1))

    assert receipt0.durable is True
    assert receipt1.generation == 1
    head = store.get_session_head("session_aaaaaaaaaaaaaaaa")
    assert head is not None
    assert head.snapshot_id == "snapshot_0000000000000001"
    assert head.checkpoint_id == "checkpoint_0000000000000001"
    assert head.generation == 1

    snapshot = store.get_session_snapshot("snapshot_0000000000000000")
    assert snapshot is not None
    assert snapshot.checkpoint_id == "checkpoint_0000000000000000"
    assert snapshot.parent_checkpoint_id is None
    lineage = list(store.list_session_lineage(head.session_id))
    assert [item.generation for item in lineage] == [1, 0]
    assert lineage[0].parent_checkpoint_id == "checkpoint_0000000000000000"


def test_stale_generation_checkpoint_and_owner_are_typed(store) -> None:
    store.commit_session_snapshot(_commit(0))
    store.commit_session_snapshot(_commit(1))

    stale = SessionSnapshotCommit(
        session_id="session_aaaaaaaaaaaaaaaa",
        snapshot_id="snapshot_ffffffffffffffff",
        checkpoint_id="checkpoint_ffffffffffffffff",
        owner_run_id="run_aaaaaaaaaaaaaaaa",
        lifecycle="paused",
        payload={"head_generation": 1, "lifecycle": "paused"},
        expected_generation=0,
        expected_checkpoint_id="checkpoint_0000000000000000",
        expected_owner_run_id="run_aaaaaaaaaaaaaaaa",
    )
    with pytest.raises(CheckpointConflictError) as conflict:
        store.commit_session_snapshot(stale)
    assert conflict.value.error_code is CheckpointSessionErrorCode.GENERATION_CONFLICT

    wrong_owner = _commit(2, expected_owner="run_bbbbbbbbbbbbbbbb")
    with pytest.raises(CheckpointConflictError) as owner:
        store.commit_session_snapshot(wrong_owner)
    assert owner.value.error_code is CheckpointSessionErrorCode.OWNER_CONFLICT


def test_returned_session_data_is_deep_isolated(store) -> None:
    store.commit_session_snapshot(_commit(0))
    first = store.get_session_snapshot("snapshot_0000000000000000")
    assert first is not None
    first.payload["nested"]["items"].append(9)
    second = store.get_session_snapshot("snapshot_0000000000000000")
    assert second is not None
    assert second.payload["nested"]["items"] == [0]


def test_sqlite_head_and_snapshot_survive_reopen(tmp_path) -> None:
    path = tmp_path / "restart.db"
    store = SqliteCheckpointStore(str(path))
    store.commit_session_snapshot(_commit(0))
    store.close()

    reopened = SqliteCheckpointStore(str(path))
    try:
        head = reopened.get_session_head("session_aaaaaaaaaaaaaaaa")
        snapshot = reopened.get_session_snapshot("snapshot_0000000000000000")
        assert head is not None and head.generation == 0
        assert snapshot is not None and snapshot.payload["head_generation"] == 0
    finally:
        reopened.close()


def test_state_only_checkpoint_is_typed_incompatible_not_guessed() -> None:
    store = InMemoryCheckpointStore()
    store.put(
        CheckpointConfig(thread_id="legacy-run"),
        Checkpoint(
            id=CheckpointId("legacy-checkpoint"),
            thread_id="legacy-run",
            step=1,
            state_data={"task": "old state only"},
        ),
        {"run_id": "legacy-run"},
        {},
    )
    from qitos.checkpoint import CheckpointSessionError

    with pytest.raises(CheckpointSessionError) as incompatible:
        session_snapshot_from_checkpoint(
            store, CheckpointConfig(thread_id="legacy-run")
        )
    assert (
        incompatible.value.error_code
        is CheckpointSessionErrorCode.INCOMPATIBLE_CHECKPOINT
    )
