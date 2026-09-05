"""Snapshot integrity, cursor isolation and bounded retained state."""
import os
from dataclasses import replace

import pytest

from qitos.qita.reader import candidate_file_reader
from qitos.tracing.paging import BoundedReadUnsupported, CursorRejected, iter_records, read_page
from qitos.tracing.readers import StoreTrajectoryReader
from qitos.tracing.journal_store import JournalTrajectoryStore
from qitos.tracing.store import MemoryTrajectoryStore, StoreIntegrityError
from qitos.tracing.trajectory import PrivacyView, RecordKind, TrajectoryQuery, TrajectoryRecord

RAW = PrivacyView.RAW_PRIVATE


def record(i):
    return TrajectoryRecord.create(RecordKind.RUN, record_id=f"r{i}", run_id="run",
                                   session_id="session", occurred_at="2026-01-01T00:00:00+00:00", payload={"i": i, "data": "x" * 1024})


@pytest.fixture
def journal(tmp_path):
    path = tmp_path / "trajectory.journal"
    writer = JournalTrajectoryStore(path)
    for start in range(0, 259, 32):
        writer.append_batch(record(i) for i in range(start, min(start + 32, 259)))
    writer.close()
    return path


def test_pages_equal_whole_snapshot_and_live_watermark(journal, monkeypatch):
    whole = JournalTrajectoryStore(journal, read_only=True).read_run("run")
    reader = candidate_file_reader(journal)
    monkeypatch.setattr(JournalTrajectoryStore, "__init__", lambda *a, **k: pytest.fail("full store"))
    query = TrajectoryQuery(run_id="run", limit=128)
    first = read_page(reader, query, view=RAW)
    second = read_page(reader, query, first.next_cursor, view=RAW)
    again = read_page(reader, query, first.next_cursor, view=RAW)
    assert second == again
    last = read_page(reader, query, second.next_cursor, view=RAW)
    assert first.records + second.records + last.records == whole.records
    assert last.next_cursor is None and last.watermark == 258
    assert reader._materialized is None
    assert reader.work.peak_retained_records <= 160
    reader.close()


def test_append_is_outside_snapshot_and_new_capture_uses_watermark(journal):
    reader = candidate_file_reader(journal)
    query = TrajectoryQuery(limit=128)
    first = reader.read_page(query, view=RAW)
    writer = JournalTrajectoryStore(journal)
    writer.append(record(259))
    second = reader.read_page(query, first.next_cursor, view=RAW)
    last = reader.read_page(query, second.next_cursor, view=RAW)
    assert [r.sequence for r in last.records] == [256, 257, 258]
    added = reader.read_page(replace(query, after_sequence=last.watermark), view=RAW)
    assert [r.sequence for r in added.records] == [259]
    assert reader.read_page(query, first.next_cursor, view=RAW) == second
    writer.close()
    reader.close()


def test_cursor_filter_view_source_and_offset_binding(journal):
    first = candidate_file_reader(journal)
    second = candidate_file_reader(journal)
    query = TrajectoryQuery(limit=128)
    cursor = first.read_page(query).next_cursor
    for other in (replace(query, run_id="changed"), replace(query, limit=127)):
        with pytest.raises(CursorRejected, match="filter"):
            first.read_page(other, cursor)
    with pytest.raises(CursorRejected):
        first.read_page(query, cursor, view=RAW)
    with pytest.raises(CursorRejected):
        second.read_page(query, cursor)
    with pytest.raises(CursorRejected):
        first.read_page(query, replace(cursor, token=cursor.token.replace('a', 'b')))
    first.close()
    second.close()


