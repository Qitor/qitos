from __future__ import annotations

from qitos.engine.events import EngineEvent, EngineEventType
from qitos.engine.states import RuntimeEvent, RuntimePhase, StepRecord
from qitos.render.events import RenderEvent
from qitos.trace.events import TraceEvent, TraceStep
from qitos.tracing.adapters import (
    classify_event,
    engine_event_to_record,
    render_event_to_record,
    runtime_event_to_record,
    step_record_to_record,
    trace_event_to_record,
    trace_step_to_record,
)
from qitos.tracing.trajectory import RecordKind, RecordRole


def test_event_vocabulary_covers_required_runtime_facts() -> None:
    cases = {
        RecordKind.SESSION: ("session_start", {}),
        RecordKind.RUN: ("run_start", {}),
        RecordKind.MODEL_REQUEST: ("decide", {"stage": "model_input"}),
        RecordKind.MODEL_RESPONSE: ("decide", {"stage": "model_output"}),
        RecordKind.REASONING: ("reasoning", {}),
        RecordKind.CONTINUATION: ("continuation", {}),
        RecordKind.TOOL_BATCH: ("tool_batch_start", {}),
        RecordKind.TOOL_SLOT: ("tool_slot_end", {}),
        RecordKind.LIFECYCLE: ("phase_start", {}),
        RecordKind.EFFECT: ("effect_committed", {}),
        RecordKind.CONTEXT: ("context_history", {}),
        RecordKind.COMPACTION: ("compact", {}),
        RecordKind.STEERING: ("steering_applied", {}),
        RecordKind.SNAPSHOT: ("snapshot_persisted", {}),
        RecordKind.PAUSE: ("pause_requested", {}),
        RecordKind.RESTORE: ("restore", {}),
        RecordKind.BUDGET: ("budget_exhausted", {}),
        RecordKind.STOP: ("stop", {}),
        RecordKind.ERROR: ("decide", {}, False, "boom"),
        RecordKind.LOSS: ("loss", {}),
        RecordKind.ARTIFACT: ("artifact", {}),
        RecordKind.WORK_GRAPH: ("join_committed", {}),
    }
    for expected, values in cases.items():
        phase = values[0]
        payload = values[1]
        ok = values[2] if len(values) > 2 else True
        error = values[3] if len(values) > 3 else None
        assert classify_event(phase, payload, ok=ok, error=error) == expected
    assert classify_event("check_stop", {}) == RecordKind.LIFECYCLE
    assert classify_event("error", {}) == RecordKind.ERROR


def test_runtime_event_adapter_preserves_authority_and_reports_embedded_loss() -> None:
    event = RuntimeEvent(
        step_id=2,
        phase=RuntimePhase.DECIDE,
        payload={
            "stage": "model_output",
            "reasoning_content": "opaque reasoning",
        },
    )
    record = runtime_event_to_record(
        event,
        run_id="run-1",
        session_id="session-1",
        work_item_id="work-1",
    )
    assert record.kind == RecordKind.MODEL_RESPONSE
    assert record.role == RecordRole.CANONICAL_RUNTIME_FACT
    assert record.step_id == 2
    assert not record.loss.is_lossless


def test_step_and_render_adapters_are_declared_derived_views() -> None:
    step = step_record_to_record(
        StepRecord(step_id=1),
        run_id="run-1",
    )
    render = render_event_to_record(
        RenderEvent(channel="thinking", node="model_output", step_id=1),
        run_id="run-1",
    )
    assert step.kind == RecordKind.STEP
    assert step.role == RecordRole.DERIVED_VIEW
    assert render.kind == RecordKind.MODEL_RESPONSE
    assert render.role == RecordRole.DERIVED_VIEW
    assert not render.loss.is_lossless


def test_engine_stream_and_frozen_trace_roles_are_not_promoted() -> None:
    engine = engine_event_to_record(
        EngineEvent(event_type=EngineEventType.RUN_END),
        run_id="run-1",
    )
    trace_event = trace_event_to_record(
        TraceEvent(run_id="run-1", step_id=1, phase="END")
    )
    trace_step = trace_step_to_record(TraceStep(step_id=1), run_id="run-1")

    assert engine.kind == RecordKind.STOP
    assert engine.role == RecordRole.DERIVED_VIEW
    assert trace_event.kind == RecordKind.STOP
    assert trace_event.role == RecordRole.COMPATIBILITY_ARTIFACT
    assert trace_step.role == RecordRole.COMPATIBILITY_ARTIFACT
