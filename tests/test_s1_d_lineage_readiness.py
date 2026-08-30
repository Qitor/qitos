"""S1 Lane D strict lineage, receipt, and developer-readiness contracts."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "benchmark_trajectory_store.py"
TRAJECTORY_FIXTURES = ROOT / "tests" / "fixtures" / "trajectories"
READINESS_FIXTURES = ROOT / "tests" / "fixtures" / "readiness"
SCENARIOS = READINESS_FIXTURES / "scenarios.json"
SCENARIO_SCHEMA = READINESS_FIXTURES / "scenario.schema.json"
RECEIPT_SET = READINESS_FIXTURES / "contract-qualification-receipts.json"
RECEIPT_SET_SCHEMA = READINESS_FIXTURES / "receipt-set.schema.json"


def _load_script() -> Any:
    name = "benchmark_trajectory_store_s1"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _run(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _exact_contract(
    tmp_path: Path,
    module: Any,
    *,
    requires_identity: bool = False,
    requires_lineage: bool = False,
) -> tuple[Path, Any, dict[str, Any], dict[str, Any]]:
    repo = tmp_path / "producer"
    repo.mkdir()
    _run(repo, "init")
    _run(repo, "config", "user.email", "lane-d@example.invalid")
    _run(repo, "config", "user.name", "Lane D Test")

    fixture_path = "producer/fixture.json"
    evidence_path = "producer/evidence.json"
    fixture = {
        "schema_version": "producer.contract/1",
        "fact": "synthetic test-only committed bytes",
    }
    evidence: dict[str, Any] = {
        "contract_id": "producer.contract",
        "contract_version": "producer.contract/1",
        "fixture_path": fixture_path,
        "qualification_authority": module.S1_QUALIFICATION_AUTHORITY,
        "qualified": True,
    }
    if requires_identity:
        evidence["identity_bindings"] = {
            "session": "session_id",
            "run": "run_id",
            "work": "work_item_id",
            "owner_generation": "owner_generation",
        }
    if requires_lineage:
        evidence["lineage_evidence"] = {
            "status": "explicit",
            "edge_source": "producer_fact",
            "inferred": False,
        }
    _write_json(repo / fixture_path, fixture)
    _write_json(repo / evidence_path, evidence)
    _run(repo, "add", fixture_path, evidence_path)
    _run(repo, "commit", "-m", "test: publish synthetic producer evidence")
    commit = _run(repo, "rev-parse", "HEAD")
    fixture_digest = hashlib.sha256((repo / fixture_path).read_bytes()).hexdigest()
    evidence_digest = hashlib.sha256((repo / evidence_path).read_bytes()).hexdigest()
    requirement = module.ContractRequirement(
        contract_id="lane_a.synthetic_contract",
        owner="lane_a",
        required_artifact="synthetic fixture and evidence",
        short_message="Synthetic producer evidence is required.",
        remediation="Publish exact committed evidence.",
        expected_version="producer.contract/1",
        producer_contract_id="producer.contract",
        producer_source_commit=commit,
        fixture_path=fixture_path,
        fixture_sha256=fixture_digest,
        qualification_evidence_path=evidence_path,
        qualification_evidence_sha256=evidence_digest,
        qualification_authority=module.S1_QUALIFICATION_AUTHORITY,
        required_identity_bindings=(
            ("session", "run", "work", "owner_generation")
            if requires_identity
            else ()
        ),
        requires_lineage_evidence=requires_lineage,
    )
    receipt = {
        "contract_id": requirement.contract_id,
        "producer_contract_id": requirement.producer_contract_id,
        "version": requirement.expected_version,
        "producer_source_commit": commit,
        "fixture_path": fixture_path,
        "fixture_sha256": fixture_digest,
        "qualification_evidence_path": evidence_path,
        "qualification_evidence_sha256": evidence_digest,
        "qualification_authority": module.S1_QUALIFICATION_AUTHORITY,
    }
    return repo, requirement, receipt, evidence


def _codes(findings: list[dict[str, str]]) -> set[str]:
    return {item["code"] for item in findings}


def test_readiness_scenario_fixture_schema_and_required_matrix() -> None:
    schema = json.loads(SCENARIO_SCHEMA.read_text(encoding="utf-8"))
    payload = json.loads(SCENARIOS.read_text(encoding="utf-8"))

    Draft202012Validator(schema).validate(payload)
    ids = {item["id"] for item in payload["scenarios"]}
    assert ids == {
        "all_producers_missing",
        "only_a_available",
        "a_c_available",
        "exact_a_c_b_available",
        "stale_a",
        "wrong_b_digest",
        "conflicting_ownership",
        "missing_lineage",
        "late_result_without_generation",
        "inferred_parent_edge_rejected",
        "unknown_schema",
        "exact_receipt_clears_one_blocker",
        "all_receipts_runtime_absent",
        "trajectory_still_not_ready",
    }
    assert all(item["trajectory_ready"] is False for item in payload["scenarios"])


def test_stable_receipt_set_matches_its_independent_schema() -> None:
    schema = json.loads(RECEIPT_SET_SCHEMA.read_text(encoding="utf-8"))
    payload = json.loads(RECEIPT_SET.read_text(encoding="utf-8"))

    Draft202012Validator(schema).validate(payload)
    assert payload["receipt_type"] == "trajectory_contract_qualification_receipts"
    assert payload["schema_version"] == "1"
    assert len(payload["receipts"]) == 2


@pytest.mark.parametrize(
    ("wrapper", "expected"),
    [
        (
            {
                "receipt_type": "trajectory_contract_qualification_receipts",
                "schema_version": "999",
                "receipts": [],
            },
            "unsupported_receipt_set_schema",
        ),
        (
            {
                "receipt_version": "trajectory-contract-qualification-receipts-v1",
                "receipts": [],
            },
            None,
        ),
        ({"schema_version": "1", "receipts": []}, "receipt_set_shape_invalid"),
    ],
)
def test_receipt_set_wrapper_is_versioned_and_compatibility_is_bounded(
    tmp_path: Path,
    wrapper: dict[str, Any],
    expected: str | None,
) -> None:
    module = _load_script()
    path = tmp_path / "receipt-set.json"
    _write_json(path, wrapper)

    receipts, findings = module._load_receipts(path)

    assert receipts == []
    assert ([item["code"] for item in findings] or [None]) == [expected]


def test_s1_inventory_is_complete_unestablished_and_owner_specific() -> None:
    module = _load_script()
    result = module.build_readiness_result(TRAJECTORY_FIXTURES, dry_run=True)
    contracts = {item["contract_id"]: item for item in result["required_contracts"]}

    expected = {
        "lane_a.identity_vocabulary",
        "lane_a.session_lifecycle",
        "lane_a.session_snapshot",
        "lane_a.session_head_generation",
        "lane_a.resolver_reference",
        "lane_b.request_view",
        "lane_b.provider_codec",
        "lane_b.codec_report",
        "lane_b.steering",
        "lane_b.provider_continuation",
        "lane_b.context_artifact_snapshot",
        "lane_c.effect_recovery",
        "lane_c.safe_boundary_matrix",
        "lane_c.work_graph",
        "lane_c.ownership_generation",
        "lane_c.operation_semantics",
        "lane_c.late_stale_result_behavior",
    }
    assert expected <= set(contracts)
    for contract_id in expected:
        item = contracts[contract_id]
        assert item["owner"] == contract_id.split(".", 1)[0]
        assert item["producer_commit"] is None
        assert item["schema_version"] is None
        assert item["fixture_digest"] is None
        assert item["evidence_digest"] is None
        assert item["current_qualification_state"] == (
            "producer_version_unestablished"
        )


def test_exact_receipt_qualifies_only_its_owned_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    repo, requirement, receipt, _ = _exact_contract(tmp_path, module)
    second = replace(
        requirement,
        contract_id="lane_b.synthetic_contract",
        owner="lane_b",
    )
    monkeypatch.setattr(module, "CONTRACT_REQUIREMENTS", (requirement, second))

    qualified, findings = module.validate_contract_receipts(
        [receipt], repository_root=repo
    )

    assert qualified == [requirement.contract_id]
    assert any(
        item["code"] == "contract_receipt_missing"
        and item["subject"] == second.contract_id
        for item in findings
    )


def test_exact_receipt_and_committed_bytes_qualify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    repo, requirement, receipt, _ = _exact_contract(
        tmp_path, module, requires_identity=True, requires_lineage=True
    )
    monkeypatch.setattr(module, "CONTRACT_REQUIREMENTS", (requirement,))

    qualified, findings = module.validate_contract_receipts(
        [receipt], repository_root=repo
    )

    assert qualified == [requirement.contract_id]
    assert findings == []


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("stale", "producer_source_commit_mismatch"),
        ("wrong_commit", "producer_source_commit_mismatch"),
        ("wrong_path", "producer_path_mismatch"),
        ("wrong_digest", "producer_digest_mismatch"),
        ("invalid_authority", "qualification_authority_not_approved"),
        ("unsupported_schema", "contract_version_mismatch"),
    ],
)
def test_receipt_identity_failures_are_typed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected: str,
) -> None:
    module = _load_script()
    repo, requirement, receipt, _ = _exact_contract(tmp_path, module)
    monkeypatch.setattr(module, "CONTRACT_REQUIREMENTS", (requirement,))
    if mutation in {"stale", "wrong_commit"}:
        receipt["producer_source_commit"] = "0" * 40
    elif mutation == "wrong_path":
        receipt["fixture_path"] = "producer/other.json"
    elif mutation == "wrong_digest":
        receipt["fixture_sha256"] = "0" * 64
    elif mutation == "invalid_authority":
        receipt["qualification_authority"] = "qitos.s1.lane_a.self/v1"
    elif mutation == "unsupported_schema":
        receipt["version"] = "producer.contract/999"

    qualified, findings = module.validate_contract_receipts(
        [receipt], repository_root=repo
    )

    assert qualified == []
    assert expected in _codes(findings)


def test_source_commit_must_contain_fixture_and_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    repo, requirement, receipt, _ = _exact_contract(tmp_path, module)
    _run(repo, "checkout", "--orphan", "empty-history")
    for path in sorted(repo.glob("producer/*.json")):
        path.unlink()
    placeholder = repo / "README"
    placeholder.write_text("empty producer commit\n", encoding="utf-8")
    _run(repo, "add", "-A")
    _run(repo, "commit", "-m", "test: commit without evidence")
    absent_commit = _run(repo, "rev-parse", "HEAD")
    _write_json(repo / str(requirement.fixture_path), {"current": True})
    _write_json(repo / str(requirement.qualification_evidence_path), {"current": True})
    requirement = replace(requirement, producer_source_commit=absent_commit)
    receipt["producer_source_commit"] = absent_commit
    monkeypatch.setattr(module, "CONTRACT_REQUIREMENTS", (requirement,))

    qualified, findings = module.validate_contract_receipts(
        [receipt], repository_root=repo
    )

    assert qualified == []
    assert "producer_file_not_at_commit" in _codes(findings)


def test_worktree_bytes_must_equal_committed_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    repo, requirement, receipt, _ = _exact_contract(tmp_path, module)
    monkeypatch.setattr(module, "CONTRACT_REQUIREMENTS", (requirement,))
    _write_json(repo / str(requirement.fixture_path), {"changed": True})

    qualified, findings = module.validate_contract_receipts(
        [receipt], repository_root=repo
    )

    assert qualified == []
    assert {"producer_digest_mismatch", "producer_worktree_bytes_mismatch"} <= (
        _codes(findings)
    )


def test_unestablished_schema_cannot_be_caller_qualified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    repo, requirement, receipt, _ = _exact_contract(tmp_path, module)
    requirement = replace(
        requirement,
        expected_version=None,
        producer_contract_id=None,
        producer_source_commit=None,
        fixture_path=None,
        fixture_sha256=None,
        qualification_evidence_path=None,
        qualification_evidence_sha256=None,
    )
    monkeypatch.setattr(module, "CONTRACT_REQUIREMENTS", (requirement,))

    qualified, findings = module.validate_contract_receipts(
        [receipt], repository_root=repo
    )

    assert qualified == []
    assert "producer_version_unestablished" in _codes(findings)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("conflicting", "conflicting_identities"),
        ("missing_lineage", "missing_lineage"),
        ("inferred", "inferred_edge"),
    ],
)
def test_identity_and_lineage_evidence_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected: str,
) -> None:
    module = _load_script()
    repo, requirement, receipt, evidence = _exact_contract(
        tmp_path, module, requires_identity=True, requires_lineage=True
    )
    if mutation == "conflicting":
        evidence["identity_bindings"]["run"] = "session_id"
    elif mutation == "missing_lineage":
        evidence.pop("lineage_evidence")
    elif mutation == "inferred":
        evidence["lineage_evidence"]["inferred"] = True
    _write_json(repo / str(requirement.qualification_evidence_path), evidence)
    _run(repo, "add", str(requirement.qualification_evidence_path))
    _run(repo, "commit", "-m", f"test: {mutation} evidence")
    commit = _run(repo, "rev-parse", "HEAD")
    digest = hashlib.sha256(
        (repo / str(requirement.qualification_evidence_path)).read_bytes()
    ).hexdigest()
    requirement = replace(
        requirement,
        producer_source_commit=commit,
        qualification_evidence_sha256=digest,
    )
    receipt.update(
        producer_source_commit=commit,
        qualification_evidence_sha256=digest,
    )
    monkeypatch.setattr(module, "CONTRACT_REQUIREMENTS", (requirement,))

    qualified, findings = module.validate_contract_receipts(
        [receipt], repository_root=repo
    )

    assert qualified == []
    assert expected in _codes(findings)


def test_late_result_without_owner_generation_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    repo, requirement, receipt, evidence = _exact_contract(
        tmp_path, module, requires_identity=True, requires_lineage=True
    )
    requirement = replace(
        requirement,
        required_identity_bindings=("work", "owner_generation"),
    )
    evidence["identity_bindings"].pop("owner_generation")
    _write_json(repo / str(requirement.qualification_evidence_path), evidence)
    _run(repo, "add", str(requirement.qualification_evidence_path))
    _run(repo, "commit", "-m", "test: late result without generation")
    commit = _run(repo, "rev-parse", "HEAD")
    digest = hashlib.sha256(
        (repo / str(requirement.qualification_evidence_path)).read_bytes()
    ).hexdigest()
    requirement = replace(
        requirement,
        producer_source_commit=commit,
        qualification_evidence_sha256=digest,
    )
    receipt.update(
        producer_source_commit=commit,
        qualification_evidence_sha256=digest,
    )
    monkeypatch.setattr(module, "CONTRACT_REQUIREMENTS", (requirement,))

    qualified, findings = module.validate_contract_receipts(
        [receipt], repository_root=repo
    )

    assert qualified == []
    assert "conflicting_identities" in _codes(findings)


def test_all_exact_receipts_still_do_not_claim_runtime_or_trajectory_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_script()
    repo, requirement, receipt, _ = _exact_contract(tmp_path, module)
    monkeypatch.setattr(module, "CONTRACT_REQUIREMENTS", (requirement,))

    result = module.build_readiness_result(
        TRAJECTORY_FIXTURES,
        dry_run=True,
        repository_root=repo,
        contract_receipts=[receipt],
    )
    codes = {item["code"] for item in result["blockers"]}

    assert result["qualified_contract_ids"] == [requirement.contract_id]
    assert result["status"] == "schema_not_ready"
    assert result["trajectory_schema_frozen"] is False
    assert result["canonical_writer_available"] is False
    assert result["store_benchmark_available"] is False
    assert result["qita_migration_qualified"] is False
    assert result["measurements"] == []
    assert result["claims"] == []
    assert {
        "consumer_not_qualified",
        "trajectory_schema_not_ready",
        "canonical_trajectory_writer_missing",
    } <= codes


def test_privacy_and_portability_findings_never_echo_rejected_values() -> None:
    module = _load_script()
    secret = "Bearer value-that-must-never-be-echoed"
    host_path = "/Users/example/private/session.json"
    receipt = {
        "contract_id": "lane_x.unknown",
        "authorization": secret,
        "fixture_path": host_path,
    }

    _, findings = module.validate_contract_receipts([receipt])
    rendered = json.dumps(findings, sort_keys=True)

    assert {"sensitive_key", "secret_value", "absolute_posix_path"} <= _codes(findings)
    assert secret not in rendered
    assert host_path not in rendered
    assert "authorization" not in rendered


def test_new_readiness_artifacts_are_portable() -> None:
    module = _load_script()
    checked = [
        READINESS_FIXTURES / "README.md",
        RECEIPT_SET,
        RECEIPT_SET_SCHEMA,
        SCENARIOS,
        SCENARIO_SCHEMA,
        ROOT / "docs" / "internal" / "plans" / "s1_d_lineage_readiness.md",
        ROOT / "docs" / "internal" / "plans" / "s1_d_lineage_evidence.md",
        ROOT / "docs" / "internal" / "plans" / "s1_d_source_census.md",
        ROOT / "docs" / "internal" / "plans" / "s1_d_trajectory_adr.md",
        ROOT
        / "docs"
        / "internal"
        / "plans"
        / "assets"
        / "s1_d_trajectory_architecture.drawio",
    ]
    for path in checked:
        text = path.read_text(encoding="utf-8")
        assert module.portability_finding_codes(text) == [], path
