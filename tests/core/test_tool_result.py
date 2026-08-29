from __future__ import annotations

import json
from pathlib import Path

import pytest

from qitos.core.action import ActionResult, ActionStatus
from qitos.core.tool_result import (
    TOOL_RESULT_MODEL_VIEW_VERSION,
    TOOL_RESULT_SCHEMA_VERSION,
    TOOL_RESULT_TRACE_SAFE_VERSION,
    ToolResult,
    ToolResultContractError,
)


FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "tool_results" / "v1"


def test_canonical_result_round_trip_is_lossless() -> None:
    result = ToolResult(
        tool_name="edit",
        action_id="call-1",
        output={"changed": True, "private": "canonical"},
        model_output="Changed one file.",
        complete=False,
        truncated=True,
        omitted={"lines": 4},
        next_action={"name": "read", "args": {"path": "a.py"}},
        attempts=2,
        latency_ms=3.5,
        declared_effects=[{"kind": "filesystem_write"}],
        filesystem_changes=[{"path": "a.py", "operation": "updated"}],
        artifact_refs=[{"artifact_id": "sha256:abc"}],
        normalized_request={"path": "a.py"},
        provenance={"source": "executor"},
    )

    payload = json.loads(json.dumps(result.to_dict()))
    loaded = ToolResult.from_value(payload)

    assert loaded.to_dict() == payload
    assert payload["schema_version"] == TOOL_RESULT_SCHEMA_VERSION
    assert payload["success"] is True
    assert payload["output"]["private"] == "canonical"
    assert payload["model_output"] == "Changed one file."


def test_action_result_adapter_preserves_terminal_execution_fields() -> None:
    action_result = ActionResult(
        name="slow",
        action_id="call-timeout",
        status=ActionStatus.TIMED_OUT,
        error="deadline exceeded",
        attempts=1,
        latency_ms=50.0,
        metadata={
            "error_category": "timeout",
            "worker_still_running": True,
            "recoverable": False,
            "provenance": {"timeout_source": "action"},
        },
    )

    canonical = action_result.to_tool_result()

    assert canonical.status == "timed_out"
    assert canonical.tool_name == "slow"
    assert canonical.action_id == "call-timeout"
    assert canonical.error_code == "timeout"
    assert canonical.error_kind == "execution"
    assert canonical.worker_still_running is True
    assert canonical.attempts == 1
    assert canonical.latency_ms == 50.0


def test_nested_canonical_result_is_authoritative_during_action_adaptation() -> None:
    semantic = ToolResult.semantic_error(
        code="path_not_found",
        error="missing path",
        recovery_hint="List the directory.",
        next_action={"name": "list_files", "args": {"path": "."}},
    )
    executor_record = ActionResult(
        name="read",
        action_id="call-2",
        status=ActionStatus.SUCCESS,
        output=semantic,
        attempts=2,
        latency_ms=4.0,
        metadata={"source": "function"},
    )

    canonical = ToolResult.from_action_result(executor_record)

    assert canonical.status == "error"
    assert canonical.error_kind == "semantic"
    assert canonical.error_code == "path_not_found"
    assert canonical.tool_name == "read"
    assert canonical.action_id == "call-2"
    assert canonical.attempts == 2


def test_legacy_dict_and_model_summary_remain_compatible() -> None:
    result = ToolResult.from_value(
        {
            "status": "partial",
            "output": {"model_summary": "bounded", "raw": [1, 2, 3]},
            "metadata": {"tool_name": "legacy"},
        }
    )

    assert result.status == "success"
    assert result.model_output == "bounded"
    assert result.output["raw"] == [1, 2, 3]
    assert result.tool_name == "legacy"


def test_canonical_serializer_does_not_flatten_output_but_legacy_adapter_can() -> None:
    result = ToolResult(output={"value": 7, "status": "nested"})

    canonical = result.to_persistence_dict()
    legacy = result.to_legacy_dict()

    assert "value" not in canonical
    assert canonical["status"] == "success"
    assert legacy["value"] == 7
    assert legacy["status"] == "success"


def test_from_value_discriminates_canonical_before_legacy_adaptation() -> None:
    with pytest.raises(ToolResultContractError) as caught:
        ToolResult.from_value(
            {
                "schema_version": "qitos.tool_result/v999",
                "status": "success",
                "output": "must not be guessed",
            }
        )

    assert caught.value.code == "unknown_schema_version"


