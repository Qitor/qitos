"""Concrete search adapters."""

from __future__ import annotations

from typing import List, Optional, TypeVar

from qitos.core.decision import Decision
from qitos.engine.search import Search


ActionT = TypeVar("ActionT")
StateT = TypeVar("StateT")
ObsT = TypeVar("ObsT")


class GreedySearch(Search[StateT, ObsT, ActionT]):
    def __init__(self, top_k: Optional[int] = None):
        self.top_k = top_k

    def expand(self, state: StateT, obs: ObsT, seed_decision: Decision[ActionT]) -> List[Decision[ActionT]]:
        return list(seed_decision.candidates)

    def score(self, state: StateT, obs: ObsT, candidates: List[Decision[ActionT]]) -> List[float]:
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
            raise ValueError("Search.select requires candidates")
        if len(scores) != len(candidates):
            raise ValueError("Search.select requires scores aligned with candidates")
        best_idx = max(range(len(scores)), key=lambda i: scores[i])
        return candidates[best_idx]

    def prune(self, candidates: List[Decision[ActionT]], scores: List[float]) -> List[Decision[ActionT]]:
        if len(scores) != len(candidates):
            raise ValueError("Search.prune requires scores aligned with candidates")
        ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
        if self.top_k is None:
            return [c for _, c in ranked]
        return [c for _, c in ranked[: self.top_k]]

    def backtrack(self, state: StateT) -> StateT:
        return state


__all__ = ["GreedySearch"]
