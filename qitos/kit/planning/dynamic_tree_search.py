"""Dynamic tree-style search for branch decisions."""

from __future__ import annotations

from typing import Any, List, Optional, TypeVar

from qitos.core.decision import Decision
from qitos.engine.search import Search


ActionT = TypeVar("ActionT")
StateT = TypeVar("StateT")
ObsT = TypeVar("ObsT")


class DynamicTreeSearch(Search[StateT, ObsT, ActionT]):
    """Keep a frontier and adaptively select branches by score + novelty."""

    def __init__(
        self,
        top_k: int = 3,
        max_frontier: int = 64,
        score_key: str = "score",
        exploration_bonus: float = 0.25,
    ):
        self.top_k = top_k
        self.max_frontier = max_frontier
        self.score_key = score_key
        self.exploration_bonus = exploration_bonus
        self._frontier: List[Decision[ActionT]] = []

    def expand(self, state: StateT, obs: ObsT, seed_decision: Decision[ActionT]) -> List[Decision[ActionT]]:
        fresh = list(seed_decision.candidates)
        combined = self._frontier + fresh
        self._frontier = []
        return combined

    def score(self, state: StateT, obs: ObsT, candidates: List[Decision[ActionT]]) -> List[float]:
        scores: List[float] = []
        visit_map = self._visit_counts(state)
        for idx, candidate in enumerate(candidates):
            base = self._read_base_score(candidate, default=float(len(candidates) - idx))
            key = self._candidate_key(candidate, idx)
            visits = visit_map.get(key, 0)
            novelty = self.exploration_bonus / float(1 + visits)
            scores.append(base + novelty)
        return scores

    def prune(self, candidates: List[Decision[ActionT]], scores: List[float]) -> List[Decision[ActionT]]:
        if len(candidates) != len(scores):
            raise ValueError("DynamicTreeSearch.prune requires aligned candidates/scores")
        ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)
        kept = [c for _, c in ranked[: self.top_k]]
        rest = [c for _, c in ranked[self.top_k :]]
        if rest:
            self._frontier.extend(rest)
            if len(self._frontier) > self.max_frontier:
                self._frontier = self._frontier[: self.max_frontier]
        return kept

    def select(self, candidates: List[Decision[ActionT]], scores: List[float]) -> Decision[ActionT]:
        if not candidates:
            raise ValueError("DynamicTreeSearch.select requires candidates")
        if len(candidates) != len(scores):
            raise ValueError("DynamicTreeSearch.select requires aligned candidates/scores")
        best = max(range(len(candidates)), key=lambda i: scores[i])
        return candidates[best]

    def backtrack(self, state: StateT) -> StateT:
        metadata = getattr(state, "metadata", None)
        if isinstance(metadata, dict):
            metadata["tree_backtrack"] = True
            metadata["frontier_size"] = len(self._frontier)
            setattr(state, "metadata", metadata)
        return state

    def mark_selected(self, state: StateT, selected: Decision[ActionT]) -> None:
        metadata = getattr(state, "metadata", None)
        if not isinstance(metadata, dict):
            return
        visits = metadata.get("tree_visits", {})
        if not isinstance(visits, dict):
            visits = {}
        key = self._candidate_key(selected, 0)
        visits[key] = int(visits.get(key, 0)) + 1
        metadata["tree_visits"] = visits
        metadata["frontier_size"] = len(self._frontier)
        metadata["tree_backtrack"] = False
        setattr(state, "metadata", metadata)

    def _read_base_score(self, candidate: Decision[ActionT], default: float) -> float:
        if isinstance(candidate.meta, dict):
            value = candidate.meta.get(self.score_key)
            if isinstance(value, (int, float)):
                return float(value)
        return default

    def _candidate_key(self, candidate: Decision[ActionT], idx: int) -> str:
        if isinstance(candidate.meta, dict) and "id" in candidate.meta:
            return str(candidate.meta["id"])
        if candidate.final_answer:
            return f"final::{candidate.final_answer[:64]}"
        if candidate.actions:
            return f"act::{str(candidate.actions[0])[:96]}"
        return f"candidate::{idx}"

    def _visit_counts(self, state: StateT) -> dict[str, int]:
        metadata = getattr(state, "metadata", None)
        if not isinstance(metadata, dict):
            return {}
        visits = metadata.get("tree_visits")
        if isinstance(visits, dict):
            return {str(k): int(v) for k, v in visits.items()}
        return {}


__all__ = ["DynamicTreeSearch"]
