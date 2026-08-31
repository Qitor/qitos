from __future__ import annotations

import inspect
import json
from pathlib import Path

from qitos.qita import _cli_app
from qitos.qita._cli_app import _discover_runs, _load_run_payload
from qitos.qita.reader import (
    default_reader,
    discover_run_payloads,
    load_session_payload,
)
from qitos.tracing import (
    MemoryTrajectoryStore,
    PrivacyView,
    RecordKind,
    StoreTrajectoryReader,
    TrajectoryRecord,
)
from qitos.tracing.readers import trajectory_to_qita_payload


def _trace_run(root: Path) -> Path:
    run = root / "compat-run"
    run.mkdir()
    (run / "screen.png").write_bytes(b"png")
    (run / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "v1",
                "run_id": "compat-run",
                "status": "completed",
                "updated_at": "2026-08-31T00:00:00+00:00",
                "step_count": 1,
                "event_count": 1,
                "summary": {
                    "stop_reason": "final",
                    "final_result": "ok",
                    "steps": 1,
                },
            }
        ),
        encoding="utf-8",
    )
    (run / "events.jsonl").write_text(
        json.dumps(
            {
                "step_id": 0,
                "phase": "DECIDE",
                "ok": True,
                "ts": "2026-08-31T00:00:01+00:00",
                "payload": {"stage": "model_output", "text": "ok"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run / "steps.jsonl").write_text(
        json.dumps(
            {
                "step_id": 0,
                "observation": {},
                "decision": {},
                "actions": [],
                "action_results": [],
                "tool_invocations": [],
                "critic_outputs": [],
                "state_diff": {},
                "visual_assets": [
                    {
                        "kind": "screenshot",
                        "path": str(run / "screen.png"),
                        "mime_type": "image/png",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return run


def test_qita_default_reader_preserves_frozen_trace_parity(tmp_path: Path) -> None:
    run = _trace_run(tmp_path)
    reader = default_reader(tmp_path)
    assert reader.capabilities.source_kind == "frozen_trace_compatibility"
    assert reader.capabilities.default_qualified is True

    runs = _discover_runs(tmp_path)
    assert runs[0]["id"] == "compat-run"
    assert runs[0]["status"] == "completed"
    assert Path(runs[0]["path"]) == run

    public_runs = discover_run_payloads(reader)
    assert "path" not in public_runs[0]

    payload = _load_run_payload(run)
    assert payload["run_id"] == "compat-run"
    assert payload["manifest"]["summary"]["final_result"] == "ok"
    assert payload["events"][0]["phase"] == "DECIDE"
    assert payload["steps"][0]["step_id"] == 0
    assert payload["events_by_step"]["0"][0]["ok"] is True
    assert payload["steps"][0]["visual_assets"][0]["path"] == "screen.png"
    assert "/Users/" not in json.dumps(payload)
    assert payload["trajectory_meta"]["privacy_view"] == "redacted_public"
    loss_codes = {
        entry["code"] for entry in payload["trajectory_meta"]["loss"]["entries"]
    }
    assert "missing_session_id" in loss_codes


def test_store_reader_exposes_tool_effect_and_snapshot_timelines() -> None:
    store = MemoryTrajectoryStore()
    records = (
        TrajectoryRecord.create(
            RecordKind.RUN,
            record_id="run",
            run_id="run-1",
            session_id="session-1",
            payload={"run_id": "run-1", "status": "paused"},
        ),
        TrajectoryRecord.create(
            RecordKind.TOOL_SLOT,
            record_id="slot",
            run_id="run-1",
            session_id="session-1",
            step_id=0,
            payload={"tool_call_id": "call-1", "status": "completed"},
        ),
        TrajectoryRecord.create(
            RecordKind.EFFECT,
            record_id="effect",
            run_id="run-1",
            session_id="session-1",
            payload={"status": "committed"},
        ),
        TrajectoryRecord.create(
            RecordKind.SNAPSHOT,
            record_id="snapshot",
            run_id="run-1",
            session_id="session-1",
            snapshot_id="snapshot-1",
            payload={"head_generation": 2},
        ),
    )
    store.append_batch(records)
    reader = StoreTrajectoryReader(store)
    assert reader.capabilities.default_qualified is False
    trajectory = reader.read_run("run-1", view=PrivacyView.REDACTED_PUBLIC)
    payload = trajectory_to_qita_payload(trajectory)
    assert len(payload["tool_effect_timeline"]) == 2
    assert len(payload["snapshot_lineage"]) == 1
    assert payload["work_graph"] == []
    assert payload["trajectory_meta"]["session_ids"] == ["session-1"]

    session = load_session_payload(reader, "session-1")
    assert session["trajectory_meta"]["session_id"] == "session-1"
    assert session["trajectory_meta"]["session_ids"] == ["session-1"]


def test_qita_no_longer_owns_trace_copy_fork_semantics() -> None:
    source = inspect.getsource(_cli_app._build_handler)
    assert "ReplaySession" not in source
    assert "fork_dir.mkdir" not in source
    assert "runtime_not_ready" in source
