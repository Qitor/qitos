"""Canonical agent module interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, List, TypeVar

from .decision import Decision


StateT = TypeVar("StateT")
ObservationT = TypeVar("ObservationT")
ActionT = TypeVar("ActionT")


class AgentModule(ABC, Generic[StateT, ObservationT, ActionT]):
    """Canonical policy contract for step-based agents."""

    name: str = "agent"

    def __init__(self, toolkit: Any = None, llm: Any = None, **config: Any):
        self.toolkit = toolkit
        self.llm = llm
        self.config = config

    @abstractmethod
    def init_state(self, task: str, **kwargs: Any) -> StateT:
        """Create and return the initial typed state for a run."""

    def build_system_prompt(self, state: StateT) -> str | None:
        """Optional dynamic system prompt hook."""
        return None

    @abstractmethod
    def observe(self, state: StateT, env_view: Dict[str, Any]) -> ObservationT:
        """Build observation for current step from state and runtime env view."""

    @abstractmethod
    def decide(self, state: StateT, observation: ObservationT) -> Decision[ActionT]:
        """Produce decision for current step."""

    @abstractmethod
    def reduce(
        self,
        state: StateT,
        observation: ObservationT,
        decision: Decision[ActionT],
        action_results: List[Any],
    ) -> StateT:
        """Reduce observation + action results into next state."""

    def should_stop(self, state: StateT) -> bool:
        """Optional additional stop condition."""
        return False

    def build_engine(self, **engine_kwargs: Any):
        """Create an FSMEngine bound to this agent."""
        from ..engine.fsm_engine import FSMEngine

        return FSMEngine(agent=self, **engine_kwargs)

    def run(
        self,
        task: str,
        return_state: bool = False,
        engine_kwargs: Dict[str, Any] | None = None,
        **state_kwargs: Any,
    ) -> Any:
        """Execute task with FSMEngine."""
        engine = self.build_engine(**(engine_kwargs or {}))
        result = engine.run(task, **state_kwargs)
        if return_state:
            return result
        return result.state.final_result


class LegacyPerceiveAdapter(AgentModule[Dict[str, Any], Dict[str, Any], Dict[str, Any]]):
    """Compatibility adapter for old perceive/update_context style agents."""

    def __init__(self, legacy_agent: Any, **config: Any):
        super().__init__(toolkit=getattr(legacy_agent, "toolkit", None), llm=getattr(legacy_agent, "llm", None), **config)
        self.legacy_agent = legacy_agent

    def init_state(self, task: str, **kwargs: Any) -> Dict[str, Any]:
        state: Dict[str, Any] = {"task": task, "metadata": kwargs, "legacy_context": kwargs.get("context")}
        return state

    def observe(self, state: Dict[str, Any], env_view: Dict[str, Any]) -> Dict[str, Any]:
        if hasattr(self.legacy_agent, "perceive"):
            context = state.get("legacy_context") or state
            return {"messages": self.legacy_agent.perceive(context)}
        return {"messages": []}

    def decide(self, state: Dict[str, Any], observation: Dict[str, Any]) -> Decision[Dict[str, Any]]:
        return Decision.wait(rationale="Legacy adapter does not implement automatic decision policy.")

    def reduce(
        self,
        state: Dict[str, Any],
        observation: Dict[str, Any],
        decision: Decision[Dict[str, Any]],
        action_results: List[Any],
    ) -> Dict[str, Any]:
        if hasattr(self.legacy_agent, "update_context"):
            context = state.get("legacy_context") or state
            self.legacy_agent.update_context(context, action_results)
        state["last_action_results"] = action_results
        state["last_decision_mode"] = decision.mode
        return state


__all__ = ["AgentModule", "LegacyPerceiveAdapter"]
