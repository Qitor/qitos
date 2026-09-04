"""Integration tests for needs_approval and read_only markers in the Engine loop."""
from __future__ import annotations

from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from qitos import AgentModule, StateSchema
from qitos.core.action import Action, ActionStatus
from qitos.core.function_tool_decorator import function_tool
from qitos.core.tool_registry import ToolRegistry
from qitos.engine.action_executor import ActionExecutor
from qitos.engine.engine import Engine
from qitos.engine.interrupt import EngineInterrupt


# --- Test tools ---


class _TestToolSet:
    """Minimal toolset with both needs_approval and read_only tools."""

    name = "test_integration"
    version = "1"

    def setup(self, context):
        pass

    def teardown(self, context):
        pass

    def tools(self):
        return [
            self.read_only_tool,
            self.needs_approval_tool,
            self.both_markers_tool,
            self.no_marker_tool,
        ]

    @function_tool(
        name="read_only_query",
        description="A read-only tool",
        read_only=True,
    )
    def read_only_tool(self, query: str) -> Dict[str, Any]:
        return {"status": "ok", "query": query}

    @function_tool(
        name="approval_action",
        description="An action requiring approval",
        needs_approval=True,
    )
    def needs_approval_tool(self, command: str) -> Dict[str, Any]:
        return {"status": "executed", "command": command}

    @function_tool(
        name="read_and_approve",
        description="Read-only but needs approval",
        read_only=True,
        needs_approval=True,
    )
    def both_markers_tool(self, path: str) -> Dict[str, Any]:
        return {"status": "ok", "path": path}

    @function_tool(
        name="basic_tool",
        description="A basic tool without markers",
    )
    def no_marker_tool(self, value: str) -> Dict[str, Any]:
        return {"status": "ok", "value": value}


# --- Test agent ---


class _TestAgent(AgentModule):
    """Minimal agent for integration testing."""

    name = "test_integration_agent"

    def __init__(self, *, llm=None, auto_approve=False):
        ts = _TestToolSet()
        registry = ToolRegistry().register_toolset(ts, namespace="")
        super().__init__(tool_registry=registry, llm=llm)
        self._auto_approve = auto_approve

    def init_state(self, task, **kwargs):
        return StateSchema(task=task, max_steps=kwargs.get("max_steps", 5))

    def build_system_prompt(self, state):
        return "You are a test agent."

    def prepare(self, state):
        return f"Task: {state.task}"

    def reduce(self, state, observation, decision):
        return state


# --- Tests ---


class TestNeedsApproval:
    """Tests for needs_approval marker in ActionExecutor."""

    def test_needs_approval_raises_interrupt(self):
        """ActionExecutor._execute_one raises EngineInterrupt for needs_approval=True tools."""
        ts = _TestToolSet()
        registry = ToolRegistry().register_toolset(ts, namespace="")
        executor = ActionExecutor(tool_registry=registry, auto_approve=False)

        action = Action(name="approval_action", args={"command": "rm -rf /"}, kind="tool")
        with pytest.raises(EngineInterrupt):
            executor._execute_one(action)

    def test_needs_approval_auto_approve_skips_interrupt(self):
        """With auto_approve=True, needs_approval tools execute without interrupt."""
        ts = _TestToolSet()
        registry = ToolRegistry().register_toolset(ts, namespace="")
        executor = ActionExecutor(tool_registry=registry, auto_approve=True)

        action = Action(name="approval_action", args={"command": "echo hello"}, kind="tool")
        result = executor._execute_one(action)
        assert result.status == ActionStatus.SUCCESS

    def test_both_markers_triggers_interrupt(self):
        """A tool with both read_only and needs_approval still triggers interrupt."""
        ts = _TestToolSet()
        registry = ToolRegistry().register_toolset(ts, namespace="")
        executor = ActionExecutor(tool_registry=registry, auto_approve=False)

        action = Action(name="read_and_approve", args={"path": "/etc/passwd"}, kind="tool")
        with pytest.raises(EngineInterrupt):
            executor._execute_one(action)


