"""Artifact-level publication qualification for Trajectory exports.

This module can qualify one transformed payload. It cannot freeze the candidate
schema, enable a writer, switch qita, or declare the release publication-ready.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Tuple

from .privacy import portability_finding_codes
from .trajectory import LossReport, PrivacyView


REQUIRED_PUBLICATION_SCANS = (
    "artifact_body",
    "host_path",
    "local_endpoint",
    "secret",
)

_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class TransformReceipt:
    transform_id: str
    source_digest: str
    output_digest: str
    deterministic: bool


@dataclass(frozen=True)
class ScanReceipt:
    scanner_id: str
    payload_digest: str
    passed: bool
    finding_codes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PublicationQualification:
    status: str
    payload_digest: str
    finding_codes: Tuple[str, ...]
    loss: LossReport

    @property
    def qualified(self) -> bool:
        return self.status == "artifact_qualified"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "payload_digest": self.payload_digest,
            "finding_codes": list(self.finding_codes),
            "loss": self.loss.to_dict(),
            "global_publication_ready": False,
            "schema_frozen": False,
        }


def qualify_publication_artifact(
    artifact: Any,
    *,
    license_id: str,
    license_qualified: bool,
    transform: TransformReceipt,
    scans: Iterable[ScanReceipt],
) -> PublicationQualification:
    """Qualify one payload using non-echoing, content-bound receipts."""
    findings = []
    data = bytes(getattr(artifact, "data", b""))
    payload_digest = hashlib.sha256(data).hexdigest()
    artifact_digest = str(getattr(artifact, "digest", ""))
    privacy_view = getattr(artifact, "privacy_view", None)
    loss = getattr(artifact, "loss", LossReport(policy_id="qitos.loss/unknown"))
    if not isinstance(loss, LossReport):
        findings.append("invalid_loss_report")
        loss = LossReport(policy_id="qitos.loss/unknown")
    if not license_id.strip() or not license_qualified:
        findings.append("license_not_qualified")
    if privacy_view not in {
        PrivacyView.REDACTED_PUBLIC,
        PrivacyView.SAFE_DIAGNOSTIC,
    }:
        findings.append("raw_private_view_rejected")
    if artifact_digest != payload_digest:
        findings.append("payload_digest_mismatch")
    if not transform.transform_id.strip() or not transform.deterministic:
        findings.append("transform_not_qualified")
    if transform.output_digest != payload_digest:
        findings.append("transform_output_digest_mismatch")
    if not _SHA256.fullmatch(transform.source_digest):
        findings.append("transform_source_digest_invalid")
    try:
        unsafe_codes = portability_finding_codes(data.decode("utf-8"))
    except UnicodeDecodeError:
        unsafe_codes = ("non_utf8_public_payload",)
    if unsafe_codes:
        findings.append("public_payload_scan_failed")

    scan_receipts = tuple(scans)
    by_id = {receipt.scanner_id: receipt for receipt in scan_receipts}
    if len(by_id) != len(scan_receipts):
        findings.append("duplicate_scan_receipt")
    for scanner_id in REQUIRED_PUBLICATION_SCANS:
        receipt = by_id.get(scanner_id)
        if receipt is None:
            findings.append(f"{scanner_id}_scan_missing")
            continue
        if receipt.payload_digest != payload_digest:
            findings.append(f"{scanner_id}_scan_digest_mismatch")
        if not receipt.passed or receipt.finding_codes:
            findings.append(f"{scanner_id}_scan_failed")

    unique_findings = tuple(dict.fromkeys(findings))
    return PublicationQualification(
        status="artifact_qualified" if not unique_findings else "artifact_rejected",
        payload_digest=payload_digest,
        finding_codes=unique_findings,
        loss=loss,
    )


__all__ = [
    "PublicationQualification",
    "REQUIRED_PUBLICATION_SCANS",
    "ScanReceipt",
    "TransformReceipt",
    "qualify_publication_artifact",
]
