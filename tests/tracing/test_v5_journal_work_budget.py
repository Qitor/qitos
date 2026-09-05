"""Mechanism gates: constant warm append work and bounded fresh reader state."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from qitos.tracing.journal_store import JournalTrajectoryStore
from qitos.tracing.store import StoreConflictError
from test_v5_bounded_reader import record

ROOT = Path(__file__).resolve().parents[2]
WORKLOAD = ROOT / "examples/v5/r1_d_trajectory/workload.py"


def test_warm_append_never_snapshots_or_rewrites_full_index(tmp_path, monkeypatch):
    store = JournalTrajectoryStore(tmp_path / "journal")
    store.append_batch(record(i) for i in range(256))
    before = store.work.visited_index_entries
    written = store.work.written_index_entries
    monkeypatch.setattr(store._memory, "_snapshot_records", lambda: pytest.fail("full tuple"))
    monkeypatch.setattr(store, "_write_index", lambda **kw: pytest.fail("implicit checkpoint"))
    for i in range(256, 288):
        store.append(record(i))
    assert store.work.visited_index_entries - before == 32
    assert store.work.written_index_entries == written
    assert store.work.hash_bytes > 256 * 1024
    assert store.append(record(256)).detail_code == "already_persisted"
    with pytest.raises(StoreConflictError, match="partial_duplicate_batch"):
        store.append_batch([record(256), record(289)])
    store.flush()  # Flush is fsync only, never an implicit checkpoint.


@pytest.mark.parametrize("count", [10_000, 100_000])
def test_independent_writer_and_bounded_reader_workload(tmp_path, count):
    path = tmp_path / "trajectory.journal"
    env = dict(os.environ, PYTHONPATH=str(ROOT), QITOS_MEASURE_TRACE="1")
    subprocess.run([sys.executable, str(WORKLOAD), "seed", str(path), "--count", str(count)],
                   env=env, check=True)
    result = subprocess.run([sys.executable, str(WORKLOAD), "page", str(path)],
                            env=env, check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    assert data["record_count"] == 128
    assert data["work"]["peak_retained_records"] <= 160
    assert data["work"]["decoded_records"] == count + 128
    assert data["work"]["hash_bytes"] >= path.stat().st_size * 3
    # Fixed SQLite cache plus page/frame buffers; no threshold on unstable wall time.
    assert data["tracemalloc_peak_bytes"] < 16 * 1024 * 1024
