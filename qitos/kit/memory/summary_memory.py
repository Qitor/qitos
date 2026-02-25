"""Summary memory implementation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from qitos.core.memory import Memory, MemoryRecord


class SummaryMemory(Memory):
    def __init__(self, keep_last: int = 10):
        self.keep_last = keep_last
        self._records: List[MemoryRecord] = []
        self._summaries: List[str] = []

    def append(self, record: MemoryRecord) -> None:
        self._records.append(record)

    def retrieve(
        self,
        query: Optional[Dict[str, Any]] = None,
        state: Any = None,
        observation: Any = None,
    ) -> List[MemoryRecord]:
        query = query or {}
        max_items = int(query.get("max_items", self.keep_last))
        items = self._records[-max_items:]
        return items

    def summarize(self, max_items: int = 5) -> str:
        chunk = self._records[-max_items:]
        if not chunk:
            return ""
        summary = " | ".join(f"{r.role}:{str(r.content)[:80]}" for r in chunk)
        self._summaries.append(summary)
        return summary

    def evict(self) -> int:
        if len(self._records) <= self.keep_last:
            return 0
        removed = len(self._records) - self.keep_last
        if removed > 0:
            self.summarize(max_items=removed)
        self._records = self._records[-self.keep_last :]
        return removed

    def reset(self, run_id: Optional[str] = None) -> None:
        self._records = []
        self._summaries = []


__all__ = ["SummaryMemory"]