class TestReadOnly:
    """Tests for read_only marker in ActionExecutor."""

    def test_read_only_tool_no_interrupt(self):
        """A read_only tool (without needs_approval) does not trigger interrupt."""
        ts = _TestToolSet()
        registry = ToolRegistry().register_toolset(ts, namespace="")
        executor = ActionExecutor(tool_registry=registry, auto_approve=False)

        action = Action(name="read_only_query", args={"query": "test"}, kind="tool")
        result = executor._execute_one(action)
        assert result.status == ActionStatus.SUCCESS

    def test_read_only_tool_is_concurrency_safe(self):
        """A tool with read_only=True is classified as concurrency-safe."""
        ts = _TestToolSet()
        registry = ToolRegistry().register_toolset(ts, namespace="")
        executor = ActionExecutor(tool_registry=registry)
        assert executor._is_concurrency_safe("read_only_query") is True

    def test_needs_approval_tool_is_not_concurrency_safe(self):
        """A tool with needs_approval=True is NOT concurrency-safe."""
        ts = _TestToolSet()
        registry = ToolRegistry().register_toolset(ts, namespace="")
        executor = ActionExecutor(tool_registry=registry)
        assert executor._is_concurrency_safe("approval_action") is False

    def test_both_markers_not_concurrency_safe(self):
        """A tool with both markers is NOT concurrency-safe (needs_approval wins)."""
        ts = _TestToolSet()
        registry = ToolRegistry().register_toolset(ts, namespace="")
        executor = ActionExecutor(tool_registry=registry)
        assert executor._is_concurrency_safe("read_and_approve") is False

    def test_no_marker_tool_default(self):
        """A tool without markers is not concurrency-safe and doesn't trigger interrupt."""
        ts = _TestToolSet()
        registry = ToolRegistry().register_toolset(ts, namespace="")
        executor = ActionExecutor(tool_registry=registry)

        # Not concurrency-safe (no read_only)
        assert executor._is_concurrency_safe("basic_tool") is False

        # No needs_approval → no interrupt
        action = Action(name="basic_tool", args={"value": "test"}, kind="tool")
        result = executor._execute_one(action)
        assert result.status == ActionStatus.SUCCESS


class TestEngineIntegration:
    """End-to-end tests with Engine loop."""

    def test_needs_approval_in_engine_loop(self):
        """Approval interruption stops without spending a second model request."""
        from examples._support import SequenceModel

        outputs = [
            'Thought: do it\nAction: approval_action(command="echo hello")',
            "Final Answer: Done.",
        ]
        llm = SequenceModel(outputs)
        agent = _TestAgent(llm=llm, auto_approve=False)
        engine = Engine(agent=agent, auto_approve=False)
        result = engine.run("test", max_steps=5, return_state=True)
        assert result.state.stop_reason == "interrupt"
        assert result.step_count == 1

    def test_auto_approve_in_engine_loop(self):
        """With auto_approve=True, needs_approval tools execute normally."""
        from examples._support import SequenceModel

        outputs = [
            'Thought: do it\nAction: approval_action(command="echo hello")',
            "Final Answer: Done.",
        ]
        llm = SequenceModel(outputs)
        agent = _TestAgent(llm=llm, auto_approve=True)
        engine = Engine(agent=agent, auto_approve=True)
        result = engine.run("test", max_steps=3, return_state=True)
        assert result.state.stop_reason == "final"

    def test_read_only_tool_executes_normally(self):
        """A read_only tool (without needs_approval) runs without interrupt."""
        from examples._support import SequenceModel

        outputs = [
            'Thought: query\nAction: read_only_query(query="test")',
            "Final Answer: Found it.",
        ]
        llm = SequenceModel(outputs)
        agent = _TestAgent(llm=llm, auto_approve=False)
        engine = Engine(agent=agent, auto_approve=False)
        result = engine.run("test", max_steps=3, return_state=True)
        assert result.state.stop_reason == "final"


class TestSpecMarkers:
    """Tests that FunctionTool spec markers are correctly set."""

    def test_all_markers_preserved(self):
        ts = _TestToolSet()
        tools = ts.tools()
        tool_map = {t.spec.name: t for t in tools}

        assert tool_map["read_only_query"].spec.read_only is True
        assert tool_map["read_only_query"].spec.needs_approval is False

        assert tool_map["approval_action"].spec.read_only is False
        assert tool_map["approval_action"].spec.needs_approval is True

        assert tool_map["read_and_approve"].spec.read_only is True
        assert tool_map["read_and_approve"].spec.needs_approval is True

        assert tool_map["basic_tool"].spec.read_only is False
        assert tool_map["basic_tool"].spec.needs_approval is False
