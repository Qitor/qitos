from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from qitos.qita.inspection import QitaReadError, ReadOnlyInspection
from qitos.tracing.exporter import CanonicalTrajectoryExporter
from qitos.tracing.readers import StoreTrajectoryReader, TraceCompatibilityReader
from qitos.tracing.store import MemoryTrajectoryStore
from qitos.tracing.trajectory import RecordKind, TrajectoryRecord


def _candidate() -> ReadOnlyInspection:
    store = MemoryTrajectoryStore()
    store.append_batch(
        (
            TrajectoryRecord.create(
                RecordKind.RUN,
                record_id="run",
                run_id="run-1",
                session_id="session-1",
                work_item_id="work-1",
                payload={"run_id": "run-1", "status": "running"},
            ),
            TrajectoryRecord.create(
                RecordKind.OWNERSHIP,
                record_id="owner",
                run_id="run-1",
                session_id="session-1",
                work_item_id="work-1",
                attempt_id="attempt-1",
                owner_id="agent-1",
                owner_generation=3,
                payload={"status": "active"},
            ),
            TrajectoryRecord.create(
                RecordKind.BUDGET,
                record_id="budget",
                run_id="run-1",
                session_id="session-1",
                payload={"remaining": 4},
            ),
            TrajectoryRecord.create(
                RecordKind.SANDBOX,
                record_id="sandbox",
                run_id="run-1",
                session_id="session-1",
                sandbox_id="sandbox-1",
                payload={"network": "none"},
            ),
        )
    )
    return ReadOnlyInspection(StoreTrajectoryReader(store))


def test_all_candidate_inspection_views_use_one_read_only_reader() -> None:
    inspection = _candidate()
    assert inspection.board()[0]["run_id"] == "run-1"
    assert len(inspection.timeline(run_id="run-1").records) == 4
    assert inspection.graph(run_id="run-1").unknown
    assert inspection.item("owner", run_id="run-1").records[0]["owner_id"] == "agent-1"
    assert len(inspection.attempts(run_id="run-1").records) == 1
    assert len(inspection.ownership(run_id="run-1").records) == 1
    assert len(inspection.budgets(run_id="run-1").records) == 1
    assert len(inspection.sandbox(run_id="run-1").records) == 1
    assert inspection.losses(run_id="run-1").unknown
    assert len(inspection.poll(run_id="run-1", after_sequence=1)) == 2
    artifact = inspection.export(
        CanonicalTrajectoryExporter(), run_id="run-1"
    )
    assert artifact.exact_reimport

    public_methods = {
        name
        for name, value in inspect.getmembers(inspection, predicate=callable)
        if not name.startswith("_")
    }
    assert not public_methods.intersection(
        {"pause", "resume", "fork", "handoff", "mutate_work_graph"}
    )


def test_historical_missing_candidate_facts_are_unknown_with_loss(
    tmp_path: Path,
) -> None:
    run = tmp_path / "historical"
    run.mkdir()
    (run / "manifest.json").write_text(
        json.dumps({"schema_version": "v1", "run_id": "historical"}),
        encoding="utf-8",
    )
    (run / "events.jsonl").write_text(
        json.dumps({"step_id": 0, "phase": "END", "ok": True}) + "\n",
        encoding="utf-8",
    )
    inspection = ReadOnlyInspection(TraceCompatibilityReader(tmp_path))

    sandbox = inspection.sandbox(run_id="historical")
    assert sandbox.unknown
    codes = {entry.code for entry in sandbox.loss.entries}
    assert "compatibility_trace_input" in codes
    assert "sandbox_fact_unavailable" in codes
    with pytest.raises(QitaReadError) as captured:
        inspection.session("session-unknown")
    assert captured.value.code == "session_source_unavailable"


def test_missing_reader_and_missing_item_are_typed_without_echo() -> None:
    with pytest.raises(QitaReadError) as captured:
        ReadOnlyInspection(object())
    assert captured.value.code == "trajectory_reader_unavailable"

    with pytest.raises(QitaReadError) as captured:
        _candidate().item("secret-record-value", run_id="run-1")
    assert captured.value.code == "trajectory_item_not_found"
    assert "secret-record-value" not in str(captured.value)
