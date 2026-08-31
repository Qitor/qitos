from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from qitos.tracing.qualification import (
    QUALIFICATION_AUTHORITY,
    RECEIPT_VERSION,
    REQUIRED_SCENARIOS,
    load_receipts,
    qualify_runtime,
)


ROOT = Path(__file__).resolve().parents[2]


def _run(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _receipt_repo(
    tmp_path: Path, *, synthetic_lanes: Iterable[str] = ()
) -> Tuple[Path, list[Dict[str, Any]]]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(repo, "init")
    _run(repo, "config", "user.name", "Lane D Test")
    _run(repo, "config", "user.email", "lane-d@example.invalid")
    synthetic = set(synthetic_lanes)
    paths: Dict[str, Tuple[Path, Path]] = {}
    for lane, scenarios in REQUIRED_SCENARIOS.items():
        fixture = repo / "producer" / lane.lower() / "runtime-fixture.json"
        evidence = repo / "producer" / lane.lower() / "qualification.json"
        _write_json(
            fixture,
            {
                "lane": lane,
                "runtime_facts": list(scenarios),
                "bounded": True,
            },
        )
        _write_json(
            evidence,
            {
                "runtime_execution": True,
                "synthetic": lane in synthetic,
                "scenario_results": [
                    {"scenario": scenario, "status": "passed"}
                    for scenario in scenarios
                ],
            },
        )
        paths[lane] = (fixture, evidence)
    _run(repo, "add", ".")
    _run(repo, "commit", "-m", "test: runtime producer evidence")
    commit = _run(repo, "rev-parse", "HEAD")

    receipts = []
    for lane, (fixture, evidence) in paths.items():
        receipts.append(
            {
                "receipt_version": RECEIPT_VERSION,
                "lane": lane,
                "qualification_authority": QUALIFICATION_AUTHORITY,
                "producer_commit": commit,
                "fixture_path": fixture.relative_to(repo).as_posix(),
                "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
                "qualification_path": evidence.relative_to(repo).as_posix(),
                "qualification_sha256": hashlib.sha256(
                    evidence.read_bytes()
                ).hexdigest(),
                "scenarios": list(REQUIRED_SCENARIOS[lane]),
            }
        )
    return repo, receipts


def test_missing_producer_receipts_report_runtime_not_ready() -> None:
    result = qualify_runtime([], repository_root=ROOT)
    assert result.status == "s2_runtime_blocked"
    assert result.runtime_producer_qualified is False
    assert result.trajectory_schema_frozen is False
    assert result.qita_store_reader_default is False
    assert result.publication_ready is False
    assert result.measurement_claims_available is False
    assert result.qualified_lanes == ()
    assert {finding.code for finding in result.findings} >= {
        "producer_lane_not_qualified",
        "runtime_fact_missing",
    }


def test_exact_committed_a_b_c_receipts_can_qualify(tmp_path: Path) -> None:
    repo, receipts = _receipt_repo(tmp_path)
    result = qualify_runtime(receipts, repository_root=repo)
    assert result.status == "s2_runtime_ready"
    assert result.runtime_producer_qualified is True
    assert result.qualified_lanes == ("A", "B", "C")
    assert set(result.qualified_scenarios) == {
        scenario
        for scenarios in REQUIRED_SCENARIOS.values()
        for scenario in scenarios
    }
    assert result.trajectory_schema_frozen is False


def test_synthetic_runtime_evidence_is_rejected(tmp_path: Path) -> None:
    repo, receipts = _receipt_repo(tmp_path, synthetic_lanes=("B",))
    result = qualify_runtime(receipts, repository_root=repo)
    assert result.status == "s2_runtime_blocked"
    assert "B" not in result.qualified_lanes
    assert "synthetic_evidence_rejected" in {
        finding.code for finding in result.findings
    }


def test_default_exact_receipts_close_runtime_but_not_schema() -> None:
    path = ROOT / "tests" / "fixtures" / "s2" / "lane_d" / "producer-receipts.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    result = qualify_runtime(load_receipts(path), repository_root=ROOT)
    assert value["status"] == "s2_runtime_ready"
    assert result.status == "s2_runtime_ready"
    assert result.s2_runtime_ready is True
    assert result.trajectory_schema_publication_ready is False
    assert result.qita_store_reader_default is False
    assert result.measurement_claims_available is False
