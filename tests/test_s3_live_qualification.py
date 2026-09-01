from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "qualify_s3_live.py"
SUMMARY = (
    ROOT
    / "docs"
    / "internal"
    / "plans"
    / "s3_g4_live_qualification_summary.json"
)


def _module():
    spec = importlib.util.spec_from_file_location("qualify_s3_live", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_matrix_is_the_only_profile_configuration_source() -> None:
    module = _module()
    profiles = module.load_profiles()

    assert [item.profile_id for item in profiles] == [
        "sii-dsv4-flash",
        "sii-glm-5-2",
        "sii-qwen3-8-27b",
    ]
    assert {item.credential_env for item in profiles} == {
        "QITOS_LIVE_DSV4_API_KEY",
        "QITOS_LIVE_GLM52_API_KEY",
        "QITOS_LIVE_QWEN38_API_KEY",
    }
    assert all(item.endpoint.startswith("https://") for item in profiles)
    assert all(item.base_url.endswith("/v1") for item in profiles)


def test_missing_credentials_are_typed_blocked_before_requests(
    monkeypatch,
) -> None:
    module = _module()
    profiles = module.load_profiles()
    for profile in profiles:
        monkeypatch.delenv(profile.credential_env, raising=False)

    result = module.qualify(
        profiles,
        live=True,
        source_commit="7b89dbcca97be5dfd9562276578353900af4e02d",
        private_dir=None,
        attestation_path=None,
        generated_at="2026-09-01T00:00:00+00:00",
    )

    assert result["decision"] == {
        "s3_status": "blocked_live_qualification",
        "g4_live": "configuration_blocked",
        "s4_ready": False,
        "feature_baseline_promoted": False,
        "default_branch_ready": False,
    }
    assert result["totals"]["requests"] == 0
    assert result["totals"]["configuration_blocked"] == 3
    assert all(item["stop_reason"] == "credential_missing" for item in result["profiles"])
    assert result["sandbox"]["pre_model_attestation"] == "not_started"
    assert result["sandbox"]["model_requests_before_attestation"] == 0
    assert result["privacy"]["scan_passed"] is True


def test_live_flag_is_mandatory_and_credentials_are_not_read(
    monkeypatch,
) -> None:
    module = _module()
    profile = module.load_profiles()[0]
    monkeypatch.setenv(profile.credential_env, "sentinel-secret-that-must-not-appear")

    result = module.qualify(
        [profile],
        live=False,
        source_commit="7b89dbcca97be5dfd9562276578353900af4e02d",
        private_dir=None,
        attestation_path=None,
        generated_at="2026-09-01T00:00:00+00:00",
    )
    rendered = json.dumps(result, sort_keys=True)

    assert result["profiles"][0]["stop_reason"] == "live_flag_required"
    assert result["profiles"][0]["credential_reference_status"] == "not_read"
    assert result["totals"]["requests"] == 0
    assert "sentinel-secret-that-must-not-appear" not in rendered


def test_private_evidence_must_be_outside_repository(tmp_path: Path) -> None:
    module = _module()
    inside = ROOT / "private-live-evidence"
    try:
        module._validate_private_dir(inside)
    except module.QualificationConfigurationError as exc:
        assert "outside the repository" in str(exc)
    else:  # pragma: no cover - safety boundary
        raise AssertionError("repository-local private evidence was accepted")

    outside = module._validate_private_dir(tmp_path / "private")
    assert outside.is_dir()


def test_native_calls_never_parse_assistant_text() -> None:
    module = _module()
    response = {
        "choices": [
            {
                "message": {
                    "content": '{"tool_calls":[{"function":{"name":"fake"}}]}',
                    "tool_calls": None,
                }
            }
        ]
    }

    assert module._native_calls(response) == []


def test_privacy_scan_rejects_values_paths_endpoints_and_auth_markers() -> None:
    module = _module()
    endpoint = module.load_profiles()[0].endpoint
    report = module._privacy_report(
        {"value": f"Bearer top-secret {endpoint} /Users/private/file"},
        ["top-secret"],
    )

    assert report["scan_passed"] is False
    assert report["credential_values_absent"] is False
    assert report["raw_endpoints_absent"] is False
    assert report["host_paths_absent"] is False


def test_committed_blocked_summary_binds_current_runner_and_matrix() -> None:
    module = _module()
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))

    assert summary["schema_version"] == module.SCHEMA_VERSION
    assert summary["runner_digest"] == hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    assert summary["matrix_digest"] == hashlib.sha256(
        module.MATRIX_PATH.read_bytes()
    ).hexdigest()
    assert summary["decision"]["g4_live"] == "configuration_blocked"
    assert summary["totals"] == {
        "configuration_blocked": 3,
        "input_tokens": 0,
        "latency_ms": 0,
        "output_tokens": 0,
        "profiles": 3,
        "reported_tokens": 0,
        "requests": 0,
        "retries": 0,
        "tool_capable_profiles": 0,
    }
    assert summary["privacy"]["scan_passed"] is True
