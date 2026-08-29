"""Strict readiness tests for the schema-neutral trajectory benchmark gate."""

from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "benchmark_trajectory_store.py"
FIXTURES = ROOT / "tests" / "fixtures" / "trajectories"
SOURCE_MANIFEST = FIXTURES / "unrelated-agent" / "fixture-manifest.json"
MANIFEST_SCHEMA = FIXTURES / "fixture-manifest.schema.json"
VERIFIED_RECEIPTS_PATH = FIXTURES / "contract-qualification-receipts.json"


def _load_script() -> Any:
    name = "benchmark_trajectory_store"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _manifest() -> dict[str, Any]:
    return json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))


def _write_manifest(root: Path, name: str, manifest: Any) -> Path:
    target = root / name / "fixture-manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return target


def _codes(result: Mapping[str, Any]) -> set[str]:
    return {item["code"] for item in result["blockers"]}


def _receipt(**updates: Any) -> dict[str, Any]:
    receipt_set = json.loads(VERIFIED_RECEIPTS_PATH.read_text(encoding="utf-8"))
    result = copy.deepcopy(receipt_set["receipts"][0])
    result.update(updates)
    return result


def _verified_receipts() -> list[dict[str, Any]]:
    receipt_set = json.loads(VERIFIED_RECEIPTS_PATH.read_text(encoding="utf-8"))
    return receipt_set["receipts"]


def _verified_receipt(contract_id: str) -> dict[str, Any]:
    return copy.deepcopy(
        next(
            receipt
            for receipt in _verified_receipts()
            if receipt["contract_id"] == contract_id
        )
    )


def test_repository_fixture_set_is_strictly_blocked_and_portable() -> None:
    module = _load_script()

    first = module.build_readiness_result(FIXTURES.resolve(), dry_run=True)
    second = module.build_readiness_result(FIXTURES.resolve(), dry_run=True)
    serialized = json.dumps(first, sort_keys=True)

    assert first == second
    assert first["status"] == "schema_not_ready"
    assert first["reason_code"] == "TRAJECTORY_SCHEMA_NOT_READY"
    assert first["trajectory_v2_schema_frozen"] is False
    assert first["fixture_set_id"] == "qitos-representative-trajectories-v1"
    assert first["source_classes"] == ["campaign_long", "unrelated_agent"]
    assert first["publication_qualified_count"] == 0
    assert first["measurements"] == []
    assert first["claims"] == []
    assert str(FIXTURES.resolve()) not in serialized
    assert "fixture_root" not in serialized
    assert "lane_b_c_contracts_not_versioned" not in serialized
    assert _codes(first) == {
        "contract_receipt_missing",
        "publication_status_not_ready",
        "trajectory_v2_schema_not_frozen",
    }


def test_documented_schema_and_checked_evidence_are_portable() -> None:
    module = _load_script()
    schema = json.loads(MANIFEST_SCHEMA.read_text(encoding="utf-8"))
    assert schema["properties"]["manifest_version"]["const"] == module.MANIFEST_VERSION
    assert set(schema["properties"]["source_class"]["enum"]) == module.SUPPORTED_SOURCE_CLASSES
    assert set(schema["properties"]["status"]["enum"]) == module.SUPPORTED_STATUSES

    checked = [
        ROOT / "docs" / "internal" / "plans" / "lane_d_data_convergence.md",
        ROOT / "docs" / "v4" / "05-trajectory-data-plane.md",
        ROOT / "docs" / "v4" / "10-consolidation-and-surface-reduction.md",
        FIXTURES / "README.md",
        MANIFEST_SCHEMA,
        VERIFIED_RECEIPTS_PATH,
        *sorted(FIXTURES.glob("*/fixture-manifest.json")),
    ]
    for path in checked:
        assert module.portability_finding_codes(path.read_text(encoding="utf-8")) == [], path


