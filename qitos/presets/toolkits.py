"""Toolkit presets."""

from __future__ import annotations

from qitos import ToolRegistry, tool
from qitos.skills.editor import EditorSkill


def math_toolkit() -> ToolRegistry:
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


def editor_toolkit(workspace_root: str) -> ToolRegistry:
    registry = ToolRegistry()
    registry.include(EditorSkill(workspace_root=workspace_root))
    return registry


__all__ = ["math_toolkit", "editor_toolkit"]
