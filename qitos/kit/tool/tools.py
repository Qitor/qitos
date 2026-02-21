"""Tool registry builders backed by concrete tool implementations."""

from __future__ import annotations

from qitos.core.tool import tool
from qitos.core.tool_registry import ToolRegistry
from qitos.kit.tool.editor import EditorToolSet


def math_tools() -> ToolRegistry:
    registry = ToolRegistry()

    @tool(name="add")
    def add(a: int, b: int) -> int:
        return a + b

    @tool(name="multiply")
    def multiply(a: int, b: int) -> int:
        return a * b

    registry.register(add)
    registry.register(multiply)
    return registry


def editor_tools(workspace_root: str) -> ToolRegistry:
    registry = ToolRegistry()
    registry.include(EditorToolSet(workspace_root=workspace_root))
    return registry


__all__ = ["math_tools", "editor_tools"]
