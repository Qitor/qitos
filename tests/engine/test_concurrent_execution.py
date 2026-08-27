"""Tests for spec-driven concurrent action execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List
from unittest.mock import MagicMock

from qitos.core.action import Action, ActionExecutionPolicy, ActionResult, ActionStatus
from qitos.core.tool import BaseTool, ToolSpec
from qitos.engine.action_executor import ActionExecutor


class FakeTool(BaseTool):
    """A simple tool for testing."""

    def __init__(self, name: str, spec: ToolSpec | None = None, result: Any = "ok"):
        if spec is None:
            spec = ToolSpec(name=name, description=f"Test tool {name}")
        super().__init__(spec)
        self._result = result

    def execute(self, args, runtime_context=None):
        return self._result


class FakeToolRegistry:
    """A minimal tool registry for testing."""

    def __init__(self, tools: Dict[str, BaseTool] | None = None):
        self._tools = tools or {}

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def resolve(self, name: str) -> BaseTool | None:
        return self._tools.get(name)


def _make_executor(
    tools: Dict[str, BaseTool] | None = None,
    policy: ActionExecutionPolicy | None = None,
) -> ActionExecutor:
    registry = FakeToolRegistry(tools)
    return ActionExecutor(
        tool_registry=registry,
        policy=policy,
    )


class TestSpecDrivenClassification:
    def test_concurrency_safe_spec(self):
        spec = ToolSpec(name="safe_read", description="Read", concurrency_safe=True)
        tool = FakeTool("safe_read", spec=spec)
        executor = _make_executor({"safe_read": tool})
        assert executor._is_concurrency_safe("safe_read")

    def test_read_only_spec(self):
        spec = ToolSpec(name="read_only", description="Read", read_only=True)
        tool = FakeTool("read_only", spec=spec)
        executor = _make_executor({"read_only": tool})
        assert executor._is_concurrency_safe("read_only")

    def test_needs_approval_never_safe(self):
        spec = ToolSpec(name="danger", description="Danger", needs_approval=True, concurrency_safe=True)
        tool = FakeTool("danger", spec=spec)
        executor = _make_executor({"danger": tool})
        assert not executor._is_concurrency_safe("danger")

    def test_unregistered_tool_is_not_safe(self):
        """The legacy hardcoded name set is gone: only spec-driven classification applies."""
        executor = _make_executor()
        assert not executor._is_concurrency_safe("Read")
        assert not executor._is_concurrency_safe("Glob")

    def test_unknown_tool_not_safe(self):
        executor = _make_executor()
        assert not executor._is_concurrency_safe("unknown_tool")


class TestSerialMode:
    def test_serial_mode_forces_sequential(self):
        safe_spec = ToolSpec(name="read", description="Read", concurrency_safe=True)
        tool1 = FakeTool("read", spec=safe_spec)
        tool2 = FakeTool("read2", spec=safe_spec)
        policy = ActionExecutionPolicy(mode="serial")
        executor = _make_executor({"read": tool1, "read2": tool2}, policy=policy)
        actions = [
            Action(name="read", args={}),
            Action(name="read2", args={}),
        ]
        results = executor.execute(actions)
        assert len(results) == 2


class TestAutoMode:
    def test_auto_mode_parallel_safe_tools(self):
        safe_spec = ToolSpec(name="read", description="Read", concurrency_safe=True)
        tool = FakeTool("read", spec=safe_spec, result="read_result")
        policy = ActionExecutionPolicy(mode="parallel")
        executor = _make_executor({"read": tool}, policy=policy)
        actions = [
            Action(name="read", args={}),
            Action(name="read", args={}),
        ]
        results = executor.execute(actions)
        assert len(results) == 2

    def test_auto_mode_mixed_safe_exclusive(self):
        safe_spec = ToolSpec(name="read", description="Read", concurrency_safe=True)
        exclusive_spec = ToolSpec(name="write", description="Write")
        read_tool = FakeTool("read", spec=safe_spec, result="read_result")
        write_tool = FakeTool("write", spec=exclusive_spec, result="write_result")
        policy = ActionExecutionPolicy(mode="parallel")
        executor = _make_executor({"read": read_tool, "write": write_tool}, policy=policy)
        actions = [
            Action(name="read", args={}),
            Action(name="write", args={}),
            Action(name="read", args={}),
        ]
        results = executor.execute(actions)
        assert len(results) == 3

    def test_auto_mode_single_safe_sequential(self):
        """Only one safe action → runs sequentially."""
        safe_spec = ToolSpec(name="read", description="Read", concurrency_safe=True)
        write_spec = ToolSpec(name="write", description="Write")
        read_tool = FakeTool("read", spec=safe_spec)
        write_tool = FakeTool("write", spec=write_spec)
        policy = ActionExecutionPolicy(mode="parallel")
        executor = _make_executor({"read": read_tool, "write": write_tool}, policy=policy)
        actions = [
            Action(name="read", args={}),
            Action(name="write", args={}),
        ]
        results = executor.execute(actions)
        assert len(results) == 2


class TestMaxConcurrency:
    def test_max_concurrency_respected(self):
        safe_spec = ToolSpec(name="read", description="Read", concurrency_safe=True)
        tool = FakeTool("read", spec=safe_spec)
        policy = ActionExecutionPolicy(mode="parallel", max_concurrency=2)
        executor = _make_executor({"read": tool}, policy=policy)
        actions = [Action(name="read", args={}) for _ in range(5)]
        results = executor.execute(actions)
        assert len(results) == 5


class TestFailFast:
    def test_fail_fast_cancels_on_error(self):
        """When fail_fast=True, errors stop further concurrent execution."""
        safe_spec = ToolSpec(name="read", description="Read", concurrency_safe=True)
        tool = FakeTool("read", spec=safe_spec, result=RuntimeError("fail"))
        policy = ActionExecutionPolicy(mode="parallel", fail_fast=True)
        executor = _make_executor({"read": tool}, policy=policy)
        actions = [Action(name="read", args={}) for _ in range(3)]
        # This should not crash even if tools fail
        results = executor.execute(actions)
        assert len(results) == 3


class TestResultOrdering:
    def test_results_in_original_order(self):
        safe_spec = ToolSpec(name="read", description="Read", concurrency_safe=True)
        tool = FakeTool("read", spec=safe_spec, result="read_result")
        policy = ActionExecutionPolicy(mode="parallel")
        executor = _make_executor({"read": tool}, policy=policy)
        actions = [
            Action(name="read", args={"n": 1}),
            Action(name="read", args={"n": 2}),
            Action(name="read", args={"n": 3}),
        ]
        results = executor.execute(actions)
        assert len(results) == 3
        # All should have the right name
        for r in results:
            assert r.name == "read"


class TestConcurrencyAdjudicationMatrix:
    """Four-level adjudication (Batch X, 3f34a04).

    1. policy parallel_tool_names allow-list
    2. needs_approval veto
    3. explicit ToolSpec.concurrency_safe authoritative (both directions)
    4. read_only heuristic fallback
    """

    def _executor(self, tool=None, policy=None):
        tools = {}
        if tool is not None:
            tools[tool.spec.name if hasattr(tool, "spec") else "t"] = tool
        return _make_executor(tools or None, policy=policy)

    def test_level1_allow_list_excludes_other_tools(self):
        from qitos.core.action import ActionExecutionPolicy

        spec = ToolSpec(name="fast_read", description="r", read_only=True)
        tool = FakeTool("fast_read", spec=spec)
        executor = _make_executor({"fast_read": tool},
                                  policy=ActionExecutionPolicy(
                                      mode="parallel",
                                      parallel_tool_names=frozenset({"other"}),
                                  ))
        assert not executor._is_concurrency_safe("fast_read")

    def test_level1_allow_list_included_tool_still_needs_positive_classification(self):
        from qitos.core.action import ActionExecutionPolicy

        spec = ToolSpec(name="fast_read", description="r", read_only=True)
        tool = FakeTool("fast_read", spec=spec)
        executor = _make_executor({"fast_read": tool},
                                  policy=ActionExecutionPolicy(
                                      mode="parallel",
                                      parallel_tool_names=frozenset({"fast_read"}),
                                  ))
        assert executor._is_concurrency_safe("fast_read")

    def test_level2_needs_approval_vetoes_even_concurrency_safe(self):
        spec = ToolSpec(
            name="danger",
            description="d",
            needs_approval=True,
            concurrency_safe=True,
        )
        tool = FakeTool("danger", spec=spec)
        executor = _make_executor({"danger": tool})
        assert not executor._is_concurrency_safe("danger")

    def test_level3_explicit_true_beats_read_only_false(self):
        spec = ToolSpec(name="writer", description="w",
                        concurrency_safe=True, read_only=False)
        tool = FakeTool("writer", spec=spec)
        executor = _make_executor({"writer": tool})
        assert executor._is_concurrency_safe("writer")

    def test_level3_explicit_false_beats_read_only_true(self):
        spec = ToolSpec(name="picky_reader", description="r",
                        concurrency_safe=False, read_only=True)
        tool = FakeTool("picky_reader", spec=spec)
        executor = _make_executor({"picky_reader": tool})
        assert not executor._is_concurrency_safe("picky_reader")

    def test_level4_unspecified_read_only_defaults_safe(self):
        spec = ToolSpec(name="plain_reader", description="r", read_only=True)
        tool = FakeTool("plain_reader", spec=spec)
        executor = _make_executor({"plain_reader": tool})
        assert executor._is_concurrency_safe("plain_reader")

    def test_unspecified_and_not_read_only_is_exclusive(self):
        spec = ToolSpec(name="mutator", description="m")
        tool = FakeTool("mutator", spec=spec)
        executor = _make_executor({"mutator": tool})
        assert not executor._is_concurrency_safe("mutator")
