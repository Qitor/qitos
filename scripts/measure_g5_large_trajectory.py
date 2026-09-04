#!/usr/bin/env python3
"""Measure a bounded synthetic 10,003-record workload; never producer evidence."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qitos.tracing.exporter import CanonicalTrajectoryExporter
from qitos.tracing.journal_store import JournalTrajectoryStore
from qitos.tracing.trajectory import PrivacyView, RecordKind, TrajectoryQuery, TrajectoryRecord


class MeasuredJournal(JournalTrajectoryStore):
    """Instrumentation counts full journal loads; it does not change storage."""

    scans = 0
    logical_scan_bytes = 0

    def _load(self, *, recover):
        self.scans += 1
        self.logical_scan_bytes += self._path.stat().st_size
        return super()._load(recover=recover)


def main():
    output = []
    for repetition in range(3):
        tracemalloc.start()
        with tempfile.TemporaryDirectory(prefix="qitos-g5-large-") as directory:
            records = tuple(
                TrajectoryRecord.create(
                    RecordKind.STEP,
                    record_id=f"measurement-{i}",
                    run_id="measurement-run",
                    session_id="measurement-session",
                    payload={"measurement_only": True, "ordinal": i},
                )
                for i in range(10_003)
            )
            store = MeasuredJournal(Path(directory) / "trajectory.journal")
            measurements = {}

            def measure(name, operation):
                scans, size = store.scans, store.logical_scan_bytes
                started = time.perf_counter_ns()
                result = operation()
                measurements[name] = {
                    "elapsed_ns": time.perf_counter_ns() - started,
                    "full_loads": store.scans - scans,
                    "logical_scan_bytes": store.logical_scan_bytes - size,
                }
                return result

            measure("append_batch", lambda: store.append_batch(records))
            page = measure("query_first_page", lambda: store.query(TrajectoryQuery(limit=10_000)))
            tail = measure(
                "query_last_page",
                lambda: store.query(
                    TrajectoryQuery(limit=10_000, after_sequence=page[-1].sequence)
                ),
            )
            assert len(page) == 10_000 and len(tail) == 3
            whole = measure("complete_read", lambda: store.read_run("measurement-run"))
            assert [record.sequence for record in whole.records] == list(range(10_003))
            exporter = CanonicalTrajectoryExporter()
            exported = measure(
                "exact_export", lambda: exporter.export(whole, view=PrivacyView.RAW_PRIVATE)
            )
            restored = measure("exact_reimport", lambda: exporter.reimport(exported))
            assert restored.to_dict() == whole.to_dict()
            measure("duplicate_append", lambda: store.append_batch(records))
            assert len(store.read_session("measurement-session").records) == 10_003
            _, peak = tracemalloc.get_traced_memory()
            output.append(
                {
                    "repetition": repetition,
                    "record_count": len(records),
                    "journal_bytes": store._path.stat().st_size,
                    "export_bytes": len(exported.data),
                    "tracemalloc_peak_bytes": peak,
                    "operations": measurements,
                }
            )
            store.close()
        tracemalloc.stop()
    print(
        json.dumps(
            {
                "schema": "qitos.g5.large_measurement/v1",
                "measurement_only": True,
                "code_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "source_dirty": bool(
                    subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip()
                ),
                "memory_boundary": "Complete journal, records and export are materialized; total memory is not bounded by query limit.",
                "scan_counter": "Full _load invocations and file size, not physical disk reads or cache misses.",
                "measurements": output,
                "claims": [],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
