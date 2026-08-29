"""Canonical action/tool outcome used by execution, observations, and replay."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Mapping, TYPE_CHECKING

if TYPE_CHECKING:
    from .action import ActionResult


ToolResultStatus = Literal[
    "success",
    "error",
    "skipped",
    "timed_out",
    "cancelled",
]
ToolErrorKind = Literal["semantic", "execution", "policy"]

TOOL_RESULT_SCHEMA_VERSION = "qitos.tool_result/v1"
_TERMINAL_STATUSES = frozenset(
    {"success", "error", "skipped", "timed_out", "cancelled"}
)
_ERROR_KINDS = frozenset({"semantic", "execution", "policy"})


def _copy_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _copy_dict_list(value: Any) -> list[Dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _model_projection(output: Any, explicit: Any = None) -> Any:
    if explicit is not None:
        return explicit
    if isinstance(output, Mapping):
        summary = output.get("model_summary")
        if isinstance(summary, str) and summary.strip():
            return summary.strip()
    return None


def _validated_next_action(value: Any) -> Dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("next_action must be an object")
    name = value.get("name")
    args = value.get("args", {})
    action_id = value.get("action_id")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("next_action.name must be a non-empty string")
    if not isinstance(args, Mapping):
        raise ValueError("next_action.args must be an object")
    if action_id is not None and not isinstance(action_id, str):
        raise ValueError("next_action.action_id must be a string when provided")
    normalized: Dict[str, Any] = {"name": name.strip(), "args": dict(args)}
    if action_id is not None:
        normalized["action_id"] = action_id
    return normalized


@dataclass
class ToolResult:
    """Lossless terminal outcome for one declared action/tool slot.

    ``output`` is the canonical structured value. ``model_output`` is an
    explicit, possibly redacted/bounded projection and never replaces it.
    ``ActionResult`` is accepted only through :meth:`from_action_result` as an
    executor compatibility boundary.
    """

    status: ToolResultStatus = "success"
    output: Any = None
    error: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    tool_name: str | None = None
    action_id: str | None = None
    model_output: Any = None
    error_kind: ToolErrorKind | None = None
    error_code: str | None = None
    recoverable: bool = False
    recovery_hint: str | None = None
    next_action: Dict[str, Any] | None = None
    complete: bool = True
    truncated: bool = False
    omitted: Dict[str, int] = field(default_factory=dict)
    attempts: int = 1
    latency_ms: float = 0.0
    declared_effects: list[Dict[str, Any]] = field(default_factory=list)
    filesystem_changes: list[Dict[str, Any]] = field(default_factory=list)
    artifact_refs: list[Dict[str, Any]] = field(default_factory=list)
    normalized_request: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    worker_still_running: bool = False
    schema_version: str = TOOL_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status not in _TERMINAL_STATUSES:
            raise ValueError(f"unsupported ToolResult status: {self.status!r}")
        if self.error_kind is not None and self.error_kind not in _ERROR_KINDS:
            raise ValueError(f"unsupported ToolResult error_kind: {self.error_kind!r}")
        if self.attempts < 0:
            raise ValueError("attempts must be non-negative")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must be non-negative")
        for key, count in self.omitted.items():
            if not isinstance(key, str) or not isinstance(count, int) or count < 0:
                raise ValueError("omitted must map string names to non-negative integers")
        self.next_action = _validated_next_action(self.next_action)
        self.metadata = _copy_dict(self.metadata)
        self.omitted = dict(self.omitted)
        self.declared_effects = _copy_dict_list(self.declared_effects)
        self.filesystem_changes = _copy_dict_list(self.filesystem_changes)
        self.artifact_refs = _copy_dict_list(self.artifact_refs)
        self.normalized_request = _copy_dict(self.normalized_request)
        self.provenance = _copy_dict(self.provenance)
        self.model_output = _model_projection(self.output, self.model_output)

    @property
    def is_success(self) -> bool:
        return self.status == "success"

    @property
    def text(self) -> str:
        if isinstance(self.output, str):
            return self.output
        try:
            return json.dumps(self.output, ensure_ascii=False, default=str)
        except Exception:
            return str(self.output)

    @property
    def model_text(self) -> str:
        visible = self.model_output if self.model_output is not None else self.output
        if isinstance(visible, str):
            return visible
        try:
            return json.dumps(visible, ensure_ascii=False, default=str)
        except Exception:
            return str(visible)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "status": str(self.status),
            "success": self.is_success,
            "tool_name": self.tool_name,
            "action_id": self.action_id,
            "output": self.output,
            "model_output": self.model_output,
            "error": self.error,
            "error_kind": self.error_kind,
            "error_code": self.error_code,
            "recoverable": self.recoverable,
            "recovery_hint": self.recovery_hint,
            "next_action": dict(self.next_action) if self.next_action is not None else None,
            "complete": self.complete,
            "truncated": self.truncated,
            "omitted": dict(self.omitted),
            "attempts": self.attempts,
            "latency_ms": self.latency_ms,
            "declared_effects": list(self.declared_effects),
            "filesystem_changes": list(self.filesystem_changes),
            "artifact_refs": list(self.artifact_refs),
            "normalized_request": dict(self.normalized_request),
            "provenance": dict(self.provenance),
            "worker_still_running": self.worker_still_running,
            "metadata": dict(self.metadata),
        }
        if isinstance(self.output, dict):
            for key, value in self.output.items():
                if key in payload:
                    continue
                payload[str(key)] = value
        return payload

    @classmethod
    def semantic_error(
        cls,
        *,
        code: str,
        error: str,
        output: Any = None,
        recoverable: bool = True,
        recovery_hint: str | None = None,
        next_action: Mapping[str, Any] | None = None,
        complete: bool = True,
        **kwargs: Any,
    ) -> "ToolResult":
        return cls(
            status="error",
            output=output,
            error=error,
            error_kind="semantic",
            error_code=code,
            recoverable=recoverable,
            recovery_hint=recovery_hint,
            next_action=dict(next_action) if next_action is not None else None,
            complete=complete,
            **kwargs,
        )

    @classmethod
    def execution_error(
        cls,
        *,
        code: str,
        error: str,
        output: Any = None,
        recoverable: bool = False,
        recovery_hint: str | None = None,
        **kwargs: Any,
    ) -> "ToolResult":
        return cls(
            status="error",
            output=output,
            error=error,
            error_kind="execution",
            error_code=code,
            recoverable=recoverable,
            recovery_hint=recovery_hint,
            **kwargs,
        )

    @classmethod
    def from_action_result(cls, payload: "ActionResult") -> "ToolResult":
        """Adapt the executor compatibility record into the canonical result."""
        from .action import ActionResult

        if not isinstance(payload, ActionResult):
            raise TypeError("from_action_result() expects ActionResult")

        metadata = dict(payload.metadata or {})
        nested = payload.output if isinstance(payload.output, ToolResult) else None
        if nested is not None:
            return cls(
                status=nested.status,
                output=nested.output,
                error=nested.error,
                metadata={**metadata, **nested.metadata},
                tool_name=nested.tool_name or payload.name,
                action_id=nested.action_id or payload.action_id,
                model_output=nested.model_output,
                error_kind=nested.error_kind,
                error_code=nested.error_code,
                recoverable=nested.recoverable,
                recovery_hint=nested.recovery_hint,
                next_action=nested.next_action,
                complete=nested.complete,
                truncated=nested.truncated,
                omitted=nested.omitted,
                attempts=payload.attempts,
                latency_ms=payload.latency_ms,
                declared_effects=nested.declared_effects,
                filesystem_changes=nested.filesystem_changes,
                artifact_refs=nested.artifact_refs,
                normalized_request=nested.normalized_request,
                provenance=nested.provenance,
                worker_still_running=nested.worker_still_running,
            )

        status = str(getattr(payload.status, "value", payload.status))
        if status not in _TERMINAL_STATUSES:
            status = "error"
        output = payload.output
        error_code = metadata.get("error_code") or metadata.get("error_category")
        error_kind: ToolErrorKind | None = None
        if status == "skipped":
            error_kind = "policy"
        elif status != "success":
            error_kind = "execution"
        return cls(
            status=status,  # type: ignore[arg-type]
            output=output,
            error=payload.error,
            metadata=metadata,
            tool_name=payload.name,
            action_id=payload.action_id,
            model_output=_model_projection(output, metadata.get("model_output")),
            error_kind=error_kind,
            error_code=str(error_code) if error_code not in (None, "") else None,
            recoverable=bool(metadata.get("recoverable", False)),
            recovery_hint=(
                str(metadata["recovery_hint"])
                if metadata.get("recovery_hint") not in (None, "")
                else None
            ),
            next_action=metadata.get("next_action"),
            complete=bool(metadata.get("complete", True)),
            truncated=bool(metadata.get("truncated", False)),
            omitted=_copy_dict(metadata.get("omitted")),
            attempts=payload.attempts,
            latency_ms=payload.latency_ms,
            declared_effects=_copy_dict_list(metadata.get("declared_effects")),
            filesystem_changes=_copy_dict_list(metadata.get("filesystem_changes")),
            artifact_refs=_copy_dict_list(
                metadata.get("artifact_refs", metadata.get("artifacts"))
            ),
            normalized_request=_copy_dict(metadata.get("normalized_request")),
            provenance=_copy_dict(metadata.get("provenance")),
            worker_still_running=bool(metadata.get("worker_still_running", False)),
        )

    @classmethod
    def from_value(cls, payload: Any) -> "ToolResult":
        if isinstance(payload, ToolResult):
            return payload

        from .action import ActionResult

        if isinstance(payload, ActionResult):
            return cls.from_action_result(payload)
        if isinstance(payload, Mapping):
            schema_version = str(payload.get("schema_version") or "")
            raw_status = str(payload.get("status") or "success")
            if raw_status not in _TERMINAL_STATUSES:
                if schema_version == TOOL_RESULT_SCHEMA_VERSION:
                    raise ValueError(f"unsupported ToolResult status: {raw_status!r}")
                raw_status = "error" if payload.get("error") else "success"
            output = payload.get("output", payload)
            metadata = _copy_dict(payload.get("metadata"))
            error = payload.get("error")
            if error in (None, "") and raw_status == "error":
                error = payload.get("message")
            error_kind = payload.get("error_kind")
            if error_kind not in _ERROR_KINDS:
                error_kind = None
            return cls(
                status=raw_status,  # type: ignore[arg-type]
                output=output,
                error=str(error) if error not in (None, "") else None,
                metadata=metadata,
                tool_name=(
                    str(payload["tool_name"])
                    if payload.get("tool_name") not in (None, "")
                    else metadata.get("tool_name")
                ),
                action_id=(
                    str(payload["action_id"])
                    if payload.get("action_id") not in (None, "")
                    else None
                ),
                model_output=_model_projection(output, payload.get("model_output")),
                error_kind=error_kind,  # type: ignore[arg-type]
                error_code=(
                    str(payload["error_code"])
                    if payload.get("error_code") not in (None, "")
                    else (
                        str(metadata["error_category"])
                        if metadata.get("error_category") not in (None, "")
                        else None
                    )
                ),
                recoverable=bool(
                    payload.get("recoverable", metadata.get("recoverable", False))
                ),
                recovery_hint=(
                    str(payload["recovery_hint"])
                    if payload.get("recovery_hint") not in (None, "")
                    else None
                ),
                next_action=payload.get("next_action"),
                complete=bool(payload.get("complete", True)),
                truncated=bool(payload.get("truncated", False)),
                omitted=_copy_dict(payload.get("omitted")),
                attempts=int(payload.get("attempts", metadata.get("attempts", 1))),
                latency_ms=float(
                    payload.get("latency_ms", metadata.get("latency_ms", 0.0))
                ),
                declared_effects=_copy_dict_list(payload.get("declared_effects")),
                filesystem_changes=_copy_dict_list(payload.get("filesystem_changes")),
                artifact_refs=_copy_dict_list(payload.get("artifact_refs")),
                normalized_request=_copy_dict(payload.get("normalized_request")),
                provenance=_copy_dict(payload.get("provenance")),
                worker_still_running=bool(payload.get("worker_still_running", False)),
                schema_version=schema_version or TOOL_RESULT_SCHEMA_VERSION,
            )
        if isinstance(payload, str):
            return cls(status="success", output=payload)
        return cls(status="success", output=payload)


__all__ = [
    "TOOL_RESULT_SCHEMA_VERSION",
    "ToolErrorKind",
    "ToolResult",
    "ToolResultStatus",
]
