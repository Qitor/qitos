"""Markdown-backed memory implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from qitos.core.memory import Memory, MemoryRecord


class MarkdownFileMemory(Memory):
    """Persist memory records in a local markdown log file."""

    def __init__(self, path: str = "memory.md", max_in_memory: int = 200):
        self.path = Path(path)
        self.max_in_memory = max_in_memory
        self._records: List[MemoryRecord] = []
        self._ensure_file()

    def append(self, record: MemoryRecord) -> None:
        self._records.append(record)
        self._append_markdown(record)
        if self.max_in_memory > 0 and len(self._records) > self.max_in_memory:
            self._records = self._records[-self.max_in_memory :]

    def retrieve(
        self,
        query: Optional[Dict[str, object]] = None,
        state: object = None,
        observation: object = None,
    ) -> List[MemoryRecord]:
        query = query or {}
        roles = set(query.get("roles", [])) if isinstance(query.get("roles"), list) else None
        step_min = query.get("step_min")
        max_items = int(query.get("max_items", 50))

        items = list(self._records)
        if roles:
            items = [r for r in items if r.role in roles]
        if isinstance(step_min, int):
            items = [r for r in items if r.step_id >= step_min]
        items = items[-max_items:]
        return items

    def summarize(self, max_items: int = 5) -> str:
        items = self._records[-max_items:]
        return "\n".join(f"[{r.step_id}] {r.role}: {str(r.content)[:120]}" for r in items)

    def evict(self) -> int:
        if self.max_in_memory <= 0 or len(self._records) <= self.max_in_memory:
            return 0
        removed = len(self._records) - self.max_in_memory
        self._records = self._records[-self.max_in_memory :]
        return removed

    def reset(self, run_id: Optional[str] = None) -> None:
        self._records = []

    def _ensure_file(self) -> None:
        if self.path.exists():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        header = [
            "# QitOS Memory Log",
            "",
            "This file is append-only runtime memory for one or more agent runs.",
            "",
        ]
        self.path.write_text("\n".join(header), encoding="utf-8")

    def _append_markdown(self, record: MemoryRecord) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        block = [
            f"## Step {record.step_id} · {record.role}",
            f"- time_utc: {ts}",
        ]
        if record.metadata:
            block.append(f"- metadata: {record.metadata}")
        block.extend(["", "```text", str(record.content), "```", ""])
        with self.path.open("a", encoding="utf-8") as fp:
            fp.write("\n".join(block))


__all__ = ["MarkdownFileMemory"]
