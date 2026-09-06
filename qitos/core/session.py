"""Canonical contracts for durable QitOS sessions.

This module owns the shared identity vocabulary used by session, checkpoint,
conversation, tool, work-graph, and trace consumers.  It deliberately contains
data contracts only: Engine behavior and checkpoint persistence remain in their
existing owning packages.
"""

from __future__ import annotations

from dataclasses import InitVar, dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Callable, ClassVar, Dict, Iterable, Mapping, Type, TypeVar
from uuid import uuid4

from .artifact import ArtifactRef


class SessionErrorCode(str, Enum):
    """Stable machine-readable failures for the session contract."""

    MISSING_RESOLVER = "missing_resolver"
    RESOLVER_TYPE_MISMATCH = "resolver_type_mismatch"
    UNSUPPORTED_SNAPSHOT_SCHEMA = "unsupported_snapshot_schema"
    UNSUPPORTED_COMPONENT_SCHEMA = "unsupported_component_schema"
    GENERATION_CONFLICT = "generation_conflict"
    UNSAFE_PAUSE_BOUNDARY = "unsafe_pause_boundary"
    CORRUPT_SNAPSHOT = "corrupt_snapshot"
    UNAVAILABLE_SECRET = "unavailable_secret"
    SUPERSEDED_OWNER = "superseded_owner"
    UNRESOLVED_EFFECT = "unresolved_effect"
    INVALID_IDENTITY_RELATIONSHIP = "invalid_identity_relationship"
    PERSISTENCE_REJECTED = "persistence_rejected"
    PERSISTENCE_FAILED = "persistence_failed"
    UNKNOWN_COMPONENT_OWNER = "unknown_component_owner"
    COMPONENT_DIGEST_MISMATCH = "component_digest_mismatch"
    MISSING_REQUIRED_COMPONENT = "missing_required_component"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    INVALID_LIFECYCLE_OPERATION = "invalid_lifecycle_operation"
    SESSION_NOT_FOUND = "session_not_found"
    SNAPSHOT_NOT_FOUND = "snapshot_not_found"
    SNAPSHOT_SESSION_MISMATCH = "snapshot_session_mismatch"
    DUPLICATE_FORK_OPERATION = "duplicate_fork_operation"
    INCOMPATIBLE_CHECKPOINT = "incompatible_checkpoint"
    CONFIG_DIGEST_MISMATCH = "config_digest_mismatch"


class SessionContractError(ValueError):
    """Typed, redaction-safe contract failure.

    Metadata is restricted to scalar values by the full snapshot contract.  The
    identity producer uses an empty mapping so an invalid raw value can never be
    reflected into diagnostics.
    """

    def __init__(
        self,
        error_code: SessionErrorCode,
        message: str,
        *,
        recoverable: bool,
        remediation: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.recoverable = bool(recoverable)
        self.remediation = remediation
        self.metadata = MappingProxyType(_safe_failure_metadata(metadata or {}))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_code": self.error_code.value,
            "message": str(self),
            "recoverable": self.recoverable,
            "remediation": self.remediation,
            "metadata": dict(self.metadata),
        }


class IdentityKind(str, Enum):
    """Closed identity vocabulary shared by all S1 lanes."""

    SESSION = "session"
    RUN = "run"
    SNAPSHOT = "snapshot"
    CHECKPOINT = "checkpoint"
    WORK_ITEM = "work_item"
    ATTEMPT = "attempt"
    TOOL_CALL = "tool_call"
    AGENT = "agent"
    CONTINUATION = "continuation"


_IDENTITY_TOKEN = re.compile(r"^[a-z][a-z0-9_]{2,31}_[0-9a-f]{16,64}$")
_IdentityT = TypeVar("_IdentityT", bound="RuntimeIdentity")


@dataclass(frozen=True)
class RuntimeIdentity:
    """Base for distinct, JSON-safe runtime identities.

    Concrete subclasses cannot compare equal to each other even if a malicious
    caller bypasses validation and supplies the same text.  Relationships are
    explicit records; parentage is never parsed from identifier text.
    """

    value: str
    KIND: ClassVar[IdentityKind]
    PREFIX: ClassVar[str]

    def __post_init__(self) -> None:
        valid = (
            isinstance(self.value, str)
            and self.value.startswith(f"{self.PREFIX}_")
            and _IDENTITY_TOKEN.fullmatch(self.value) is not None
        )
        if not valid:
            raise SessionContractError(
                SessionErrorCode.INVALID_IDENTITY_RELATIONSHIP,
                f"Invalid {self.KIND.value} identity.",
                recoverable=False,
                remediation="Use the framework identity producer for this identity kind.",
            )

    @classmethod
    def generate(cls: Type[_IdentityT]) -> _IdentityT:
        """Generate a framework-owned opaque identity."""

        return cls(f"{cls.PREFIX}_{uuid4().hex}")

    def to_dict(self) -> Dict[str, str]:
        return {"kind": self.KIND.value, "value": self.value}

    @classmethod
    def from_dict(cls: Type[_IdentityT], payload: Mapping[str, Any]) -> _IdentityT:
        if not isinstance(payload, Mapping) or set(payload) != {"kind", "value"}:
            raise SessionContractError(
                SessionErrorCode.INVALID_IDENTITY_RELATIONSHIP,
                "Identity must contain exactly kind and value.",
                recoverable=False,
                remediation="Read the identity with the current strict codec.",
            )
        if payload.get("kind") != cls.KIND.value:
            raise SessionContractError(
                SessionErrorCode.INVALID_IDENTITY_RELATIONSHIP,
                f"Expected {cls.KIND.value} identity.",
                recoverable=False,
                remediation="Use the identity type declared by the containing field.",
            )
        value = payload.get("value")
        if not isinstance(value, str):
            raise SessionContractError(
                SessionErrorCode.INVALID_IDENTITY_RELATIONSHIP,
                "Identity value must be a string.",
                recoverable=False,
                remediation="Use a framework-generated identity value.",
            )
        return cls(value)


@dataclass(frozen=True)
class SessionIdentity(RuntimeIdentity):
    KIND: ClassVar[IdentityKind] = IdentityKind.SESSION
    PREFIX: ClassVar[str] = "session"


@dataclass(frozen=True)
class RunIdentity(RuntimeIdentity):
    KIND: ClassVar[IdentityKind] = IdentityKind.RUN
    PREFIX: ClassVar[str] = "run"


@dataclass(frozen=True)
class SnapshotIdentity(RuntimeIdentity):
    KIND: ClassVar[IdentityKind] = IdentityKind.SNAPSHOT
    PREFIX: ClassVar[str] = "snapshot"


@dataclass(frozen=True)
class CheckpointIdentity(RuntimeIdentity):
    KIND: ClassVar[IdentityKind] = IdentityKind.CHECKPOINT
    PREFIX: ClassVar[str] = "checkpoint"


@dataclass(frozen=True)
class WorkItemIdentity(RuntimeIdentity):
    KIND: ClassVar[IdentityKind] = IdentityKind.WORK_ITEM
    PREFIX: ClassVar[str] = "work_item"


@dataclass(frozen=True)
class AttemptIdentity(RuntimeIdentity):
    KIND: ClassVar[IdentityKind] = IdentityKind.ATTEMPT
    PREFIX: ClassVar[str] = "attempt"


@dataclass(frozen=True)
class ToolCallIdentity(RuntimeIdentity):
    KIND: ClassVar[IdentityKind] = IdentityKind.TOOL_CALL
    PREFIX: ClassVar[str] = "tool_call"


@dataclass(frozen=True)
class AgentIdentity(RuntimeIdentity):
    KIND: ClassVar[IdentityKind] = IdentityKind.AGENT
    PREFIX: ClassVar[str] = "agent"


@dataclass(frozen=True)
class ContinuationIdentity(RuntimeIdentity):
    KIND: ClassVar[IdentityKind] = IdentityKind.CONTINUATION
    PREFIX: ClassVar[str] = "continuation"


_IDENTITY_TYPES: Mapping[IdentityKind, Type[RuntimeIdentity]] = MappingProxyType(
    {
        IdentityKind.SESSION: SessionIdentity,
        IdentityKind.RUN: RunIdentity,
        IdentityKind.SNAPSHOT: SnapshotIdentity,
        IdentityKind.CHECKPOINT: CheckpointIdentity,
        IdentityKind.WORK_ITEM: WorkItemIdentity,
        IdentityKind.ATTEMPT: AttemptIdentity,
        IdentityKind.TOOL_CALL: ToolCallIdentity,
        IdentityKind.AGENT: AgentIdentity,
        IdentityKind.CONTINUATION: ContinuationIdentity,
    }
)


