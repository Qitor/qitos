"""Canonical agent module interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, List, Optional, TypeVar

from .decision import Decision
from .history import History
from .memory import Memory
from .task import Task


StateT = TypeVar("StateT")
ObservationT = TypeVar("ObservationT")
ActionT = TypeVar("ActionT")


class AgentModule(ABC, Generic[StateT, ObservationT, ActionT]):
    """Canonical policy contract for step-based agents."""

    name: str = "agent"

    def __init__(
        self,
        tool_registry: Any = None,
        llm: Any = None,
        model_parser: Any = None,
        memory: Memory | None = None,
        history: History | None = None,
        **config: Any,
    ):
        self.tool_registry = tool_registry
        self.llm = llm
        self.model_parser = model_parser
        self.memory = memory
        self.history = history
        self.config = config

    @abstractmethod
    def init_state(self, task: str, **kwargs: Any) -> StateT:
        """Create and return the initial typed state for a run."""

    def build_system_prompt(self, state: StateT) -> str | None:
        """Optional dynamic system prompt hook."""
        return None

    def prepare(self, state: StateT) -> str:
        """Convert current state into model-ready text."""
        return str(state)

    def decide(self, state: StateT, observation: ObservationT) -> Optional[Decision[ActionT]]:
        """Optional custom decision hook. Return None to use Engine model decision."""
        return None

    @abstractmethod
    def reduce(
        self,
        state: StateT,
        observation: ObservationT,
        decision: Decision[ActionT],
    ) -> StateT:
        """Reduce observation (including action/env outputs) into next state."""

    def should_stop(self, state: StateT) -> bool:
        """Optional additional stop condition."""
        return False

    def build_engine(self, **engine_kwargs: Any):
        """Create an Engine bound to this agent."""
        from ..engine.engine import Engine

        return Engine(agent=self, **engine_kwargs)

    def run(
        self,
        task: str | Task,
        return_state: bool = False,
        hooks: List[Any] | None = None,
        render_hooks: List[Any] | None = None,
        engine_kwargs: Dict[str, Any] | None = None,
        **state_kwargs: Any,
    ) -> Any:
        """Execute task with Engine using plain text objective or structured Task."""
        kwargs = dict(engine_kwargs or {})
        if hooks is not None:
            kwargs["hooks"] = hooks
        if render_hooks is not None:
            kwargs["render_hooks"] = render_hooks
        engine = self.build_engine(**kwargs)
        result = engine.run(task, **state_kwargs)
        if return_state:
            return result
        return result.state.final_result


__all__ = ["AgentModule"]
