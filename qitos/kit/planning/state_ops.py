"""State utility ops for concise, repeatable reduce logic."""

from __future__ import annotations

from typing import Any

from qitos.core.action import Action


def append_log(state: Any, field: str, item: str, max_items: int | None = None) -> None:
    logs = list(getattr(state, field, []))
    logs.append(item)
    if max_items is not None and max_items > 0:
        logs = logs[-max_items:]
    setattr(state, field, logs)


def set_final(state: Any, value: str) -> None:
    if hasattr(state, "final_result"):
        state.final_result = value


def set_if_empty(state: Any, field: str, value: Any) -> None:
    if getattr(state, field, None) is None:
        setattr(state, field, value)


def format_action(action: Any) -> str:
    if isinstance(action, Action):
        name = action.name
        args = action.args
    elif isinstance(action, dict):
        name = str(action.get("name", ""))
        args = action.get("args", {})
    else:
        return str(action)
    if not isinstance(args, dict):
        return f"{name}()"
    pairs = ", ".join(f"{k}={repr(v)}" for k, v in args.items())
    return f"{name}({pairs})"


__all__ = ["append_log", "set_final", "set_if_empty", "format_action"]
