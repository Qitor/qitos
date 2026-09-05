"""Durable multi-agent ownership records without scheduling behavior.

``WorkGraph`` is the sole control-plane truth for child work and ownership.
It records generation-checked mutations; it does not start workers or Engines.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Dict, Iterable, Literal, Mapping, Type, TypeVar

from .diagnostics import diagnostic_string_is_sensitive, safe_diagnostic_text
from .session import (
    AgentIdentity,
    AttemptIdentity,
    RuntimeIdentity,
    SessionIdentity,
    SnapshotComponentCodec,
    WorkItemIdentity,
)
from .tool_result import ToolResult


WORK_GRAPH_SCHEMA_VERSION = "qitos.work_graph/v4"
WORK_DESCRIPTOR_SCHEMA_VERSION = "qitos.work_descriptor/v1"
WORK_GRAPH_SNAPSHOT_COMPONENT_VERSION = "qitos.work_graph.snapshot_component/v3"

WorkLifecycle = Literal[
    "created",
    "running",
    "paused",
    "waiting_input",
    "completed",
    "failed",
    "cancelled",
]
WorkOperation = Literal["handoff", "delegate", "spawn", "fan_out"]
AttemptState = Literal[
    "accepted",
    "running",
    "completed",
    "failed",
    "timed_out",
    "cancelled",
    "unknown",
]
JoinPolicy = Literal["all", "all_successful", "first_success", "quorum"]
CompletionDisposition = Literal[
    "committed",
    "duplicate_ignored",
    "stale_owner_rejected",
    "late_terminal_rejected",
]

_LIFECYCLES = frozenset(
    {"created", "running", "paused", "waiting_input", "completed", "failed", "cancelled"}
)
_OPERATIONS = frozenset({"handoff", "delegate", "spawn", "fan_out"})
_ATTEMPT_STATES = frozenset(
    {"accepted", "running", "completed", "failed", "timed_out", "cancelled", "unknown"}
)
_JOIN_POLICIES = frozenset({"all", "all_successful", "first_success", "quorum"})
_TERMINAL = frozenset({"completed", "failed", "cancelled"})
_DURABLE_OPERATIONS = frozenset(
    {"handoff", "delegate", "spawn", "fan_out", "join", "cancellation", "detach", "terminal_completion"}
)
_OPERATION_STATES = frozenset(
    {
        "declared", "dispatchable", "queued", "dispatched", "running", "completed", "failed",
        "cancelled", "cancellation_requested_worker_still_running", "outcome_unknown",
        "rejected", "transfer_admitted", "ownership_committed",
    }
)
_MAX_GRAPH_DEPTH = 32
_MAX_FAN_OUT_WIDTH = 64


class WorkGraphContractError(ValueError):
    """Typed strict-reader or ownership-transition failure."""

    def __init__(self, code: str, message: str):
        self.code = str(code)
        safe = safe_diagnostic_text(message, fallback="work graph contract rejected input")
        super().__init__(f"{self.code}: {safe}")


def _fail(code: str, message: str) -> WorkGraphContractError:
    return WorkGraphContractError(code, message)


def _clone_json(value: Any, path: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _fail("non_json_value", f"{path} must be finite")
        return value
    if isinstance(value, list):
        return [_clone_json(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, dict):
        result: Dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise _fail("non_json_value", f"{path} keys must be strings")
            result[key] = _clone_json(item, f"{path}.{key}")
        return result
    raise _fail("non_json_value", f"{path} contains {type(value).__name__}")


def _identifier(value: Any, path: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or diagnostic_string_is_sensitive(value)
    ):
        raise _fail("invalid_identifier", f"{path} must be a non-empty string")
    return value.strip()


_IdentityT = TypeVar("_IdentityT", bound=RuntimeIdentity)


def _identity(value: Any, identity_type: Type[_IdentityT], path: str) -> _IdentityT:
    if not isinstance(value, identity_type):
        raise _fail("invalid_identity_kind", f"{path} must use {identity_type.__name__}")
    return value


def _optional_identity(
    value: Any, identity_type: Type[_IdentityT], path: str
) -> _IdentityT | None:
    if value is None:
        return None
    return _identity(value, identity_type, path)


def _optional_identifier(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, path)


def _generation(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise _fail("invalid_generation", f"{path} must be a non-negative integer")
    return value


def _strict(data: Mapping[str, Any], fields: set[str], path: str) -> Dict[str, Any]:
    if not isinstance(data, Mapping):
        raise _fail("invalid_record", f"{path} must be an object")
    result = dict(data)
    unknown = sorted(set(result) - fields)
    if unknown:
        raise _fail("unknown_field", f"{path} has unknown field {unknown[0]!r}")
    missing = sorted(fields - set(result))
    if missing:
        raise _fail("missing_field", f"{path} is missing {missing[0]!r}")
    return result


def _record_dict(record: Any) -> Dict[str, Any]:
    def encode(value: Any) -> Any:
        if isinstance(value, RuntimeIdentity):
            return value.to_dict()
        if is_dataclass(value):
            return {item.name: encode(getattr(value, item.name)) for item in fields(value)}
        if isinstance(value, dict):
            return {str(key): encode(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [encode(item) for item in value]
        return value

    return _clone_json(encode(record), type(record).__name__)


@dataclass(frozen=True)
class WorkOwner:
    agent_id: AgentIdentity
    generation: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "agent_id", _identity(self.agent_id, AgentIdentity, "owner.agent_id")
        )
        object.__setattr__(self, "generation", _generation(self.generation, "owner.generation"))


@dataclass(frozen=True)
class WorkAttempt:
    attempt_id: AttemptIdentity
    work_item_id: WorkItemIdentity
    owner_generation: int
    state: AttemptState
    worker_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "attempt_id", _identity(self.attempt_id, AttemptIdentity, "attempt_id"))
        object.__setattr__(self, "work_item_id", _identity(self.work_item_id, WorkItemIdentity, "work_item_id"))
        object.__setattr__(
            self,
            "owner_generation",
            _generation(self.owner_generation, "owner_generation"),
        )
        if self.state not in _ATTEMPT_STATES:
            raise _fail("invalid_attempt_state", f"unsupported state {self.state!r}")
        object.__setattr__(self, "worker_ref", _optional_identifier(self.worker_ref, "worker_ref"))


@dataclass(frozen=True)
class WorkItem:
    work_item_id: WorkItemIdentity
    session_ref: SessionIdentity
    task_ref: str
    lifecycle: WorkLifecycle
    owner: WorkOwner
    parent_work_item_id: WorkItemIdentity | None = None
    detached: bool = False
    budget_allocation_ref: str | None = None
    capability_allocation_ref: str | None = None
    context_transfer_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "work_item_id", _identity(self.work_item_id, WorkItemIdentity, "work_item_id"))
        object.__setattr__(self, "session_ref", _identity(self.session_ref, SessionIdentity, "session_ref"))
        object.__setattr__(self, "task_ref", _identifier(self.task_ref, "task_ref"))
        if self.lifecycle not in _LIFECYCLES:
            raise _fail("invalid_work_lifecycle", f"unsupported lifecycle {self.lifecycle!r}")
        if not isinstance(self.owner, WorkOwner):
            raise _fail("invalid_owner", "owner must be WorkOwner")
        object.__setattr__(
            self,
            "parent_work_item_id",
            _optional_identity(self.parent_work_item_id, WorkItemIdentity, "parent_work_item_id"),
        )
        for name in (
            "budget_allocation_ref",
            "capability_allocation_ref",
            "context_transfer_ref",
        ):
            object.__setattr__(self, name, _optional_identifier(getattr(self, name), name))
        if not isinstance(self.detached, bool):
            raise _fail("invalid_record", "detached must be boolean")


@dataclass(frozen=True)
class WorkEdge:
    edge_id: str
    operation: WorkOperation
    source_work_item_id: WorkItemIdentity
    target_work_item_id: WorkItemIdentity
    declaration_order: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "edge_id", _identifier(self.edge_id, "edge_id"))
        object.__setattr__(self, "source_work_item_id", _identity(self.source_work_item_id, WorkItemIdentity, "source_work_item_id"))
        object.__setattr__(self, "target_work_item_id", _identity(self.target_work_item_id, WorkItemIdentity, "target_work_item_id"))
        if self.operation not in _OPERATIONS:
            raise _fail("invalid_operation", f"unsupported operation {self.operation!r}")
        object.__setattr__(
            self,
            "declaration_order",
            _generation(self.declaration_order, "declaration_order"),
        )


@dataclass(frozen=True)
class OwnershipTransfer:
    transfer_id: str
    work_item_id: WorkItemIdentity
    expected_generation: int
    committed_generation: int
    from_agent_id: AgentIdentity
    to_agent_id: AgentIdentity
    context_transfer_ref: str | None
    reason: str

    def __post_init__(self) -> None:
        for name in ("transfer_id", "reason"):
            object.__setattr__(self, name, _identifier(getattr(self, name), name))
        object.__setattr__(self, "work_item_id", _identity(self.work_item_id, WorkItemIdentity, "work_item_id"))
        object.__setattr__(self, "from_agent_id", _identity(self.from_agent_id, AgentIdentity, "from_agent_id"))
        object.__setattr__(self, "to_agent_id", _identity(self.to_agent_id, AgentIdentity, "to_agent_id"))
        expected = _generation(self.expected_generation, "expected_generation")
        committed = _generation(self.committed_generation, "committed_generation")
        if committed != expected + 1:
            raise _fail("invalid_generation", "transfer generation must advance by one")
        object.__setattr__(self, "expected_generation", expected)
        object.__setattr__(self, "committed_generation", committed)
        object.__setattr__(
            self,
            "context_transfer_ref",
            _optional_identifier(self.context_transfer_ref, "context_transfer_ref"),
        )


@dataclass(frozen=True)
class DelegationRecord:
    delegation_id: str
    parent_work_item_id: WorkItemIdentity
    child_work_item_id: WorkItemIdentity
    await_child: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "delegation_id", _identifier(self.delegation_id, "delegation_id"))
        object.__setattr__(self, "parent_work_item_id", _identity(self.parent_work_item_id, WorkItemIdentity, "parent_work_item_id"))
        object.__setattr__(self, "child_work_item_id", _identity(self.child_work_item_id, WorkItemIdentity, "child_work_item_id"))
        if not isinstance(self.await_child, bool):
            raise _fail("invalid_delegation", "await_child must be boolean")


@dataclass(frozen=True)
class SpawnRecord:
    spawn_id: str
    parent_work_item_id: WorkItemIdentity
    child_work_item_id: WorkItemIdentity
    supervision_policy: str

    def __post_init__(self) -> None:
        for name in ("spawn_id", "supervision_policy"):
            object.__setattr__(self, name, _identifier(getattr(self, name), name))
        object.__setattr__(self, "parent_work_item_id", _identity(self.parent_work_item_id, WorkItemIdentity, "parent_work_item_id"))
        object.__setattr__(self, "child_work_item_id", _identity(self.child_work_item_id, WorkItemIdentity, "child_work_item_id"))


@dataclass(frozen=True)
class FanOutGroup:
    group_id: str
    parent_work_item_id: WorkItemIdentity
    child_work_item_ids: list[WorkItemIdentity]

    def __post_init__(self) -> None:
        object.__setattr__(self, "group_id", _identifier(self.group_id, "group_id"))
        object.__setattr__(
            self,
            "parent_work_item_id",
            _identity(self.parent_work_item_id, WorkItemIdentity, "parent_work_item_id"),
        )
        children = [
            _identity(item, WorkItemIdentity, "child_work_item_id") for item in self.child_work_item_ids
        ]
        if not children or len(children) != len(set(children)):
            raise _fail("invalid_fan_out", "fan_out children must be non-empty and unique")
        object.__setattr__(self, "child_work_item_ids", children)


@dataclass(frozen=True)
class JoinDependency:
    join_id: str
    parent_work_item_id: WorkItemIdentity
    child_work_item_ids: list[WorkItemIdentity]
    policy: JoinPolicy
    quorum: int | None = None
    accepted_child_ids: list[WorkItemIdentity] = field(default_factory=list)
    generation: int = 0
    reducer_ref: str | None = None
    reducer_digest: str | None = None
    state: Literal["open", "closing", "closed"] = "open"
    outstanding_child_ids: list[WorkItemIdentity] = field(default_factory=list)
    completion_order: list[WorkItemIdentity] = field(default_factory=list)
    discarded_child_ids: list[WorkItemIdentity] = field(default_factory=list)
    terminal_receipt_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "join_id", _identifier(self.join_id, "join_id"))
        object.__setattr__(
            self,
            "parent_work_item_id",
            _identity(self.parent_work_item_id, WorkItemIdentity, "parent_work_item_id"),
        )
        children = [
            _identity(item, WorkItemIdentity, "child_work_item_id") for item in self.child_work_item_ids
        ]
        accepted = [
            _identity(item, WorkItemIdentity, "accepted_child_id") for item in self.accepted_child_ids
        ]
        raw_outstanding = self.outstanding_child_ids
        if (
            not raw_outstanding
            and self.state == "open"
            and not accepted
            and not self.completion_order
        ):
            raw_outstanding = children
        outstanding = [
            _identity(item, WorkItemIdentity, "outstanding_child_id")
            for item in raw_outstanding
        ]
        completion_order = [
            _identity(item, WorkItemIdentity, "completion_child_id")
            for item in self.completion_order
        ]
        discarded = [
            _identity(item, WorkItemIdentity, "discarded_child_id")
            for item in self.discarded_child_ids
        ]
        if not children or len(children) != len(set(children)):
            raise _fail("invalid_join", "join children must be non-empty and unique")
        if len(accepted) != len(set(accepted)) or not set(accepted).issubset(children):
            raise _fail("undeclared_join_child", "accepted child was not declared")
        if self.policy not in _JOIN_POLICIES:
            raise _fail("invalid_join_policy", f"unsupported policy {self.policy!r}")
        if self.policy == "quorum":
            if (
                not isinstance(self.quorum, int)
                or isinstance(self.quorum, bool)
                or not 1 <= self.quorum <= len(children)
            ):
                raise _fail("invalid_join", "quorum must fit the declared child count")
        elif self.quorum is not None:
            raise _fail("invalid_join", "quorum is legal only for quorum policy")
        for label, values in (
            ("outstanding", outstanding),
            ("completion", completion_order),
            ("discarded", discarded),
        ):
            if len(values) != len(set(values)) or not set(values).issubset(children):
                raise _fail("invalid_join", f"{label} children must be unique and declared")
        if set(outstanding) & set(accepted):
            raise _fail("invalid_join", "accepted children cannot remain outstanding")
        object.__setattr__(self, "generation", _generation(self.generation, "join.generation"))
        object.__setattr__(self, "reducer_ref", _optional_identifier(self.reducer_ref, "reducer_ref"))
        object.__setattr__(self, "reducer_digest", _optional_identifier(self.reducer_digest, "reducer_digest"))
        if (self.reducer_ref is None) != (self.reducer_digest is None):
            raise _fail("invalid_join", "reducer reference and digest must be declared together")
        if self.state not in {"open", "closing", "closed"}:
            raise _fail("invalid_join", "unsupported join state")
        if self.state == "closed" and self.terminal_receipt_ref is None:
            raise _fail("invalid_join", "closed join requires a terminal receipt")
        object.__setattr__(
            self,
            "terminal_receipt_ref",
            _optional_identifier(self.terminal_receipt_ref, "terminal_receipt_ref"),
        )
        object.__setattr__(self, "child_work_item_ids", children)
        object.__setattr__(self, "accepted_child_ids", accepted)
        object.__setattr__(self, "outstanding_child_ids", outstanding)
        object.__setattr__(self, "completion_order", completion_order)
        object.__setattr__(self, "discarded_child_ids", discarded)


@dataclass(frozen=True)
class CancellationRequest:
    cancellation_id: str
    work_item_id: WorkItemIdentity
    requested_generation: int
    propagation: Literal["propagate", "detach", "request_and_wait"]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "cancellation_id", _identifier(self.cancellation_id, "cancellation_id")
        )
        object.__setattr__(
            self, "work_item_id", _identity(self.work_item_id, WorkItemIdentity, "work_item_id")
        )
        object.__setattr__(
            self,
            "requested_generation",
            _generation(self.requested_generation, "requested_generation"),
        )
        if self.propagation not in {"propagate", "detach", "request_and_wait"}:
            raise _fail("invalid_cancellation", "unsupported propagation policy")


@dataclass(frozen=True)
class DetachmentRecord:
    detachment_id: str
    parent_work_item_id: WorkItemIdentity
    child_work_item_id: WorkItemIdentity
    supervisor_ref: str

    def __post_init__(self) -> None:
        for name in ("detachment_id", "supervisor_ref"):
            object.__setattr__(self, name, _identifier(getattr(self, name), name))
        object.__setattr__(self, "parent_work_item_id", _identity(self.parent_work_item_id, WorkItemIdentity, "parent_work_item_id"))
        object.__setattr__(self, "child_work_item_id", _identity(self.child_work_item_id, WorkItemIdentity, "child_work_item_id"))


@dataclass(frozen=True)
class WorkCompletion:
    completion_id: str
    work_item_id: WorkItemIdentity
    owner_generation: int
    outcome: Dict[str, Any]
    outcome_digest: str

    def __post_init__(self) -> None:
        for name in ("completion_id", "outcome_digest"):
            object.__setattr__(self, name, _identifier(getattr(self, name), name))
        object.__setattr__(self, "work_item_id", _identity(self.work_item_id, WorkItemIdentity, "work_item_id"))
        object.__setattr__(
            self,
            "owner_generation",
            _generation(self.owner_generation, "owner_generation"),
        )
        outcome = ToolResult.from_canonical_dict(self.outcome).to_persistence_dict()
        digest = hashlib.sha256(
            json.dumps(outcome, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        if self.outcome_digest != digest:
            raise _fail("outcome_digest_mismatch", "completion digest does not match outcome")
        object.__setattr__(self, "outcome", outcome)


@dataclass(frozen=True)
class LateResult:
    late_result_id: str
    work_item_id: WorkItemIdentity
    owner_generation: int
    reason: Literal["stale_owner", "terminal_state", "cancelled"]
    outcome: Dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "late_result_id", _identifier(self.late_result_id, "late_result_id"))
        object.__setattr__(self, "work_item_id", _identity(self.work_item_id, WorkItemIdentity, "work_item_id"))
        object.__setattr__(
            self,
            "owner_generation",
            _generation(self.owner_generation, "owner_generation"),
        )
        if self.reason not in {"stale_owner", "terminal_state", "cancelled"}:
            raise _fail("invalid_late_result", "unsupported rejection reason")
        outcome = ToolResult.from_canonical_dict(self.outcome).to_persistence_dict()
        object.__setattr__(self, "outcome", outcome)


@dataclass(frozen=True)
class BudgetAllocation:
    allocation_id: str
    parent_work_item_id: WorkItemIdentity
    child_work_item_id: WorkItemIdentity
    limits: Dict[str, Any]
    reclaim_policy: Literal["return_unused", "no_reclaim"] = "return_unused"

    def __post_init__(self) -> None:
        object.__setattr__(self, "allocation_id", _identifier(self.allocation_id, "allocation_id"))
        object.__setattr__(self, "parent_work_item_id", _identity(self.parent_work_item_id, WorkItemIdentity, "parent_work_item_id"))
        object.__setattr__(self, "child_work_item_id", _identity(self.child_work_item_id, WorkItemIdentity, "child_work_item_id"))
        object.__setattr__(self, "limits", _clone_json(self.limits, "limits"))
        if self.reclaim_policy not in {"return_unused", "no_reclaim"}:
            raise _fail("invalid_budget", "unsupported reclaim policy")


@dataclass(frozen=True)
class CapabilityAllocation:
    allocation_id: str
    parent_work_item_id: WorkItemIdentity
    child_work_item_id: WorkItemIdentity
    capabilities: list[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "allocation_id", _identifier(self.allocation_id, "allocation_id"))
        object.__setattr__(self, "parent_work_item_id", _identity(self.parent_work_item_id, WorkItemIdentity, "parent_work_item_id"))
        object.__setattr__(self, "child_work_item_id", _identity(self.child_work_item_id, WorkItemIdentity, "child_work_item_id"))
        capabilities = [_identifier(item, "capability") for item in self.capabilities]
        if len(capabilities) != len(set(capabilities)):
            raise _fail("invalid_capability", "capabilities must be unique")
        object.__setattr__(self, "capabilities", capabilities)


@dataclass(frozen=True)
class WorkDescriptor:
    """Reconstructable work declaration; contains references, never live objects."""

    operation_id: str
    operation: str
    parent_session_id: str
    parent_work_item_id: str
    child_session_ids: list[str]
    child_work_item_ids: list[str]
    agent_refs: list[Dict[str, Any]]
    task_input: Dict[str, Any]
    fork_receipts: list[Dict[str, Any]]
    transfer_receipts: list[Dict[str, Any]]
    budget_allocations: list[Dict[str, Any]]
    capability_allocations: list[Dict[str, Any]]
    artifact_refs: list[Dict[str, Any]]
    resolver_requirements: list[Dict[str, Any]]
    graph_depth: int
    fan_out_width: int
    schema_version: str = WORK_DESCRIPTOR_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != WORK_DESCRIPTOR_SCHEMA_VERSION:
            raise _fail("unknown_schema_version", "unsupported work descriptor version")
        for name in (
            "operation_id", "operation", "parent_session_id", "parent_work_item_id"
        ):
            object.__setattr__(self, name, _identifier(getattr(self, name), name))
        if self.operation not in _DURABLE_OPERATIONS:
            raise _fail("invalid_operation", "unsupported descriptor operation")
        for name in ("child_session_ids", "child_work_item_ids"):
            values = [_identifier(item, name) for item in getattr(self, name)]
            if len(values) != len(set(values)):
                raise _fail("duplicate_identity", f"{name} must be unique")
            object.__setattr__(self, name, values)
        if len(self.child_session_ids) != len(self.child_work_item_ids):
            raise _fail("invalid_descriptor", "child Session/work identities must align")
        for name in (
            "agent_refs", "fork_receipts", "transfer_receipts",
            "budget_allocations", "capability_allocations", "artifact_refs",
            "resolver_requirements",
        ):
            value = _clone_json(getattr(self, name), name)
            _reject_unsafe_descriptor_value(value, name)
            object.__setattr__(self, name, value)
        task_input = _clone_json(self.task_input, "task_input")
        _reject_unsafe_descriptor_value(task_input, "task_input")
        object.__setattr__(self, "task_input", task_input)
        object.__setattr__(self, "graph_depth", _generation(self.graph_depth, "graph_depth"))
        width = _generation(self.fan_out_width, "fan_out_width")
        if width < 1 or width > _MAX_FAN_OUT_WIDTH:
            raise _fail("fan_out_width_exceeded", "descriptor fan-out width is invalid")
        object.__setattr__(self, "fan_out_width", width)

    def to_dict(self) -> Dict[str, Any]:
        return _record_dict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorkDescriptor":
        fields = {
            "schema_version", "operation_id", "operation", "parent_session_id",
            "parent_work_item_id", "child_session_ids", "child_work_item_ids",
            "agent_refs", "task_input", "fork_receipts", "transfer_receipts",
            "budget_allocations", "capability_allocations", "artifact_refs",
            "resolver_requirements", "graph_depth", "fan_out_width",
        }
        return cls(**_strict(payload, fields, "WorkDescriptor"))


@dataclass(frozen=True)
class WorkOperationReceipt:
    """Durable idempotency and dispatch fact for one logical operation."""

    operation_id: str
    operation: str
    payload_digest: str
    state: str
    generation: int = 0
    attempt: int = 0
    worker_ref: str | None = None
    outcome_unknown: bool = False
    terminal_receipt_ref: str | None = None
    descriptor: Dict[str, Any] | None = None
    admission_state: str = "eligible"
    queue_position: int | None = None

    def __post_init__(self) -> None:
        for name in ("operation_id", "operation", "payload_digest", "state"):
            object.__setattr__(self, name, _identifier(getattr(self, name), name))
        if self.operation not in _DURABLE_OPERATIONS:
            raise _fail("invalid_operation", "unsupported durable operation")
        if self.state not in _OPERATION_STATES:
            raise _fail("invalid_operation_state", "unsupported durable operation state")
        object.__setattr__(self, "generation", _generation(self.generation, "generation"))
        object.__setattr__(self, "attempt", _generation(self.attempt, "attempt"))
        object.__setattr__(self, "worker_ref", _optional_identifier(self.worker_ref, "worker_ref"))
        object.__setattr__(
            self,
            "terminal_receipt_ref",
            _optional_identifier(self.terminal_receipt_ref, "terminal_receipt_ref"),
        )
        if not isinstance(self.outcome_unknown, bool):
            raise _fail("invalid_record", "outcome_unknown must be boolean")
        if self.descriptor is not None:
            descriptor = WorkDescriptor.from_dict(self.descriptor).to_dict()
            if descriptor["operation_id"] != self.operation_id:
                raise _fail("identity_mismatch", "descriptor operation identity mismatched")
            object.__setattr__(self, "descriptor", descriptor)
        if self.admission_state not in {"eligible", "admitted", "queued", "closed"}:
            raise _fail("invalid_admission", "unsupported admission state")
        if self.queue_position is not None:
            object.__setattr__(
                self, "queue_position", _generation(self.queue_position, "queue_position")
            )


def _reject_unsafe_descriptor_value(value: Any, path: str) -> None:
    if isinstance(value, str):
        if diagnostic_string_is_sensitive(value):
            raise _fail("unsafe_descriptor_value", f"{path} contains non-portable data")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_unsafe_descriptor_value(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if any(token in key.lower() for token in ("secret", "password", "credential", "token")):
                raise _fail("unsafe_descriptor_value", f"{path} contains a forbidden field")
            _reject_unsafe_descriptor_value(item, f"{path}.{key}")


@dataclass(frozen=True)
class WorkGraphSnapshotComponent:
    graph_ref: str
    unresolved_work_item_ids: list[WorkItemIdentity]
    graph: Dict[str, Any] | None = None
    schema_version: str = WORK_GRAPH_SNAPSHOT_COMPONENT_VERSION

    def to_dict(self) -> Dict[str, Any]:
        if self.schema_version != WORK_GRAPH_SNAPSHOT_COMPONENT_VERSION:
            raise _fail("unknown_schema_version", "unsupported snapshot component")
        _identifier(self.graph_ref, "graph_ref")
        for index, item in enumerate(self.unresolved_work_item_ids):
            _identity(item, WorkItemIdentity, f"unresolved_work_item_ids[{index}]")
        if len(set(self.unresolved_work_item_ids)) != len(self.unresolved_work_item_ids):
            raise _fail("duplicate_identity", "unresolved work identities must be unique")
        if self.graph is not None:
            canonical = WorkGraph.from_canonical_dict(self.graph).to_persistence_dict()
            if canonical["graph_id"] != self.graph_ref:
                raise _fail("identity_mismatch", "snapshot graph_ref must match graph identity")
            object.__setattr__(self, "graph", canonical)
        return _record_dict(self)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "WorkGraphSnapshotComponent":
        data = _strict(
            payload,
            {"schema_version", "graph_ref", "unresolved_work_item_ids", "graph"},
            "snapshot_component",
        )
        unresolved = data["unresolved_work_item_ids"]
        if not isinstance(unresolved, list):
            raise _fail("invalid_record", "unresolved_work_item_ids must be an array")
        return cls(
            graph_ref=data["graph_ref"],
            unresolved_work_item_ids=[WorkItemIdentity.from_dict(item) for item in unresolved],
            graph=data["graph"],
            schema_version=data["schema_version"],
        )


def _encode_work_graph_component(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, WorkGraphSnapshotComponent):
        raise _fail("invalid_record", "work-graph codec requires its component type")
    return value.to_dict()


WORK_GRAPH_SNAPSHOT_COMPONENT_CODEC = SnapshotComponentCodec(
    slot="work_graph",
    owner="qitos.work_graph",
    schema_version=WORK_GRAPH_SNAPSHOT_COMPONENT_VERSION,
    required=True,
    encode=_encode_work_graph_component,
    decode=WorkGraphSnapshotComponent.from_dict,
)


@dataclass
class WorkGraph:
    """Versioned ownership graph and generation-checked record builder."""

    graph_id: str
    work_items: Dict[WorkItemIdentity, WorkItem] = field(default_factory=dict)
    attempts: list[WorkAttempt] = field(default_factory=list)
    edges: list[WorkEdge] = field(default_factory=list)
    transfers: list[OwnershipTransfer] = field(default_factory=list)
    delegations: list[DelegationRecord] = field(default_factory=list)
    spawns: list[SpawnRecord] = field(default_factory=list)
    fan_out_groups: list[FanOutGroup] = field(default_factory=list)
    joins: list[JoinDependency] = field(default_factory=list)
    cancellations: list[CancellationRequest] = field(default_factory=list)
    detachments: list[DetachmentRecord] = field(default_factory=list)
    completions: list[WorkCompletion] = field(default_factory=list)
    late_results: list[LateResult] = field(default_factory=list)
    budget_allocations: list[BudgetAllocation] = field(default_factory=list)
    capability_allocations: list[CapabilityAllocation] = field(default_factory=list)
    operation_receipts: list[WorkOperationReceipt] = field(default_factory=list)
    schema_version: str = WORK_GRAPH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.graph_id = _identifier(self.graph_id, "graph_id")
        if self.schema_version != WORK_GRAPH_SCHEMA_VERSION:
            raise _fail("unknown_schema_version", f"unsupported version {self.schema_version!r}")
        self.work_items = dict(self.work_items)
        for name in (
            "attempts", "edges", "transfers", "delegations", "spawns",
            "fan_out_groups", "joins", "cancellations", "detachments",
            "completions", "late_results", "budget_allocations",
            "capability_allocations",
            "operation_receipts",
        ):
            setattr(self, name, list(getattr(self, name)))
        self._validate_identity_sets()

    def _validate_identity_sets(self) -> None:
        for key, item in self.work_items.items():
            if key != item.work_item_id:
                raise _fail("identity_mismatch", "work item mapping key must match identity")
        groups: Iterable[tuple[str, Iterable[Any]]] = (
            ("attempt", (item.attempt_id for item in self.attempts)),
            ("edge", (item.edge_id for item in self.edges)),
            ("transfer", (item.transfer_id for item in self.transfers)),
            ("delegation", (item.delegation_id for item in self.delegations)),
            ("spawn", (item.spawn_id for item in self.spawns)),
            ("fan_out", (item.group_id for item in self.fan_out_groups)),
            ("join", (item.join_id for item in self.joins)),
            ("cancellation", (item.cancellation_id for item in self.cancellations)),
            ("detachment", (item.detachment_id for item in self.detachments)),
            ("completion", (item.completion_id for item in self.completions)),
            ("late_result", (item.late_result_id for item in self.late_results)),
            ("budget", (item.allocation_id for item in self.budget_allocations)),
            ("capability", (item.allocation_id for item in self.capability_allocations)),
            ("operation", (item.operation_id for item in self.operation_receipts)),
        )
        for label, identities in groups:
            values = list(identities)
            if len(values) != len(set(values)):
                raise _fail("duplicate_identity", f"duplicate {label} identity")

    def add_work_item(self, item: WorkItem) -> None:
        if item.work_item_id in self.work_items:
            raise _fail("duplicate_identity", "duplicate work item identity")
        self.work_items[item.work_item_id] = item

    def record_attempt(self, attempt: WorkAttempt) -> None:
        item = self._item(attempt.work_item_id)
        if attempt.owner_generation != item.owner.generation:
            raise _fail("stale_owner", "attempt generation is not authoritative")
        if any(existing.attempt_id == attempt.attempt_id for existing in self.attempts):
            raise _fail("duplicate_identity", "duplicate attempt identity")
        self.attempts.append(attempt)

    def transfer_owner(
        self,
        work_item_id: WorkItemIdentity,
        *,
        expected_generation: int,
        to_agent_id: AgentIdentity,
        transfer_id: str,
        context_transfer_ref: str | None = None,
        reason: str = "handoff",
    ) -> OwnershipTransfer:
        item = self._item(work_item_id)
        expected = _generation(expected_generation, "expected_generation")
        if item.owner.generation != expected:
            raise _fail("owner_generation_conflict", "ownership compare-and-set failed")
        if item.lifecycle in _TERMINAL:
            raise _fail("terminal_work_item", "terminal work cannot transfer ownership")
        new_owner = WorkOwner(_identity(to_agent_id, AgentIdentity, "to_agent_id"), expected + 1)
        transfer = OwnershipTransfer(
            transfer_id=_identifier(transfer_id, "transfer_id"),
            work_item_id=item.work_item_id,
            expected_generation=expected,
            committed_generation=new_owner.generation,
            from_agent_id=item.owner.agent_id,
            to_agent_id=new_owner.agent_id,
            context_transfer_ref=_optional_identifier(
                context_transfer_ref, "context_transfer_ref"
            ),
            reason=_identifier(reason, "reason"),
        )
        self._ensure_unique(transfer.transfer_id, (x.transfer_id for x in self.transfers))
        self.transfers.append(transfer)
        self.work_items[item.work_item_id] = _replace_work_item(
            item, owner=new_owner
        )
        return transfer

    def restore_owner(
        self,
        work_item_id: WorkItemIdentity,
        *,
        expected_generation: int,
        agent_id: AgentIdentity,
        transfer_id: str,
    ) -> OwnershipTransfer:
        return self.transfer_owner(
            work_item_id,
            expected_generation=expected_generation,
            to_agent_id=agent_id,
            transfer_id=transfer_id,
            reason="restore",
        )

    def add_delegation(
        self,
        *,
        delegation_id: str,
        edge_id: str,
        parent_work_item_id: WorkItemIdentity,
        child: WorkItem,
        await_child: bool = True,
    ) -> DelegationRecord:
        parent = self._item(parent_work_item_id)
        if parent.lifecycle in _TERMINAL:
            raise _fail("terminal_work_item", "terminal parent cannot delegate")
        if child.parent_work_item_id != parent_work_item_id or child.detached:
            raise _fail("invalid_delegation", "delegate child must be attached to parent")
        delegation_key = _identifier(delegation_id, "delegation_id")
        edge_key = _identifier(edge_id, "edge_id")
        self._ensure_unique(delegation_key, (x.delegation_id for x in self.delegations))
        self._prevalidate_child(child, edge_key)
        self.add_work_item(child)
        self._add_edge(edge_key, "delegate", parent_work_item_id, child.work_item_id)
        record = DelegationRecord(
            delegation_key,
            parent_work_item_id,
            child.work_item_id,
            bool(await_child),
        )
        self.delegations.append(record)
        return record

    def add_spawn(
        self,
        *,
        spawn_id: str,
        edge_id: str,
        parent_work_item_id: WorkItemIdentity,
        child: WorkItem,
        supervision_policy: str,
    ) -> SpawnRecord:
        parent = self._item(parent_work_item_id)
        if parent.lifecycle in _TERMINAL:
            raise _fail("terminal_work_item", "terminal parent cannot spawn")
        if child.parent_work_item_id != parent_work_item_id:
            raise _fail("invalid_spawn", "spawn child must name its parent")
        spawn_key = _identifier(spawn_id, "spawn_id")
        edge_key = _identifier(edge_id, "edge_id")
        policy = _identifier(supervision_policy, "supervision_policy")
        self._ensure_unique(spawn_key, (x.spawn_id for x in self.spawns))
        self._prevalidate_child(child, edge_key)
        self.add_work_item(child)
        self._add_edge(edge_key, "spawn", parent_work_item_id, child.work_item_id)
        record = SpawnRecord(
            spawn_key,
            parent_work_item_id,
            child.work_item_id,
            policy,
        )
        self.spawns.append(record)
        return record

    def add_fan_out(
        self,
        *,
        group_id: str,
        parent_work_item_id: WorkItemIdentity,
        children: list[WorkItem],
    ) -> FanOutGroup:
        parent = self._item(parent_work_item_id)
        if parent.lifecycle in _TERMINAL:
            raise _fail("terminal_work_item", "terminal parent cannot fan out")
        if not children:
            raise _fail("invalid_fan_out", "fan_out requires at least one child")
        if len(children) > _MAX_FAN_OUT_WIDTH:
            raise _fail("fan_out_width_exceeded", "fan_out exceeds configured graph bound")
        group_key = _identifier(group_id, "group_id")
        self._ensure_unique(group_key, (x.group_id for x in self.fan_out_groups))
        child_ids = [child.work_item_id for child in children]
        if len(child_ids) != len(set(child_ids)):
            raise _fail("duplicate_identity", "fan_out child identity is duplicated")
        for index, child in enumerate(children):
            if child.parent_work_item_id != parent_work_item_id or child.detached:
                raise _fail("invalid_fan_out", "fan_out children must be attached")
            self._prevalidate_child(child, f"{group_key}:edge:{index}")
        # All validation completes before the first graph mutation.
        for index, child in enumerate(children):
            self.add_work_item(child)
            self._add_edge(
                f"{group_key}:edge:{index}",
                "fan_out",
                parent_work_item_id,
                child.work_item_id,
            )
        group = FanOutGroup(
            group_key,
            parent_work_item_id,
            [item.work_item_id for item in children],
        )
        self.fan_out_groups.append(group)
        return group

    def declare_join(
        self,
        *,
        join_id: str,
        parent_work_item_id: WorkItemIdentity,
        child_work_item_ids: list[WorkItemIdentity],
        policy: JoinPolicy = "all",
        quorum: int | None = None,
        reducer_ref: str | None = None,
        reducer_digest: str | None = None,
    ) -> JoinDependency:
        self._item(parent_work_item_id)
        if policy not in _JOIN_POLICIES:
            raise _fail("invalid_join_policy", f"unsupported policy {policy!r}")
        children = [_identity(item, WorkItemIdentity, "child_work_item_id") for item in child_work_item_ids]
        if not children or len(children) != len(set(children)):
            raise _fail("invalid_join", "join children must be non-empty and unique")
        for child_id in children:
            child = self._item(child_id)
            if child.parent_work_item_id != parent_work_item_id:
                raise _fail("undeclared_join_child", "join child is not declared by the parent")
        if policy == "quorum":
            if not isinstance(quorum, int) or isinstance(quorum, bool) or not 1 <= quorum <= len(children):
                raise _fail("invalid_join", "quorum must be within the declared child count")
        elif quorum is not None:
            raise _fail("invalid_join", "quorum is legal only for quorum policy")
        join = JoinDependency(
            _identifier(join_id, "join_id"),
            parent_work_item_id,
            children,
            policy,
            quorum,
            [],
            0,
            reducer_ref,
            reducer_digest,
            "open",
            list(children),
            [],
            [],
            None,
        )
        self._ensure_unique(join.join_id, (x.join_id for x in self.joins))
        self.joins.append(join)
        return join

    def accept_join_result(self, join_id: str, child_work_item_id: WorkItemIdentity) -> None:
        join_index, join = self._join(join_id)
        child_id = _identity(child_work_item_id, WorkItemIdentity, "child_work_item_id")
        if child_id not in join.child_work_item_ids:
            raise _fail("undeclared_join_child", "join may consume only declared children")
        completion = next(
            (item for item in self.completions if item.work_item_id == child_id),
            None,
        )
        if completion is None:
            raise _fail("child_not_terminal", "join child has no committed completion")
        if join.state == "closed":
            if child_id not in join.discarded_child_ids and child_id not in join.accepted_child_ids:
                self.joins[join_index] = replace_join(
                    join,
                    discarded_child_ids=list(join.discarded_child_ids) + [child_id],
                )
            return
        if child_id in join.accepted_child_ids:
            return
        accepted = list(join.accepted_child_ids) + [child_id]
        outstanding = [item for item in join.outstanding_child_ids if item != child_id]
        order = list(join.completion_order) + [child_id]
        successful = [
            item for item in accepted
            if ToolResult.from_canonical_dict(
                next(entry for entry in self.completions if entry.work_item_id == item).outcome
            ).is_success
        ]
        closed = (
            (join.policy == "all" and not outstanding)
            or (join.policy == "all_successful" and not outstanding)
            or (join.policy == "first_success" and bool(successful))
            or (join.policy == "quorum" and len(successful) >= int(join.quorum or 0))
        )
        successful_close = not (
            join.policy == "all_successful"
            and closed
            and len(successful) != len(join.child_work_item_ids)
        )
        self.joins[join_index] = replace_join(
            join,
            accepted_child_ids=accepted,
            outstanding_child_ids=outstanding,
            completion_order=order,
            generation=join.generation + 1,
            state="closed" if closed else "open",
            terminal_receipt_ref=(
                f"{'join_terminal' if successful_close else 'join_failed'}:"
                f"{join.join_id}:{join.generation + 1}"
                if closed
                else None
            ),
        )

    def request_cancel(
        self,
        *,
        cancellation_id: str,
        work_item_id: WorkItemIdentity,
        expected_generation: int,
        propagation: Literal["propagate", "detach", "request_and_wait"],
    ) -> CancellationRequest:
        item = self._item(work_item_id)
        if item.owner.generation != expected_generation:
            raise _fail("owner_generation_conflict", "cancel generation is stale")
        if propagation not in {"propagate", "detach", "request_and_wait"}:
            raise _fail("invalid_cancellation", "unsupported propagation policy")
        record = CancellationRequest(
            _identifier(cancellation_id, "cancellation_id"),
            work_item_id,
            expected_generation,
            propagation,
        )
        self._ensure_unique(
            record.cancellation_id, (x.cancellation_id for x in self.cancellations)
        )
        self.cancellations.append(record)
        return record

    def detach_child(
        self,
        *,
        detachment_id: str,
        parent_work_item_id: WorkItemIdentity,
        child_work_item_id: WorkItemIdentity,
        supervisor_ref: str,
    ) -> DetachmentRecord:
        child = self._item(child_work_item_id)
        if child.parent_work_item_id != parent_work_item_id:
            raise _fail("invalid_detachment", "child is not attached to parent")
        record = DetachmentRecord(
            _identifier(detachment_id, "detachment_id"),
            parent_work_item_id,
            child_work_item_id,
            _identifier(supervisor_ref, "supervisor_ref"),
        )
        self._ensure_unique(record.detachment_id, (x.detachment_id for x in self.detachments))
        self.detachments.append(record)
        self.work_items[child_work_item_id] = _replace_work_item(
            child, detached=True
        )
        return record

    def record_completion(
        self,
        *,
        completion_id: str,
        work_item_id: WorkItemIdentity,
        owner_generation: int,
        outcome: ToolResult,
    ) -> CompletionDisposition:
        item = self._item(work_item_id)
        generation = _generation(owner_generation, "owner_generation")
        payload = outcome.to_persistence_dict()
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        existing = next(
            (entry for entry in self.completions if entry.work_item_id == work_item_id),
            None,
        )
        if existing is not None:
            if existing.outcome_digest == digest:
                return "duplicate_ignored"
            self._record_late(completion_id, item, generation, "terminal_state", payload)
            return "late_terminal_rejected"
        if generation != item.owner.generation:
            self._record_late(completion_id, item, generation, "stale_owner", payload)
            return "stale_owner_rejected"
        if item.lifecycle in _TERMINAL:
            reason: Literal["cancelled", "terminal_state"] = (
                "cancelled" if item.lifecycle == "cancelled" else "terminal_state"
            )
            self._record_late(completion_id, item, generation, reason, payload)
            return "late_terminal_rejected"
        completion = WorkCompletion(
            _identifier(completion_id, "completion_id"),
            work_item_id,
            generation,
            _clone_json(payload, "outcome"),
            digest,
        )
        self._ensure_unique(completion.completion_id, (x.completion_id for x in self.completions))
        self.completions.append(completion)
        lifecycle: WorkLifecycle = "completed" if outcome.is_success else "failed"
        self.work_items[work_item_id] = _replace_work_item(
            item, lifecycle=lifecycle
        )
        return "committed"

    def add_budget_allocation(self, allocation: BudgetAllocation) -> None:
        self._validate_child_allocation(
            allocation.parent_work_item_id, allocation.child_work_item_id
        )
        allocation = BudgetAllocation(
            _identifier(allocation.allocation_id, "allocation_id"),
            allocation.parent_work_item_id,
            allocation.child_work_item_id,
            _clone_json(allocation.limits, "limits"),
            allocation.reclaim_policy,
        )
        if allocation.reclaim_policy not in {"return_unused", "no_reclaim"}:
            raise _fail("invalid_budget", "unsupported reclaim policy")
        self._ensure_unique(allocation.allocation_id, (x.allocation_id for x in self.budget_allocations))
        if any(item.child_work_item_id == allocation.child_work_item_id for item in self.budget_allocations):
            raise _fail("duplicate_allocation", "child already has a budget allocation")
        self.budget_allocations.append(allocation)

    def add_capability_allocation(self, allocation: CapabilityAllocation) -> None:
        self._validate_child_allocation(
            allocation.parent_work_item_id, allocation.child_work_item_id
        )
        capabilities = [_identifier(item, "capability") for item in allocation.capabilities]
        if len(capabilities) != len(set(capabilities)):
            raise _fail("invalid_capability", "capabilities must be unique")
        allocation_id = _identifier(allocation.allocation_id, "allocation_id")
        self._ensure_unique(allocation_id, (x.allocation_id for x in self.capability_allocations))
        if any(item.child_work_item_id == allocation.child_work_item_id for item in self.capability_allocations):
            raise _fail("duplicate_allocation", "child already has a capability allocation")
        self.capability_allocations.append(
            CapabilityAllocation(
                allocation_id,
                allocation.parent_work_item_id,
                allocation.child_work_item_id,
                capabilities,
            )
        )

    def snapshot_component(self) -> WorkGraphSnapshotComponent:
        unresolved = sorted(
            (
                item.work_item_id
                for item in self.work_items.values()
                if item.lifecycle not in _TERMINAL
            ),
            key=lambda identity: identity.value,
        )
        return WorkGraphSnapshotComponent(
            self.graph_id,
            unresolved,
            self.to_persistence_dict(),
        )

    def to_persistence_dict(self) -> Dict[str, Any]:
        self.__post_init__()
        self._validate_references()
        payload = {
            "schema_version": WORK_GRAPH_SCHEMA_VERSION,
            "graph_id": self.graph_id,
            "work_items": [
                _work_item_dict(self.work_items[key])
                for key in sorted(self.work_items, key=lambda identity: identity.value)
            ],
            "attempts": [_record_dict(item) for item in self.attempts],
            "edges": [_record_dict(item) for item in self.edges],
            "transfers": [_record_dict(item) for item in self.transfers],
            "delegations": [_record_dict(item) for item in self.delegations],
            "spawns": [_record_dict(item) for item in self.spawns],
            "fan_out_groups": [_record_dict(item) for item in self.fan_out_groups],
            "joins": [_record_dict(item) for item in self.joins],
            "cancellations": [_record_dict(item) for item in self.cancellations],
            "detachments": [_record_dict(item) for item in self.detachments],
            "completions": [_record_dict(item) for item in self.completions],
            "late_results": [_record_dict(item) for item in self.late_results],
            "budget_allocations": [
                _record_dict(item) for item in self.budget_allocations
            ],
            "capability_allocations": [
                _record_dict(item) for item in self.capability_allocations
            ],
            "operation_receipts": [
                _record_dict(item) for item in self.operation_receipts
            ],
        }
        return _clone_json(payload, "WorkGraph")

    @classmethod
    def from_canonical_dict(cls, payload: Mapping[str, Any]) -> "WorkGraph":
        fields = {
            "schema_version", "graph_id", "work_items", "attempts", "edges",
            "transfers", "delegations", "spawns", "fan_out_groups", "joins",
            "cancellations", "detachments", "completions", "late_results",
            "budget_allocations", "capability_allocations",
            "operation_receipts",
        }
        data = _strict(payload, fields, "WorkGraph")
        if data["schema_version"] not in {"qitos.work_graph/v3", WORK_GRAPH_SCHEMA_VERSION}:
            raise _fail("unknown_schema_version", "unsupported WorkGraph version")
        for name in fields - {"schema_version", "graph_id"}:
            if not isinstance(data[name], list):
                raise _fail("invalid_record", f"{name} must be an array")
        work_items = [_parse_work_item(item) for item in data["work_items"]]
        graph = cls(
            graph_id=data["graph_id"],
            work_items={item.work_item_id: item for item in work_items},
            attempts=[_parse_attempt(item) for item in data["attempts"]],
            edges=[_parse_edge(item) for item in data["edges"]],
            transfers=[_parse_transfer(item) for item in data["transfers"]],
            delegations=[_parse_simple(DelegationRecord, item) for item in data["delegations"]],
            spawns=[_parse_simple(SpawnRecord, item) for item in data["spawns"]],
            fan_out_groups=[_parse_simple(FanOutGroup, item) for item in data["fan_out_groups"]],
            joins=[_parse_join(item) for item in data["joins"]],
            cancellations=[_parse_cancellation(item) for item in data["cancellations"]],
            detachments=[_parse_simple(DetachmentRecord, item) for item in data["detachments"]],
            completions=[_parse_completion(item) for item in data["completions"]],
            late_results=[_parse_late(item) for item in data["late_results"]],
            budget_allocations=[_parse_budget(item) for item in data["budget_allocations"]],
            capability_allocations=[
                _parse_simple(CapabilityAllocation, item)
                for item in data["capability_allocations"]
            ],
            operation_receipts=[
                _parse_operation_receipt(item)
                for item in data["operation_receipts"]
            ],
            schema_version=WORK_GRAPH_SCHEMA_VERSION,
        )
        graph._validate_references()
        return graph

    def _validate_references(self) -> None:
        self._validate_identity_sets()
        for item in self.work_items.values():
            if item.parent_work_item_id is not None:
                self._item(item.parent_work_item_id)
                if item.parent_work_item_id == item.work_item_id:
                    raise _fail("self_edge", "work item cannot be its own parent")
        for attempt in self.attempts:
            item = self._item(attempt.work_item_id)
            if attempt.owner_generation > item.owner.generation:
                raise _fail("invalid_generation", "attempt generation exceeds owner generation")
        for edge in self.edges:
            source = self._item(edge.source_work_item_id)
            target = self._item(edge.target_work_item_id)
            if source.work_item_id == target.work_item_id:
                raise _fail("self_edge", "work edge cannot target its source")
            if target.parent_work_item_id != source.work_item_id:
                raise _fail("parent_edge_mismatch", "edge target does not belong to source parent")
        self._validate_acyclic_and_bounded()
        for delegation in self.delegations:
            self._validate_operation_edge(
                delegation.parent_work_item_id,
                delegation.child_work_item_id,
                "delegate",
            )
        for spawn in self.spawns:
            self._validate_operation_edge(
                spawn.parent_work_item_id, spawn.child_work_item_id, "spawn"
            )
        for group in self.fan_out_groups:
            if len(group.child_work_item_ids) > _MAX_FAN_OUT_WIDTH:
                raise _fail("fan_out_width_exceeded", "fan_out exceeds configured graph bound")
            for child_id in group.child_work_item_ids:
                self._validate_operation_edge(group.parent_work_item_id, child_id, "fan_out")
        for join in self.joins:
            parent = self._item(join.parent_work_item_id)
            for child_id in join.child_work_item_ids:
                child = self._item(child_id)
                if child.parent_work_item_id != parent.work_item_id:
                    raise _fail("undeclared_join_child", "join child does not belong to parent")
        for budget_allocation in self.budget_allocations:
            self._validate_child_allocation(
                budget_allocation.parent_work_item_id,
                budget_allocation.child_work_item_id,
            )
        for capability_allocation in self.capability_allocations:
            self._validate_child_allocation(
                capability_allocation.parent_work_item_id,
                capability_allocation.child_work_item_id,
            )
        for cancellation in self.cancellations:
            self._item(cancellation.work_item_id)
        for detachment in self.detachments:
            self._validate_child_allocation(
                detachment.parent_work_item_id, detachment.child_work_item_id
            )
        for transfer in self.transfers:
            item = self._item(transfer.work_item_id)
            if transfer.committed_generation > item.owner.generation:
                raise _fail("invalid_generation", "transfer exceeds current owner generation")
        for completion in self.completions:
            self._item(completion.work_item_id)
            ToolResult.from_canonical_dict(completion.outcome)
        for late in self.late_results:
            self._item(late.work_item_id)
            ToolResult.from_canonical_dict(late.outcome)

    def _prevalidate_child(self, child: WorkItem, edge_id: str) -> None:
        if child.work_item_id in self.work_items:
            raise _fail("duplicate_identity", "duplicate work item identity")
        self._ensure_unique(edge_id, (item.edge_id for item in self.edges))
        depth = 1
        parent_id = child.parent_work_item_id
        seen = {child.work_item_id}
        while parent_id is not None:
            if parent_id in seen:
                raise _fail("graph_cycle", "child would create an ancestor cycle")
            seen.add(parent_id)
            parent = self._item(parent_id)
            parent_id = parent.parent_work_item_id
            depth += 1
            if depth > _MAX_GRAPH_DEPTH:
                raise _fail("graph_depth_exceeded", "work graph exceeds configured depth")

    def _validate_acyclic_and_bounded(self) -> None:
        for item in self.work_items.values():
            depth = 1
            current = item
            seen: set[WorkItemIdentity] = set()
            while current.parent_work_item_id is not None:
                if current.work_item_id in seen:
                    raise _fail("graph_cycle", "work graph contains an ancestor cycle")
                seen.add(current.work_item_id)
                current = self._item(current.parent_work_item_id)
                depth += 1
                if depth > _MAX_GRAPH_DEPTH:
                    raise _fail("graph_depth_exceeded", "work graph exceeds configured depth")

    def _validate_operation_edge(
        self,
        parent_id: WorkItemIdentity,
        child_id: WorkItemIdentity,
        operation: WorkOperation,
    ) -> None:
        matches = [
            edge for edge in self.edges
            if edge.source_work_item_id == parent_id
            and edge.target_work_item_id == child_id
            and edge.operation == operation
        ]
        if len(matches) != 1:
            raise _fail("operation_edge_mismatch", "operation must have exactly one matching edge")

    def _add_edge(
        self,
        edge_id: str,
        operation: WorkOperation,
        source: WorkItemIdentity,
        target: WorkItemIdentity,
    ) -> None:
        edge = WorkEdge(
            _identifier(edge_id, "edge_id"),
            operation,
            source,
            target,
            len(self.edges),
        )
        self._ensure_unique(edge.edge_id, (item.edge_id for item in self.edges))
        self.edges.append(edge)

    def _item(self, work_item_id: WorkItemIdentity) -> WorkItem:
        identity = _identity(work_item_id, WorkItemIdentity, "work_item_id")
        try:
            return self.work_items[identity]
        except KeyError as exc:
            raise _fail("missing_work_item", "work item identity is not present") from exc

    def _join(self, join_id: str) -> tuple[int, JoinDependency]:
        identity = _identifier(join_id, "join_id")
        for index, item in enumerate(self.joins):
            if item.join_id == identity:
                return index, item
        raise _fail("missing_join", "join identity is not present")

    def _record_late(
        self,
        completion_id: str,
        item: WorkItem,
        generation: int,
        reason: Literal["stale_owner", "terminal_state", "cancelled"],
        payload: Dict[str, Any],
    ) -> None:
        identity = f"late:{_identifier(completion_id, 'completion_id')}"
        self._ensure_unique(identity, (entry.late_result_id for entry in self.late_results))
        self.late_results.append(
            LateResult(identity, item.work_item_id, generation, reason, payload)
        )

    def _validate_child_allocation(
        self, parent_id: WorkItemIdentity, child_id: WorkItemIdentity
    ) -> None:
        self._item(parent_id)
        child = self._item(child_id)
        if child.parent_work_item_id != parent_id:
            raise _fail("invalid_allocation", "allocation target is not a child")

    @staticmethod
    def _ensure_unique(identity: str, existing: Iterable[str]) -> None:
        if identity in set(existing):
            raise _fail("duplicate_identity", "record identity is duplicated")


def _work_item_dict(item: WorkItem) -> Dict[str, Any]:
    payload = _record_dict(item)
    payload["owner"] = _record_dict(item.owner)
    return payload


def _replace_work_item(item: WorkItem, **changes: Any) -> WorkItem:
    payload = _work_item_dict(item)
    payload.update(changes)
    if isinstance(payload.get("owner"), WorkOwner):
        payload["owner"] = _record_dict(payload["owner"])
    return _parse_work_item(payload)


def replace_join(join: JoinDependency, **changes: Any) -> JoinDependency:
    values = {item.name: getattr(join, item.name) for item in fields(join)}
    values.update(changes)
    return JoinDependency(**values)


def _parse_work_item(payload: Mapping[str, Any]) -> WorkItem:
    fields = {
        "work_item_id", "session_ref", "task_ref", "lifecycle", "owner",
        "parent_work_item_id", "detached", "budget_allocation_ref",
        "capability_allocation_ref", "context_transfer_ref",
    }
    data = _strict(payload, fields, "WorkItem")
    owner_data = _strict(data["owner"], {"agent_id", "generation"}, "WorkOwner")
    owner_data["agent_id"] = AgentIdentity.from_dict(owner_data["agent_id"])
    data["owner"] = WorkOwner(**owner_data)
    data["work_item_id"] = WorkItemIdentity.from_dict(data["work_item_id"])
    data["session_ref"] = SessionIdentity.from_dict(data["session_ref"])
    if data["parent_work_item_id"] is not None:
        data["parent_work_item_id"] = WorkItemIdentity.from_dict(
            data["parent_work_item_id"]
        )
    return WorkItem(**data)


def _parse_attempt(payload: Mapping[str, Any]) -> WorkAttempt:
    data = _strict(
        payload,
        {"attempt_id", "work_item_id", "owner_generation", "state", "worker_ref"},
        "WorkAttempt",
    )
    data["attempt_id"] = AttemptIdentity.from_dict(data["attempt_id"])
    data["work_item_id"] = WorkItemIdentity.from_dict(data["work_item_id"])
    return WorkAttempt(**data)


def _parse_edge(payload: Mapping[str, Any]) -> WorkEdge:
    data = _strict(
        payload,
        {"edge_id", "operation", "source_work_item_id", "target_work_item_id", "declaration_order"},
        "WorkEdge",
    )
    if data["operation"] not in _OPERATIONS:
        raise _fail("invalid_operation", "unsupported edge operation")
    data["declaration_order"] = _generation(data["declaration_order"], "declaration_order")
    data["source_work_item_id"] = WorkItemIdentity.from_dict(
        data["source_work_item_id"]
    )
    data["target_work_item_id"] = WorkItemIdentity.from_dict(
        data["target_work_item_id"]
    )
    return WorkEdge(**data)


def _parse_transfer(payload: Mapping[str, Any]) -> OwnershipTransfer:
    fields = {
        "transfer_id", "work_item_id", "expected_generation", "committed_generation",
        "from_agent_id", "to_agent_id", "context_transfer_ref", "reason",
    }
    data = _strict(payload, fields, "OwnershipTransfer")
    data["expected_generation"] = _generation(data["expected_generation"], "expected_generation")
    data["committed_generation"] = _generation(data["committed_generation"], "committed_generation")
    if data["committed_generation"] != data["expected_generation"] + 1:
        raise _fail("invalid_generation", "transfer generation must advance by one")
    data["work_item_id"] = WorkItemIdentity.from_dict(data["work_item_id"])
    data["from_agent_id"] = AgentIdentity.from_dict(data["from_agent_id"])
    data["to_agent_id"] = AgentIdentity.from_dict(data["to_agent_id"])
    return OwnershipTransfer(**data)


def _parse_simple(record_type: Any, payload: Mapping[str, Any]) -> Any:
    fields = set(record_type.__dataclass_fields__)
    data = _strict(payload, fields, record_type.__name__)
    if record_type in {
        DelegationRecord,
        SpawnRecord,
        DetachmentRecord,
        CapabilityAllocation,
    }:
        data["parent_work_item_id"] = WorkItemIdentity.from_dict(
            data["parent_work_item_id"]
        )
        data["child_work_item_id"] = WorkItemIdentity.from_dict(
            data["child_work_item_id"]
        )
    elif record_type is FanOutGroup:
        data["parent_work_item_id"] = WorkItemIdentity.from_dict(
            data["parent_work_item_id"]
        )
        data["child_work_item_ids"] = [
            WorkItemIdentity.from_dict(item) for item in data["child_work_item_ids"]
        ]
    return record_type(**data)


def _parse_join(payload: Mapping[str, Any]) -> JoinDependency:
    data = _strict(
        payload,
        {
            "join_id", "parent_work_item_id", "child_work_item_ids", "policy",
            "quorum", "accepted_child_ids", "generation", "reducer_ref",
            "reducer_digest", "state", "outstanding_child_ids",
            "completion_order", "discarded_child_ids", "terminal_receipt_ref",
        },
        "JoinDependency",
    )
    if data["policy"] not in _JOIN_POLICIES:
        raise _fail("invalid_join_policy", "unsupported join policy")
    for name in (
        "child_work_item_ids", "accepted_child_ids", "outstanding_child_ids",
        "completion_order", "discarded_child_ids",
    ):
        if not isinstance(data[name], list):
            raise _fail("invalid_join", f"{name} must be an array")
    data["parent_work_item_id"] = WorkItemIdentity.from_dict(
        data["parent_work_item_id"]
    )
    data["child_work_item_ids"] = [
        WorkItemIdentity.from_dict(item) for item in data["child_work_item_ids"]
    ]
    for name in (
        "accepted_child_ids", "outstanding_child_ids", "completion_order",
        "discarded_child_ids",
    ):
        data[name] = [WorkItemIdentity.from_dict(item) for item in data[name]]
    if not set(data["accepted_child_ids"]).issubset(set(data["child_work_item_ids"])):
        raise _fail("undeclared_join_child", "accepted child was not declared")
    return JoinDependency(**data)


def _parse_cancellation(payload: Mapping[str, Any]) -> CancellationRequest:
    data = _strict(
        payload,
        {"cancellation_id", "work_item_id", "requested_generation", "propagation"},
        "CancellationRequest",
    )
    data["requested_generation"] = _generation(
        data["requested_generation"], "requested_generation"
    )
    if data["propagation"] not in {"propagate", "detach", "request_and_wait"}:
        raise _fail("invalid_cancellation", "unsupported propagation")
    data["work_item_id"] = WorkItemIdentity.from_dict(data["work_item_id"])
    return CancellationRequest(**data)


def _parse_completion(payload: Mapping[str, Any]) -> WorkCompletion:
    data = _strict(
        payload,
        {"completion_id", "work_item_id", "owner_generation", "outcome", "outcome_digest"},
        "WorkCompletion",
    )
    ToolResult.from_canonical_dict(data["outcome"])
    data["work_item_id"] = WorkItemIdentity.from_dict(data["work_item_id"])
    return WorkCompletion(**data)


def _parse_late(payload: Mapping[str, Any]) -> LateResult:
    data = _strict(
        payload,
        {"late_result_id", "work_item_id", "owner_generation", "reason", "outcome"},
        "LateResult",
    )
    if data["reason"] not in {"stale_owner", "terminal_state", "cancelled"}:
        raise _fail("invalid_late_result", "unsupported rejection reason")
    ToolResult.from_canonical_dict(data["outcome"])
    data["work_item_id"] = WorkItemIdentity.from_dict(data["work_item_id"])
    return LateResult(**data)


def _parse_budget(payload: Mapping[str, Any]) -> BudgetAllocation:
    data = _strict(
        payload,
        {"allocation_id", "parent_work_item_id", "child_work_item_id", "limits", "reclaim_policy"},
        "BudgetAllocation",
    )
    data["limits"] = _clone_json(data["limits"], "limits")
    data["parent_work_item_id"] = WorkItemIdentity.from_dict(
        data["parent_work_item_id"]
    )
    data["child_work_item_id"] = WorkItemIdentity.from_dict(
        data["child_work_item_id"]
    )
    return BudgetAllocation(**data)


def _parse_operation_receipt(payload: Mapping[str, Any]) -> WorkOperationReceipt:
    legacy = {
        "operation_id", "operation", "payload_digest", "state", "generation",
        "attempt", "worker_ref", "outcome_unknown", "terminal_receipt_ref",
    }
    current = legacy | {"descriptor", "admission_state", "queue_position"}
    if not isinstance(payload, Mapping):
        raise _fail("invalid_record", "WorkOperationReceipt must be an object")
    if set(payload) == legacy:
        data = dict(payload)
        data.update(descriptor=None, admission_state="eligible", queue_position=None)
    else:
        data = _strict(payload, current, "WorkOperationReceipt")
    return WorkOperationReceipt(**data)


__all__ = [
    "WORK_GRAPH_SCHEMA_VERSION",
    "WORK_GRAPH_SNAPSHOT_COMPONENT_VERSION",
    "WORK_GRAPH_SNAPSHOT_COMPONENT_CODEC",
    "BudgetAllocation",
    "CancellationRequest",
    "CapabilityAllocation",
    "CompletionDisposition",
    "DelegationRecord",
    "DetachmentRecord",
    "FanOutGroup",
    "JoinDependency",
    "LateResult",
    "OwnershipTransfer",
    "SpawnRecord",
    "WorkAttempt",
    "WorkCompletion",
    "WorkEdge",
    "WorkGraph",
    "WorkGraphContractError",
    "WorkGraphSnapshotComponent",
    "WorkItem",
    "WorkOwner",
]
