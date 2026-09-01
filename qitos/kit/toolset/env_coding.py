"""Small coding toolset that can operate only through the configured Env."""

from __future__ import annotations

from typing import Any, Dict, Optional

from qitos.core.function_tool_decorator import function_tool
from qitos.kit.tool.toolset import BaseToolSet


def _ops(runtime_context: Optional[Dict[str, Any]], group: str) -> Any:
    context = runtime_context or {}
    env = context.get("env")
    if env is None:
        raise RuntimeError("configured Env is required")
    capability = dict(context.get("ops") or {}).get(group)
    if capability is None:
        raise RuntimeError(f"configured Env does not provide {group!r} operations")
    return capability


class EnvCodingToolSet(BaseToolSet):
    """Read, grep, edit, and test exclusively through one runtime Env."""

    name = "env_coding"
    version = "1"

    def tools(self) -> list[Any]:
        return [read_file, list_files, grep_file, write_file, run_command]


@function_tool(
    name="read_file",
    read_only=True,
    concurrency_safe=True,
    required_ops=["file"],
)
def read_file(
    path: str, runtime_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Read a UTF-8 text file from the configured workspace."""
    content = _ops(runtime_context, "file").read_text(path)
    return {"status": "success", "path": path, "content": content}


@function_tool(
    name="list_files",
    read_only=True,
    concurrency_safe=True,
    required_ops=["file"],
)
def list_files(
    path: str = ".",
    limit: int = 200,
    runtime_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """List files beneath a workspace-relative directory."""
    files = _ops(runtime_context, "file").list_files(path=path, limit=int(limit))
    return {"status": "success", "path": path, "files": files}


@function_tool(
    name="grep_file",
    read_only=True,
    concurrency_safe=True,
    required_ops=["process"],
)
def grep_file(
    query: str,
    path: str = ".",
    runtime_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Search workspace files with ripgrep inside the configured environment."""
    import shlex

    command = f"rg -n -- {shlex.quote(query)} {shlex.quote(path)}"
    return dict(_ops(runtime_context, "process").run(command, timeout=30))


@function_tool(
    name="write_file",
    needs_approval=False,
    required_ops=["file"],
)
def write_file(
    path: str,
    content: str,
    runtime_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Write a UTF-8 text file through the configured environment."""
    _ops(runtime_context, "file").write_text(path, content)
    return {"status": "success", "path": path, "size": len(content)}


@function_tool(
    name="run_command",
    needs_approval=False,
    required_ops=["process"],
)
def run_command(
    command: str,
    timeout: int = 30,
    runtime_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run a bounded command inside the configured environment."""
    return dict(
        _ops(runtime_context, "process").run(command, timeout=int(timeout))
    )


__all__ = ["EnvCodingToolSet"]