def identity_from_dict(payload: Mapping[str, Any]) -> RuntimeIdentity:
    """Strictly decode one identity without inferring its kind from its value."""

    if not isinstance(payload, Mapping) or set(payload) != {"kind", "value"}:
        raise SessionContractError(
            SessionErrorCode.INVALID_IDENTITY_RELATIONSHIP,
            "Identity must contain exactly kind and value.",
            recoverable=False,
            remediation="Read the identity with the current strict codec.",
        )
    raw_kind = payload.get("kind")
    try:
        kind = IdentityKind(raw_kind)
    except (TypeError, ValueError) as exc:
        raise SessionContractError(
            SessionErrorCode.INVALID_IDENTITY_RELATIONSHIP,
            "Identity kind is unsupported.",
            recoverable=False,
            remediation="Use an identity kind from the current vocabulary.",
        ) from exc
    return _IDENTITY_TYPES[kind].from_dict(payload)


class IdentityRelation(str, Enum):
    """Explicit relationship kinds; never derive these from names."""

    SESSION_RUN = "session_run"
    SESSION_SNAPSHOT = "session_snapshot"
    SNAPSHOT_CHECKPOINT = "snapshot_checkpoint"
    RUN_WORK_ITEM = "run_work_item"
    WORK_ITEM_ATTEMPT = "work_item_attempt"
    ATTEMPT_TOOL_CALL = "attempt_tool_call"
    AGENT_OWNS_WORK_ITEM = "agent_owns_work_item"
    RESTORED_FROM = "restored_from"
    FORKED_FROM = "forked_from"


_RELATION_KINDS: Mapping[IdentityRelation, tuple[IdentityKind, IdentityKind]] = (
    MappingProxyType(
        {
            IdentityRelation.SESSION_RUN: (IdentityKind.SESSION, IdentityKind.RUN),
            IdentityRelation.SESSION_SNAPSHOT: (
                IdentityKind.SESSION,
                IdentityKind.SNAPSHOT,
            ),
            IdentityRelation.SNAPSHOT_CHECKPOINT: (
                IdentityKind.SNAPSHOT,
                IdentityKind.CHECKPOINT,
            ),
            IdentityRelation.RUN_WORK_ITEM: (
                IdentityKind.RUN,
                IdentityKind.WORK_ITEM,
            ),
            IdentityRelation.WORK_ITEM_ATTEMPT: (
                IdentityKind.WORK_ITEM,
                IdentityKind.ATTEMPT,
            ),
            IdentityRelation.ATTEMPT_TOOL_CALL: (
                IdentityKind.ATTEMPT,
                IdentityKind.TOOL_CALL,
            ),
            IdentityRelation.AGENT_OWNS_WORK_ITEM: (
                IdentityKind.AGENT,
                IdentityKind.WORK_ITEM,
            ),
            IdentityRelation.RESTORED_FROM: (
                IdentityKind.RUN,
                IdentityKind.SNAPSHOT,
            ),
            IdentityRelation.FORKED_FROM: (
                IdentityKind.SESSION,
                IdentityKind.SNAPSHOT,
            ),
        }
    )
)


@dataclass(frozen=True)
class IdentityRelationship:
    """One validated, directional identity edge."""

    relation: IdentityRelation
    source: RuntimeIdentity
    target: RuntimeIdentity

    def __post_init__(self) -> None:
        expected = _RELATION_KINDS.get(self.relation)
        actual = (self.source.KIND, self.target.KIND)
        if expected != actual:
            raise SessionContractError(
                SessionErrorCode.INVALID_IDENTITY_RELATIONSHIP,
                f"Invalid identity kinds for {self.relation.value} relationship.",
                recoverable=False,
                remediation="Use the declared source and target identity kinds.",
                metadata={
                    "relation": self.relation.value,
                    "source_kind": self.source.KIND.value,
                    "target_kind": self.target.KIND.value,
                },
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relation": self.relation.value,
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IdentityRelationship":
        if not isinstance(payload, Mapping) or set(payload) != {
            "relation",
            "source",
            "target",
        }:
            raise SessionContractError(
                SessionErrorCode.INVALID_IDENTITY_RELATIONSHIP,
                "Identity relationship has unknown or missing fields.",
                recoverable=False,
                remediation="Use the current strict relationship codec.",
            )
        try:
            relation = IdentityRelation(payload.get("relation"))
        except (TypeError, ValueError) as exc:
            raise SessionContractError(
                SessionErrorCode.INVALID_IDENTITY_RELATIONSHIP,
                "Identity relationship kind is unsupported.",
                recoverable=False,
                remediation="Use a relationship from the current vocabulary.",
            ) from exc
        source = payload.get("source")
        target = payload.get("target")
        if not isinstance(source, Mapping) or not isinstance(target, Mapping):
            raise SessionContractError(
                SessionErrorCode.INVALID_IDENTITY_RELATIONSHIP,
                "Relationship endpoints must be typed identities.",
                recoverable=False,
                remediation="Encode source and target with kind and value.",
            )
        return cls(
            relation=relation,
            source=identity_from_dict(source),
            target=identity_from_dict(target),
        )


class SessionLifecycle(str, Enum):
    """Canonical lifecycle for one session owner view."""

    CREATED = "created"
    RUNNING = "running"
    PAUSE_REQUESTED = "pause_requested"
    PAUSING = "pausing"
    PAUSED = "paused"
    WAITING_INPUT = "waiting_input"
    RESTORING = "restoring"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"

    @property
    def terminal(self) -> bool:
        return self in {
            SessionLifecycle.COMPLETED,
            SessionLifecycle.FAILED,
            SessionLifecycle.CANCELLED,
            SessionLifecycle.SUPERSEDED,
        }


class SessionOperation(str, Enum):
    """Operations gated by lifecycle state."""

    RUN = "run"
    PAUSE = "pause"
    RESTORE = "restore"
    FORK = "fork"


_LIFECYCLE_TRANSITIONS: Mapping[SessionLifecycle, frozenset[SessionLifecycle]] = (
    MappingProxyType(
        {
            SessionLifecycle.CREATED: frozenset(
                {SessionLifecycle.RUNNING, SessionLifecycle.CANCELLED}
            ),
            SessionLifecycle.RUNNING: frozenset(
                {
                    SessionLifecycle.PAUSE_REQUESTED,
                    SessionLifecycle.COMPLETED,
                    SessionLifecycle.FAILED,
                    SessionLifecycle.CANCELLED,
                    SessionLifecycle.SUPERSEDED,
                }
            ),
            SessionLifecycle.PAUSE_REQUESTED: frozenset(
                {
                    SessionLifecycle.PAUSING,
                    SessionLifecycle.RUNNING,
                    SessionLifecycle.FAILED,
                    SessionLifecycle.CANCELLED,
                    SessionLifecycle.SUPERSEDED,
                }
            ),
            SessionLifecycle.PAUSING: frozenset(
                {
                    SessionLifecycle.PAUSED,
                    SessionLifecycle.WAITING_INPUT,
                    SessionLifecycle.FAILED,
                    SessionLifecycle.CANCELLED,
                    SessionLifecycle.SUPERSEDED,
                }
            ),
            SessionLifecycle.PAUSED: frozenset(
                {SessionLifecycle.RESTORING, SessionLifecycle.SUPERSEDED}
            ),
            SessionLifecycle.WAITING_INPUT: frozenset(
                {
                    SessionLifecycle.RESTORING,
                    SessionLifecycle.CANCELLED,
                    SessionLifecycle.SUPERSEDED,
                }
            ),
            SessionLifecycle.RESTORING: frozenset(
                {
                    SessionLifecycle.RUNNING,
                    SessionLifecycle.FAILED,
                    SessionLifecycle.SUPERSEDED,
                }
            ),
            SessionLifecycle.COMPLETED: frozenset(),
            SessionLifecycle.FAILED: frozenset(),
            SessionLifecycle.CANCELLED: frozenset(),
            SessionLifecycle.SUPERSEDED: frozenset(),
        }
    )
)

_OPERATION_STATES: Mapping[SessionOperation, frozenset[SessionLifecycle]] = (
    MappingProxyType(
        {
            SessionOperation.RUN: frozenset(
                {
                    SessionLifecycle.CREATED,
                    SessionLifecycle.PAUSED,
                    SessionLifecycle.WAITING_INPUT,
                }
            ),
            SessionOperation.PAUSE: frozenset(
                {
                    SessionLifecycle.RUNNING,
                    SessionLifecycle.PAUSE_REQUESTED,
                    SessionLifecycle.PAUSING,
                }
            ),
            SessionOperation.RESTORE: frozenset(
                {SessionLifecycle.PAUSED, SessionLifecycle.WAITING_INPUT}
            ),
            SessionOperation.FORK: frozenset(
                {
                    SessionLifecycle.PAUSED,
                    SessionLifecycle.WAITING_INPUT,
                    SessionLifecycle.COMPLETED,
                    SessionLifecycle.FAILED,
                    SessionLifecycle.CANCELLED,
                    SessionLifecycle.SUPERSEDED,
                }
            ),
        }
    )
)


def lifecycle_can_transition(
    current: SessionLifecycle, target: SessionLifecycle
) -> bool:
    """Return whether a lifecycle transition is defined."""

    return target in _LIFECYCLE_TRANSITIONS[current]


def lifecycle_allows(
    lifecycle: SessionLifecycle, operation: SessionOperation
) -> bool:
    """Return whether an operation can be requested from this state."""

    return lifecycle in _OPERATION_STATES[operation]


class SafeBoundaryKind(str, Enum):
    """Declared boundaries at which persistence may be considered migratable."""

    AFTER_MODEL_RESULT = "after_model_result"
    AFTER_TOOL_RESULT = "after_tool_result"
    PARTIAL_PARALLEL_RECORDED = "partial_parallel_recorded"
    WAITING_INPUT = "waiting_input"
    IN_FLIGHT_OPERATION = "in_flight_operation"


@dataclass(frozen=True)
class PauseSafety:
    """Quiescence facts used to decide whether a pause can become durable."""

    boundary: SafeBoundaryKind
    completed_slots_recorded: bool = True
    open_slots_recorded: bool = True
    framework_workers_quiesced: bool = True
    unresolved_effect_count: int = 0

    def __post_init__(self) -> None:
        if (
            isinstance(self.unresolved_effect_count, bool)
            or not isinstance(self.unresolved_effect_count, int)
            or self.unresolved_effect_count < 0
        ):
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Unresolved effect count must be a non-negative integer.",
                recoverable=False,
                remediation="Rebuild the pause-safety component from validated receipts.",
            )

    @property
    def migratable(self) -> bool:
        return (
            self.boundary is not SafeBoundaryKind.IN_FLIGHT_OPERATION
            and self.completed_slots_recorded
            and self.open_slots_recorded
            and self.framework_workers_quiesced
            and self.unresolved_effect_count == 0
        )

    def require_migratable(self) -> None:
        if self.unresolved_effect_count:
            raise SessionContractError(
                SessionErrorCode.UNRESOLVED_EFFECT,
                "Pause has unresolved external effects.",
                recoverable=True,
                remediation="Reconcile each unresolved effect before restoring or retrying.",
                metadata={"unresolved_effect_count": self.unresolved_effect_count},
            )
        if not self.migratable:
            raise SessionContractError(
                SessionErrorCode.UNSAFE_PAUSE_BOUNDARY,
                "Execution has not reached a migratable pause boundary.",
                recoverable=True,
                remediation="Wait for recorded results and framework-owned workers to quiesce.",
                metadata={"boundary": self.boundary.value},
            )