@pytest.mark.parametrize(
    "override",
    [
        {"metadata": []},
        {"omitted": []},
        {"declared_effects": ["not-an-object"]},
        {"filesystem_changes": {}},
        {"artifact_refs": [{"artifact_id": "x", "host_path": "/tmp/x"}]},
        {"normalized_request": []},
        {"provenance": []},
    ],
)
def test_malformed_canonical_collections_fail_without_silent_drops(
    override: dict[str, object],
) -> None:
    payload = ToolResult().to_dict()
    payload.update(override)

    with pytest.raises(ToolResultContractError):
        ToolResult.from_canonical_dict(payload)


@pytest.mark.parametrize(
    "override",
    [
        {"attempts": True},
        {"attempts": -1},
        {"latency_ms": float("inf")},
        {"complete": 1},
        {"truncated": 0},
        {"worker_still_running": "yes"},
        {"omitted": {"characters": True}},
    ],
)
def test_canonical_scalar_types_and_ranges_are_strict(
    override: dict[str, object],
) -> None:
    payload = ToolResult().to_dict()
    payload.update(override)

    with pytest.raises(ToolResultContractError):
        ToolResult.from_canonical_dict(payload)


def test_contradictory_terminal_state_is_rejected() -> None:
    payload = ToolResult().to_dict()
    payload.update(
        {
            "status": "success",
            "success": True,
            "error_kind": "execution",
            "error_code": "tool_failed",
        }
    )

    with pytest.raises(ToolResultContractError) as caught:
        ToolResult.from_canonical_dict(payload)

    assert caught.value.code == "contradictory_outcome"


def test_non_json_value_fails_at_typed_contract_boundary() -> None:
    with pytest.raises(ToolResultContractError) as caught:
        ToolResult(output=object())

    assert caught.value.code == "non_serializable_value"


def test_serializer_revalidates_mutated_canonical_object() -> None:
    result = ToolResult(output="valid")
    result.attempts = True

    with pytest.raises(ToolResultContractError) as caught:
        result.to_persistence_dict()

    assert caught.value.code == "invalid_canonical_field"


def test_present_success_field_must_be_boolean() -> None:
    payload = ToolResult().to_dict()
    payload["success"] = None

    with pytest.raises(ToolResultContractError) as caught:
        ToolResult.from_canonical_dict(payload)

    assert caught.value.code == "contradictory_outcome"


def test_model_view_is_allowlisted_redacted_and_bounded() -> None:
    result = ToolResult(
        tool_name="inspect",
        action_id="call-safe",
        output={"raw": "x" * 200},
        model_output=(
            "token=super-secret /Users/alice/work/private.txt " + "x" * 200
        ),
        metadata={"authorization": "Bearer internal"},
        normalized_request={"path": "/Users/alice/work/private.txt"},
        provenance={"exception_repr": "RuntimeError(secret)"},
        artifact_refs=[{"artifact_id": "sha256:abc"}],
        filesystem_changes=[{"path": "/Users/alice/work/private.txt"}],
    )

    visible = result.to_model_dict(max_chars=80)

    assert set(visible) == {
        "schema_version",
        "status",
        "tool_name",
        "action_id",
        "model_output",
        "error",
        "error_code",
        "recoverable",
        "recovery_hint",
        "next_action",
    }
    assert visible["schema_version"] == TOOL_RESULT_MODEL_VIEW_VERSION
    assert len(visible["model_output"]) <= 80
    rendered = json.dumps(visible)
    assert "super-secret" not in rendered
    assert "/Users/alice" not in rendered
    assert "authorization" not in rendered
    assert "exception_repr" not in rendered
    assert "artifact_id" not in rendered
    assert "filesystem_changes" not in rendered
    assert result.output == {"raw": "x" * 200}


def test_zero_remaining_model_budget_emits_no_oversized_truncation_card() -> None:
    visible = ToolResult(output="x" * 100).to_model_dict(max_chars=0)

    assert visible["model_output"] == ""
    assert visible["error"] is None


def test_large_error_output_and_message_share_one_budget() -> None:
    result = ToolResult.execution_error(
        code="tool_failed",
        error="e" * 100,
        output="o" * 100,
    )

    visible = result.to_model_dict(max_chars=32)

    assert len(visible["model_output"] or "") + len(visible["error"] or "") <= 32


