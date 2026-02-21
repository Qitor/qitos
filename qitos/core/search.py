"""Search adapter contracts for tree-style decision workflows."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, List, Optional, TypeVar

from .decision import Decision


ActionT = TypeVar("ActionT")
StateT = TypeVar("StateT")
ObsT = TypeVar("ObsT")


class SearchAdapter(ABC, Generic[StateT, ObsT, ActionT]):
    @abstractmethod
    def expand(self, state: StateT, obs: ObsT, seed_decision: Decision[ActionT]) -> List[Decision[ActionT]]:
        """Expand a seed branch decision into concrete candidates."""

    @abstractmethod
    def score(self, state: StateT, obs: ObsT, candidates: List[Decision[ActionT]]) -> List[float]:
        """Score candidates for selection/pruning."""

    @abstractmethod
    def select(self, candidates: List[Decision[ActionT]], scores: List[float]) -> Decision[ActionT]:
        """Select one candidate for execution."""

    @abstractmethod
    def prune(self, candidates: List[Decision[ActionT]], scores: List[float]) -> List[Decision[ActionT]]:
        """Prune candidate set before selection."""

    @abstractmethod
    def backtrack(self, state: StateT) -> StateT:
        """Adjust state when search cannot proceed."""


class GreedySearchAdapter(SearchAdapter[StateT, ObsT, ActionT]):
    def __init__(self, top_k: Optional[int] = None):
        self.top_k = top_k

    def expand(self, state: StateT, obs: ObsT, seed_decision: Decision[ActionT]) -> List[Decision[ActionT]]:
        return list(seed_decision.candidates)

    def score(self, state: StateT, obs: ObsT, candidates: List[Decision[ActionT]]) -> List[float]:
        # Prefer candidates with explicit score in meta; fallback to insertion order.
        scores: List[float] = []
        for idx, candidate in enumerate(candidates):
            score = candidate.meta.get("score") if isinstance(candidate.meta, dict) else None
            if isinstance(score, (int, float)):
                scores.append(float(score))
            else:
                scores.append(float(len(candidates) - idx))
        return scores

    def select(self, candidates: List[Decision[ActionT]], scores: List[float]) -> Decision[ActionT]:
        if not candidates:
            raise ValueError("SearchAdapter.select requires candidates")
        if len(scores) != len(candidates):
            raise ValueError("SearchAdapter.select requires scores aligned with candidates")
        best_idx = max(range(len(scores)), key=lambda i: scores[i])
        return candidates[best_idx]

    def prune(self, candidates: List[Decision[ActionT]], scores: List[float]) -> List[Decision[ActionT]]:
        if len(scores) != len(candidates):
            raise ValueError("SearchAdapter.prune requires scores aligned with candidates")
        ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
        if self.top_k is None:
            return [c for _, c in ranked]
        return [c for _, c in ranked[: self.top_k]]

    def backtrack(self, state: StateT) -> StateT:
        return state


__all__ = ["SearchAdapter", "GreedySearchAdapter"]