@pytest.mark.parametrize("damage", ["same_size", "truncate", "replace", "partial"])
def test_source_changes_typed_reject_without_repair(journal, damage):
    reader = candidate_file_reader(journal)
    query = TrajectoryQuery(limit=128)
    cursor = reader.read_page(query).next_cursor
    before = journal.stat()
    data = journal.read_bytes()
    if damage == "same_size":
        journal.write_bytes(data.replace(b'"i":0', b'"i":9', 1))
        os.utime(journal, ns=(before.st_atime_ns, before.st_mtime_ns))
    elif damage == "truncate":
        journal.write_bytes(data[:10])
    elif damage == "replace":
        replacement = journal.with_suffix(".replacement")
        replacement.write_bytes(data)
        replacement.replace(journal)
    else:
        journal.write_bytes(data + b'{"partial":')
    damaged = journal.read_bytes()
    if damage == "partial":
        # Already captured snapshot excludes an uncommitted/new suffix.
        assert reader.read_page(query, cursor).records
        with pytest.raises(StoreIntegrityError, match="incomplete"):
            reader.read_page(query)
        assert reader.read_page(query, cursor).records
    else:
        with pytest.raises(CursorRejected):
            reader.read_page(query, cursor)
    assert journal.read_bytes() == damaged
    reader.close()


@pytest.mark.parametrize("index", ["missing", "stale", "corrupt"])
def test_derived_sidecar_cannot_address_wrong_bytes(journal, index):
    sidecar = journal.with_name(journal.name + ".index.json")
    if index == "missing":
        sidecar.unlink()
    else:
        sidecar.write_text('{}' if index == "stale" else 'corrupt')
    before = {p.name: p.read_bytes() for p in journal.parent.iterdir()}
    reader = candidate_file_reader(journal)
    assert len(list(iter_records(reader, TrajectoryQuery(limit=128), view=RAW))) == 259
    assert before == {p.name: p.read_bytes() for p in journal.parent.iterdir()}
    reader.close()


def test_early_iterator_close_releases_locks_and_unsupported_is_explicit(journal):
    reader = candidate_file_reader(journal)
    iterator = iter_records(reader, TrajectoryQuery(limit=128))
    next(iterator)
    iterator.close()
    writer = JournalTrajectoryStore(journal)
    assert writer.append(record(259)).persisted_count == 1
    writer.close()
    reader.close()
    with pytest.raises(BoundedReadUnsupported):
        read_page(StoreTrajectoryReader(MemoryTrajectoryStore()), TrajectoryQuery())


@pytest.mark.parametrize("count", [0, 1, 128, 129, 256])
def test_exact_page_end_and_empty_filter(tmp_path, count):
    path = tmp_path / "trajectory.journal"
    writer = JournalTrajectoryStore(path)
    for start in range(0, count, 32):
        writer.append_batch(record(i) for i in range(start, min(start + 32, count)))
    writer.close()
    reader = candidate_file_reader(path)
    query = TrajectoryQuery(limit=128)
    observed = tuple(iter_records(reader, query, view=RAW))
    assert [r.sequence for r in observed] == list(range(count))
    first = reader.read_page(query)
    assert (first.next_cursor is None) == (count <= 128)
    empty = reader.read_page(replace(query, run_id="absent"))
    assert empty.records == () and empty.next_cursor is None
    assert empty.watermark == count - 1
    reader.close()


def test_corrupt_duplicate_ids_reject_even_with_valid_frame_digests(journal):
    import json
    from qitos.tracing.trajectory import canonical_json_bytes, integrity_digest

    frames = [json.loads(line) for line in journal.read_bytes().splitlines()]
    frames[-1]["records"][-1]["record_id"] = frames[0]["records"][0]["record_id"]
    item = frames[-1]["records"][-1]
    item.pop("digest")
    item["digest"] = integrity_digest(item)
    frames[-1].pop("frame_digest")
    frames[-1]["frame_digest"] = integrity_digest(frames[-1])
    journal.write_bytes(b"".join(canonical_json_bytes(frame) + b"\n" for frame in frames))
    with pytest.raises(StoreIntegrityError, match="duplicate_record_id"):
        candidate_file_reader(journal)
