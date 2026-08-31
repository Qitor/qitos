"""Cancellation support for Engine runs.

Provides ``EngineResult.cancel(mode)`` to stop a running Engine
either immediately or after the current step completes.

Modes
-----
- ``"immediate"`` — signal the Engine loop to stop right away.
  The current step may be mid-execution; partial results are preserved.
- ``"after_step"`` — wait for the current step to finish before stopping.
  This ensures the step's reduce/critic/check_stop lifecycle completes.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Optional

from ..core.session import AttemptIdentity
from ..core.tool_runtime import (
    CancellationCapability,
    ToolLifecycleReceipt,
    ToolLifecycleSpec,
    ToolLifecycleState,
)


class CancelMode(str, Enum):
    """Cancellation mode for Engine runs."""

    NONE = "none"
    IMMEDIATE = "immediate"
    AFTER_STEP = "after_step"


class CancelToken:
    """Thread-safe cancellation signal shared between EngineResult and Engine.

    The Engine checks ``token.is_cancel_requested`` at each loop iteration
    and after each step. Setting the mode to ``"immediate"`` causes the
    next check to break; ``"after_step"`` waits until the step finishes.
    """

    def __init__(self) -> None:
        self._mode = CancelMode.NONE
        self._lock = threading.Lock()
        self._step_complete = threading.Event()

    @property
    def mode(self) -> CancelMode:
        with self._lock:
            return self._mode

    @property
    def is_cancel_requested(self) -> bool:
        with self._lock:
            return self._mode != CancelMode.NONE

    def request_cancel(self, mode: str = "immediate") -> None:
        """Signal the Engine to cancel.

        Parameters
        ----------
        mode : str
            ``"immediate"`` or ``"after_step"``.
        """
        with self._lock:
            self._mode = CancelMode(mode)

    def clear(self) -> None:
        """Reset the token (called at the start of each Engine run)."""
        with self._lock:
            self._mode = CancelMode.NONE
        self._step_complete.clear()

    def mark_step_complete(self) -> None:
        """Signal that the current step has finished."""
        self._step_complete.set()

    def wait_for_step_complete(self, timeout: float = 30.0) -> bool:
        """Wait until the current step completes or timeout expires."""
        return self._step_complete.wait(timeout=timeout)

    def reset_step_event(self) -> None:
        """Reset the step-complete event for the next step."""
        self._step_complete.clear()


class QuiescenceState(str, Enum):
    """Closed pause/cancellation boundary vocabulary for tool attempts."""

    RUNNING = "running"
    PAUSE_REQUESTED = "pause_requested"
    QUIESCING = "quiescing"
    QUIESCED = "quiesced"
    NON_MIGRATABLE = "non_migratable"
    CANCELLATION_REQUESTED = "cancellation_requested"
    CANCELLED = "cancelled"
    WORKER_STILL_RUNNING = "worker_still_running"
    OUTCOME_UNKNOWN = "outcome_unknown"


@dataclass(frozen=True)
class AttemptQuiescence:
    attempt_id: AttemptIdentity
    owner_generation: int
    lifecycle: ToolLifecycleSpec
    state: QuiescenceState
    worker_still_running: bool = False
    outcome_unknown: bool = False

    @property
    def settled(self) -> bool:
        return self.state in {QuiescenceState.QUIESCED, QuiescenceState.CANCELLED}

    def to_dict(self) -> Dict[str, object]:
        return {
            "attempt_id": self.attempt_id.to_dict(),
            "owner_generation": self.owner_generation,
            "resource_kind": self.lifecycle.resource_kind.value,
            "cancellation_capability": self.lifecycle.cancellation_capability.value,
            "state": self.state.value,
            "worker_still_running": self.worker_still_running,
            "outcome_unknown": self.outcome_unknown,
            "settled": self.settled,
        }


@dataclass(frozen=True)
class QuiescenceReceipt:
    state: QuiescenceState
    attempts: tuple[AttemptQuiescence, ...]
    deadline_reached: bool

    @property
    def migratable(self) -> bool:
        return self.state is QuiescenceState.QUIESCED

    def to_dict(self) -> Dict[str, object]:
        return {
            "state": self.state.value,
            "migratable": self.migratable,
            "deadline_reached": self.deadline_reached,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
        }


class QuiescenceBarrier:
    """Condition-based barrier over real attempt completion acknowledgements."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._attempts: Dict[AttemptIdentity, AttemptQuiescence] = {}
        self._cancel_callbacks: Dict[AttemptIdentity, Callable[[], bool]] = {}
        self._state = QuiescenceState.RUNNING

    @property
    def state(self) -> QuiescenceState:
        with self._condition:
            return self._state

    def register(
        self,
        attempt_id: AttemptIdentity,
        lifecycle: ToolLifecycleSpec,
        *,
        owner_generation: int,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> None:
        with self._condition:
            current = self._attempts.get(attempt_id)
            if current is not None and not current.settled:
                raise ValueError("attempt is already registered and unresolved")
            self._attempts[attempt_id] = AttemptQuiescence(
                attempt_id=attempt_id,
                owner_generation=owner_generation,
                lifecycle=lifecycle,
                state=QuiescenceState.RUNNING,
            )
            if cancel_callback is not None:
                self._cancel_callbacks[attempt_id] = cancel_callback
            self._state = QuiescenceState.RUNNING
            self._condition.notify_all()

    def mark_terminal(self, receipt: ToolLifecycleReceipt) -> None:
        with self._condition:
            current = self._attempts.get(receipt.attempt_id)
            if current is None:
                return
            if current.owner_generation != receipt.owner_generation:
                return
            if receipt.worker_still_running and current.state in {
                QuiescenceState.QUIESCED,
                QuiescenceState.OUTCOME_UNKNOWN,
            }:
                return
            if receipt.worker_still_running:
                state = QuiescenceState.WORKER_STILL_RUNNING
            elif receipt.outcome_unknown:
                state = QuiescenceState.OUTCOME_UNKNOWN
            elif receipt.state is ToolLifecycleState.CANCELLED:
                state = QuiescenceState.CANCELLED
            else:
                state = QuiescenceState.QUIESCED
            self._attempts[receipt.attempt_id] = AttemptQuiescence(
                attempt_id=current.attempt_id,
                owner_generation=current.owner_generation,
                lifecycle=current.lifecycle,
                state=state,
                worker_still_running=receipt.worker_still_running,
                outcome_unknown=receipt.outcome_unknown,
            )
            self._cancel_callbacks.pop(receipt.attempt_id, None)
            self._condition.notify_all()

    def mark_worker_completed(
        self,
        attempt_id: AttemptIdentity,
        *,
        owner_generation: int,
        outcome_unknown: bool,
    ) -> None:
        """Acknowledge natural completion of a worker observed after timeout."""
        with self._condition:
            current = self._attempts.get(attempt_id)
            if current is None or current.owner_generation != owner_generation:
                return
            state = (
                QuiescenceState.OUTCOME_UNKNOWN
                if outcome_unknown
                else QuiescenceState.QUIESCED
            )
            self._attempts[attempt_id] = AttemptQuiescence(
                attempt_id=current.attempt_id,
                owner_generation=current.owner_generation,
                lifecycle=current.lifecycle,
                state=state,
                worker_still_running=False,
                outcome_unknown=outcome_unknown,
            )
            self._cancel_callbacks.pop(attempt_id, None)
            self._condition.notify_all()

    def request_cancellation(self, attempt_id: AttemptIdentity) -> AttemptQuiescence:
        with self._condition:
            current = self._attempts[attempt_id]
            if current.settled:
                return current
            requested = AttemptQuiescence(
                attempt_id=current.attempt_id,
                owner_generation=current.owner_generation,
                lifecycle=current.lifecycle,
                state=QuiescenceState.CANCELLATION_REQUESTED,
                worker_still_running=current.worker_still_running,
                outcome_unknown=current.outcome_unknown,
            )
            self._attempts[attempt_id] = requested
            callback = self._cancel_callbacks.get(attempt_id)
        accepted = False
        if (
            callback is not None
            and current.lifecycle.cancellation_capability
            is not CancellationCapability.NONE
        ):
            try:
                accepted = bool(callback())
            except Exception:
                accepted = False
        if not accepted:
            with self._condition:
                latest = self._attempts[attempt_id]
                unresolved = AttemptQuiescence(
                    attempt_id=latest.attempt_id,
                    owner_generation=latest.owner_generation,
                    lifecycle=latest.lifecycle,
                    state=QuiescenceState.WORKER_STILL_RUNNING,
                    worker_still_running=True,
                    outcome_unknown=latest.outcome_unknown,
                )
                self._attempts[attempt_id] = unresolved
                self._condition.notify_all()
                return unresolved
        return requested

    def request_pause(self, timeout: float) -> QuiescenceReceipt:
        """Wait for a safe boundary until one monotonic bounded deadline."""
        deadline = time.monotonic() + max(0.0, float(timeout))
        with self._condition:
            self._state = QuiescenceState.PAUSE_REQUESTED
            self._condition.notify_all()
            self._state = QuiescenceState.QUIESCING
            callbacks = list(self._cancel_callbacks.items())

        for attempt_id, callback in callbacks:
            with self._condition:
                current = self._attempts.get(attempt_id)
                capable = bool(
                    current is not None
                    and current.lifecycle.cancellation_capability
                    is not CancellationCapability.NONE
                )
            if not capable:
                continue
            try:
                callback()
            except Exception:
                pass

        deadline_reached = False
        with self._condition:
            while not self._all_quiesced_unlocked():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    deadline_reached = True
                    break
                self._condition.wait(timeout=remaining)
            if self._all_quiesced_unlocked():
                self._state = QuiescenceState.QUIESCED
            else:
                self._state = QuiescenceState.NON_MIGRATABLE
                for attempt_id, current in list(self._attempts.items()):
                    if current.settled:
                        continue
                    state = (
                        QuiescenceState.OUTCOME_UNKNOWN
                        if current.outcome_unknown
                        else QuiescenceState.WORKER_STILL_RUNNING
                    )
                    self._attempts[attempt_id] = AttemptQuiescence(
                        attempt_id=current.attempt_id,
                        owner_generation=current.owner_generation,
                        lifecycle=current.lifecycle,
                        state=state,
                        worker_still_running=not current.outcome_unknown,
                        outcome_unknown=current.outcome_unknown,
                    )
            return QuiescenceReceipt(
                state=self._state,
                attempts=self._attempt_snapshot_unlocked(),
                deadline_reached=deadline_reached,
            )

    def snapshot(self) -> QuiescenceReceipt:
        with self._condition:
            return QuiescenceReceipt(
                state=self._state,
                attempts=self._attempt_snapshot_unlocked(),
                deadline_reached=False,
            )

    def _all_quiesced_unlocked(self) -> bool:
        return all(attempt.settled for attempt in self._attempts.values())

    def _attempt_snapshot_unlocked(self) -> tuple[AttemptQuiescence, ...]:
        return tuple(
            sorted(self._attempts.values(), key=lambda item: item.attempt_id.value)
        )


__all__ = [
    "AttemptQuiescence",
    "CancelMode",
    "CancelToken",
    "QuiescenceBarrier",
    "QuiescenceReceipt",
    "QuiescenceState",
]
