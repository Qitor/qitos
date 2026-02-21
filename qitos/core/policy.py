"""Policy abstractions for next-gen kernel."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Generic, Optional, TypeVar

from .decision import Decision


StateT = TypeVar("StateT")
ObsT = TypeVar("ObsT")
ActionT = TypeVar("ActionT")


class Policy(ABC, Generic[StateT, ObsT, ActionT]):
    def prepare(self, state: StateT, context: Optional[Dict[str, Any]] = None) -> None:
        """Optional pre-run hook."""

    @abstractmethod
    def propose(self, state: StateT, obs: ObsT) -> Decision[ActionT]:
        """Propose next decision from current state and observation."""

    @abstractmethod
    def update(
        self,
        state: StateT,
        obs: ObsT,
        decision: Decision[ActionT],
        results: list[Any],
    ) -> StateT:
        """Apply reducer update and return state."""

    def finalize(self, state: StateT) -> None:
        """Optional post-run hook."""


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


class ObservationBuilder(ABC, Generic[StateT, ObsT]):
    @abstractmethod
    def build(self, state: StateT, runtime_view: Dict[str, Any]) -> ObsT:
        """Build observation for policy input."""
