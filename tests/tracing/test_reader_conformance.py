from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from qitos.tracing.readers import (
    StoreTrajectoryReader,
    TraceCompatibilityReader,
    TrajectoryReader,
)
from qitos.tracing.store import MemoryTrajectoryStore
from qitos.tracing.trajectory import (
    PrivacyView,
    RecordKind,
    TrajectoryQuery,
    TrajectoryRecord,
)


ROOT = Path(__file__).resolve().parents[2]


def _third_party_store() -> Any:
    path = ROOT / "tests" / "fixtures" / "s2" / "lane_d" / "third_party.py"
    spec = importlib.util.spec_from_file_location("lane_d_reader_store", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ThirdPartyStore()


def _store_reader(store: Any) -> StoreTrajectoryReader:
    store.append_batch(
        (
            TrajectoryRecord.create(
                RecordKind.RUN,
                record_id="run",
                run_id="run-1",
                session_id="session-1",
                payload={"run_id": "run-1", "status": "completed"},
            ),
            TrajectoryRecord.create(
                RecordKind.STOP,
                record_id="stop",
                run_id="run-1",
                session_id="session-1",
                payload={"reason": "final"},
            ),
        )
    )
    return StoreTrajectoryReader(store)


@pytest.mark.parametrize(
    "reader",
    [
        pytest.param(_store_reader(MemoryTrajectoryStore()), id="reference-store"),
        pytest.param(_store_reader(_third_party_store()), id="third-party-store"),
    ],
)
def test_store_reader_conformance(reader: Any) -> None:
    assert isinstance(reader, TrajectoryReader)
    assert reader.capabilities.session_query
    summaries = reader.discover_runs()
    assert [summary.run_id for summary in summaries] == ["run-1"]
    run = reader.read_run("run-1", view=PrivacyView.REDACTED_PUBLIC)
    session = reader.read_session(
        "session-1", view=PrivacyView.REDACTED_PUBLIC
    )
    replay = reader.replay(
        TrajectoryQuery(run_id="run-1", kinds=(RecordKind.STOP,)),
        view=PrivacyView.SAFE_DIAGNOSTIC,
    )
    assert len(run.records) == 2
    assert len(session.records) == 2
    assert [record.kind for record in replay] == [RecordKind.STOP]
    assert reader.validate_integrity().valid


def test_frozen_trace_reader_conformance_and_loss(tmp_path: Path) -> None:
    run = tmp_path / "run-1"
    run.mkdir()
    (run / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "v1",
                "run_id": "run-1",
                "status": "completed",
                "step_count": 0,
                "event_count": 1,
                "summary": {"stop_reason": "final", "final_result": "ok"},
            }
        ),
        encoding="utf-8",
    )
    (run / "events.jsonl").write_text(
        '{"step_id":0,"phase":"END","ok":true,"ts":"x"}\n',
        encoding="utf-8",
    )
    reader = TraceCompatibilityReader(tmp_path)
    assert isinstance(reader, TrajectoryReader)
    trajectory = reader.read_run("run-1")
    assert trajectory.records[0].kind == RecordKind.STOP
    assert not trajectory.loss.is_lossless
    with pytest.raises(LookupError, match="session_query_unavailable"):
        reader.read_session("session-1")
    assert reader.validate_integrity().valid
