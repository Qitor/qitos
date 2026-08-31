"""Session-head persistence protocol for canonical checkpoints.

This module is intentionally self-contained.  It stores strict JSON snapshot
bytes produced by the session contract without importing or interpreting any
Engine or core runtime type.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional


ATOMIC_SESSION_COMMIT = "checkpoint.session.atomic_commit/v1"
READ_SESSION_HEAD = "checkpoint.session.read_head/v1"
READ_SESSION_SNAPSHOT = "checkpoint.session.read_snapshot/v1"
LIST_SESSION_LINEAGE = "checkpoint.session.list_lineage/v1"
SESSION_PERSISTENCE_CAPABILITIES = frozenset(
    {
        ATOMIC_SESSION_COMMIT,
        READ_SESSION_HEAD,
        READ_SESSION_SNAPSHOT,
        LIST_SESSION_LINEAGE,
    }
)


class CheckpointSessionErrorCode(str, Enum):
    """Stable persistence failures independent of an Engine implementation."""

    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    GENERATION_CONFLICT = "generation_conflict"
    OWNER_CONFLICT = "owner_conflict"
    CHECKPOINT_CONFLICT = "checkpoint_conflict"
    SNAPSHOT_NOT_FOUND = "snapshot_not_found"
    SESSION_NOT_FOUND = "session_not_found"
    CORRUPT_SNAPSHOT = "corrupt_snapshot"
    INCOMPATIBLE_CHECKPOINT = "incompatible_checkpoint"
    PERSISTENCE_FAILED = "persistence_failed"


class CheckpointSessionError(RuntimeError):
    """Typed, machine-readable checkpoint session failure."""

    def __init__(
        self,
        error_code: CheckpointSessionErrorCode,
        message: str,
        *,
        recoverable: bool,
        capability: str = "",
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.recoverable = bool(recoverable)
        self.capability = str(capability or "")
        self.metadata = MappingProxyType(_safe_metadata(metadata or {}))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_code": self.error_code.value,
            "message": str(self),
            "recoverable": self.recoverable,
            "capability": self.capability,
            "metadata": dict(self.metadata),
        }


class CheckpointCapabilityError(CheckpointSessionError):
    """The store does not implement one required session capability."""

    def __init__(self, capability: str) -> None:
        super().__init__(
            CheckpointSessionErrorCode.UNSUPPORTED_CAPABILITY,
            f"Checkpoint store does not provide capability: {capability}",
            recoverable=True,
            capability=capability,
        )


class CheckpointConflictError(CheckpointSessionError):
    """A compare-and-swap precondition no longer matches the current head."""


class CheckpointPersistenceError(CheckpointSessionError):
    """The store could not atomically persist a snapshot and its head."""

    def __init__(self, message: str = "Atomic session persistence failed.") -> None:
        super().__init__(
            CheckpointSessionErrorCode.PERSISTENCE_FAILED,
            message,
            recoverable=True,
            capability=ATOMIC_SESSION_COMMIT,
        )


@dataclass(frozen=True)
class SessionHeadRecord:
    """Small mutable-index value pointing at one immutable snapshot."""

    session_id: str
    snapshot_id: str
    checkpoint_id: str
    generation: int
    owner_run_id: str
    lifecycle: str

    def __post_init__(self) -> None:
        _require_token(self.session_id, "session_id")
        _require_token(self.snapshot_id, "snapshot_id")
        _require_token(self.checkpoint_id, "checkpoint_id")
        _require_token(self.owner_run_id, "owner_run_id")
        _require_token(self.lifecycle, "lifecycle")
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation < 0
        ):
            raise _corrupt("Session head generation must be a non-negative integer.")


@dataclass(frozen=True)
class SessionSnapshotRecord:
    """Immutable checkpoint-backed snapshot record returned by a store."""

    session_id: str
    snapshot_id: str
    checkpoint_id: str
    generation: int
    owner_run_id: str
    lifecycle: str
    payload: Dict[str, Any]
    parent_checkpoint_id: Optional[str] = None

    def __post_init__(self) -> None:
        SessionHeadRecord(
            session_id=self.session_id,
            snapshot_id=self.snapshot_id,
            checkpoint_id=self.checkpoint_id,
            generation=self.generation,
            owner_run_id=self.owner_run_id,
            lifecycle=self.lifecycle,
        )
        if self.parent_checkpoint_id is not None:
            _require_token(self.parent_checkpoint_id, "parent_checkpoint_id")
        object.__setattr__(self, "payload", _strict_json_copy(self.payload))

    def isolated_copy(self) -> "SessionSnapshotRecord":
        return SessionSnapshotRecord(
            session_id=self.session_id,
            snapshot_id=self.snapshot_id,
            checkpoint_id=self.checkpoint_id,
            generation=self.generation,
            owner_run_id=self.owner_run_id,
            lifecycle=self.lifecycle,
            payload=copy.deepcopy(self.payload),
            parent_checkpoint_id=self.parent_checkpoint_id,
        )


@dataclass(frozen=True)
class SessionSnapshotCommit:
    """One atomic immutable-snapshot plus mutable-head CAS request."""

    session_id: str
    snapshot_id: str
    checkpoint_id: str
    owner_run_id: str
    lifecycle: str
    payload: Dict[str, Any]
    expected_generation: Optional[int] = None
    expected_checkpoint_id: Optional[str] = None
    expected_owner_run_id: Optional[str] = None

    def __post_init__(self) -> None:
        _require_token(self.session_id, "session_id")
        _require_token(self.snapshot_id, "snapshot_id")
        _require_token(self.checkpoint_id, "checkpoint_id")
        _require_token(self.owner_run_id, "owner_run_id")
        _require_token(self.lifecycle, "lifecycle")
        create = self.expected_generation is None
        if create:
            if (
                self.expected_checkpoint_id is not None
                or self.expected_owner_run_id is not None
            ):
                raise _corrupt("Session creation cannot declare an existing head.")
        else:
            if (
                isinstance(self.expected_generation, bool)
                or not isinstance(self.expected_generation, int)
                or self.expected_generation < 0
            ):
                raise _corrupt("Expected generation must be a non-negative integer.")
            if self.expected_checkpoint_id is None or self.expected_owner_run_id is None:
                raise _corrupt("Session head advancement requires checkpoint and owner CAS.")
            _require_token(self.expected_checkpoint_id, "expected_checkpoint_id")
            _require_token(self.expected_owner_run_id, "expected_owner_run_id")
        payload = _strict_json_copy(self.payload)
        payload_generation = payload.get("head_generation")
        if payload_generation != self.target_generation:
            raise _corrupt("Snapshot generation does not match its head commit.")
        object.__setattr__(self, "payload", payload)

    @property
    def target_generation(self) -> int:
        return 0 if self.expected_generation is None else self.expected_generation + 1


@dataclass(frozen=True)
class SessionCommitReceipt:
    """Proof that one atomic head commit is durably visible."""

    session_id: str
    snapshot_id: str
    checkpoint_id: str
    generation: int
    owner_run_id: str
    lifecycle: str
    durable: bool
    store_kind: str

    def __post_init__(self) -> None:
        SessionHeadRecord(
            session_id=self.session_id,
            snapshot_id=self.snapshot_id,
            checkpoint_id=self.checkpoint_id,
            generation=self.generation,
            owner_run_id=self.owner_run_id,
            lifecycle=self.lifecycle,
        )
        if self.durable is not True:
            raise _corrupt("A successful session commit receipt must be durable.")
        _require_token(self.store_kind, "store_kind")


def generation_conflict(expected: Optional[int], actual: Optional[int]) -> CheckpointConflictError:
    return CheckpointConflictError(
        CheckpointSessionErrorCode.GENERATION_CONFLICT,
        "Session head generation changed before commit.",
        recoverable=True,
        capability=ATOMIC_SESSION_COMMIT,
        metadata={"expected_generation": expected, "actual_generation": actual},
    )


def checkpoint_conflict() -> CheckpointConflictError:
    return CheckpointConflictError(
        CheckpointSessionErrorCode.CHECKPOINT_CONFLICT,
        "Session head checkpoint changed before commit.",
        recoverable=True,
        capability=ATOMIC_SESSION_COMMIT,
    )


def owner_conflict() -> CheckpointConflictError:
    return CheckpointConflictError(
        CheckpointSessionErrorCode.OWNER_CONFLICT,
        "This run no longer owns the session head.",
        recoverable=False,
        capability=ATOMIC_SESSION_COMMIT,
    )


def _strict_json_copy(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise _corrupt("Session snapshot payload must be a JSON object.")
    try:
        raw = json.dumps(
            dict(payload),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        decoded = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise _corrupt("Session snapshot payload is not strict JSON.") from exc
    if not isinstance(decoded, dict):
        raise _corrupt("Session snapshot payload must be a JSON object.")
    return decoded


def _require_token(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise _corrupt(f"{field_name} must be a bounded non-empty string.")


def _corrupt(message: str) -> CheckpointSessionError:
    return CheckpointSessionError(
        CheckpointSessionErrorCode.CORRUPT_SNAPSHOT,
        message,
        recoverable=False,
    )


def _safe_metadata(metadata: Mapping[str, Any]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or len(key) > 64:
            continue
        if value is None or isinstance(value, (bool, int)):
            safe[key] = value
        elif isinstance(value, str) and len(value) <= 128:
            safe[key] = value
    return safe


__all__ = [
    "ATOMIC_SESSION_COMMIT",
    "CheckpointCapabilityError",
    "CheckpointConflictError",
    "CheckpointPersistenceError",
    "CheckpointSessionError",
    "CheckpointSessionErrorCode",
    "LIST_SESSION_LINEAGE",
    "READ_SESSION_HEAD",
    "READ_SESSION_SNAPSHOT",
    "SESSION_PERSISTENCE_CAPABILITIES",
    "SessionCommitReceipt",
    "SessionHeadRecord",
    "SessionSnapshotCommit",
    "SessionSnapshotRecord",
    "checkpoint_conflict",
    "generation_conflict",
    "owner_conflict",
]
