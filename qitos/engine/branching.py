"""Branch selection abstractions owned by Engine."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from qitos.core.decision import Decision


StateT = TypeVar("StateT")
ObsT = TypeVar("ObsT")
ActionT = TypeVar("ActionT")


class BranchSelector(ABC, Generic[StateT, ObsT, ActionT]):
    @abstractmethod
    def select(
        self,
        candidates: list[Decision[ActionT]],
        state: StateT,
        obs: ObsT,
    ) -> Decision[ActionT]:
        """Select one decision from branch candidates."""


class FirstCandidateSelector(BranchSelector[StateT, ObsT, ActionT]):
    def select(
        self,
        candidates: list[Decision[ActionT]],
        state: StateT,
        obs: ObsT,
    ) -> Decision[ActionT]:
        if not candidates:
            raise ValueError("Branch selector received empty candidates")
        return candidates[0]


__all__ = ["BranchSelector", "FirstCandidateSelector"]
