from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from qitos.core.artifact import ArtifactRef
from qitos.tracing.store import (
    JsonTrajectoryStore,
    MemoryTrajectoryStore,
    TrajectoryStore,
)
from qitos.tracing.store import StoreConflictError, StoreIntegrityError
from qitos.tracing.trajectory import RecordKind, TrajectoryQuery, TrajectoryRecord


ROOT = Path(__file__).resolve().parents[1]


def _third_party_store() -> Any:
    path = ROOT / "tests" / "fixtures" / "s2" / "lane_d" / "third_party.py"
    spec = importlib.util.spec_from_file_location("lane_d_third_party_store", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ThirdPartyStore()


def _fact(index: int, *, kind: RecordKind = RecordKind.TOOL_SLOT) -> TrajectoryRecord:
    artifact = ArtifactRef(
        artifact_id=f"artifact-{index}",
        resolver_key="trajectory-artifacts",
        sha256=hashlib.sha256(f"artifact-{index}".encode()).hexdigest(),
        byte_length=10 + index,
        media_type="text/plain",
    )
    return TrajectoryRecord.create(
        kind,
        record_id=f"record-{index}",
        session_id="session-1",
        run_id="run-1",
        work_item_id="work-1",
        step_id=index,
        payload={"slot": index},
        artifact_refs=(artifact,),
    )


@pytest.mark.parametrize(
    "factory",
    [
        MemoryTrajectoryStore,
        _third_party_store,
    ],
    ids=["reference-memory", "third-party-style"],
)
def test_store_conformance(factory: Callable[[], Any]) -> None:
    store = factory()
    assert isinstance(store, TrajectoryStore)
    assert store.capabilities.atomic_batch

    receipt = store.append_batch((_fact(0), _fact(1, kind=RecordKind.EFFECT)))
    assert receipt.accepted_count == 2
    records = store.query(TrajectoryQuery(run_id="run-1"))
    assert [record.sequence for record in records] == [0, 1]
    assert [record.kind for record in store.replay(TrajectoryQuery(run_id="run-1"))] == [
        RecordKind.TOOL_SLOT,
        RecordKind.EFFECT,
    ]
    assert len(store.read_run("run-1").records) == 2
    assert len(store.read_session("session-1").records) == 2
    assert len(store.artifact_refs(TrajectoryQuery(run_id="run-1"))) == 2
    assert store.validate_integrity().valid
    measurement = store.measure_storage()
    assert measurement.record_count == 2
    assert measurement.size_bytes > 0

    records[0].payload["slot"] = 99
    assert store.query(TrajectoryQuery(limit=1))[0].payload["slot"] == 0

    before = store.query(TrajectoryQuery())
    with pytest.raises(StoreConflictError):
        store.append_batch((_fact(2), _fact(2)))
    after = store.query(TrajectoryQuery())
    assert [item.record_id for item in after] == [item.record_id for item in before]


def test_json_store_atomic_reopen_and_integrity(tmp_path: Path) -> None:
    path = tmp_path / "trajectory-store.json"
    store = JsonTrajectoryStore(path)
    receipt = store.append_batch((_fact(0), _fact(1)))
    assert receipt.persisted_count == 2
    assert store.validate_integrity().valid
    observed = store.measure_storage()
    assert observed.measurement_kind == "observed_file_bytes"
    assert observed.size_bytes == path.stat().st_size
    store.close()

    reopened = JsonTrajectoryStore(path)
    assert [record.record_id for record in reopened.read_run("run-1").records] == [
        "record-0",
        "record-1",
    ]
    reopened.close()


def test_json_store_rejects_tampering(tmp_path: Path) -> None:
    path = tmp_path / "trajectory-store.json"
    store = JsonTrajectoryStore(path)
    store.append(_fact(0))
    store.close()
    document = json.loads(path.read_text(encoding="utf-8"))
    document["records"][0]["payload"]["slot"] = 999
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(StoreIntegrityError, match="store_digest_mismatch"):
        JsonTrajectoryStore(path)


def test_json_store_rejects_non_record_entries_with_valid_outer_digest(
    tmp_path: Path,
) -> None:
    from qitos.tracing.trajectory import integrity_digest

    path = tmp_path / "trajectory-store.json"
    document = {
        "storage_schema": "qitos.trajectory-store/candidate-1",
        "records": ["not-a-record"],
    }
    document["store_digest"] = integrity_digest(document)
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(StoreIntegrityError, match="invalid_store_records"):
        JsonTrajectoryStore(path)


def test_store_schema_fixture_matches_implementation() -> None:
    schema = json.loads(
        (
            ROOT
            / "tests"
            / "fixtures"
            / "s2"
            / "lane_d"
            / "trajectory-store.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert schema["properties"]["storage_schema"]["const"] == (
        "qitos.trajectory-store/candidate-1"
    )
