from __future__ import annotations

from qitos.core.action import ActionResult, ActionStatus
from qitos.core.tool_result import ToolResult
from qitos.engine._action_runtime import _ActionRuntime


def test_explicit_model_projection_hides_canonical_output_fields() -> None:
    runtime = _ActionRuntime.__new__(_ActionRuntime)
    result = ToolResult(
        tool_name="inspect",
        output={"public": "fact", "private_host_path": "/private/tmp/raw"},
        model_output="fact",
        artifact_refs=[{"artifact_id": "sha256:abc"}],
    )

    visible = runtime._model_visible_tool_result_dict(result, "inspect")

    assert visible["output"] == "fact"
    assert visible["model_output"] == "fact"
    assert "private_host_path" not in visible
    assert result.output["private_host_path"] == "/private/tmp/raw"
    assert visible["artifact_refs"] == [{"artifact_id": "sha256:abc"}]


def test_action_adapter_keeps_skip_timeout_and_cancel_statuses() -> None:
    results = [
        ActionResult(name="a", status=ActionStatus.SKIPPED),
        ActionResult(
            name="b",
            status=ActionStatus.TIMED_OUT,
            metadata={"worker_still_running": True},
        ),
        ActionResult(name="c", status=ActionStatus.CANCELLED, attempts=0),
    ]

    canonical = [ToolResult.from_action_result(item) for item in results]

    assert [item.status for item in canonical] == ["skipped", "timed_out", "cancelled"]
    assert canonical[1].worker_still_running is True
    assert canonical[2].attempts == 0


def test_legacy_model_summary_projects_without_mutating_canonical_output() -> None:
    runtime = _ActionRuntime.__new__(_ActionRuntime)
    result = ToolResult.from_value(
        {"output": {"model_summary": "bounded", "raw": "retained"}}
    )

    visible = runtime._model_visible_tool_result_dict(result, "legacy")

    assert visible["output"] == "bounded"
    assert "raw" not in visible
    assert result.output["raw"] == "retained"
