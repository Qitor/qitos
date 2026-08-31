"""Checkpoint durability with monotonic completion acknowledgements."""

from __future__ import annotations

import atexit
import logging
import queue
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

_logger = logging.getLogger("qitos.checkpoint.durability")

from .store import (
    Checkpoint,
    CheckpointConfig,
    CheckpointMetadata,
    CheckpointStore,
    StateVersions,
)


class DurabilityMode(Enum):
    SYNC = "sync"
    ASYNC = "async"
    EXIT = "exit"


class DurabilityWriteState(str, Enum):
    QUEUED = "queued"
    BUFFERED = "buffered"
    PERSISTED = "persisted"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclass(frozen=True)
class DurabilityWriteReceipt:
    sequence: int
    checkpoint_id: str
    state: DurabilityWriteState
    error_code: Optional[str] = None

    @property
    def completed(self) -> bool:
        return self.state in {
            DurabilityWriteState.PERSISTED,
            DurabilityWriteState.FAILED,
            DurabilityWriteState.REJECTED,
        }

    @property
    def durable(self) -> bool:
        return self.state is DurabilityWriteState.PERSISTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "checkpoint_id": self.checkpoint_id,
            "state": self.state.value,
            "error_code": self.error_code,
            "completed": self.completed,
            "durable": self.durable,
        }


@dataclass(frozen=True)
class DurabilityFlushReceipt:
    target_sequence: int
    completed_sequence: int
    complete: bool
    durable: bool
    deadline_reached: bool
    failed_sequences: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_sequence": self.target_sequence,
            "completed_sequence": self.completed_sequence,
            "complete": self.complete,
            "durable": self.durable,
            "deadline_reached": self.deadline_reached,
            "failed_sequences": list(self.failed_sequences),
        }


@dataclass(frozen=True)
class _QueuedWrite:
    sequence: int
    config: CheckpointConfig
    checkpoint: Checkpoint
    metadata: CheckpointMetadata
    new_versions: StateVersions


