"""Small coding toolset that can operate only through the configured Env."""

from __future__ import annotations

from typing import Any, Dict, Optional

from qitos.core.function_tool_decorator import function_tool
from qitos.core.tool_result import ToolResult
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


_MODEL_TEXT_LIMIT = 16_000
_FILE_LIST_LIMIT = 200
_COMMAND_TIMEOUT_LIMIT = 180


def _bounded_text(value: Any, *, limit: int = _MODEL_TEXT_LIMIT) -> tuple[str, int]:
    text = str(value or "")
    if len(text) <= limit:
        return text, 0
    marker = "...[TRUNCATED]"
    kept = max(0, limit - len(marker))
    return text[:kept] + marker, len(text) - kept


def _bounded_command_result(raw: Dict[str, Any]) -> tuple[Dict[str, Any], int]:
    projected = dict(raw)
    omitted = 0
    for key in ("stdout", "stderr", "output", "content"):
        if key in projected:
            projected[key], count = _bounded_text(projected[key])
            omitted += count
    return projected, omitted


def _tool_result(
    *,
    output: Dict[str, Any],
    model_output: Dict[str, Any],
    tool_name: str,
    omitted_characters: int = 0,
) -> ToolResult:
    return ToolResult(
        output=output,
        model_output=model_output,
        tool_name=tool_name,
        truncated=omitted_characters > 0,
        omitted={"model_output_characters": omitted_characters},
    )


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
) -> ToolResult:
    """Read a UTF-8 text file from the configured workspace."""
    content = _ops(runtime_context, "file").read_text(path)
    bounded, omitted = _bounded_text(content)
    return _tool_result(
        output={"status": "success", "path": path, "content": content},
        model_output={
            "status": "success",
            "content": bounded,
            "loss_receipt": {
                "truncated": omitted > 0,
                "omitted_characters": omitted,
            },
        },
        tool_name="read_file",
        omitted_characters=omitted,
    )


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
) -> ToolResult:
    """List files beneath a workspace-relative directory."""
    applied_limit = min(_FILE_LIST_LIMIT, max(1, int(limit)))
    files = _ops(runtime_context, "file").list_files(
        path=path, limit=applied_limit
    )
    output = {"status": "success", "path": path, "files": files}
    return _tool_result(
        output=output,
        model_output={
            "status": "success",
            "files": list(files)[:applied_limit],
            "selection_receipt": {
                "requested_limit": int(limit),
                "applied_limit": applied_limit,
            },
        },
        tool_name="list_files",
    )


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
) -> ToolResult:
    """Search workspace files with ripgrep inside the configured environment."""
    import shlex

    command = f"rg -n -- {shlex.quote(query)} {shlex.quote(path)}"
    raw = dict(_ops(runtime_context, "process").run(command, timeout=30))
    projected, omitted = _bounded_command_result(raw)
    projected["loss_receipt"] = {
        "truncated": omitted > 0,
        "omitted_characters": omitted,
    }
    return _tool_result(
        output=raw,
        model_output=projected,
        tool_name="grep_file",
        omitted_characters=omitted,
    )


@function_tool(
    name="write_file",
    needs_approval=False,
    required_ops=["file"],
)
def write_file(
    path: str,
    content: str,
    runtime_context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Write a UTF-8 text file through the configured environment."""
    _ops(runtime_context, "file").write_text(path, content)
    output = {"status": "success", "path": path, "size": len(content)}
    return _tool_result(
        output=output,
        model_output={"status": "success", "size": len(content)},
        tool_name="write_file",
    )


@function_tool(
    name="run_command",
    needs_approval=False,
    required_ops=["process"],
)
def run_command(
    command: str,
    timeout: int = 30,
    runtime_context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Run a bounded command inside the configured environment."""
    applied_timeout = min(_COMMAND_TIMEOUT_LIMIT, max(1, int(timeout)))
    raw = dict(
        _ops(runtime_context, "process").run(
            command, timeout=applied_timeout
        )
    )
    projected, omitted = _bounded_command_result(raw)
    projected["execution_receipt"] = {
        "timeout_seconds": applied_timeout,
        "truncated": omitted > 0,
        "omitted_characters": omitted,
    }
    return _tool_result(
        output=raw,
        model_output=projected,
        tool_name="run_command",
        omitted_characters=omitted,
    )


__all__ = ["EnvCodingToolSet"]
