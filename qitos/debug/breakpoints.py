"""Breakpoint utilities for replay and debugging."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class Breakpoint:
    step_id: Optional[int] = None
    phase: Optional[str] = None
    condition: Optional[Callable[[dict], bool]] = None

    def matches(self, event: dict) -> bool:
        if self.step_id is not None and int(event.get("step_id", -1)) != self.step_id:
            return False
        if self.phase is not None and str(event.get("phase")) != self.phase:
            return False
        if self.condition is not None and not self.condition(event):
            return False
        return True