def test_manifest_json_schema_and_executable_validator_have_full_corpus_parity() -> None:
    module = _load_script()
    schema = json.loads(MANIFEST_SCHEMA.read_text(encoding="utf-8"))
    json_validator = Draft202012Validator(schema)
    unrelated = _manifest()
    campaign = json.loads(
        (FIXTURES / "campaign-long" / "fixture-manifest.json").read_text(
            encoding="utf-8"
        )
    )

    def mutated(base: dict[str, Any], mutation: Any) -> dict[str, Any]:
        value = copy.deepcopy(base)
        mutation(value)
        return value

    corpus: list[tuple[str, dict[str, Any], bool]] = [
        ("valid_unrelated", unrelated, True),
        ("valid_campaign", campaign, True),
        ("unknown_top_field", mutated(unrelated, lambda x: x.update(extra=True)), False),
        ("unknown_version", mutated(unrelated, lambda x: x.update(manifest_version="v999")), False),
        ("empty_fixture_id", mutated(unrelated, lambda x: x.update(fixture_id="")), False),
        ("unknown_source_class", mutated(unrelated, lambda x: x.update(source_class="other")), False),
        ("unknown_status", mutated(unrelated, lambda x: x.update(status="ready")), False),
        ("payload_flag_type", mutated(unrelated, lambda x: x.update(payloads_committed=1)), False),
        ("payload_status_mismatch", mutated(unrelated, lambda x: x.update(payloads_committed=True)), False),
        ("provenance_missing", mutated(unrelated, lambda x: x["provenance"].pop("source_kind")), False),
        ("provenance_extra", mutated(unrelated, lambda x: x["provenance"].update(extra=True)), False),
        ("provenance_empty", mutated(unrelated, lambda x: x["provenance"].update(logical_source_id="")), False),
        ("provenance_bool", mutated(unrelated, lambda x: x["provenance"].update(model_call_performed_by_d1=1)), False),
        ("license_status", mutated(unrelated, lambda x: x["license"].update(status="unknown")), False),
        ("license_empty", mutated(unrelated, lambda x: x["license"].update(requirement="")), False),
        ("generator_missing", mutated(unrelated, lambda x: x["source_evidence"].pop("generator")), False),
        ("generator_extra", mutated(unrelated, lambda x: x["source_evidence"].update(extra=True)), False),
        ("generator_negative_steps", mutated(unrelated, lambda x: x["source_evidence"].update(expected_steps=-1)), False),
        ("generator_bool_type", mutated(unrelated, lambda x: x["source_evidence"].update(network_required=1)), False),
        ("campaign_bad_digest", mutated(campaign, lambda x: x["source_evidence"].update(events_sha256="bad")), False),
        ("campaign_negative_count", mutated(campaign, lambda x: x["source_evidence"].update(event_records=-1)), False),
        ("coverage_missing", mutated(unrelated, lambda x: x["observed_coverage"].pop("retry")), False),
        ("coverage_extra", mutated(unrelated, lambda x: x["observed_coverage"].update(extra=True)), False),
        ("coverage_value", mutated(unrelated, lambda x: x["observed_coverage"].update(retry="maybe")), False),
        ("sanitization_status", mutated(unrelated, lambda x: x["sanitization"].update(status="unknown")), False),
        ("sanitization_actions", mutated(unrelated, lambda x: x["sanitization"].update(required_actions=[])), False),
        ("sanitization_gate", mutated(unrelated, lambda x: x["sanitization"].update(publication_gate="")), False),
        ("sanitization_optional_bool", mutated(unrelated, lambda x: x["sanitization"].update(raw_source_secret_key_names_detected=1)), False),
        ("qualification_shape", mutated(unrelated, lambda x: x["sanitization"].update(publication_qualification={})), False),
    ]

    for name, payload, expected in corpus:
        schema_accepts = json_validator.is_valid(payload)
        record = module.ManifestRecord(name, FIXTURES, copy.deepcopy(payload), [])
        module._validate_manifest(record, FIXTURES)
        executable_accepts = not any(
            finding["category"] == "manifest_schema"
            for finding in record.diagnostics
        )
        assert schema_accepts is expected, name
        assert executable_accepts is expected, name
        assert executable_accepts == schema_accepts, name


