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
