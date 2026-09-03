"""Versioned trajectory exporters with explicit fidelity and re-import rules."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Protocol, Tuple, runtime_checkable

from .privacy import project_data
from .sinks import project_record
from .trajectory import (
    EXPORT_SCHEMA_VERSION,
    LossEntry,
    LossReport,
    PrivacyView,
    RecordKind,
    RecordRole,
    Trajectory,
    TrajectoryRecord,
    canonical_json_bytes,
    integrity_digest,
)


class TrajectoryExportError(RuntimeError):
    """Raised for invalid, unsupported, or corrupted exports."""


@dataclass(frozen=True)
class ExportCapabilities:
    exporter_id: str
    format_version: str
    exact_reimport: bool
    supported_views: Tuple[PrivacyView, ...]


@dataclass(frozen=True)
class ExportArtifact:
    exporter_id: str
    format_version: str
    content_type: str
    data: bytes
    digest: str
    privacy_view: PrivacyView
    exact_reimport: bool
    provenance: Dict[str, Any]
    loss: LossReport

    @property
    def size_bytes(self) -> int:
        return len(self.data)


@runtime_checkable
class TrajectoryExporter(Protocol):
    @property
    def capabilities(self) -> ExportCapabilities:
        ...

    def export(
        self,
        trajectory: Trajectory,
        *,
        view: PrivacyView = PrivacyView.REDACTED_PUBLIC,
    ) -> ExportArtifact:
        ...

    def reimport(self, artifact: ExportArtifact) -> Trajectory:
        ...


def _project_trajectory(
    trajectory: Trajectory, view: PrivacyView
) -> Trajectory:
    if view == PrivacyView.RAW_PRIVATE:
        return Trajectory.from_dict(trajectory.to_dict())
    records = tuple(project_record(record, view) for record in trajectory.records)
    metadata = project_data(trajectory.metadata, view=view)
    provenance = project_data(trajectory.provenance, view=view)
    return Trajectory(
        records=records,
        metadata=copy.deepcopy(dict(metadata.data or {})),
        provenance=copy.deepcopy(dict(provenance.data or {})),
        privacy_view=view,
        loss=trajectory.loss.merged(
            *(record.loss for record in records),
            metadata.loss,
            provenance.loss,
        ),
    )


class CanonicalTrajectoryExporter:
    """Canonical JSON exporter; exact for the selected projection."""

    @property
    def capabilities(self) -> ExportCapabilities:
        return ExportCapabilities(
            exporter_id="qitos.canonical_trajectory",
            format_version=EXPORT_SCHEMA_VERSION,
            exact_reimport=True,
            supported_views=(
                PrivacyView.RAW_PRIVATE,
                PrivacyView.REDACTED_PUBLIC,
                PrivacyView.SAFE_DIAGNOSTIC,
            ),
        )

    def export(
        self,
        trajectory: Trajectory,
        *,
        view: PrivacyView = PrivacyView.REDACTED_PUBLIC,
    ) -> ExportArtifact:
        projected = _project_trajectory(trajectory, view)
        document: Dict[str, Any] = {
            "format_version": self.capabilities.format_version,
            "exporter_id": self.capabilities.exporter_id,
            "privacy_view": view.value,
            "exact_reimport": True,
            "provenance": copy.deepcopy(projected.provenance),
            "loss": projected.loss.to_dict(),
            "trajectory": projected.to_dict(),
        }
        document["content_digest"] = integrity_digest(document)
        data = canonical_json_bytes(document)
        return ExportArtifact(
            exporter_id=self.capabilities.exporter_id,
            format_version=self.capabilities.format_version,
            content_type="application/json",
            data=data,
            digest=hashlib.sha256(data).hexdigest(),
            privacy_view=view,
            exact_reimport=True,
            provenance=copy.deepcopy(projected.provenance),
            loss=projected.loss,
        )

    def reimport(self, artifact: ExportArtifact) -> Trajectory:
        if artifact.exporter_id != self.capabilities.exporter_id:
            raise TrajectoryExportError("exporter_id_mismatch")
        if artifact.format_version != self.capabilities.format_version:
            raise TrajectoryExportError("artifact_version_mismatch")
        if not artifact.exact_reimport:
            raise TrajectoryExportError("artifact_exactness_mismatch")
        if hashlib.sha256(artifact.data).hexdigest() != artifact.digest:
            raise TrajectoryExportError("artifact_digest_mismatch")
        try:
            document = json.loads(artifact.data)
        except json.JSONDecodeError as exc:
            raise TrajectoryExportError("invalid_export_json") from exc
        if document.get("format_version") != self.capabilities.format_version:
            raise TrajectoryExportError("unsupported_export_version")
        if document.get("exporter_id") != self.capabilities.exporter_id:
            raise TrajectoryExportError("document_exporter_id_mismatch")
        if document.get("exact_reimport") is not True:
            raise TrajectoryExportError("document_exactness_mismatch")
        if document.get("privacy_view") != artifact.privacy_view.value:
            raise TrajectoryExportError("privacy_view_mismatch")
        supplied_digest = str(document.get("content_digest", ""))
        digest_input = dict(document)
        digest_input.pop("content_digest", None)
        if supplied_digest != integrity_digest(digest_input):
            raise TrajectoryExportError("content_digest_mismatch")
        trajectory_value = document.get("trajectory")
        if not isinstance(trajectory_value, Mapping):
            raise TrajectoryExportError("trajectory_missing")
        return Trajectory.from_dict(trajectory_value)


class EventSummaryExporter:
    """Deliberately lossy exporter retaining event identity/order invariants."""

    @property
    def capabilities(self) -> ExportCapabilities:
        return ExportCapabilities(
            exporter_id="qitos.event_summary",
            format_version="qitos.event-summary/candidate-1",
            exact_reimport=False,
            supported_views=(
                PrivacyView.REDACTED_PUBLIC,
                PrivacyView.SAFE_DIAGNOSTIC,
            ),
        )

    @staticmethod
    def _loss(trajectory: Trajectory) -> LossReport:
        by_kind = {
            kind: sum(record.kind == kind for record in trajectory.records)
            for kind in RecordKind
        }
        return trajectory.loss.merged(
            LossReport(
                policy_id="qitos.export/event-summary",
                entries=(
                    LossEntry(
                        code="record_payload_omitted",
                        scope="records.payload",
                        count=len(trajectory.records),
                        consequence="exact_replay_unavailable",
                    ),
                    LossEntry(
                        code="artifact_detail_omitted",
                        scope="records.artifact_refs",
                        count=sum(
                            len(record.artifact_refs)
                            for record in trajectory.records
                        ),
                        consequence="artifact_resolution_unavailable",
                    ),
                    LossEntry(
                        code="reasoning_omitted",
                        scope="records.reasoning",
                        count=by_kind[RecordKind.REASONING],
                        consequence="reasoning_replay_unavailable",
                    ),
                    LossEntry(
                        code="continuation_omitted",
                        scope="records.continuation",
                        count=by_kind[RecordKind.CONTINUATION],
                        consequence="provider_continuation_unavailable",
                    ),
                    LossEntry(
                        code="tool_batch_order_omitted",
                        scope="records.tool_batch",
                        count=by_kind[RecordKind.TOOL_BATCH],
                        consequence="batch_replay_unavailable",
                    ),
                    LossEntry(
                        code="effect_detail_omitted",
                        scope="records.effect",
                        count=by_kind[RecordKind.EFFECT],
                        consequence="effect_reconciliation_unavailable",
                    ),
                    LossEntry(
                        code="sandbox_detail_omitted",
                        scope="records.sandbox",
                        count=by_kind[RecordKind.SANDBOX],
                        consequence="sandbox_attestation_unavailable",
                    ),
                    LossEntry(
                        code="owner_generation_omitted",
                        scope="records.owner_generation",
                        count=sum(
                            record.owner_generation is not None
                            for record in trajectory.records
                        ),
                        consequence="ownership_replay_unavailable",
                    ),
                    LossEntry(
                        code="work_graph_detail_omitted",
                        scope="records.work_graph",
                        count=by_kind[RecordKind.WORK_GRAPH],
                        consequence="graph_replay_unavailable",
                    ),
                    LossEntry(
                        code="uncertainty_detail_omitted",
                        scope="records.loss",
                        count=sum(
                            not record.loss.is_lossless
                            for record in trajectory.records
                        ),
                        consequence="uncertainty_replay_unavailable",
                    ),
                ),
            )
        )

    def export(
        self,
        trajectory: Trajectory,
        *,
        view: PrivacyView = PrivacyView.REDACTED_PUBLIC,
    ) -> ExportArtifact:
        if view not in self.capabilities.supported_views:
            raise TrajectoryExportError("unsupported_privacy_view")
        projected = _project_trajectory(trajectory, view)
        loss = self._loss(projected)
        records = [
            {
                "record_id": record.record_id,
                "sequence": record.sequence,
                "kind": record.kind.value,
                "role": record.role.value,
                "occurred_at": record.occurred_at,
                "recorded_at": record.recorded_at,
                "session_id": record.session_id,
                "run_id": record.run_id,
                "work_item_id": record.work_item_id,
                "step_id": record.step_id,
                "phase": record.phase,
                "agent_id": record.agent_id,
                "causation_id": record.causation_id,
                "correlation_id": record.correlation_id,
            }
            for record in projected.records
        ]
        document: Dict[str, Any] = {
            "format_version": self.capabilities.format_version,
            "exporter_id": self.capabilities.exporter_id,
            "privacy_view": view.value,
            "exact_reimport": False,
            "provenance": copy.deepcopy(projected.provenance),
            "loss": loss.to_dict(),
            "records": records,
        }
        document["content_digest"] = integrity_digest(document)
        data = canonical_json_bytes(document)
        return ExportArtifact(
            exporter_id=self.capabilities.exporter_id,
            format_version=self.capabilities.format_version,
            content_type="application/json",
            data=data,
            digest=hashlib.sha256(data).hexdigest(),
            privacy_view=view,
            exact_reimport=False,
            provenance=copy.deepcopy(projected.provenance),
            loss=loss,
        )

    def reimport(self, artifact: ExportArtifact) -> Trajectory:
        if artifact.exporter_id != self.capabilities.exporter_id:
            raise TrajectoryExportError("exporter_id_mismatch")
        if artifact.format_version != self.capabilities.format_version:
            raise TrajectoryExportError("artifact_version_mismatch")
        if artifact.exact_reimport:
            raise TrajectoryExportError("artifact_exactness_mismatch")
        try:
            document = json.loads(artifact.data)
        except json.JSONDecodeError as exc:
            raise TrajectoryExportError("invalid_export_json") from exc
        if hashlib.sha256(artifact.data).hexdigest() != artifact.digest:
            raise TrajectoryExportError("artifact_digest_mismatch")
        if document.get("format_version") != self.capabilities.format_version:
            raise TrajectoryExportError("unsupported_export_version")
        if document.get("exporter_id") != self.capabilities.exporter_id:
            raise TrajectoryExportError("document_exporter_id_mismatch")
        if document.get("exact_reimport") is not False:
            raise TrajectoryExportError("document_exactness_mismatch")
        if document.get("privacy_view") != artifact.privacy_view.value:
            raise TrajectoryExportError("privacy_view_mismatch")
        supplied_digest = str(document.get("content_digest", ""))
        digest_input = dict(document)
        digest_input.pop("content_digest", None)
        if supplied_digest != integrity_digest(digest_input):
            raise TrajectoryExportError("content_digest_mismatch")
        loss = LossReport.from_dict(dict(document.get("loss") or {}))
        records = []
        for item in document.get("records") or []:
            if not isinstance(item, Mapping):
                continue
            record = TrajectoryRecord.create(
                RecordKind(str(item["kind"])),
                role=RecordRole(str(item["role"])),
                record_id=str(item["record_id"]),
                payload={},
                sequence=(
                    int(item["sequence"])
                    if item.get("sequence") is not None
                    else None
                ),
                occurred_at=str(item["occurred_at"]),
                recorded_at=str(item["recorded_at"]),
                session_id=item.get("session_id"),
                run_id=item.get("run_id"),
                work_item_id=item.get("work_item_id"),
                step_id=item.get("step_id"),
                phase=item.get("phase"),
                agent_id=item.get("agent_id"),
                causation_id=item.get("causation_id"),
                correlation_id=item.get("correlation_id"),
                privacy_view=artifact.privacy_view,
                loss=loss,
            )
            records.append(record)
        return Trajectory(
            records=tuple(records),
            provenance=copy.deepcopy(dict(document.get("provenance") or {})),
            privacy_view=artifact.privacy_view,
            loss=loss,
        )


__all__ = [
    "CanonicalTrajectoryExporter",
    "EventSummaryExporter",
    "ExportArtifact",
    "ExportCapabilities",
    "TrajectoryExportError",
    "TrajectoryExporter",
]
