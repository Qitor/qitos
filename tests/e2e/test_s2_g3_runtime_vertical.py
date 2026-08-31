"""Authoritative offline subprocess proof for S2 runtime convergence."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/e2e/s2_g3_runtime_fixture.py"


def _run(phase: str, root: Path, receipt: dict | None = None) -> dict:
    command = [sys.executable, str(FIXTURE), phase, str(root)]
    if receipt is not None:
        command.append(json.dumps(receipt, sort_keys=True))
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT)
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_twenty_clean_process_vertical_continuity_rounds(tmp_path: Path) -> None:
    for index in range(20):
        round_root = tmp_path / f"round-{index:02d}"
        parent = _run("parent", round_root)
        assert parent["lifecycle"] == "paused"
        assert parent["missing_slots"] == ["call_missing"]
        assert parent["worker_running_proof"] is True
        assert parent["reduced_batches"] == 0
        assert parent["counters"] == {
            "committed_effect": 1,
            "barrier": 1,
            "eligible_missing": 0,
        }

        child = _run("child", round_root, parent)
        assert child["run_id"] != parent["run_id"]
        assert child["lifecycle"] == "completed"
        assert child["final_result"] == "complete"
        assert child["reduced_batches"] == 1
        assert child["counters"] == {
            "committed_effect": 1,
            "barrier": 1,
            "eligible_missing": 1,
        }
        assert child["stale_rejected"] is True
        assert child["steering_applied_once"] is True
        assert child["continuation_count"] == 1
        assert child["artifact_count"] == 1
        assert child["budget_continuity"] is True
        assert child["trajectory_session_match"] is True
        assert child["trajectory_cursor_monotonic"] is True
        assert child["qita_read_only"] is True
        assert child["runtime_sink_reports"] > 0
        assert all(child["required_kinds_present"].values())