def test_trace_safe_projection_is_versioned_and_declares_loss() -> None:
    result = ToolResult(
        output={"token": "secret", "path": "/Users/alice/work/a.py"},
        metadata={"internal": True},
        provenance={"source": "executor"},
        artifact_refs=[{"artifact_id": "sha256:abc"}],
    )

    visible = result.to_trace_safe_dict(max_chars=120)

    assert visible["schema_version"] == TOOL_RESULT_TRACE_SAFE_VERSION
    assert visible["loss"]["canonical_output_included"] is False
    assert set(visible["loss"]["excluded_fields"]) >= {
        "output",
        "metadata",
        "provenance",
        "artifact_refs",
    }
    assert visible["loss"]["redacted_secret_values"] == 1
    assert visible["loss"]["redacted_host_paths"] == 1
    assert '"token": "secret"' not in json.dumps(visible)
    assert "/Users/alice" not in json.dumps(visible)


@pytest.mark.parametrize(
    "next_action",
    ["read", {"name": "", "args": {}}, {"name": "read", "args": []}],
)
def test_next_action_is_validated(next_action: object) -> None:
    with pytest.raises(ValueError, match="next_action"):
        ToolResult(next_action=next_action)  # type: ignore[arg-type]


def test_versioned_outcome_fixture_inventory() -> None:
    fixture = json.loads((FIXTURE_DIR / "canonical_outcomes.json").read_text())
    cases = {item["case"]: ToolResult.from_value(item["result"]) for item in fixture["cases"]}

    assert fixture["schema_version"] == TOOL_RESULT_SCHEMA_VERSION
    assert set(cases) == {
        "success",
        "semantic_error",
        "execution_error",
        "permission_skipped",
        "timed_out_worker_still_running",
        "cancelled",
        "missing_parallel_slot",
        "retries_attempt_count",
        "truncated_next_action",
        "filesystem_effects",
        "artifact_ref_slot",
        "legacy_dict_model_summary",
    }
    assert cases["timed_out_worker_still_running"].worker_still_running is True
    assert cases["retries_attempt_count"].attempts == 3
    assert cases["truncated_next_action"].omitted == {"hits": 19}
    assert cases["filesystem_effects"].filesystem_changes[0]["path"] == "notes.txt"
    assert cases["artifact_ref_slot"].artifact_refs[0]["artifact_id"].startswith("sha256:")


def test_versioned_durability_and_lifecycle_fixture_inventory() -> None:
    durability = json.loads((FIXTURE_DIR / "durability_receipts.json").read_text())
    lifecycle = json.loads((FIXTURE_DIR / "lifecycle_receipts.json").read_text())

    assert {item["receipt"]["state"] for item in durability["cases"]} == {
        "accepted",
        "queued",
        "persisted",
        "failed",
        "dropped",
    }
    lifecycle_cases = {item["case"]: item["receipt"] for item in lifecycle["cases"]}
    assert lifecycle_cases["repeated_shutdown"]["close_effects"] == 1
    assert lifecycle_cases["borrowed_resource_remains_open"]["state"] == "open"
    assert lifecycle_cases["borrowed_resource_remains_open"]["framework_close_calls"] == 0


def test_contract_hardening_fixture_is_consumable_by_lanes_b_and_d() -> None:
    fixture = json.loads((FIXTURE_DIR / "contract_hardening.json").read_text())

    assert fixture["canonical_schema_version"] == TOOL_RESULT_SCHEMA_VERSION
    assert fixture["model_view_version"] == TOOL_RESULT_MODEL_VIEW_VERSION
    assert fixture["trace_safe_version"] == TOOL_RESULT_TRACE_SAFE_VERSION
    for case in fixture["invalid_canonical_cases"]:
        with pytest.raises(ToolResultContractError) as caught:
            ToolResult.from_value(case["result"])
        assert caught.value.code == case["expected_error_code"]

    canonical = ToolResult.from_value(fixture["model_safe_source"])
    model_view = canonical.to_model_dict(max_chars=200)
    trace_view = canonical.to_trace_safe_dict(max_chars=200)
    rendered_model = json.dumps(model_view)
    rendered_trace = json.dumps(trace_view)

    assert "fixture-secret" not in rendered_model
    assert "/Users/example" not in rendered_model
    assert "fixture-secret" not in rendered_trace
    assert "/Users/example" not in rendered_trace
    assert trace_view["loss"]["canonical_output_included"] is False
    assert set(trace_view["loss"]["excluded_fields"]) == set(
        fixture["expected_trace_loss"]["excluded_fields"]
    )