@dataclass(frozen=True, order=True)
class HeadGeneration:
    """Monotonic concurrency version of the authoritative session head."""

    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int) or self.value < 0:
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Head generation must be a non-negative integer.",
                recoverable=False,
                remediation="Read generation from the authoritative session head.",
            )

    def next(self) -> "HeadGeneration":
        return HeadGeneration(self.value + 1)


@dataclass(frozen=True)
class SessionHead:
    """The one authoritative mutable pointer for a session."""

    session_id: SessionIdentity
    snapshot_id: SnapshotIdentity
    checkpoint_id: CheckpointIdentity
    generation: HeadGeneration
    owner_run_id: RunIdentity

    def advance(
        self,
        *,
        expected_generation: HeadGeneration,
        owner_run_id: RunIdentity,
        snapshot_id: SnapshotIdentity,
        checkpoint_id: CheckpointIdentity,
    ) -> "SessionHead":
        """Validate a pure compare-and-set head advance."""

        if expected_generation != self.generation:
            raise SessionContractError(
                SessionErrorCode.GENERATION_CONFLICT,
                "Session head generation changed before commit.",
                recoverable=True,
                remediation="Reload the authoritative head before deciding whether to retry.",
                metadata={
                    "expected_generation": expected_generation.value,
                    "actual_generation": self.generation.value,
                },
            )
        if owner_run_id != self.owner_run_id:
            raise SessionContractError(
                SessionErrorCode.SUPERSEDED_OWNER,
                "This run no longer owns the session head.",
                recoverable=False,
                remediation="Stop the stale process and inspect the current session owner.",
            )
        return SessionHead(
            session_id=self.session_id,
            snapshot_id=snapshot_id,
            checkpoint_id=checkpoint_id,
            generation=self.generation.next(),
            owner_run_id=owner_run_id,
        )


class ResolverNamespace(str, Enum):
    """Closed namespaces for process-local resource resolution."""

    AGENT = "agent"
    MODEL = "model"
    TOOL_REGISTRY = "tool_registry"
    ENVIRONMENT = "environment"
    ARTIFACT_STORE = "artifact_store"
    SECRET = "secret"
    CHECKPOINT_STORE = "checkpoint_store"
    PROVIDER_CONTINUATION = "provider_continuation"
    RUNTIME_EVENT_SINK = "runtime_event_sink"


_REFERENCE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_CAPABILITY_TOKEN = re.compile(r"^[a-z][a-z0-9_.:-]{1,95}$")
_SCHEMA_TOKEN = re.compile(r"^[a-z][a-z0-9_.:-]{1,95}/v[1-9][0-9]*$")
_HOST_LOCAL_OR_CREDENTIAL_VALUE = re.compile(
    r"(?i)(?:^|\s)(?:/users/|/home/|[a-z]:\\)|"
    r"(?:authorization\s*[:=]|bearer\s+|api[_-]?key\s*[:=]|password\s*[:=])"
)


@dataclass(frozen=True)
class ResolverReference:
    """Serializable locator for a live resource resolved in a new process."""

    namespace: ResolverNamespace
    reference_id: str
    expected_capability: str
    version: int = 1

    def __post_init__(self) -> None:
        if (
            not isinstance(self.reference_id, str)
            or _REFERENCE_TOKEN.fullmatch(self.reference_id) is None
            or self.reference_id.startswith((".", "~"))
        ):
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Resolver reference ID is not portable.",
                recoverable=False,
                remediation="Persist a logical resolver alias, never a secret or host path.",
            )
        lowered = self.reference_id.lower()
        if any(token in lowered for token in ("password", "credential", "bearer", "api_key")):
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Resolver reference ID may not contain credential material.",
                recoverable=False,
                remediation="Use a non-secret logical alias.",
            )
        if (
            not isinstance(self.expected_capability, str)
            or _CAPABILITY_TOKEN.fullmatch(self.expected_capability) is None
        ):
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Resolver capability is invalid.",
                recoverable=False,
                remediation="Use a stable capability identifier.",
            )
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Resolver reference version must be a positive integer.",
                recoverable=False,
                remediation="Use the current resolver reference version.",
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "namespace": self.namespace.value,
            "reference_id": self.reference_id,
            "expected_capability": self.expected_capability,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResolverReference":
        _require_exact_fields(
            payload,
            {"namespace", "reference_id", "expected_capability", "version"},
            SessionErrorCode.CORRUPT_SNAPSHOT,
            "resolver reference",
        )
        try:
            namespace = ResolverNamespace(payload.get("namespace"))
        except (TypeError, ValueError) as exc:
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Resolver namespace is unsupported.",
                recoverable=False,
                remediation="Use a namespace from the current resolver contract.",
            ) from exc
        return cls(
            namespace=namespace,
            reference_id=payload["reference_id"],
            expected_capability=payload["expected_capability"],
            version=payload["version"],
        )


@dataclass(frozen=True)
class ResolvedResource:
    """Process-local resolution result; never serializable into a snapshot."""

    namespace: ResolverNamespace
    capabilities: frozenset[str]
    resource: Any


Resolver = Callable[[ResolverReference], ResolvedResource | None]


