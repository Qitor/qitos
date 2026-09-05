"""Deterministic journal workload and fresh-process measurement driver.

No provider, private campaign or runtime state is accessed. Seed writes the frozen
journal wire directly, <=32 records per frame, and exits before reader measurement.
Run this same driver with the exact baseline import path for before measurements.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import resource
import time
import tracemalloc
from dataclasses import asdict, dataclass
from pathlib import Path

from qitos.tracing.journal_store import JOURNAL_SCHEMA_VERSION, JournalTrajectoryStore
from qitos.tracing.trajectory import (
    STORE_SCHEMA_VERSION, PrivacyView, RecordKind, TrajectoryQuery, TrajectoryRecord,
    canonical_json_bytes, integrity_digest,
)


def seed(path: Path, count: int) -> None:
    previous = None
    with path.open("wb") as output:
        for start in range(0, count, 32):
            records = [TrajectoryRecord.create(
                RecordKind.RUN, record_id=f"record-{i}", sequence=i,
                occurred_at="2026-01-01T00:00:00+00:00", recorded_at="2026-01-01T00:00:00+00:00",
                run_id="run", session_id="session", payload={"data": "x" * 1024},
            ).to_dict() for i in range(start, min(count, start + 32))]
            frame = {"journal_schema": JOURNAL_SCHEMA_VERSION, "store_schema": STORE_SCHEMA_VERSION,
                     "transaction_id": f"batch-{start}", "start_sequence": start,
                     "previous_digest": previous, "records": records}
            previous = integrity_digest(frame)
            frame["frame_digest"] = previous
            output.write(canonical_json_bytes(frame) + b"\n")
        output.flush()
        os.fsync(output.fileno())
    path.with_name(path.name + ".lock").touch()


@dataclass
class BaselineWork:
    read_bytes: int = 0
    hash_bytes: int = 0
    decoded_records: int = 0
    copied_records: int = 0
    retained_records: int = 0
    peak_retained_records: int = 0
    visited_index_entries: int = 0
    written_index_entries: int = 0
    fsync_calls: int = 0


def baseline_probes(path: Path) -> None:
    """Observe the unchanged fixed source; no algorithm/cache/index replacement."""
    from qitos.tracing.store import MemoryTrajectoryStore
    work = BaselineWork()
    original_init = JournalTrajectoryStore.__init__
    original_decode = JournalTrajectoryStore._decode_frame
    original_snapshot = MemoryTrajectoryStore._snapshot_records
    original_restore = MemoryTrajectoryStore._restore
    original_query = MemoryTrajectoryStore.query
    original_append = JournalTrajectoryStore.append_batch
    original_index = JournalTrajectoryStore._index_document
    original_write = JournalTrajectoryStore._write_index
    original_open, original_fsync = Path.open, os.fsync

    def initialized(self, *args, **kwargs):
        self.work = work
        original_init(self, *args, **kwargs)

    def decoded(value, **kwargs):
        result = original_decode(value, **kwargs)
        work.decoded_records += len(result[0])
        return result

    def snapshot(self):
        result = original_snapshot(self)
        work.copied_records += len(result)
        work.retained_records = len(result)
        work.peak_retained_records = max(work.peak_retained_records, len(result))
        return result

    def restored(self, records):
        result = original_restore(self, records)
        work.copied_records += len(self._records)
        work.retained_records = len(self._records)
        work.peak_retained_records = max(work.peak_retained_records, len(self._records))
        return result

    def queried(self, query):
        result = original_query(self, query)
        work.copied_records += len(result)
        return result

    def appended(self, records):
        # The fixed source rebuilds its identity dict once on every warm append.
        work.visited_index_entries += len(self._memory._records)
        return original_append(self, records)

    def index(self):
        work.visited_index_entries += len(self._memory._records) * 3
        document = original_index(self)
        work.written_index_entries += sum(len(values) for name in ("runs", "sessions", "work_items")
                                          for values in document[name].values())
        return document

    def written(self, **kwargs):
        return original_write(self, **kwargs)

    class ReadProbe:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.handle.close()

        def __getattr__(self, name):
            return getattr(self.handle, name)

        def read(self, *args):
            data = self.handle.read(*args)
            work.read_bytes += len(data)
            work.hash_bytes += len(data)
            return data

        def readline(self, *args):
            data = self.handle.readline(*args)
            work.read_bytes += len(data)
            work.hash_bytes += len(data)
            return data

    def opened(self, mode="r", *args, **kwargs):
        handle = original_open(self, mode, *args, **kwargs)
        return ReadProbe(handle) if self == path and mode == "rb" else handle

    def synced(fd):
        work.fsync_calls += 1
        return original_fsync(fd)

    JournalTrajectoryStore.__init__ = initialized
    JournalTrajectoryStore._decode_frame = staticmethod(decoded)
    MemoryTrajectoryStore._snapshot_records = snapshot
    MemoryTrajectoryStore._restore = restored
    MemoryTrajectoryStore.query = queried
    JournalTrajectoryStore.append_batch = appended
    JournalTrajectoryStore._index_document = index
    JournalTrajectoryStore._write_index = written
    Path.open, os.fsync = opened, synced


def measure(path: Path, mode: str) -> dict:
    if "TrajectoryWork" not in JournalTrajectoryStore.__init__.__globals__:
        baseline_probes(path)
    fsync_calls = 0
    original_fsync = os.fsync

    def counted_fsync(fd):
        nonlocal fsync_calls
        fsync_calls += 1
        return original_fsync(fd)

    os.fsync = counted_fsync
    equivalence_digest = None
    started = time.perf_counter()
    traced = os.environ.get("QITOS_MEASURE_TRACE") == "1"
    if traced:
        tracemalloc.start()
    if mode == "append":
        store = JournalTrajectoryStore(path)
        cold = time.perf_counter() - started
        before = asdict(store.work) if hasattr(store, "work") else {}
        started = time.perf_counter()
        store.append_batch(TrajectoryRecord.create(RecordKind.STEP, payload={"data": "x" * 1024})
                           for _ in range(32))
        elapsed = time.perf_counter() - started
        after = asdict(store.work) if hasattr(store, "work") else {}
        counters = {key: after[key] - before[key] for key in before}
        for gauge in ("retained_records", "peak_retained_records"):
            counters[gauge] = after[gauge]
        count = 32
    elif mode == "page":
        from qitos.tracing.readers import StoreTrajectoryReader
        reader = StoreTrajectoryReader.from_journal(path)
        cold = time.perf_counter() - started
        started = time.perf_counter()
        page = reader.read_page(TrajectoryQuery(run_id="run", limit=128), view=PrivacyView.RAW_PRIVATE)
        elapsed = time.perf_counter() - started
        count = len(page.records)
        counters = asdict(reader.work)
        reader.close()
    elif mode in {"iterate", "stream"}:
        from qitos.tracing.readers import StoreTrajectoryReader
        reader = StoreTrajectoryReader.from_journal(path)
        cold = time.perf_counter() - started
        started = time.perf_counter()
        if mode == "iterate":
            from qitos.tracing.paging import iter_records
            digest = hashlib.sha256()
            count = 0
            for record in iter_records(reader, TrajectoryQuery(limit=128), view=PrivacyView.RAW_PRIVATE):
                digest.update(canonical_json_bytes(record.to_dict()))
                count += 1
            equivalence_digest = digest.hexdigest()
        else:
            from qitos.tracing.exporter import CanonicalTrajectoryExporter
            receipt = CanonicalTrajectoryExporter().export_file(
                reader, TrajectoryQuery(run_id="run", limit=128), path.with_suffix(".export"),
                view=PrivacyView.RAW_PRIVATE)
            count = receipt.record_count
            equivalence_digest = receipt.digest
        elapsed = time.perf_counter() - started
        counters = asdict(reader.work)
        reader.close()
    else:
        store = JournalTrajectoryStore(path, read_only=True)
        cold = time.perf_counter() - started
        started = time.perf_counter()
        trajectory = store.read_run("run")
        if mode == "export":
            from qitos.tracing.exporter import CanonicalTrajectoryExporter
            artifact = CanonicalTrajectoryExporter().export(trajectory, view=PrivacyView.RAW_PRIVATE)
            path.with_suffix(".export").write_bytes(artifact.data)
            equivalence_digest = artifact.digest
        count = len(trajectory.records)
        elapsed = time.perf_counter() - started
        counters = asdict(store.work) if hasattr(store, "work") else {}
        if mode == "read":
            digest = hashlib.sha256()
            for record in trajectory.records:
                digest.update(canonical_json_bytes(record.to_dict()))
            equivalence_digest = digest.hexdigest()
    _, peak = tracemalloc.get_traced_memory() if traced else (0, 0)
    if traced:
        tracemalloc.stop()
    return {"mode": mode, "cold_seconds": cold, "operation_seconds": elapsed,
            "tracemalloc_enabled": traced, "tracemalloc_peak_bytes": peak, "rss_max_native": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "rss_native_unit": "bytes" if platform.system() == "Darwin" else "KiB",
            "fsync_calls_total": fsync_calls, "record_count": count, "equivalence_digest": equivalence_digest, "work": counters, "python": platform.python_version(),
            "platform": platform.platform(), "frame_records": 32, "page_limit": 128,
            "payload_bytes": 1024, "cache": "fresh process; OS cache uncontrolled/warm after seeding"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["seed", "append", "page", "iterate", "stream", "read", "export"])
    parser.add_argument("path", type=Path)
    parser.add_argument("--count", type=int, default=10000)
    args = parser.parse_args()
    if args.mode == "seed":
        seed(args.path, args.count)
    else:
        print(json.dumps(measure(args.path, args.mode), sort_keys=True))
