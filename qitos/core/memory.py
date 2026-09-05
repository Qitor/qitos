"""Canonical memory adapter contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, Sequence, runtime_checkable
from uuid import uuid4

from .request_view import ContextContribution


class MemoryResourceError(ValueError):
    """A bound durable memory resource is missing or unavailable."""

    code = "memory_resource_unavailable"


@dataclass
class MemoryRecord:
    """One logical memory fact; independent equal facts receive distinct IDs."""

    role: str
    content: Any
    step_id: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    record_id: str = field(default_factory=lambda: uuid4().hex)


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
