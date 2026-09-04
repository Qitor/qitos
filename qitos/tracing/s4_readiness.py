"""Strict exact-source intake for S4 Lane A/B/C producer handoffs."""

from __future__ import annotations

import hashlib
import ast
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Mapping, Tuple

from qitos.core.session import AttemptIdentity, RunIdentity, SessionIdentity, WorkItemIdentity

from ._g5_requirements import QUALIFICATION_PINS, REPLAY_HEADS, REQUIREMENTS, SOURCE_HEADS


S4_READINESS_SCHEMA = "qitos.s4.lane_d.readiness/1"
S4_PRODUCER_AUTHORITY = "qitos.s4.g5.exact_source/1"

REQUIRED_LANE_REQUIREMENTS = {
    "A": (
        "public_composition",
        "session_default",
        "cli_programmatic_equivalence",
        "cleanup_ownership",
        "config_extension_slots",
    ),
    "B": (
        "provider_transaction",
        "message_ordering",
        "reasoning_continuation",
        "context_compaction_artifact",
        "usage_loss_failure",
    ),
    "C": (
        "tool_result_aci",
        "sandbox_attestation",
        "effect_lifecycle",
        "mcp",
        "work_graph_operations",
        "cleanup_unknown",
    ),
}


@dataclass(frozen=True)
class S4ReadinessResult:
    status: str
    qualified_lanes: Tuple[str, ...]
    finding_codes: Tuple[str, ...]
    schema_frozen: bool = False
    default_writer_enabled: bool = False
    default_reader_switched: bool = False
    publication_ready: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "qualified_lanes": list(self.qualified_lanes),
            "finding_codes": list(self.finding_codes),
            "schema_frozen": self.schema_frozen,
            "default_writer_enabled": self.default_writer_enabled,
            "default_reader_switched": self.default_reader_switched,
            "publication_ready": self.publication_ready,
        }


def _safe_path(value: Any) -> str | None:
    text = str(value or "")
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts:
        return None
    return path.as_posix()


