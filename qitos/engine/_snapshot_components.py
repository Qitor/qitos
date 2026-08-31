"""Engine-owned bridges for canonical Session snapshot components."""

from __future__ import annotations

from typing import Any

from ..core.conversation import ExchangeLog
from ..core.request_view import (
    CONVERSATION_SNAPSHOT_COMPONENT_CODEC,
    ConversationSnapshotComponent,
)
from ..models.codec import CodecReport
from ..core.tool_runtime import (
    TOOL_BATCH_SNAPSHOT_COMPONENT_CODEC,
    ToolBatchSnapshot,
)
from .runtime import RuntimeSnapshotContext


class ConversationRuntimeSnapshotComponent:
    """Capture and restore the model runtime's one canonical conversation."""

    codec = CONVERSATION_SNAPSHOT_COMPONENT_CODEC

    def capture(
        self, context: RuntimeSnapshotContext
    ) -> ConversationSnapshotComponent:
        engine = context.engine
        previous = getattr(engine, "_qitos_conversation_component", None)
        log = getattr(engine, "_qitos_exchange_log", None)
        if not isinstance(log, ExchangeLog):
            if isinstance(previous, ConversationSnapshotComponent):
                log = previous.exchange_log
            else:
                identity = str(
                    getattr(engine, "_session_run_id", "")
                    or getattr(engine, "_active_run_id", "")
                    or "pending"
                )
                log = ExchangeLog(log_id=f"session_log_{identity}")

        request = getattr(engine, "_qitos_last_request_view", None)
        report = getattr(engine, "_qitos_last_codec_report", None)
        report_payload = report.to_dict() if isinstance(report, CodecReport) else None
        if request is None and isinstance(previous, ConversationSnapshotComponent):
            request = previous.last_request_view
        if report_payload is None and isinstance(
            previous, ConversationSnapshotComponent
        ):
            report_payload = previous.last_codec_report

        component = ConversationSnapshotComponent.from_exchange_log(
            log,
            steering_receipts=tuple(
                getattr(engine, "_qitos_steering_receipts", ())
                or (
                    previous.steering_receipts
                    if isinstance(previous, ConversationSnapshotComponent)
                    else ()
                )
            ),
            continuation_refs=tuple(
                getattr(engine, "_qitos_continuation_refs", ())
                or (
                    previous.continuation_refs
                    if isinstance(previous, ConversationSnapshotComponent)
                    else ()
                )
            ),
            context_selection=(
                request.selection
                if request is not None
                else (
                    previous.context_selection
                    if isinstance(previous, ConversationSnapshotComponent)
                    else None
                )
            ),
            compaction_receipts=(
                request.compaction_receipts
                if request is not None
                else (
                    previous.compaction_receipts
                    if isinstance(previous, ConversationSnapshotComponent)
                    else ()
                )
            ),
            artifact_refs=(
                request.artifact_refs
                if request is not None
                else (
                    previous.artifact_refs
                    if isinstance(previous, ConversationSnapshotComponent)
                    else ()
                )
            ),
            last_request_view=request,
            last_codec_report=report_payload,
            reconstruction_requirements=(
                previous.reconstruction_requirements
                if isinstance(previous, ConversationSnapshotComponent)
                else None
            ),
        )
        engine._qitos_exchange_log = log
        engine._qitos_conversation_component = component
        return component

    def restore(
        self,
        value: Any,
        context: RuntimeSnapshotContext,
    ) -> None:
        if not isinstance(value, ConversationSnapshotComponent):
            raise TypeError(
                "conversation runtime restore requires ConversationSnapshotComponent"
            )
        engine = context.engine
        engine._qitos_conversation_component = value
        engine._qitos_exchange_log = value.exchange_log
        engine._qitos_steering_receipts = value.steering_receipts
        engine._qitos_continuation_refs = value.continuation_refs
        engine._qitos_continuation_ref = (
            value.continuation_refs[-1] if value.continuation_refs else None
        )
        engine._qitos_last_request_view = value.last_request_view
        engine._qitos_last_codec_report = (
            CodecReport.from_dict(value.last_codec_report)
            if value.last_codec_report is not None
            else None
        )


class ToolBatchRuntimeSnapshotComponent:
    """Bind the executor's current canonical batch to the Session head."""

    codec = TOOL_BATCH_SNAPSHOT_COMPONENT_CODEC

    def capture(self, context: RuntimeSnapshotContext) -> Any:
        value = getattr(context.engine, "_qitos_tool_batch_snapshot", None)
        if value is not None and not isinstance(value, ToolBatchSnapshot):
            raise TypeError("Engine tool-batch runtime state is invalid")
        return value

    def restore(self, value: Any, context: RuntimeSnapshotContext) -> None:
        if value is not None and not isinstance(value, ToolBatchSnapshot):
            raise TypeError("tool-batch restore requires ToolBatchSnapshot or None")
        context.engine._qitos_tool_batch_snapshot = value


DEFAULT_RUNTIME_SNAPSHOT_COMPONENTS = (
    ConversationRuntimeSnapshotComponent(),
    ToolBatchRuntimeSnapshotComponent(),
)


__all__: list[str] = []
