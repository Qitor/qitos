from __future__ import annotations

from typing import Any

import pytest

from qitos.core.action import Action, ActionStatus
from qitos.core.interceptor import InterceptorChain, InterceptorContext, ToolInterceptor
from qitos.core.tool import (
    BaseTool,
    ToolPermissionDecision,
    ToolSpec,
    validate_tool_arguments,
)
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


class _BoundaryRecordingTool(_RecordingTool):
    def __init__(self) -> None:
        super().__init__()
        self.permission_calls = 0

    def check_permissions(
        self, args: dict[str, Any], runtime_context: Any = None
    ) -> ToolPermissionDecision:
        _ = args, runtime_context
        self.permission_calls += 1
        return ToolPermissionDecision.allow()


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


@pytest.mark.parametrize(
    "args",
    [
        {"value": object()},
        {"value": [object()]},
        {"value": float("nan")},
        {"value": float("inf")},
        {"value": float("-inf")},
        {1: "non-string-key"},
    ],
)
def test_recursive_json_gate_rejects_values_before_schema_matching(
    args: dict[Any, Any],
) -> None:
    result = validate_tool_arguments(
        args,
        {"type": "object", "additionalProperties": True},
    )

    assert result.valid is False
    assert result.code == "invalid_json_value"


class _CountingInterceptor(ToolInterceptor):
    def __init__(self) -> None:
        self.calls = 0

    def before_execute(self, action: Action, context: InterceptorContext) -> Action:
        _ = context
        self.calls += 1
        return action

    def after_execute(
        self, action: Action, result: Any, context: InterceptorContext
    ) -> Any:
        _ = action, context
        return result


class _CountingPermissionPipeline:
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, **kwargs: Any) -> ToolPermissionDecision:
        _ = kwargs
        self.calls += 1
        return ToolPermissionDecision.allow()


def test_non_json_executor_args_fail_before_interceptor_permission_and_tool() -> None:
    tool = _BoundaryRecordingTool()
    interceptor = _CountingInterceptor()
    pipeline = _CountingPermissionPipeline()
    executor = ActionExecutor(
        ToolRegistry().register(tool),
        interceptor_chain=InterceptorChain([interceptor]),
        permission_pipeline=pipeline,
    )

    result = executor.execute(
        [Action(name="search", args={"query": "x", "extra": float("nan")})]
    )[0]

    assert result.status == ActionStatus.ERROR
    assert result.attempts == 0
    assert result.metadata["error_code"] == "invalid_json_value"
    assert interceptor.calls == 0
    assert pipeline.calls == 0
    assert tool.permission_calls == 0
    assert tool.calls == 0


def test_non_json_registry_args_fail_before_permission_and_tool() -> None:
    tool = _BoundaryRecordingTool()
    tool.spec.input_schema = {"type": "object", "additionalProperties": True}
    registry = ToolRegistry().register(tool)

    with pytest.raises(ValueError, match="invalid_json_value"):
        registry.call("search", value={"nested": [object()]})

    assert tool.permission_calls == 0
    assert tool.calls == 0


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


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "mystery"},
        {"type": "any"},
        {"type": "object", "required": "query", "properties": {}},
        {"type": "object", "properties": []},
        {"type": "object", "properties": {"query": {"type": "array", "items": []}}},
        {"type": "object", "anyOf": [{"type": "object"}, "invalid"]},
        {"type": "object", "oneOf": []},
        {"type": "object", "enum": [object()]},
        {"type": "object", "minimum": 1},
    ],
)
def test_malformed_schema_fails_closed_with_distinct_code(schema: dict[str, Any]) -> None:
    result = validate_tool_arguments({}, schema)

    assert result.valid is False
    assert result.code == "schema_contract_violation"


def test_malformed_schema_is_rejected_before_tool_execution() -> None:
    tool = _RecordingTool()
    tool.spec.input_schema = {
        "type": "object",
        "properties": {"query": {"type": "unknown"}},
    }
    executor = ActionExecutor(ToolRegistry().register(tool))

    result = executor.execute([Action(name="search", args={"query": "x"})])[0]

    assert result.status == ActionStatus.ERROR
    assert result.attempts == 0
    assert result.metadata["error_code"] == "schema_contract_violation"
    assert result.metadata["executed"] is False
    assert tool.calls == 0


