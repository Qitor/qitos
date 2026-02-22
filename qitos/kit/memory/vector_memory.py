"""Vector-like memory implementation with simple embedding."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from qitos.core.memory import Memory, MemoryRecord


class VectorMemory(Memory):
    def __init__(self, embedder: Optional[Callable[[str], List[float]]] = None, top_k: int = 5):
        self.embedder = embedder or self._default_embedder
        self.top_k = top_k
        self._records: List[MemoryRecord] = []
        self._vectors: List[List[float]] = []

    def append(self, record: MemoryRecord) -> None:
        self._records.append(record)
        self._vectors.append(self.embedder(str(record.content)))

    def retrieve(
        self,
        query: Optional[Dict[str, Any]] = None,
        state: Any = None,
        observation: Any = None,
    ) -> List[MemoryRecord] | List[Dict[str, str]]:
        query = query or {}
        fmt = str(query.get("format", "records"))
        text = str(query.get("text", ""))
        k = int(query.get("top_k", self.top_k))

        if not self._records:
            return []
        if not text:
            items = self._records[-k:]
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

        qv = self.embedder(text)
        scored: List[Tuple[float, int]] = []
        for idx, vec in enumerate(self._vectors):
            scored.append((self._dot(qv, vec), idx))
        scored.sort(key=lambda x: x[0], reverse=True)
        items = [self._records[idx] for _, idx in scored[:k]]
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
        return "\n".join(str(r.content)[:120] for r in self._records[-max_items:])

    def evict(self) -> int:
        return 0

    def reset(self, run_id: Optional[str] = None) -> None:
        self._records = []
        self._vectors = []

    def _default_embedder(self, text: str) -> List[float]:
        buckets = [0.0] * 16
        for i, ch in enumerate(text):
            buckets[i % 16] += (ord(ch) % 31) / 31.0
        return buckets

    def _dot(self, a: List[float], b: List[float]) -> float:
        n = min(len(a), len(b))
        return sum(a[i] * b[i] for i in range(n))


__all__ = ["VectorMemory"]
