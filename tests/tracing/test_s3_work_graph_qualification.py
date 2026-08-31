from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from qitos.tracing.work_graph_qualification import (
    EXPECTED_CONTRACTS,
    PRODUCER_MANIFEST_VERSION,
    READINESS_AUTHORITY,
    READINESS_INVENTORY_VERSION,
    load_readiness_inventory,
    qualify_s3_readiness,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INVENTORY = ROOT / "tests" / "fixtures" / "s3" / "lane_d" / "readiness-inventory.json"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _qualified_inventory(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "S3 Lane D Test")
    _git(repo, "config", "user.email", "s3-lane-d@example.invalid")
    _write(repo / "base.txt", "base\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")

    dependencies = []
    for contract_id, (lane, branch) in EXPECTED_CONTRACTS.items():
        _git(repo, "switch", "main")
        _git(repo, "switch", "-c", branch)
        source = repo / "producer" / lane.lower() / "contract.py"
        _write(source, f"CONTRACT_ID = {contract_id!r}\n")
        source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
        manifest_path = repo / "producer" / lane.lower() / "producer-manifest.json"
        scenarios = [f"lane_{lane.lower()}_executable"]
        if lane == "C":
            scenarios.append("multi_agent_process_loss")
        schema = f"qitos.s3.lane_{lane.lower()}/1"
        test_binding = [f"tests/lane_{lane.lower()}/test_producer.py::test_executable"]
        _write(manifest_path, {
            "manifest_version": PRODUCER_MANIFEST_VERSION,
            "contract_id": contract_id,
            "schema_identifier": schema,
            "authority": READINESS_AUTHORITY,
            "runtime_execution": True,
            "synthetic": False,
            "test_binding": test_binding,
            "qualified_scenarios": scenarios,
            "producer_files": [{
                "path": source.relative_to(repo).as_posix(),
                "digest": source_digest,
            }],
        })
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", f"producer {lane}")
        commit = _git(repo, "rev-parse", "HEAD")
        dependencies.append({
            "contract_id": contract_id,
            "owner_lane": lane,
            "producer_branch": branch,
            "source_commit": commit,
            "producer_commit": commit,
            "path": manifest_path.relative_to(repo).as_posix(),
            "digest": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "schema_identifier": schema,
            "authority": READINESS_AUTHORITY,
            "compatibility": "direct_exact_source",
            "test_binding": test_binding,
            "qualification_state": "qualified",
            "blocker": None,
            "remediation": None,
        })
    return repo, {
        "inventory_version": READINESS_INVENTORY_VERSION,
        "status": "candidate",
        "dependencies": dependencies,
    }


def test_default_inventory_qualifies_integrated_exact_sources_without_rollout_claims() -> None:
    result = qualify_s3_readiness(
        load_readiness_inventory(DEFAULT_INVENTORY), repository_root=ROOT
    )
    payload = result.to_dict()
    assert result.status == "s3_lane_d_qualified"
    assert result.ready is True
    assert {item["owner_lane"] for item in payload["qualified_producers"]} == {
        "A", "B", "C"
    }
    assert payload["schema_frozen"] is False
    assert payload["writer_default"] == "frozen_trace_v1_unchanged"
    assert payload["qita_reader_default"] == "frozen_trace_v1_compatibility"
    assert payload["publication_ready"] is False
    assert payload["claims"] == []
    assert payload["measurements"] == []
    assert payload["findings"] == []
    assert "multi_agent_process_loss" in payload["qualified_scenarios"]


def test_exact_committed_manifests_and_executable_scenarios_qualify(tmp_path: Path) -> None:
    repo, inventory = _qualified_inventory(tmp_path)
    result = qualify_s3_readiness(inventory, repository_root=repo)
    assert result.status == "s3_lane_d_qualified"
    assert result.ready is True
    assert {item["owner_lane"] for item in result.qualified_producers} == {"A", "B", "C"}
    assert "multi_agent_process_loss" in result.qualified_scenarios
    assert result.to_dict()["publication_ready"] is False


def test_receipt_presence_cannot_mask_digest_or_executable_fact_failure(tmp_path: Path) -> None:
    repo, inventory = _qualified_inventory(tmp_path)
    broken = copy.deepcopy(inventory)
    broken["dependencies"][0]["digest"] = "0" * 64
    broken["dependencies"][2]["test_binding"] = []
    result = qualify_s3_readiness(broken, repository_root=repo)
    codes = {finding.code for finding in result.findings}
    assert result.status == "waiting_on_lane_a_b_c"
    assert "producer_digest_mismatch" in codes
    assert "executable_test_binding_missing" in codes
    assert result.to_dict()["claims"] == []
