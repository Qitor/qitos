import json
from pathlib import Path

from benchmarks.swe_mini_eval import run_eval as run_swe_eval
from benchmarks.voyager_eval import run_eval as run_voyager_eval
from qitos.debug import ReplaySession
from qitos.trace import TraceSchemaValidator, TraceWriter


def _load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_trace_writer_manifest_required_fields(tmp_path: Path):
    writer = TraceWriter(
        output_dir=str(tmp_path),
        run_id="trace-contract",
        metadata={
            "model_id": "unit-test-model",
            "prompt_hash": "p-hash",
            "tool_versions": {"tool": "1.0"},
            "seed": 7,
            "run_config_hash": "cfg-hash",
        },
    )
    writer.finalize(
        status="completed",
        summary={
            "stop_reason": "final_result",
            "final_result": "ok",
            "steps": 0,
            "failure_report": {},
        },
    )

    manifest = json.loads((tmp_path / "trace-contract" / "manifest.json").read_text(encoding="utf-8"))
    validator = TraceSchemaValidator()
    validator.validate_manifest(manifest)


def test_swe_and_voyager_benchmarks_emit_valid_traces(tmp_path: Path):
    swe_trace_dir = tmp_path / "swe"
    voyager_trace_dir = tmp_path / "voyager"
    swe_trace_dir.mkdir(parents=True, exist_ok=True)
    voyager_trace_dir.mkdir(parents=True, exist_ok=True)

    swe_metrics = run_swe_eval(trace_output_dir=str(swe_trace_dir))
    voyager_metrics = run_voyager_eval(trace_output_dir=str(voyager_trace_dir))

    assert swe_metrics["success_rate"] == 1.0
    assert voyager_metrics["success_rate"] == 1.0

    validator = TraceSchemaValidator()
    for run_dir in [p for p in swe_trace_dir.iterdir() if p.is_dir()] + [p for p in voyager_trace_dir.iterdir() if p.is_dir()]:
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        events = _load_jsonl(run_dir / "events.jsonl")
        steps = _load_jsonl(run_dir / "steps.jsonl")
        validator.validate_manifest(manifest)
        validator.validate_events(events)
        validator.validate_steps(steps)


def test_inspector_payload_and_step_comparison(tmp_path: Path):
    trace_dir = tmp_path / "inspector"
    trace_dir.mkdir(parents=True, exist_ok=True)
    run_swe_eval(trace_output_dir=str(trace_dir))

    run_dirs = [p for p in trace_dir.iterdir() if p.is_dir()]
    assert run_dirs

    session = ReplaySession(str(run_dirs[0]))
    payload = session.inspect_step(0)
    assert payload is not None
    required = {
        "step_id",
        "rationale",
        "decision_mode",
        "actions",
        "action_results",
        "critic_outputs",
        "state_diff",
        "stop_reason",
    }
    assert required.issubset(payload.keys())

    if len(session.steps) >= 2:
        diff = session.compare_steps(0, 1)
        assert diff is not None
        assert "changes" in diff
