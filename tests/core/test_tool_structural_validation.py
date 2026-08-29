from __future__ import annotations

from typing import Any

import pytest

from qitos.core.action import Action, ActionStatus
from qitos.core.tool import BaseTool, ToolSpec, validate_tool_arguments
from qitos.core.tool_registry import ToolRegistry
from qitos.engine.action_executor import ActionExecutor


SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "limit": {"type": "integer"},
        "options": {
            "type": "object",
            "properties": {"literal": {"type": "boolean"}},
            "additionalProperties": False,
        },
    },
    "required": ["query"],
    "additionalProperties": False,
}


class _RecordingTool(BaseTool):
    def __init__(self) -> None:
        self.calls = 0
        super().__init__(ToolSpec(name="search", description="search", input_schema=SCHEMA))

    def execute(self, args: dict[str, Any], runtime_context: Any = None) -> Any:
        self.calls += 1
        return {"query": args["query"]}


@pytest.mark.parametrize(
    ("args", "code"),
    [
        ([], "invalid_arguments_shape"),
        ({"limit": 1}, "missing_required_argument"),
        ({"query": 7}, "invalid_argument_type"),
        ({"query": "x", "extra": True}, "unexpected_argument"),
        ({"query": "x", "options": {"literal": "yes"}}, "invalid_argument_type"),
    ],
)
def test_structural_schema_gate_rejects_invalid_json(args: Any, code: str) -> None:
    result = validate_tool_arguments(args, SCHEMA)
    assert result.valid is False
    assert result.code == code


def test_action_executor_structural_gate_runs_before_tool_code() -> None:
    tool = _RecordingTool()
    executor = ActionExecutor(ToolRegistry().register(tool))

    result = executor.execute([Action(name="search", args={"query": 7})])[0]

    assert result.status == ActionStatus.ERROR
    assert result.attempts == 0
    assert result.metadata["error_code"] == "invalid_argument_type"
    assert result.metadata["executed"] is False
    assert tool.calls == 0


def test_registry_standalone_call_uses_same_structural_gate() -> None:
    tool = _RecordingTool()
    registry = ToolRegistry().register(tool)

    with pytest.raises(ValueError, match="invalid_argument_type"):
        registry.call("search", query=7)

    assert tool.calls == 0
    assert registry.call("search", query="needle") == {"query": "needle"}
    registered = registry.get("search")
    assert isinstance(registered, _RecordingTool)
    assert registered.calls == 1
