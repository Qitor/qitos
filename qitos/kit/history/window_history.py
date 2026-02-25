"""Window history implementation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from qitos.core.history import History, HistoryMessage


class WindowHistory(History):
    def __init__(self, window_size: int = 24):
        self.window_size = int(window_size)
        self._messages: List[HistoryMessage] = []

    def append(self, message: HistoryMessage) -> None:
        self._messages.append(message)
        self.evict()

    def retrieve(
        self,
        query: Optional[Dict[str, Any]] = None,
        state: Any = None,
        observation: Any = None,
    ) -> List[HistoryMessage]:
        query = query or {}
        max_items = int(query.get("max_items", self.window_size if self.window_size > 0 else len(self._messages)))
        roles = query.get("roles")
        step_min = query.get("step_min")
        step_max = query.get("step_max")

        items = list(self._messages)
        if roles:
            role_set = set(roles)
            items = [m for m in items if m.role in role_set]
        if step_min is not None:
            items = [m for m in items if m.step_id >= int(step_min)]
        if step_max is not None:
            items = [m for m in items if m.step_id <= int(step_max)]
        if max_items > 0:
            items = items[-max_items:]
        return items

    def summarize(self, max_items: int = 5) -> str:
        items = self.retrieve(query={"max_items": max_items})
        lines = [f"[{m.step_id}] {m.role}: {m.content[:120]}" for m in items]
        return "\n".join(lines)

    def evict(self) -> int:
        if self.window_size <= 0 or len(self._messages) <= self.window_size:
            return 0
        removed = len(self._messages) - self.window_size
        self._messages = self._messages[-self.window_size :]
        return removed

    def reset(self, run_id: Optional[str] = None) -> None:
        self._messages = []

    @property
    def messages(self) -> List[HistoryMessage]:
        return list(self._messages)


__all__ = ["WindowHistory"]
