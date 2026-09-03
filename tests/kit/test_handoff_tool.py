"""Tests for Handoff-as-Tool feature."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qitos.core.agent_module import AgentModule
from qitos.core.state import StateSchema
from qitos.core.tool_registry import ToolRegistry
from qitos.engine._handoff_runtime import compact_handoff_history
from qitos.kit.tool.handoff_tool import HandoffTool


@dataclass
class DummyState(StateSchema):
    task: str = ""


class DummyAgent(AgentModule[DummyState, Any, Any]):
    name = "dummy"
    handoff_targets = ["researcher", "coder"]

    def init_state(self, task: str, **kwargs: Any) -> DummyState:
        return DummyState(task=task)

    def reduce(self, state: DummyState, observation: Any, decision: Any) -> DummyState:
        return state


class TestHandoffTool:
    def test_tool_name_format(self):
        tool = HandoffTool("researcher", "Deep research analysis")
        assert tool.name == "transfer_to_researcher"

    def test_tool_description(self):
        tool = HandoffTool("researcher", "Deep research analysis")
        assert "researcher" in tool.spec.description
        assert "Deep research analysis" in tool.spec.description

    def test_tool_declares_durable_effect(self):
        tool = HandoffTool("researcher")
        assert tool.spec.read_only is False
        assert tool.spec.effect is not None

    def test_execute_without_runtime_returns_typed_error(self):
        tool = HandoffTool("researcher")
        result = tool.execute({"rationale": "Need deep research"})
        assert result["status"] == "error"
        assert result["error_code"] == "durable_work_runtime_unavailable"

    def test_input_filter_stored(self):
        def my_filter(history):
            return history[-5:]

        tool = HandoffTool("researcher", input_filter=my_filter)
        assert tool.input_filter is my_filter


class TestHandoffToolRegistration:
    def test_handoff_targets_attribute(self):
        agent = DummyAgent()
        assert agent.handoff_targets == ["researcher", "coder"]

    def test_no_handoff_targets_default(self):
        class NoHandoffAgent(AgentModule[DummyState, Any, Any]):
            name = "no_handoff"

            def init_state(self, task, **kwargs):
                return DummyState(task=task)

            def reduce(self, state, observation, decision):
                return state

        agent = NoHandoffAgent()
        assert agent.handoff_targets is None

    def test_engine_registers_handoff_tools(self):
        from qitos.engine.engine import Engine

        agent = DummyAgent()
        # Need a tool registry that can register
        registry = ToolRegistry()
        agent.tool_registry = registry
        Engine(agent)

        # Check that handoff tools were registered
        tool_names = registry.list_tools()
        assert "transfer_to_researcher" in tool_names
        assert "transfer_to_coder" in tool_names

    def test_engine_intercept_handoff_action(self):
        from qitos.core.action import Action
        from qitos.engine.engine import Engine

        agent = DummyAgent()
        registry = ToolRegistry()
        agent.tool_registry = registry
        engine = Engine(agent)

        action = Action(name="transfer_to_researcher", args={"rationale": "Need research"})
        result = engine._intercept_handoff_action(action)

        assert result is not None
        assert result.mode == "handoff"
        assert result.meta.get("handoff_target") == "researcher"

    def test_engine_no_intercept_for_normal_action(self):
        from qitos.core.action import Action
        from qitos.engine.engine import Engine

        agent = DummyAgent()
        registry = ToolRegistry()
        agent.tool_registry = registry
        engine = Engine(agent)

        action = Action(name="read_file", args={"path": "/tmp/test"})
        result = engine._intercept_handoff_action(action)
        assert result is None


class TestCompactHandoffHistory:
    def test_no_compaction_needed(self):
        items = [{"role": "user", "content": f"msg {i}"} for i in range(5)]
        result = compact_handoff_history(items, max_items=10)
        assert len(result) == 5

    def test_compaction_reduces_items(self):
        items = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
        result = compact_handoff_history(items, max_items=5)
        # Should be: 1 summary + 5 recent = 6
        assert len(result) == 6
        assert result[0]["role"] == "system"

    def test_compaction_preserves_recent(self):
        items = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
        result = compact_handoff_history(items, max_items=5)
        # Last 5 items should be intact
        assert result[-1]["content"] == "msg 19"
        assert result[-5]["content"] == "msg 15"

    def test_compaction_mixed_roles(self):
        items = []
        for i in range(12):
            items.append({"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"})
        result = compact_handoff_history(items, max_items=4)
        assert result[0]["role"] == "system"
        assert "user" in result[0]["content"]
        assert "assistant" in result[0]["content"]
