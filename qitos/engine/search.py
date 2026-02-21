"""Search adapter contracts for branch-style decision workflows."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, List, TypeVar

from ..core.decision import Decision


ActionT = TypeVar("ActionT")
StateT = TypeVar("StateT")
ObsT = TypeVar("ObsT")


class Search(ABC, Generic[StateT, ObsT, ActionT]):
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


__all__ = ["Search"]