class ResolverRegistry:
    """Caller-owned process-local resolver set with typed diagnostics."""

    def __init__(self, resolvers: Mapping[ResolverNamespace, Resolver] | None = None):
        self._resolvers = dict(resolvers or {})
        self._resources: Dict[tuple[ResolverNamespace, str], ResolvedResource] = {}
        if any(not callable(value) for value in self._resolvers.values()):
            raise SessionContractError(
                SessionErrorCode.RESOLVER_TYPE_MISMATCH,
                "Every resolver must be callable.",
                recoverable=True,
                remediation="Register a callable for each resolver namespace.",
            )

    def register(self, namespace: ResolverNamespace, resolver: Resolver) -> None:
        """Register or replace one explicit namespace resolver."""
        if not isinstance(namespace, ResolverNamespace) or not callable(resolver):
            raise SessionContractError(
                SessionErrorCode.RESOLVER_TYPE_MISMATCH,
                "Resolver registration is incompatible.",
                recoverable=True,
                remediation="Register a callable under a canonical namespace.",
            )
        self._resolvers[namespace] = resolver

    def register_resource(
        self,
        reference: ResolverReference,
        resource: Any,
        *,
        capabilities: Iterable[str] | None = None,
    ) -> None:
        """Bind one process-local resource to one logical reference."""
        declared = frozenset(capabilities or {reference.expected_capability})
        if reference.expected_capability not in declared:
            raise SessionContractError(
                SessionErrorCode.RESOLVER_TYPE_MISMATCH,
                "Bound resource lacks the reference's expected capability.",
                recoverable=True,
                remediation="Declare the capability required by the logical reference.",
            )
        self._resources[(reference.namespace, reference.reference_id)] = ResolvedResource(
            namespace=reference.namespace,
            capabilities=declared,
            resource=resource,
        )

    def copy(self) -> "ResolverRegistry":
        """Return an isolated registry with the same process-local bindings."""
        registry = ResolverRegistry(self._resolvers)
        registry._resources = dict(self._resources)
        return registry

    def resolve(self, reference: ResolverReference) -> ResolvedResource:
        bound = self._resources.get((reference.namespace, reference.reference_id))
        if bound is not None:
            if reference.expected_capability not in bound.capabilities:
                raise SessionContractError(
                    SessionErrorCode.RESOLVER_TYPE_MISMATCH,
                    "Bound resource lacks the expected capability.",
                    recoverable=True,
                    remediation="Bind a resource with the expected capability.",
                    metadata={
                        "namespace": reference.namespace.value,
                        "expected_capability": reference.expected_capability,
                    },
                )
            return bound
        resolver = self._resolvers.get(reference.namespace)
        if resolver is None:
            raise SessionContractError(
                SessionErrorCode.MISSING_RESOLVER,
                f"No {reference.namespace.value} resolver is registered.",
                recoverable=True,
                remediation="Register the missing resolver or use the framework default set.",
                metadata={"namespace": reference.namespace.value},
            )
        try:
            result = resolver(reference)
        except Exception as exc:
            code = (
                SessionErrorCode.UNAVAILABLE_SECRET
                if reference.namespace is ResolverNamespace.SECRET
                else SessionErrorCode.RESOLVER_TYPE_MISMATCH
            )
            message = (
                "The referenced secret is unavailable."
                if code is SessionErrorCode.UNAVAILABLE_SECRET
                else "Resolver failed to return a compatible resource."
            )
            raise SessionContractError(
                code,
                message,
                recoverable=True,
                remediation="Check resolver availability and capability configuration.",
                metadata={"namespace": reference.namespace.value},
            ) from exc
        if result is None and reference.namespace is ResolverNamespace.SECRET:
            raise SessionContractError(
                SessionErrorCode.UNAVAILABLE_SECRET,
                "The referenced secret is unavailable.",
                recoverable=True,
                remediation="Make the secret alias available to the restore process.",
                metadata={"namespace": reference.namespace.value},
            )
        if (
            not isinstance(result, ResolvedResource)
            or result.namespace is not reference.namespace
            or reference.expected_capability not in result.capabilities
        ):
            raise SessionContractError(
                SessionErrorCode.RESOLVER_TYPE_MISMATCH,
                "Resolver returned an incompatible resource.",
                recoverable=True,
                remediation="Register a resource with the expected namespace and capability.",
                metadata={
                    "namespace": reference.namespace.value,
                    "expected_capability": reference.expected_capability,
                },
            )
        return result


class ComponentSlot(str, Enum):
    """Stable envelope slots; semantic owners define payload schemas."""

    AGENT_STATE = "agent_state"
    ENGINE_PROGRESS = "engine_progress"
    EXCHANGE_CONTEXT = "exchange_context"
    PARTIAL_PARALLEL_BATCH = "partial_parallel_batch"
    TOOL_EFFECTS = "tool_effects"
    QUEUED_STEERING = "queued_steering"
    PROVIDER_CONTINUATION = "provider_continuation"
    WORK_GRAPH = "work_graph"
    BUDGET_CAPABILITY = "budget_capability"
    TRACE_LINEAGE = "trace_lineage"
    FORK_LINEAGE = "fork_lineage"


CURRENT_SNAPSHOT_SCHEMA = 2


@dataclass(frozen=True)
class SnapshotComponentCodec:
    """One semantic owner's encoder/decoder for one component schema."""

    slot: str
    owner: str
    schema_version: str
    required: bool
    encode: Callable[[Any], Mapping[str, Any]]
    decode: Callable[[Mapping[str, Any]], Any]

    def __post_init__(self) -> None:
        for name in ("slot", "owner"):
            value = getattr(self, name)
            if not isinstance(value, str) or _CAPABILITY_TOKEN.fullmatch(value) is None:
                raise SessionContractError(
                    SessionErrorCode.UNSUPPORTED_COMPONENT_SCHEMA,
                    "Snapshot component codec declaration is invalid.",
                    recoverable=False,
                    remediation="Use portable owner, slot, and schema identifiers.",
                )
        if (
            not isinstance(self.schema_version, str)
            or _SCHEMA_TOKEN.fullmatch(self.schema_version) is None
        ):
            raise SessionContractError(
                SessionErrorCode.UNSUPPORTED_COMPONENT_SCHEMA,
                "Snapshot component codec schema is invalid.",
                recoverable=False,
                remediation="Use a namespaced /vN schema identifier.",
            )
        if not isinstance(self.required, bool) or not callable(self.encode) or not callable(
            self.decode
        ):
            raise SessionContractError(
                SessionErrorCode.UNSUPPORTED_COMPONENT_SCHEMA,
                "Snapshot component codec declaration is incomplete.",
                recoverable=False,
                remediation="Declare required, encode, and decode fields explicitly.",
            )


class SnapshotComponentRegistry:
    """Explicit composition of independently owned component codecs."""

    def __init__(self, codecs: Iterable[SnapshotComponentCodec] = ()) -> None:
        by_key: Dict[tuple[str, str, str], SnapshotComponentCodec] = {}
        owners: set[str] = set()
        required: set[tuple[str, str]] = set()
        for codec in codecs:
            if not isinstance(codec, SnapshotComponentCodec):
                raise TypeError("snapshot registry entries must be SnapshotComponentCodec")
            key = (codec.owner, codec.slot, codec.schema_version)
            if key in by_key:
                raise SessionContractError(
                    SessionErrorCode.UNSUPPORTED_COMPONENT_SCHEMA,
                    "Snapshot component codec is registered more than once.",
                    recoverable=False,
                    remediation="Register one codec for each owner, slot, and schema.",
                )
            by_key[key] = codec
            owners.add(codec.owner)
            if codec.required:
                required.add((codec.owner, codec.slot))
        self._codecs = MappingProxyType(by_key)
        self._owners = frozenset(owners)
        self._required = frozenset(required)

    @property
    def required_components(self) -> frozenset[tuple[str, str]]:
        return self._required

    def codec_for(self, component: "SnapshotComponent") -> SnapshotComponentCodec:
        if component.owner not in self._owners:
            raise SessionContractError(
                SessionErrorCode.UNKNOWN_COMPONENT_OWNER,
                "Snapshot component owner is not registered.",
                recoverable=False,
                remediation="Install the semantic owner's component codec before restore.",
            )
        codec = self._codecs.get(
            (component.owner, component.slot, component.schema_version)
        )
        if codec is None:
            raise SessionContractError(
                SessionErrorCode.UNSUPPORTED_COMPONENT_SCHEMA,
                "Snapshot component schema is not registered.",
                recoverable=False,
                remediation="Install a reader or explicit migration for this component schema.",
                metadata={"owner": component.owner, "slot": component.slot},
            )
        if component.required != codec.required:
            raise SessionContractError(
                SessionErrorCode.UNSUPPORTED_COMPONENT_SCHEMA,
                "Snapshot component required policy disagrees with its owner codec.",
                recoverable=False,
                remediation="Write the required flag declared by the owner codec.",
            )
        return codec

    def validate(self, components: Iterable["SnapshotComponent"]) -> None:
        present: set[tuple[str, str]] = set()
        for component in components:
            codec = self.codec_for(component)
            codec.decode(_thaw_json(component.payload))
            present.add((component.owner, component.slot))
        if not self._required.issubset(present):
            raise SessionContractError(
                SessionErrorCode.MISSING_REQUIRED_COMPONENT,
                "Snapshot is missing a component required by the composed registry.",
                recoverable=False,
                remediation="Provide every required owner component before persistence.",
                metadata={"missing_count": len(self._required - present)},
            )

    def decode(self, component: "SnapshotComponent") -> Any:
        codec = self.codec_for(component)
        return codec.decode(_thaw_json(component.payload))


