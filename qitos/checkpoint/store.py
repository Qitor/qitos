"""Checkpoint store abstraction and core data types.

Borrowed from LangGraph's BaseCheckpointSaver design:
- references/langgraph/libs/checkpoint/langgraph/checkpoint/base/__init__.py
- Config-based addressing (thread_id + checkpoint_id)
- Per-field state versioning (channel_versions)
- Pending writes for crash recovery
- Parent chain for fork / time-travel
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, NamedTuple, NewType, Optional, Sequence, TypedDict

from .session import (
    ATOMIC_SESSION_FORK,
    ATOMIC_SESSION_COMMIT,
    LIST_SESSION_LINEAGE,
    READ_SESSION_HEAD,
    READ_SESSION_SNAPSHOT,
    CheckpointCapabilityError,
    SessionCommitReceipt,
    SessionHeadRecord,
    SessionForkReceipt,
    SessionForkRequest,
    SessionSnapshotCommit,
    SessionSnapshotRecord,
)

# ---------------------------------------------------------------------------
# Core type aliases
# ---------------------------------------------------------------------------

CheckpointId = NewType("CheckpointId", str)
"""Unique identifier for a checkpoint (UUID-based)."""

StateVersions = Dict[str, int]
"""Mapping of state field name → monotonic version number."""


# ---------------------------------------------------------------------------
# CheckpointConfig — addresses a checkpoint within a store
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CheckpointConfig:
    """Address a specific checkpoint within a store.

    If ``checkpoint_id`` is ``None``, operations target the *latest*
    checkpoint for the given ``thread_id``.
    """

    thread_id: str
    checkpoint_id: Optional[CheckpointId] = None


# ---------------------------------------------------------------------------
# PendingWrite — partial tool results awaiting commit
# ---------------------------------------------------------------------------

class PendingWrite(NamedTuple):
    """A partial tool-execution result linked to a checkpoint.

    Borrowed from LangGraph's PendingWrite tuple (task_id, channel, value).
    """

    task_id: str
    channel: str
    value: Any


# ---------------------------------------------------------------------------
# CheckpointMetadata
# ---------------------------------------------------------------------------

class CheckpointMetadata(TypedDict, total=False):
    """Metadata associated with a checkpoint."""

    source: str  # "input" | "loop" | "update" | "fork"
    step: int
    parents: Dict[str, str]
    run_id: str


# ---------------------------------------------------------------------------
# Checkpoint — the core snapshot data model
# ---------------------------------------------------------------------------

@dataclass
class Checkpoint:
    """State snapshot at a given point in time.

    Replaces the legacy ``CheckpointData`` with richer versioning and
    parent-chain support for fork / time-travel.
    """

    id: CheckpointId
    thread_id: str
    step: int
    state_data: Dict[str, Any]
    state_versions: StateVersions = field(default_factory=dict)
    versions_seen: Dict[str, StateVersions] = field(default_factory=dict)
    pending_writes: List[PendingWrite] = field(default_factory=list)
    parent_id: Optional[CheckpointId] = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    schema_version: str = "v2"

    # ---- serialization helpers ----

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "step": self.step,
            "state_data": self.state_data,
            "state_versions": self.state_versions,
            "versions_seen": self.versions_seen,
            "pending_writes": [
                {"task_id": w.task_id, "channel": w.channel, "value": w.value}
                for w in self.pending_writes
            ],
            "parent_id": self.parent_id,
            "created_at": self.created_at,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> Checkpoint:
        writes = [
            PendingWrite(
                task_id=w["task_id"],
                channel=w["channel"],
                value=w["value"],
            )
            for w in payload.get("pending_writes", [])
        ]
        return cls(
            id=CheckpointId(payload["id"]),
            thread_id=payload["thread_id"],
            step=payload["step"],
            state_data=payload["state_data"],
            state_versions=payload.get("state_versions", {}),
            versions_seen=payload.get("versions_seen", {}),
            pending_writes=writes,
            parent_id=payload.get("parent_id"),
            created_at=payload.get("created_at", ""),
            schema_version=payload.get("schema_version", "v2"),
        )


# ---------------------------------------------------------------------------
# CheckpointTuple — bundles checkpoint + metadata + parent for retrieval
# ---------------------------------------------------------------------------

class CheckpointTuple(NamedTuple):
    """A checkpoint together with its metadata and parent reference."""

    config: CheckpointConfig
    checkpoint: Checkpoint
    metadata: CheckpointMetadata
    parent_config: Optional[CheckpointConfig] = None
    pending_writes: Optional[List[PendingWrite]] = None


# ---------------------------------------------------------------------------
# CheckpointStore ABC
# ---------------------------------------------------------------------------

class CheckpointStore(ABC):
    """Abstract base class for checkpoint persistence.

    Borrowed from LangGraph's ``BaseCheckpointSaver`` interface
    (``references/langgraph/libs/checkpoint/langgraph/checkpoint/base/__init__.py``).

    Every method has both sync and async variants.  Subclasses should
    override the async variants; the sync ones delegate via ``asyncio.run``
    by default.
    """

    # ---- sync interface ----

    @abstractmethod
    def put(
        self,
        config: CheckpointConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: StateVersions,
    ) -> CheckpointConfig:
        """Store a checkpoint.  Returns the updated config."""

    @abstractmethod
    def get_tuple(self, config: CheckpointConfig) -> Optional[CheckpointTuple]:
        """Fetch a checkpoint tuple.  Returns ``None`` if not found."""

    def get(self, config: CheckpointConfig) -> Optional[Checkpoint]:
        """Fetch just the checkpoint (convenience wrapper)."""
        result = self.get_tuple(config)
        return result.checkpoint if result else None

    @abstractmethod
    def list(
        self,
        config: CheckpointConfig,
        *,
        limit: Optional[int] = None,
        before: Optional[CheckpointConfig] = None,
    ) -> Iterator[CheckpointTuple]:
        """List checkpoints for a thread, newest first."""

    @abstractmethod
    def put_writes(
        self,
        config: CheckpointConfig,
        writes: Sequence[PendingWrite],
        task_id: str,
    ) -> None:
        """Store intermediate writes linked to a checkpoint."""

    @abstractmethod
    def delete(self, config: CheckpointConfig) -> None:
        """Delete a single checkpoint."""

    # ---- durable Session protocol (optional for compatibility stores) ----

    def session_capabilities(self) -> frozenset[str]:
        """Return stable Session capabilities implemented by this store."""
        return frozenset()

    def commit_session_snapshot(
        self, request: SessionSnapshotCommit
    ) -> SessionCommitReceipt:
        """Atomically persist an immutable snapshot and advance its head."""
        raise CheckpointCapabilityError(ATOMIC_SESSION_COMMIT)

    def get_session_head(self, session_id: str) -> Optional[SessionHeadRecord]:
        """Read the current mutable head for one session."""
        raise CheckpointCapabilityError(READ_SESSION_HEAD)

    def get_session_snapshot(
        self, snapshot_id: str
    ) -> Optional[SessionSnapshotRecord]:
        """Read one immutable Session snapshot by its distinct identity."""
        raise CheckpointCapabilityError(READ_SESSION_SNAPSHOT)

    def list_session_lineage(
        self, session_id: str, *, limit: Optional[int] = None
    ) -> Iterator[SessionSnapshotRecord]:
        """List immutable snapshots for a session, newest first."""
        raise CheckpointCapabilityError(LIST_SESSION_LINEAGE)

    def fork_session_snapshot(self, request: SessionForkRequest) -> SessionForkReceipt:
        """Atomically declare a fork and create its independent child head."""
        raise CheckpointCapabilityError(ATOMIC_SESSION_FORK)

    def get_session_fork(self, operation_id: str) -> Optional[SessionForkReceipt]:
        """Read a previously committed fork declaration by idempotency key."""
        raise CheckpointCapabilityError(ATOMIC_SESSION_FORK)

    # ---- async interface (default: delegate to sync) ----

    async def aput(
        self,
        config: CheckpointConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: StateVersions,
    ) -> CheckpointConfig:
        return self.put(config, checkpoint, metadata, new_versions)

    async def aget_tuple(self, config: CheckpointConfig) -> Optional[CheckpointTuple]:
        return self.get_tuple(config)

    async def aget(self, config: CheckpointConfig) -> Optional[Checkpoint]:
        result = await self.aget_tuple(config)
        return result.checkpoint if result else None

    async def alist(
        self,
        config: CheckpointConfig,
        *,
        limit: Optional[int] = None,
        before: Optional[CheckpointConfig] = None,
    ) -> List[CheckpointTuple]:
        return list(self.list(config, limit=limit, before=before))

    async def aput_writes(
        self,
        config: CheckpointConfig,
        writes: Sequence[PendingWrite],
        task_id: str,
    ) -> None:
        self.put_writes(config, writes, task_id)

    async def adelete(self, config: CheckpointConfig) -> None:
        self.delete(config)


__all__ = [
    "CheckpointId",
    "CheckpointConfig",
    "Checkpoint",
    "CheckpointMetadata",
    "CheckpointTuple",
    "CheckpointStore",
    "PendingWrite",
    "StateVersions",
]
