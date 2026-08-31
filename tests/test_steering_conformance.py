from __future__ import annotations

import json

import pytest

from qitos.core.conversation import (
    ArgumentParseStatus,
    AssistantItem,
    CallIdentity,
    ExchangeLog,
    SteeringItem,
    ToolBatchBuilder,
    ToolCall,
    ToolResultItem,
)
from qitos.core.request_view import (
    ConversationSnapshotComponent,
    reconcile_steering_receipts,
    submit_steering,
)
from qitos.core.tool_result import ToolResult


def _open_batch() -> tuple[ExchangeLog, ToolCall]:
    call = ToolCall(
        identity=CallIdentity("fixture:native", "call-steering"),
        batch_id="batch-steering",
        name="read",
        raw_arguments="{}",
        parsed_arguments={},
        parse_status=ArgumentParseStatus.PARSED,
    )
    log = ExchangeLog(log_id="steering-log")
    builder = log.append(
        AssistantItem(
            item_id="assistant-steering",
            exchange_id="exchange-tools",
            parts=[call],
        )
    )
    assert builder is not None
    return log, call


def _complete(log: ExchangeLog, call: ToolCall) -> None:
    ToolBatchBuilder(log, call.batch_id).record_result(
        ToolResultItem(
            item_id="result-steering",
            exchange_id="exchange-tools",
            identity=call.identity,
            batch_id=call.batch_id,
            result=ToolResult(
                status="success",
                output={"ok": True},
                tool_name=call.name,
                action_id=call.identity.call_id,
                provenance={"source": "steering.fixture"},
            ),
        )
    )


def test_queued_steering_survives_snapshot_restore_and_is_consumed_once() -> None:
    log, call = _open_batch()
    receipt = submit_steering(
        log,
        "Use the smaller artifact.",
        sequence=7,
        boundary_id="batch-open",
        exchange_id="exchange-next",
    )
    assert receipt.disposition == "queued"
    assert receipt.applied_once is False

    component = ConversationSnapshotComponent.from_exchange_log(
        log, steering_receipts=(receipt,)
    )
    restored_component = ConversationSnapshotComponent.from_dict(
        json.loads(json.dumps(component.to_dict()))
    )
    restored = restored_component.exchange_log

    _complete(restored, call)
    reconciled = reconcile_steering_receipts(
        restored,
        restored_component.steering_receipts,
        boundary_id="batch-closed",
    )
    repeated = reconcile_steering_receipts(
        restored, reconciled, boundary_id="later-boundary"
    )

    assert reconciled[0].disposition == "applied"
    assert reconciled[0].applied_once is True
    assert repeated == reconciled
    assert restored.queued_steering == ()
    assert sum(isinstance(item, SteeringItem) for item in restored.items) == 1


def test_steering_at_safe_boundary_is_applied_without_a_second_queue() -> None:
    log = ExchangeLog(log_id="safe-steering-log")

    receipt = submit_steering(
        log,
        "Proceed now.",
        sequence=1,
        boundary_id="safe-boundary",
        exchange_id="exchange-now",
    )

    assert receipt.disposition == "applied"
    assert receipt.applied_once is True
    assert log.queued_steering == ()
    assert [item.item_id for item in log.items] == [receipt.item_id]


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
def test_terminal_session_steering_is_typed_rejected(status: str) -> None:
    log = ExchangeLog(log_id=f"terminal-{status}")

    receipt = submit_steering(
        log,
        "Too late.",
        sequence=2,
        boundary_id="terminal-boundary",
        exchange_id="exchange-terminal",
        session_status=status,
    )

    assert receipt.disposition == "rejected"
    assert receipt.reason_code == f"session_{status}"
    assert receipt.applied_once is False
    assert log.items == ()
    assert log.queued_steering == ()