def _mapping_component(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SessionContractError(
            SessionErrorCode.CORRUPT_SNAPSHOT,
            "Core snapshot component must be a JSON object.",
            recoverable=False,
            remediation="Encode core component facts as a JSON object.",
        )
    return value


@dataclass(frozen=True)
class AgentStateSnapshotComponent:
    agent_id: AgentIdentity
    state_schema: str
    state: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.agent_id, AgentIdentity):
            raise SessionContractError(
                SessionErrorCode.INVALID_IDENTITY_RELATIONSHIP,
                "Agent state requires AgentIdentity.",
                recoverable=False,
                remediation="Decode agent_id with the canonical identity codec.",
            )
        if not isinstance(self.state_schema, str) or _CAPABILITY_TOKEN.fullmatch(
            self.state_schema
        ) is None:
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Agent state schema is invalid.",
                recoverable=False,
                remediation="Use a portable state schema identifier.",
            )
        object.__setattr__(self, "state", _mapping_component(self.state))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id.to_dict(),
            "state_schema": self.state_schema,
            "state": _thaw_json(_freeze_json(self.state, path="agent_state.state")),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AgentStateSnapshotComponent":
        _require_exact_fields(
            payload,
            {"agent_id", "state_schema", "state"},
            SessionErrorCode.CORRUPT_SNAPSHOT,
            "agent state component",
        )
        return cls(
            agent_id=AgentIdentity.from_dict(payload["agent_id"]),
            state_schema=payload["state_schema"],
            state=payload["state"],
        )


@dataclass(frozen=True)
class TraceLineageSnapshotComponent:
    run_id: RunIdentity
    trace_complete: bool
    parent_run_id: RunIdentity | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, RunIdentity) or (
            self.parent_run_id is not None
            and not isinstance(self.parent_run_id, RunIdentity)
        ):
            raise SessionContractError(
                SessionErrorCode.INVALID_IDENTITY_RELATIONSHIP,
                "Trace lineage requires RunIdentity values.",
                recoverable=False,
                remediation="Decode trace lineage with the canonical identity codec.",
            )
        if not isinstance(self.trace_complete, bool):
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Trace completeness must be boolean.",
                recoverable=False,
                remediation="Write an explicit trace completeness fact.",
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id.to_dict(),
            "trace_complete": self.trace_complete,
            "parent_run_id": (
                self.parent_run_id.to_dict() if self.parent_run_id else None
            ),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TraceLineageSnapshotComponent":
        _require_exact_fields(
            payload,
            {"run_id", "trace_complete", "parent_run_id"},
            SessionErrorCode.CORRUPT_SNAPSHOT,
            "trace lineage component",
        )
        return cls(
            run_id=RunIdentity.from_dict(payload["run_id"]),
            trace_complete=payload["trace_complete"],
            parent_run_id=(
                RunIdentity.from_dict(payload["parent_run_id"])
                if payload["parent_run_id"] is not None
                else None
            ),
        )


@dataclass(frozen=True)
class ForkLineageSnapshotComponent:
    """Explicit work ownership and optional immutable fork ancestry.

    This is a separate component/schema so the established trace-lineage writer
    remains byte-compatible.  Parentage is represented only by typed fields;
    consumers never need to inspect identifier spelling.
    """

    work_item_id: WorkItemIdentity
    attempt_id: AttemptIdentity
    source_session_id: SessionIdentity | None = None
    source_snapshot_id: SnapshotIdentity | None = None
    source_checkpoint_id: CheckpointIdentity | None = None
    source_work_item_id: WorkItemIdentity | None = None
    fork_operation_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.work_item_id, WorkItemIdentity) or not isinstance(
            self.attempt_id, AttemptIdentity
        ):
            raise SessionContractError(
                SessionErrorCode.INVALID_IDENTITY_RELATIONSHIP,
                "Fork lineage requires work-item and attempt identities.",
                recoverable=False,
                remediation="Decode fork lineage with the canonical identity types.",
            )
        ancestry = (
            self.source_session_id,
            self.source_snapshot_id,
            self.source_checkpoint_id,
            self.source_work_item_id,
            self.fork_operation_id,
        )
        if any(item is not None for item in ancestry) and any(
            item is None for item in ancestry
        ):
            raise SessionContractError(
                SessionErrorCode.INVALID_IDENTITY_RELATIONSHIP,
                "Fork ancestry must be either complete or absent.",
                recoverable=False,
                remediation="Persist every source identity and the fork operation together.",
            )
        if self.fork_operation_id is not None and (
            not isinstance(self.fork_operation_id, str)
            or re.fullmatch(r"fork_[0-9a-f]{16,64}", self.fork_operation_id) is None
        ):
            raise SessionContractError(
                SessionErrorCode.INVALID_IDENTITY_RELATIONSHIP,
                "Fork operation identity is invalid.",
                recoverable=False,
                remediation="Use the framework fork operation identity producer.",
            )

    @property
    def forked(self) -> bool:
        return self.source_session_id is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "work_item_id": self.work_item_id.to_dict(),
            "attempt_id": self.attempt_id.to_dict(),
            "source_session_id": (
                self.source_session_id.to_dict() if self.source_session_id else None
            ),
            "source_snapshot_id": (
                self.source_snapshot_id.to_dict() if self.source_snapshot_id else None
            ),
            "source_checkpoint_id": (
                self.source_checkpoint_id.to_dict()
                if self.source_checkpoint_id
                else None
            ),
            "source_work_item_id": (
                self.source_work_item_id.to_dict()
                if self.source_work_item_id
                else None
            ),
            "fork_operation_id": self.fork_operation_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ForkLineageSnapshotComponent":
        _require_exact_fields(
            payload,
            {
                "work_item_id",
                "attempt_id",
                "source_session_id",
                "source_snapshot_id",
                "source_checkpoint_id",
                "source_work_item_id",
                "fork_operation_id",
            },
            SessionErrorCode.CORRUPT_SNAPSHOT,
            "fork lineage component",
        )
        return cls(
            work_item_id=WorkItemIdentity.from_dict(payload["work_item_id"]),
            attempt_id=AttemptIdentity.from_dict(payload["attempt_id"]),
            source_session_id=(
                SessionIdentity.from_dict(payload["source_session_id"])
                if payload["source_session_id"] is not None
                else None
            ),
            source_snapshot_id=(
                SnapshotIdentity.from_dict(payload["source_snapshot_id"])
                if payload["source_snapshot_id"] is not None
                else None
            ),
            source_checkpoint_id=(
                CheckpointIdentity.from_dict(payload["source_checkpoint_id"])
                if payload["source_checkpoint_id"] is not None
                else None
            ),
            source_work_item_id=(
                WorkItemIdentity.from_dict(payload["source_work_item_id"])
                if payload["source_work_item_id"] is not None
                else None
            ),
            fork_operation_id=payload["fork_operation_id"],
        )


def _encode_agent_state(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, AgentStateSnapshotComponent):
        raise SessionContractError(
            SessionErrorCode.CORRUPT_SNAPSHOT,
            "Agent-state codec requires AgentStateSnapshotComponent.",
            recoverable=False,
            remediation="Use the typed agent-state component producer.",
        )
    return value.to_dict()


def _encode_trace_lineage(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, TraceLineageSnapshotComponent):
        raise SessionContractError(
            SessionErrorCode.CORRUPT_SNAPSHOT,
            "Trace-lineage codec requires TraceLineageSnapshotComponent.",
            recoverable=False,
            remediation="Use the typed trace-lineage component producer.",
        )
    return value.to_dict()


