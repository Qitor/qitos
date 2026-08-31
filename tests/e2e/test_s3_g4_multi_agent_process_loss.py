from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).parents[2]
FIXTURE = "tests/e2e/s3_g4_process_fixture.py"


def _run(phase: str, *, database: Path, control: Path, candidate: Path) -> dict:
    env = dict(os.environ)
    env.update(
        {
            "QITOS_G4_PHASE": phase,
            "QITOS_G4_DB": str(database),
            "QITOS_G4_CONTROL": str(control),
            "QITOS_G4_CANDIDATE": str(candidate),
        }
    )
    completed = subprocess.run(
        [sys.executable, FIXTURE],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if phase in {"create", "prepare_create"}:
        assert control.is_file()
        return json.loads(control.read_text(encoding="utf-8"))
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_g4_twenty_clean_process_rounds(tmp_path: Path) -> None:
    receipts = []
    for round_index in range(20):
        root = tmp_path / f"round-{round_index:02d}"
        root.mkdir()
        database = root / "g4.sqlite"
        control = root / "control.json"
        candidate = root / "candidate.json"
        created = _run(
            "create", database=database, control=control, candidate=candidate
        )
        restored = _run(
            "restore", database=database, control=control, candidate=candidate
        )

        assert created["session_id"]
        assert restored["before"]["delegate:completed"] == "completed"
        assert restored["before"]["delegate:queued"] == "queued"
        assert restored["after"]["delegate:completed"] == "completed"
        assert restored["after"]["delegate:queued"] == "dispatched"
        assert restored["after"]["spawn:running"] == "outcome_unknown"
        assert restored["restore_dispatches"] == ["delegate:queued"]
        assert restored["join_state"] == "closed"
        assert len(restored["accepted"]) == 2
        assert len(restored["discarded"]) == 1
        assert restored["owner_transfers"] == 1
        assert restored["authoritative_owner"]
        assert restored["cancellation_policies"] == [
            "detach", "propagate", "request_and_wait"
        ]
        assert restored["detachments"] == 1
        assert restored["fan_out_width"] == 2
        assert restored["secret_free"] is True
        assert restored["qita_graph"] is True
        assert restored["qita_timeline"] is True
        receipts.append((created["session_id"], restored["join_generation"]))

    assert len({session_id for session_id, _ in receipts}) == 20
    assert {generation for _, generation in receipts} == {2}


def test_g4_twenty_preparation_crash_rounds(tmp_path: Path) -> None:
    sessions = []
    for round_index in range(20):
        root = tmp_path / f"prepare-{round_index:02d}"
        root.mkdir()
        database = root / "preparation.sqlite"
        control = root / "control.json"
        candidate = root / "unused.json"
        created = _run(
            "prepare_create",
            database=database,
            control=control,
            candidate=candidate,
        )
        restored = _run(
            "prepare_restore",
            database=database,
            control=control,
            candidate=candidate,
        )

        assert restored == {
            "after": "dispatched",
            "before": "declared",
            "dispatches": ["delegate:declared"],
            "fork_reused": True,
            "operation_id": "delegate:declared",
        }
        sessions.append(created["session_id"])

    assert len(set(sessions)) == 20
