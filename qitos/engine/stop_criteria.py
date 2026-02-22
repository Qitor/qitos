"""Stop criteria contracts for the canonical Engine."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, Tuple

from ..core.errors import StopReason


class StopCriteria(ABC):
    @abstractmethod
    def should_stop(
        self,
        state: Any,
        step_count: int,
        runtime_info: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[StopReason], Optional[str]]:
        """Return (should_stop, reason, detail)."""


class MaxStepsCriteria(StopCriteria):
    def __init__(self, max_steps: int):
        self.max_steps = max_steps

    def should_stop(
        self,
        state: Any,
        step_count: int,
        runtime_info: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[StopReason], Optional[str]]:
        if step_count >= self.max_steps:
            return True, StopReason.BUDGET_STEPS, f"step_id={step_count} reached max_steps={self.max_steps}"
        return False, None, None


class FinalResultCriteria(StopCriteria):
    def should_stop(
        self,
        state: Any,
        step_count: int,
        runtime_info: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[StopReason], Optional[str]]:
        final_result = getattr(state, "final_result", None)
        if final_result:
            return True, StopReason.FINAL, "state.final_result is set"
        return False, None, None


class MaxRuntimeCriteria(StopCriteria):
    def __init__(self, max_runtime_seconds: float):
        self.max_runtime_seconds = float(max_runtime_seconds)

    def should_stop(
        self,
        state: Any,
        step_count: int,
        runtime_info: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[StopReason], Optional[str]]:
        info = runtime_info or {}
        elapsed = float(info.get("elapsed_seconds", 0.0))
        if elapsed >= self.max_runtime_seconds:
            return True, StopReason.BUDGET_TIME, f"elapsed={elapsed:.3f}s >= max_runtime_seconds={self.max_runtime_seconds:.3f}s"
        return False, None, None


class StagnationCriteria(StopCriteria):
    def __init__(self, max_stagnant_steps: int = 3, signature_fn: Optional[Callable[[Any], Any]] = None):
        self.max_stagnant_steps = max_stagnant_steps
        self.signature_fn = signature_fn or (lambda s: (getattr(s, "final_result", None), getattr(s, "phase", None)))
        self._last_signature: Any = object()
        self._stagnant_steps: int = 0

    def should_stop(
        self,
        state: Any,
        step_count: int,
        runtime_info: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[StopReason], Optional[str]]:
        signature = self.signature_fn(state)
        if signature == self._last_signature:
            self._stagnant_steps += 1
        else:
            self._stagnant_steps = 0
            self._last_signature = signature

        if self._stagnant_steps >= self.max_stagnant_steps:
            return True, StopReason.STAGNATION, f"stagnant_steps={self._stagnant_steps}"
        return False, None, None


__all__ = [
    "StopCriteria",
    "MaxStepsCriteria",
    "FinalResultCriteria",
    "MaxRuntimeCriteria",
    "StagnationCriteria",
]
