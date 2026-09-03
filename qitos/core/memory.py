"""Canonical memory adapter contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, Sequence, runtime_checkable

from .request_view import ContextContribution


@dataclass
class MemoryRecord:
    role: str
    content: Any
    step_id: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class Memory(ABC):
    @abstractmethod
    def append(self, record: MemoryRecord) -> None:
        """Append one memory record."""

    @abstractmethod
    def retrieve(
        self,
        query: Optional[Dict[str, Any]] = None,
        state: Any = None,
        observation: Any = None,
    ) -> Any:
        """Retrieve memory payload by strategy.

        Common format:
        - List[MemoryRecord]
        """

    @abstractmethod
    def summarize(self, max_items: int = 5) -> str:
        """Return strategy-specific summary."""

    @abstractmethod
    def evict(self) -> int:
        """Apply retention strategy and return number of evicted records."""

    @abstractmethod
    def reset(self, run_id: Optional[str] = None) -> None:
        """Reset memory runtime state for a new run."""


@runtime_checkable
class MemorySource(Protocol):
    """Request-scoped semantic recall extension used by context assembly."""

    contributor_id: str

    def contribute(self, request: Any) -> Sequence[ContextContribution]:
        """Return deterministic, receipt-producing context contributions."""


__all__ = ["MemoryRecord", "Memory", "MemorySource"]