def _encode_fork_lineage(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, ForkLineageSnapshotComponent):
        raise SessionContractError(
            SessionErrorCode.CORRUPT_SNAPSHOT,
            "Fork-lineage codec requires ForkLineageSnapshotComponent.",
            recoverable=False,
            remediation="Use the typed fork-lineage component producer.",
        )
    return value.to_dict()


CORE_SNAPSHOT_COMPONENT_CODECS = (
    SnapshotComponentCodec(
        slot=ComponentSlot.AGENT_STATE.value,
        owner="qitos.session",
        schema_version="qitos.session.agent_state/v1",
        required=True,
        encode=_encode_agent_state,
        decode=AgentStateSnapshotComponent.from_dict,
    ),
    *tuple(
        SnapshotComponentCodec(
            slot=slot.value,
            owner="qitos.session",
            schema_version=f"qitos.session.{slot.value}/v1",
            required=True,
            encode=_mapping_component,
            decode=_mapping_component,
        )
        for slot in (
            ComponentSlot.ENGINE_PROGRESS,
            ComponentSlot.BUDGET_CAPABILITY,
        )
    ),
    SnapshotComponentCodec(
        slot=ComponentSlot.TRACE_LINEAGE.value,
        owner="qitos.session",
        schema_version="qitos.session.trace_lineage/v1",
        required=True,
        encode=_encode_trace_lineage,
        decode=TraceLineageSnapshotComponent.from_dict,
    ),
    SnapshotComponentCodec(
        slot=ComponentSlot.FORK_LINEAGE.value,
        owner="qitos.session",
        schema_version="qitos.session.fork_lineage/v1",
        required=False,
        encode=_encode_fork_lineage,
        decode=ForkLineageSnapshotComponent.from_dict,
    ),
)
CORE_SNAPSHOT_COMPONENT_REGISTRY = SnapshotComponentRegistry(
    CORE_SNAPSHOT_COMPONENT_CODECS
)
SUPPORTED_COMPONENT_SCHEMAS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        codec.slot: frozenset({codec.schema_version})
        for codec in CORE_SNAPSHOT_COMPONENT_CODECS
    }
)
REQUIRED_COMPONENT_SLOTS = frozenset(
    codec.slot for codec in CORE_SNAPSHOT_COMPONENT_CODECS if codec.required
)


@dataclass(frozen=True)
class SnapshotComponent:
    """Deeply immutable component entry in the session envelope."""

    slot: str
    schema_version: str
    required: bool
    owner: str
    payload: Mapping[str, Any]
    digest: str = ""

    def __post_init__(self) -> None:
        slot = self.slot.value if isinstance(self.slot, ComponentSlot) else self.slot
        if not isinstance(slot, str) or _CAPABILITY_TOKEN.fullmatch(slot) is None:
            raise SessionContractError(
                SessionErrorCode.UNSUPPORTED_COMPONENT_SCHEMA,
                "Snapshot component slot is invalid.",
                recoverable=False,
                remediation="Use a portable semantic component slot.",
            )
        object.__setattr__(self, "slot", slot)
        if (
            not isinstance(self.schema_version, str)
            or _SCHEMA_TOKEN.fullmatch(self.schema_version) is None
        ):
            raise SessionContractError(
                SessionErrorCode.UNSUPPORTED_COMPONENT_SCHEMA,
                "Snapshot component schema identifier is invalid.",
                recoverable=False,
                remediation="Use the schema identifier declared by the owner codec.",
            )
        if not isinstance(self.required, bool):
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Component required flag must be boolean.",
                recoverable=False,
                remediation="Read the component with the current strict codec.",
            )
        if not isinstance(self.owner, str) or _CAPABILITY_TOKEN.fullmatch(self.owner) is None:
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Component owner is invalid.",
                recoverable=False,
                remediation="Use the declared semantic owner identifier.",
            )
        frozen_payload = _freeze_json(self.payload, path="component.payload")
        if not isinstance(frozen_payload, Mapping):
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Component payload must be a JSON object.",
                recoverable=False,
                remediation="Encode component facts as a JSON object.",
            )
        object.__setattr__(self, "payload", frozen_payload)
        expected_digest = _digest_json(_thaw_json(frozen_payload))
        if self.digest and self.digest != expected_digest:
            raise SessionContractError(
                SessionErrorCode.COMPONENT_DIGEST_MISMATCH,
                "Snapshot component digest verification failed.",
                recoverable=False,
                remediation="Restore component bytes written by the owning codec.",
                metadata={"owner": self.owner, "slot": self.slot},
            )
        object.__setattr__(self, "digest", expected_digest)

    @classmethod
    def from_value(
        cls, codec: SnapshotComponentCodec, value: Any
    ) -> "SnapshotComponent":
        return cls(
            slot=codec.slot,
            schema_version=codec.schema_version,
            required=codec.required,
            owner=codec.owner,
            payload=codec.encode(value),
        )

    def decode(self, registry: SnapshotComponentRegistry) -> Any:
        return registry.decode(self)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot": self.slot,
            "schema_version": self.schema_version,
            "required": self.required,
            "owner": self.owner,
            "payload": _thaw_json(self.payload),
            "digest": self.digest,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SnapshotComponent":
        _require_exact_fields(
            payload,
            {"slot", "schema_version", "required", "owner", "payload", "digest"},
            SessionErrorCode.CORRUPT_SNAPSHOT,
            "snapshot component",
        )
        return cls(
            slot=payload["slot"],
            schema_version=payload["schema_version"],
            required=payload["required"],
            owner=payload["owner"],
            payload=payload["payload"],
            digest=payload["digest"],
        )


@dataclass(frozen=True)
class SnapshotTiming:
    """Portable wall-clock facts; monotonic process clocks are not persisted."""

    captured_at: str
    pause_requested_at: str | None = None
    safe_boundary_at: str | None = None

    def __post_init__(self) -> None:
        _validate_timestamp(self.captured_at, "captured_at")
        if self.pause_requested_at is not None:
            _validate_timestamp(self.pause_requested_at, "pause_requested_at")
        if self.safe_boundary_at is not None:
            _validate_timestamp(self.safe_boundary_at, "safe_boundary_at")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "captured_at": self.captured_at,
            "pause_requested_at": self.pause_requested_at,
            "safe_boundary_at": self.safe_boundary_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SnapshotTiming":
        _require_exact_fields(
            payload,
            {"captured_at", "pause_requested_at", "safe_boundary_at"},
            SessionErrorCode.CORRUPT_SNAPSHOT,
            "snapshot timing",
        )
        return cls(
            captured_at=payload["captured_at"],
            pause_requested_at=payload.get("pause_requested_at"),
            safe_boundary_at=payload.get("safe_boundary_at"),
        )


@dataclass(frozen=True)
class SnapshotIntegrity:
    algorithm: str
    digest: str

    def __post_init__(self) -> None:
        if self.algorithm != "sha256" or re.fullmatch(r"[0-9a-f]{64}", self.digest or "") is None:
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Snapshot integrity record is invalid.",
                recoverable=False,
                remediation="Load an intact snapshot from the checkpoint store.",
            )

    def to_dict(self) -> Dict[str, str]:
        return {"algorithm": self.algorithm, "digest": self.digest}


