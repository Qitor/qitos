"""Canonical contracts for durable QitOS sessions.

This module owns the shared identity vocabulary used by session, checkpoint,
conversation, tool, work-graph, and trace consumers.  It deliberately contains
data contracts only: Engine behavior and checkpoint persistence remain in their
existing owning packages.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from types import MappingProxyType
from typing import Any, ClassVar, Dict, Mapping, Type, TypeVar
from uuid import uuid4


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
        self.metadata = MappingProxyType(dict(metadata or {}))

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


__all__ = [
    "AgentIdentity",
    "AttemptIdentity",
    "CheckpointIdentity",
    "IdentityKind",
    "IdentityRelation",
    "IdentityRelationship",
    "RunIdentity",
    "RuntimeIdentity",
    "SessionContractError",
    "SessionErrorCode",
    "SessionIdentity",
    "SnapshotIdentity",
    "ToolCallIdentity",
    "WorkItemIdentity",
    "identity_from_dict",
]
