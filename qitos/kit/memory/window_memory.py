"""Window memory implementation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from qitos.core.memory import Memory, MemoryRecord


class WindowMemory(Memory):
    def __init__(self, window_size: int = 20):
        self.window_size = window_size
        self._records: List[MemoryRecord] = []

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
        roles = query.get("roles")
        step_min = query.get("step_min")

        items = self._records[-self.window_size :] if self.window_size > 0 else list(self._records)
        if roles:
            role_set = set(roles)
            items = [r for r in items if r.role in role_set]
        if step_min is not None:
            items = [r for r in items if r.step_id >= step_min]
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
        items = self.retrieve()[-max_items:]
        return "\n".join(f"[{r.step_id}] {r.role}: {str(r.content)[:120]}" for r in items)

    def evict(self) -> int:
        if self.window_size <= 0 or len(self._records) <= self.window_size:
            return 0
        remove_n = len(self._records) - self.window_size
        self._records = self._records[-self.window_size :]
        return remove_n

    def reset(self, run_id: Optional[str] = None) -> None:
        self._records = []

    @property
    def records(self) -> List[MemoryRecord]:
        return list(self._records)


__all__ = ["WindowMemory"]
