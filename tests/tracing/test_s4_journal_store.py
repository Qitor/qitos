from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path

import pytest

from qitos.core.artifact import ArtifactRef
from qitos.tracing.journal_store import JournalTrajectoryStore
from qitos.tracing.store import StoreIOError, StoreIntegrityError, TrajectoryStoreError
from qitos.tracing.trajectory import RecordKind, TrajectoryQuery, TrajectoryRecord


def _record(index: int) -> TrajectoryRecord:
    return TrajectoryRecord.create(
        RecordKind.SANDBOX if index % 2 else RecordKind.PROVIDER_TRANSACTION,
        record_id=f"record-{index}",
        session_id="session-1",
        run_id="run-1",
        work_item_id="work-1",
        attempt_id=f"attempt-{index}",
        attempt=index,
        owner_id="agent-1",
        owner_generation=2,
        operation_id=f"operation-{index}",
        lifecycle_state="running",
        provider_transaction_id=f"provider-{index}",
        effect_id=f"effect-{index}",
        sandbox_id="sandbox-1",
        monotonic_ns=100 + index,
        payload={"index": index},
    )


def test_journal_store_reopens_after_abrupt_process_exit(tmp_path: Path) -> None:
    path = tmp_path / "trajectory.journal"
    code = "\n".join(
        (
            "import os, sys",
            "from qitos.tracing.journal_store import JournalTrajectoryStore",
            "from qitos.tracing.trajectory import RecordKind, TrajectoryRecord",
            "store = JournalTrajectoryStore(sys.argv[1])",
            "store.append(TrajectoryRecord.create(RecordKind.RUN, "
            "record_id='child-record', run_id='run-1', session_id='session-1'))",
            "os._exit(0)",
        )
    )
    completed = subprocess.run(
        [sys.executable, "-c", code, str(path)],
        check=False,
        env=dict(os.environ),
    )
    assert completed.returncode == 0

    reopened = JournalTrajectoryStore(path)
    assert [item.record_id for item in reopened.read_run("run-1").records] == [
        "child-record"
    ]
    assert reopened.validate_integrity().valid


def test_partial_tail_is_recovered_but_complete_corruption_is_rejected(
    tmp_path: Path,
) -> None:
    path = tmp_path / "trajectory.journal"
    store = JournalTrajectoryStore(path)
    store.append(_record(0))
    store.close()
    with path.open("ab") as handle:
        handle.write(b'{"journal_schema":"interrupted"')

    recovered = JournalTrajectoryStore(path)
    report = recovered.validate_integrity()
    assert report.valid
    assert report.recovered_tail_bytes > 0
    assert len(recovered.query(TrajectoryQuery())) == 1
    recovered.close()

    with path.open("ab") as handle:
        handle.write(b"not-json\n")
    with pytest.raises(StoreIntegrityError, match="invalid_journal_frame"):
        JournalTrajectoryStore(path)


def test_two_store_handles_follow_serialized_writer_policy(tmp_path: Path) -> None:
    path = tmp_path / "trajectory.journal"
    first = JournalTrajectoryStore(path)
    second = JournalTrajectoryStore(path)
    assert "serialized" in first.capabilities.concurrent_writer_policy
    first.append(_record(0))
    second.append(_record(1))
    assert [item.sequence for item in first.query(TrajectoryQuery())] == [0, 1]
    assert [item.sequence for item in second.query(TrajectoryQuery())] == [0, 1]


def test_concurrent_handles_serialize_without_lost_updates(tmp_path: Path) -> None:
    path = tmp_path / "trajectory.journal"
    stores = (JournalTrajectoryStore(path), JournalTrajectoryStore(path))

    def append(index: int) -> None:
        stores[index % 2].append(_record(index))

    with ThreadPoolExecutor(max_workers=4) as pool:
        tuple(pool.map(append, range(20)))

    observed = stores[0].query(TrajectoryQuery(limit=20))
    assert len(observed) == 20
    assert [record.sequence for record in observed] == list(range(20))
    assert {record.record_id for record in observed} == {
        f"record-{index}" for index in range(20)
    }


def test_artifacts_are_referenced_and_reads_are_isolated(tmp_path: Path) -> None:
    path = tmp_path / "trajectory.journal"
    artifact = ArtifactRef(
        artifact_id="artifact-1",
        resolver_key="external-artifact-store",
        sha256=hashlib.sha256(b"artifact bytes live elsewhere").hexdigest(),
        byte_length=29,
        media_type="text/plain",
    )
    record = TrajectoryRecord.create(
        RecordKind.ARTIFACT,
        record_id="artifact-record",
        run_id="run-1",
        artifact_refs=(artifact,),
        payload={"artifact_id": artifact.artifact_id},
    )
    store = JournalTrajectoryStore(path)
    receipt = store.append(record)
    assert receipt.persisted_count == 1

    observed = store.query(TrajectoryQuery(run_id="run-1"))
    observed[0].payload["artifact_id"] = "mutated"
    assert store.query(TrajectoryQuery(run_id="run-1"))[0].payload == {
        "artifact_id": "artifact-1"
    }
    assert store.artifact_refs(TrajectoryQuery(run_id="run-1")) == (artifact,)
    assert b"artifact bytes live elsewhere" not in path.read_bytes()
    assert store.flush().persisted_count == 1
    assert store.close().persisted_count == 1


def test_atomic_batch_rolls_back_memory_on_io_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "trajectory.journal"
    store = JournalTrajectoryStore(path)
    before = path.read_bytes()

    def fail(_document: object) -> None:
        raise StoreIOError("store_append_failed")

    monkeypatch.setattr(store, "_append_frame", fail)
    with pytest.raises(StoreIOError, match="store_append_failed"):
        store.append_batch((_record(0), _record(1)))
    assert path.read_bytes() == before
    assert store.query(TrajectoryQuery()) == ()


def test_index_is_derived_rebuildable_and_query_is_bounded(tmp_path: Path) -> None:
    path = tmp_path / "trajectory.journal"
    store = JournalTrajectoryStore(path, max_query_records=2)
    store.append_batch((_record(0), _record(1), _record(2)))
    index_path = path.with_name(path.name + ".index.json")
    index_path.unlink()

    report = store.rebuild_index()
    assert report.persisted
    assert report.record_count == 3
    assert report.run_count == 1
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["record_count"] == 3
    assert len(store.query(TrajectoryQuery(limit=2))) == 2
    with pytest.raises(TrajectoryStoreError, match="query_requires_pagination"):
        store.query(TrajectoryQuery())
    with pytest.raises(TrajectoryStoreError, match="query_limit_exceeded"):
        store.query(TrajectoryQuery(limit=3))


def test_complete_frame_checksum_corruption_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "trajectory.journal"
    store = JournalTrajectoryStore(path)
    store.append(_record(0))
    store.close()
    line = json.loads(path.read_text(encoding="utf-8"))
    line["records"][0]["payload"]["index"] = 999
    path.write_text(json.dumps(line) + "\n", encoding="utf-8")

    with pytest.raises(StoreIntegrityError, match="journal_frame_digest_mismatch"):
        JournalTrajectoryStore(path)
