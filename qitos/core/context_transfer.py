"""Strict child-input and least-privilege authority transfer contracts.

The module composes existing conversation, continuation, artifact, Session, and
WorkGraph contracts.  It is deliberately not a scheduler and never owns live
agents, provider clients, stores, projectors, workers, or credentials.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import (
    Any,
    Dict,
    Iterable,
    Literal,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    cast,
    runtime_checkable,
)

from .artifact import ArtifactRef
from .conversation import ExchangeLog
from .diagnostics import diagnostic_string_is_sensitive
from .request_view import ContinuationRef, ConversationSnapshotComponent
from .session import (
    AgentIdentity,
    ResolverNamespace,
    ResolverReference,
    RunIdentity,
    SessionIdentity,
    SnapshotIdentity,
    WorkItemIdentity,
)
from .work_graph import BudgetAllocation, CapabilityAllocation


CONTEXT_TRANSFER_PLAN_SCHEMA_VERSION = "qitos.context_transfer_plan/v1"
CONTEXT_TRANSFER_RECEIPT_SCHEMA_VERSION = "qitos.context_transfer_receipt/v1"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[a-z][a-z0-9_.:-]{1,127}$")
_OPERATION = frozenset({"handoff", "delegate", "spawn", "fan_out"})
_CONTEXT_POLICIES = frozenset(
    {"full", "recent_window", "compacted", "none", "custom"}
)
_AUTHORITY_SOURCES = frozenset(
    {
        "parent_grant",
        "destination_policy",
        "tool_environment",
        "artifact_access",
        "caller_transfer_policy",
    }
)
_SECRET_KEY = re.compile(
    r"(?:^|[_-])(?:authorization|api[_-]?key|token|credential|password|passwd|"
    r"secret|cookie|headers?|private[_-]?key|provider[_-]?payload)(?:$|[_-])",
    re.IGNORECASE,
)
_MAX_TRANSFER_DEPTH = 64
_MAX_TRANSFER_NODES = 100_000
_MAX_TRANSFER_BYTES = 8 * 1024 * 1024


class ContextTransferError(ValueError):
    """Typed strict-reader or transfer execution failure without input echo."""

    def __init__(self, code: str, message: str) -> None:
        self.code = str(code)
        super().__init__(f"{self.code}: {message}")


def _fail(code: str, message: str) -> ContextTransferError:
    return ContextTransferError(code, message)


def _strict_json(
    value: Any,
    path: str,
    *,
    portable: bool = True,
    _active: Optional[set[int]] = None,
    _counter: Optional[list[int]] = None,
    _depth: int = 0,
) -> Any:
    """Clone strict JSON and reject process-local or sensitive strings."""

    active = _active if _active is not None else set()
    counter = _counter if _counter is not None else [0]
    if _depth > _MAX_TRANSFER_DEPTH:
        raise _fail("contract_too_deep", f"{path} exceeds the depth bound")
    counter[0] += 1
    if counter[0] > _MAX_TRANSFER_NODES:
        raise _fail("contract_too_large", f"{path} exceeds the node bound")

    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _fail("non_json_value", f"{path} must contain finite numbers")
        return value
    if isinstance(value, str):
        if portable and diagnostic_string_is_sensitive(value):
            raise _fail("unsafe_persisted_value", f"{path} is not portable")
        return value
    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in active:
            raise _fail("cyclic_contract", f"{path} contains a cycle")
        active.add(identity)
        try:
            return [
                _strict_json(
                    item,
                    f"{path}[{index}]",
                    portable=portable,
                    _active=active,
                    _counter=counter,
                    _depth=_depth + 1,
                )
                for index, item in enumerate(value)
            ]
        finally:
            active.remove(identity)
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            raise _fail("cyclic_contract", f"{path} contains a cycle")
        active.add(identity)
        result: Dict[str, Any] = {}
        try:
            for key, item in value.items():
                if not isinstance(key, str):
                    raise _fail("non_json_value", f"{path} keys must be strings")
                if _SECRET_KEY.search(key):
                    raise _fail(
                        "unsafe_persisted_value",
                        f"{path} contains a sensitive key",
                    )
                result[key] = _strict_json(
                    item,
                    f"{path}.[field]",
                    portable=portable,
                    _active=active,
                    _counter=counter,
                    _depth=_depth + 1,
                )
            return result
        finally:
            active.remove(identity)
    raise _fail("non_json_value", f"{path} contains a process-local value")


def _canonical_json(value: Any, path: str, *, portable: bool = True) -> str:
    cloned = _strict_json(value, path, portable=portable)
    encoded = json.dumps(
        cloned,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(encoded.encode("utf-8")) > _MAX_TRANSFER_BYTES:
        raise _fail("contract_too_large", f"{path} exceeds the byte bound")
    return encoded


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value, "digest_input").encode()).hexdigest()


def _token(value: Any, path: str) -> str:
    if (
        not isinstance(value, str)
        or _TOKEN.fullmatch(value) is None
        or diagnostic_string_is_sensitive(value)
    ):
        raise _fail("invalid_identifier", f"{path} is invalid")
    return value


def _strict_object(value: Any, fields: frozenset[str], path: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _fail("malformed_contract", f"{path} must be an object")
    data = dict(value)
    unknown = sorted(set(data) - fields)
    missing = sorted(fields - set(data))
    if unknown:
        raise _fail("unknown_field", f"{path} has an unknown field")
    if missing:
        raise _fail("missing_field", f"{path} is missing a field")
    return data


def _allocation_dict(value: BudgetAllocation | CapabilityAllocation) -> Dict[str, Any]:
    if isinstance(value, BudgetAllocation):
        return {
            "allocation_id": value.allocation_id,
            "parent_work_item_id": value.parent_work_item_id.to_dict(),
            "child_work_item_id": value.child_work_item_id.to_dict(),
            "limits": _strict_json(value.limits, "budget.limits"),
            "reclaim_policy": value.reclaim_policy,
        }
    if isinstance(value, CapabilityAllocation):
        return {
            "allocation_id": value.allocation_id,
            "parent_work_item_id": value.parent_work_item_id.to_dict(),
            "child_work_item_id": value.child_work_item_id.to_dict(),
            "capabilities": list(value.capabilities),
        }
    raise _fail("invalid_allocation", "allocation type is unsupported")


def _budget_from_dict(value: Any) -> BudgetAllocation:
    fields = frozenset(
        {"allocation_id", "parent_work_item_id", "child_work_item_id", "limits", "reclaim_policy"}
    )
    data = _strict_object(value, fields, "budget_request")
    return BudgetAllocation(
        allocation_id=data["allocation_id"],
        parent_work_item_id=WorkItemIdentity.from_dict(data["parent_work_item_id"]),
        child_work_item_id=WorkItemIdentity.from_dict(data["child_work_item_id"]),
        limits=_strict_json(data["limits"], "budget.limits"),
        reclaim_policy=data["reclaim_policy"],
    )


def _capability_from_dict(value: Any) -> CapabilityAllocation:
    fields = frozenset(
        {"allocation_id", "parent_work_item_id", "child_work_item_id", "capabilities"}
    )
    data = _strict_object(value, fields, "capability_request")
    return CapabilityAllocation(
        allocation_id=data["allocation_id"],
        parent_work_item_id=WorkItemIdentity.from_dict(data["parent_work_item_id"]),
        child_work_item_id=WorkItemIdentity.from_dict(data["child_work_item_id"]),
        capabilities=list(data["capabilities"]),
    )


@runtime_checkable
class StateProjector(Protocol):
    """Process-local typed state projector; the object is never serialized."""

    projector_ref: str
    projector_digest: str
    source_schema_id: str
    destination_schema_id: str
    capabilities: frozenset[str]

    def project(
        self, source_state: Mapping[str, Any], *, selected_fields: Sequence[str]
    ) -> Mapping[str, Any]:
        """Return state plus selected/transformed/omitted/defaulted/validation facts."""


@runtime_checkable
class ContextSelectionPolicy(Protocol):
    """Independent deterministic exchange selection policy."""

    policy_ref: str
    policy_digest: str

    def select_exchange_ids(self, log: ExchangeLog) -> Sequence[str]:
        ...


@dataclass(frozen=True)
class ContextTransferPlan:
    operation_id: str
    operation_kind: Literal["handoff", "delegate", "spawn", "fan_out"]
    source_session_id: SessionIdentity
    source_run_id: RunIdentity
    source_work_item_id: WorkItemIdentity
    source_snapshot_id: SnapshotIdentity
    source_head_generation: int
    source_head_digest: str
    destination_agent_id: AgentIdentity
    destination_agent_ref: ResolverReference
    destination_provider: str
    destination_model: str
    destination_api_mode: str
    context_policy: Literal["full", "recent_window", "compacted", "none", "custom"]
    context_policy_ref: str
    context_policy_digest: str
    recent_exchange_count: int
    custom_exchange_ids: tuple[str, ...]
    source_schema_id: str
    destination_schema_id: str
    state_projector_ref: str
    state_projector_digest: str
    state_projector_capability: str
    state_fields: tuple[str, ...]
    continuation_required: bool
    continuation: Optional[ContinuationRef]
    artifact_refs: tuple[ArtifactRef, ...]
    required_components: tuple[str, ...]
    approved_losses: tuple[str, ...]
    _budget_request_json: str = field(repr=False)
    _capability_request_json: str = field(repr=False)
    _destination_constraints_json: str = field(repr=False)
    schema_version: str = CONTEXT_TRANSFER_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CONTEXT_TRANSFER_PLAN_SCHEMA_VERSION:
            raise _fail("unknown_schema_version", "transfer plan schema is unsupported")
        _token(self.operation_id, "operation_id")
        if self.operation_kind not in _OPERATION:
            raise _fail("invalid_operation", "operation kind is unsupported")
        if not isinstance(self.source_session_id, SessionIdentity):
            raise _fail("invalid_identity", "source session identity is invalid")
        if not isinstance(self.source_run_id, RunIdentity):
            raise _fail("invalid_identity", "source run identity is invalid")
        if not isinstance(self.source_work_item_id, WorkItemIdentity):
            raise _fail("invalid_identity", "source work identity is invalid")
        if not isinstance(self.source_snapshot_id, SnapshotIdentity):
            raise _fail("invalid_identity", "source snapshot identity is invalid")
        if (
            not isinstance(self.source_head_generation, int)
            or isinstance(self.source_head_generation, bool)
            or self.source_head_generation < 0
        ):
            raise _fail("invalid_generation", "source head generation is invalid")
        if not isinstance(self.destination_agent_id, AgentIdentity):
            raise _fail("invalid_identity", "destination agent identity is invalid")
        if (
            not isinstance(self.destination_agent_ref, ResolverReference)
            or self.destination_agent_ref.namespace is not ResolverNamespace.AGENT
        ):
            raise _fail("invalid_resolver", "destination agent resolver is invalid")
        for name in (
            "source_head_digest",
            "context_policy_digest",
            "state_projector_digest",
        ):
            if _SHA256.fullmatch(getattr(self, name)) is None:
                raise _fail("invalid_digest", f"{name} must be SHA-256")
        for name in (
            "destination_provider",
            "destination_model",
            "destination_api_mode",
            "context_policy_ref",
            "source_schema_id",
            "destination_schema_id",
            "state_projector_ref",
            "state_projector_capability",
        ):
            _token(getattr(self, name), name)
        if self.context_policy not in _CONTEXT_POLICIES:
            raise _fail("invalid_context_policy", "context policy is unsupported")
        if (
            not isinstance(self.recent_exchange_count, int)
            or isinstance(self.recent_exchange_count, bool)
            or self.recent_exchange_count < 0
        ):
            raise _fail("invalid_context_policy", "recent exchange count is invalid")
        if self.context_policy == "recent_window" and self.recent_exchange_count < 1:
            raise _fail("invalid_context_policy", "recent window must be positive")
        for values, path in (
            (self.custom_exchange_ids, "custom_exchange_ids"),
            (self.state_fields, "state_fields"),
            (self.required_components, "required_components"),
            (self.approved_losses, "approved_losses"),
        ):
            if len(values) != len(set(values)):
                raise _fail("duplicate_value", f"{path} must be unique")
            for value in values:
                _token(value, path)
        if self.context_policy != "custom" and self.custom_exchange_ids:
            raise _fail("invalid_context_policy", "custom IDs require custom policy")
        if not isinstance(self.continuation_required, bool):
            raise _fail("invalid_continuation", "continuation requirement must be boolean")
        if self.continuation_required and self.continuation is None:
            raise _fail("missing_continuation", "required continuation is absent")
        if len({item.artifact_id for item in self.artifact_refs}) != len(self.artifact_refs):
            raise _fail("duplicate_artifact", "artifact references must be unique")
        if len(self.artifact_refs) > 256:
            raise _fail("contract_too_large", "artifact reference count exceeds the bound")
        budget = _budget_from_dict(json.loads(self._budget_request_json))
        capability = _capability_from_dict(json.loads(self._capability_request_json))
        if (
            budget.parent_work_item_id != self.source_work_item_id
            or capability.parent_work_item_id != self.source_work_item_id
            or budget.child_work_item_id != capability.child_work_item_id
        ):
            raise _fail("allocation_identity_mismatch", "authority allocation lineage mismatched")
        _strict_json(json.loads(self._destination_constraints_json), "destination_constraints")
        constraints = json.loads(self._destination_constraints_json)
        for name, default in (("max_selected_items", 1024), ("max_selected_bytes", 1_000_000)):
            value = constraints.get(name, default)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise _fail("invalid_destination_constraint", f"{name} must be positive")

    @classmethod
    def create(
        cls,
        *,
        operation_id: str,
        operation_kind: str,
        source_session_id: SessionIdentity,
        source_run_id: RunIdentity,
        source_work_item_id: WorkItemIdentity,
        source_snapshot_id: SnapshotIdentity,
        source_head_generation: int,
        source_head_digest: str,
        destination_agent_id: AgentIdentity,
        destination_agent_ref: ResolverReference,
        destination_provider: str,
        destination_model: str,
        destination_api_mode: str,
        context_policy: str,
        context_policy_ref: str,
        context_policy_digest: str,
        budget_request: BudgetAllocation,
        capability_request: CapabilityAllocation,
        source_schema_id: str,
        destination_schema_id: str,
        state_projector_ref: str,
        state_projector_digest: str,
        state_projector_capability: str,
        recent_exchange_count: int = 0,
        custom_exchange_ids: Iterable[str] = (),
        state_fields: Iterable[str] = (),
        continuation_required: bool = False,
        continuation: Optional[ContinuationRef] = None,
        artifact_refs: Iterable[ArtifactRef] = (),
        required_components: Iterable[str] = (),
        approved_losses: Iterable[str] = (),
        destination_constraints: Optional[Mapping[str, Any]] = None,
    ) -> "ContextTransferPlan":
        return cls(
            operation_id=operation_id,
            operation_kind=cast(
                Literal["handoff", "delegate", "spawn", "fan_out"], operation_kind
            ),
            source_session_id=source_session_id,
            source_run_id=source_run_id,
            source_work_item_id=source_work_item_id,
            source_snapshot_id=source_snapshot_id,
            source_head_generation=source_head_generation,
            source_head_digest=source_head_digest,
            destination_agent_id=destination_agent_id,
            destination_agent_ref=destination_agent_ref,
            destination_provider=destination_provider,
            destination_model=destination_model,
            destination_api_mode=destination_api_mode,
            context_policy=cast(
                Literal["full", "recent_window", "compacted", "none", "custom"],
                context_policy,
            ),
            context_policy_ref=context_policy_ref,
            context_policy_digest=context_policy_digest,
            recent_exchange_count=recent_exchange_count,
            custom_exchange_ids=tuple(custom_exchange_ids),
            source_schema_id=source_schema_id,
            destination_schema_id=destination_schema_id,
            state_projector_ref=state_projector_ref,
            state_projector_digest=state_projector_digest,
            state_projector_capability=state_projector_capability,
            state_fields=tuple(state_fields),
            continuation_required=continuation_required,
            continuation=continuation,
            artifact_refs=tuple(artifact_refs),
            required_components=tuple(required_components),
            approved_losses=tuple(approved_losses),
            _budget_request_json=_canonical_json(_allocation_dict(budget_request), "budget_request"),
            _capability_request_json=_canonical_json(
                _allocation_dict(capability_request), "capability_request"
            ),
            _destination_constraints_json=_canonical_json(
                destination_constraints or {}, "destination_constraints"
            ),
        )

    @property
    def budget_request(self) -> BudgetAllocation:
        return _budget_from_dict(json.loads(self._budget_request_json))

    @property
    def capability_request(self) -> CapabilityAllocation:
        return _capability_from_dict(json.loads(self._capability_request_json))

    @property
    def destination_constraints(self) -> Dict[str, Any]:
        return json.loads(self._destination_constraints_json)

    def _unsigned_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_id": self.operation_id,
            "operation_kind": self.operation_kind,
            "source": {
                "session_id": self.source_session_id.to_dict(),
                "run_id": self.source_run_id.to_dict(),
                "work_item_id": self.source_work_item_id.to_dict(),
                "snapshot_id": self.source_snapshot_id.to_dict(),
                "head_generation": self.source_head_generation,
                "head_digest": self.source_head_digest,
            },
            "destination": {
                "agent_id": self.destination_agent_id.to_dict(),
                "agent_ref": self.destination_agent_ref.to_dict(),
                "provider": self.destination_provider,
                "model": self.destination_model,
                "api_mode": self.destination_api_mode,
                "constraints": self.destination_constraints,
            },
            "context": {
                "policy": self.context_policy,
                "policy_ref": self.context_policy_ref,
                "policy_digest": self.context_policy_digest,
                "recent_exchange_count": self.recent_exchange_count,
                "custom_exchange_ids": list(self.custom_exchange_ids),
            },
            "state": {
                "source_schema_id": self.source_schema_id,
                "destination_schema_id": self.destination_schema_id,
                "projector_ref": self.state_projector_ref,
                "projector_digest": self.state_projector_digest,
                "projector_capability": self.state_projector_capability,
                "selected_fields": list(self.state_fields),
            },
            "continuation_required": self.continuation_required,
            "continuation": self.continuation.to_dict() if self.continuation else None,
            "budget_request": _allocation_dict(self.budget_request),
            "capability_request": _allocation_dict(self.capability_request),
            "artifact_refs": [item.to_dict() for item in self.artifact_refs],
            "required_components": list(self.required_components),
            "approved_losses": list(self.approved_losses),
        }

    @property
    def policy_digest(self) -> str:
        return _digest(
            {
                "context": self._unsigned_dict()["context"],
                "state": self._unsigned_dict()["state"],
                "required_components": list(self.required_components),
                "approved_losses": list(self.approved_losses),
                "destination_constraints": self.destination_constraints,
            }
        )

    @property
    def integrity_digest(self) -> str:
        return _digest(self._unsigned_dict())

    def to_dict(self) -> Dict[str, Any]:
        payload = self._unsigned_dict()
        payload["policy_digest"] = self.policy_digest
        payload["integrity_digest"] = self.integrity_digest
        return json.loads(_canonical_json(payload, "transfer_plan"))

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict(), "transfer_plan")

    @classmethod
    def from_dict(cls, value: Any) -> "ContextTransferPlan":
        fields = frozenset(
            {
                "schema_version", "operation_id", "operation_kind", "source",
                "destination", "context", "state", "continuation_required",
                "continuation", "budget_request", "capability_request",
                "artifact_refs", "required_components", "approved_losses",
                "policy_digest", "integrity_digest",
            }
        )
        data = _strict_object(value, fields, "transfer_plan")
        source = _strict_object(
            data["source"],
            frozenset({"session_id", "run_id", "work_item_id", "snapshot_id", "head_generation", "head_digest"}),
            "transfer_plan.source",
        )
        destination = _strict_object(
            data["destination"],
            frozenset({"agent_id", "agent_ref", "provider", "model", "api_mode", "constraints"}),
            "transfer_plan.destination",
        )
        context = _strict_object(
            data["context"],
            frozenset({"policy", "policy_ref", "policy_digest", "recent_exchange_count", "custom_exchange_ids"}),
            "transfer_plan.context",
        )
        state = _strict_object(
            data["state"],
            frozenset({"source_schema_id", "destination_schema_id", "projector_ref", "projector_digest", "projector_capability", "selected_fields"}),
            "transfer_plan.state",
        )
        result = cls.create(
            operation_id=data["operation_id"], operation_kind=data["operation_kind"],
            source_session_id=SessionIdentity.from_dict(source["session_id"]),
            source_run_id=RunIdentity.from_dict(source["run_id"]),
            source_work_item_id=WorkItemIdentity.from_dict(source["work_item_id"]),
            source_snapshot_id=SnapshotIdentity.from_dict(source["snapshot_id"]),
            source_head_generation=source["head_generation"],
            source_head_digest=source["head_digest"],
            destination_agent_id=AgentIdentity.from_dict(destination["agent_id"]),
            destination_agent_ref=ResolverReference.from_dict(destination["agent_ref"]),
            destination_provider=destination["provider"], destination_model=destination["model"],
            destination_api_mode=destination["api_mode"], destination_constraints=destination["constraints"],
            context_policy=context["policy"], context_policy_ref=context["policy_ref"],
            context_policy_digest=context["policy_digest"],
            recent_exchange_count=context["recent_exchange_count"], custom_exchange_ids=context["custom_exchange_ids"],
            budget_request=_budget_from_dict(data["budget_request"]),
            capability_request=_capability_from_dict(data["capability_request"]),
            source_schema_id=state["source_schema_id"], destination_schema_id=state["destination_schema_id"],
            state_projector_ref=state["projector_ref"], state_projector_digest=state["projector_digest"],
            state_projector_capability=state["projector_capability"], state_fields=state["selected_fields"],
            continuation_required=data["continuation_required"],
            continuation=ContinuationRef.from_dict(data["continuation"]) if data["continuation"] else None,
            artifact_refs=(ArtifactRef.from_dict(item) for item in data["artifact_refs"]),
            required_components=data["required_components"], approved_losses=data["approved_losses"],
        )
        if data["schema_version"] != CONTEXT_TRANSFER_PLAN_SCHEMA_VERSION:
            raise _fail("unknown_schema_version", "transfer plan schema is unsupported")
        if result.policy_digest != data["policy_digest"] or result.integrity_digest != data["integrity_digest"]:
            raise _fail("integrity_mismatch", "transfer plan integrity verification failed")
        return result

    @classmethod
    def from_json(cls, raw: str) -> "ContextTransferPlan":
        try:
            value = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise _fail("malformed_json", "transfer plan is not strict JSON") from exc
        return cls.from_dict(value)


@dataclass(frozen=True)
class ContextTransferReceipt:
    receipt_id: str
    plan: ContextTransferPlan
    selected_item_ids: tuple[str, ...]
    selected_exchange_ids: tuple[str, ...]
    selected_components: tuple[str, ...]
    transformed_fields: tuple[str, ...]
    omitted_fields: tuple[str, ...]
    loss_facts: tuple[str, ...]
    continuation_disposition: Literal["none", "preserved", "stateless_reconstruction", "rejected"]
    artifact_refs: tuple[ArtifactRef, ...]
    granted_capabilities: tuple[str, ...]
    rejected_capabilities: tuple[str, ...]
    rejected_budget_fields: tuple[str, ...]
    reconstruction_requirements: tuple[str, ...]
    policy_digest: str
    provenance_digest: str
    terminal_disposition: Literal["accepted", "rejected"]
    failure_code: Optional[str]
    _selected_items_json: str = field(repr=False)
    _queued_steering_json: str = field(repr=False)
    _projected_state_json: Optional[str] = field(default=None, repr=False)
    _granted_budget_json: Optional[str] = field(default=None, repr=False)
    schema_version: str = CONTEXT_TRANSFER_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CONTEXT_TRANSFER_RECEIPT_SCHEMA_VERSION:
            raise _fail("unknown_schema_version", "transfer receipt schema is unsupported")
        _token(self.receipt_id, "receipt_id")
        if self.policy_digest != self.plan.policy_digest or _SHA256.fullmatch(self.provenance_digest) is None:
            raise _fail("integrity_mismatch", "receipt policy or provenance digest is invalid")
        if self.terminal_disposition == "rejected" and not self.failure_code:
            raise _fail("invalid_receipt", "rejected receipt requires typed failure")
        if self.terminal_disposition == "accepted" and self.failure_code is not None:
            raise _fail("invalid_receipt", "accepted receipt cannot contain failure")
        for values, path in (
            (self.selected_components, "selected_components"),
            (self.transformed_fields, "transformed_fields"),
            (self.omitted_fields, "omitted_fields"),
            (self.loss_facts, "loss_facts"),
            (self.granted_capabilities, "granted_capabilities"),
            (self.rejected_capabilities, "rejected_capabilities"),
            (self.rejected_budget_fields, "rejected_budget_fields"),
            (self.reconstruction_requirements, "reconstruction_requirements"),
        ):
            if len(values) > 256 or len(values) != len(set(values)):
                raise _fail("invalid_receipt", f"{path} is not bounded and unique")
            for value in values:
                _token(value, path)
        if self.failure_code is not None:
            _token(self.failure_code, "failure_code")
        for raw, path in (
            (self._selected_items_json, "selected_items"),
            (self._queued_steering_json, "queued_steering"),
        ):
            _strict_json(json.loads(raw), path)
        if self._projected_state_json is not None:
            _strict_json(json.loads(self._projected_state_json), "projected_state")
        if self._granted_budget_json is not None:
            _budget_from_dict(json.loads(self._granted_budget_json))
        max_items = self.plan.destination_constraints.get("max_selected_items", 1024)
        max_bytes = self.plan.destination_constraints.get("max_selected_bytes", 1_000_000)
        if len(self.selected_items) > max_items or len(self._selected_items_json.encode()) > max_bytes:
            raise _fail("destination_context_limit", "receipt child input exceeds its bound")

    @property
    def selected_items(self) -> tuple[Dict[str, Any], ...]:
        return tuple(json.loads(self._selected_items_json))

    @property
    def queued_steering(self) -> tuple[Dict[str, Any], ...]:
        return tuple(json.loads(self._queued_steering_json))

    @property
    def projected_state(self) -> Optional[Dict[str, Any]]:
        return json.loads(self._projected_state_json) if self._projected_state_json else None

    @property
    def granted_budget(self) -> Optional[BudgetAllocation]:
        return _budget_from_dict(json.loads(self._granted_budget_json)) if self._granted_budget_json else None

    def _unsigned_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "plan": self.plan.to_dict(),
            "selected_item_ids": list(self.selected_item_ids),
            "selected_exchange_ids": list(self.selected_exchange_ids),
            "selected_components": list(self.selected_components),
            "selected_items": list(self.selected_items),
            "queued_steering": list(self.queued_steering),
            "transformed_fields": list(self.transformed_fields),
            "omitted_fields": list(self.omitted_fields),
            "loss_facts": list(self.loss_facts),
            "projected_state": self.projected_state,
            "continuation_disposition": self.continuation_disposition,
            "artifact_refs": [item.to_dict() for item in self.artifact_refs],
            "granted_capabilities": list(self.granted_capabilities),
            "rejected_capabilities": list(self.rejected_capabilities),
            "granted_budget": _allocation_dict(self.granted_budget) if self.granted_budget else None,
            "rejected_budget_fields": list(self.rejected_budget_fields),
            "reconstruction_requirements": list(self.reconstruction_requirements),
            "policy_digest": self.policy_digest,
            "provenance_digest": self.provenance_digest,
            "terminal_disposition": self.terminal_disposition,
            "failure_code": self.failure_code,
        }

    @property
    def integrity_digest(self) -> str:
        return _digest(self._unsigned_dict())

    def to_dict(self) -> Dict[str, Any]:
        payload = self._unsigned_dict()
        payload["integrity_digest"] = self.integrity_digest
        return json.loads(_canonical_json(payload, "transfer_receipt"))

    def canonical_json(self) -> str:
        return _canonical_json(self.to_dict(), "transfer_receipt")

    def to_model_dict(self) -> Dict[str, Any]:
        """Bounded allowlist; excludes state, resolver keys, policy bodies, and failures."""

        return {
            "schema_version": "qitos.context_transfer_receipt.model/v1",
            "operation_id": self.plan.operation_id,
            "operation_kind": self.plan.operation_kind,
            "selected_items": list(self.selected_items),
            "continuation_disposition": self.continuation_disposition,
            "artifact_refs": [item.to_model_projection() for item in self.artifact_refs],
            "reconstruction_requirements": list(self.reconstruction_requirements),
            "loss_facts": list(self.loss_facts),
        }

    def to_diagnostic_dict(self) -> Dict[str, Any]:
        """Non-echo diagnostic allowlist for graph/timeline consumers."""

        return {
            "schema_version": "qitos.context_transfer_receipt.diagnostic/v1",
            "receipt_id": self.receipt_id,
            "operation_id": self.plan.operation_id,
            "operation_kind": self.plan.operation_kind,
            "source_identity_kinds": ["session", "run", "work_item", "snapshot"],
            "destination_identity_kind": "agent",
            "selected_item_count": len(self.selected_item_ids),
            "selected_exchange_count": len(self.selected_exchange_ids),
            "selected_components": list(self.selected_components),
            "transformed_fields": list(self.transformed_fields[:64]),
            "transformed_field_count": len(self.transformed_fields),
            "omitted_fields": list(self.omitted_fields[:64]),
            "omitted_field_count": len(self.omitted_fields),
            "loss_facts": list(self.loss_facts[:64]),
            "loss_fact_count": len(self.loss_facts),
            "continuation_disposition": self.continuation_disposition,
            "artifact_count": len(self.artifact_refs),
            "granted_capabilities": list(self.granted_capabilities[:64]),
            "granted_capability_count": len(self.granted_capabilities),
            "rejected_capabilities": list(self.rejected_capabilities[:64]),
            "rejected_capability_count": len(self.rejected_capabilities),
            "rejected_budget_fields": list(self.rejected_budget_fields[:64]),
            "rejected_budget_field_count": len(self.rejected_budget_fields),
            "terminal_disposition": self.terminal_disposition,
            "failure_code": self.failure_code,
            "policy_digest": self.policy_digest,
            "provenance_digest": self.provenance_digest,
            "integrity_digest": self.integrity_digest,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ContextTransferReceipt":
        fields = frozenset(
            {
                "schema_version", "receipt_id", "plan", "selected_item_ids",
                "selected_exchange_ids", "selected_components", "selected_items",
                "queued_steering", "transformed_fields", "omitted_fields", "loss_facts",
                "projected_state", "continuation_disposition", "artifact_refs",
                "granted_capabilities", "rejected_capabilities", "granted_budget",
                "rejected_budget_fields", "reconstruction_requirements", "policy_digest",
                "provenance_digest", "terminal_disposition", "failure_code", "integrity_digest",
            }
        )
        data = _strict_object(value, fields, "transfer_receipt")
        result = cls(
            receipt_id=data["receipt_id"], plan=ContextTransferPlan.from_dict(data["plan"]),
            selected_item_ids=tuple(data["selected_item_ids"]), selected_exchange_ids=tuple(data["selected_exchange_ids"]),
            selected_components=tuple(data["selected_components"]), transformed_fields=tuple(data["transformed_fields"]),
            omitted_fields=tuple(data["omitted_fields"]), loss_facts=tuple(data["loss_facts"]),
            continuation_disposition=data["continuation_disposition"],
            artifact_refs=tuple(ArtifactRef.from_dict(item) for item in data["artifact_refs"]),
            granted_capabilities=tuple(data["granted_capabilities"]), rejected_capabilities=tuple(data["rejected_capabilities"]),
            rejected_budget_fields=tuple(data["rejected_budget_fields"]),
            reconstruction_requirements=tuple(data["reconstruction_requirements"]),
            policy_digest=data["policy_digest"], provenance_digest=data["provenance_digest"],
            terminal_disposition=data["terminal_disposition"], failure_code=data["failure_code"],
            _selected_items_json=_canonical_json(data["selected_items"], "selected_items"),
            _queued_steering_json=_canonical_json(data["queued_steering"], "queued_steering"),
            _projected_state_json=_canonical_json(data["projected_state"], "projected_state") if data["projected_state"] is not None else None,
            _granted_budget_json=_canonical_json(data["granted_budget"], "granted_budget") if data["granted_budget"] is not None else None,
        )
        if data["schema_version"] != CONTEXT_TRANSFER_RECEIPT_SCHEMA_VERSION:
            raise _fail("unknown_schema_version", "transfer receipt schema is unsupported")
        if result.integrity_digest != data["integrity_digest"]:
            raise _fail("integrity_mismatch", "transfer receipt integrity verification failed")
        return result

    @classmethod
    def from_json(cls, raw: str) -> "ContextTransferReceipt":
        try:
            value = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise _fail("malformed_json", "transfer receipt is not strict JSON") from exc
        return cls.from_dict(value)


def _sanitize_transfer_value(value: Any, path: str) -> tuple[Any, bool]:
    """Filter secrets/paths/endpoints without echoing them or hashing them."""

    if value is None or isinstance(value, (bool, int)):
        return value, False
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _fail("non_json_value", f"{path} is non-finite")
        return value, False
    if isinstance(value, str):
        return ("[filtered]", True) if diagnostic_string_is_sensitive(value) else (value, False)
    if isinstance(value, list):
        output_list: list[Any] = []
        changed = False
        for index, item in enumerate(value):
            nested, filtered = _sanitize_transfer_value(item, f"{path}[{index}]")
            output_list.append(nested)
            changed = changed or filtered
        return output_list, changed
    if isinstance(value, Mapping):
        output_dict: Dict[str, Any] = {}
        changed = False
        for key, item in value.items():
            if not isinstance(key, str):
                raise _fail("non_json_value", f"{path} has a non-string key")
            if key in {"metadata", "opaque_payload", "continuation_attachments", "path"}:
                # These fields are outside the child-input allowlist regardless
                # of their content; the caller records their omission by name.
                continue
            if _SECRET_KEY.search(key):
                changed = True
                continue
            nested, filtered = _sanitize_transfer_value(item, f"{path}.{key}")
            output_dict[key] = nested
            changed = changed or filtered
        return output_dict, changed
    raise _fail("non_json_value", f"{path} contains a process-local value")


def _selection(
    plan: ContextTransferPlan,
    component: ConversationSnapshotComponent,
    policy: Optional[ContextSelectionPolicy],
) -> tuple[ExchangeLog, tuple[str, ...]]:
    log = component.exchange_log
    ordered: list[str] = []
    for item in log.items:
        if item.exchange_id not in ordered:
            ordered.append(item.exchange_id)
    if plan.context_policy == "full":
        selected = ordered
    elif plan.context_policy == "none":
        selected = []
    elif plan.context_policy == "recent_window":
        selected = ordered[-plan.recent_exchange_count :]
    elif plan.context_policy == "compacted":
        if component.last_request_view is None or not component.compaction_receipts:
            raise _fail("missing_compaction_receipt", "compacted transfer lacks source receipt")
        selected = list(component.last_request_view.selection.selected_exchange_ids)
    else:
        if policy is not None:
            if (
                policy.policy_ref != plan.context_policy_ref
                or policy.policy_digest != plan.context_policy_digest
            ):
                raise _fail("selection_policy_mismatch", "custom selection resolver mismatched")
            selected = list(policy.select_exchange_ids(log))
        else:
            selected = list(plan.custom_exchange_ids)
        if len(selected) != len(set(selected)) or any(item not in ordered for item in selected):
            raise _fail("invalid_custom_selection", "custom selection is not a source subset")
        selected_set = set(selected)
        selected = [item for item in ordered if item in selected_set]
    return log, tuple(selected)


def _rejected(
    plan: ContextTransferPlan,
    code: str,
    *,
    rejected_capabilities: Iterable[str] = (),
    rejected_budget_fields: Iterable[str] = (),
    loss_facts: Iterable[str] = (),
) -> ContextTransferReceipt:
    provenance = _digest({"plan": plan.integrity_digest, "disposition": "rejected", "failure_code": code})
    return ContextTransferReceipt(
        receipt_id=f"receipt.{plan.operation_id}", plan=plan,
        selected_item_ids=(), selected_exchange_ids=(), selected_components=(),
        transformed_fields=(), omitted_fields=(), loss_facts=tuple(sorted(set(loss_facts))),
        continuation_disposition="rejected" if plan.continuation else "none",
        artifact_refs=(), granted_capabilities=(), rejected_capabilities=tuple(sorted(set(rejected_capabilities))),
        rejected_budget_fields=tuple(sorted(set(rejected_budget_fields))), reconstruction_requirements=(),
        policy_digest=plan.policy_digest, provenance_digest=provenance,
        terminal_disposition="rejected", failure_code=code,
        _selected_items_json="[]", _queued_steering_json="[]",
    )


def _required_codec_capabilities(
    selected_items: Sequence[Mapping[str, Any]],
) -> frozenset[str]:
    """Derive semantic replay requirements from the selected canonical items."""

    required = {"stateless_replay"} if selected_items else set()
    for item in selected_items:
        if item.get("kind") == "tool_result":
            required.add("native_tool_calls")
        content = item.get("content")
        if isinstance(content, list) and any(
            isinstance(block, Mapping) and block.get("type") != "text"
            for block in content
        ):
            required.add("multimodal_input")
        parts = item.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, Mapping):
                continue
            if part.get("kind") == "tool_call":
                required.add("native_tool_calls")
            if part.get("kind") in {"reasoning_block", "reasoning_reference"}:
                required.add("reasoning_input")
            block = part.get("block")
            if (
                isinstance(block, Mapping)
                and block.get("type") != "text"
            ):
                required.add("multimodal_input")
    return frozenset(required)


def execute_context_transfer(
    plan: ContextTransferPlan,
    *,
    conversation: ConversationSnapshotComponent,
    observed_source_head_digest: str,
    source_state: Mapping[str, Any],
    projector: Optional[StateProjector],
    capability_authorities: Mapping[str, Iterable[str]],
    budget_authorities: Mapping[str, Mapping[str, float | int]],
    destination_codec_capabilities: Iterable[str],
    available_artifact_ids: Iterable[str],
    authorized_artifact_ids: Iterable[str],
    authorized_sensitive_artifact_ids: Iterable[str] = (),
    destination_agent_resolved: bool = True,
    evaluated_at: str,
    available_continuation_refs: Iterable[str] = (),
    selection_policy: Optional[ContextSelectionPolicy] = None,
) -> ContextTransferReceipt:
    """Build one immutable child input and least-privilege terminal receipt."""

    if observed_source_head_digest != plan.source_head_digest:
        return _rejected(plan, "source_head_mismatch")
    if not destination_agent_resolved:
        return _rejected(plan, "missing_destination_resolver")
    if set(capability_authorities) != _AUTHORITY_SOURCES or set(budget_authorities) != _AUTHORITY_SOURCES:
        return _rejected(plan, "incomplete_authority_sources")
    capability_sets = [set(values) for values in capability_authorities.values()]
    allowed_capabilities = set.intersection(*capability_sets)
    requested_capabilities = set(plan.capability_request.capabilities)
    rejected_capabilities = requested_capabilities - allowed_capabilities
    if rejected_capabilities:
        return _rejected(plan, "capability_escalation", rejected_capabilities=rejected_capabilities)

    rejected_budget: list[str] = []
    for key, requested in plan.budget_request.limits.items():
        if not isinstance(requested, (int, float)) or isinstance(requested, bool) or requested < 0:
            return _rejected(plan, "invalid_budget_request", rejected_budget_fields=(key,))
        ceilings = [source.get(key) for source in budget_authorities.values()]
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0 for value in ceilings):
            rejected_budget.append(key)
        elif requested > min(float(value) for value in ceilings if value is not None):
            rejected_budget.append(key)
    if rejected_budget:
        return _rejected(plan, "budget_escalation", rejected_budget_fields=rejected_budget)

    available = set(available_artifact_ids)
    authorized = set(authorized_artifact_ids)
    sensitive = set(authorized_sensitive_artifact_ids)
    transferred_artifacts: list[ArtifactRef] = []
    omitted: list[str] = []
    for artifact in plan.artifact_refs:
        permitted = artifact.artifact_id in authorized
        if artifact.sensitivity in {"confidential", "restricted"}:
            permitted = permitted and artifact.artifact_id in sensitive
        resolved = artifact.artifact_id in available
        if not permitted or not resolved:
            if artifact.required:
                return _rejected(
                    plan,
                    "artifact_access_denied" if not permitted else "missing_required_artifact",
                )
            omitted.append("artifact_optional_omitted")
            continue
        transferred_artifacts.append(artifact)

    try:
        log, selected_exchange_ids = _selection(plan, conversation, selection_policy)
    except ContextTransferError as exc:
        return _rejected(plan, exc.code)
    selected_set = set(selected_exchange_ids)
    model_items = log.to_model_dict()["items"]
    selected_raw = [item for item in model_items if item["exchange_id"] in selected_set]
    codec_capabilities = set(destination_codec_capabilities)
    missing_codec_capabilities = (
        _required_codec_capabilities(selected_raw) - codec_capabilities
    )
    if missing_codec_capabilities:
        return _rejected(
            plan,
            "provider_context_capability_mismatch",
            rejected_capabilities=missing_codec_capabilities,
        )
    if any(item.get("metadata") for item in selected_raw):
        omitted.append("conversation.metadata")
    if any(item.get("continuation_attachments") for item in selected_raw):
        omitted.append("conversation.opaque_provider_payload")
    selected_items: list[Dict[str, Any]] = []
    filtered = False
    for index, item in enumerate(selected_raw):
        safe, changed = _sanitize_transfer_value(item, f"selected_items[{index}]")
        selected_items.append(safe)
        filtered = filtered or changed
    max_items = plan.destination_constraints.get("max_selected_items", 1024)
    max_bytes = plan.destination_constraints.get("max_selected_bytes", 1_000_000)
    selected_json = _canonical_json(selected_items, "selected_items")
    if len(selected_items) > max_items or len(selected_json.encode()) > max_bytes:
        return _rejected(plan, "destination_context_limit")
    losses: list[str] = []
    transformed: list[str] = []
    if filtered:
        if "sensitive_context_filtering" not in plan.approved_losses:
            return _rejected(plan, "unapproved_context_loss", loss_facts=("sensitive_context_filtering",))
        losses.append("sensitive_context_filtering")
        transformed.append("context_sensitive_fields")

    queued: list[Dict[str, Any]] = []
    if log.queued_steering:
        queued_raw = log.to_model_dict()["queued_steering"]
        for index, item in enumerate(queued_raw):
            safe, changed = _sanitize_transfer_value(item, f"queued_steering[{index}]")
            queued.append(safe)
            filtered = filtered or changed
        transformed.append("queued_steering_durable_queue")

    selected_components = ["conversation"] if selected_items else []
    if queued:
        selected_components.append("queued_steering")
    if conversation.compaction_receipts and plan.context_policy == "compacted":
        selected_components.append("compaction_receipts")
        for receipt in conversation.compaction_receipts:
            try:
                losses.extend(
                    _token(item, "compaction.declared_losses")
                    for item in receipt.declared_losses
                )
            except ContextTransferError:
                return _rejected(plan, "invalid_compaction_loss_fact")
    missing_components = set(plan.required_components) - set(selected_components) - {
        "state", "continuation", "artifacts", "authority"
    }
    if missing_components:
        return _rejected(plan, "missing_required_component")

    projected_state: Optional[Dict[str, Any]] = None
    state_facts: Mapping[str, Any] = {}
    if plan.state_fields or "state" in plan.required_components:
        if projector is None:
            return _rejected(plan, "missing_state_projector")
        if (
            projector.projector_ref != plan.state_projector_ref
            or projector.projector_digest != plan.state_projector_digest
            or projector.source_schema_id != plan.source_schema_id
            or projector.destination_schema_id != plan.destination_schema_id
            or plan.state_projector_capability not in projector.capabilities
        ):
            return _rejected(plan, "state_projector_mismatch")
        if any(field not in source_state for field in plan.state_fields):
            return _rejected(plan, "unknown_state_field")
        try:
            state_facts = projector.project(source_state, selected_fields=plan.state_fields)
            state_facts = _strict_object(
                state_facts,
                frozenset({"state", "selected_fields", "transformed_fields", "omitted_fields", "defaulted_fields", "validation"}),
                "state_projection",
            )
            if state_facts["validation"] != "valid":
                return _rejected(plan, "state_validation_failed")
            if tuple(state_facts["selected_fields"]) != plan.state_fields:
                return _rejected(plan, "state_projection_mismatch")
            projected_state = _strict_json(state_facts["state"], "projected_state")
        except ContextTransferError as exc:
            return _rejected(plan, exc.code)
        except Exception:
            return _rejected(plan, "state_projection_failed")
        try:
            transformed.extend(
                _token(item, "state_projection.transformed_fields")
                for item in state_facts["transformed_fields"]
            )
            omitted.extend(
                _token(item, "state_projection.omitted_fields")
                for item in state_facts["omitted_fields"]
            )
            transformed.extend(
                f"defaulted:{_token(item, 'state_projection.defaulted_fields')}"
                for item in state_facts["defaulted_fields"]
            )
        except (TypeError, ContextTransferError):
            return _rejected(plan, "invalid_state_projection_facts")
        selected_components.append("state")

    continuation_disposition: Literal["none", "preserved", "stateless_reconstruction", "rejected"] = "none"
    reconstruction = ["exchange_log_reader", "state_projector_resolver", "artifact_resolver"]
    if plan.continuation is not None:
        continuation = plan.continuation
        continuation_resolved = (
            continuation.reference_id.value in set(available_continuation_refs)
        )
        compatible = (
            continuation.provider == plan.destination_provider
            and continuation.model == plan.destination_model
            and continuation.api_mode == plan.destination_api_mode
            and "continuation" in codec_capabilities
            and continuation_resolved
        )
        try:
            now = datetime.fromisoformat(evaluated_at.replace("Z", "+00:00"))
            expiry = datetime.fromisoformat(continuation.expires_at.replace("Z", "+00:00")) if continuation.expires_at else None
            if now.tzinfo is None:
                raise ValueError("evaluation time must be timezone-aware")
        except (AttributeError, ValueError):
            return _rejected(plan, "invalid_evaluation_time")
        expired = expiry is not None and now >= expiry
        if compatible and not expired:
            continuation_disposition = "preserved"
            selected_components.append("continuation")
            reconstruction.append("continuation_resolver")
        elif "continuation_stateless_reconstruction" in plan.approved_losses:
            continuation_disposition = "stateless_reconstruction"
            losses.append("continuation_stateless_reconstruction")
            reconstruction.append("stateless_replay")
        else:
            if expired:
                code = "continuation_expired"
            elif not continuation_resolved:
                code = "missing_continuation_resolver"
            else:
                code = "continuation_incompatible"
            return _rejected(plan, code)
    elif plan.continuation_required:
        return _rejected(plan, "missing_continuation")

    selected_components.extend(["authority"] + (["artifacts"] if transferred_artifacts else []))
    provenance = _digest(
        {
            "plan": plan.integrity_digest,
            "source_log_id": log.log_id,
            "selected_item_ids": [item["item_id"] for item in selected_items],
            "selection_policy": plan.context_policy_digest,
            "projector": plan.state_projector_digest,
        }
    )
    return ContextTransferReceipt(
        receipt_id=f"receipt.{plan.operation_id}", plan=plan,
        selected_item_ids=tuple(item["item_id"] for item in selected_items),
        selected_exchange_ids=selected_exchange_ids,
        selected_components=tuple(dict.fromkeys(selected_components)),
        transformed_fields=tuple(dict.fromkeys(transformed)), omitted_fields=tuple(dict.fromkeys(omitted)),
        loss_facts=tuple(dict.fromkeys(losses)), continuation_disposition=continuation_disposition,
        artifact_refs=tuple(transferred_artifacts), granted_capabilities=tuple(sorted(requested_capabilities)),
        rejected_capabilities=(), rejected_budget_fields=(),
        reconstruction_requirements=tuple(dict.fromkeys(reconstruction)),
        policy_digest=plan.policy_digest, provenance_digest=provenance,
        terminal_disposition="accepted", failure_code=None,
        _selected_items_json=selected_json,
        _queued_steering_json=_canonical_json(queued, "queued_steering"),
        _projected_state_json=_canonical_json(projected_state, "projected_state") if projected_state is not None else None,
        _granted_budget_json=_canonical_json(_allocation_dict(plan.budget_request), "granted_budget"),
    )


__all__ = [
    "CONTEXT_TRANSFER_PLAN_SCHEMA_VERSION",
    "CONTEXT_TRANSFER_RECEIPT_SCHEMA_VERSION",
    "ContextTransferError",
    "StateProjector",
    "ContextSelectionPolicy",
    "ContextTransferPlan",
    "ContextTransferReceipt",
    "execute_context_transfer",
]