def _git_bytes(root: Path, commit: str, path: str) -> bytes | None:
    try:
        completed = subprocess.run(
            ["git", "show", f"{commit}:{path}"],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout


def _validate_binding(
    lane: str,
    binding: Mapping[str, Any],
    *,
    repository_root: Path,
) -> Tuple[str, ...]:
    findings = []
    commit = str(binding.get("exact_commit", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        findings.append(f"lane_{lane.lower()}_commit_invalid")
    if binding.get("producer_authority") != S4_PRODUCER_AUTHORITY:
        findings.append(f"lane_{lane.lower()}_authority_invalid")
    if binding.get("source_wave") != "S4":
        findings.append(f"lane_{lane.lower()}_source_wave_rejected")
    if binding.get("source_commit") != SOURCE_HEADS[lane]:
        findings.append(f"lane_{lane.lower()}_source_identity_mismatch")
    if binding.get("replay_commit") != REPLAY_HEADS[lane]:
        findings.append(f"lane_{lane.lower()}_replay_identity_mismatch")
    requirements = binding.get("requirements")
    if not isinstance(requirements, list):
        return tuple(findings + [f"lane_{lane.lower()}_requirements_invalid"])
    by_id = {
        str(item.get("requirement_id")): item
        for item in requirements
        if isinstance(item, Mapping)
    }
    if set(by_id) != set(REQUIRED_LANE_REQUIREMENTS[lane]):
        findings.append(f"lane_{lane.lower()}_requirement_set_mismatch")
    if len(by_id) != len(requirements):
        findings.append(f"lane_{lane.lower()}_duplicate_or_invalid_requirement")
    for requirement_id in REQUIRED_LANE_REQUIREMENTS[lane]:
        item = by_id.get(requirement_id)
        if item is None:
            continue
        path = _safe_path(item.get("committed_path"))
        digest = str(item.get("sha256", ""))
        schema = str(item.get("schema", ""))
        writer = str(item.get("current_writer", ""))
        test_node = str(item.get("consumer_test_node", ""))
        prefix = f"lane_{lane.lower()}_{requirement_id}"
        expected_writer, expected_node = REQUIREMENTS[lane][requirement_id]
        expected_path = f"tests/fixtures/s4/g5/current-facts/{lane.lower()}-{requirement_id}.json"
        if path != expected_path:
            findings.append(f"{prefix}_producer_artifact_mismatch")
        if schema != "qitos.g5.runtime_fact/v1":
            findings.append(f"{prefix}_schema_invalid")
        if writer != expected_writer:
            findings.append(f"{prefix}_writer_invalid")
        elif not _writer_exists(repository_root, commit, writer):
            findings.append(f"{prefix}_writer_missing_from_current_code")
        if test_node != expected_node:
            findings.append(f"{prefix}_consumer_node_unapproved")
        pin = QUALIFICATION_PINS.get((lane, requirement_id))
        if pin is None:
            findings.append(f"{prefix}_integration_qualification_pending")
        if path is None:
            findings.append(f"{prefix}_path_invalid")
            continue
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            findings.append(f"{prefix}_digest_invalid")
        if not schema.strip():
            findings.append(f"{prefix}_schema_missing")
        if not writer.strip():
            findings.append(f"{prefix}_writer_missing")
        if item.get("producer_authority") != S4_PRODUCER_AUTHORITY:
            findings.append(f"{prefix}_authority_invalid")
        if item.get("no_identity_conflict") is not True:
            findings.append(f"{prefix}_identity_conflict")
        artifact_commit = str(item.get("artifact_commit", ""))
        if not re.fullmatch(r"[0-9a-f]{40}", artifact_commit):
            findings.append(f"{prefix}_artifact_commit_invalid")
        committed = _git_bytes(repository_root, artifact_commit, path)
        if committed is None:
            findings.append(f"{prefix}_committed_bytes_missing")
        elif hashlib.sha256(committed).hexdigest() != digest:
            findings.append(f"{prefix}_digest_mismatch")
        else:
            try:
                artifact = json.loads(committed)
                if not isinstance(artifact, dict):
                    raise ValueError("artifact is not an object")
            except (ValueError, UnicodeDecodeError):
                findings.append(f"{prefix}_artifact_invalid")
                artifact = {}
            if (artifact.get("schema") != schema or artifact.get("writer") != writer
                    or artifact.get("requirement_id") != requirement_id
                    or artifact.get("code_commit") != commit):
                findings.append(f"{prefix}_artifact_contract_mismatch")
            if pin is not None:
                findings.extend(_validate_execution_pin(
                    repository_root, pin, artifact, commit, artifact_commit, digest, expected_node, prefix,
                ))
        test_path = _safe_path(test_node.partition("::")[0])
        test_bytes = _git_bytes(repository_root, commit, test_path) if test_path else None
        if test_bytes is None:
            findings.append(f"{prefix}_consumer_test_missing")
        else:
            try:
                node = test_node.split("::")
                symbols = {n.name for n in ast.parse(test_bytes).body if isinstance(n, ast.FunctionDef)}
                if len(node) != 2 or node[1] not in symbols:
                    findings.append(f"{prefix}_consumer_node_missing")
            except (SyntaxError, UnicodeDecodeError):
                findings.append(f"{prefix}_consumer_node_missing")
    return tuple(findings)


def _writer_exists(root: Path, commit: str, writer: str) -> bool:
    """Resolve only integration-approved source symbols; never import producer code."""
    parts = writer.split(".")
    module_path = "/".join(parts)
    for path in (module_path + ".py", module_path + "/__init__.py"):
        if _git_bytes(root, commit, path) is not None:
            return True
    if len(parts) < 2:
        return False
    module_path = "/".join(parts[:-1])
    for path in (module_path + ".py", module_path + "/__init__.py"):
        source = _git_bytes(root, commit, path)
        if source is None:
            continue
        try:
            return any(isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                       and node.name == parts[-1] for node in ast.parse(source).body)
        except (SyntaxError, UnicodeDecodeError):
            return False
    return False


def _validate_execution_pin(root: Path, pin: Mapping[str, str], artifact: Mapping[str, Any],
                            commit: str, artifact_commit: str, digest: str, node: str, prefix: str) -> Tuple[str, ...]:
    """Validate an integration-pinned result; never execute manifest-supplied code."""
    if (pin.get("code_commit") != commit or pin.get("artifact_sha256") != digest
            or pin.get("artifact_commit") != artifact_commit):
        return (f"{prefix}_current_identity_mismatch",)
    path = pin.get("execution_path", "")
    if path != "tests/fixtures/s4/g5/controlled-execution.json":
        return (f"{prefix}_execution_path_invalid",)
    data = _git_bytes(root, pin.get("qualification_commit", ""), path)
    if data is None or hashlib.sha256(data).hexdigest() != pin.get("execution_sha256"):
        return (f"{prefix}_execution_digest_mismatch",)
    try:
        evidence = json.loads(data)
        result = evidence["nodes"][node]
        identity = artifact["identity"]
        consumer = evidence["consumers"][pin["consumer"]]
        SessionIdentity(identity["session_id"])
        RunIdentity(identity["run_id"])
        WorkItemIdentity(identity["work_item_id"])
        AttemptIdentity(identity["attempt_id"])
        valid = (
            evidence["schema"] == "qitos.g5.controlled_execution/v1"
            and evidence["code_commit"] == commit
            and result["collected"] is True and result["outcome"] == "passed"
            and result["skipped"] is False
            and consumer["outcome"] == "passed"
            and consumer["installed_distribution"] is True
            and consumer["identity"] == identity
            and consumer["code_commit"] == commit
            and consumer["wheel_sha256"] == pin["wheel_sha256"]
            and re.fullmatch(r"[0-9a-f]{64}", consumer["wheel_sha256"]) is not None
            and consumer["runtime_facts"] == artifact["runtime_facts"]
            and artifact["runtime_facts"]["session_id"] == identity["session_id"]
            and artifact["runtime_facts"]["run_id"] == identity["run_id"]
            and artifact["runtime_facts"]["work_item_id"] == identity["work_item_id"]
            and artifact["runtime_facts"]["attempt_id"] == identity["attempt_id"]
            and artifact["runtime_facts"]["owner_generation"] == identity["owner_generation"]
            and isinstance(identity["owner_generation"], int)
            and not isinstance(identity["owner_generation"], bool)
            and identity["owner_generation"] >= 0
            and bool(identity["session_id"]) and bool(identity["run_id"])
        )
    except (KeyError, TypeError, ValueError):
        valid = False
    return () if valid else (f"{prefix}_execution_or_identity_invalid",)


def qualify_s4_readiness(
    inventory: Mapping[str, Any], *, repository_root: Path
) -> S4ReadinessResult:
    """Validate exact S4 producer bindings; S3 fixtures never satisfy this gate."""
    findings = []
    qualified = []
    if inventory.get("schema_version") != S4_READINESS_SCHEMA:
        findings.append("readiness_schema_invalid")
    lanes = inventory.get("lanes")
    if not isinstance(lanes, Mapping):
        lanes = {}
        findings.append("lane_inventory_invalid")
    if set(lanes) - set(REQUIRED_LANE_REQUIREMENTS):
        findings.append("unknown_lane")
    for lane in REQUIRED_LANE_REQUIREMENTS:
        binding = lanes.get(lane)
        if not isinstance(binding, Mapping):
            findings.append(f"lane_{lane.lower()}_producer_missing")
            continue
        lane_findings = _validate_binding(
            lane, binding, repository_root=repository_root
        )
        findings.extend(lane_findings)
        if not lane_findings:
            qualified.append(lane)
    status = (
        "ready_for_g5_review"
        if not findings and set(qualified) == set(REQUIRED_LANE_REQUIREMENTS)
        else "waiting_on_a_b_c"
    )
    return S4ReadinessResult(
        status=status,
        qualified_lanes=tuple(sorted(qualified)),
        finding_codes=tuple(dict.fromkeys(findings)),
    )


def load_s4_readiness(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError("S4 readiness inventory must be an object")
    return value


__all__ = [
    "REQUIRED_LANE_REQUIREMENTS",
    "S4_PRODUCER_AUTHORITY",
    "S4_READINESS_SCHEMA",
    "S4ReadinessResult",
    "load_s4_readiness",
    "qualify_s4_readiness",
]
