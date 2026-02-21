"""Search presets."""

from __future__ import annotations

from qitos.core.search import GreedySearchAdapter


def greedy_search(top_k: int | None = None) -> GreedySearchAdapter:
    return GreedySearchAdapter(top_k=top_k)


__all__ = ["greedy_search"]
