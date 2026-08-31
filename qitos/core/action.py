"""Action protocol for QitOS kernel."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .tool_result import ToolResult


class ActionKind(str, Enum):
    TOOL = "tool"


class ActionStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


@dataclass
class Action:
    """Normalized action contract emitted by policy and consumed by executor."""

    name: str
    args: Dict[str, Any] = field(default_factory=dict)
    kind: ActionKind = ActionKind.TOOL
    action_id: Optional[str] = None
    timeout_s: Optional[float] = None
    max_retries: int = 0
    idempotent: bool = True
    classification: str = "default"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "Action":
        return cls(
            name=payload.get("name", ""),
            args=payload.get("args", {}),
            kind=ActionKind(payload.get("kind", ActionKind.TOOL.value)),
            action_id=payload.get("action_id"),
            timeout_s=payload.get("timeout_s"),
            max_retries=int(payload.get("max_retries", 0)),
            idempotent=bool(payload.get("idempotent", True)),
            classification=payload.get("classification", "default"),
            metadata=payload.get("metadata", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        kind = self.kind.value if isinstance(self.kind, ActionKind) else str(self.kind)
        return {
            "name": self.name,
            "args": dict(self.args),
            "kind": kind,
            "action_id": self.action_id,
            "timeout_s": self.timeout_s,
            "max_retries": self.max_retries,
            "idempotent": self.idempotent,
            "classification": self.classification,
            "metadata": dict(self.metadata),
        }


@dataclass
class ActionResult:
    """Executor compatibility record.

    ``ToolResult`` is the canonical public outcome. Executor callers may keep
    consuming this record during migration and adapt it explicitly with
    :meth:`to_tool_result`.
    """

    name: str
    status: ActionStatus
    output: Any = None
    error: Optional[str] = None
    action_id: Optional[str] = None
    attempts: int = 1
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_tool_result(self) -> "ToolResult":
        """Adapt this executor record to the canonical outcome contract."""
        from .tool_result import ToolResult

        return ToolResult.from_action_result(self)

    @classmethod
    def from_tool_result(cls, result: "ToolResult") -> "ActionResult":
        """Project the canonical outcome for legacy executor consumers."""
        from .tool_result import ToolResult

        if not isinstance(result, ToolResult):
            raise TypeError("from_tool_result() expects ToolResult")
        metadata = dict(result.metadata)
        metadata.update(
            {
                "error_code": result.error_code,
                "error_kind": result.error_kind,
                "recoverable": result.recoverable,
                "recovery_hint": result.recovery_hint,
                "next_action": result.next_action,
                "complete": result.complete,
                "truncated": result.truncated,
                "omitted": dict(result.omitted),
                "model_output": result.model_output,
                "declared_effects": list(result.declared_effects),
                "filesystem_changes": list(result.filesystem_changes),
                "artifact_refs": [item.to_dict() for item in result.artifact_refs],
                "normalized_request": dict(result.normalized_request),
                "provenance": dict(result.provenance),
                "worker_still_running": result.worker_still_running,
                "attempt_id": (
                    result.attempt_id.to_dict() if result.attempt_id else None
                ),
                "effect_ref": result.effect_ref,
                "effect_state": result.effect_state,
                "idempotency_ref": result.idempotency_ref,
                "retry_disposition": result.retry_disposition,
                "reconciliation_required": result.reconciliation_required,
                "outcome_unknown": result.outcome_unknown,
                "late_result": result.late_result,
                "owner_generation": result.owner_generation,
                "stale_owner": result.stale_owner,
                "batch_closure": dict(result.batch_closure),
            }
        )
        return cls(
            name=result.tool_name or "",
            status=ActionStatus(result.status),
            output=result.output,
            error=result.error,
            action_id=result.action_id,
            attempts=result.attempts,
            latency_ms=result.latency_ms,
            metadata=metadata,
        )


@dataclass
class ActionExecutionPolicy:
    """Executor policy for action batches."""

    mode: str = "serial"  # serial | parallel
    fail_fast: bool = False
    max_concurrency: int = 4
    # ``None`` preserves the executor's ordinary read-only/concurrency-safe
    # classification. A caller may restrict parallel execution to a smaller
    # set without changing the global QitOS policy.
    parallel_tool_names: FrozenSet[str] | None = None
