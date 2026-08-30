from __future__ import annotations

import json
from pathlib import Path

import pytest

from qitos.core.action import ActionResult, ActionStatus
from qitos.core.tool_result import (
    TOOL_BATCH_CLOSURE_SCHEMA_VERSION,
    ToolResult,
    ToolResultContractError,
)


FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "tool_results"
    / "recovery_outcomes.json"
)


@pytest.mark.parametrize(
    "case",
    json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"],
    ids=lambda case: case["name"],
)
def test_recovery_fixture_round_trips_through_canonical_tool_result(case: dict) -> None:
    result = ToolResult(**case["tool_result"])
    payload = json.loads(json.dumps(result.to_persistence_dict()))
    restored = ToolResult.from_canonical_dict(payload)

    assert restored.to_persistence_dict() == payload
    for key, expected in case["expected"].items():
        assert getattr(restored, key) == expected


def test_effect_state_and_retry_invariants_reject_unsafe_claims() -> None:
    with pytest.raises(ToolResultContractError) as caught:
        ToolResult(effect_state="committed", effect_ref="effect:1", recoverable=True,
                   retry_disposition="retryable")
    assert caught.value.code == "unsafe_retry_disposition"

    with pytest.raises(ToolResultContractError) as caught:
        ToolResult(effect_state="unknown", effect_ref="effect:2")
    assert caught.value.code == "contradictory_effect"

    with pytest.raises(ToolResultContractError) as caught:
        ToolResult(retry_disposition="blocked_worker_running")
    assert caught.value.code == "unsafe_retry_disposition"


def test_partial_batch_closure_is_per_slot_and_strict() -> None:
    closure = {
        "schema_version": TOOL_BATCH_CLOSURE_SCHEMA_VERSION,
        "batch_id": "batch:1",
        "slots": [
            {"action_id": "call:1", "state": "success", "result_ref": "result:1"},
            {"action_id": "call:2", "state": "open", "attempt_id": "attempt:2"},
        ],
    }
    result = ToolResult(batch_closure=closure)
    closure["slots"][1]["state"] = "success"

    assert result.batch_closure["slots"][1]["state"] == "open"
    assert ToolResult.from_canonical_dict(result.to_dict()).batch_closure == result.batch_closure

    payload = result.to_dict()
    payload["batch_closure"]["slots"].append(
        {"action_id": "call:1", "state": "error"}
    )
    with pytest.raises(ToolResultContractError) as caught:
        ToolResult.from_canonical_dict(payload)
    assert caught.value.code == "invalid_batch_closure"


def test_action_result_adapter_carries_recovery_metadata_without_new_outcome_type() -> None:
    action = ActionResult(
        name="remote_write",
        status=ActionStatus.TIMED_OUT,
        action_id="call:remote",
        error="deadline elapsed",
        metadata={
            "error_category": "timeout",
            "worker_still_running": True,
            "attempt_id": "attempt:remote:1",
            "effect_ref": "effect:remote:1",
            "effect_state": "unknown",
            "idempotency_ref": "idem:remote:1",
            "retry_disposition": "blocked_worker_running",
            "outcome_unknown": True,
            "owner_generation": 4,
        },
    )

    result = action.to_tool_result()

    assert isinstance(result, ToolResult)
    assert result.attempt_id == "attempt:remote:1"
    assert result.effect_state == "unknown"
    assert result.outcome_unknown is True
    assert result.worker_still_running is True
    assert result.retry_disposition == "blocked_worker_running"
    assert result.owner_generation == 4


def test_recovery_refs_are_redacted_in_trace_view_but_canonical_is_lossless() -> None:
    result = ToolResult(
        attempt_id="/Users/alice/private/attempt",
        effect_ref="token=effect-secret",
        effect_state="unknown",
        idempotency_ref="secret=idem-secret",
        outcome_unknown=True,
        reconciliation_required=True,
        retry_disposition="requires_reconciliation",
    )

    canonical = result.to_persistence_dict()
    trace = result.to_trace_safe_dict()
    rendered = json.dumps(trace)

    assert canonical["attempt_id"] == "/Users/alice/private/attempt"
    assert "/Users/alice" not in rendered
    assert "effect-secret" not in rendered
    assert "idem-secret" not in rendered
    assert trace["loss"]["redacted_identifiers"] >= 3


def test_unknown_new_field_and_non_json_batch_value_fail_strictly() -> None:
    payload = ToolResult().to_dict()
    payload["effect_receipt_v2"] = {}
    with pytest.raises(ToolResultContractError) as caught:
        ToolResult.from_canonical_dict(payload)
    assert caught.value.code == "unknown_canonical_field"

    with pytest.raises(ToolResultContractError) as caught:
        ToolResult(batch_closure={"live_future": object()})
    assert caught.value.code == "non_serializable_value"
