"""Canonical memory adapter contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MemoryRecord:
    role: str
    content: Any
    step_id: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class MemoryAdapter(ABC):
    @abstractmethod
    def append(self, record: MemoryRecord) -> None:
        """Append one memory record."""

    @abstractmethod
    def retrieve(self, query: Optional[Dict[str, Any]] = None) -> List[MemoryRecord]:
        """Retrieve records by strategy."""

    @abstractmethod
    def summarize(self, max_items: int = 5) -> str:
        """Return strategy-specific summary."""

    @abstractmethod
    def evict(self) -> int:
        """Apply retention strategy and return number of evicted records."""


__all__ = ["MemoryRecord", "MemoryAdapter"]
