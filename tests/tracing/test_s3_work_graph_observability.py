from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from qitos.qita._cli_app import main as qita_main
from qitos.tracing.privacy import ProjectionLimits, project_data
from qitos.tracing.readers import StoreTrajectoryReader, TraceCompatibilityReader
from qitos.tracing.store import MemoryTrajectoryStore
from qitos.tracing.trajectory import PrivacyView, TrajectoryRecord
from qitos.tracing.work_graph_reader import (
    WORK_GRAPH_EVENT_TYPES,
    GraphSelector,
    WorkGraphReadError,
    WorkGraphReader,
    work_graph_event_record,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "s3" / "lane_d"


def _fixture_records() -> tuple[TrajectoryRecord, ...]:
    fixture = json.loads((FIXTURES / "work-graph-events.json").read_text(encoding="utf-8"))
    identities = fixture["identities"]
    records = []
    for sequence, raw in enumerate(fixture["records"]):
        value = dict(raw)
        event_type = value.pop("event_type")
        records.append(
            work_graph_event_record(
                event_type,
                session_id=identities["session_id"],
                run_id=identities["run_id"],
                producer_authority="qitos.fixture.conformance",
                record_provenance={
                    "fixture_version": fixture["fixture_version"],
                    "runtime_qualification": False,
                },
                record_id=f"fixture-record-{sequence}",
                sequence=sequence,
                occurred_at=f"2026-08-31T00:00:{sequence:02d}+00:00",
                **value,
            )
        )
    return tuple(records)


def _third_party_reader(records: tuple[TrajectoryRecord, ...]) -> Any:
    path = FIXTURES / "third_party_reader.py"
    spec = importlib.util.spec_from_file_location("s3_third_party_reader", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ThirdPartyGraphReader(records)


def _candidate_reader(records: tuple[TrajectoryRecord, ...]) -> StoreTrajectoryReader:
    store = MemoryTrajectoryStore()
    store.append_batch(records)
    return StoreTrajectoryReader(store)


def test_event_vocabulary_and_serialized_identity_fields_are_explicit() -> None:
    required = {
        "session_created", "session_restored", "session_forked",
        "run_started", "run_terminated", "work_declared", "work_attempt",
        "owner_assigned", "ownership_transfer_requested",
        "ownership_transfer_committed", "ownership_transfer_rejected",
        "delegate_declared", "spawn_declared", "fan_out_declared",
        "child_dispatched", "child_running", "child_paused", "child_waiting",
        "child_terminal", "cancellation_requested", "cancellation_acknowledged",
        "cancellation_unresolved", "child_detached", "supervision_declared",
        "join_declared", "join_progressed", "join_closed", "outcome_accepted",
        "outcome_discarded", "outcome_late", "outcome_stale", "outcome_unknown",
        "budget_allocated", "capability_allocated", "context_transferred",
        "continuation_transferred", "artifact_referenced",
        "process_loss_recovered", "generation_conflict", "loss_projected",
        "privacy_projected",
    }
    assert WORK_GRAPH_EVENT_TYPES == required
    for record in _fixture_records():
        encoded = record.to_dict()
        assert record.validate_integrity()
        assert encoded["session_id"]
        assert encoded["run_id"]
        assert "work_item_id" in encoded
        assert "attempt_id" in encoded
        assert "parent_work_item_id" in encoded
        assert "source_work_item_id" in encoded
        assert encoded["operation_id"]
        assert encoded["producer_authority"]
        assert encoded["record_provenance"]
        assert encoded["loss"] is not None


@pytest.mark.parametrize("source", ("candidate", "third_party"))
def test_unified_graph_reader_conformance(source: str) -> None:
    records = _fixture_records()
    reader = (
        _candidate_reader(records)
        if source == "candidate"
        else _third_party_reader(records)
    )
    model = WorkGraphReader(reader).read(
        GraphSelector("session", "session_1111111111111111")
    )
    expected = json.loads(
        (FIXTURES / "graph-reader-cases.json").read_text(encoding="utf-8")
    )["expected"]
    assert model.session_summary["work_item_count"] == expected["work_item_count"]
    assert len(model.edges) == expected["edge_count"]
    assert len(model.fan_out_groups) == expected["fan_out_count"]
    assert len(model.joins) == expected["join_count"]
    assert len(model.restore_generations) == expected["restore_count"]
    parent = next(
        item
        for item in model.work_items
        if item.work_item_id == "work_item_1111111111111111"
    )
    unknown = next(
        item
        for item in model.work_items
        if item.work_item_id == expected["unknown_work_item_id"]
    )
    assert parent.current_owner_id == expected["current_parent_owner"]
    assert parent.owner_generation == expected["current_parent_generation"]
    assert {item["event_type"] for item in unknown.unresolved_facts} >= {
        "outcome_unknown", "cancellation_unresolved"
    }
    assert model.timeline == tuple(sorted(
        model.timeline, key=lambda item: item.sequence if item.sequence is not None else 9999
    ))


def test_work_selector_navigates_explicit_children_only() -> None:
    model = WorkGraphReader(_candidate_reader(_fixture_records())).read(
        GraphSelector("work", "work_item_1111111111111111")
    )
    assert {item.work_item_id for item in model.work_items} == {
        "work_item_1111111111111111",
        "work_item_2222222222222222",
        "work_item_3333333333333333",
    }


def test_compatibility_reader_reports_loss_and_never_infers_lineage(tmp_path: Path) -> None:
    run = tmp_path / "opaque-run"
    run.mkdir()
    (run / "manifest.json").write_text(
        json.dumps({
            "schema_version": "v1", "run_id": "opaque-run", "status": "completed",
            "step_count": 0, "event_count": 1,
            "parent_run_id": "metadata-only-parent",
            "summary": {"stop_reason": "final", "final_result": "ok"},
        }),
        encoding="utf-8",
    )
    (run / "events.jsonl").write_text(
        '{"step_id":0,"phase":"END","ok":true,"ts":"x"}\n',
        encoding="utf-8",
    )
    reader = TraceCompatibilityReader(tmp_path)
    model = WorkGraphReader(reader).read(GraphSelector("run", "opaque-run"))
    assert model.work_items == ()
    assert model.edges == ()
    loss_codes = {
        entry["code"] for entry in model.completeness["loss"]["entries"]
    }
    assert {"missing_work_item_id", "missing_snapshot_lineage"} <= loss_codes
    assert "unverified_parent_run_metadata" in loss_codes
    with pytest.raises(WorkGraphReadError, match="session_query_unavailable"):
        WorkGraphReader(reader).read(GraphSelector("session", "any-session"))


def test_privacy_projection_is_non_echoing_bounded_and_non_mutating() -> None:
    fixture = json.loads((FIXTURES / "privacy-cases.json").read_text(encoding="utf-8"))
    for case in fixture["cases"]:
        original = json.loads(json.dumps(case["value"]))
        limits = (
            ProjectionLimits(max_string_chars=case["max_string_chars"])
            if case.get("max_string_chars") is not None
            else None
        )
        result = project_data(
            case["value"], view=PrivacyView.SAFE_DIAGNOSTIC, limits=limits
        )
        assert case["value"] == original
        assert set(case["codes"]) <= {finding.code for finding in result.findings}
        rendered = json.dumps(result.data, ensure_ascii=False)
        assert "not-for-output" not in rendered
        assert all("not-for-output" not in json.dumps(finding.to_dict()) for finding in result.findings)

    cyclic: dict[str, Any] = {}
    cyclic["self"] = cyclic
    projected = project_data(cyclic, view=PrivacyView.REDACTED_PUBLIC)
    assert "cyclic_object" in {finding.code for finding in projected.findings}
    assert cyclic["self"] is cyclic


def test_qita_one_command_family_is_read_only_and_typed_blocked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    candidate = tmp_path / "candidate.json"
    candidate.write_text(
        json.dumps({"records": [record.to_dict() for record in _fixture_records()]}),
        encoding="utf-8",
    )
    code = qita_main([
        "inspect", "graph", "session_1111111111111111",
        "--candidate-store", str(candidate),
    ])
    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output["session_summary"]["work_item_count"] == 3
    assert "events" not in output

    code = qita_main([
        "inspect", "session", "session_1111111111111111", "--logdir", str(tmp_path)
    ])
    blocked = json.loads(capsys.readouterr().out)
    assert code == 2
    assert blocked["status"] == "blocked"
    assert blocked["code"] == "session_query_unavailable"
    assert list(tmp_path.iterdir()) == [candidate]
