#!/usr/bin/env python3
"""Strict, portable readiness gate for the future Trajectory architecture.

This stdlib-only development tool validates publication evidence and caller-
owned contract receipts. It never defines Trajectory records, parses trajectory
payloads, benchmarks storage, or qualifies a contract from file presence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from qitos.core.diagnostics import (
    _diagnostic_key_is_sensitive,
    _diagnostic_string_categories,
)


RESULT_TYPE = "trajectory_readiness_report"
RESULT_SCHEMA_VERSION = "1"
MANIFEST_VERSION = "trajectory-fixture-source-manifest-v1"
RECEIPT_SET_TYPE = "trajectory_contract_qualification_receipts"
RECEIPT_SET_SCHEMA_VERSION = "1"
COMPAT_RECEIPT_SET_VERSION = "trajectory-contract-qualification-receipts-v1"
TRANSFORM_RECEIPT_VERSION = "trajectory-fixture-transform-receipt-v1"
LOSS_REPORT_VERSION = "trajectory-fixture-loss-report-v1"
MANIFEST_NAME = "fixture-manifest.json"
DEFAULT_FIXTURE_SET_ID = "qitos-representative-trajectories"
S1_QUALIFICATION_AUTHORITY = "qitos.s1.integration_owner/v1"


@dataclass(frozen=True)
class ProducerBinding:
    """One reviewed producer bundle shared by independently receipted contracts."""

    contract_id: str
    version: str
    source_commit: str
    fixture_path: str
    fixture_sha256: str
    evidence_path: str
    evidence_sha256: str


G2_PRODUCER_BINDINGS = {
    "lane_a": ProducerBinding(
        contract_id="qitos.session_contract_bundle",
        version="qitos.session_contract_bundle/v2",
        source_commit="58864253a169d1bac5749ad2b2de5de6872c0da2",
        fixture_path="tests/fixtures/session/fixture-manifest.json",
        fixture_sha256=(
            "952dc20f3c412830ef1f18fe73805cc6d8e04ecc28d89e4991883c983a983466"
        ),
        evidence_path="tests/fixtures/session/qualification-evidence.json",
        evidence_sha256=(
            "7a7dfd831a4da4d45c2645d47404da8827f60aa498b92d9d98d92570cfe28834"
        ),
    ),
    "lane_b": ProducerBinding(
        contract_id="qitos.request_contract_bundle",
        version="qitos.request_contract_bundle/v1",
        source_commit="3cc29bea2bd311a2343862fd0b4f32636524bbb6",
        fixture_path="tests/fixtures/conversation/request_contracts.json",
        fixture_sha256=(
            "a42f6c8ede18acf408348b9f38d657095cbe32bd4613659c46258eb18eedc637"
        ),
        evidence_path=(
            "tests/fixtures/conversation/request-contracts-evidence.json"
        ),
        evidence_sha256=(
            "a72bc8d8627854b2b805a2e8ca762daaf0f50dc10b95b0af64bbd4a5399a04b1"
        ),
    ),
    "lane_c": ProducerBinding(
        contract_id="qitos.work_effect_contract_bundle",
        version="qitos.work_effect_contract_bundle/v2",
        source_commit="bd7fca95e9ba9acfbbd9e8d0655a14ece066bcb6",
        fixture_path="tests/fixtures/work_graph/g2-contract-manifest.json",
        fixture_sha256=(
            "d1112ac60a359af4bf6ff2525621214cea6dc8e52f2a03a8e69254e930a89964"
        ),
        evidence_path="tests/fixtures/work_graph/qualification-evidence.json",
        evidence_sha256=(
            "9ddef7c73b18698e6c9ec69431448b8a63501ac4527a4e64e44ee9d35596e26d"
        ),
    ),
}
G1_QUALIFICATION_AUTHORITY = "qitos.g1.integration_owner/v1"

SUPPORTED_SOURCE_CLASSES = {"campaign_long", "unrelated_agent"}
SUPPORTED_STATUSES = {
    "selected_source_only",
    "generator_selected_not_materialized",
    "sanitized_payload_ready",
}
SUPPORTED_LICENSE_STATUSES = {
    "authorization_required",
    "repository_license",
    "qualified",
}
SUPPORTED_SANITIZATION_STATUSES = {
    "not_started",
    "generator_selected_not_materialized",
    "sanitized_payload_ready",
}
UNKNOWN_COVERAGE_MARKERS = {
    "unknown_pending_lane_b_fixture",
    "unknown_pending_lane_c_receipt",
}
REQUIRED_COVERAGE_KEYS = {
    "long_run_scale",
    "run_step_phase_correlation",
    "multimodal_content",
    "parallel_tool_calls",
    "out_of_order_completion",
    "reasoning_continuation",
    "context_injection",
    "compaction",
    "artifact",
    "provider_failure",
    "tool_failure",
    "retry",
    "cancellation_timeout",
}
OPTIONAL_COVERAGE_KEYS = {
    "native_tool_call_result_correlation",
    "non_json_tool_result_normalization",
}


@dataclass(frozen=True)
class ContractRequirement:
    contract_id: str
    owner: str
    required_artifact: str
    short_message: str
    remediation: str
    expected_version: Optional[str]
    producer_contract_id: Optional[str] = None
    producer_source_commit: Optional[str] = None
    fixture_path: Optional[str] = None
    fixture_sha256: Optional[str] = None
    qualification_evidence_path: Optional[str] = None
    qualification_evidence_sha256: Optional[str] = None
    qualification_authority: Optional[str] = None
    compatibility_status: str = "not_established"
    required_identity_bindings: Tuple[str, ...] = ()
    requires_lineage_evidence: bool = False
    runtime_behavior_required: bool = True

    @property
    def producer_binding_complete(self) -> bool:
        return all(
            (
                self.expected_version,
                self.producer_contract_id,
                self.producer_source_commit,
                self.fixture_path,
                self.fixture_sha256,
                self.qualification_evidence_path,
                self.qualification_evidence_sha256,
                self.qualification_authority,
            )
        )


def _bind_g2_requirement(requirement: ContractRequirement) -> ContractRequirement:
    """Bind a G2 requirement to its reviewed semantic-owner artifact."""

    if requirement.expected_version is not None:
        return requirement
    binding = G2_PRODUCER_BINDINGS[requirement.owner]
    return replace(
        requirement,
        expected_version=binding.version,
        producer_contract_id=binding.contract_id,
        producer_source_commit=binding.source_commit,
        fixture_path=binding.fixture_path,
        fixture_sha256=binding.fixture_sha256,
        qualification_evidence_path=binding.evidence_path,
        qualification_evidence_sha256=binding.evidence_sha256,
        compatibility_status="qualified_g2_contract",
    )


# Every G2 item remains independently receipted even when several items share
# the same exact semantic-owner bundle. A receipt can therefore clear only its
# own contract_id, while all producer bytes stay content- and commit-addressed.
_CONTRACT_REQUIREMENTS = (
    ContractRequirement(
        "lane_b.exchange_log_fixture_version",
        "lane_b",
        "committed ExchangeLog fixture and producer-owned qualification evidence",
        "The accepted ExchangeLog foundation fixture must remain exactly bound.",
        "Use the integration-owner-approved G1 receipt; do not infer qualification from file presence.",
        "qitos.exchange_log.v2",
        producer_contract_id="qitos.exchange_log",
        producer_source_commit="2e46fc8e0228af42d6eaeaa6a665ffe5998c0bd5",
        fixture_path="tests/fixtures/conversation/v3/semantic_fixtures.json",
        fixture_sha256="927e0ace339337fa1a2c2cb5a1a8b03147df3ae4ec97b3b54634908249be8a40",
        qualification_evidence_path=(
            "tests/fixtures/conversation/v3/qualification-evidence.json"
        ),
        qualification_evidence_sha256=(
            "86d52fd2c6c3d37e33e35dd42a662d556e2fc96422be35e6c9d9a24529419b0a"
        ),
        qualification_authority=G1_QUALIFICATION_AUTHORITY,
        compatibility_status="qualified_foundation",
        runtime_behavior_required=False,
    ),
    ContractRequirement(
        "lane_c.canonical_tool_result_fixture_version",
        "lane_c",
        "committed canonical ToolResult fixture and producer-owned qualification evidence",
        "The accepted ToolResult foundation fixture must remain exactly bound.",
        "Use the integration-owner-approved G1 receipt; do not infer qualification from file presence.",
        "qitos.tool_result/v1",
        producer_contract_id="qitos.tool_result",
        producer_source_commit="9a0c5ed5d6c1c959ff277d3888f54c927be3e183",
        fixture_path="tests/fixtures/tool_results/v1/contract_hardening.json",
        fixture_sha256="b7f4dc6dfe8958bcd9c47617869a14bc8114629038d3428e6a623642fd2e5415",
        qualification_evidence_path=(
            "tests/fixtures/tool_results/v1/qualification-evidence.json"
        ),
        qualification_evidence_sha256=(
            "96b0e641ccca7e049a90658496a19964217aa7c359a29c6b6e6b345fb7cf99f5"
        ),
        qualification_authority=G1_QUALIFICATION_AUTHORITY,
        compatibility_status="qualified_foundation",
        runtime_behavior_required=False,
    ),
    ContractRequirement(
        "lane_a.identity_vocabulary",
        "lane_a",
        "identity vocabulary fixture",
        "Session, run, snapshot, checkpoint, work, attempt, and owner identities are not established.",
        "Lane A must publish a versioned identity fixture and qualification evidence.",
        None,
        qualification_authority=S1_QUALIFICATION_AUTHORITY,
        required_identity_bindings=(
            "session",
            "run",
            "snapshot",
            "checkpoint",
            "work",
            "attempt",
            "owner",
            "owner_generation",
            "head_generation",
        ),
    ),
    ContractRequirement(
        "lane_a.session_lifecycle",
        "lane_a",
        "session lifecycle and safe-transition fixture",
        "The durable session lifecycle is not established.",
        "Lane A must publish lifecycle transitions, terminal states, and typed invalid transitions.",
        None,
        qualification_authority=S1_QUALIFICATION_AUTHORITY,
    ),
    ContractRequirement(
        "lane_a.session_snapshot",
        "lane_a",
        "SessionSnapshot envelope fixture",
        "The immutable session snapshot envelope is not established.",
        "Lane A must publish the snapshot envelope with component ownership and compatibility evidence.",
        None,
        qualification_authority=S1_QUALIFICATION_AUTHORITY,
        requires_lineage_evidence=True,
    ),
    ContractRequirement(
        "lane_a.session_head_generation",
        "lane_a",
        "session head and generation conflict fixture",
        "The authoritative head and generation rules are not established.",
        "Lane A must publish expected-generation commit, stale-owner rejection, and last-safe-snapshot facts.",
        None,
        qualification_authority=S1_QUALIFICATION_AUTHORITY,
        required_identity_bindings=("session", "head_generation"),
    ),
    ContractRequirement(
        "lane_a.resolver_reference",
        "lane_a",
        "resolver reference fixture",
        "Process-independent resolver references are not established.",
        "Lane A must publish typed resolver references and missing/mismatch failure evidence without secrets or live objects.",
        None,
        qualification_authority=S1_QUALIFICATION_AUTHORITY,
    ),
    ContractRequirement(
        "lane_b.request_view",
        "lane_b",
        "RequestView fixture",
        "The provider-facing request projection is not established.",
        "Lane B must publish a versioned RequestView fixture with selection and loss facts.",
        None,
        qualification_authority=S1_QUALIFICATION_AUTHORITY,
    ),
    ContractRequirement(
        "lane_b.provider_codec",
        "lane_b",
        "provider transport/API-mode codec fixture",
        "Provider codec capability facts are not established.",
        "Lane B must publish transport/API-mode capability and typed failure evidence.",
        None,
        qualification_authority=S1_QUALIFICATION_AUTHORITY,
    ),
    ContractRequirement(
        "lane_b.codec_report",
        "lane_b",
        "CodecReport fixture",
        "Codec fidelity and loss reporting are not established.",
        "Lane B must publish a versioned CodecReport with input/output identity and declared loss.",
        None,
        qualification_authority=S1_QUALIFICATION_AUTHORITY,
    ),
    ContractRequirement(
        "lane_b.steering",
        "lane_b",
        "queued steering and consume-once fixture",
        "Queued steering lineage is not established.",
        "Lane B must publish accepted, queued, applied-once, and restore behavior at an explicit safe boundary.",
        None,
        qualification_authority=S1_QUALIFICATION_AUTHORITY,
        requires_lineage_evidence=True,
    ),
    ContractRequirement(
        "lane_b.provider_continuation",
        "lane_b",
        "opaque provider continuation fixture",
        "Opaque provider continuation policy is not established.",
        "Lane B must publish storage, replay, display prohibition, and unsupported-transfer evidence.",
        None,
        qualification_authority=S1_QUALIFICATION_AUTHORITY,
    ),
    ContractRequirement(
        "lane_b.context_artifact_snapshot",
        "lane_b",
        "context, compaction, and ArtifactRef snapshot component",
        "Context/artifact snapshot facts are not established.",
        "Lane B must publish referenced context/artifact components, loss facts, and missing/corrupt behavior.",
        None,
        qualification_authority=S1_QUALIFICATION_AUTHORITY,
    ),
    ContractRequirement(
        "lane_c.effect_recovery",
        "lane_c",
        "attempt/effect/recovery fixture",
        "Effect and recovery truth is not established.",
        "Lane C must publish attempt identity, idempotency, effect states, reconciliation, and outcome-unknown evidence.",
        None,
        qualification_authority=S1_QUALIFICATION_AUTHORITY,
        required_identity_bindings=("work", "attempt"),
    ),
    ContractRequirement(
        "lane_c.safe_boundary_matrix",
        "lane_c",
        "resource safe-boundary and quiescence matrix",
        "Resource quiescence rules are not established.",
        "Lane C must publish safe/unsafe pause conditions for model, thread, process, client, durability, and partial-batch work.",
        None,
        qualification_authority=S1_QUALIFICATION_AUTHORITY,
    ),
    ContractRequirement(
        "lane_c.work_graph",
        "lane_c",
        "WorkGraph lineage fixture",
        "The durable work graph is not established.",
        "Lane C must publish explicit work items, parent/child edges, fan-out groups, join dependencies, and outcome references.",
        None,
        qualification_authority=S1_QUALIFICATION_AUTHORITY,
        required_identity_bindings=("work", "parent_work", "owner"),
        requires_lineage_evidence=True,
    ),
    ContractRequirement(
        "lane_c.ownership_generation",
        "lane_c",
        "ownership generation and transfer fixture",
        "Single-owner generation rules are not established.",
        "Lane C must publish transfer, expected generation, current owner, and stale-owner rejection evidence.",
        None,
        qualification_authority=S1_QUALIFICATION_AUTHORITY,
        required_identity_bindings=("work", "owner", "owner_generation"),
        requires_lineage_evidence=True,
    ),
    ContractRequirement(
        "lane_c.operation_semantics",
        "lane_c",
        "handoff/delegate/fan-out/spawn/fork/steer operation fixture",
        "Multi-agent operation distinctions are not established.",
        "Lane C must publish distinct operation, cancellation, detachment, budget, capability, and join semantics.",
        None,
        qualification_authority=S1_QUALIFICATION_AUTHORITY,
        requires_lineage_evidence=True,
    ),
    ContractRequirement(
        "lane_c.late_stale_result_behavior",
        "lane_c",
        "late result and stale owner rejection fixture",
        "Late/stale result behavior is not established.",
        "Lane C must publish generation-checked rejection, uncertainty, and no-head-mutation evidence.",
        None,
        qualification_authority=S1_QUALIFICATION_AUTHORITY,
        required_identity_bindings=(
            "work",
            "attempt",
            "owner_generation",
            "head_generation",
        ),
        requires_lineage_evidence=True,
    ),
)

CONTRACT_REQUIREMENTS = tuple(
    _bind_g2_requirement(item) for item in _CONTRACT_REQUIREMENTS
)

PLANNED_MEASUREMENTS = [
    "current_v1_bytes",
    "naive_repeated_json_bytes",
    "digest_references_uncompressed_bytes",
    "optional_gzip_bytes",
    "optional_zstd_bytes",
    "write_time",
    "read_time",
    "replay_time",
    "query_render_time",
    "artifact_dedup_ratio",
]
PLANNED_VIEWS = ["raw_private", "redacted_public"]

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

Diagnostic = Dict[str, str]


@dataclass
class ManifestRecord:
    logical_path: str
    directory: Path
    data: Optional[Dict[str, Any]]
    diagnostics: List[Diagnostic]


def _diag(
    category: str, code: str, subject: str, field: Optional[str] = None
) -> Diagnostic:
    result = {"category": category, "code": code, "subject": subject}
    if field:
        result["field"] = field
    return result


def _diag_key(item: Mapping[str, str]) -> Tuple[str, str, str, str]:
    return (
        item.get("category", ""),
        item.get("code", ""),
        item.get("subject", ""),
        item.get("field", ""),
    )


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.fullmatch(value))


def portability_finding_codes(value: str) -> List[str]:
    """Return typed findings without returning the inspected value."""
    codes = set()
    category_codes = {
        "absolute_posix_path": "absolute_posix_path",
        "windows_path": "windows_drive_path",
        "windows_unc_path": "windows_unc_path",
        "file_uri": "file_uri",
        "home_path": "home_expansion_path",
        "local_endpoint": "host_endpoint",
    }
    for category in _diagnostic_string_categories(value):
        code = category_codes.get(category)
        if code:
            codes.add(code)
    normalized = value.replace("\\", "/")
    if normalized.startswith("../") or "/../" in normalized:
        codes.add("repository_external_path")
    return sorted(codes)


def _strings(value: Any, field: str = "$") -> Iterable[Tuple[str, str]]:
    if isinstance(value, str):
        yield field, value
    elif isinstance(value, Mapping):
        for index, key in enumerate(sorted(value, key=lambda item: str(item))):
            # Never place an inspected mapping key into a public finding path.
            yield from _strings(value[key], f"{field}.mapping[{index}]")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _strings(item, f"{field}[{index}]")


def portability_diagnostics(value: Any, subject: str) -> List[Diagnostic]:
    findings = []
    for field, text in _strings(value):
        findings.extend(
            _diag("portability", code, subject, field)
            for code in portability_finding_codes(text)
        )
    return findings


def privacy_diagnostics(value: Any, subject: str) -> List[Diagnostic]:
    """Return typed privacy findings without echoing keys or scalar values."""

    findings: List[Diagnostic] = []

    def visit(item: Any, field: str) -> None:
        if isinstance(item, Mapping):
            for index, key in enumerate(sorted(item, key=lambda raw: str(raw))):
                child = f"{field}.mapping[{index}]"
                token = str(key)
                if _diagnostic_key_is_sensitive(token):
                    code = (
                        "raw_provider_payload"
                        if "provider" in token.lower() and "payload" in token.lower()
                        else "sensitive_key"
                    )
                    findings.append(_diag("privacy", code, subject, child))
                visit(item[key], child)
            return
        if isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, f"{field}[{index}]")
            return
        if (
            isinstance(item, str)
            and "secret" in _diagnostic_string_categories(item)
        ):
            findings.append(_diag("privacy", "secret_value", subject, field))

    visit(value, "$")
    return sorted(findings, key=_diag_key)


def _object(
    value: Any,
    required: set[str],
    optional: set[str],
    subject: str,
    field: str,
    diagnostics: List[Diagnostic],
) -> Optional[Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        diagnostics.append(_diag("manifest_schema", "object_required", subject, field))
        return None
    keys = {str(key) for key in value}
    diagnostics.extend(
        _diag("manifest_schema", "required_field_missing", subject, f"{field}.{key}")
        for key in sorted(required - keys)
    )
    diagnostics.extend(
        _diag("manifest_schema", "unexpected_field", subject, f"{field}.<unknown>")
        for _key in sorted(keys - required - optional)
    )
    return value


def _check_string(value: Any, subject: str, field: str, out: List[Diagnostic]) -> None:
    if not _nonempty(value):
        out.append(_diag("manifest_schema", "nonempty_string_required", subject, field))


def _check_bool(value: Any, subject: str, field: str, out: List[Diagnostic]) -> None:
    if not isinstance(value, bool):
        out.append(_diag("manifest_schema", "boolean_required", subject, field))


def _check_int(value: Any, subject: str, field: str, out: List[Diagnostic]) -> None:
    if not _nonnegative_int(value):
        out.append(
            _diag("manifest_schema", "nonnegative_integer_required", subject, field)
        )


def _check_sha(value: Any, subject: str, field: str, out: List[Diagnostic]) -> None:
    if not _sha256(value):
        out.append(_diag("manifest_schema", "invalid_sha256", subject, field))


def _validate_provenance(value: Any, subject: str, out: List[Diagnostic]) -> None:
    required = {
        "source_kind",
        "logical_source_id",
        "collection_owner",
        "independent_consumer",
        "model_call_performed_by_d1",
    }
    data = _object(value, required, set(), subject, "provenance", out)
    if data is None:
        return
    for key in required - {"model_call_performed_by_d1"}:
        _check_string(data.get(key), subject, f"provenance.{key}", out)
    _check_bool(
        data.get("model_call_performed_by_d1"),
        subject,
        "provenance.model_call_performed_by_d1",
        out,
    )


def _validate_license(value: Any, subject: str, out: List[Diagnostic]) -> None:
    data = _object(value, {"status", "requirement"}, set(), subject, "license", out)
    if data is None:
        return
    if data.get("status") not in SUPPORTED_LICENSE_STATUSES:
        out.append(
            _diag("manifest_schema", "unsupported_license_status", subject, "license.status")
        )
    _check_string(data.get("requirement"), subject, "license.requirement", out)


def _validate_source(
    value: Any, source_class: Any, subject: str, out: List[Diagnostic]
) -> None:
    if source_class == "campaign_long":
        required = {
            "schema_version",
            "manifest_sha256",
            "events_sha256",
            "steps_sha256",
            "event_records",
            "step_records",
            "total_source_bytes",
        }
        data = _object(value, required, set(), subject, "source_evidence", out)
        if data is None:
            return
        _check_string(data.get("schema_version"), subject, "source_evidence.schema_version", out)
        for key in ("manifest_sha256", "events_sha256", "steps_sha256"):
            _check_sha(data.get(key), subject, f"source_evidence.{key}", out)
        for key in ("event_records", "step_records", "total_source_bytes"):
            _check_int(data.get(key), subject, f"source_evidence.{key}", out)
        return
    if source_class == "unrelated_agent":
        required = {
            "generator",
            "generation_mode",
            "expected_steps",
            "network_required",
            "live_key_required",
        }
        data = _object(value, required, set(), subject, "source_evidence", out)
        if data is None:
            return
        for key in ("generator", "generation_mode"):
            _check_string(data.get(key), subject, f"source_evidence.{key}", out)
        _check_int(data.get("expected_steps"), subject, "source_evidence.expected_steps", out)
        for key in ("network_required", "live_key_required"):
            _check_bool(data.get(key), subject, f"source_evidence.{key}", out)
        return
    out.append(
        _diag(
            "manifest_schema",
            "unknown_required_semantic_shape",
            subject,
            "source_evidence",
        )
    )


def _validate_coverage(value: Any, subject: str, out: List[Diagnostic]) -> None:
    data = _object(
        value,
        REQUIRED_COVERAGE_KEYS,
        OPTIONAL_COVERAGE_KEYS,
        subject,
        "observed_coverage",
        out,
    )
    if data is None:
        return
    for key in sorted(data):
        item = data[key]
        if isinstance(item, bool):
            continue
        if isinstance(item, str) and item in UNKNOWN_COVERAGE_MARKERS:
            continue
        out.append(
            _diag(
                "manifest_schema",
                "unknown_required_semantic_shape",
                subject,
                f"observed_coverage.{key}",
            )
        )


def _validate_sanitization(
    value: Any, subject: str, out: List[Diagnostic]
) -> Optional[Mapping[str, Any]]:
    data = _object(
        value,
        {"status", "required_actions", "publication_gate"},
        {"raw_source_secret_key_names_detected", "publication_qualification"},
        subject,
        "sanitization",
        out,
    )
    if data is None:
        return None
    if data.get("status") not in SUPPORTED_SANITIZATION_STATUSES:
        out.append(
            _diag(
                "manifest_schema",
                "unsupported_sanitization_status",
                subject,
                "sanitization.status",
            )
        )
    actions = data.get("required_actions")
    if not isinstance(actions, list) or not actions or not all(_nonempty(x) for x in actions):
        out.append(
            _diag(
                "manifest_schema",
                "nonempty_string_list_required",
                subject,
                "sanitization.required_actions",
            )
        )
    _check_string(
        data.get("publication_gate"), subject, "sanitization.publication_gate", out
    )
    if "raw_source_secret_key_names_detected" in data:
        _check_bool(
            data.get("raw_source_secret_key_names_detected"),
            subject,
            "sanitization.raw_source_secret_key_names_detected",
            out,
        )
    return data


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _payload_set_digest(entries: Sequence[Tuple[str, str, int]]) -> str:
    digest = hashlib.sha256()
    for logical_path, sha, size in sorted(entries):
        digest.update(f"{logical_path}\0{sha}\0{size}\n".encode())
    return digest.hexdigest()


def _validate_publication(
    record: ManifestRecord, fixture_root: Path
) -> List[Diagnostic]:
    data = record.data or {}
    subject = record.logical_path
    out: List[Diagnostic] = []
    ready = data.get("status") == "sanitized_payload_ready"
    if not ready:
        out.append(
            _diag("publication", "publication_status_not_ready", subject, "status")
        )
    if ready and (
        not isinstance(data.get("license"), Mapping)
        or data["license"].get("status") != "qualified"
    ):
        out.append(
            _diag(
                "publication", "publication_license_not_qualified", subject, "license.status"
            )
        )
    sanitization = data.get("sanitization")
    if ready and (
        not isinstance(sanitization, Mapping)
        or sanitization.get("status") != "sanitized_payload_ready"
    ):
        out.append(
            _diag(
                "publication", "sanitization_status_not_ready", subject, "sanitization.status"
            )
        )
    qualification = (
        sanitization.get("publication_qualification")
        if isinstance(sanitization, Mapping)
        else None
    )
    if qualification is None and not ready:
        return out
    required = {
        "transform_receipt",
        "privacy_policy",
        "dropped_field_paths",
        "rewritten_field_paths",
        "scans",
        "loss_report",
        "payload_files",
    }
    qualification = _object(
        qualification,
        required,
        set(),
        subject,
        "sanitization.publication_qualification",
        out,
    )
    if qualification is None:
        out.append(
            _diag(
                "publication",
                "publication_qualification_missing",
                subject,
                "sanitization.publication_qualification",
            )
        )
        return out

    transform = _object(
        qualification.get("transform_receipt"),
        {"receipt_version", "receipt_id", "input_sha256", "output_sha256"},
        set(),
        subject,
        "sanitization.publication_qualification.transform_receipt",
        out,
    )
    output_sha: Any = None
    if transform is not None:
        if transform.get("receipt_version") != TRANSFORM_RECEIPT_VERSION:
            out.append(
                _diag(
                    "publication",
                    "unsupported_transform_receipt_version",
                    subject,
                    "sanitization.publication_qualification.transform_receipt.receipt_version",
                )
            )
        _check_string(
            transform.get("receipt_id"),
            subject,
            "sanitization.publication_qualification.transform_receipt.receipt_id",
            out,
        )
        for key in ("input_sha256", "output_sha256"):
            _check_sha(
                transform.get(key),
                subject,
                f"sanitization.publication_qualification.transform_receipt.{key}",
                out,
            )
        output_sha = transform.get("output_sha256")

    privacy = _object(
        qualification.get("privacy_policy"),
        {"policy_id", "version"},
        set(),
        subject,
        "sanitization.publication_qualification.privacy_policy",
        out,
    )
    if privacy is not None:
        for key in ("policy_id", "version"):
            _check_string(
                privacy.get(key),
                subject,
                f"sanitization.publication_qualification.privacy_policy.{key}",
                out,
            )

    for key in ("dropped_field_paths", "rewritten_field_paths"):
        paths = qualification.get(key)
        if not isinstance(paths, list) or not all(_nonempty(x) for x in paths):
            out.append(
                _diag(
                    "publication",
                    "field_path_list_required",
                    subject,
                    f"sanitization.publication_qualification.{key}",
                )
            )

    required_scans = {"secret_keys", "secret_values", "pii", "portability", "artifacts"}
    scans = _object(
        qualification.get("scans"),
        required_scans,
        set(),
        subject,
        "sanitization.publication_qualification.scans",
        out,
    )
    if scans is not None:
        for name in sorted(required_scans):
            field = f"sanitization.publication_qualification.scans.{name}"
            scan = _object(
                scans.get(name),
                {"qualified", "finding_count", "receipt_sha256"},
                set(),
                subject,
                field,
                out,
            )
            if scan is None:
                continue
            _check_bool(scan.get("qualified"), subject, f"{field}.qualified", out)
            _check_int(scan.get("finding_count"), subject, f"{field}.finding_count", out)
            _check_sha(scan.get("receipt_sha256"), subject, f"{field}.receipt_sha256", out)
            if scan.get("qualified") is not True or scan.get("finding_count") != 0:
                out.append(_diag("publication", "publication_scan_not_qualified", subject, field))

    loss = _object(
        qualification.get("loss_report"),
        {"report_version", "qualified", "report_sha256"},
        set(),
        subject,
        "sanitization.publication_qualification.loss_report",
        out,
    )
    if loss is not None:
        if loss.get("report_version") != LOSS_REPORT_VERSION:
            out.append(
                _diag(
                    "publication",
                    "unsupported_loss_report_version",
                    subject,
                    "sanitization.publication_qualification.loss_report.report_version",
                )
            )
        _check_bool(
            loss.get("qualified"),
            subject,
            "sanitization.publication_qualification.loss_report.qualified",
            out,
        )
        _check_sha(
            loss.get("report_sha256"),
            subject,
            "sanitization.publication_qualification.loss_report.report_sha256",
            out,
        )
        if loss.get("qualified") is not True:
            out.append(_diag("publication", "loss_report_not_qualified", subject))

    files = qualification.get("payload_files")
    payload_entries: List[Tuple[str, str, int]] = []
    if not isinstance(files, list) or not files:
        out.append(_diag("publication", "payload_file_inventory_required", subject))
    else:
        seen = set()
        for index, raw in enumerate(files):
            field = f"sanitization.publication_qualification.payload_files[{index}]"
            entry = _object(
                raw, {"logical_path", "sha256", "bytes"}, set(), subject, field, out
            )
            if entry is None:
                continue
            logical_path = entry.get("logical_path")
            declared_sha = entry.get("sha256")
            declared_size = entry.get("bytes")
            _check_string(logical_path, subject, f"{field}.logical_path", out)
            _check_sha(declared_sha, subject, f"{field}.sha256", out)
            _check_int(declared_size, subject, f"{field}.bytes", out)
            if not _nonempty(logical_path):
                continue
            if logical_path in seen:
                out.append(_diag("publication", "duplicate_payload_logical_path", subject, field))
                continue
            seen.add(logical_path)
            if portability_finding_codes(logical_path) or PurePosixPath(logical_path).is_absolute():
                out.append(_diag("portability", "payload_path_not_portable", subject, field))
                continue
            payload_path = (record.directory / str(logical_path)).resolve()
            try:
                payload_path.relative_to(record.directory.resolve())
                payload_path.relative_to(fixture_root.resolve())
            except ValueError:
                out.append(_diag("portability", "payload_path_outside_fixture", subject, field))
                continue
            if not payload_path.is_file():
                out.append(_diag("publication", "payload_file_missing", subject, field))
                continue
            actual_size = payload_path.stat().st_size
            actual_sha = _hash_file(payload_path)
            if declared_size != actual_size:
                out.append(_diag("publication", "payload_size_mismatch", subject, field))
            if declared_sha != actual_sha:
                out.append(_diag("publication", "payload_digest_mismatch", subject, field))
            if _sha256(declared_sha) and _nonnegative_int(declared_size):
                payload_entries.append((str(logical_path), str(declared_sha), int(declared_size)))
    if payload_entries and _sha256(output_sha):
        if output_sha != _payload_set_digest(payload_entries):
            out.append(_diag("publication", "transform_output_digest_mismatch", subject))
    return out


def _validate_manifest(record: ManifestRecord, fixture_root: Path) -> None:
    data = record.data
    out = record.diagnostics
    subject = record.logical_path
    if data is None:
        return
    required = {
        "manifest_version",
        "fixture_id",
        "source_class",
        "status",
        "payloads_committed",
        "provenance",
        "license",
        "source_evidence",
        "observed_coverage",
        "sanitization",
    }
    manifest = _object(data, required, set(), subject, "$", out)
    if manifest is None:
        return
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        out.append(
            _diag("manifest_schema", "unsupported_manifest_version", subject, "manifest_version")
        )
    _check_string(manifest.get("fixture_id"), subject, "fixture_id", out)
    source_class = manifest.get("source_class")
    if source_class not in SUPPORTED_SOURCE_CLASSES:
        out.append(_diag("manifest_schema", "unsupported_source_class", subject, "source_class"))
    status = manifest.get("status")
    if status not in SUPPORTED_STATUSES:
        out.append(_diag("manifest_schema", "unsupported_fixture_status", subject, "status"))
    _check_bool(manifest.get("payloads_committed"), subject, "payloads_committed", out)
    if isinstance(manifest.get("payloads_committed"), bool):
        if manifest["payloads_committed"] != (status == "sanitized_payload_ready"):
            out.append(_diag("manifest_schema", "payload_status_mismatch", subject, "payloads_committed"))
    _validate_provenance(manifest.get("provenance"), subject, out)
    _validate_license(manifest.get("license"), subject, out)
    _validate_source(manifest.get("source_evidence"), source_class, subject, out)
    _validate_coverage(manifest.get("observed_coverage"), subject, out)
    sanitization = _validate_sanitization(manifest.get("sanitization"), subject, out)
    if status == "sanitized_payload_ready" and isinstance(sanitization, Mapping):
        if sanitization.get("status") != "sanitized_payload_ready":
            out.append(_diag("manifest_schema", "payload_status_mismatch", subject, "sanitization.status"))
    out.extend(portability_diagnostics(manifest, subject))
    out.extend(_validate_publication(record, fixture_root))


def load_fixture_manifests(
    fixture_root: Path,
) -> Tuple[List[ManifestRecord], List[Diagnostic]]:
    records: List[ManifestRecord] = []
    root_findings: List[Diagnostic] = []
    if not fixture_root.is_dir():
        return records, [_diag("fixture_io", "fixture_root_not_found", "fixture-set")]
    paths = sorted(fixture_root.rglob(MANIFEST_NAME))
    if not paths:
        return records, [_diag("fixture_io", "no_fixture_manifests", "fixture-set")]
    for path in paths:
        logical_path = path.relative_to(fixture_root).as_posix()
        findings: List[Diagnostic] = []
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            findings.append(_diag("manifest_schema", "malformed_manifest_json", logical_path))
            records.append(ManifestRecord(logical_path, path.parent, None, findings))
            continue
        if not isinstance(raw, dict):
            findings.append(_diag("manifest_schema", "manifest_not_object", logical_path))
            records.append(ManifestRecord(logical_path, path.parent, None, findings))
            continue
        record = ManifestRecord(logical_path, path.parent, raw, findings)
        _validate_manifest(record, fixture_root)
        records.append(record)

    for field, code in (
        ("fixture_id", "duplicate_fixture_id"),
        ("logical_source_id", "duplicate_source_identity"),
    ):
        indexed: Dict[str, List[ManifestRecord]] = {}
        for record in records:
            if record.data is None:
                continue
            value = record.data.get("fixture_id")
            if field == "logical_source_id":
                provenance = record.data.get("provenance")
                value = provenance.get(field) if isinstance(provenance, Mapping) else None
            if _nonempty(value):
                indexed.setdefault(str(value), []).append(record)
        for duplicates in indexed.values():
            if len(duplicates) > 1:
                for record in duplicates:
                    record.diagnostics.append(
                        _diag("manifest_identity", code, record.logical_path, field)
                    )
    return records, root_findings


def _receipt_list(
    receipts: Optional[Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]]]
) -> List[Mapping[str, Any]]:
    if receipts is None:
        return []
    if isinstance(receipts, Mapping):
        result = []
        for contract_id in sorted(receipts):
            raw = receipts[contract_id]
            item = dict(raw) if isinstance(raw, Mapping) else {"value": raw}
            item.setdefault("contract_id", contract_id)
            result.append(item)
        return result
    return sorted(
        receipts,
        key=lambda item: (
            str(item.get("contract_id", "")) if isinstance(item, Mapping) else "",
            str(item.get("version", "")) if isinstance(item, Mapping) else "",
            str(item.get("fixture_path", ""))
            if isinstance(item, Mapping)
            else "",
        ),
    )


def _committed_file_bytes(
    repository_root: Path, commit: str, logical_path: str
) -> Optional[bytes]:
    result = subprocess.run(
        ["git", "-C", str(repository_root), "show", f"{commit}:{logical_path}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def _commit_exists(repository_root: Path, commit: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repository_root), "cat-file", "-e", f"{commit}^{{commit}}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _verify_receipt_file(
    *,
    repository_root: Path,
    commit: str,
    logical_path: Any,
    declared_sha: Any,
    expected_path: str,
    subject: str,
    path_field: str,
    digest_field: str,
) -> Tuple[Optional[bytes], List[Diagnostic]]:
    out: List[Diagnostic] = []
    if logical_path != expected_path:
        out.append(
            _diag("contract_receipt", "producer_path_mismatch", subject, path_field)
        )
        return None, out
    if not isinstance(logical_path, str) or (
        PurePosixPath(logical_path).is_absolute()
        or portability_finding_codes(logical_path)
    ):
        out.append(
            _diag("contract_receipt", "producer_path_not_portable", subject, path_field)
        )
        return None, out
    target = (repository_root / logical_path).resolve()
    try:
        target.relative_to(repository_root.resolve())
    except ValueError:
        out.append(
            _diag("contract_receipt", "producer_path_outside_repository", subject, path_field)
        )
        return None, out
    if not target.is_file():
        out.append(
            _diag("contract_receipt", "producer_file_missing", subject, path_field)
        )
        return None, out
    current = target.read_bytes()
    current_sha = hashlib.sha256(current).hexdigest()
    if declared_sha != current_sha:
        out.append(
            _diag("contract_receipt", "producer_digest_mismatch", subject, digest_field)
        )
    committed = _committed_file_bytes(repository_root, commit, logical_path)
    if committed is None:
        out.append(
            _diag("contract_receipt", "producer_file_not_at_commit", subject, path_field)
        )
        return None, out
    if committed != current:
        out.append(
            _diag("contract_receipt", "producer_worktree_bytes_mismatch", subject, path_field)
        )
    if hashlib.sha256(committed).hexdigest() != declared_sha:
        out.append(
            _diag(
                "contract_receipt",
                "producer_committed_digest_mismatch",
                subject,
                digest_field,
            )
        )
    return committed, out


def _validate_producer_evidence(
    payload: Optional[bytes],
    requirement: ContractRequirement,
    subject: str,
) -> List[Diagnostic]:
    if payload is None:
        return []
    try:
        evidence = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return [
            _diag("contract_receipt", "producer_evidence_malformed", subject)
        ]
    expected = {
        "contract_id": requirement.producer_contract_id,
        "contract_version": requirement.expected_version,
        "fixture_path": requirement.fixture_path,
        "qualification_authority": requirement.qualification_authority,
        "qualified": True,
    }
    if not isinstance(evidence, Mapping):
        return [_diag("contract_receipt", "producer_evidence_not_object", subject)]
    findings = [
        _diag(
            "contract_receipt",
            "producer_evidence_mismatch",
            subject,
            f"qualification_evidence.{field}",
        )
        for field, expected_value in expected.items()
        if evidence.get(field) != expected_value
    ]
    findings.extend(portability_diagnostics(evidence, subject))
    findings.extend(privacy_diagnostics(evidence, subject))

    if requirement.required_identity_bindings:
        bindings = evidence.get("identity_bindings")
        if not isinstance(bindings, Mapping) or not bindings:
            findings.append(
                _diag("contract_receipt", "conflicting_identities", subject)
            )
        else:
            missing = set(requirement.required_identity_bindings) - set(bindings)
            values = [str(value).strip() for value in bindings.values()]
            if (
                missing
                or any(not value for value in values)
                or len(values) != len(set(values))
            ):
                findings.append(
                    _diag("contract_receipt", "conflicting_identities", subject)
                )

    if requirement.requires_lineage_evidence:
        lineage = evidence.get("lineage_evidence")
        if not isinstance(lineage, Mapping):
            findings.append(_diag("contract_receipt", "missing_lineage", subject))
        elif (
            lineage.get("status") != "explicit"
            or lineage.get("edge_source") != "producer_fact"
        ):
            findings.append(_diag("contract_receipt", "missing_lineage", subject))
        elif lineage.get("inferred") is not False:
            findings.append(_diag("contract_receipt", "inferred_edge", subject))

    return findings


def validate_contract_receipts(
    receipts: Optional[Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]]],
    *,
    repository_root: Optional[Path] = None,
) -> Tuple[List[str], List[Diagnostic]]:
    repo_root = (
        Path(__file__).resolve().parents[1]
        if repository_root is None
        else repository_root.resolve()
    )
    normalized = _receipt_list(receipts)
    requirements = {item.contract_id: item for item in CONTRACT_REQUIREMENTS}
    out: List[Diagnostic] = []
    by_id: Dict[str, List[Tuple[Mapping[str, Any], bool]]] = {}
    required = {
        "contract_id",
        "producer_contract_id",
        "version",
        "producer_source_commit",
        "fixture_path",
        "fixture_sha256",
        "qualification_evidence_path",
        "qualification_evidence_sha256",
        "qualification_authority",
    }
    for index, receipt in enumerate(normalized):
        subject = f"contract-receipt[{index}]"
        if not isinstance(receipt, Mapping):
            out.append(_diag("contract_receipt", "receipt_not_object", subject))
            continue
        valid = True
        keys = {str(key) for key in receipt}
        for field in sorted(required - keys):
            out.append(_diag("contract_receipt", "receipt_required_field_missing", subject, field))
            valid = False
        for field in sorted(keys - required):
            out.append(
                _diag(
                    "contract_receipt",
                    "receipt_unexpected_field",
                    subject,
                    "<unknown>",
                )
            )
            valid = False
        for field in (
            "contract_id",
            "producer_contract_id",
            "version",
            "producer_source_commit",
            "fixture_path",
            "qualification_evidence_path",
            "qualification_authority",
        ):
            if not _nonempty(receipt.get(field)):
                out.append(_diag("contract_receipt", "receipt_nonempty_string_required", subject, field))
                valid = False
        for field in ("fixture_sha256", "qualification_evidence_sha256"):
            if not _sha256(receipt.get(field)):
                out.append(
                    _diag("contract_receipt", "receipt_invalid_digest", subject, field)
                )
                valid = False
        if not isinstance(receipt.get("producer_source_commit"), str) or not (
            _COMMIT_RE.fullmatch(str(receipt.get("producer_source_commit")))
        ):
            out.append(
                _diag(
                    "contract_receipt",
                    "receipt_invalid_source_commit",
                    subject,
                    "producer_source_commit",
                )
            )
            valid = False
        portability = portability_diagnostics(receipt, subject)
        out.extend(portability)
        privacy = privacy_diagnostics(receipt, subject)
        out.extend(privacy)
        valid = valid and not portability and not privacy
        contract_id = receipt.get("contract_id")
        if _nonempty(contract_id):
            by_id.setdefault(str(contract_id), []).append((receipt, valid))
            if contract_id not in requirements:
                out.append(
                    _diag(
                        "contract_receipt",
                        "unknown_contract_receipt",
                        subject,
                    )
                )

    duplicate_ids = {key for key, values in by_id.items() if len(values) > 1}
    out.extend(
        _diag(
            "contract_receipt",
            "duplicate_contract_receipt",
            contract_id if contract_id in requirements else "contract-receipt",
        )
        for contract_id in sorted(duplicate_ids)
    )
    qualified = []
    for requirement in CONTRACT_REQUIREMENTS:
        values = by_id.get(requirement.contract_id, [])
        if not values:
            missing_code = (
                "producer_version_unestablished"
                if requirement.expected_version is None
                else (
                    "exact_fixture_unavailable"
                    if not requirement.producer_binding_complete
                    else "contract_receipt_missing"
                )
            )
            out.append(
                _diag("contract_receipt", missing_code, requirement.contract_id)
            )
            continue
        if requirement.contract_id in duplicate_ids:
            continue
        receipt, valid = values[0]
        if not valid:
            out.append(
                _diag("contract_receipt", "contract_receipt_invalid", requirement.contract_id)
            )
        elif requirement.expected_version is None:
            out.append(
                _diag(
                    "contract_receipt",
                    "producer_version_unestablished",
                    requirement.contract_id,
                )
            )
        elif receipt.get("version") != requirement.expected_version:
            out.append(
                _diag("contract_receipt", "contract_version_mismatch", requirement.contract_id)
            )
        elif receipt.get("producer_contract_id") != requirement.producer_contract_id:
            out.append(
                _diag("contract_receipt", "producer_contract_mismatch", requirement.contract_id)
            )
        else:
            receipt_findings: List[Diagnostic] = []
            commit = str(receipt.get("producer_source_commit"))
            if commit != requirement.producer_source_commit:
                receipt_findings.append(
                    _diag(
                        "contract_receipt",
                        "producer_source_commit_mismatch",
                        requirement.contract_id,
                    )
                )
            if receipt.get("qualification_authority") != (
                requirement.qualification_authority
            ):
                receipt_findings.append(
                    _diag(
                        "contract_receipt",
                        "qualification_authority_not_approved",
                        requirement.contract_id,
                    )
                )
            if receipt.get("fixture_sha256") != requirement.fixture_sha256:
                receipt_findings.append(
                    _diag(
                        "contract_receipt",
                        "producer_digest_mismatch",
                        requirement.contract_id,
                        "fixture_sha256",
                    )
                )
            if receipt.get("qualification_evidence_sha256") != (
                requirement.qualification_evidence_sha256
            ):
                receipt_findings.append(
                    _diag(
                        "contract_receipt",
                        "producer_digest_mismatch",
                        requirement.contract_id,
                        "qualification_evidence_sha256",
                    )
                )
            if not receipt_findings and not _commit_exists(repo_root, commit):
                receipt_findings.append(
                    _diag(
                        "contract_receipt",
                        "producer_source_commit_not_found",
                        requirement.contract_id,
                    )
                )
            if not receipt_findings:
                fixture_bytes, fixture_findings = _verify_receipt_file(
                    repository_root=repo_root,
                    commit=commit,
                    logical_path=receipt.get("fixture_path"),
                    declared_sha=receipt.get("fixture_sha256"),
                    expected_path=str(requirement.fixture_path),
                    subject=requirement.contract_id,
                    path_field="fixture_path",
                    digest_field="fixture_sha256",
                )
                evidence_bytes, evidence_findings = _verify_receipt_file(
                    repository_root=repo_root,
                    commit=commit,
                    logical_path=receipt.get("qualification_evidence_path"),
                    declared_sha=receipt.get("qualification_evidence_sha256"),
                    expected_path=str(requirement.qualification_evidence_path),
                    subject=requirement.contract_id,
                    path_field="qualification_evidence_path",
                    digest_field="qualification_evidence_sha256",
                )
                _ = fixture_bytes
                receipt_findings.extend(fixture_findings)
                receipt_findings.extend(evidence_findings)
                receipt_findings.extend(
                    _validate_producer_evidence(
                        evidence_bytes, requirement, requirement.contract_id
                    )
                )
            out.extend(receipt_findings)
            if not receipt_findings:
                qualified.append(requirement.contract_id)
    return sorted(qualified), sorted(out, key=_diag_key)


def _load_receipts(path: Optional[Path]) -> Tuple[List[Mapping[str, Any]], List[Diagnostic]]:
    if path is None:
        return [], []
    subject = "contract-receipt-set"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], [_diag("contract_receipt", "malformed_receipt_set", subject)]
    if not isinstance(raw, Mapping):
        return [], [_diag("contract_receipt", "receipt_set_not_object", subject)]
    stable_shape = {"receipt_type", "schema_version", "receipts"}
    compatibility_shape = {"receipt_version", "receipts"}
    if set(raw) == stable_shape:
        if raw.get("receipt_type") != RECEIPT_SET_TYPE:
            return [], [_diag("contract_receipt", "unsupported_receipt_set_type", subject)]
        if raw.get("schema_version") != RECEIPT_SET_SCHEMA_VERSION:
            return [], [_diag("contract_receipt", "unsupported_receipt_set_schema", subject)]
    elif set(raw) == compatibility_shape:
        if raw.get("receipt_version") != COMPAT_RECEIPT_SET_VERSION:
            return [], [_diag("contract_receipt", "unsupported_receipt_set_schema", subject)]
    else:
        return [], [_diag("contract_receipt", "receipt_set_shape_invalid", subject)]
    if not isinstance(raw.get("receipts"), list):
        return [], [_diag("contract_receipt", "receipt_list_required", subject)]
    return raw["receipts"], []


def _safe_fixture_set_id(value: str) -> Tuple[str, List[Diagnostic]]:
    out = portability_diagnostics(value, "fixture-set-id")
    if not _nonempty(value):
        out.append(_diag("fixture_io", "fixture_set_id_required", "fixture-set-id"))
    return (value, []) if not out else ("invalid-fixture-set", out)


_GLOBAL_BLOCKERS = (
    (
        "trajectory_schema_not_ready",
        "The canonical Trajectory record schema is not frozen.",
        "Accept A, C, then B producer contracts and qualify runtime behavior before schema review.",
        "reviewed A/B/C lineage fixtures and G2 behavior evidence",
    ),
    (
        "canonical_trajectory_writer_missing",
        "No authoritative Trajectory writer exists.",
        "Implement one writer only after the schema and migration gates are accepted.",
        "canonical writer parity evidence",
    ),
    (
        "trajectory_store_benchmark_missing",
        "No TrajectoryStore benchmark has run.",
        "Run the committed benchmark only after representative fixtures and a store exist.",
        "representative benchmark receipt",
    ),
    (
        "consumer_not_qualified",
        "Receipt presence does not prove runtime lineage behavior.",
        "Qualify pause/restore/fork, stale-owner, late-result, and work-graph behavior in runtime consumers.",
        "runtime behavior qualification evidence",
    ),
    (
        "publication_claim_unavailable",
        "Publication readiness is not established.",
        "Qualify license, sanitization, loss, portability, and public projection evidence.",
        "publication qualification receipt",
    ),
    (
        "compression_claim_unavailable",
        "No compression claim is supported.",
        "Measure representative fixtures after the canonical store exists.",
        "measured compression comparison",
    ),
    (
        "deduplication_claim_unavailable",
        "No deduplication claim is supported.",
        "Measure referenced and unique bytes with the committed benchmark protocol.",
        "measured deduplication report",
    ),
    (
        "performance_claim_unavailable",
        "No performance claim is supported.",
        "Measure write, read, replay, and query workloads on both representative sources.",
        "measured performance report",
    ),
    (
        "qita_migration_not_qualified",
        "qita migration is not qualified.",
        "Preserve trace compatibility until reader parity and lineage navigation pass.",
        "qita compatibility and navigation evidence",
    ),
)


def _qualification_state(code: str) -> str:
    if code in {
        "producer_version_unestablished",
        "exact_fixture_unavailable",
        "contract_receipt_missing",
    }:
        return "blocked"
    if code.endswith("_unavailable") or code.endswith("_missing"):
        return "blocked"
    if code in {"trajectory_schema_not_ready", "consumer_not_qualified"}:
        return "blocked"
    return "rejected"


def _enrich_blocker(
    item: Mapping[str, str],
    requirements: Mapping[str, ContractRequirement],
) -> Dict[str, str]:
    result = dict(item)
    requirement = requirements.get(str(item.get("subject", "")))
    if requirement is not None:
        result.update(
            {
                "owner": requirement.owner,
                "short_message": requirement.short_message,
                "remediation": requirement.remediation,
                "required_artifact": requirement.required_artifact,
            }
        )
    else:
        code = str(item.get("code", ""))
        global_item = next((entry for entry in _GLOBAL_BLOCKERS if entry[0] == code), None)
        if global_item is not None:
            result.update(
                {
                    "owner": "lane_d",
                    "short_message": global_item[1],
                    "remediation": global_item[2],
                    "required_artifact": global_item[3],
                }
            )
        elif item.get("category") in {"publication", "manifest_schema", "manifest_identity"}:
            result.update(
                {
                    "owner": "lane_d",
                    "short_message": "Representative fixture evidence is not qualified.",
                    "remediation": "Repair the named fixture evidence without exposing rejected values.",
                    "required_artifact": "portable fixture manifest and qualification evidence",
                }
            )
        else:
            result.update(
                {
                    "owner": "lane_d",
                    "short_message": "Readiness evidence was rejected.",
                    "remediation": "Correct the typed finding and rerun the readiness gate.",
                    "required_artifact": "valid portable readiness evidence",
                }
            )
    result["current_qualification_state"] = _qualification_state(
        str(item.get("code", ""))
    )
    return result


def build_readiness_result(
    fixture_root: Path,
    dry_run: bool,
    *,
    fixture_set_id: str = DEFAULT_FIXTURE_SET_ID,
    repository_root: Optional[Path] = None,
    contract_receipts: Optional[
        Sequence[Mapping[str, Any]] | Mapping[str, Mapping[str, Any]]
    ] = None,
    extra_diagnostics: Optional[Sequence[Diagnostic]] = None,
) -> Dict[str, Any]:
    """Return deterministic typed blockers without exposing local paths."""
    safe_id, id_findings = _safe_fixture_set_id(fixture_set_id)
    records, root_findings = load_fixture_manifests(fixture_root)
    qualified_contracts, contract_findings = validate_contract_receipts(
        contract_receipts,
        repository_root=repository_root,
    )
    blockers = list(id_findings) + list(root_findings) + list(contract_findings)
    for record in records:
        blockers.extend(record.diagnostics)
    blockers.extend(extra_diagnostics or [])
    blockers.extend(
        _diag("readiness_gate", code, "trajectory")
        for code, _message, _remediation, _artifact in _GLOBAL_BLOCKERS
    )
    blockers = sorted(blockers, key=_diag_key)
    requirements = {item.contract_id: item for item in CONTRACT_REQUIREMENTS}
    public_blockers = [_enrich_blocker(item, requirements) for item in blockers]
    counts: Dict[str, int] = {}
    for item in blockers:
        counts[item["category"]] = counts.get(item["category"], 0) + 1
    source_classes = sorted(
        {
            str(record.data.get("source_class"))
            for record in records
            if record.data and record.data.get("source_class") in SUPPORTED_SOURCE_CLASSES
        }
    )
    publication_qualified = 0
    for record in records:
        if not record.data or record.data.get("status") != "sanitized_payload_ready":
            continue
        blocking = {"manifest_schema", "manifest_identity", "publication", "portability"}
        if not any(item["category"] in blocking for item in record.diagnostics):
            publication_qualified += 1
    result = {
        "result_type": RESULT_TYPE,
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": "schema_not_ready",
        "reason_code": "TRAJECTORY_SCHEMA_NOT_READY",
        "dry_run": dry_run,
        "trajectory_schema_frozen": False,
        "canonical_writer_available": False,
        "store_benchmark_available": False,
        "qita_migration_qualified": False,
        "fixture_set_id": safe_id,
        "fixture_manifests_found": len(records),
        "source_classes": source_classes,
        "publication_qualified_count": publication_qualified,
        "manifest_diagnostics": [
            {
                "logical_path": record.logical_path,
                "valid": not record.diagnostics,
                "blocker_codes": sorted({item["code"] for item in record.diagnostics}),
            }
            for record in sorted(records, key=lambda item: item.logical_path)
        ],
        "required_contracts": [
            {
                "contract_id": item.contract_id,
                "owner": item.owner,
                "producer_commit": item.producer_source_commit,
                "fixture_path": item.fixture_path,
                "evidence_path": item.qualification_evidence_path,
                "schema_version": item.expected_version,
                "fixture_digest": item.fixture_sha256,
                "evidence_digest": item.qualification_evidence_sha256,
                "authority": item.qualification_authority,
                "compatibility_status": item.compatibility_status,
                "runtime_behavior_required": item.runtime_behavior_required,
                "required_artifact": item.required_artifact,
                "short_message": item.short_message,
                "remediation": item.remediation,
                "current_qualification_state": (
                    "qualified"
                    if item.contract_id in qualified_contracts
                    else (
                        "producer_version_unestablished"
                        if item.expected_version is None
                        else (
                            "exact_fixture_unavailable"
                            if not item.producer_binding_complete
                            else "receipt_missing_or_rejected"
                        )
                    )
                ),
            }
            for item in sorted(CONTRACT_REQUIREMENTS, key=lambda item: item.contract_id)
        ],
        "qualified_contract_ids": qualified_contracts,
        "blocker_categories": {key: counts[key] for key in sorted(counts)},
        "blockers": public_blockers,
        "planned_measurements": PLANNED_MEASUREMENTS,
        "planned_views": PLANNED_VIEWS,
        "measurements": [],
        "claims": [],
    }
    output_findings = portability_diagnostics(result, "readiness-output")
    output_findings.extend(privacy_diagnostics(result, "readiness-output"))
    if output_findings:
        enriched = [_enrich_blocker(item, requirements) for item in output_findings]
        result["blockers"] = sorted(
            public_blockers + enriched,
            key=lambda item: _diag_key(item),
        )
        for finding in output_findings:
            category = finding["category"]
            result["blocker_categories"][category] = (
                result["blocker_categories"].get(category, 0) + 1
            )
        result["blocker_categories"] = {
            key: result["blocker_categories"][key]
            for key in sorted(result["blocker_categories"])
        }
    return result


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report strict trajectory-store benchmark readiness."
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "trajectories",
        help="fixture root (defaults to the repository representative set)",
    )
    parser.add_argument("--fixture-set-id", default=DEFAULT_FIXTURE_SET_ID)
    parser.add_argument("--contract-receipts", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    receipts, receipt_findings = _load_receipts(args.contract_receipts)
    result = build_readiness_result(
        args.fixture,
        args.dry_run,
        fixture_set_id=args.fixture_set_id,
        contract_receipts=receipts,
        extra_diagnostics=receipt_findings,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if args.dry_run else 2


if __name__ == "__main__":
    raise SystemExit(main())
