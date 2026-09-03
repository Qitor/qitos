from __future__ import annotations

from dataclasses import replace

import pytest

from qitos.tracing.exporter import (
    CanonicalTrajectoryExporter,
    EventSummaryExporter,
    TrajectoryExporter,
)
from qitos.tracing.exporter import TrajectoryExportError
from qitos.tracing.trajectory import (
    PrivacyView,
    RecordKind,
    Trajectory,
    TrajectoryRecord,
)


def _trajectory() -> Trajectory:
    records = (
        TrajectoryRecord.create(
            RecordKind.RUN,
            record_id="run-start",
            session_id="session-1",
            run_id="run-1",
            payload={"status": "running"},
        ).with_sequence(0),
        TrajectoryRecord.create(
            RecordKind.MODEL_RESPONSE,
            record_id="response-1",
            session_id="session-1",
            run_id="run-1",
            step_id=0,
            payload={
                "text": "answer",
                "authorization": "Bearer private-export-value",
                "host_path": "/Users/example/private.json",
            },
        ).with_sequence(1),
    )
    return Trajectory(
        records=records,
        metadata={"purpose": "conformance"},
        provenance={"producer": "test-runtime"},
    )


def test_canonical_export_exactly_reimports_selected_private_view() -> None:
    trajectory = _trajectory()
    exporter = CanonicalTrajectoryExporter()
    artifact = exporter.export(trajectory, view=PrivacyView.RAW_PRIVATE)
    restored = exporter.reimport(artifact)

    assert artifact.exact_reimport
    assert restored.to_dict() == trajectory.to_dict()
    assert b"private-export-value" in artifact.data


def test_canonical_public_export_is_sanitized_with_explicit_loss() -> None:
    trajectory = _trajectory()
    artifact = CanonicalTrajectoryExporter().export(
        trajectory,
        view=PrivacyView.REDACTED_PUBLIC,
    )
    restored = CanonicalTrajectoryExporter().reimport(artifact)

    assert b"private-export-value" not in artifact.data
    assert b"/Users/" not in artifact.data
    assert not restored.loss.is_lossless
    assert trajectory.records[1].payload["authorization"].startswith("Bearer")


def test_lossy_export_reimports_declared_invariants_only() -> None:
    trajectory = _trajectory()
    exporter = EventSummaryExporter()
    artifact = exporter.export(
        trajectory,
        view=PrivacyView.REDACTED_PUBLIC,
    )
    restored = exporter.reimport(artifact)

    assert artifact.exact_reimport is False
    assert not artifact.loss.is_lossless
    assert [record.record_id for record in restored.records] == [
        record.record_id for record in trajectory.records
    ]
    assert [record.kind for record in restored.records] == [
        record.kind for record in trajectory.records
    ]
    assert [record.sequence for record in restored.records] == [0, 1]
    assert all(record.payload == {} for record in restored.records)
    codes = {entry.code for entry in restored.loss.entries}
    assert {
        "record_payload_omitted",
        "artifact_detail_omitted",
        "reasoning_omitted",
        "continuation_omitted",
        "tool_batch_order_omitted",
        "effect_detail_omitted",
        "sandbox_detail_omitted",
        "owner_generation_omitted",
        "work_graph_detail_omitted",
        "uncertainty_detail_omitted",
    } <= codes


class _ThirdPartyExporter:
    """Structural extension with no inheritance or store access."""

    def __init__(self) -> None:
        self._delegate = CanonicalTrajectoryExporter()

    @property
    def capabilities(self):
        return self._delegate.capabilities

    def export(self, trajectory, *, view=PrivacyView.REDACTED_PUBLIC):
        return self._delegate.export(trajectory, view=view)

    def reimport(self, artifact):
        return self._delegate.reimport(artifact)


def test_independent_exporter_structurally_conforms_without_store_access() -> None:
    exporter = _ThirdPartyExporter()
    assert isinstance(exporter, TrajectoryExporter)
    trajectory = _trajectory()
    artifact = exporter.export(trajectory, view=PrivacyView.RAW_PRIVATE)
    assert exporter.reimport(artifact).to_dict() == trajectory.to_dict()


def test_export_digest_corruption_is_rejected() -> None:
    artifact = CanonicalTrajectoryExporter().export(
        _trajectory(),
        view=PrivacyView.RAW_PRIVATE,
    )
    corrupted = replace(artifact, data=artifact.data + b" ")
    with pytest.raises(TrajectoryExportError, match="artifact_digest_mismatch"):
        CanonicalTrajectoryExporter().reimport(corrupted)


def test_export_envelope_mismatch_is_rejected() -> None:
    artifact = CanonicalTrajectoryExporter().export(
        _trajectory(),
        view=PrivacyView.REDACTED_PUBLIC,
    )
    mismatched = replace(artifact, privacy_view=PrivacyView.RAW_PRIVATE)
    with pytest.raises(TrajectoryExportError, match="privacy_view_mismatch"):
        CanonicalTrajectoryExporter().reimport(mismatched)