def test_missing_fixture_root_is_a_typed_blocker(tmp_path: Path) -> None:
    module = _load_script()

    result = module.build_readiness_result(tmp_path / "missing", dry_run=True)

    assert "fixture_root_not_found" in _codes(result)
    assert str(tmp_path) not in json.dumps(result)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("{", "malformed_manifest_json"), ([], "manifest_not_object")],
)
def test_malformed_and_nonobject_manifests_are_typed(
    tmp_path: Path, raw: Any, expected: str
) -> None:
    module = _load_script()
    target = tmp_path / "case" / "fixture-manifest.json"
    target.parent.mkdir(parents=True)
    target.write_text(raw if isinstance(raw, str) else json.dumps(raw), encoding="utf-8")

    result = module.build_readiness_result(tmp_path, dry_run=True)

    assert expected in _codes(result)


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda data: data.update(manifest_version="future"), "unsupported_manifest_version"),
        (
            lambda data: data["source_evidence"].update(generator_sha256="not-a-digest"),
            "unexpected_field",
        ),
        (
            lambda data: data["observed_coverage"].update(retry="maybe"),
            "unknown_required_semantic_shape",
        ),
        (lambda data: data.update(payloads_committed=True), "payload_status_mismatch"),
    ],
)
def test_manifest_schema_failures_are_typed(
    tmp_path: Path, mutator: Any, expected: str
) -> None:
    module = _load_script()
    data = _manifest()
    mutator(data)
    _write_manifest(tmp_path, "case", data)

    result = module.build_readiness_result(tmp_path, dry_run=True)

    assert expected in _codes(result)


def test_invalid_declared_digest_is_typed(tmp_path: Path) -> None:
    module = _load_script()
    data = json.loads(
        (FIXTURES / "campaign-long" / "fixture-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    data["source_evidence"]["events_sha256"] = "invalid"
    _write_manifest(tmp_path, "case", data)

    assert "invalid_sha256" in _codes(
        module.build_readiness_result(tmp_path, dry_run=True)
    )


def test_duplicate_fixture_and_source_identities_are_typed(tmp_path: Path) -> None:
    module = _load_script()
    data = _manifest()
    _write_manifest(tmp_path, "one", data)
    _write_manifest(tmp_path, "two", copy.deepcopy(data))

    codes = _codes(module.build_readiness_result(tmp_path, dry_run=True))

    assert "duplicate_fixture_id" in codes
    assert "duplicate_source_identity" in codes


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("/Users/example/private-run", "absolute_posix_path"),
        (r"C:\\Users\\example\\private-run", "windows_drive_path"),
        ("file:///Users/example/private-run", "file_uri"),
        ("~/private-run", "home_expansion_path"),
        ("../outside-repository", "repository_external_path"),
        ("http://127.0.0.1:9010/private-run", "host_endpoint"),
    ],
)
def test_host_specific_manifest_values_are_typed_without_echo(
    tmp_path: Path, value: str, expected: str
) -> None:
    module = _load_script()
    data = _manifest()
    data["provenance"]["logical_source_id"] = value
    _write_manifest(tmp_path, "case", data)

    result = module.build_readiness_result(tmp_path, dry_run=True)

    assert expected in _codes(result)
    assert value not in json.dumps(result)


def test_ready_status_requires_license_and_sanitization_receipts(tmp_path: Path) -> None:
    module = _load_script()
    data = _manifest()
    data["status"] = "sanitized_payload_ready"
    data["payloads_committed"] = True
    _write_manifest(tmp_path, "case", data)

    codes = _codes(module.build_readiness_result(tmp_path, dry_run=True))

    assert "publication_license_not_qualified" in codes
    assert "sanitization_status_not_ready" in codes
    assert "publication_qualification_missing" in codes


