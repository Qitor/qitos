"""Common state construction helpers."""

from __future__ import annotations

from typing import Any


def set_str(state: Any, key: str, value: str) -> Any:
    setattr(state, key, value)
    return state


def append_str(state: Any, key: str, value: str, max_items: int = 50) -> Any:
    items = list(getattr(state, key, []))
    items.append(value)
    if max_items > 0 and len(items) > max_items:
        items = items[-max_items:]
    setattr(state, key, items)
    return state


__all__ = ["set_str", "append_str"]
