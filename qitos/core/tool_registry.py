"""Canonical tool registry with function and ToolSet support."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .tool import BaseTool, FunctionTool, ToolMeta, get_tool_meta


@dataclass
class ToolOrigin:
    source: str  # function | toolset
    toolset_name: Optional[str] = None
    toolset_version: Optional[str] = None


class ToolRegistry:
    """Registry for function tools, bound methods, tool objects, and ToolSets."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._origins: Dict[str, ToolOrigin] = {}
        self._toolsets: List[Any] = []
        self._setup_done: bool = False

    def register(self, item: Any, name: Optional[str] = None, meta: Optional[ToolMeta] = None) -> "ToolRegistry":
        tool_obj = self._to_tool(item, meta=meta)
        resolved_name = name or getattr(item, "name", None) or getattr(item, "_name", None)
        if resolved_name:
            tool_obj.spec.name = str(resolved_name)
        self._register_tool_object(tool_obj, origin=ToolOrigin(source="function"))
        return self

    def register_toolset(self, toolset: Any, namespace: Optional[str] = None) -> "ToolRegistry":
        if not hasattr(toolset, "tools"):
            raise TypeError("register_toolset() expects an object with tools()")

        toolset_name = str(getattr(toolset, "name", toolset.__class__.__name__.lower()))
        toolset_version = str(getattr(toolset, "version", "0"))
        prefix = namespace if namespace is not None else toolset_name

        if toolset not in self._toolsets:
            self._toolsets.append(toolset)

        for item in toolset.tools():
            tool_obj = self._to_tool(item)
            base_name = tool_obj.spec.name
            full_name = f"{prefix}.{base_name}" if prefix else base_name
            tool_obj.spec.name = full_name
            self._register_tool_object(
                tool_obj,
                origin=ToolOrigin(source="toolset", toolset_name=toolset_name, toolset_version=toolset_version),
            )

        return self

    def include(self, obj: Any) -> "ToolRegistry":
        for attr_name in dir(obj):
            if attr_name.startswith("_"):
                continue
            attr = getattr(obj, attr_name)
            if not callable(attr):
                continue

            meta = get_tool_meta(attr)
            if meta is not None:
                self.register(attr, meta=meta)
                continue

            underlying = getattr(attr, "__func__", None)
            is_legacy_skill = (
                (hasattr(attr, "_is_skill") and getattr(attr, "_is_skill"))
                or (underlying is not None and hasattr(underlying, "_is_skill") and getattr(underlying, "_is_skill"))
            )
            if is_legacy_skill:
                skill_name = getattr(attr, "_name", None) or (
                    getattr(underlying, "_name", None) if underlying is not None else None
                )
                self.register(attr, name=skill_name)

        return self

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        return sorted(self._tools.keys())

    def list_toolsets(self) -> List[str]:
        names: List[str] = []
        for toolset in self._toolsets:
            names.append(str(getattr(toolset, "name", toolset.__class__.__name__.lower())))
        return names

    def describe_tool(self, name: str) -> Dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError(f"Tool '{name}' not found")
        origin = self._origins.get(name, ToolOrigin(source="function"))
        return {
            "name": tool.name,
            "description": tool.spec.description,
            "origin": {
                "source": origin.source,
                "toolset_name": origin.toolset_name,
                "toolset_version": origin.toolset_version,
            },
        }

    def call(self, name: str, **kwargs: Any) -> Any:
        tool = self.get(name)
        if tool is None:
            raise ValueError(f"Tool '{name}' not found")
        return tool(**kwargs)

    def setup(self, context: Optional[Dict[str, Any]] = None) -> None:
        if self._setup_done:
            return
        payload = context or {}
        for toolset in self._toolsets:
            if hasattr(toolset, "setup"):
                toolset.setup(payload)
        self._setup_done = True

    def teardown(self, context: Optional[Dict[str, Any]] = None) -> None:
        payload = context or {}
        for toolset in reversed(self._toolsets):
            if hasattr(toolset, "teardown"):
                toolset.teardown(payload)
        self._setup_done = False

    def get_tool_descriptions(self) -> str:
        lines: List[str] = []
        for name in self.list_tools():
            tool = self._tools[name]
            origin = self._origins.get(name, ToolOrigin(source="function"))
            lines.append(f"## {tool.name}")
            lines.append(f"Description: {tool.spec.description}")
            lines.append(f"Source: {origin.source}")
            if origin.toolset_name:
                lines.append(f"ToolSet: {origin.toolset_name}@{origin.toolset_version}")
            lines.append("Parameters:")
            for param, p_spec in tool.spec.parameters.items():
                t = p_spec.get("type", "any")
                lines.append(f"  - {param} ({t})")
            lines.append("")
        return "\n".join(lines)

    def get_all_specs(self) -> List[Dict[str, Any]]:
        specs = []
        for name in self.list_tools():
            tool = self._tools[name]
            origin = self._origins.get(name, ToolOrigin(source="function"))
            specs.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.spec.name,
                        "description": tool.spec.description,
                        "parameters": {
                            "type": "object",
                            "properties": tool.spec.parameters,
                            "required": tool.spec.required,
                        },
                    },
                    "origin": {
                        "source": origin.source,
                        "toolset_name": origin.toolset_name,
                        "toolset_version": origin.toolset_version,
                    },
                    "permissions": {
                        "filesystem_read": tool.spec.permissions.filesystem_read,
                        "filesystem_write": tool.spec.permissions.filesystem_write,
                        "network": tool.spec.permissions.network,
                        "command": tool.spec.permissions.command,
                    },
                }
            )
        return specs

    def _to_tool(self, item: Any, meta: Optional[ToolMeta] = None) -> BaseTool:
        if isinstance(item, BaseTool):
            return item
        if callable(item):
            return FunctionTool(item, meta=meta or get_tool_meta(item))
        raise TypeError("register() expects BaseTool or callable")

    def _register_tool_object(self, tool_obj: BaseTool, origin: ToolOrigin) -> None:
        if tool_obj.name in self._tools:
            raise ValueError(f"Tool name collision: '{tool_obj.name}'")
        self._tools[tool_obj.name] = tool_obj
        self._origins[tool_obj.name] = origin

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)


__all__ = ["ToolOrigin", "ToolRegistry"]
