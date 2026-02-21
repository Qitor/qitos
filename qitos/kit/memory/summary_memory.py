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
    ) -> List[MemoryRecord] | List[Dict[str, str]]:
        query = query or {}
        fmt = str(query.get("format", "records"))
        max_items = int(query.get("max_items", self.keep_last))
        items = self._records[-max_items:]
        if fmt == "messages":
            messages: List[Dict[str, str]] = []
            for item in items:
                if item.role != "message" or not isinstance(item.content, dict):
                    continue
                role = str(item.content.get("role", "")).strip()
                content = str(item.content.get("content", ""))
                if role and content:
                    messages.append({"role": role, "content": content})
            return messages
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


__all__ = ["SummaryMemory"]
