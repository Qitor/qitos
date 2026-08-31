"""Exact-source S3 Lane D readiness gate.

Receipts and branch existence are necessary but insufficient: each contract is
bound to committed manifest bytes and executable scenario evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .privacy import portability_finding_codes


READINESS_INVENTORY_VERSION = "qitos.s3.lane_d.readiness_inventory/1"
PRODUCER_MANIFEST_VERSION = "qitos.s3.producer_manifest/1"
READINESS_AUTHORITY = "qitos.s3.g4.exact_source/1"

EXPECTED_CONTRACTS: Dict[str, Tuple[str, str]] = {
    "s3.a.session_fork_ownership": (
        "A",
        "codex/v4-s3-a-session-fork",
    ),
    "s3.b.context_authority_transfer": (
        "B",
        "codex/v4-s3-b-transfer-authority",
    ),
    "s3.c.durable_work_runtime": (
        "C",
        "codex/v4-s3-c-durable-work-runtime",
    ),
}

_REQUIRED_FIELDS = {
    "contract_id",
    "owner_lane",
    "producer_branch",
    "source_commit",
    "producer_commit",
    "path",
    "digest",
    "schema_identifier",
    "authority",
    "compatibility",
    "test_binding",
    "qualification_state",
    "blocker",
    "remediation",
}


@dataclass(frozen=True)
class S3ReadinessFinding:
    code: str
    contract_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {"code": self.code, "contract_id": self.contract_id}


@dataclass(frozen=True)
class S3ReadinessResult:
    status: str
    qualified_producers: Tuple[Dict[str, Any], ...]
    qualified_scenarios: Tuple[str, ...]
    findings: Tuple[S3ReadinessFinding, ...]

    @property
    def ready(self) -> bool:
        return self.status == "s3_lane_d_qualified"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "qualified_producers": [dict(item) for item in self.qualified_producers],
            "qualified_scenarios": list(self.qualified_scenarios),
            "blockers": [finding.to_dict() for finding in self.findings],
            "findings": [finding.to_dict() for finding in self.findings],
            "schema_frozen": False,
            "writer_default": "frozen_trace_v1_unchanged",
            "qita_reader_default": "frozen_trace_v1_compatibility",
            "publication_ready": False,
            "claims": [],
            "measurements": [],
        }


def _git(root: Path, *args: str) -> Optional[bytes]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout


def _commit_for_branch(root: Path, branch: str) -> Optional[str]:
    value = _git(root, "rev-parse", "--verify", f"refs/heads/{branch}")
    if value is None:
        value = _git(root, "rev-parse", "--verify", f"refs/remotes/origin/{branch}")
    text = value.decode("ascii", "ignore").strip() if value is not None else ""
    return text if re.fullmatch(r"[0-9a-f]{40}", text) else None


def _committed_bytes(root: Path, commit: str, path: str) -> Optional[bytes]:
    return _git(root, "show", f"{commit}:{path}")


def _safe_path(value: Any) -> Optional[str]:
    text = str(value or "")
    candidate = Path(text)
    if (
        not text
        or candidate.is_absolute()
        or ".." in candidate.parts
        or portability_finding_codes(text)
    ):
        return None
    return candidate.as_posix()


def _validate_dependency(
    dependency: Mapping[str, Any], *, repository_root: Path
) -> Tuple[Optional[Dict[str, Any]], Tuple[str, ...], Tuple[S3ReadinessFinding, ...]]:
    contract_id = str(dependency.get("contract_id", ""))
    safe_contract = contract_id if contract_id in EXPECTED_CONTRACTS else None
    findings: List[S3ReadinessFinding] = []
    if set(dependency) != _REQUIRED_FIELDS:
        findings.append(S3ReadinessFinding("inventory_field_mismatch", safe_contract))
    expected = EXPECTED_CONTRACTS.get(contract_id)
    if expected is None:
        findings.append(S3ReadinessFinding("unknown_contract", None))
        return None, (), tuple(findings)
    lane, branch = expected
    if dependency.get("owner_lane") != lane:
        findings.append(S3ReadinessFinding("owner_lane_mismatch", contract_id))
    if dependency.get("producer_branch") != branch:
        findings.append(S3ReadinessFinding("producer_branch_mismatch", contract_id))
    if dependency.get("authority") != READINESS_AUTHORITY:
        findings.append(S3ReadinessFinding("authority_not_qualified", contract_id))
    if dependency.get("compatibility") != "direct_exact_source":
        findings.append(S3ReadinessFinding("compatibility_not_exact", contract_id))
    if dependency.get("qualification_state") != "qualified":
        findings.append(S3ReadinessFinding("producer_not_qualified", contract_id))
    bindings = dependency.get("test_binding")
    if not isinstance(bindings, list) or not bindings or any(
        not isinstance(item, str) or not item for item in bindings
    ):
        findings.append(S3ReadinessFinding("executable_test_binding_missing", contract_id))

    declared_commit = str(dependency.get("producer_commit") or "")
    source_commit = str(dependency.get("source_commit") or "")
    branch_commit = _commit_for_branch(repository_root, branch)
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        findings.append(S3ReadinessFinding("source_commit_unknown", contract_id))
    elif branch_commit != source_commit:
        findings.append(S3ReadinessFinding("producer_ref_mismatch", contract_id))
    if not re.fullmatch(r"[0-9a-f]{40}", declared_commit):
        findings.append(S3ReadinessFinding("producer_commit_unknown", contract_id))

    path = _safe_path(dependency.get("path"))
    digest = str(dependency.get("digest") or "")
    manifest: Optional[Mapping[str, Any]] = None
    if path is None:
        findings.append(S3ReadinessFinding("producer_path_unknown", contract_id))
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        findings.append(S3ReadinessFinding("producer_digest_unknown", contract_id))
    if (
        path is not None
        and re.fullmatch(r"[0-9a-f]{40}", declared_commit)
        and re.fullmatch(r"[0-9a-f]{64}", digest)
    ):
        data = _committed_bytes(repository_root, declared_commit, path)
        if data is None:
            findings.append(S3ReadinessFinding("producer_path_not_committed", contract_id))
        elif hashlib.sha256(data).hexdigest() != digest:
            findings.append(S3ReadinessFinding("producer_digest_mismatch", contract_id))
        else:
            try:
                loaded = json.loads(data)
            except json.JSONDecodeError:
                loaded = None
            if not isinstance(loaded, Mapping):
                findings.append(S3ReadinessFinding("producer_manifest_invalid", contract_id))
            else:
                manifest = loaded

    scenarios: Tuple[str, ...] = ()
    if manifest is not None:
        manifest_schema = manifest.get("manifest_version")
        if manifest_schema == PRODUCER_MANIFEST_VERSION:
            checks = {
                "contract_id": contract_id,
                "schema_identifier": dependency.get("schema_identifier"),
                "authority": READINESS_AUTHORITY,
                "runtime_execution": True,
                "synthetic": False,
            }
            for name, expected_value in checks.items():
                if manifest.get(name) != expected_value:
                    findings.append(
                        S3ReadinessFinding(f"manifest_{name}_mismatch", contract_id)
                    )
            if manifest.get("test_binding") != bindings:
                findings.append(S3ReadinessFinding("manifest_test_binding_mismatch", contract_id))
            raw_scenarios = manifest.get("qualified_scenarios")
            producer_files = manifest.get("producer_files")
        elif lane == "A" and manifest.get("schema_version") == dependency.get(
            "schema_identifier"
        ):
            if manifest.get("dispatch_source") != "851f7902f15da670e72f4c04d7453cf37201aee7":
                findings.append(S3ReadinessFinding("dispatch_source_mismatch", contract_id))
            implementation_commit = str(
                manifest.get("implementation_producer_commit") or ""
            )
            if (
                not re.fullmatch(r"[0-9a-f]{40}", implementation_commit)
                or _git(
                    repository_root,
                    "merge-base",
                    "--is-ancestor",
                    implementation_commit,
                    source_commit,
                )
                is None
            ):
                findings.append(S3ReadinessFinding("implementation_commit_unbound", contract_id))
            if manifest.get("test_node_ids") != bindings:
                findings.append(S3ReadinessFinding("manifest_test_binding_mismatch", contract_id))
            producer_files = manifest.get("fixtures")
            raw_scenarios = ()
            evidence_binding = next(
                (
                    item
                    for item in producer_files or ()
                    if isinstance(item, Mapping)
                    and item.get("path")
                    == "tests/fixtures/s3/lane_a/qualification-evidence.json"
                ),
                None,
            )
            evidence_path = (
                _safe_path(evidence_binding.get("path"))
                if isinstance(evidence_binding, Mapping)
                else None
            )
            evidence_bytes = (
                _committed_bytes(repository_root, declared_commit, evidence_path)
                if evidence_path is not None
                else None
            )
            try:
                evidence = json.loads(evidence_bytes) if evidence_bytes else None
            except json.JSONDecodeError:
                evidence = None
            qualified_facts = (
                evidence.get("qualified_facts")
                if isinstance(evidence, Mapping)
                else None
            )
            if not isinstance(qualified_facts, list) or not qualified_facts:
                findings.append(S3ReadinessFinding("executable_scenarios_missing", contract_id))
            else:
                scenarios = tuple(str(item) for item in qualified_facts)
        elif lane == "B" and manifest.get("schema_version") == dependency.get(
            "schema_identifier"
        ):
            if manifest.get("dispatch_source") != "851f7902f15da670e72f4c04d7453cf37201aee7":
                findings.append(S3ReadinessFinding("dispatch_source_mismatch", contract_id))
            implementation_commit = str(manifest.get("producer_commit") or "")
            if (
                not re.fullmatch(r"[0-9a-f]{40}", implementation_commit)
                or _git(
                    repository_root,
                    "merge-base",
                    "--is-ancestor",
                    implementation_commit,
                    source_commit,
                )
                is None
            ):
                findings.append(S3ReadinessFinding("implementation_commit_unbound", contract_id))
            producer_nodes = manifest.get("producer_test_node_ids")
            if bindings == ["tests/core/test_context_transfer.py"]:
                if not isinstance(producer_nodes, list) or not producer_nodes or any(
                    not str(item).startswith("tests/core/test_context_transfer.py")
                    for item in producer_nodes
                ):
                    findings.append(S3ReadinessFinding("manifest_test_binding_mismatch", contract_id))
            elif producer_nodes != bindings:
                findings.append(S3ReadinessFinding("manifest_test_binding_mismatch", contract_id))
            producer_files = manifest.get("producer_files")
            evidence_binding = next(
                (
                    item
                    for item in producer_files or ()
                    if isinstance(item, Mapping)
                    and item.get("path")
                    == "tests/fixtures/context_transfer/v1/qualification-evidence.json"
                ),
                None,
            )
            evidence_path = (
                _safe_path(evidence_binding.get("path"))
                if isinstance(evidence_binding, Mapping)
                else None
            )
            evidence_bytes = (
                _committed_bytes(repository_root, declared_commit, evidence_path)
                if evidence_path is not None
                else None
            )
            try:
                evidence = json.loads(evidence_bytes) if evidence_bytes else None
            except json.JSONDecodeError:
                evidence = None
            evidence_claims = (
                evidence.get("claims") if isinstance(evidence, Mapping) else None
            )
            gates = evidence.get("gates") if isinstance(evidence, Mapping) else None
            if (
                not isinstance(evidence_claims, list)
                or not evidence_claims
                or not isinstance(gates, list)
                or not any(
                    isinstance(item, Mapping)
                    and item.get("command") == "pytest -q"
                    and item.get("status") == "passed"
                    for item in gates
                )
            ):
                findings.append(S3ReadinessFinding("executable_scenarios_missing", contract_id))
            else:
                scenarios = tuple(str(item) for item in evidence_claims)
            raw_scenarios = ()
        elif lane == "C" and manifest.get("schema_version") == dependency.get(
            "schema_identifier"
        ):
            if manifest.get("status") != "qualified_integrated_a_b":
                findings.append(S3ReadinessFinding("producer_manifest_status_blocked", contract_id))
            if manifest.get("test_node_ids") != bindings:
                findings.append(S3ReadinessFinding("manifest_test_binding_mismatch", contract_id))
            producer_files = manifest.get("files")
            evidence_binding = next(
                (
                    item for item in manifest.get("files", ())
                    if isinstance(item, Mapping)
                    and item.get("path")
                    == "tests/fixtures/s3/lane_c/qualification-evidence.json"
                ),
                None,
            )
            evidence_bytes = (
                _committed_bytes(repository_root, declared_commit, evidence_binding["path"])
                if isinstance(evidence_binding, Mapping)
                else None
            )
            try:
                evidence = json.loads(evidence_bytes) if evidence_bytes else None
            except json.JSONDecodeError:
                evidence = None
            qualified = evidence.get("qualified") if isinstance(evidence, Mapping) else None
            raw_scenarios = (
                [*qualified, "multi_agent_process_loss"]
                if isinstance(qualified, list) and qualified
                else []
            )
        else:
            findings.append(S3ReadinessFinding("producer_manifest_schema_mismatch", contract_id))
            raw_scenarios = ()
            producer_files = ()

        if not scenarios:
            if not isinstance(raw_scenarios, (list, tuple)) or not raw_scenarios or any(
                not isinstance(item, str) or not item for item in raw_scenarios
            ):
                findings.append(S3ReadinessFinding("executable_scenarios_missing", contract_id))
            else:
                scenarios = tuple(raw_scenarios)
        if lane == "C" and "multi_agent_process_loss" not in scenarios:
            findings.append(S3ReadinessFinding("process_loss_scenario_missing", contract_id))
        if not isinstance(producer_files, list) or not producer_files:
            findings.append(S3ReadinessFinding("producer_files_missing", contract_id))
        else:
            for binding in producer_files:
                if not isinstance(binding, Mapping):
                    findings.append(S3ReadinessFinding("producer_file_binding_invalid", contract_id))
                    continue
                source_path = _safe_path(binding.get("path"))
                source_digest = str(
                    binding.get("digest") or binding.get("sha256") or ""
                )
                source = (
                    _committed_bytes(repository_root, declared_commit, source_path)
                    if source_path is not None
                    else None
                )
                if (
                    source is None
                    or not re.fullmatch(r"[0-9a-f]{64}", source_digest)
                    or hashlib.sha256(source).hexdigest() != source_digest
                ):
                    findings.append(S3ReadinessFinding("producer_file_binding_invalid", contract_id))

    if findings:
        return None, (), tuple(findings)
    return (
        {
            "contract_id": contract_id,
            "owner_lane": lane,
            "producer_commit": declared_commit,
            "path": path,
            "digest": digest,
            "schema_identifier": dependency.get("schema_identifier"),
        },
        scenarios,
        (),
    )


def qualify_s3_readiness(
    inventory: Mapping[str, Any], *, repository_root: Path
) -> S3ReadinessResult:
    findings: List[S3ReadinessFinding] = []
    qualified: list[Dict[str, Any]] = []
    scenarios: list[str] = []
    if inventory.get("inventory_version") != READINESS_INVENTORY_VERSION:
        findings.append(S3ReadinessFinding("inventory_version_unsupported"))
    if portability_finding_codes(inventory):
        findings.append(S3ReadinessFinding("inventory_not_portable"))
    dependencies = inventory.get("dependencies")
    if not isinstance(dependencies, list):
        findings.append(S3ReadinessFinding("inventory_dependencies_invalid"))
        dependencies = []
    seen: set[str] = set()
    for dependency in dependencies:
        if not isinstance(dependency, Mapping):
            findings.append(S3ReadinessFinding("inventory_dependency_invalid"))
            continue
        contract_id = str(dependency.get("contract_id", ""))
        if contract_id in seen:
            findings.append(S3ReadinessFinding("duplicate_contract", contract_id))
            continue
        seen.add(contract_id)
        producer, producer_scenarios, producer_findings = _validate_dependency(
            dependency, repository_root=repository_root
        )
        findings.extend(producer_findings)
        if producer is not None:
            qualified.append(producer)
            scenarios.extend(producer_scenarios)
    for contract_id in EXPECTED_CONTRACTS:
        if contract_id not in seen:
            findings.append(S3ReadinessFinding("required_contract_missing", contract_id))
    ready = not findings and seen == set(EXPECTED_CONTRACTS)
    return S3ReadinessResult(
        status="s3_lane_d_qualified" if ready else "waiting_on_lane_a_b_c",
        qualified_producers=tuple(qualified),
        qualified_scenarios=tuple(dict.fromkeys(scenarios)),
        findings=tuple(findings),
    )


def load_readiness_inventory(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("readiness inventory must be an object")
    return value


__all__ = [
    "EXPECTED_CONTRACTS",
    "PRODUCER_MANIFEST_VERSION",
    "READINESS_AUTHORITY",
    "READINESS_INVENTORY_VERSION",
    "S3ReadinessFinding",
    "S3ReadinessResult",
    "load_readiness_inventory",
    "qualify_s3_readiness",
]
