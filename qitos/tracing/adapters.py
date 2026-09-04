"""Structural adapters into the one candidate trajectory record vocabulary."""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any, Mapping, Optional

from ..core.artifact import ArtifactRef
from .trajectory import (
    LossEntry,
    LossReport,
    RecordKind,
    RecordRole,
    TrajectoryRecord,
)


def _json_value(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _json_value(dataclasses.asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return {"type": type(value).__name__}


def classify_event(
    phase: str,
    payload: Optional[Mapping[str, Any]] = None,
    *,
    ok: bool = True,
    error: Any = None,
) -> RecordKind:
    """Classify all current event planes with one low-cardinality vocabulary."""
    upper = phase.upper()
    stage = str((payload or {}).get("stage", "")).lower()
    if not ok or error:
        return RecordKind.ERROR
    if "ERROR" in upper:
        return RecordKind.ERROR
    if stage == "steering_receipt":
        return RecordKind.STEERING
    if stage in {"model_input", "request_view"} or any(
        token in upper for token in ("MODEL_REQUEST", "MODEL_INPUT")
    ):
        return RecordKind.MODEL_REQUEST
    if stage == "provider_transaction":
        return RecordKind.PROVIDER_TRANSACTION
    if stage == "model_output" or any(
        token in upper for token in ("MODEL_RESPONSE", "MODEL_OUTPUT")
    ):
        return RecordKind.MODEL_RESPONSE
    if "REASON" in upper:
        return RecordKind.REASONING
    if "CONTINU" in upper:
        return RecordKind.CONTINUATION
    if "COMPACT" in upper or stage.startswith("compact"):
        return RecordKind.COMPACTION
    if "CONTEXT" in upper or stage == "context_history":
        return RecordKind.CONTEXT
    if "STEER" in upper:
        return RecordKind.STEERING
    if "SNAPSHOT" in upper or "CHECKPOINT" in upper:
        return RecordKind.SNAPSHOT
    if "RESTORE" in upper or "RESUME" in upper:
        return RecordKind.RESTORE
    if "PAUSE" in upper or "INTERRUPT" in upper:
        return RecordKind.PAUSE
    if "EFFECT" in upper:
        return RecordKind.EFFECT
    if "SANDBOX" in upper or stage.startswith("sandbox"):
        return RecordKind.SANDBOX
    if "OWNER" in upper or stage.startswith("ownership"):
        return RecordKind.OWNERSHIP
    if "BUDGET" in upper:
        return RecordKind.BUDGET
    if (
        ("STOP" in upper and upper != "CHECK_STOP")
        or upper in {"END", "SESSION_END", "RUN_END", "DONE"}
    ):
        return RecordKind.STOP
    if any(
        token in upper
        for token in ("HANDOFF", "DELEGATE", "FANOUT", "JOIN", "SPAWN", "WORK")
    ):
        return RecordKind.WORK_GRAPH
    if stage == "tool_batch_snapshot" or "TOOL_BATCH" in upper:
        return RecordKind.TOOL_BATCH
    if stage == "tool_result":
        return RecordKind.TOOL_RESULT
    if stage == "tool_slot_terminal" or "TOOL" in upper or upper in {
        "ACT",
        "ACT_ERROR",
        "ACTION",
    }:
        return RecordKind.TOOL_SLOT
    if "ARTIFACT" in upper:
        return RecordKind.ARTIFACT
    if upper in {"SESSION", "SESSION_START"}:
        return RecordKind.SESSION
    if upper in {"INIT", "RUN_START", "RUN"}:
        return RecordKind.RUN
    if "LOSS" in upper:
        return RecordKind.LOSS
    return RecordKind.LIFECYCLE


def _payload_text(payload: Mapping[str, Any], key: str) -> Optional[str]:
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _payload_int(payload: Mapping[str, Any], key: str) -> Optional[int]:
    value = payload.get(key)
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _explicit_identities(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Copy producer-emitted identities without deriving facts from names."""
    return {
        "attempt_id": _payload_text(payload, "attempt_id"),
        "attempt": _payload_int(payload, "attempt"),
        "owner_id": _payload_text(payload, "owner_id"),
        "owner_generation": _payload_int(payload, "owner_generation"),
        "operation_id": _payload_text(payload, "operation_id"),
        "lifecycle_state": _payload_text(payload, "lifecycle_state"),
        "provider_transaction_id": _payload_text(
            payload, "provider_transaction_id"
        ),
        "effect_id": _payload_text(payload, "effect_id"),
        "sandbox_id": _payload_text(payload, "sandbox_id"),
    }


def _event_name(event: Any, *, prefer_event_type: bool = False) -> str:
    values = (
        (getattr(event, "event_type", None), getattr(event, "phase", None))
        if prefer_event_type
        else (getattr(event, "phase", None), getattr(event, "event_type", None))
    )
    for value in values:
        if value is None:
            continue
        if hasattr(value, "value"):
            value = value.value
        text = str(value).strip()
        if text:
            return text
    return ""


def runtime_event_to_record(
    event: Any,
    *,
    run_id: str,
    session_id: Optional[str] = None,
    work_item_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> TrajectoryRecord:
    """Adapt a RuntimeEvent-like object without importing Engine types."""
    phase = _event_name(event)
    payload = _json_value(getattr(event, "payload", {}) or {})
    if not isinstance(payload, dict):
        payload = {"value": payload}
    error = getattr(event, "error", None)
    ok = bool(getattr(event, "ok", True))
    losses = []
    if (
        classify_event(phase, payload, ok=ok, error=error)
        == RecordKind.MODEL_RESPONSE
        and any(
            key in payload
            for key in ("reasoning_content", "reasoning_fields", "continuation")
        )
    ):
        losses.append(
            LossEntry(
                "embedded_reasoning_or_continuation",
                consequence="producer_fact_not_separately_identified",
            )
        )
    return TrajectoryRecord.create(
        classify_event(phase, payload, ok=ok, error=error),
        role=RecordRole.CANONICAL_RUNTIME_FACT,
        run_id=run_id,
        session_id=session_id,
        work_item_id=work_item_id,
        step_id=int(getattr(event, "step_id", 0)),
        phase=phase or None,
        agent_id=agent_id,
        occurred_at=str(getattr(event, "ts", "unknown")),
        monotonic_ns=getattr(event, "monotonic_ns", None),
        **_explicit_identities(payload),
        payload={"ok": ok, "payload": payload, "error": _json_value(error)},
        loss=LossReport(
            policy_id="qitos.adapter/runtime-event",
            entries=tuple(losses),
        ),
    )


def session_lifecycle_event_to_record(event: Any) -> TrajectoryRecord:
    """Adapt an explicit Session-head commit without inferring lineage."""
    lifecycle = str(getattr(event, "lifecycle", ""))
    kind = {
        "paused": RecordKind.PAUSE,
        "restoring": RecordKind.RESTORE,
    }.get(lifecycle, RecordKind.SESSION)
    return TrajectoryRecord.create(
        kind,
        role=RecordRole.CANONICAL_RUNTIME_FACT,
        session_id=str(getattr(event, "session_id")),
        run_id=str(getattr(event, "run_id")),
        snapshot_id=str(getattr(event, "snapshot_id")),
        checkpoint_ref=str(getattr(event, "checkpoint_id")),
        owner_id=getattr(event, "owner_id", None),
        owner_generation=int(getattr(event, "generation")),
        lifecycle_state=lifecycle or None,
        occurred_at=str(getattr(event, "captured_at")),
        payload={
            "lifecycle": lifecycle,
            "durability": str(getattr(event, "durability", "persisted")),
        },
    )


def runtime_event_to_records(
    event: Any,
    *,
    run_id: str,
    session_id: Optional[str] = None,
    work_item_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> tuple[TrajectoryRecord, ...]:
    """Expand one runtime publication into independently queryable facts."""
    primary = runtime_event_to_record(
        event,
        run_id=run_id,
        session_id=session_id,
        work_item_id=work_item_id,
        agent_id=agent_id,
    )
    raw = getattr(event, "payload", {}) or {}
    payload = raw if isinstance(raw, Mapping) else {}
    stage = str(payload.get("stage", ""))
    records = [primary]
    if stage == "request_view":
        request = payload.get("request_view", {})
        for receipt in request.get("compaction_receipts", ()):
            records.append(TrajectoryRecord.create(
                RecordKind.COMPACTION, role=RecordRole.CANONICAL_RUNTIME_FACT,
                run_id=run_id, session_id=session_id, work_item_id=work_item_id,
                step_id=int(getattr(event, "step_id", 0)), phase=primary.phase,
                agent_id=agent_id, **_explicit_identities(payload),
                payload={"compaction_receipt": _json_value(receipt),
                         "source": _json_value(request.get("source")),
                         "request_id": request.get("request_id"),
                         "selection": _json_value(request.get("selection"))},
                loss=LossReport(policy_id=str(receipt["policy_id"]), entries=tuple(
                    LossEntry(code=str(code), scope="model_request", consequence="model_projection_omitted")
                    for code in receipt.get("declared_losses", ())
                )),
            ))
    if stage == "provider_transaction":
        for kind, key in (
            (RecordKind.REASONING, "reasoning"),
            (RecordKind.CONTINUATION, "continuation_refs"),
            (RecordKind.LOSS, "loss"),
        ):
            if payload.get(key):
                records.append(
                    TrajectoryRecord.create(
                        kind,
                        role=RecordRole.CANONICAL_RUNTIME_FACT,
                        run_id=run_id,
                        session_id=session_id,
                        work_item_id=work_item_id,
                        step_id=int(getattr(event, "step_id", 0)),
                        phase=str(getattr(getattr(event, "phase", None), "value", ""))
                        or None,
                        agent_id=agent_id,
                        **_explicit_identities(payload),
                        payload={key: _json_value(payload[key])},
                    )
                )
    if stage == "tool_slot_terminal" and payload.get("effect") is not None:
        records.append(
            TrajectoryRecord.create(
                RecordKind.EFFECT,
                role=RecordRole.CANONICAL_RUNTIME_FACT,
                run_id=run_id,
                session_id=session_id,
                work_item_id=work_item_id,
                step_id=int(getattr(event, "step_id", 0)),
                phase=str(getattr(getattr(event, "phase", None), "value", ""))
                or None,
                agent_id=agent_id,
                tool_call_id=str(payload.get("slot_id") or "") or None,
                **_explicit_identities(payload),
                payload={"effect": _json_value(payload["effect"])},
            )
        )
        raw_artifacts = payload.get("artifact_refs", ())
        for raw_artifact in raw_artifacts:
            artifact = ArtifactRef.from_dict(raw_artifact)
            records.append(
                TrajectoryRecord.create(
                    RecordKind.ARTIFACT,
                    role=RecordRole.CANONICAL_RUNTIME_FACT,
                    run_id=run_id,
                    session_id=session_id,
                    work_item_id=work_item_id,
                    step_id=int(getattr(event, "step_id", 0)),
                    phase=str(
                        getattr(getattr(event, "phase", None), "value", "")
                    )
                    or None,
                    agent_id=agent_id,
                    tool_call_id=str(payload.get("slot_id") or "") or None,
                    **_explicit_identities(payload),
                    artifact_refs=(artifact,),
                    payload={"artifact_id": artifact.artifact_id},
                )
            )
    return tuple(records)


def engine_event_to_record(
    event: Any,
    *,
    run_id: str,
    session_id: Optional[str] = None,
    work_item_id: Optional[str] = None,
) -> TrajectoryRecord:
    """Adapt an EngineEvent-like streaming view without importing Engine."""
    event_name = _event_name(event, prefer_event_type=True)
    payload = _json_value(getattr(event, "payload", {}) or {})
    if not isinstance(payload, dict):
        payload = {"value": payload}
    error = _json_value(getattr(event, "error", None))
    ok = bool(getattr(event, "ok", True))
    return TrajectoryRecord.create(
        classify_event(event_name, payload, ok=ok, error=error),
        role=RecordRole.DERIVED_VIEW,
        run_id=run_id,
        session_id=session_id,
        work_item_id=work_item_id,
        step_id=int(getattr(event, "step_id", 0)),
        phase=event_name or None,
        agent_id=getattr(event, "agent_id", None),
        occurred_at=str(getattr(event, "ts", "unknown")),
        monotonic_ns=getattr(event, "monotonic_ns", None),
        **_explicit_identities(payload),
        payload={"ok": ok, "payload": payload, "error": error},
        loss=LossReport(
            policy_id="qitos.adapter/engine-event",
            entries=(
                LossEntry(
                    "derived_engine_stream",
                    consequence="not_runtime_storage_authority",
                ),
            ),
        ),
    )


def trace_event_to_record(event: Any) -> TrajectoryRecord:
    """Adapt a frozen TraceEvent-like compatibility artifact structurally."""
    phase = _event_name(event)
    payload = _json_value(getattr(event, "payload", {}) or {})
    if not isinstance(payload, dict):
        payload = {"value": payload}
    error = _json_value(getattr(event, "error", None))
    ok = bool(getattr(event, "ok", True))
    return TrajectoryRecord.create(
        classify_event(phase, payload, ok=ok, error=error),
        role=RecordRole.COMPATIBILITY_ARTIFACT,
        run_id=str(getattr(event, "run_id", "")) or None,
        step_id=int(getattr(event, "step_id", 0)),
        phase=phase or None,
        occurred_at=str(getattr(event, "ts", "unknown")),
        payload={"ok": ok, "payload": payload, "error": error},
        loss=LossReport(
            policy_id="qitos.adapter/frozen-trace-event",
            entries=(
                LossEntry(
                    "compatibility_trace_input",
                    consequence="session_and_work_lineage_unavailable",
                ),
            ),
        ),
    )


def step_record_to_record(
    step: Any,
    *,
    run_id: str,
    session_id: Optional[str] = None,
    work_item_id: Optional[str] = None,
) -> TrajectoryRecord:
    """Adapt a StepRecord-like aggregate as a declared derived view."""
    payload = _json_value(step)
    if not isinstance(payload, dict):
        payload = {"value": payload}
    return TrajectoryRecord.create(
        RecordKind.STEP,
        role=RecordRole.DERIVED_VIEW,
        run_id=run_id,
        session_id=session_id,
        work_item_id=work_item_id,
        step_id=int(getattr(step, "step_id", 0)),
        agent_id=getattr(step, "agent_id", None),
        payload=payload,
        loss=LossReport(
            policy_id="qitos.adapter/step-record",
            entries=(
                LossEntry(
                    "step_is_aggregate_view",
                    consequence="event_order_requires_runtime_records",
                ),
            ),
        ),
    )


def trace_step_to_record(step: Any, *, run_id: str) -> TrajectoryRecord:
    """Adapt a frozen TraceStep-like aggregate as a compatibility artifact."""
    payload = _json_value(step)
    if not isinstance(payload, dict):
        payload = {"value": payload}
    return TrajectoryRecord.create(
        RecordKind.STEP,
        role=RecordRole.COMPATIBILITY_ARTIFACT,
        run_id=run_id,
        step_id=int(getattr(step, "step_id", 0)),
        agent_id=getattr(step, "agent_id", None),
        payload=payload,
        loss=LossReport(
            policy_id="qitos.adapter/frozen-trace-step",
            entries=(
                LossEntry(
                    "compatibility_step_aggregate",
                    consequence="event_order_and_lineage_unavailable",
                ),
            ),
        ),
    )


def span_to_record(span: Any, *, run_id: Optional[str] = None) -> TrajectoryRecord:
    """Adapt a tracing Span-like object as a derived diagnostic view."""
    data = getattr(span, "data", None)
    span_type = str(getattr(data, "type", "custom"))
    export = getattr(data, "export", None)
    exported = export() if callable(export) else {}
    return TrajectoryRecord.create(
        classify_event(span_type, exported),
        role=RecordRole.DERIVED_VIEW,
        record_id=str(getattr(span, "span_id", "")) or None,
        run_id=run_id or str(getattr(span, "trace_id", "")) or None,
        causation_id=getattr(span, "parent_span_id", None),
        occurred_at=str(getattr(span, "started_at", "unknown")),
        payload={
            "span_data": _json_value(exported),
            "ended_at": getattr(span, "ended_at", None),
            "error": getattr(span, "error", None),
            "output": _json_value(getattr(span, "output", None)),
        },
        loss=LossReport(
            policy_id="qitos.adapter/span",
            entries=(
                LossEntry(
                    "derived_span_view",
                    consequence="not_runtime_storage_authority",
                ),
            ),
        ),
    )


def render_event_to_record(
    event: Any, *, run_id: str
) -> TrajectoryRecord:
    """Adapt a RenderEvent-like object as a lossy presentation view."""
    node = str(getattr(event, "node", ""))
    payload = _json_value(getattr(event, "payload", {}) or {})
    if not isinstance(payload, dict):
        payload = {"value": payload}
    return TrajectoryRecord.create(
        classify_event(node, payload),
        role=RecordRole.DERIVED_VIEW,
        run_id=run_id,
        step_id=int(getattr(event, "step_id", 0)),
        phase=node or None,
        occurred_at=str(getattr(event, "ts", "unknown")),
        payload={
            "channel": str(getattr(event, "channel", "")),
            "node": node,
            "payload": payload,
        },
        loss=LossReport(
            policy_id="qitos.adapter/render-event",
            entries=(
                LossEntry(
                    "presentation_projection",
                    consequence="exact_replay_unavailable",
                ),
            ),
        ),
    )


__all__ = [
    "classify_event",
    "engine_event_to_record",
    "render_event_to_record",
    "runtime_event_to_record",
    "runtime_event_to_records",
    "session_lifecycle_event_to_record",
    "span_to_record",
    "step_record_to_record",
    "trace_event_to_record",
    "trace_step_to_record",
]
