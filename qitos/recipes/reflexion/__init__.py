"""Reflexion method template for QitOS.

Implements the Reflexion pattern (Shinn et al. 2023):
act → evaluate → reflect → store reflection → act again with memory.

The ReflexionCritic evaluates whether the current trajectory is
successful. On failure, it generates a verbal reflection stored in
the agent's memory, which informs future attempts.

Usage::

    from qitos.recipes.reflexion import ReflexionAgent, ReflexionCritic

    agent = ReflexionAgent(llm=my_llm)
    result = agent.run(
        task="Debug the failing test in ...",
        critics=[ReflexionCritic(max_reflections=3)],
        max_steps=15,
        return_state=True,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from qitos.core.agent_module import AgentModule
from qitos.core.decision import Decision
from qitos.core.state import StateSchema
from qitos.core.decision import Decision as CoreDecision
from qitos.engine.critic import Critic
from qitos.engine.critic_result import CriticResult
from qitos.kit.parser import ReActTextParser


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class ReflexionState(StateSchema):
    """State for the Reflexion agent."""

    reflections: List[str] = field(default_factory=list)
    reflection_count: int = 0
    max_reflections: int = 3
    last_action_success: bool = True
    attempt: int = 1


# ---------------------------------------------------------------------------
# Critic
# ---------------------------------------------------------------------------


class ReflexionCritic(Critic):
    """Critic that drives the Reflexion loop.

    Evaluates whether the current step succeeded. On failure (e.g.,
    tool error or empty result), generates a reflection as an
    ``instruction_patch`` that is stored in state and injected into
    the next iteration's system prompt.

    Parameters
    ----------
    max_reflections:
        Maximum number of reflection iterations before forcing stop.
    success_threshold:
        Minimum score to consider the trajectory successful.
    """

    def __init__(
        self,
        max_reflections: int = 3,
        success_threshold: float = 0.6,
    ) -> None:
        self.max_reflections = max_reflections
        self.success_threshold = success_threshold

    def evaluate(
        self,
        state: Any,
        decision: CoreDecision[Any],
        results: list[Any],
    ) -> CriticResult:
        reflex_state = state if isinstance(state, ReflexionState) else None
        if reflex_state is None:
            return CriticResult(action="continue")

        # Determine if current step failed
        has_error = any(
            isinstance(r, dict) and (r.get("error") or r.get("returncode", 0) != 0)
            for r in results
        )
        has_empty = not results or all(
            isinstance(r, dict) and not r.get("output", "").strip() for r in results
        )

        is_failure = has_error or has_empty

        if is_failure and reflex_state.reflection_count < self.max_reflections:
            # Generate reflection
            reflection = self._generate_reflection(decision, results)
            return CriticResult(
                action="retry",
                reason=f"Step failed. Generating reflection "
                       f"({reflex_state.reflection_count + 1}/{self.max_reflections}).",
                score=0.2,
                instruction_patch=(
                    f"REFLECTION on previous attempt: {reflection}\n\n"
                    f"Use this reflection to avoid the same mistakes. "
                    f"Try a different approach."
                ),
                state_patch={
                    "reflection_count": reflex_state.reflection_count + 1,
                    "last_action_success": False,
                },
            )

        # If we've exhausted reflections, stop
        if is_failure and reflex_state.reflection_count >= self.max_reflections:
            return CriticResult(
                action="stop",
                reason=f"Max reflections ({self.max_reflections}) reached with no success.",
                score=0.1,
            )

        # Success path
        score = 0.8 if reflex_state.last_action_success else 0.6
        if score >= self.success_threshold:
            return CriticResult(
                action="continue",
                reason="Step succeeded.",
                score=score,
                state_patch={"last_action_success": True},
            )

        return CriticResult(action="continue", score=score)

    def _generate_reflection(
        self, decision: CoreDecision[Any], results: list[Any]
    ) -> str:
        """Generate a verbal reflection from the failed step."""
        parts = []
        if decision.rationale:
            parts.append(f"Planned action rationale: {decision.rationale}")

        error_msgs = []
        for r in results:
            if isinstance(r, dict):
                if r.get("error"):
                    error_msgs.append(str(r["error"]))
                rc = r.get("returncode", 0)
                if rc != 0:
                    error_msgs.append(f"exit code {rc}")
        if error_msgs:
            parts.append(f"Errors encountered: {'; '.join(error_msgs)}")

        if parts:
            return " | ".join(parts)
        return "The previous attempt did not produce useful output. Consider an alternative approach."


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


_REFLEXION_SYSTEM_PROMPT = """\
You are a Reflexion agent. Your workflow:

1. **Act**: Take an action toward solving the task.
2. **Observe**: Process the result of your action.
3. **Reflect**: When you encounter failures, reflect on what went wrong and how to improve.
4. **Retry**: Use your reflections to guide better future actions.

Previous reflections are provided in your context. Learn from them.

When you have completed the task, output:
FINAL ANSWER: <your answer>
"""


class ReflexionAgent(AgentModule[ReflexionState, Dict[str, Any], Any]):
    """Agent that implements the Reflexion pattern.

    The agent takes actions, and when failures occur the
    ReflexionCritic generates reflections stored in state.
    These reflections are injected into subsequent prompts,
    enabling the agent to learn from past mistakes.
    """

    def __init__(self, llm: Any = None, **kwargs: Any) -> None:
        super().__init__(
            llm=llm,
            model_parser=ReActTextParser(),
            **kwargs,
        )

    def init_state(self, task: str, **kwargs: Any) -> ReflexionState:
        max_ref = int(kwargs.get("max_reflections", 3))
        return ReflexionState(
            task=task,
            max_steps=int(kwargs.get("max_steps", 15)),
            max_reflections=max_ref,
        )

    def build_system_prompt(self, state: ReflexionState) -> str | None:
        parts = [_REFLEXION_SYSTEM_PROMPT]
        if state.reflections:
            parts.append("\n## Previous Reflections")
            for i, r in enumerate(state.reflections, 1):
                parts.append(f"{i}. {r}")
        return "\n".join(parts)

    def prepare(self, state: ReflexionState, observation: Dict[str, Any]) -> str:
        lines = [f"Task: {state.task}"]
        lines.append(f"Attempt: {state.attempt}")
        lines.append(f"Reflections so far: {state.reflection_count}")
        return "\n".join(lines)

    def reduce(
        self,
        state: ReflexionState,
        observation: Dict[str, Any],
        decision: Decision[Any],
        action_results: List[Any],
    ) -> ReflexionState:
        # Store reflections from critic state patches
        result_text = ""
        if action_results:
            for r in action_results:
                if isinstance(r, dict):
                    result_text += r.get("output", r.get("text", str(r)))
                elif isinstance(r, str):
                    result_text += r

        # Check for FINAL ANSWER
        if "FINAL ANSWER:" in result_text:
            answer = result_text.split("FINAL ANSWER:", 1)[1].strip()
            state.final_result = answer

        # Track attempts
        if not state.last_action_success:
            state.attempt += 1

        return state


__all__ = ["ReflexionAgent", "ReflexionCritic", "ReflexionState"]
