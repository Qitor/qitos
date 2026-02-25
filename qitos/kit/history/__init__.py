"""Concrete history implementations."""

from qitos.core.history import History, HistoryMessage

from .window_history import WindowHistory


def window_history(window_size: int = 24) -> WindowHistory:
    return WindowHistory(window_size=window_size)


__all__ = [
    "History",
    "HistoryMessage",
    "WindowHistory",
    "window_history",
]