@dataclass(frozen=True)
class SessionSnapshot:
    """Current immutable, deterministic session snapshot envelope."""

    schema_version: int
    snapshot_id: SnapshotIdentity
    session_id: SessionIdentity
    head_generation: HeadGeneration
    lifecycle: SessionLifecycle
    created_at: str
    timing: SnapshotTiming
    components: tuple[SnapshotComponent, ...]
    resolver_references: tuple[ResolverReference, ...]
    artifact_refs: tuple[ArtifactRef, ...]
    integrity: SnapshotIntegrity
    component_registry: InitVar[SnapshotComponentRegistry | None] = None

    def __post_init__(self, component_registry: SnapshotComponentRegistry | None) -> None:
        if self.schema_version != CURRENT_SNAPSHOT_SCHEMA:
            raise SessionContractError(
                SessionErrorCode.UNSUPPORTED_SNAPSHOT_SCHEMA,
                "Snapshot schema is unsupported.",
                recoverable=False,
                remediation="Install a current reader or explicit migration adapter.",
                metadata={"schema_version": self.schema_version},
            )
        _validate_timestamp(self.created_at, "created_at")
        components = tuple(self.components)
        references = tuple(self.resolver_references)
        artifacts = tuple(self.artifact_refs)
        if any(not isinstance(item, SnapshotComponent) for item in components):
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Snapshot components must use the component envelope.",
                recoverable=False,
                remediation="Read components with the current strict codec.",
            )
        if any(not isinstance(item, ResolverReference) for item in references):
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Snapshot resolver references are invalid.",
                recoverable=False,
                remediation="Read resolver references with the current strict codec.",
            )
        if any(not isinstance(item, ArtifactRef) for item in artifacts):
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Snapshot artifact references must use the canonical ArtifactRef.",
                recoverable=False,
                remediation="Read artifact references with the current strict codec.",
            )
        component_keys = [(item.owner, item.slot) for item in components]
        if len(component_keys) != len(set(component_keys)):
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Snapshot contains duplicate owner component slots.",
                recoverable=False,
                remediation="Keep one component per semantic owner and slot.",
            )
        (component_registry or CORE_SNAPSHOT_COMPONENT_REGISTRY).validate(components)
        ref_keys = [(ref.namespace, ref.reference_id) for ref in references]
        if len(ref_keys) != len(set(ref_keys)):
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Snapshot contains duplicate resolver references.",
                recoverable=False,
                remediation="Keep one reference for each namespace and logical alias.",
            )
        artifact_keys = [item.artifact_id for item in artifacts]
        if len(artifact_keys) != len(set(artifact_keys)):
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Snapshot contains duplicate artifact references.",
                recoverable=False,
                remediation="Keep one canonical reference for each artifact identity.",
            )
        object.__setattr__(self, "components", components)
        object.__setattr__(self, "resolver_references", references)
        object.__setattr__(self, "artifact_refs", artifacts)

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: SnapshotIdentity,
        session_id: SessionIdentity,
        head_generation: HeadGeneration,
        lifecycle: SessionLifecycle,
        created_at: str,
        timing: SnapshotTiming,
        components: Iterable[SnapshotComponent],
        resolver_references: Iterable[ResolverReference] = (),
        artifact_refs: Iterable[ArtifactRef] = (),
        component_registry: SnapshotComponentRegistry | None = None,
    ) -> "SessionSnapshot":
        components_tuple = tuple(components)
        refs_tuple = tuple(resolver_references)
        artifacts_tuple = tuple(artifact_refs)
        unsigned = _snapshot_unsigned_dict(
            schema_version=CURRENT_SNAPSHOT_SCHEMA,
            snapshot_id=snapshot_id,
            session_id=session_id,
            head_generation=head_generation,
            lifecycle=lifecycle,
            created_at=created_at,
            timing=timing,
            components=components_tuple,
            resolver_references=refs_tuple,
            artifact_refs=artifacts_tuple,
        )
        integrity = SnapshotIntegrity("sha256", _digest_json(unsigned))
        return cls(
            schema_version=CURRENT_SNAPSHOT_SCHEMA,
            snapshot_id=snapshot_id,
            session_id=session_id,
            head_generation=head_generation,
            lifecycle=lifecycle,
            created_at=created_at,
            timing=timing,
            components=components_tuple,
            resolver_references=refs_tuple,
            artifact_refs=artifacts_tuple,
            integrity=integrity,
            component_registry=component_registry,
        )

    def to_dict(self) -> Dict[str, Any]:
        payload = _snapshot_unsigned_dict(
            schema_version=self.schema_version,
            snapshot_id=self.snapshot_id,
            session_id=self.session_id,
            head_generation=self.head_generation,
            lifecycle=self.lifecycle,
            created_at=self.created_at,
            timing=self.timing,
            components=self.components,
            resolver_references=self.resolver_references,
            artifact_refs=self.artifact_refs,
        )
        payload["integrity"] = self.integrity.to_dict()
        return payload

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        component_registry: SnapshotComponentRegistry | None = None,
    ) -> "SessionSnapshot":
        _require_exact_fields(
            payload,
            {
                "schema_version",
                "snapshot_id",
                "session_id",
                "head_generation",
                "lifecycle",
                "created_at",
                "timing",
                "components",
                "resolver_references",
                "artifact_refs",
                "integrity",
            },
            SessionErrorCode.CORRUPT_SNAPSHOT,
            "session snapshot",
        )
        schema_version = payload.get("schema_version")
        if schema_version != CURRENT_SNAPSHOT_SCHEMA:
            raise SessionContractError(
                SessionErrorCode.UNSUPPORTED_SNAPSHOT_SCHEMA,
                "Snapshot schema is unsupported.",
                recoverable=False,
                remediation="Install a current reader or explicit migration adapter.",
                metadata={"schema_version": schema_version},
            )
        try:
            lifecycle = SessionLifecycle(payload.get("lifecycle"))
        except (TypeError, ValueError) as exc:
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Snapshot lifecycle is invalid.",
                recoverable=False,
                remediation="Use the canonical lifecycle vocabulary.",
            ) from exc
        components_raw = payload.get("components")
        refs_raw = payload.get("resolver_references")
        artifacts_raw = payload.get("artifact_refs")
        if (
            not isinstance(components_raw, list)
            or not isinstance(refs_raw, list)
            or not isinstance(artifacts_raw, list)
        ):
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Snapshot components and resolver references must be arrays.",
                recoverable=False,
                remediation="Read the snapshot with the current strict codec.",
            )
        integrity_raw = payload["integrity"]
        timing_raw = payload["timing"]
        snapshot_raw = payload["snapshot_id"]
        session_raw = payload["session_id"]
        if (
            not isinstance(integrity_raw, Mapping)
            or not isinstance(timing_raw, Mapping)
            or not isinstance(snapshot_raw, Mapping)
            or not isinstance(session_raw, Mapping)
        ):
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Snapshot typed fields must be JSON objects.",
                recoverable=False,
                remediation="Read the snapshot with the current strict codec.",
            )
        _require_exact_fields(
            integrity_raw,
            {"algorithm", "digest"},
            SessionErrorCode.CORRUPT_SNAPSHOT,
            "snapshot integrity",
        )
        snapshot = cls(
            schema_version=schema_version,
            snapshot_id=SnapshotIdentity.from_dict(snapshot_raw),
            session_id=SessionIdentity.from_dict(session_raw),
            head_generation=HeadGeneration(payload["head_generation"]),
            lifecycle=lifecycle,
            created_at=payload["created_at"],
            timing=SnapshotTiming.from_dict(timing_raw),
            components=tuple(SnapshotComponent.from_dict(item) for item in components_raw),
            resolver_references=tuple(
                ResolverReference.from_dict(item) for item in refs_raw
            ),
            artifact_refs=tuple(ArtifactRef.from_dict(item) for item in artifacts_raw),
            integrity=SnapshotIntegrity(
                algorithm=integrity_raw["algorithm"],
                digest=integrity_raw["digest"],
            ),
            component_registry=component_registry,
        )
        unsigned = dict(snapshot.to_dict())
        unsigned.pop("integrity")
        if _digest_json(unsigned) != snapshot.integrity.digest:
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Snapshot integrity verification failed.",
                recoverable=False,
                remediation="Restore a verified snapshot from the checkpoint store.",
            )
        return snapshot

    @classmethod
    def from_json(
        cls,
        raw: str,
        *,
        component_registry: SnapshotComponentRegistry | None = None,
    ) -> "SessionSnapshot":
        try:
            payload = json.loads(raw, parse_constant=_reject_json_constant)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Snapshot is not strict JSON.",
                recoverable=False,
                remediation="Restore an intact snapshot written by the current codec.",
            ) from exc
        if not isinstance(payload, Mapping):
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Snapshot root must be a JSON object.",
                recoverable=False,
                remediation="Restore an intact snapshot written by the current codec.",
            )
        return cls.from_dict(payload, component_registry=component_registry)


