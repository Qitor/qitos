"""Readiness tests for the schema-neutral trajectory benchmark scaffold."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "benchmark_trajectory_store.py"


def _load_script() -> Any:
    spec = importlib.util.spec_from_file_location("benchmark_trajectory_store", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_readiness_result_is_typed_and_makes_no_measurement_claims() -> None:
    module = _load_script()
    fixture_root = ROOT / "tests" / "fixtures" / "trajectories"

    result = module.build_readiness_result(fixture_root, dry_run=True)

    assert result["status"] == "schema_not_ready"
    assert result["reason_code"] == "TRAJECTORY_SCHEMA_NOT_READY"
    assert result["trajectory_v2_schema_frozen"] is False
    assert result["source_classes"] == ["campaign_long", "unrelated_agent"]
    assert result["measurements"] == []
    assert result["claims"] == []


def test_missing_fixture_root_is_a_typed_blocker(tmp_path: Path) -> None:
    module = _load_script()

    result = module.build_readiness_result(tmp_path / "missing", dry_run=True)

    assert "fixture_root_not_found" in result["blockers"]
    assert result["status"] == "schema_not_ready"
