from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def _run(phase: str, db_path: Path, session_id: str = "") -> dict:
    env = dict(os.environ)
    env.update(
        {
            "QITOS_S3_C_PHASE": phase,
            "QITOS_S3_C_DB": str(db_path),
            "QITOS_S3_C_SESSION": session_id,
        }
    )
    completed = subprocess.run(
        [sys.executable, "tests/e2e/s3_lane_c_process_fixture.py"],
        cwd=str(Path(__file__).parents[2]),
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_clean_process_restores_receipts_without_replaying_unknown(tmp_path) -> None:
    created = _run("create", tmp_path / "lane-c.db")
    restored = _run("restore", tmp_path / "lane-c.db", created["session_id"])

    assert restored["dispatch_count"] == 0
    assert restored["states"] == {
        "spawn:completed": "completed",
        "spawn:missing": "outcome_unknown",
        "spawn:unknown": "outcome_unknown",
    }
    assert restored["unknown"] == {
        "spawn:completed": False,
        "spawn:missing": True,
        "spawn:unknown": True,
    }
