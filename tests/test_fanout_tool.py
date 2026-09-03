"""Tests for FanOutTool, ContextStrategy integration, and depth propagation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qitos import (
    Action,
    AgentModule,
    AgentRegistry,
    AgentSpec,
    StateSchema,
    ToolRegistry,
)
from qitos.kit.tool.fanout import FanOutTool, MAX_DELEGATE_DEPTH
from qitos.engine.states import RuntimePhase


# ── Fixtures ─────────────────────────────────────────────────────────────


@dataclass
class DummyState(StateSchema):
    scratchpad: list[str] = field(default_factory=list)


class DummyAgent(AgentModule[DummyState, dict[str, Any], Action]):
    def __init__(self, name: str = "agent", final_answer: str = "done"):
        registry = ToolRegistry()
        super().__init__(tool_registry=registry)
        self.name = name
        self._final_answer = final_answer

    def init_state(self, task: str, **kwargs: Any) -> DummyState:
        return DummyState(task=task, max_steps=3)

    def reduce(self, state, observation, decision):
        return state


def _make_registry() -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(
        AgentSpec(name="worker", description="A test worker", agent=DummyAgent(final_answer="explored"))
    )
    return registry


# ── FanOutTool creation tests ────────────────────────────────────────────


class TestFanOutToolCreation:
    def test_get_fanout_tool_from_registry(self):
        registry = _make_registry()
        tool = registry.get_fanout_tool()
        assert isinstance(tool, FanOutTool)
        assert tool.name == "fanout"

    def test_fanout_tool_custom_workers(self):
        registry = _make_registry()
        tool = registry.get_fanout_tool(max_workers=8)
        assert tool._max_workers == 8

    def test_fanout_tool_registered_in_tool_registry(self):
        registry = _make_registry()
        tool = registry.get_fanout_tool()
        tool_reg = ToolRegistry()
        tool_reg.register(tool)
        assert tool_reg.resolve_name("fanout") == "fanout"

    def test_fanout_tool_spec_flags(self):
        registry = _make_registry()
        tool = registry.get_fanout_tool()
        assert tool.spec.concurrency_safe is not True
        assert tool.spec.supports_background is True


# ── FanOutTool execution tests ───────────────────────────────────────────


class TestFanOutToolExecution:
    def test_empty_tasks_returns_error(self):
        registry = _make_registry()
        tool = registry.get_fanout_tool()
        result = tool.execute({"tasks": []})
        assert result["status"] == "error"
        assert "tasks" in result["message"]

    def test_without_durable_runtime_is_typed_error(self):
        registry = _make_registry()
        tool = registry.get_fanout_tool()
        result = tool.execute(
            {"tasks": [{"agent": "worker", "task": "do something"}]},
            runtime_context={"delegate_depth": MAX_DELEGATE_DEPTH},
        )
        assert result["status"] == "error"
        assert result["error_code"] == "durable_work_runtime_unavailable"

    def test_missing_task_field(self):
        registry = _make_registry()
        tool = registry.get_fanout_tool()
        result = tool.execute(
            {"tasks": [{"agent": "worker"}]},
        )
        # Invalid task spec should produce error in results
        assert "invalid_0" in result.get("results", {}) or result["status"] == "error"

    def test_custom_per_task_timeout(self):
        """FanOutTool should accept custom per_task_timeout."""
        registry = _make_registry()
        tool = registry.get_fanout_tool(per_task_timeout=60.0)
        assert tool._per_task_timeout == 60.0


# ── RuntimePhase tests ────────────────────────────────────────────────────


class TestRuntimePhaseFanout:
    def test_fanout_phases_exist(self):
        assert RuntimePhase.FANOUT_START == "FANOUT_START"
        assert RuntimePhase.FANOUT_END == "FANOUT_END"
