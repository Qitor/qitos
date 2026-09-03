from __future__ import annotations

import hashlib
from dataclasses import replace

from qitos.tracing.exporter import CanonicalTrajectoryExporter
from qitos.tracing.publication import (
    REQUIRED_PUBLICATION_SCANS,
    ScanReceipt,
    TransformReceipt,
    qualify_publication_artifact,
)
from qitos.tracing.trajectory import PrivacyView, RecordKind, Trajectory, TrajectoryRecord


def _private_trajectory() -> Trajectory:
    return Trajectory(
        records=(
            TrajectoryRecord.create(
                RecordKind.MODEL_REQUEST,
                record_id="request",
                run_id="run-1",
                payload={
                    "authorization": "Bearer publication-secret-value",
                    "artifact_body": "private body",
                    "path": "/Users/example/private.txt",
                    "endpoint": "http://127.0.0.1:8080",
                },
            ).with_sequence(0),
        ),
        provenance={"source": "offline-test"},
    )


def _receipts(digest: str) -> tuple[ScanReceipt, ...]:
    return tuple(
        ScanReceipt(scanner_id=name, payload_digest=digest, passed=True)
        for name in REQUIRED_PUBLICATION_SCANS
    )


def test_redacted_artifact_qualification_is_content_bound_and_not_global() -> None:
    raw = _private_trajectory()
    artifact = CanonicalTrajectoryExporter().export(
        raw, view=PrivacyView.REDACTED_PUBLIC
    )
    source_digest = hashlib.sha256(
        CanonicalTrajectoryExporter()
        .export(raw, view=PrivacyView.RAW_PRIVATE)
        .data
    ).hexdigest()
    result = qualify_publication_artifact(
        artifact,
        license_id="MIT",
        license_qualified=True,
        transform=TransformReceipt(
            transform_id="qitos.redaction/1",
            source_digest=source_digest,
            output_digest=artifact.digest,
            deterministic=True,
        ),
        scans=_receipts(artifact.digest),
    )

    assert result.qualified
    assert result.to_dict()["global_publication_ready"] is False
    assert result.to_dict()["schema_frozen"] is False
    assert b"publication-secret-value" not in artifact.data
    assert b"/Users/" not in artifact.data
    assert not result.loss.is_lossless


def test_hash_identity_cannot_replace_sanitization_license_or_scans() -> None:
    artifact = CanonicalTrajectoryExporter().export(
        _private_trajectory(), view=PrivacyView.RAW_PRIVATE
    )
    result = qualify_publication_artifact(
        artifact,
        license_id="",
        license_qualified=False,
        transform=TransformReceipt(
            transform_id="identity",
            source_digest=artifact.digest,
            output_digest=artifact.digest,
            deterministic=True,
        ),
        scans=(),
    )
    assert not result.qualified
    assert "raw_private_view_rejected" in result.finding_codes
    assert "license_not_qualified" in result.finding_codes
    assert "secret_scan_missing" in result.finding_codes
    assert "public_payload_scan_failed" in result.finding_codes
    assert "publication-secret-value" not in str(result.finding_codes)


def test_mismatched_scan_is_rejected_without_echoing_payload() -> None:
    artifact = CanonicalTrajectoryExporter().export(
        _private_trajectory(), view=PrivacyView.REDACTED_PUBLIC
    )
    bad = list(_receipts(artifact.digest))
    bad[0] = replace(bad[0], payload_digest="0" * 64, finding_codes=("found",))
    result = qualify_publication_artifact(
        artifact,
        license_id="MIT",
        license_qualified=True,
        transform=TransformReceipt(
            transform_id="qitos.redaction/1",
            source_digest="1" * 64,
            output_digest=artifact.digest,
            deterministic=True,
        ),
        scans=bad,
    )
    assert not result.qualified
    assert all("publication-secret-value" not in code for code in result.finding_codes)
