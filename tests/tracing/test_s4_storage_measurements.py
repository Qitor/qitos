from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "s4" / "lane_d" / "storage-measurement-manifest.json"


def _module() -> Any:
    path = ROOT / "scripts" / "measure_trajectory_store.py"
    spec = importlib.util.spec_from_file_location("s4_measure_trajectory", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_measurement_dry_run_validates_both_sources_without_fake_numbers() -> None:
    result = _module().build_result(FIXTURE, repetitions=2, dry_run=True)
    assert result["status"] == "dry_run_ready"
    assert result["source_names"] == ["coding-tool-agent", "research-tool-agent"]
    assert result["measurements"] == []
    assert result["claims"] == []


def test_real_mode_emits_raw_repeated_measurements_without_release_claim() -> None:
    result = _module().build_result(FIXTURE, repetitions=2, dry_run=False)
    assert result["status"] == "measured_not_release_qualified"
    assert result["claims"] == []
    assert len(result["measurements"]) == 2
    for source in result["measurements"]:
        assert len(source["raw_measurements"]) == 2
        assert source["canonical_bytes"] > 0
        assert source["gzip_bytes"] > 0
        assert source["record_count"] >= 300
        assert all(item["journal_append_ns"] > 0 for item in source["raw_measurements"])
        assert all(item["reopen_ns"] > 0 for item in source["raw_measurements"])
        assert all(item["query_ns"] > 0 for item in source["raw_measurements"])
        assert all(item["replay_ns"] > 0 for item in source["raw_measurements"])


def test_missing_fixture_is_typed_not_ready_without_empty_success(tmp_path: Path) -> None:
    result = _module().build_result(
        tmp_path / "missing.json", repetitions=2, dry_run=False
    )
    assert result["status"] == "not_ready"
    assert result["reason_code"] == "measurement_fixture_unavailable"
    assert result["measurements"] == []
    assert result["claims"] == []
