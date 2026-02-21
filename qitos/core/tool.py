"""Tool abstraction and decorator for QitOS kernel."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ToolPermission:
    filesystem_read: bool = False
    filesystem_write: bool = False
    network: bool = False
    command: bool = False


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    required: List[str] = field(default_factory=list)
    timeout_s: Optional[float] = None
    max_retries: int = 0
    permissions: ToolPermission = field(default_factory=ToolPermission)
    required_ops: List[str] = field(default_factory=list)


@dataclass
class ToolMeta:
    name: Optional[str] = None
    description: Optional[str] = None
    timeout_s: Optional[float] = None
    max_retries: int = 0
    permissions: ToolPermission = field(default_factory=ToolPermission)
    required_ops: List[str] = field(default_factory=list)


class BaseTool:
    """Base abstraction for callable tools."""

    def __init__(self, spec: ToolSpec):
        self.spec = spec

    @property
    def name(self) -> str:
        return self.spec.name

    def run(self, **kwargs: Any) -> Any:  # pragma: no cover - interface
        raise NotImplementedError

    def execute(self, args: Dict[str, Any], runtime_context: Optional[Dict[str, Any]] = None) -> Any:
        """Execute tool with optional runtime context."""
        sig = inspect.signature(self.run)
        call_args = dict(args)
        if "runtime_context" in sig.parameters:
            call_args["runtime_context"] = runtime_context or {}
        return self.run(**call_args)

    def __call__(self, **kwargs: Any) -> Any:
        return self.run(**kwargs)


class FunctionTool(BaseTool):
    """Tool wrapper around callable functions or bound methods."""

    def __init__(self, func: Callable[..., Any], meta: Optional[ToolMeta] = None):
        self.func = func
        self.meta = meta or get_tool_meta(func) or ToolMeta()
        spec = build_tool_spec(func, self.meta)
        super().__init__(spec)

    def run(self, **kwargs: Any) -> Any:
        return self.func(**kwargs)

    def execute(self, args: Dict[str, Any], runtime_context: Optional[Dict[str, Any]] = None) -> Any:
        runtime_context = runtime_context or {}
        env = runtime_context.get("env")
        ops = runtime_context.get("ops", {})
        sig = inspect.signature(self.func)
        call_kwargs = dict(args)
        if "runtime_context" in sig.parameters:
            call_kwargs["runtime_context"] = runtime_context
        if "env" in sig.parameters:
            call_kwargs["env"] = env
        if "ops" in sig.parameters:
            call_kwargs["ops"] = ops
        if "file_ops" in sig.parameters and "file" in ops:
            call_kwargs["file_ops"] = ops["file"]
        if "process_ops" in sig.parameters and "process" in ops:
            call_kwargs["process_ops"] = ops["process"]
        return self.func(**call_kwargs)


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    timeout_s: Optional[float] = None,
    max_retries: int = 0,
    permissions: Optional[ToolPermission] = None,
    required_ops: Optional[List[str]] = None,
):
    """Decorator that marks a callable as a QitOS tool without changing binding semantics."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        meta = ToolMeta(
            name=name,
            description=description,
            timeout_s=timeout_s,
            max_retries=max_retries,
            permissions=permissions or ToolPermission(),
            required_ops=list(required_ops or []),
        )
        setattr(func, "__qitos_tool_meta__", meta)
        setattr(func, "_is_tool", True)
        return func

    return decorator


def get_tool_meta(func: Callable[..., Any]) -> Optional[ToolMeta]:
    if hasattr(func, "__qitos_tool_meta__"):
        return getattr(func, "__qitos_tool_meta__")

    underlying = getattr(func, "__func__", None)
    if underlying is not None and hasattr(underlying, "__qitos_tool_meta__"):
        return getattr(underlying, "__qitos_tool_meta__")

    return None


def build_tool_spec(func: Callable[..., Any], meta: ToolMeta) -> ToolSpec:
    sig = inspect.signature(func)
    params = {}
    required = []

    for name, p in sig.parameters.items():
        if name in {"self", "cls"}:
            continue
        params[name] = {"type": _type_to_json(p.annotation), "description": ""}
        if p.default is inspect.Parameter.empty:
            required.append(name)

    desc = meta.description or (inspect.getdoc(func) or "")
    tool_name = meta.name or getattr(func, "__name__", "tool")

    return ToolSpec(
        name=tool_name,
        description=desc.splitlines()[0] if desc else "",
        parameters=params,
        required=required,
        timeout_s=meta.timeout_s,
        max_retries=meta.max_retries,
        permissions=meta.permissions,
        required_ops=list(meta.required_ops),
    )


def _type_to_json(annotation: Any) -> str:
    mapping = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        dict: "object",
        list: "array",
    }
    return mapping.get(annotation, "any")
