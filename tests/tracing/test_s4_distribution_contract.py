from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any

import setuptools


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "s4" / "lane_d"


def _setup_metadata(monkeypatch: Any) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def capture(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(setuptools, "setup", capture)
    runpy.run_path(str(ROOT / "setup.py"), run_name="qitos_setup_metadata")
    return captured


def test_every_advertised_extra_has_a_clean_wheel_profile(monkeypatch: Any) -> None:
    metadata = _setup_metadata(monkeypatch)
    qualifier = runpy.run_path(
        str(ROOT / "scripts" / "qualify_wheel_distribution.py"),
        run_name="qitos_wheel_qualifier",
    )
    profiles = set(qualifier["PROFILE_IMPORTS"])

    assert profiles == {"base", *metadata["extras_require"]}


def test_required_capability_extras_match_import_dependencies(monkeypatch: Any) -> None:
    extras = _setup_metadata(monkeypatch)["extras_require"]

    assert extras["openai"] == ["openai>=1.66.0"]
    assert extras["local"] == ["openai>=1.66.0"]
    assert extras["litellm"] == ["litellm>=1.52.0"]
    assert extras["mcp"] == ["httpx>=0.27.0"]
    assert extras["wandb"] == ["wandb>=0.16.0"]
    assert extras["mlflow"] == ["mlflow>=2.0.0"]


def test_empty_extras_use_only_base_or_external_executables(monkeypatch: Any) -> None:
    extras = _setup_metadata(monkeypatch)["extras_require"]

    assert extras["anthropic"] == []  # requests is a base dependency
    assert extras["gemini"] == []  # requests is a base dependency
    assert extras["qita"] == []  # pure Python plus base rich
    assert extras["docker"] == []  # Docker is an external executable
    assert extras["evaluation"] == []  # framework-only contracts


def test_fixture_bundle_is_complete_and_makes_no_release_claims() -> None:
    manifest = json.loads((FIXTURES / "fixture-manifest.json").read_text())
    required = {
        "candidate_records",
        "crash_reopen_and_integrity",
        "reader_parity_and_qita",
        "evaluator_and_exporter",
        "privacy_and_publication",
        "storage_measurement",
        "a_b_c_readiness",
        "producer_manifest",
        "qualification_evidence",
        "g5_switch_and_rollback",
        "packaging_matrix",
    }

    assert set(manifest["categories"]) == required
    assert manifest["schema_frozen"] is False
    assert manifest["publication_ready"] is False
    for filename in manifest["categories"].values():
        payload = json.loads((FIXTURES / filename).read_text())
        assert payload.get("claims", []) == []
