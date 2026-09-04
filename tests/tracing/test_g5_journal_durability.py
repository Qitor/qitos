"""Journal acknowledgement, restart and complete-reader G5 regression gates."""

import os
from pathlib import Path

import pytest

from qitos.qita.inspection import ReadOnlyInspection
from qitos.tracing.exporter import CanonicalTrajectoryExporter
from qitos.tracing.journal_store import JournalTrajectoryStore
from qitos.tracing.readers import StoreTrajectoryReader
from qitos.tracing.store import StoreIOError, StoreIntegrityError, TrajectoryStoreError
from qitos.tracing.trajectory import PrivacyView, RecordKind, TrajectoryQuery, TrajectoryRecord


def record(index):
    return TrajectoryRecord.create(RecordKind.RUN, record_id=f"item-{index}",
                                   run_id="run", session_id="session",
                                   payload={"index": index})


@pytest.mark.parametrize("mode", ["zero", "partial_error", "complete_error", "fsync"])
def test_interrupted_write_reports_uncertainty_and_retry_never_duplicates(tmp_path, monkeypatch, mode):
    path = tmp_path / "journal"
    store = JournalTrajectoryStore(path)
    item = record(0)
    original_open, original_sync = Path.open, os.fsync

    class Writer:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.handle.close()

        def fileno(self):
            return self.handle.fileno()

        def write(self, data):
            if mode == "zero":
                return 0
            if mode == "partial_error":
                self.handle.write(data[:len(data) // 2])
                raise OSError("PRIVATE DISK ERROR")
            if mode == "complete_error":
                self.handle.write(data)
                raise OSError("PRIVATE DISK ERROR")
            return self.handle.write(data)

    def opened(self, mode="r", *args, **kwargs):
        handle = original_open(self, mode, *args, **kwargs)
        return Writer(handle) if self == path and mode == "ab" else handle

    monkeypatch.setattr(Path, "open", opened)
    if mode == "fsync":
        def fail_sync(fd):
            raise OSError("PRIVATE DISK ERROR")
        monkeypatch.setattr(os, "fsync", fail_sync)
    with pytest.raises(StoreIOError) as failure:
        store.append(item)
    assert failure.value.durability_unknown is True
    assert "PRIVATE" not in str(failure.value)
    if mode == "fsync":
        assert failure.value.bytes_written == path.stat().st_size > 0
    monkeypatch.setattr(Path, "open", original_open)
    monkeypatch.setattr(os, "fsync", original_sync)
    reopened = JournalTrajectoryStore(path)
    receipt = reopened.append(item)
    assert receipt.persisted_count == 1
    assert len(reopened.read_run("run").records) == 1
    before = path.read_bytes()
    assert reopened.append(item).detail_code == "already_persisted"
    assert path.read_bytes() == before
    assert reopened.read_run("run").records[0].payload == item.payload


def test_missing_delimiter_is_not_a_committed_frame(tmp_path):
    path = tmp_path / "journal"
    store = JournalTrajectoryStore(path)
    item = record(0)
    store.append(item)
    path.write_bytes(path.read_bytes().removesuffix(b"\n"))
    with pytest.raises(StoreIntegrityError, match="incomplete_journal_frame"):
        JournalTrajectoryStore(path, recover_partial_tail=False)
    reopened = JournalTrajectoryStore(path)
    assert reopened.read_run("run").records == ()
    assert reopened.append(item).persisted_count == 1
    assert len(reopened.read_run("run").records) == 1


def test_complete_read_over_default_limit_and_page_boundary(tmp_path):
    store = JournalTrajectoryStore(tmp_path / "journal")
    store.append_batch(record(i) for i in range(10_003))
    with pytest.raises(TrajectoryStoreError, match="query_requires_pagination"):
        store.query(TrajectoryQuery())
    first = store.query(TrajectoryQuery(limit=10_000))
    last = store.query(TrajectoryQuery(limit=10_000, after_sequence=first[-1].sequence))
    assert len(first) == 10_000
    assert [r.sequence for r in last] == [10_000, 10_001, 10_002]
    whole = store.read_run("run")
    assert len(whole.records) == 10_003
    assert [r.sequence for r in whole.records] == list(range(10_003))
    assert len(store.read_session("session").records) == 10_003
    assert len(ReadOnlyInspection(StoreTrajectoryReader(store)).run("run").records) == 10_003
    exporter = CanonicalTrajectoryExporter()
    artifact = exporter.export(whole, view=PrivacyView.RAW_PRIVATE)
    restored = exporter.reimport(artifact)
    assert restored.to_dict() == whole.to_dict()
