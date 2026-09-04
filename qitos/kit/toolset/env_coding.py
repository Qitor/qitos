"""Small native coding ACI that can operate only through a configured Env."""

from __future__ import annotations

import hashlib
import json
import posixpath
import shlex
from typing import Any, Dict, Optional

from qitos.core.artifact import ArtifactRef
from qitos.core.env import EnvCapabilityError, ProcessHandle
from qitos.core.function_tool_decorator import function_tool
from qitos.core.tool import ToolPermission
from qitos.core.tool_result import ToolResult
from qitos.core.tool_runtime import ToolEffectDeclaration
from qitos.kit.tool.toolset import BaseToolSet


_MODEL_TEXT_LIMIT = 16_000
_FILE_LIST_LIMIT = 200
_COMMAND_TIMEOUT_LIMIT = 180
_PROTECTED_PARTS = frozenset({".git", ".ssh", ".gnupg", ".aws", ".env"})


def _ops(runtime_context: Optional[Dict[str, Any]], group: str) -> Any:
    context = runtime_context or {}
    env = context.get("env")
    if env is None:
        raise EnvCapabilityError("env_required", "configured Env is required")
    capability = dict(context.get("ops") or {}).get(group)
    if capability is None:
        raise EnvCapabilityError(
            "capability_unavailable",
            f"configured Env does not provide {group!r} operations",
        )
    return capability


def _path(value: str) -> str:
    path = str(value or ".").replace("\\", "/")
    normalized = posixpath.normpath(path)
    parts = tuple(part for part in normalized.split("/") if part not in {"", "."})
    if path.startswith("/") or normalized == ".." or normalized.startswith("../"):
        raise EnvCapabilityError("path_outside_workspace", "path must be workspace-relative")
    if any(part in _PROTECTED_PARTS for part in parts):
        raise EnvCapabilityError("protected_path", "path targets protected controller data")
    return normalized


def _bounded_text(value: Any, *, limit: int = _MODEL_TEXT_LIMIT) -> tuple[str, int]:
    text = str(value or "")
    if len(text) <= limit:
        return text, 0
    marker = "...[TRUNCATED]"
    kept = max(0, limit - len(marker))
    return text[:kept] + marker, len(text) - kept


