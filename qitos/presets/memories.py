"""Memory presets."""

from __future__ import annotations

from qitos.memory import SummaryMemory, VectorMemory, WindowMemory


def window_memory(window_size: int = 20) -> WindowMemory:
    return WindowMemory(window_size=window_size)


def summary_memory(keep_last: int = 10) -> SummaryMemory:
    return SummaryMemory(keep_last=keep_last)


def vector_memory(top_k: int = 5) -> VectorMemory:
    return VectorMemory(top_k=top_k)


__all__ = ["window_memory", "summary_memory", "vector_memory"]
