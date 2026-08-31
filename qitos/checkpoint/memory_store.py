"""In-memory checkpoint store for development and testing.

Dict-backed implementation of :class:`CheckpointStore`.
"""

from __future__ import annotations

import copy
import threading
from typing import Dict, Iterator, List, Optional, Sequence

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
from .session import (
    SESSION_PERSISTENCE_CAPABILITIES,
    CheckpointSessionError,
    CheckpointSessionErrorCode,
    SessionCommitReceipt,
    SessionHeadRecord,
    SessionSnapshotCommit,
    SessionSnapshotRecord,
    checkpoint_conflict,
    generation_conflict,
    owner_conflict,
)


class InMemoryCheckpointStore(CheckpointStore):
    """Thread-safe, dict-backed checkpoint store.

    Suitable for development, testing, and single-process scenarios.
    All data is lost when the process exits.
    """

    def __init__(self) -> None:
        self._store: Dict[CheckpointId, CheckpointTuple] = {}
        self._thread_index: Dict[str, List[CheckpointId]] = {}
        self._session_heads: Dict[str, SessionHeadRecord] = {}
        self._session_snapshot_index: Dict[str, CheckpointId] = {}
        self._lock = threading.Lock()

    # ---- helpers ----

    def _latest_id(self, thread_id: str) -> Optional[CheckpointId]:
        ids = self._thread_index.get(thread_id)
        if not ids:
            return None
        return ids[-1]

    def _resolve_id(self, config: CheckpointConfig) -> Optional[CheckpointId]:
        if config.checkpoint_id is not None:
            return config.checkpoint_id
        return self._latest_id(config.thread_id)

    # ---- sync interface ----

    def put(
        self,
        config: CheckpointConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: StateVersions,
    ) -> CheckpointConfig:
        with self._lock:
            parent_id = self._latest_id(config.thread_id)
            # determine parent_config
            parent_config: Optional[CheckpointConfig] = None
            if parent_id is not None:
                parent_config = CheckpointConfig(
                    thread_id=config.thread_id, checkpoint_id=parent_id
                )

            stored_config = CheckpointConfig(
                thread_id=config.thread_id, checkpoint_id=checkpoint.id
            )
            tuple_ = CheckpointTuple(
                config=stored_config,
                checkpoint=copy.deepcopy(checkpoint),
                metadata=copy.deepcopy(metadata),
                parent_config=parent_config,
                pending_writes=None,
            )
            self._store[checkpoint.id] = tuple_

            tid = config.thread_id
            if tid not in self._thread_index:
                self._thread_index[tid] = []
            self._thread_index[tid].append(checkpoint.id)

            return CheckpointConfig(
                thread_id=config.thread_id, checkpoint_id=checkpoint.id
            )

    def get_tuple(self, config: CheckpointConfig) -> Optional[CheckpointTuple]:
        with self._lock:
            cp_id = self._resolve_id(config)
            if cp_id is None:
                return None
            entry = self._store.get(cp_id)
            return copy.deepcopy(entry) if entry is not None else None

    def list(
        self,
        config: CheckpointConfig,
        *,
        limit: Optional[int] = None,
        before: Optional[CheckpointConfig] = None,
    ) -> Iterator[CheckpointTuple]:
        with self._lock:
            ids = list(self._thread_index.get(config.thread_id, []))

        # newest first
        ids = list(reversed(ids))

        if before is not None and before.checkpoint_id is not None:
            try:
                idx = ids.index(before.checkpoint_id)
                ids = ids[idx + 1 :]
            except ValueError:
                pass

        if limit is not None:
            ids = ids[:limit]

        for cp_id in ids:
            with self._lock:
                entry = self._store.get(cp_id)
            if entry is not None:
                yield copy.deepcopy(entry)

    def put_writes(
        self,
        config: CheckpointConfig,
        writes: Sequence[PendingWrite],
        task_id: str,
    ) -> None:
        with self._lock:
            cp_id = self._resolve_id(config)
            if cp_id is None:
                return
            existing = self._store.get(cp_id)
            if existing is None:
                return
            current_writes = list(existing.pending_writes or [])
            current_writes.extend(copy.deepcopy(list(writes)))
            self._store[cp_id] = CheckpointTuple(
                config=existing.config,
                checkpoint=existing.checkpoint,
                metadata=existing.metadata,
                parent_config=existing.parent_config,
                pending_writes=current_writes,
            )

    def delete(self, config: CheckpointConfig) -> None:
        with self._lock:
            cp_id = self._resolve_id(config)
            if cp_id is None:
                return
            self._store.pop(cp_id, None)
            ids = self._thread_index.get(config.thread_id, [])
            if cp_id in ids:
                ids.remove(cp_id)

    # ---- durable Session protocol ----

    def session_capabilities(self) -> frozenset[str]:
        return SESSION_PERSISTENCE_CAPABILITIES

    def commit_session_snapshot(
        self, request: SessionSnapshotCommit
    ) -> SessionCommitReceipt:
        with self._lock:
            current = self._session_heads.get(request.session_id)
            self._validate_session_cas(request, current)
            if request.snapshot_id in self._session_snapshot_index:
                raise checkpoint_conflict()
            checkpoint_id = CheckpointId(request.checkpoint_id)
            if checkpoint_id in self._store:
                raise checkpoint_conflict()

            parent_id = (
                CheckpointId(current.checkpoint_id) if current is not None else None
            )
            checkpoint = Checkpoint(
                id=checkpoint_id,
                thread_id=request.session_id,
                step=request.target_generation,
                state_data={"session_snapshot": copy.deepcopy(request.payload)},
                parent_id=parent_id,
                schema_version="qitos.session.snapshot/v2",
            )
            config = CheckpointConfig(
                thread_id=request.session_id, checkpoint_id=checkpoint_id
            )
            parent_config = (
                CheckpointConfig(
                    thread_id=request.session_id,
                    checkpoint_id=CheckpointId(current.checkpoint_id),
                )
                if current is not None
                else None
            )
            self._store[checkpoint_id] = CheckpointTuple(
                config=config,
                checkpoint=copy.deepcopy(checkpoint),
                metadata={
                    "source": "session",
                    "step": request.target_generation,
                    "run_id": request.owner_run_id,
                },
                parent_config=parent_config,
                pending_writes=None,
            )
            self._thread_index.setdefault(request.session_id, []).append(checkpoint_id)
            self._session_snapshot_index[request.snapshot_id] = checkpoint_id
            head = SessionHeadRecord(
                session_id=request.session_id,
                snapshot_id=request.snapshot_id,
                checkpoint_id=request.checkpoint_id,
                generation=request.target_generation,
                owner_run_id=request.owner_run_id,
                lifecycle=request.lifecycle,
            )
            self._session_heads[request.session_id] = head
            return SessionCommitReceipt(
                session_id=head.session_id,
                snapshot_id=head.snapshot_id,
                checkpoint_id=head.checkpoint_id,
                generation=head.generation,
                owner_run_id=head.owner_run_id,
                lifecycle=head.lifecycle,
                durable=True,
                store_kind="memory",
            )

    def get_session_head(self, session_id: str) -> Optional[SessionHeadRecord]:
        with self._lock:
            head = self._session_heads.get(session_id)
            return copy.deepcopy(head) if head is not None else None

    def get_session_snapshot(
        self, snapshot_id: str
    ) -> Optional[SessionSnapshotRecord]:
        with self._lock:
            checkpoint_id = self._session_snapshot_index.get(snapshot_id)
            if checkpoint_id is None:
                return None
            entry = self._store.get(checkpoint_id)
            if entry is None:
                return None
            head = next(
                (
                    value
                    for value in self._session_heads.values()
                    if value.snapshot_id == snapshot_id
                ),
                None,
            )
            return self._session_record(entry, snapshot_id, head)

    def list_session_lineage(
        self, session_id: str, *, limit: Optional[int] = None
    ) -> Iterator[SessionSnapshotRecord]:
        with self._lock:
            ids = list(reversed(self._thread_index.get(session_id, [])))
            if limit is not None:
                ids = ids[:limit]
            entries = [copy.deepcopy(self._store[item]) for item in ids]
            snapshot_by_checkpoint = {
                checkpoint_id: snapshot_id
                for snapshot_id, checkpoint_id in self._session_snapshot_index.items()
            }
            current = self._session_heads.get(session_id)
        for entry in entries:
            snapshot_id = snapshot_by_checkpoint.get(entry.checkpoint.id)
            if snapshot_id is not None:
                yield self._session_record(entry, snapshot_id, current)

    @staticmethod
    def _validate_session_cas(
        request: SessionSnapshotCommit, current: Optional[SessionHeadRecord]
    ) -> None:
        if request.expected_generation is None:
            if current is not None:
                raise generation_conflict(None, current.generation)
            return
        if current is None:
            raise generation_conflict(request.expected_generation, None)
        if current.generation != request.expected_generation:
            raise generation_conflict(request.expected_generation, current.generation)
        if current.checkpoint_id != request.expected_checkpoint_id:
            raise checkpoint_conflict()
        if current.owner_run_id != request.expected_owner_run_id:
            raise owner_conflict()

    @staticmethod
    def _session_record(
        entry: CheckpointTuple,
        snapshot_id: str,
        current: Optional[SessionHeadRecord],
    ) -> SessionSnapshotRecord:
        payload = entry.checkpoint.state_data.get("session_snapshot")
        if not isinstance(payload, dict):
            raise CheckpointSessionError(
                CheckpointSessionErrorCode.INCOMPATIBLE_CHECKPOINT,
                "Checkpoint does not contain a canonical Session snapshot.",
                recoverable=False,
            )
        owner = str(entry.metadata.get("run_id", ""))
        lifecycle = str(payload.get("lifecycle", ""))
        generation = payload.get("head_generation")
        if not isinstance(generation, int) or isinstance(generation, bool):
            raise CheckpointSessionError(
                CheckpointSessionErrorCode.CORRUPT_SNAPSHOT,
                "Stored Session snapshot generation is invalid.",
                recoverable=False,
            )
        if current is not None and current.snapshot_id == snapshot_id:
            owner = current.owner_run_id
            lifecycle = current.lifecycle
        return SessionSnapshotRecord(
            session_id=entry.checkpoint.thread_id,
            snapshot_id=snapshot_id,
            checkpoint_id=str(entry.checkpoint.id),
            generation=generation,
            owner_run_id=owner,
            lifecycle=lifecycle,
            payload=copy.deepcopy(payload),
            parent_checkpoint_id=(
                str(entry.checkpoint.parent_id)
                if entry.checkpoint.parent_id is not None
                else None
            ),
        )


__all__ = ["InMemoryCheckpointStore"]