def test_complete_publication_receipt_qualifies_only_the_fixture(tmp_path: Path) -> None:
    module = _load_script()
    data = _manifest()
    fixture_dir = tmp_path / "case"
    payload = b'{"synthetic":true}\n'
    payload_path = fixture_dir / "payload.jsonl"
    payload_path.parent.mkdir(parents=True)
    payload_path.write_bytes(payload)
    payload_sha = hashlib.sha256(payload).hexdigest()
    output_sha = module._payload_set_digest(
        [("payload.jsonl", payload_sha, len(payload))]
    )
    data.update(status="sanitized_payload_ready", payloads_committed=True)
    data["license"]["status"] = "qualified"
    data["sanitization"].update(
        status="sanitized_payload_ready",
        publication_qualification={
            "transform_receipt": {
                "receipt_version": module.TRANSFORM_RECEIPT_VERSION,
                "receipt_id": "synthetic-transform-v1",
                "input_sha256": "b" * 64,
                "output_sha256": output_sha,
            },
            "privacy_policy": {"policy_id": "qitos-public-fixture", "version": "1"},
            "dropped_field_paths": [],
            "rewritten_field_paths": [],
            "scans": {
                name: {
                    "qualified": True,
                    "finding_count": 0,
                    "receipt_sha256": hashlib.sha256(name.encode()).hexdigest(),
                }
                for name in ("secret_keys", "secret_values", "pii", "portability", "artifacts")
            },
            "loss_report": {
                "report_version": module.LOSS_REPORT_VERSION,
                "qualified": True,
                "report_sha256": "c" * 64,
            },
            "payload_files": [
                {"logical_path": "payload.jsonl", "sha256": payload_sha, "bytes": len(payload)}
            ],
        },
    )
    _write_manifest(tmp_path, "case", data)

    result = module.build_readiness_result(tmp_path, dry_run=True)

    assert result["publication_qualified_count"] == 1
    assert "publication" not in result["blocker_categories"]
    assert result["status"] == "schema_not_ready"


def test_contract_receipt_missing_self_declaration_and_mismatch_are_distinct() -> None:
    module = _load_script()
    _, missing = module.validate_contract_receipts(None)
    _, self_declared = module.validate_contract_receipts(
        [_receipt(qualified=True)]
    )
    _, mismatch = module.validate_contract_receipts(
        [_receipt(version="qitos.exchange_log.v0")]
    )

    assert "contract_receipt_missing" in {item["code"] for item in missing}
    assert "receipt_unexpected_field" in {
        item["code"] for item in self_declared
    }
    assert "contract_version_mismatch" in {item["code"] for item in mismatch}


def test_unknown_and_duplicate_contract_receipts_are_distinct() -> None:
    module = _load_script()
    unknown = _receipt(contract_id="lane_x.unknown_contract")
    known = _receipt()

    _, unknown_findings = module.validate_contract_receipts([unknown])
    _, duplicate_findings = module.validate_contract_receipts([known, known])

    assert "unknown_contract_receipt" in {
        item["code"] for item in unknown_findings
    }
    assert "duplicate_contract_receipt" in {
        item["code"] for item in duplicate_findings
    }


def test_contract_receipt_diagnostics_are_input_order_independent() -> None:
    module = _load_script()
    known = _receipt(fixture_sha256="0" * 64)
    unknown = _receipt(contract_id="lane_x.unknown_contract")

    assert module.validate_contract_receipts([known, unknown]) == (
        module.validate_contract_receipts([unknown, known])
    )


def test_exact_qualified_receipt_does_not_auto_qualify_other_contracts() -> None:
    module = _load_script()

    qualified, findings = module.validate_contract_receipts([_receipt()])
    default_result = module.build_readiness_result(FIXTURES, dry_run=True)
    receipt_result = module.build_readiness_result(
        FIXTURES, dry_run=True, contract_receipts=[_receipt()]
    )

    assert qualified == ["lane_b.exchange_log_fixture_version"]
    missing_subjects = {
        item["subject"]
        for item in findings
        if item["code"] == "contract_receipt_missing"
    }
    assert "lane_b.request_view_report" in missing_subjects
    assert "lane_c.durability_receipt" in missing_subjects
    assert receipt_result["status"] == "schema_not_ready"
    assert receipt_result["blocker_categories"]["contract_receipt"] == (
        default_result["blocker_categories"]["contract_receipt"] - 1
    )


