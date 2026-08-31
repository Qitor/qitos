"""Acknowledged partial-result writes for crash recovery."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
from typing import Sequence

from .store import CheckpointConfig, CheckpointId, CheckpointStore, PendingWrite


class PendingWriteState(str, Enum):
    ACCEPTED = "accepted"
    STAGED = "staged"
    PERSISTED = "persisted"
    FAILED = "failed"
    DUPLICATE_IGNORED = "duplicate_ignored"
    STALE_OWNER_REJECTED = "stale_owner_rejected"


@dataclass(frozen=True)
class PendingWriteReceipt:
    task_id: str
    channel: str
    owner_generation: int
    state: PendingWriteState
    value_digest: Optional[str] = None
    error_code: Optional[str] = None

    @property
    def completed(self) -> bool:
        return self.state in {
            PendingWriteState.PERSISTED,
            PendingWriteState.FAILED,
            PendingWriteState.DUPLICATE_IGNORED,
            PendingWriteState.STALE_OWNER_REJECTED,
        }

    @property
    def durable(self) -> bool:
        return self.state in {
            PendingWriteState.PERSISTED,
            PendingWriteState.DUPLICATE_IGNORED,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "channel": self.channel,
            "owner_generation": self.owner_generation,
            "state": self.state.value,
            "value_digest": self.value_digest,
            "error_code": self.error_code,
            "completed": self.completed,
            "durable": self.durable,
        }


@dataclass(frozen=True)
class PendingWriteFlushReceipt:
    task_ids: tuple[str, ...]
    completed: bool
    durable: bool
    deadline_reached: bool
    receipts: tuple[PendingWriteReceipt, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_ids": list(self.task_ids),
            "completed": self.completed,
            "durable": self.durable,
            "deadline_reached": self.deadline_reached,
            "receipts": [receipt.to_dict() for receipt in self.receipts],
        }


class PendingWriteManager:
    """Persist terminal tool slots once and expose real completion receipts."""

    def __init__(self, store: CheckpointStore) -> None:
        self._store = store
        self._tasks: Dict[str, PendingWrite] = {}
        self._receipts: Dict[str, PendingWriteReceipt] = {}
        self._condition = threading.Condition()

    def begin_task(
        self,
        task_id: str,
        channel: str,
        *,
        owner_generation: int = 0,
    ) -> PendingWriteReceipt:
        """Declare one slot before execution without claiming persistence."""
        with self._condition:
            existing = self._receipts.get(task_id)
            if existing is not None:
                if existing.owner_generation != owner_generation:
                    return PendingWriteReceipt(
                        task_id,
                        existing.channel,
                        owner_generation,
                        PendingWriteState.STALE_OWNER_REJECTED,
                        error_code="stale_owner",
                    )
                return existing
            write = PendingWrite(task_id=task_id, channel=channel, value=None)
            receipt = PendingWriteReceipt(
                task_id,
                channel,
                owner_generation,
                PendingWriteState.ACCEPTED,
            )
            self._tasks[task_id] = write
            self._receipts[task_id] = receipt
            self._condition.notify_all()
            return receipt

    def complete_task(
        self,
        task_id: str,
        value: Any,
        config: CheckpointConfig,
        *,
        owner_generation: int = 0,
    ) -> PendingWriteReceipt:
        """Accept exactly one terminal value and persist it when a head exists."""
        digest = _value_digest(value)
        with self._condition:
            existing = self._receipts.get(task_id)
            if existing is None:
                write = PendingWrite(task_id, "tool_terminal", None)
                existing = PendingWriteReceipt(
                    task_id,
                    "tool_terminal",
                    owner_generation,
                    PendingWriteState.ACCEPTED,
                )
                self._tasks[task_id] = write
                self._receipts[task_id] = existing
            if existing.owner_generation != owner_generation:
                return PendingWriteReceipt(
                    task_id,
                    existing.channel,
                    owner_generation,
                    PendingWriteState.STALE_OWNER_REJECTED,
                    value_digest=digest,
                    error_code="stale_owner",
                )
            if existing.value_digest is not None:
                state = (
                    PendingWriteState.DUPLICATE_IGNORED
                    if existing.value_digest == digest
                    else PendingWriteState.FAILED
                )
                return PendingWriteReceipt(
                    task_id,
                    existing.channel,
                    owner_generation,
                    state,
                    value_digest=digest,
                    error_code=(
                        None
                        if state is PendingWriteState.DUPLICATE_IGNORED
                        else "conflicting_terminal"
                    ),
                )
            write = PendingWrite(task_id, existing.channel, value)
            self._tasks[task_id] = write
            staged = PendingWriteReceipt(
                task_id,
                existing.channel,
                owner_generation,
                PendingWriteState.STAGED,
                value_digest=digest,
            )
            self._receipts[task_id] = staged

        receipt = self._persist_if_addressable(write, config, staged)
        with self._condition:
            self._receipts[task_id] = receipt
            self._condition.notify_all()
        return receipt

    def get_pending(self, task_id: str) -> Optional[Any]:
        with self._condition:
            write = self._tasks.get(task_id)
            return write.value if write else None

    def get_receipt(self, task_id: str) -> Optional[PendingWriteReceipt]:
        with self._condition:
            return self._receipts.get(task_id)

    def load_pending_from_store(self, config: CheckpointConfig) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        tuple_ = self._store.get_tuple(config)
        if tuple_ is None or tuple_.pending_writes is None:
            return result
        with self._condition:
            for write in tuple_.pending_writes:
                result[write.task_id] = write.value
                self._tasks[write.task_id] = write
                self._receipts[write.task_id] = PendingWriteReceipt(
                    write.task_id,
                    write.channel,
                    0,
                    PendingWriteState.PERSISTED,
                    value_digest=_value_digest(write.value),
                )
            self._condition.notify_all()
        return result

    def commit_writes(self, config: CheckpointConfig) -> PendingWriteFlushReceipt:
        """Persist every staged terminal value against the supplied checkpoint."""
        with self._condition:
            staged = [
                (task_id, self._tasks[task_id], receipt)
                for task_id, receipt in self._receipts.items()
                if receipt.state is PendingWriteState.STAGED
                and self._tasks[task_id].value is not None
            ]
        for task_id, write, prior in staged:
            receipt = self._persist_if_addressable(write, config, prior)
            with self._condition:
                self._receipts[task_id] = receipt
                self._condition.notify_all()
        return self.wait_for_tasks(
            [task_id for task_id, _, _ in staged], timeout=0.0
        )

    def wait_for_tasks(
        self, task_ids: Sequence[str], *, timeout: float
    ) -> PendingWriteFlushReceipt:
        ordered_ids = tuple(dict.fromkeys(str(task_id) for task_id in task_ids))
        deadline = time.monotonic() + max(0.0, float(timeout))
        deadline_reached = False
        with self._condition:
            receipts: tuple[PendingWriteReceipt, ...] = ()
            complete = not ordered_ids
            while True:
                receipts = tuple(
                    self._receipts[task_id]
                    for task_id in ordered_ids
                    if task_id in self._receipts
                )
                complete = len(receipts) == len(ordered_ids) and all(
                    receipt.completed for receipt in receipts
                )
                if complete:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    deadline_reached = bool(ordered_ids)
                    break
                self._condition.wait(timeout=remaining)
            durable = len(receipts) == len(ordered_ids) and all(
                receipt.durable for receipt in receipts
            )
            return PendingWriteFlushReceipt(
                task_ids=ordered_ids,
                completed=complete,
                durable=durable,
                deadline_reached=deadline_reached,
                receipts=receipts,
            )

    def snapshot(self) -> tuple[PendingWriteReceipt, ...]:
        with self._condition:
            return tuple(self._receipts[key] for key in sorted(self._receipts))

    def clear_task(self, task_id: str) -> None:
        with self._condition:
            self._tasks.pop(task_id, None)
            self._receipts.pop(task_id, None)
            self._condition.notify_all()

    def reset(self) -> None:
        with self._condition:
            self._tasks.clear()
            self._receipts.clear()
            self._condition.notify_all()

    def _persist_if_addressable(
        self,
        write: PendingWrite,
        config: CheckpointConfig,
        prior: PendingWriteReceipt,
    ) -> PendingWriteReceipt:
        try:
            if self._store.get_tuple(config) is None:
                return prior
            self._store.put_writes(config, [write], task_id=write.task_id)
        except Exception:
            return PendingWriteReceipt(
                prior.task_id,
                prior.channel,
                prior.owner_generation,
                PendingWriteState.FAILED,
                value_digest=prior.value_digest,
                error_code="store_write_failed",
            )
        return PendingWriteReceipt(
            prior.task_id,
            prior.channel,
            prior.owner_generation,
            PendingWriteState.PERSISTED,
            value_digest=prior.value_digest,
        )


def _value_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


__all__ = [
    "PendingWriteFlushReceipt",
    "PendingWriteManager",
    "PendingWriteReceipt",
    "PendingWriteState",
]
