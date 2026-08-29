"""Strict readiness tests for the schema-neutral trajectory benchmark gate."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "benchmark_trajectory_store.py"
FIXTURES = ROOT / "tests" / "fixtures" / "trajectories"
SOURCE_MANIFEST = FIXTURES / "unrelated-agent" / "fixture-manifest.json"
MANIFEST_SCHEMA = FIXTURES / "fixture-manifest.schema.json"


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
    result = {
        "contract_id": "lane_b.exchange_log_fixture_version",
        "version": "qitos.exchange_log.v1",
        "digest": "a" * 64,
        "fixture_identity": "lane-b-exchange-log-fixture-v1",
        "qualified": True,
    }
    result.update(updates)
    return result


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
        *sorted(FIXTURES.glob("*/fixture-manifest.json")),
    ]
    for path in checked:
        assert module.portability_finding_codes(path.read_text(encoding="utf-8")) == [], path


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


def test_contract_receipt_missing_unqualified_and_mismatch_are_distinct() -> None:
    module = _load_script()
    _, missing = module.validate_contract_receipts(None)
    _, unqualified = module.validate_contract_receipts([_receipt(qualified=False)])
    _, mismatch = module.validate_contract_receipts(
        [_receipt(version="qitos.exchange_log.v0")]
    )

    assert "contract_receipt_missing" in {item["code"] for item in missing}
    assert "contract_receipt_unqualified" in {item["code"] for item in unqualified}
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
    known = _receipt(qualified=False)
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


def test_cli_exit_policy_is_stable(capsys: pytest.CaptureFixture[str]) -> None:
    module = _load_script()

    assert module.main(["--dry-run"]) == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["status"] == "schema_not_ready"
    assert module.main([]) == 2
    default = json.loads(capsys.readouterr().out)
    assert default["status"] == "schema_not_ready"
