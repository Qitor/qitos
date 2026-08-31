"""Implementation-neutral contracts for the canonical tool runtime.

The module deliberately describes facts and extension protocols only. Runtime
mechanics remain in :mod:`qitos.engine`; concrete tools remain in
:mod:`qitos.kit`. No contract here claims that every resource can be hard
cancelled or migrated.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import (
    Any,
    Callable,
    Dict,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    TYPE_CHECKING,
    cast,
)

from .session import AttemptIdentity, SnapshotComponentCodec
from .tool_result import EffectState, RetryDisposition, ToolResult

if TYPE_CHECKING:
    from .action import Action
    from .tool import BaseTool


TOOL_LIFECYCLE_RECEIPT_SCHEMA_VERSION = "qitos.tool_lifecycle_receipt/v1"
TOOL_EFFECT_RECEIPT_SCHEMA_VERSION = "qitos.tool_effect_receipt/v1"
TOOL_BATCH_SNAPSHOT_SCHEMA_VERSION = "qitos.tool_batch_snapshot/v1"
TOOL_TERMINAL_RECEIPT_SCHEMA_VERSION = "qitos.tool_terminal_receipt/v1"
TOOL_BATCH_COMPONENT_SCHEMA_VERSION = "qitos.tool_batch_component/v1"


class ToolResourceKind(str, Enum):
    """Closed resource-family vocabulary used by lifecycle policies."""

    SYNC_FUNCTION = "sync_function"
    ASYNC_COROUTINE = "async_coroutine"
    THREAD = "thread"
    SUBPROCESS = "subprocess"
    HTTP_CLIENT = "http_client"
    MCP_REQUEST = "mcp_request"
    ENVIRONMENT_OPERATION = "environment_operation"
    BACKGROUND_OPERATION = "background_operation"


class CancellationCapability(str, Enum):
    """What one lifecycle owner can honestly do to in-flight work."""

    NONE = "none"
    COOPERATIVE = "cooperative"
    TERMINATE_OWNED_PROCESS = "terminate_owned_process"
    KILL_OWNED_PROCESS = "kill_owned_process"


class MigrationDisposition(str, Enum):
    MIGRATABLE = "migratable"
    NON_MIGRATABLE = "non_migratable"


class ToolLifecycleState(str, Enum):
    DECLARED = "declared"
    RUNNING = "running"
    TERMINAL = "terminal"
    CANCELLATION_REQUESTED = "cancellation_requested"
    CANCELLED = "cancelled"
    WORKER_STILL_RUNNING = "worker_still_running"
    OUTCOME_UNKNOWN = "outcome_unknown"


class TerminalDisposition(str, Enum):
    COMMITTED = "committed"
    DUPLICATE_IGNORED = "duplicate_ignored"
    STALE_OWNER_REJECTED = "stale_owner_rejected"
    LATE_TERMINAL_REJECTED = "late_terminal_rejected"


@dataclass(frozen=True)
class ToolLifecycleSpec:
    """One executable row of the resource lifecycle ownership matrix."""

    resource_kind: ToolResourceKind
    owner: str
    completion_signal: str
    cancellation_capability: CancellationCapability
    timeout_behavior: str
    cleanup_responsibility: str
    process_loss_behavior: str
    migration: MigrationDisposition
    late_result_handling: str

    def __post_init__(self) -> None:
        for name in (
            "owner",
            "completion_signal",
            "timeout_behavior",
            "cleanup_responsibility",
            "process_loss_behavior",
            "late_result_handling",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resource_kind": self.resource_kind.value,
            "owner": self.owner,
            "completion_signal": self.completion_signal,
            "cancellation_capability": self.cancellation_capability.value,
            "timeout_behavior": self.timeout_behavior,
            "cleanup_responsibility": self.cleanup_responsibility,
            "process_loss_behavior": self.process_loss_behavior,
            "migration": self.migration.value,
            "late_result_handling": self.late_result_handling,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ToolLifecycleSpec":
        data = _strict_mapping(
            value,
            "lifecycle.spec",
            {
                "resource_kind",
                "owner",
                "completion_signal",
                "cancellation_capability",
                "timeout_behavior",
                "cleanup_responsibility",
                "process_loss_behavior",
                "migration",
                "late_result_handling",
            },
        )
        data["resource_kind"] = ToolResourceKind(data["resource_kind"])
        data["cancellation_capability"] = CancellationCapability(
            data["cancellation_capability"]
        )
        data["migration"] = MigrationDisposition(data["migration"])
        return cls(**data)


_LIFECYCLE_ROWS = {
    ToolResourceKind.SYNC_FUNCTION: ToolLifecycleSpec(
        ToolResourceKind.SYNC_FUNCTION,
        owner="executor call frame",
        completion_signal="function return or exception",
        cancellation_capability=CancellationCapability.NONE,
        timeout_behavior="observer may time out while its Python worker continues",
        cleanup_responsibility="tool closes resources it opened",
        process_loss_behavior="unfinished outcome is unknown",
        migration=MigrationDisposition.NON_MIGRATABLE,
        late_result_handling="suppress terminal replacement and record late completion",
    ),
    ToolResourceKind.ASYNC_COROUTINE: ToolLifecycleSpec(
        ToolResourceKind.ASYNC_COROUTINE,
        owner="executor-owned task while awaited",
        completion_signal="task result, exception, or cancellation acknowledgement",
        cancellation_capability=CancellationCapability.COOPERATIVE,
        timeout_behavior="deadline requests task cancellation and awaits acknowledgement",
        cleanup_responsibility="coroutine and transport context owners",
        process_loss_behavior="unfinished outcome is unknown",
        migration=MigrationDisposition.NON_MIGRATABLE,
        late_result_handling="generation-check and suppress stale terminal replacement",
    ),
    ToolResourceKind.THREAD: ToolLifecycleSpec(
        ToolResourceKind.THREAD,
        owner="thread creator",
        completion_signal="thread completion event",
        cancellation_capability=CancellationCapability.NONE,
        timeout_behavior="deadline does not terminate a running Python thread",
        cleanup_responsibility="creator joins or explicitly abandons with a receipt",
        process_loss_behavior="unfinished outcome is unknown",
        migration=MigrationDisposition.NON_MIGRATABLE,
        late_result_handling="never advance a restored owner generation",
    ),
    ToolResourceKind.SUBPROCESS: ToolLifecycleSpec(
        ToolResourceKind.SUBPROCESS,
        owner="process creator",
        completion_signal="owned process wait status",
        cancellation_capability=CancellationCapability.TERMINATE_OWNED_PROCESS,
        timeout_behavior="terminate then optionally kill only an owned process",
        cleanup_responsibility="creator closes pipes and reaps the child",
        process_loss_behavior="external effects may require reconciliation",
        migration=MigrationDisposition.NON_MIGRATABLE,
        late_result_handling="reject output from stale or already-terminal attempts",
    ),
    ToolResourceKind.HTTP_CLIENT: ToolLifecycleSpec(
        ToolResourceKind.HTTP_CLIENT,
        owner="client creator; injected clients remain borrowed",
        completion_signal="response/task completion",
        cancellation_capability=CancellationCapability.COOPERATIVE,
        timeout_behavior="transport deadline; remote outcome may remain unknown",
        cleanup_responsibility="close only internally created clients/responses",
        process_loss_behavior="remote request outcome may require reconciliation",
        migration=MigrationDisposition.NON_MIGRATABLE,
        late_result_handling="generation-check and suppress stale response commits",
    ),
    ToolResourceKind.MCP_REQUEST: ToolLifecycleSpec(
        ToolResourceKind.MCP_REQUEST,
        owner="MCP transport owner",
        completion_signal="JSON-RPC response/task completion",
        cancellation_capability=CancellationCapability.COOPERATIVE,
        timeout_behavior="request deadline does not imply server-side cancellation",
        cleanup_responsibility="transport owner closes client or owned server process",
        process_loss_behavior="request outcome may require reconciliation",
        migration=MigrationDisposition.NON_MIGRATABLE,
        late_result_handling="reject responses for stale request attempts",
    ),
    ToolResourceKind.ENVIRONMENT_OPERATION: ToolLifecycleSpec(
        ToolResourceKind.ENVIRONMENT_OPERATION,
        owner="environment implementation",
        completion_signal="Env operation result or exception",
        cancellation_capability=CancellationCapability.NONE,
        timeout_behavior="capability-specific; no universal hard-cancel claim",
        cleanup_responsibility="environment closes resources it owns",
        process_loss_behavior="unfinished external state is unknown",
        migration=MigrationDisposition.NON_MIGRATABLE,
        late_result_handling="reject stale-generation state advancement",
    ),
    ToolResourceKind.BACKGROUND_OPERATION: ToolLifecycleSpec(
        ToolResourceKind.BACKGROUND_OPERATION,
        owner="background operation creator",
        completion_signal="adapter-owned acknowledgement",
        cancellation_capability=CancellationCapability.NONE,
        timeout_behavior="deadline yields worker-still-running without termination proof",
        cleanup_responsibility="creator supplies bounded shutdown and acknowledgement",
        process_loss_behavior="unfinished outcome is unknown",
        migration=MigrationDisposition.NON_MIGRATABLE,
        late_result_handling="record late outcome without replacing terminal state",
    ),
}

TOOL_LIFECYCLE_MATRIX: Mapping[ToolResourceKind, ToolLifecycleSpec] = (
    MappingProxyType(_LIFECYCLE_ROWS)
)


@dataclass(frozen=True)
class ToolEffectDeclaration:
    """Tool- or policy-authored declaration for one external effect family."""

    effect_ref: str
    idempotency_key: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.effect_ref, str) or not self.effect_ref.strip():
            raise ValueError("effect_ref must be a non-empty string")
        if self.idempotency_key is not None and (
            not isinstance(self.idempotency_key, str)
            or not self.idempotency_key.strip()
        ):
            raise ValueError("idempotency_key must be null or a non-empty string")
        _require_json(self.metadata, "effect.metadata")
        object.__setattr__(self, "effect_ref", self.effect_ref.strip())
        object.__setattr__(
            self,
            "idempotency_key",
            self.idempotency_key.strip() if self.idempotency_key else None,
        )
        object.__setattr__(self, "metadata", _clone_json(self.metadata))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "effect_ref": self.effect_ref,
            "idempotency_key": self.idempotency_key,
            "metadata": _clone_json(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ToolEffectDeclaration":
        return cls(
            **_strict_mapping(
                value,
                "effect.declaration",
                {"effect_ref", "idempotency_key", "metadata"},
            )
        )


EffectDeclarationFactory = Callable[
    [Dict[str, Any], Dict[str, Any]], Optional[ToolEffectDeclaration]
]


@dataclass(frozen=True)
class ToolEffectReceipt:
    declaration: Optional[ToolEffectDeclaration]
    state: EffectState = "no_effect_declared"
    retry_disposition: RetryDisposition = "not_evaluated"
    reconciliation_required: bool = False
    outcome_unknown: bool = False
    schema_version: str = TOOL_EFFECT_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TOOL_EFFECT_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported tool-effect receipt version")
        if self.declaration is None and self.state != "no_effect_declared":
            raise ValueError("effect state requires a declaration")
        if self.declaration is not None and self.state == "no_effect_declared":
            raise ValueError("declared effect requires a concrete state")
        if self.state == "unknown" and not self.outcome_unknown:
            raise ValueError("unknown effect requires outcome_unknown")
        if self.reconciliation_required and not self.outcome_unknown:
            raise ValueError("reconciliation requires outcome uncertainty")

    @property
    def effect_ref(self) -> Optional[str]:
        return self.declaration.effect_ref if self.declaration else None

    @property
    def idempotency_ref(self) -> Optional[str]:
        return self.declaration.idempotency_key if self.declaration else None

    def to_dict(self) -> Dict[str, Any]:
        declaration = (
            self.declaration.to_dict() if self.declaration is not None else None
        )
        return {
            "schema_version": self.schema_version,
            "declaration": declaration,
            "state": self.state,
            "retry_disposition": self.retry_disposition,
            "reconciliation_required": self.reconciliation_required,
            "outcome_unknown": self.outcome_unknown,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ToolEffectReceipt":
        data = _strict_mapping(
            value,
            "effect",
            {
                "schema_version",
                "declaration",
                "state",
                "retry_disposition",
                "reconciliation_required",
                "outcome_unknown",
            },
        )
        data["declaration"] = (
            ToolEffectDeclaration.from_dict(data["declaration"])
            if data["declaration"] is not None
            else None
        )
        return cls(**data)


@dataclass(frozen=True)
class ToolLifecycleReceipt:
    attempt_id: AttemptIdentity
    spec: ToolLifecycleSpec
    state: ToolLifecycleState
    owner_generation: int
    started_at: float
    completed_at: Optional[float] = None
    worker_still_running: bool = False
    outcome_unknown: bool = False
    schema_version: str = TOOL_LIFECYCLE_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TOOL_LIFECYCLE_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported tool-lifecycle receipt version")
        if not isinstance(self.attempt_id, AttemptIdentity):
            raise TypeError("attempt_id must be AttemptIdentity")
        if (
            not isinstance(self.owner_generation, int)
            or isinstance(self.owner_generation, bool)
            or self.owner_generation < 0
        ):
            raise ValueError("owner_generation must be a non-negative integer")
        for name in ("started_at", "completed_at"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                or value < 0
            ):
                raise ValueError(f"{name} must be a finite non-negative number")
        if self.worker_still_running and self.state not in {
            ToolLifecycleState.WORKER_STILL_RUNNING,
            ToolLifecycleState.OUTCOME_UNKNOWN,
        }:
            raise ValueError("running worker requires an unresolved lifecycle state")

    @property
    def migratable(self) -> bool:
        if self.worker_still_running or self.outcome_unknown:
            return False
        return self.state in {ToolLifecycleState.TERMINAL, ToolLifecycleState.CANCELLED}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "attempt_id": self.attempt_id.to_dict(),
            "spec": self.spec.to_dict(),
            "state": self.state.value,
            "owner_generation": self.owner_generation,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "worker_still_running": self.worker_still_running,
            "outcome_unknown": self.outcome_unknown,
            "migratable": self.migratable,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ToolLifecycleReceipt":
        data = _strict_mapping(
            value,
            "lifecycle",
            {
                "schema_version",
                "attempt_id",
                "spec",
                "state",
                "owner_generation",
                "started_at",
                "completed_at",
                "worker_still_running",
                "outcome_unknown",
                "migratable",
            },
        )
        reported_migratable = data.pop("migratable")
        data["attempt_id"] = AttemptIdentity.from_dict(data["attempt_id"])
        data["spec"] = ToolLifecycleSpec.from_dict(data["spec"])
        data["state"] = ToolLifecycleState(data["state"])
        result = cls(**data)
        if result.migratable is not reported_migratable:
            raise ValueError("lifecycle migratable projection is inconsistent")
        return result


@dataclass(frozen=True)
class ToolSlotSnapshot:
    slot_id: str
    declaration_index: int
    action_name: str
    action_id: Optional[str]
    attempt_id: AttemptIdentity
    owner_generation: int
    action_payload: Dict[str, Any]
    result: Optional[ToolResult] = None
    completion_index: Optional[int] = None
    lifecycle: Optional[ToolLifecycleReceipt] = None
    effect: Optional[ToolEffectReceipt] = None
    durability_status: str = "open"

    def __post_init__(self) -> None:
        if not isinstance(self.slot_id, str) or not self.slot_id:
            raise ValueError("slot_id must be non-empty")
        if not isinstance(self.action_name, str) or not self.action_name:
            raise ValueError("action_name must be non-empty")
        for name in ("declaration_index", "owner_generation"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.completion_index is not None and (
            not isinstance(self.completion_index, int)
            or isinstance(self.completion_index, bool)
            or self.completion_index < 0
        ):
            raise ValueError("completion_index must be null or non-negative")
        if (self.result is None) != (self.completion_index is None):
            raise ValueError("result and completion_index must appear together")
        _require_json(self.action_payload, "slot.action_payload")
        if self.action_payload.get("name") != self.action_name:
            raise ValueError("slot action payload name does not match action_name")
        if self.durability_status not in {"open", "pending", "persisted", "failed"}:
            raise ValueError("slot durability_status is unsupported")
        if self.result is None and self.durability_status != "open":
            raise ValueError("open slot must have open durability status")
        if self.result is not None and self.durability_status == "open":
            raise ValueError("terminal slot must declare durability status")

    @property
    def terminal(self) -> bool:
        return self.result is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "declaration_index": self.declaration_index,
            "action_name": self.action_name,
            "action_id": self.action_id,
            "attempt_id": self.attempt_id.to_dict(),
            "owner_generation": self.owner_generation,
            "action": _clone_json(self.action_payload),
            "result": self.result.to_persistence_dict() if self.result else None,
            "completion_index": self.completion_index,
            "lifecycle": self.lifecycle.to_dict() if self.lifecycle else None,
            "effect": self.effect.to_dict() if self.effect else None,
            "worker_still_running": bool(
                self.lifecycle.worker_still_running if self.lifecycle else False
            ),
            "cancellation_or_timeout": (
                self.result.status in {"cancelled", "timed_out"}
                if self.result is not None
                else False
            ),
            "durability_status": self.durability_status,
            "reconciliation_required": bool(
                self.effect.reconciliation_required if self.effect else False
            ),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ToolSlotSnapshot":
        data = _strict_mapping(
            value,
            "tool_batch.slot",
            {
                "slot_id",
                "declaration_index",
                "action_name",
                "action_id",
                "attempt_id",
                "owner_generation",
                "action",
                "result",
                "completion_index",
                "lifecycle",
                "effect",
                "worker_still_running",
                "cancellation_or_timeout",
                "durability_status",
                "reconciliation_required",
            },
        )
        worker = data.pop("worker_still_running")
        cancellation = data.pop("cancellation_or_timeout")
        reconciliation = data.pop("reconciliation_required")
        data["action_payload"] = data.pop("action")
        data["attempt_id"] = AttemptIdentity.from_dict(data["attempt_id"])
        data["result"] = (
            ToolResult.from_canonical_dict(data["result"])
            if data["result"] is not None
            else None
        )
        data["lifecycle"] = (
            ToolLifecycleReceipt.from_dict(data["lifecycle"])
            if data["lifecycle"] is not None
            else None
        )
        data["effect"] = (
            ToolEffectReceipt.from_dict(data["effect"])
            if data["effect"] is not None
            else None
        )
        result = cls(**data)
        if bool(result.lifecycle and result.lifecycle.worker_still_running) is not worker:
            raise ValueError("slot worker-running projection is inconsistent")
        if bool(result.result and result.result.status in {"cancelled", "timed_out"}) is not cancellation:
            raise ValueError("slot cancellation projection is inconsistent")
        if bool(result.effect and result.effect.reconciliation_required) is not reconciliation:
            raise ValueError("slot reconciliation projection is inconsistent")
        return result


@dataclass(frozen=True)
class ToolBatchSnapshot:
    batch_id: str
    slots: tuple[ToolSlotSnapshot, ...]
    completion_order: tuple[str, ...] = ()
    closed: bool = False
    decision_payload: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = TOOL_BATCH_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TOOL_BATCH_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("unsupported tool-batch snapshot version")
        if not isinstance(self.batch_id, str) or not self.batch_id:
            raise ValueError("batch_id must be non-empty")
        if not self.slots:
            raise ValueError("tool batch requires at least one slot")
        slot_ids = [slot.slot_id for slot in self.slots]
        if len(slot_ids) != len(set(slot_ids)):
            raise ValueError("tool batch slot identities must be unique")
        if sorted(slot.declaration_index for slot in self.slots) != list(
            range(len(self.slots))
        ):
            raise ValueError("declaration indices must be contiguous")
        terminal_ids = [slot.slot_id for slot in self.slots if slot.terminal]
        if len(self.completion_order) != len(set(self.completion_order)):
            raise ValueError("completion order cannot contain duplicates")
        if set(self.completion_order) != set(terminal_ids):
            raise ValueError("completion order must name every terminal slot once")
        if self.closed != (len(terminal_ids) == len(self.slots)):
            raise ValueError("closed must exactly match terminal slot coverage")
        _require_json(self.decision_payload, "tool_batch.decision")

    @property
    def declaration_order(self) -> tuple[str, ...]:
        return tuple(
            slot.slot_id
            for slot in sorted(self.slots, key=lambda item: item.declaration_index)
        )

    @property
    def missing_slots(self) -> tuple[ToolSlotSnapshot, ...]:
        return tuple(slot for slot in self.slots if not slot.terminal)

    @property
    def results_in_completion_order(self) -> tuple[ToolResult, ...]:
        by_id = {slot.slot_id: slot for slot in self.slots}
        return tuple(
            cast(ToolResult, by_id[slot_id].result)
            for slot_id in self.completion_order
            if by_id[slot_id].result is not None
        )

    @property
    def results_in_declaration_order(self) -> tuple[ToolResult, ...]:
        return tuple(
            cast(ToolResult, slot.result)
            for slot in sorted(self.slots, key=lambda item: item.declaration_index)
            if slot.result is not None
        )

    def batch_closure(self) -> Dict[str, Any]:
        slots = []
        for slot in sorted(self.slots, key=lambda item: item.declaration_index):
            item: Dict[str, Any] = {
                "action_id": slot.slot_id,
                "state": slot.result.status if slot.result is not None else "open",
                "attempt_id": slot.attempt_id.to_dict(),
            }
            if slot.result is not None:
                canonical = slot.result.to_persistence_dict()
                item["result_ref"] = "result:" + hashlib.sha256(
                    json.dumps(
                        canonical, sort_keys=True, separators=(",", ":")
                    ).encode("utf-8")
                ).hexdigest()
            slots.append(item)
        return {
            "schema_version": "qitos.tool_batch_closure/v1",
            "batch_id": self.batch_id,
            "slots": slots,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "batch_id": self.batch_id,
            "slots": [slot.to_dict() for slot in self.slots],
            "completion_order": list(self.completion_order),
            "declaration_order": list(self.declaration_order),
            "closed": self.closed,
            "decision": _clone_json(self.decision_payload),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ToolBatchSnapshot":
        data = _strict_mapping(
            value,
            "tool_batch",
            {
                "schema_version",
                "batch_id",
                "slots",
                "completion_order",
                "declaration_order",
                "closed",
                "decision",
            },
        )
        declared_order = tuple(data.pop("declaration_order"))
        data["decision_payload"] = data.pop("decision")
        data["slots"] = tuple(ToolSlotSnapshot.from_dict(item) for item in data["slots"])
        data["completion_order"] = tuple(data["completion_order"])
        result = cls(**data)
        if result.declaration_order != declared_order:
            raise ValueError("tool batch declaration order is inconsistent")
        return result


@dataclass(frozen=True)
class ToolTerminalReceipt:
    disposition: TerminalDisposition
    slot: ToolSlotSnapshot
    lifecycle: ToolLifecycleReceipt
    effect: ToolEffectReceipt
    batch_snapshot: ToolBatchSnapshot
    schema_version: str = TOOL_TERMINAL_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TOOL_TERMINAL_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported terminal receipt version")
        if self.slot.slot_id not in {
            candidate.slot_id for candidate in self.batch_snapshot.slots
        }:
            raise ValueError("terminal receipt slot is absent from batch snapshot")

    @property
    def result(self) -> ToolResult:
        if self.slot.result is None:
            raise ValueError("terminal receipt has no result")
        return self.slot.result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "disposition": self.disposition.value,
            "slot": self.slot.to_dict(),
            "lifecycle": self.lifecycle.to_dict(),
            "effect": self.effect.to_dict(),
            "batch_snapshot": self.batch_snapshot.to_dict(),
        }


@dataclass(frozen=True)
class ToolBatchExecution:
    snapshot: ToolBatchSnapshot
    terminal_receipts: tuple[ToolTerminalReceipt, ...]

    @property
    def results_in_declaration_order(self) -> tuple[ToolResult, ...]:
        return self.snapshot.results_in_declaration_order

    @property
    def results_in_completion_order(self) -> tuple[ToolResult, ...]:
        return self.snapshot.results_in_completion_order


TerminalResultCallback = Callable[[ToolTerminalReceipt], None]
PartialBatchCallback = Callable[[ToolBatchSnapshot], None]


class ToolEffectPolicy(Protocol):
    """Replaceable effect declaration/finalization policy."""

    def declare(
        self,
        action: "Action",
        tool: Optional["BaseTool"],
        runtime_context: Dict[str, Any],
    ) -> Optional[ToolEffectDeclaration]:
        ...

    def finalize(
        self,
        declaration: Optional[ToolEffectDeclaration],
        result: ToolResult,
        *,
        dispatched: bool,
    ) -> ToolEffectReceipt:
        ...


class ToolLifecycleAdapter(Protocol):
    """Resource-family adapter; cancellation remains capability-specific."""

    @property
    def spec(self) -> ToolLifecycleSpec:
        ...

    def request_cancel(self, attempt_id: AttemptIdentity) -> bool:
        ...

    def wait_completed(self, attempt_id: AttemptIdentity, timeout: float) -> bool:
        ...


class ToolExecutorProtocol(Protocol):
    """Conformance seam for the reference and third-party executors."""

    def execute_one(
        self,
        action: "Action",
        *,
        terminal_callback: Optional[TerminalResultCallback] = None,
        env: Any = None,
        state: Any = None,
        batch_id: Optional[str] = None,
        owner_generation: int = 0,
    ) -> ToolResult:
        ...

    def execute_batch(
        self,
        actions: Sequence["Action"],
        *,
        terminal_callback: Optional[TerminalResultCallback] = None,
        partial_batch_callback: Optional[PartialBatchCallback] = None,
        env: Any = None,
        state: Any = None,
        batch_id: Optional[str] = None,
        owner_generation: int = 0,
    ) -> ToolBatchExecution:
        ...


def _require_json(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if math.isfinite(value):
            return
        raise ValueError(f"{path} must be finite")
    if isinstance(value, list):
        for index, item in enumerate(value):
            _require_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} keys must be strings")
            _require_json(item, f"{path}.{key}")
        return
    raise ValueError(f"{path} contains non-JSON value {type(value).__name__}")


def _clone_json(value: Any) -> Any:
    _require_json(value, "value")
    if isinstance(value, list):
        return [_clone_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _clone_json(item) for key, item in value.items()}
    return value


def _strict_mapping(value: Any, path: str, fields: set[str]) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError(f"{path} shape is invalid")
    return dict(value)


def _encode_tool_batch_component(value: Any) -> Mapping[str, Any]:
    if value is not None and not isinstance(value, ToolBatchSnapshot):
        raise TypeError("tool-batch component requires ToolBatchSnapshot or None")
    return {
        "schema_version": TOOL_BATCH_COMPONENT_SCHEMA_VERSION,
        "batch": value.to_dict() if value is not None else None,
    }


def _decode_tool_batch_component(value: Any) -> Optional[ToolBatchSnapshot]:
    data = _strict_mapping(
        value,
        "tool_batch_component",
        {"schema_version", "batch"},
    )
    if data["schema_version"] != TOOL_BATCH_COMPONENT_SCHEMA_VERSION:
        raise ValueError("unsupported tool-batch component schema")
    return (
        ToolBatchSnapshot.from_dict(data["batch"])
        if data["batch"] is not None
        else None
    )


TOOL_BATCH_SNAPSHOT_COMPONENT_CODEC = SnapshotComponentCodec(
    slot="tool_batch",
    owner="qitos.tool_runtime",
    schema_version=TOOL_BATCH_COMPONENT_SCHEMA_VERSION,
    required=True,
    encode=_encode_tool_batch_component,
    decode=_decode_tool_batch_component,
)


__all__ = [
    "TOOL_BATCH_SNAPSHOT_SCHEMA_VERSION",
    "TOOL_BATCH_COMPONENT_SCHEMA_VERSION",
    "TOOL_BATCH_SNAPSHOT_COMPONENT_CODEC",
    "TOOL_EFFECT_RECEIPT_SCHEMA_VERSION",
    "TOOL_LIFECYCLE_MATRIX",
    "TOOL_LIFECYCLE_RECEIPT_SCHEMA_VERSION",
    "TOOL_TERMINAL_RECEIPT_SCHEMA_VERSION",
    "CancellationCapability",
    "EffectDeclarationFactory",
    "MigrationDisposition",
    "PartialBatchCallback",
    "TerminalDisposition",
    "TerminalResultCallback",
    "ToolBatchExecution",
    "ToolBatchSnapshot",
    "ToolEffectDeclaration",
    "ToolEffectPolicy",
    "ToolEffectReceipt",
    "ToolExecutorProtocol",
    "ToolLifecycleAdapter",
    "ToolLifecycleReceipt",
    "ToolLifecycleSpec",
    "ToolLifecycleState",
    "ToolResourceKind",
    "ToolSlotSnapshot",
    "ToolTerminalReceipt",
]
