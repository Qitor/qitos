"""Bounded adapters between legacy checkpoint addressing and Session snapshots."""

from __future__ import annotations

from typing import Mapping

from .session import (
    CheckpointSessionError,
    CheckpointSessionErrorCode,
    SessionSnapshotRecord,
)
from .store import CheckpointConfig, CheckpointStore


def session_snapshot_from_checkpoint(
    store: CheckpointStore, config: CheckpointConfig
) -> SessionSnapshotRecord:
    """Read a canonical Session snapshot through an old checkpoint address.

    State-only v2 checkpoints and v1 manager files are intentionally not
    promoted into incomplete Session snapshots.
    """
    checkpoint_tuple = store.get_tuple(config)
    if checkpoint_tuple is None:
        raise CheckpointSessionError(
            CheckpointSessionErrorCode.SNAPSHOT_NOT_FOUND,
            "Checkpoint was not found.",
            recoverable=True,
        )
    payload = checkpoint_tuple.checkpoint.state_data.get("session_snapshot")
    if not isinstance(payload, Mapping):
        raise CheckpointSessionError(
            CheckpointSessionErrorCode.INCOMPATIBLE_CHECKPOINT,
            "Checkpoint predates the canonical Session snapshot envelope.",
            recoverable=False,
        )
    snapshot_id = payload.get("snapshot_id")
    session_id = payload.get("session_id")
    if not isinstance(snapshot_id, Mapping) or not isinstance(session_id, Mapping):
        raise CheckpointSessionError(
            CheckpointSessionErrorCode.CORRUPT_SNAPSHOT,
            "Checkpoint Session identity fields are invalid.",
            recoverable=False,
        )
    generation = payload.get("head_generation")
    if not isinstance(generation, int) or isinstance(generation, bool):
        raise CheckpointSessionError(
            CheckpointSessionErrorCode.CORRUPT_SNAPSHOT,
            "Checkpoint Session generation is invalid.",
            recoverable=False,
        )
    return SessionSnapshotRecord(
        session_id=str(session_id.get("value", "")),
        snapshot_id=str(snapshot_id.get("value", "")),
        checkpoint_id=str(checkpoint_tuple.checkpoint.id),
        generation=generation,
        owner_run_id=str(checkpoint_tuple.metadata.get("run_id", "")),
        lifecycle=str(payload.get("lifecycle", "")),
        payload=dict(payload),
        parent_checkpoint_id=(
            str(checkpoint_tuple.checkpoint.parent_id)
            if checkpoint_tuple.checkpoint.parent_id is not None
            else None
        ),
    )


__all__ = ["session_snapshot_from_checkpoint"]