@pytest.mark.parametrize(
    ("value", "valid", "code"),
    [
        ("fast", True, ""),
        ("slow", False, "invalid_argument_value"),
        (None, True, ""),
    ],
)
def test_repository_enum_and_nullable_shapes(
    value: Any, valid: bool, code: str
) -> None:
    schema = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["fast", "safe"], "nullable": True}
        },
        "required": ["mode"],
    }

    result = validate_tool_arguments({"mode": value}, schema)

    assert result.valid is valid
    assert result.code == code


def test_nested_arrays_additional_schema_and_variants_are_supported() -> None:
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "value": {
                            "anyOf": [{"type": "string"}, {"type": "integer"}]
                        }
                    },
                    "required": ["value"],
                    "additionalProperties": False,
                },
            }
        },
        "additionalProperties": {"type": "string"},
    }

    assert validate_tool_arguments(
        {"items": [{"value": 1}, {"value": "x"}], "label": "ok"}, schema
    ).valid
    assert validate_tool_arguments(
        {"items": [{"value": False}]}, schema
    ).code == "invalid_argument_type"
    assert validate_tool_arguments(
        {"items": [], "label": 7}, schema
    ).code == "invalid_argument_type"


def test_one_of_requires_exactly_one_matching_variant() -> None:
    schema = {
        "type": "object",
        "properties": {
            "value": {
                "oneOf": [{"type": "integer"}, {"type": "number"}]
            }
        },
        "required": ["value"],
    }

    assert validate_tool_arguments({"value": 1.5}, schema).valid
    assert validate_tool_arguments(
        {"value": 1}, schema
    ).code == "invalid_argument_type"


class _InvalidatingInterceptor(ToolInterceptor):
    def before_execute(self, action: Action, context: InterceptorContext) -> Action:
        _ = context
        return Action(name=action.name, args={"query": 7})

    def after_execute(self, action: Action, result: Any, context: InterceptorContext) -> Any:
        _ = action, context
        return result


class _InvalidatingPermissionPipeline:
    def evaluate(self, **kwargs: Any) -> ToolPermissionDecision:
        _ = kwargs
        return ToolPermissionDecision.allow(updated_args={"query": 7})


def test_interceptor_cannot_bypass_final_structure_gate() -> None:
    tool = _RecordingTool()
    executor = ActionExecutor(
        ToolRegistry().register(tool),
        interceptor_chain=InterceptorChain([_InvalidatingInterceptor()]),
    )

    result = executor.execute([Action(name="search", args={"query": "valid"})])[0]

    assert result.status == ActionStatus.ERROR
    assert result.metadata["error_category"] == "invalid_argument_type"
    assert tool.calls == 0


def test_permission_pipeline_cannot_bypass_final_structure_gate() -> None:
    tool = _RecordingTool()
    executor = ActionExecutor(
        ToolRegistry().register(tool),
        permission_pipeline=_InvalidatingPermissionPipeline(),
    )

    result = executor.execute([Action(name="search", args={"query": "valid"})])[0]

    assert result.status == ActionStatus.ERROR
    assert result.metadata["validation"]["boundary"] == "final_structural"
    assert result.metadata["error_category"] == "invalid_argument_type"
    assert tool.calls == 0


class _RegistryPermissionTool(_RecordingTool):
    def check_permissions(
        self, args: dict[str, Any], runtime_context: Any = None
    ) -> ToolPermissionDecision:
        _ = args, runtime_context
        return ToolPermissionDecision.allow(updated_args={"query": 7})


def test_registry_permission_update_cannot_bypass_final_structure_gate() -> None:
    tool = _RegistryPermissionTool()
    registry = ToolRegistry().register(tool)

    with pytest.raises(ValueError, match="invalid_argument_type"):
        registry.call("search", query="valid")

    assert tool.calls == 0
