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

        Common formats:
        - query["format"] == "records": List[MemoryRecord]
        - query["format"] == "messages": List[{"role": str, "content": str}]
        """

    def retrieve_messages(
        self,
        state: Any = None,
        observation: Any = None,
        query: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """Retrieve conversation history in chat message format."""
        merged = dict(query or {})
        merged["format"] = "messages"
        payload = self.retrieve(query=merged, state=state, observation=observation)
        messages: List[Dict[str, str]] = []
        if not isinstance(payload, list):
            return messages
        for item in payload:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "")).strip()
            content = str(item.get("content", ""))
            if role and content:
                messages.append({"role": role, "content": content})
        return messages

    @abstractmethod
    def summarize(self, max_items: int = 5) -> str:
        """Return strategy-specific summary."""

    @abstractmethod
    def evict(self) -> int:
        """Apply retention strategy and return number of evicted records."""

    @abstractmethod
    def reset(self, run_id: Optional[str] = None) -> None:
        """Reset memory runtime state for a new run."""


__all__ = ["MemoryRecord", "Memory"]
