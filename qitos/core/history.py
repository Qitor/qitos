"""Canonical history contracts for model message context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class HistoryMessage:
    role: str
    content: str
    step_id: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HistoryPolicy:
    """Engine-side policy for selecting/assembling history messages."""

    roles: List[str] = field(default_factory=lambda: ["user", "assistant"])
    max_messages: int = 24
    step_window: Optional[int] = None

    def build_query(self, step_id: int) -> Dict[str, Any]:
        query: Dict[str, Any] = {"roles": list(self.roles), "max_items": int(self.max_messages)}
        if self.step_window is not None and self.step_window > 0:
            query["step_min"] = max(0, int(step_id) - int(self.step_window) + 1)
        return query


class History(ABC):
    @abstractmethod
    def append(self, message: HistoryMessage) -> None:
        """Append one chat message into history store."""

    @abstractmethod
    def retrieve(
        self,
        query: Optional[Dict[str, Any]] = None,
        state: Any = None,
        observation: Any = None,
    ) -> Any:
        """Retrieve history payload used for model message assembly."""

    @abstractmethod
    def summarize(self, max_items: int = 5) -> str:
        """Return strategy-specific summary for old messages."""

    @abstractmethod
    def evict(self) -> int:
        """Apply retention strategy and return number of evicted messages."""

    @abstractmethod
    def reset(self, run_id: Optional[str] = None) -> None:
        """Reset history runtime state for a new run."""


__all__ = ["History", "HistoryMessage", "HistoryPolicy"]