def test_exact_committed_b_and_c_receipts_clear_only_owned_contracts() -> None:
    module = _load_script()

    qualified, findings = module.validate_contract_receipts(_verified_receipts())
    result = module.build_readiness_result(
        FIXTURES,
        dry_run=True,
        contract_receipts=_verified_receipts(),
    )

    assert qualified == [
        "lane_b.exchange_log_fixture_version",
        "lane_c.canonical_tool_result_fixture_version",
    ]
    assert set(result["qualified_contract_ids"]) == set(qualified)
    assert all(
        item["subject"] not in qualified
        for item in findings
        if item["code"] == "contract_receipt_missing"
    )
    assert any(
        item["subject"] == "lane_b.request_view_report"
        for item in findings
        if item["code"] == "contract_receipt_missing"
    )
    assert result["status"] == "schema_not_ready"
    assert result["measurements"] == []
    assert result["claims"] == []
    assert result["publication_qualified_count"] == 0


def test_r3_lane_c_receipt_cannot_qualify_the_r4_scalar_safe_producer() -> None:
    module = _load_script()
    old_c = _verified_receipt("lane_c.canonical_tool_result_fixture_version")
    old_c.update(
        {
            "producer_source_commit": "d50f41fb3b8190a953f9f37f278bf0b197af286b",
            "fixture_sha256": (
                "a3eccdbf4d0c5da282c8118ea8308b901216415e4e26bd44bb9c2f3dde8e5775"
            ),
            "qualification_evidence_sha256": (
                "16ace4464b4c5325f63ed9a9092eef00701cc15f35d0f691a07f5043dc438a19"
            ),
        }
    )

    qualified, findings = module.validate_contract_receipts([old_c])

    assert "lane_c.canonical_tool_result_fixture_version" not in qualified
    assert "producer_source_commit_mismatch" in {
        item["code"] for item in findings
    }


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        ({"fixture_sha256": "0" * 64}, "producer_digest_mismatch"),
        (
            {"qualification_evidence_sha256": "0" * 64},
            "producer_digest_mismatch",
        ),
        ({"fixture_path": "tests/fixtures/trajectories/README.md"}, "producer_path_mismatch"),
        ({"producer_source_commit": "0" * 40}, "producer_source_commit_mismatch"),
        ({"version": "qitos.exchange_log.v999"}, "contract_version_mismatch"),
        (
            {"qualification_authority": "unreviewed.authority/v1"},
            "qualification_authority_not_approved",
        ),
        ({"producer_contract_id": "qitos.fake"}, "producer_contract_mismatch"),
    ],
)
def test_forged_receipt_fields_are_typed_and_cannot_qualify(
    updates: dict[str, Any], expected: str
) -> None:
    module = _load_script()

    qualified, findings = module.validate_contract_receipts([_receipt(**updates)])

    assert "lane_b.exchange_log_fixture_version" not in qualified
    assert expected in {item["code"] for item in findings}


def test_receipt_source_commit_must_resolve_to_a_real_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    missing_commit = "0" * 40
    requirements = tuple(
        replace(item, producer_source_commit=missing_commit)
        if item.contract_id == "lane_b.exchange_log_fixture_version"
        else item
        for item in module.CONTRACT_REQUIREMENTS
    )
    monkeypatch.setattr(module, "CONTRACT_REQUIREMENTS", requirements)

    qualified, findings = module.validate_contract_receipts(
        [_receipt(producer_source_commit=missing_commit)]
    )

    assert "lane_b.exchange_log_fixture_version" not in qualified
    assert "producer_source_commit_not_found" in {
        item["code"] for item in findings
    }


def test_cli_accepts_verified_receipt_set_without_changing_exit_policy(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_script()

    assert module.main(
        ["--dry-run", "--contract-receipts", str(VERIFIED_RECEIPTS_PATH)]
    ) == 0
    dry = json.loads(capsys.readouterr().out)
    assert set(dry["qualified_contract_ids"]) == {
        "lane_b.exchange_log_fixture_version",
        "lane_c.canonical_tool_result_fixture_version",
    }
    assert dry["status"] == "schema_not_ready"


def test_cli_exit_policy_is_stable(capsys: pytest.CaptureFixture[str]) -> None:
    module = _load_script()

    assert module.main(["--dry-run"]) == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["status"] == "schema_not_ready"
    assert module.main([]) == 2
    default = json.loads(capsys.readouterr().out)
    assert default["status"] == "schema_not_ready"