class PersistenceReceiptStatus(str, Enum):
    """Observable outcomes of one head persistence request."""

    ACCEPTED = "accepted"
    PERSISTED = "persisted"
    REJECTED = "rejected"
    FAILED = "failed"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class PauseReceipt:
    """Pause request/persistence receipt; accepted never means persisted."""

    session_id: SessionIdentity
    run_id: RunIdentity
    status: PersistenceReceiptStatus
    lifecycle: SessionLifecycle
    expected_generation: HeadGeneration
    actual_generation: HeadGeneration
    snapshot_id: SnapshotIdentity | None = None
    checkpoint_id: CheckpointIdentity | None = None
    error_code: SessionErrorCode | None = None

    def __post_init__(self) -> None:
        if self.status is PersistenceReceiptStatus.PERSISTED:
            valid = (
                self.lifecycle in {SessionLifecycle.PAUSED, SessionLifecycle.WAITING_INPUT}
                and self.snapshot_id is not None
                and self.checkpoint_id is not None
                and self.actual_generation == self.expected_generation.next()
                and self.error_code is None
            )
        else:
            valid = self.lifecycle not in {
                SessionLifecycle.PAUSED,
                SessionLifecycle.WAITING_INPUT,
            }
        if not valid:
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Pause receipt contradicts persistence or lifecycle facts.",
                recoverable=False,
                remediation="Build the receipt from the authoritative head commit outcome.",
            )

    def require_persisted(self) -> None:
        if self.status is PersistenceReceiptStatus.PERSISTED:
            return
        code = {
            PersistenceReceiptStatus.REJECTED: SessionErrorCode.PERSISTENCE_REJECTED,
            PersistenceReceiptStatus.FAILED: SessionErrorCode.PERSISTENCE_FAILED,
            PersistenceReceiptStatus.CONFLICT: SessionErrorCode.GENERATION_CONFLICT,
            PersistenceReceiptStatus.ACCEPTED: SessionErrorCode.PERSISTENCE_REJECTED,
        }[self.status]
        raise SessionContractError(
            code,
            "Pause has not produced a durable session head.",
            recoverable=self.status is not PersistenceReceiptStatus.FAILED,
            remediation="Inspect the receipt and retry only after reloading the authoritative head.",
            metadata={"status": self.status.value},
        )


def _snapshot_unsigned_dict(
    *,
    schema_version: int,
    snapshot_id: SnapshotIdentity,
    session_id: SessionIdentity,
    head_generation: HeadGeneration,
    lifecycle: SessionLifecycle,
    created_at: str,
    timing: SnapshotTiming,
    components: Iterable[SnapshotComponent],
    resolver_references: Iterable[ResolverReference],
    artifact_refs: Iterable[ArtifactRef],
) -> Dict[str, Any]:
    return {
        "schema_version": schema_version,
        "snapshot_id": snapshot_id.to_dict(),
        "session_id": session_id.to_dict(),
        "head_generation": head_generation.value,
        "lifecycle": lifecycle.value,
        "created_at": created_at,
        "timing": timing.to_dict(),
        "components": [component.to_dict() for component in components],
        "resolver_references": [reference.to_dict() for reference in resolver_references],
        "artifact_refs": [reference.to_dict() for reference in artifact_refs],
    }


def _digest_json(payload: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SessionContractError(
            SessionErrorCode.CORRUPT_SNAPSHOT,
            "Snapshot contains a non-JSON value.",
            recoverable=False,
            remediation="Persist only strict JSON facts and resolver references.",
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _unsafe_snapshot_text(value: str) -> bool:
    """Inspect encoded JSON values, not escapes such as Python ``f:\\n``.

    Preserve the original bytes; decoding is only a bounded inspection view.
    Real paths/credentials remain rejected, including multiply encoded values.
    """
    pending: list[tuple[Any, int]] = [(value, 0)]
    inspected = 0
    while pending:
        current, depth = pending.pop()
        inspected += 1
        if inspected > 10_000 or depth > 32:
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Encoded snapshot text exceeds safe inspection bounds.",
                recoverable=False,
                remediation="Retain oversized material through an artifact reference.",
            )
        if isinstance(current, str):
            if current.lstrip().startswith(("{", "[", '"')):
                try:
                    decoded = json.loads(current)
                except RecursionError:
                    raise SessionContractError(
                        SessionErrorCode.CORRUPT_SNAPSHOT,
                        "Encoded snapshot text exceeds safe inspection bounds.",
                        recoverable=False,
                        remediation="Retain oversized material through an artifact reference.",
                    ) from None
                except ValueError:
                    pass  # Ordinary prose/source, not a complete JSON value.
                else:
                    pending.append((decoded, depth + 1))
                    continue
            if _HOST_LOCAL_OR_CREDENTIAL_VALUE.search(current):
                return True
        elif isinstance(current, dict):
            pending.extend((item, depth + 1) for pair in current.items() for item in pair)
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)
    return False


def _freeze_json(value: Any, *, path: str) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        if _unsafe_snapshot_text(value):
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Snapshot contains a host-local path or credential value.",
                recoverable=False,
                remediation="Persist a resolver or artifact reference instead of raw material.",
            )
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SessionContractError(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Snapshot contains a non-finite number.",
                recoverable=False,
                remediation="Encode only finite JSON numbers.",
            )
        return value
    if isinstance(value, Mapping):
        frozen: Dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise SessionContractError(
                    SessionErrorCode.CORRUPT_SNAPSHOT,
                    "Snapshot object keys must be strings.",
                    recoverable=False,
                    remediation="Encode component facts as strict JSON objects.",
                )
            frozen[key] = _freeze_json(item, path=f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, list):
        return tuple(
            _freeze_json(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    raise SessionContractError(
        SessionErrorCode.CORRUPT_SNAPSHOT,
        "Snapshot contains a non-JSON value.",
        recoverable=False,
        remediation="Persist only strict JSON facts and resolver references.",
    )


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _validate_timestamp(value: Any, field_name: str) -> None:
    if not isinstance(value, str):
        raise SessionContractError(
            SessionErrorCode.CORRUPT_SNAPSHOT,
            "Snapshot timestamp must be a string.",
            recoverable=False,
            remediation="Use a timezone-aware RFC 3339 timestamp.",
            metadata={"field": field_name},
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SessionContractError(
            SessionErrorCode.CORRUPT_SNAPSHOT,
            "Snapshot timestamp is invalid.",
            recoverable=False,
            remediation="Use a timezone-aware RFC 3339 timestamp.",
            metadata={"field": field_name},
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SessionContractError(
            SessionErrorCode.CORRUPT_SNAPSHOT,
            "Snapshot timestamp must include a timezone.",
            recoverable=False,
            remediation="Use a timezone-aware RFC 3339 timestamp.",
            metadata={"field": field_name},
        )


def _require_exact_fields(
    payload: Any,
    expected: set[str],
    error_code: SessionErrorCode,
    object_name: str,
) -> None:
    if not isinstance(payload, Mapping) or set(payload) != expected:
        raise SessionContractError(
            error_code,
            f"{object_name.capitalize()} has unknown or missing fields.",
            recoverable=False,
            remediation="Use the current strict codec or an explicit migration adapter.",
        )


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant: {value}")


def _safe_failure_metadata(metadata: Mapping[str, Any]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    secret_key = re.compile(r"(?i)(secret|credential|password|token|authorization)")
    unsafe_value = re.compile(r"(?i)(/users/|/home/|\\\\|bearer\s|api[_-]?key|password=)")
    for key, value in metadata.items():
        if not isinstance(key, str) or _CAPABILITY_TOKEN.fullmatch(key) is None:
            continue
        if secret_key.search(key):
            safe[key] = "[redacted]"
            continue
        if value is None or isinstance(value, (bool, int)):
            safe[key] = value
        elif isinstance(value, float) and math.isfinite(value):
            safe[key] = value
        elif isinstance(value, str):
            safe[key] = "[redacted]" if unsafe_value.search(value) else value[:128]
    return safe


__all__ = [
    "AgentIdentity",
    "AgentStateSnapshotComponent",
    "AttemptIdentity",
    "CheckpointIdentity",
    "ComponentSlot",
    "ContinuationIdentity",
    "CORE_SNAPSHOT_COMPONENT_CODECS",
    "CORE_SNAPSHOT_COMPONENT_REGISTRY",
    "CURRENT_SNAPSHOT_SCHEMA",
    "HeadGeneration",
    "IdentityKind",
    "IdentityRelation",
    "IdentityRelationship",
    "PauseReceipt",
    "PauseSafety",
    "PersistenceReceiptStatus",
    "REQUIRED_COMPONENT_SLOTS",
    "ResolvedResource",
    "ResolverNamespace",
    "ResolverReference",
    "ResolverRegistry",
    "RunIdentity",
    "RuntimeIdentity",
    "SafeBoundaryKind",
    "SessionContractError",
    "SessionErrorCode",
    "SessionHead",
    "SessionIdentity",
    "SessionLifecycle",
    "SessionOperation",
    "SessionSnapshot",
    "SnapshotComponent",
    "SnapshotComponentCodec",
    "SnapshotComponentRegistry",
    "SnapshotIdentity",
    "SnapshotIntegrity",
    "SnapshotTiming",
    "SUPPORTED_COMPONENT_SCHEMAS",
    "ToolCallIdentity",
    "TraceLineageSnapshotComponent",
    "WorkItemIdentity",
    "identity_from_dict",
    "lifecycle_allows",
    "lifecycle_can_transition",
]
