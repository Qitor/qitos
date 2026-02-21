"""Stop criteria contracts for the canonical Engine."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, Tuple


class StopCriteria(ABC):
    @abstractmethod
    def should_stop(
        self,
        state: Any,
        step_count: int,
        runtime_info: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Return (should_stop, reason)."""


class MaxStepsCriteria(StopCriteria):
    def __init__(self, max_steps: int):
        self.max_steps = max_steps

    def should_stop(
        self,
        state: Any,
        step_count: int,
        runtime_info: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str]]:
        if step_count + 1 >= self.max_steps:
            return True, "max_steps"
        return False, None


class FinalResultCriteria(StopCriteria):
    def should_stop(
        self,
        state: Any,
        step_count: int,
        runtime_info: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str]]:
        final_result = getattr(state, "final_result", None)
        if final_result:
            return True, "final_result"
        return False, None


class MaxRuntimeCriteria(StopCriteria):
    def __init__(self, max_runtime_seconds: float):
        self.max_runtime_seconds = float(max_runtime_seconds)

    def should_stop(
        self,
        state: Any,
        step_count: int,
        runtime_info: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str]]:
        info = runtime_info or {}
        elapsed = float(info.get("elapsed_seconds", 0.0))
        if elapsed >= self.max_runtime_seconds:
            return True, "max_runtime"
        return False, None


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
    ) -> Tuple[bool, Optional[str]]:
        signature = self.signature_fn(state)
        if signature == self._last_signature:
            self._stagnant_steps += 1
        else:
            self._stagnant_steps = 0
            self._last_signature = signature

        if self._stagnant_steps >= self.max_stagnant_steps:
            return True, "stagnation"
        return False, None


__all__ = [
    "StopCriteria",
    "MaxStepsCriteria",
    "FinalResultCriteria",
    "MaxRuntimeCriteria",
    "StagnationCriteria",
]