class DurabilityManager:
    """Wrap a checkpoint store and expose acknowledged write barriers."""

    def __init__(
        self,
        store: CheckpointStore,
        mode: DurabilityMode = DurabilityMode.SYNC,
    ) -> None:
        self._store = store
        self._mode = mode
        self._buffer: list[_QueuedWrite] = []
        self._queue: Optional[queue.Queue] = None
        self._worker: Optional[threading.Thread] = None
        self._shutdown = threading.Event()
        self._condition = threading.Condition()
        self._next_sequence = 0
        self._accepted_sequence = 0
        self._completed_sequence = 0
        self._receipts: dict[int, DurabilityWriteReceipt] = {}

        if mode == DurabilityMode.ASYNC:
            self._queue = queue.Queue(maxsize=4096)
            self._worker = threading.Thread(
                target=self._async_worker,
                daemon=True,
                name="checkpoint-durability",
            )
            self._worker.start()
        elif mode == DurabilityMode.EXIT:
            atexit.register(self.flush)

    def put(
        self,
        config: CheckpointConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: StateVersions,
    ) -> CheckpointConfig:
        result, _ = self.put_with_receipt(
            config, checkpoint, metadata, new_versions
        )
        return result

    def put_with_receipt(
        self,
        config: CheckpointConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: StateVersions,
    ) -> tuple[CheckpointConfig, DurabilityWriteReceipt]:
        sequence = self._allocate_sequence()
        item = _QueuedWrite(
            sequence, config, checkpoint, metadata, new_versions
        )
        immediate = CheckpointConfig(
            thread_id=config.thread_id, checkpoint_id=checkpoint.id
        )
        if self._mode == DurabilityMode.SYNC:
            try:
                result = self._store.put(
                    config, checkpoint, metadata, new_versions
                )
            except Exception:
                self._record_terminal(item, DurabilityWriteState.FAILED)
                raise
            receipt = self._record_terminal(item, DurabilityWriteState.PERSISTED)
            return result, receipt
        if self._mode == DurabilityMode.ASYNC:
            assert self._queue is not None
            queued = DurabilityWriteReceipt(
                sequence,
                str(checkpoint.id),
                DurabilityWriteState.QUEUED,
            )
            # Publish QUEUED while holding the same condition used by the
            # worker's terminal acknowledgement.  Otherwise a very fast store
            # can persist the item and then have its terminal receipt replaced
            # by the producer's stale QUEUED receipt.
            with self._condition:
                try:
                    self._queue.put_nowait(item)
                except queue.Full:
                    _logger.warning(
                        "DurabilityManager queue full (maxsize=4096); rejecting "
                        "checkpoint for thread_id=%s",
                        config.thread_id,
                    )
                    rejected = DurabilityWriteReceipt(
                        sequence,
                        str(checkpoint.id),
                        DurabilityWriteState.REJECTED,
                        error_code="queue_full",
                    )
                    # Rejection is a terminal acknowledgement for this
                    # submitted sequence, not permission to hide it from the
                    # next durability barrier.
                    self._accepted_sequence = max(
                        self._accepted_sequence, sequence
                    )
                    self._receipts[sequence] = rejected
                    self._condition.notify_all()
                    return immediate, rejected
                self._accepted_sequence = max(self._accepted_sequence, sequence)
                self._receipts[sequence] = queued
                self._condition.notify_all()
            return immediate, queued

        buffered = DurabilityWriteReceipt(
            sequence,
            str(checkpoint.id),
            DurabilityWriteState.BUFFERED,
        )
        with self._condition:
            self._buffer.append(item)
            self._accepted_sequence = max(self._accepted_sequence, sequence)
            self._receipts[sequence] = buffered
            self._condition.notify_all()
        return immediate, buffered

    def flush(self, timeout: float = 10.0) -> DurabilityFlushReceipt:
        """Wait for writes accepted before this call to acknowledge completion."""
        if self._mode == DurabilityMode.EXIT:
            with self._condition:
                buffered = list(self._buffer)
                self._buffer.clear()
            for item in buffered:
                self._do_write(item)
        with self._condition:
            target = self._accepted_sequence
        return self.wait_for_sequence(target, timeout=timeout)

    def wait_for_sequence(
        self, target_sequence: int, *, timeout: float
    ) -> DurabilityFlushReceipt:
        deadline = time.monotonic() + max(0.0, float(timeout))
        deadline_reached = False
        with self._condition:
            while not self._target_completed_unlocked(target_sequence):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    deadline_reached = target_sequence > 0
                    break
                self._condition.wait(timeout=remaining)
            complete = self._target_completed_unlocked(target_sequence)
            failures = tuple(
                sequence
                for sequence, receipt in sorted(self._receipts.items())
                if sequence <= target_sequence
                and receipt.state
                in {DurabilityWriteState.FAILED, DurabilityWriteState.REJECTED}
            )
            return DurabilityFlushReceipt(
                target_sequence=target_sequence,
                completed_sequence=self._completed_sequence,
                complete=complete,
                durable=complete and not failures,
                deadline_reached=deadline_reached,
                failed_sequences=failures,
            )

    def receipt(self, sequence: int) -> Optional[DurabilityWriteReceipt]:
        with self._condition:
            return self._receipts.get(sequence)

    def shutdown(self, timeout: float = 10.0) -> DurabilityFlushReceipt:
        """Drain acknowledged work, then stop the owned worker."""
        receipt = self.flush(timeout=timeout)
        if self._mode == DurabilityMode.ASYNC and self._queue is not None:
            self._shutdown.set()
            try:
                self._queue.put(None, timeout=max(0.0, float(timeout)))
            except queue.Full:
                _logger.warning(
                    "DurabilityManager queue full during shutdown; worker "
                    "termination is not acknowledged"
                )
            if self._worker is not None:
                self._worker.join(timeout=max(0.0, float(timeout)))
            with self._condition:
                target = self._accepted_sequence
            return self.wait_for_sequence(target, timeout=0.0)
        return receipt

    def _allocate_sequence(self) -> int:
        with self._condition:
            self._next_sequence += 1
            return self._next_sequence

    def _async_worker(self) -> None:
        assert self._queue is not None
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                if not isinstance(item, _QueuedWrite):
                    _logger.warning(
                        "DurabilityManager ignored invalid queued write item"
                    )
                    continue
                self._do_write(item)
            finally:
                self._queue.task_done()

    def _do_write(self, item: _QueuedWrite) -> DurabilityWriteReceipt:
        try:
            self._store.put(
                item.config,
                item.checkpoint,
                item.metadata,
                item.new_versions,
            )
        except Exception:
            return self._record_terminal(item, DurabilityWriteState.FAILED)
        return self._record_terminal(item, DurabilityWriteState.PERSISTED)

    def _record_terminal(
        self, item: _QueuedWrite, state: DurabilityWriteState
    ) -> DurabilityWriteReceipt:
        receipt = DurabilityWriteReceipt(
            item.sequence,
            str(item.checkpoint.id),
            state,
            error_code=("store_write_failed" if state is DurabilityWriteState.FAILED else None),
        )
        with self._condition:
            self._accepted_sequence = max(self._accepted_sequence, item.sequence)
            self._receipts[item.sequence] = receipt
            terminal_sequences = {
                sequence
                for sequence, candidate in self._receipts.items()
                if candidate.completed
            }
            while self._completed_sequence + 1 in terminal_sequences:
                self._completed_sequence += 1
            self._condition.notify_all()
        return receipt

    def _target_completed_unlocked(self, target_sequence: int) -> bool:
        if target_sequence <= 0:
            return True
        return all(
            sequence in self._receipts and self._receipts[sequence].completed
            for sequence in range(1, target_sequence + 1)
        )


__all__ = [
    "DurabilityFlushReceipt",
    "DurabilityManager",
    "DurabilityMode",
    "DurabilityWriteReceipt",
    "DurabilityWriteState",
]
