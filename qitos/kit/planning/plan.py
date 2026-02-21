"""Planning helpers for AgentModule state management."""

from __future__ import annotations

import re
from typing import Any, List, Optional


def parse_numbered_plan(text: str) -> List[str]:
    if not text:
        return []
    lines = text.splitlines()
    items: List[str] = []
    for line in lines:
        s = line.strip()
        m = re.match(r"^(\d+)[\.)]\s*(.+)$", s)
        if m:
            items.append(m.group(2).strip())
    return items


class PlanCursor:
    """Operate plan/cursor fields on arbitrary state objects safely."""

    def __init__(self, plan_field: str = "plan", cursor_field: str = "plan_cursor"):
        self.plan_field = plan_field
        self.cursor_field = cursor_field

    def init(self, state: Any, plan: List[str]) -> None:
        setattr(state, self.plan_field, list(plan))
        setattr(state, self.cursor_field, 0)

    def current(self, state: Any) -> Optional[str]:
        plan = list(getattr(state, self.plan_field, []))
        cursor = int(getattr(state, self.cursor_field, 0))
        if cursor < 0 or cursor >= len(plan):
            return None
        return plan[cursor]

    def advance(self, state: Any) -> None:
        cursor = int(getattr(state, self.cursor_field, 0))
        setattr(state, self.cursor_field, cursor + 1)

    def done(self, state: Any) -> bool:
        plan = list(getattr(state, self.plan_field, []))
        cursor = int(getattr(state, self.cursor_field, 0))
        return cursor >= len(plan)


__all__ = ["parse_numbered_plan", "PlanCursor"]
