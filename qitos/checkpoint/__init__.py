"""QitOS Checkpoint — run persistence and resume support.

Exports both the new v2 API (CheckpointStore, Checkpoint, etc.) and the
legacy v1 API (CheckpointData, CheckpointManager) for backward compatibility.
"""

from .checkpoint import CheckpointData, CheckpointManager
from .durability import DurabilityManager, DurabilityMode
from .fork import fork_checkpoint, list_fork_history
from .memory_store import InMemoryCheckpointStore
from .pending_writes import PendingWriteManager
from .sqlite_store import SqliteCheckpointStore
from .session import (
    CheckpointCapabilityError,
    CheckpointConflictError,
    CheckpointPersistenceError,
    CheckpointSessionError,
    CheckpointSessionErrorCode,
)
from .session_compat import session_snapshot_from_checkpoint
from .store import (
    Checkpoint,
    CheckpointConfig,
    CheckpointId,
    CheckpointMetadata,
    CheckpointStore,
    CheckpointTuple,
    PendingWrite,
    StateVersions,
)
from .versioning import StateVersionTracker

__all__ = [
    # v2 API
    "CheckpointStore",
    "Checkpoint",
    "CheckpointConfig",
    "CheckpointId",
    "CheckpointMetadata",
    "CheckpointTuple",
    "PendingWrite",
    "StateVersions",
    "InMemoryCheckpointStore",
    "SqliteCheckpointStore",
    "StateVersionTracker",
    "PendingWriteManager",
    "DurabilityManager",
    "DurabilityMode",
    "fork_checkpoint",
    "list_fork_history",
    "CheckpointCapabilityError",
    "CheckpointConflictError",
    "CheckpointPersistenceError",
    "CheckpointSessionError",
    "CheckpointSessionErrorCode",
    "session_snapshot_from_checkpoint",
    # v1 legacy (deprecated)
    "CheckpointData",
    "CheckpointManager",
]