def _artifact(payload: Any, *, kind: str, summary: str,
              runtime_context: Optional[Dict[str, Any]] = None) -> ArtifactRef:
    raw = (
        payload.encode("utf-8")
        if isinstance(payload, str)
        else json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    digest = hashlib.sha256(raw).hexdigest()
    reference = ArtifactRef(
        artifact_id=f"sha256:{digest}",
        resolver_key="tool-result-output",
        sha256=digest,
        media_type="text/plain" if isinstance(payload, str) else "application/json",
        byte_length=len(raw),
        encoding="utf-8",
        sensitivity="internal",
        model_summary=f"Full {kind} retained in the canonical tool result; {summary}",
    )
    resolver = (runtime_context or {}).get("artifact_resolver")
    if resolver is None:
        raise EnvCapabilityError("artifact_store_unavailable", "full output requires an artifact resolver")
    put = getattr(resolver, "put", None)
    if callable(put):
        put(reference, raw)
    if not resolver.probe(reference):
        raise EnvCapabilityError("missing_required_artifact", "full output artifact is unavailable")
    return reference


def _success(
    *,
    output: Dict[str, Any],
    model_output: Dict[str, Any],
    tool_name: str,
    omitted: int = 0,
    artifacts: tuple[ArtifactRef, ...] = (),
    filesystem_changes: Optional[list[Dict[str, Any]]] = None,
    complete: bool = True,
) -> ToolResult:
    return ToolResult(
        output=output,
        model_output=model_output,
        tool_name=tool_name,
        complete=complete,
        truncated=omitted > 0,
        omitted={"model_output_characters": omitted},
        artifact_refs=artifacts,
        filesystem_changes=list(filesystem_changes or []),
    )


def _semantic(
    tool_name: str,
    exc: Exception,
    *,
    output: Any = None,
    model_output: Any = None,
) -> ToolResult:
    code = getattr(exc, "code", "env_operation_failed")
    return ToolResult.semantic_error(
        code=str(code),
        error=str(exc),
        output=output,
        model_output=model_output,
        tool_name=tool_name,
        recoverable=code in {"stale_file", "capability_unavailable"},
    )


def _file_effect(args: Dict[str, Any], context: Dict[str, Any]) -> ToolEffectDeclaration:
    path = _path(str(args.get("path") or "."))
    return ToolEffectDeclaration(
        effect_ref=f"filesystem:{path}",
        metadata={"kind": "atomic_file_mutation", "path": path},
    )


def _command_effect(args: Dict[str, Any], context: Dict[str, Any]) -> ToolEffectDeclaration:
    command = str(args.get("command") or args.get("target") or "")
    digest = hashlib.sha256(command.encode("utf-8")).hexdigest()
    return ToolEffectDeclaration(
        effect_ref=f"process:{digest[:24]}",
        metadata={"kind": "bounded_process", "command_sha256": digest},
    )


class EnvCodingToolSet(BaseToolSet):
    """Read, search, edit, execute, test, and control owned processes via Env."""

    name = "env_coding"
    version = "2"

    def tools(self) -> list[Any]:
        return [
            read_file,
            list_files,
            grep_file,
            write_file,
            edit_file,
            run_command,
            run_test,
            start_process,
            poll_process,
            terminate_process,
        ]


@function_tool(
    name="read_file",
    read_only=True,
    concurrency_safe=True,
    required_ops=["file"],
    permissions=ToolPermission(filesystem_read=True),
)
def read_file(
    path: str,
    line_offset: int = 1,
    line_limit: int = 400,
    runtime_context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Read a numbered, bounded line window while retaining the full file result."""
    try:
        safe_path = _path(path)
        fs = _ops(runtime_context, "file")
        content = fs.read_text(safe_path)
        snapshot = fs.snapshot(safe_path)
        lines = content.splitlines()
        start = max(1, int(line_offset))
        applied = min(2_000, max(1, int(line_limit)))
        selected = lines[start - 1 : start - 1 + applied]
        numbered = "\n".join(
            f"{index}: {line}" for index, line in enumerate(selected, start=start)
        )
        bounded, omitted_chars = _bounded_text(numbered)
        omitted_lines = max(0, len(lines) - (start - 1 + len(selected)))
        omitted = omitted_chars + omitted_lines
        artifacts = (
            (_artifact(content, kind="file content", summary="use pagination for context", runtime_context=runtime_context),)
            if omitted
            else ()
        )
        return _success(
            output={
                "status": "success",
                "path": safe_path,
                "content": content,
                "snapshot": snapshot.to_dict(),
            },
            model_output={
                "status": "success",
                "path": safe_path,
                "lines": bounded,
                "snapshot": snapshot.to_dict(),
                "selection_receipt": {
                    "line_offset": start,
                    "line_limit": applied,
                    "selected_lines": len(selected),
                    "total_lines": len(lines),
                    "omitted_lines": omitted_lines,
                    "omitted_characters": omitted_chars,
                },
            },
            tool_name="read_file",
            omitted=omitted,
            artifacts=artifacts,
        )
    except Exception as exc:
        return _semantic("read_file", exc)


@function_tool(
    name="list_files",
    read_only=True,
    concurrency_safe=True,
    required_ops=["file"],
    permissions=ToolPermission(filesystem_read=True),
)
def list_files(
    path: str = ".",
    limit: int = 200,
    runtime_context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """List a bounded set of workspace-relative files with a completeness receipt."""
    try:
        safe_path = _path(path)
        applied = min(_FILE_LIST_LIMIT, max(1, int(limit)))
        candidates = list(_ops(runtime_context, "file").list_files(safe_path, applied + 1))
        files = candidates[:applied]
        truncated = len(candidates) > applied
        return _success(
            output={"status": "success", "path": safe_path, "files": files},
            model_output={
                "status": "success",
                "path": safe_path,
                "files": files,
                "selection_receipt": {
                    "requested_limit": int(limit),
                    "applied_limit": applied,
                    "complete": not truncated,
                    "at_least_omitted": 1 if truncated else 0,
                },
            },
            tool_name="list_files",
            omitted=1 if truncated else 0,
            complete=not truncated,
        )
    except Exception as exc:
        return _semantic("list_files", exc)


@function_tool(
    name="grep_file",
    read_only=True,
    concurrency_safe=True,
    required_ops=["process"],
    permissions=ToolPermission(filesystem_read=True, command=True),
)
def grep_file(
    query: str,
    path: str = ".",
    literal: bool = True,
    runtime_context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Search inside the Env with structured ripgrep output; literal matching is default."""
    try:
        safe_path = _path(path)
        literal_flag = "-F " if literal else ""
        command = (
            f"rg --json --no-config -n {literal_flag}-- "
            f"{shlex.quote(query)} {shlex.quote(safe_path)}"
        )
        raw = dict(_ops(runtime_context, "process").run(command, timeout=30))
        returncode = int(raw.get("returncode", 1))
        if returncode == 127:
            raise EnvCapabilityError("search_backend_unavailable", "ripgrep is unavailable")
        stdout, out_omitted = _bounded_text(raw.get("stdout"))
        stderr, err_omitted = _bounded_text(raw.get("stderr"))
        omitted = out_omitted + err_omitted
        artifacts = (
            (_artifact(raw, kind="search output", summary="refine the query for context", runtime_context=runtime_context),)
            if omitted
            else ()
        )
        result = _success(
            output=raw,
            model_output={
                "status": "success" if returncode in {0, 1} else "error",
                "returncode": returncode,
                "json_lines": stdout,
                "stderr": stderr,
                "loss_receipt": {"omitted_characters": omitted},
            },
            tool_name="grep_file",
            omitted=omitted,
            artifacts=artifacts,
        )
        if returncode not in {0, 1}:
            return ToolResult.semantic_error(
                code="search_failed",
                error="search command failed",
                output=result.output,
                model_output=result.model_output,
                tool_name="grep_file",
                artifact_refs=result.artifact_refs,
                truncated=result.truncated,
                omitted=result.omitted,
            )
        return result
    except Exception as exc:
        return _semantic("grep_file", exc)


@function_tool(
    name="write_file",
    required_ops=["file"],
    permissions=ToolPermission(filesystem_write=True),
    effect=_file_effect,
)
def write_file(
    path: str,
    content: str,
    expected_sha256: Optional[str] = None,
    runtime_context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Atomically write a file, optionally rejecting a stale expected digest."""
    try:
        safe_path = _path(path)
        snapshot = _ops(runtime_context, "file").atomic_write_text(
            safe_path, content, expected_sha256=expected_sha256
        )
        change = {"operation": "write", **snapshot.to_dict()}
        return _success(
            output={"status": "success", "snapshot": snapshot.to_dict()},
            model_output={"status": "success", "snapshot": snapshot.to_dict()},
            tool_name="write_file",
            filesystem_changes=[change],
        )
    except Exception as exc:
        return _semantic("write_file", exc)


@function_tool(
    name="edit_file",
    required_ops=["file"],
    permissions=ToolPermission(filesystem_read=True, filesystem_write=True),
    effect=_file_effect,
)
def edit_file(
    path: str,
    old_text: str,
    replacement: str,
    expected_sha256: Optional[str] = None,
    replace_all: bool = False,
    runtime_context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Atomically replace one exact text occurrence, with optimistic concurrency control."""
    try:
        safe_path = _path(path)
        fs = _ops(runtime_context, "file")
        before = fs.snapshot(safe_path)
        if expected_sha256 and before.sha256 != expected_sha256:
            raise EnvCapabilityError("stale_file", "file changed since the caller read it")
        content = fs.read_text(safe_path)
        count = content.count(old_text)
        if count == 0:
            raise EnvCapabilityError("text_not_found", "old_text was not found")
        if count > 1 and not replace_all:
            raise EnvCapabilityError("ambiguous_edit", "old_text occurs more than once")
        updated = content.replace(old_text, replacement, -1 if replace_all else 1)
        after = fs.atomic_write_text(safe_path, updated, expected_sha256=before.sha256)
        change = {
            "operation": "edit",
            "path": safe_path,
            "before_sha256": before.sha256,
            "after_sha256": after.sha256,
            "replacements": count if replace_all else 1,
        }
        return _success(
            output={"status": "success", "snapshot": after.to_dict(), **change},
            model_output={"status": "success", "snapshot": after.to_dict(), **change},
            tool_name="edit_file",
            filesystem_changes=[change],
        )
    except Exception as exc:
        return _semantic("edit_file", exc)


def _command_result(tool_name: str, command: str, timeout: int, raw: Dict[str, Any],
                    runtime_context: Optional[Dict[str, Any]] = None) -> ToolResult:
    stdout, out_omitted = _bounded_text(raw.get("stdout"))
    stderr, err_omitted = _bounded_text(raw.get("stderr"))
    omitted = out_omitted + err_omitted
    raw_returncode = raw.get("returncode")
    returncode = int(raw_returncode) if isinstance(raw_returncode, int) else None
    model_output = {
        "status": raw.get("status"),
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "execution_receipt": {
            "timeout_seconds": timeout,
            "timed_out": bool(raw.get("timed_out", False)),
            "outcome_unknown": bool(raw.get("outcome_unknown", False)),
            "omitted_characters": omitted,
        },
    }
    if raw.get("worker_still_running") or raw.get("outcome_unknown"):
        return ToolResult(
            status="error" if raw.get("outcome_unknown") else "success",
            output=raw, model_output=model_output, tool_name=tool_name,
            error="process completion is unknown" if raw.get("outcome_unknown") else None,
            error_kind="execution" if raw.get("outcome_unknown") else None,
            error_code="process_outcome_unknown" if raw.get("outcome_unknown") else None,
            worker_still_running=bool(raw.get("worker_still_running")),
            outcome_unknown=bool(raw.get("outcome_unknown")),
        )
    artifacts = (
        (_artifact(raw, kind="command output", summary="narrow the command for context", runtime_context=runtime_context),)
        if omitted
        else ()
    )
    if raw.get("timed_out"):
        return ToolResult(
            status="timed_out",
            error="command exceeded its bounded deadline",
            error_kind="execution",
            error_code="command_timed_out",
            output=raw,
            model_output=model_output,
            tool_name=tool_name,
            worker_still_running=bool(raw.get("worker_still_running", False)),
            outcome_unknown=bool(raw.get("outcome_unknown", False)),
            truncated=omitted > 0,
            omitted={"model_output_characters": omitted},
            artifact_refs=artifacts,
        )
    if returncode not in {0, None} or raw.get("status") == "error":
        return ToolResult.execution_error(
            code="command_failed",
            error="command exited unsuccessfully",
            output=raw,
            model_output=model_output,
            tool_name=tool_name,
            recoverable=True,
            truncated=omitted > 0,
            omitted={"model_output_characters": omitted},
            artifact_refs=artifacts,
        )
    return _success(
        output=raw,
        model_output=model_output,
        tool_name=tool_name,
        omitted=omitted,
        artifacts=artifacts,
    )


@function_tool(
    name="run_command",
    required_ops=["process"],
    permissions=ToolPermission(command=True),
    effect=_command_effect,
)
def run_command(
    command: str,
    timeout: int = 30,
    runtime_context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Run one command through the Env with bounded time and model-visible output."""
    applied = min(_COMMAND_TIMEOUT_LIMIT, max(1, int(timeout)))
    try:
        raw = dict(_ops(runtime_context, "process").run(command, timeout=applied))
        return _command_result("run_command", command, applied, raw, runtime_context)
    except Exception as exc:
        return _semantic("run_command", exc)


@function_tool(
    name="run_test",
    required_ops=["process"],
    permissions=ToolPermission(command=True),
    effect=_command_effect,
)
def run_test(
    target: str = "",
    timeout: int = 120,
    runtime_context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Run pytest for an optional workspace-relative target through the Env."""
    try:
        safe_target = _path(target) if target else ""
        command = "python -m pytest -q" + (f" {shlex.quote(safe_target)}" if safe_target else "")
        applied = min(_COMMAND_TIMEOUT_LIMIT, max(1, int(timeout)))
        raw = dict(_ops(runtime_context, "process").run(command, timeout=applied))
        return _command_result("run_test", command, applied, raw, runtime_context)
    except Exception as exc:
        return _semantic("run_test", exc)


@function_tool(
    name="start_process",
    required_ops=["process_control"],
    permissions=ToolPermission(command=True),
    supports_background=True,
    effect=_command_effect,
)
def start_process(
    command: str,
    runtime_context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Start an Env-owned background process and return its generation-fenced handle."""
    try:
        handle = _ops(runtime_context, "process_control").start(command)
        payload = {"status": "running", "handle": handle.to_dict()}
        return _success(output=payload, model_output=payload, tool_name="start_process")
    except Exception as exc:
        return _semantic("start_process", exc)


@function_tool(
    name="poll_process",
    read_only=True,
    concurrency_safe=True,
    required_ops=["process_control"],
    permissions=ToolPermission(command=True),
)
def poll_process(
    process_id: str,
    owner_generation: int,
    runtime_context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Poll an Env-owned process; stale or foreign handles are rejected."""
    try:
        raw = dict(
            _ops(runtime_context, "process_control").poll(
                ProcessHandle(process_id, owner_generation)
            )
        )
        return _command_result("poll_process", process_id, 0, raw, runtime_context)
    except Exception as exc:
        return _semantic("poll_process", exc)


@function_tool(
    name="terminate_process",
    required_ops=["process_control"],
    permissions=ToolPermission(command=True),
    effect=lambda args, context: ToolEffectDeclaration(
        effect_ref=f"process-control:{str(args.get('process_id') or '')[:64]}",
        metadata={"kind": "process_termination"},
    ),
)
def terminate_process(
    process_id: str,
    owner_generation: int,
    runtime_context: Optional[Dict[str, Any]] = None,
) -> ToolResult:
    """Terminate exactly one Env-owned background process and acknowledge cleanup."""
    try:
        raw = dict(
            _ops(runtime_context, "process_control").terminate(
                ProcessHandle(process_id, owner_generation)
            )
        )
        terminal = raw.get("status") == "terminal" and not raw.get("worker_still_running", True)
        return ToolResult(
            status="success" if terminal else "error", output=raw, model_output=raw,
            tool_name="terminate_process", worker_still_running=not terminal,
            outcome_unknown=not terminal,
            error=None if terminal else "owned process termination remains unknown",
            error_code=None if terminal else "process_termination_unknown",
            error_kind=None if terminal else "execution",
        )
    except Exception as exc:
        return _semantic("terminate_process", exc)


__all__ = ["EnvCodingToolSet"]
