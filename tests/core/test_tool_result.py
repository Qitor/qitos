from __future__ import annotations

import json
from pathlib import Path

import pytest

from qitos.core.action import ActionResult, ActionStatus
from qitos.core.tool_result import TOOL_RESULT_SCHEMA_VERSION, ToolResult


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
