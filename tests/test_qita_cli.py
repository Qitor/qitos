from __future__ import annotations

import json
from pathlib import Path

from qitos.qita.cli import (
    _build_handler,
    _cmd_export,
    _discover_runs,
    _render_board_html,
    _render_replay_html,
    _render_run_html,
    main,
)


def _make_run(root: Path, run_id: str) -> Path:
    run = root / run_id
    run.mkdir(parents=True, exist_ok=True)
    (run / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "completed",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "step_count": 1,
                "event_count": 1,
                "summary": {"stop_reason": "final", "final_result": "ok", "steps": 1, "failure_report": {}},
                "schema_version": "v1",
                "model_id": "x",
                "prompt_hash": "y",
                "tool_versions": {},
                "seed": None,
                "run_config_hash": "z",
            }
        ),
        encoding="utf-8",
    )
    (run / "events.jsonl").write_text('{"step_id":0,"phase":"INIT","ok":true,"ts":"x"}\n', encoding="utf-8")
    (run / "steps.jsonl").write_text('{"step_id":0,"observation":{},"decision":{},"actions":[],"action_results":[],"tool_invocations":[],"critic_outputs":[],"state_diff":{}}\n', encoding="utf-8")
    return run


def test_discover_runs_and_export(tmp_path: Path):
    run = _make_run(tmp_path, "r1")
    runs = _discover_runs(tmp_path)
    assert len(runs) == 1
    assert runs[0]["id"] == "r1"

    out = tmp_path / "report.html"
    rc = _cmd_export(run=str(run), html_path=str(out))
    assert rc == 0
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "QitOS Trace" in content
    assert "r1" in content


def test_render_pages(tmp_path: Path):
    run = _make_run(tmp_path, "r2")
    payload = {
        "run": str(run),
        "run_id": "r2",
        "manifest": json.loads((run / "manifest.json").read_text(encoding="utf-8")),
        "events": [json.loads((run / "events.jsonl").read_text(encoding="utf-8").strip())],
        "steps": [json.loads((run / "steps.jsonl").read_text(encoding="utf-8").strip())],
        "events_by_step": {"0": [json.loads((run / "events.jsonl").read_text(encoding="utf-8").strip())]},
    }
    board = _render_board_html()
    view = _render_run_html(payload, embedded=False)
    replay = _render_replay_html(payload, speed_ms=200)
    assert "qita board" in board
    assert "export raw" in view
    assert "QitOS Replay" in replay
    marker = '<script id="payload" type="application/json">'
    start = view.index(marker) + len(marker)
    end = view.index("</script>", start)
    payload_block = view[start:end]
    assert '"run_id": "r2"' in payload_block
    assert "&quot;" not in payload_block


def test_handler_routes(tmp_path: Path):
    _make_run(tmp_path, "r3")
    handler_cls = _build_handler(tmp_path)
    assert handler_cls is not None


def test_main_export(tmp_path: Path):
    run = _make_run(tmp_path, "r4")
    out = tmp_path / "x.html"
    rc = main(["export", "--run", str(run), "--html", str(out)])
    assert rc == 0
    assert out.exists()
