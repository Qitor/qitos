"""Exact-producer qualification for the S2 continuity trajectory.

This gate validates committed runtime evidence.  It does not generate runtime
facts and cannot turn sink/store schema conformance into runtime qualification.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .privacy import portability_finding_codes


RECEIPT_VERSION = "qitos.s2.runtime-producer-receipt/1"
RECEIPT_SET_VERSION = "qitos.s2.runtime-producer-receipt-set/1"
QUALIFICATION_AUTHORITY = "qitos.integration.runtime-qualification/1"

REQUIRED_SCENARIOS: Dict[str, Tuple[str, ...]] = {
    "A": (
        "session_continuity",
        "pause_restore",
        "stale_rejection",
        "trace_cursor",
        "artifact_reference",
        "budget_continuity",
    ),
    "B": (
        "request_reasoning_continuation",
        "steering_applied_once",
        "loss_declaration",
    ),
    "C": (
        "parallel_tool_slots",
        "effect_receipt",
        "late_result_rejection",
    ),
}


@dataclass(frozen=True)
class QualificationFinding:
    code: str
    lane: Optional[str] = None
    scenario: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "code": self.code,
            "lane": self.lane,
            "scenario": self.scenario,
        }


@dataclass(frozen=True)
class RuntimeQualificationResult:
    status: str
    qualified_lanes: Tuple[str, ...]
    qualified_scenarios: Tuple[str, ...]
    findings: Tuple[QualificationFinding, ...]
    s2_runtime_ready: bool
    trajectory_schema_publication_ready: bool = False
    qita_store_reader_default: bool = False
    measurement_claims_available: bool = False

    @property
    def runtime_producer_qualified(self) -> bool:
        return self.s2_runtime_ready

    @property
    def trajectory_schema_frozen(self) -> bool:
        return False

    @property
    def publication_ready(self) -> bool:
        return self.trajectory_schema_publication_ready

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "s2_runtime_ready": self.s2_runtime_ready,
            "qualified_lanes": list(self.qualified_lanes),
            "qualified_scenarios": list(self.qualified_scenarios),
            "findings": [finding.to_dict() for finding in self.findings],
            "trajectory_schema/publication_ready": (
                self.trajectory_schema_publication_ready
            ),
            "qita_store_reader_default": self.qita_store_reader_default,
            "measurement_claims_available": self.measurement_claims_available,
            "claims": [],
            "measurements": [],
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_relative_path(root: Path, value: Any) -> Optional[Path]:
    text = str(value or "")
    if not text or portability_finding_codes(text):
        return None
    candidate = Path(text)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def _git_bytes(root: Path, commit: str, relative_path: str) -> Optional[bytes]:
    try:
        result = subprocess.run(
            ["git", "show", f"{commit}:{relative_path}"],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout


def _evidence_scenarios(value: Mapping[str, Any]) -> Tuple[str, ...]:
    results = value.get("scenario_results")
    if not isinstance(results, list):
        return ()
    qualified = []
    for item in results:
        if not isinstance(item, Mapping):
            continue
        if item.get("status") != "passed":
            continue
        scenario = str(item.get("scenario", ""))
        if scenario:
            qualified.append(scenario)
    return tuple(dict.fromkeys(qualified))


def validate_runtime_receipt(
    receipt: Mapping[str, Any],
    *,
    repository_root: Path,
) -> Tuple[Tuple[str, ...], Tuple[QualificationFinding, ...]]:
    """Validate one exact, committed producer receipt without echoing values."""
    findings: List[QualificationFinding] = []
    lane = str(receipt.get("lane", ""))
    safe_lane = lane if lane in REQUIRED_SCENARIOS else None
    if receipt.get("receipt_version") != RECEIPT_VERSION:
        findings.append(QualificationFinding("unsupported_receipt_version", safe_lane))
    if safe_lane is None:
        findings.append(QualificationFinding("unknown_producer_lane"))
    if receipt.get("qualification_authority") != QUALIFICATION_AUTHORITY:
        findings.append(QualificationFinding("invalid_qualification_authority", safe_lane))
    if portability_finding_codes(receipt):
        findings.append(QualificationFinding("unsafe_receipt_content", safe_lane))

    commit = str(receipt.get("producer_commit", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        findings.append(QualificationFinding("invalid_producer_commit", safe_lane))

    bindings = (
        ("fixture", receipt.get("fixture_path"), receipt.get("fixture_sha256")),
        (
            "qualification",
            receipt.get("qualification_path"),
            receipt.get("qualification_sha256"),
        ),
    )
    loaded: Dict[str, bytes] = {}
    for role, raw_path, raw_digest in bindings:
        path = _safe_relative_path(repository_root, raw_path)
        digest = str(raw_digest or "")
        if path is None:
            findings.append(QualificationFinding(f"invalid_{role}_path", safe_lane))
            continue
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            findings.append(QualificationFinding(f"invalid_{role}_digest", safe_lane))
            continue
        try:
            current = path.read_bytes()
        except OSError:
            findings.append(QualificationFinding(f"missing_{role}", safe_lane))
            continue
        relative_path = path.relative_to(repository_root.resolve()).as_posix()
        committed = _git_bytes(repository_root, commit, relative_path)
        if committed is None:
            findings.append(
                QualificationFinding(f"{role}_not_at_producer_commit", safe_lane)
            )
            continue
        if _sha256(committed) != digest:
            findings.append(QualificationFinding(f"{role}_digest_mismatch", safe_lane))
        if current != committed:
            findings.append(QualificationFinding(f"{role}_worktree_mismatch", safe_lane))
        loaded[role] = current

    qualified: Tuple[str, ...] = ()
    evidence_bytes = loaded.get("qualification")
    if evidence_bytes is not None:
        try:
            evidence = json.loads(evidence_bytes)
        except json.JSONDecodeError:
            findings.append(QualificationFinding("invalid_qualification_json", safe_lane))
            evidence = None
        if isinstance(evidence, Mapping):
            if evidence.get("runtime_execution") is not True:
                findings.append(QualificationFinding("runtime_execution_not_proven", safe_lane))
            if evidence.get("synthetic") is not False:
                findings.append(QualificationFinding("synthetic_evidence_rejected", safe_lane))
            qualified = _evidence_scenarios(evidence)
            if safe_lane is not None:
                declared = set(str(item) for item in receipt.get("scenarios") or [])
                required = set(REQUIRED_SCENARIOS[safe_lane])
                if declared != required:
                    findings.append(QualificationFinding("scenario_set_mismatch", safe_lane))
                missing = required.difference(qualified)
                for scenario in sorted(missing):
                    findings.append(
                        QualificationFinding(
                            "runtime_scenario_not_passed",
                            safe_lane,
                            scenario,
                        )
                    )
                if set(qualified).difference(required):
                    findings.append(
                        QualificationFinding(
                            "qualification_scenario_set_mismatch",
                            safe_lane,
                        )
                    )

    if findings:
        return (), tuple(findings)
    return qualified, ()


def qualify_runtime(
    receipts: Iterable[Mapping[str, Any]],
    *,
    repository_root: Path,
) -> RuntimeQualificationResult:
    """Qualify only when exact A/B/C runtime evidence is complete."""
    findings: List[QualificationFinding] = []
    qualified_by_lane: Dict[str, Tuple[str, ...]] = {}
    lane_counts: Dict[str, int] = {}
    for receipt in receipts:
        lane = str(receipt.get("lane", ""))
        if lane in REQUIRED_SCENARIOS:
            lane_counts[lane] = lane_counts.get(lane, 0) + 1
        scenarios, receipt_findings = validate_runtime_receipt(
            receipt,
            repository_root=repository_root,
        )
        findings.extend(receipt_findings)
        if not receipt_findings and lane in REQUIRED_SCENARIOS:
            qualified_by_lane[lane] = scenarios

    for lane, count in sorted(lane_counts.items()):
        if count > 1:
            findings.append(QualificationFinding("duplicate_lane_receipt", lane))
            qualified_by_lane.pop(lane, None)
    for lane, required in REQUIRED_SCENARIOS.items():
        if lane not in qualified_by_lane:
            findings.append(QualificationFinding("producer_lane_not_qualified", lane))
            for scenario in required:
                findings.append(
                    QualificationFinding("runtime_fact_missing", lane, scenario)
                )

    runtime_ready = not findings and set(qualified_by_lane) == set(REQUIRED_SCENARIOS)
    scenarios = tuple(
        scenario
        for lane in sorted(qualified_by_lane)
        for scenario in qualified_by_lane[lane]
    )
    return RuntimeQualificationResult(
        status="s2_runtime_ready" if runtime_ready else "s2_runtime_blocked",
        qualified_lanes=tuple(sorted(qualified_by_lane)),
        qualified_scenarios=scenarios,
        findings=tuple(findings),
        s2_runtime_ready=runtime_ready,
    )


def load_receipts(path: Path) -> Tuple[Mapping[str, Any], ...]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("receipt set must be an object")
    if value.get("receipt_set_version") != RECEIPT_SET_VERSION:
        raise ValueError("unsupported receipt set version")
    receipts = value.get("receipts")
    if not isinstance(receipts, list):
        raise ValueError("receipt set receipts must be a list")
    return tuple(item for item in receipts if isinstance(item, Mapping))


__all__ = [
    "QUALIFICATION_AUTHORITY",
    "RECEIPT_SET_VERSION",
    "RECEIPT_VERSION",
    "REQUIRED_SCENARIOS",
    "QualificationFinding",
    "RuntimeQualificationResult",
    "load_receipts",
    "qualify_runtime",
    "validate_runtime_receipt",
]
