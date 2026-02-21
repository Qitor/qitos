"""Canonical baseline memory adapter implementations."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from .adapter import MemoryAdapter, MemoryRecord


class WindowMemory(MemoryAdapter):
    def __init__(self, window_size: int = 20):
        self.window_size = window_size
        self._records: List[MemoryRecord] = []

    def append(self, record: MemoryRecord) -> None:
        self._records.append(record)

    def retrieve(self, query: Optional[Dict[str, Any]] = None) -> List[MemoryRecord]:
        query = query or {}
        roles = query.get("roles")
        step_min = query.get("step_min")

        items = self._records[-self.window_size :] if self.window_size > 0 else list(self._records)
        if roles:
            role_set = set(roles)
            items = [r for r in items if r.role in role_set]
        if step_min is not None:
            items = [r for r in items if r.step_id >= step_min]
        return items

    def summarize(self, max_items: int = 5) -> str:
        items = self.retrieve()[-max_items:]
        return "\n".join(f"[{r.step_id}] {r.role}: {str(r.content)[:120]}" for r in items)

    def evict(self) -> int:
        if self.window_size <= 0 or len(self._records) <= self.window_size:
            return 0
        remove_n = len(self._records) - self.window_size
        self._records = self._records[-self.window_size :]
        return remove_n

    @property
    def records(self) -> List[MemoryRecord]:
        return list(self._records)


class SummaryMemory(MemoryAdapter):
    def __init__(self, keep_last: int = 10):
        self.keep_last = keep_last
        self._records: List[MemoryRecord] = []
        self._summaries: List[str] = []

    def append(self, record: MemoryRecord) -> None:
        self._records.append(record)

    def retrieve(self, query: Optional[Dict[str, Any]] = None) -> List[MemoryRecord]:
        query = query or {}
        max_items = int(query.get("max_items", self.keep_last))
        return self._records[-max_items:]

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


class VectorMemory(MemoryAdapter):
    def __init__(self, embedder: Optional[Callable[[str], List[float]]] = None, top_k: int = 5):
        self.embedder = embedder or self._default_embedder
        self.top_k = top_k
        self._records: List[MemoryRecord] = []
        self._vectors: List[List[float]] = []

    def append(self, record: MemoryRecord) -> None:
        self._records.append(record)
        self._vectors.append(self.embedder(str(record.content)))

    def retrieve(self, query: Optional[Dict[str, Any]] = None) -> List[MemoryRecord]:
        query = query or {}
        text = str(query.get("text", ""))
        k = int(query.get("top_k", self.top_k))

        if not self._records:
            return []
        if not text:
            return self._records[-k:]

        qv = self.embedder(text)
        scored: List[Tuple[float, int]] = []
        for idx, vec in enumerate(self._vectors):
            scored.append((self._dot(qv, vec), idx))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._records[idx] for _, idx in scored[:k]]

    def summarize(self, max_items: int = 5) -> str:
        return "\n".join(str(r.content)[:120] for r in self._records[-max_items:])

    def evict(self) -> int:
        return 0

    def _default_embedder(self, text: str) -> List[float]:
        buckets = [0.0] * 16
        for i, ch in enumerate(text):
            buckets[i % 16] += (ord(ch) % 31) / 31.0
        return buckets

    def _dot(self, a: List[float], b: List[float]) -> float:
        n = min(len(a), len(b))
        return sum(a[i] * b[i] for i in range(n))


__all__ = ["WindowMemory", "SummaryMemory", "VectorMemory"]
