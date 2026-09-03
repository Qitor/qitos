"""Strict exact-source intake for S4 Lane A/B/C producer handoffs."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Mapping, Tuple


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
        committed = _git_bytes(repository_root, commit, path)
        if committed is None:
            findings.append(f"{prefix}_committed_bytes_missing")
        elif hashlib.sha256(committed).hexdigest() != digest:
            findings.append(f"{prefix}_digest_mismatch")
        test_path = _safe_path(test_node.partition("::")[0])
        if not test_path or _git_bytes(repository_root, commit, test_path) is None:
            findings.append(f"{prefix}_consumer_test_missing")
    return tuple(findings)


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
        if set(qualified) == set(REQUIRED_LANE_REQUIREMENTS)
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
