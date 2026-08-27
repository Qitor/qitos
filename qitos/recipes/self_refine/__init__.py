"""Self-Refine method template for QitOS.

Implements the Self-Refine pattern (Madaan et al. 2023):
generate → critique → refine → critique → ... until quality threshold
or max iterations reached.

The SelfRefineCritic drives the loop: on each step it evaluates the
current draft and either requests a refinement (retry with
instruction_patch) or accepts the output (continue/stop).

Usage::

    from qitos.recipes.self_refine import SelfRefineAgent, SelfRefineCritic

    agent = SelfRefineAgent(llm=my_llm)
    result = agent.run(
        task="Write a concise summary of ...",
        critics=[SelfRefineCritic(max_refinements=3, quality_threshold=0.7)],
        max_steps=10,
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
class SelfRefineState(StateSchema):
    """State for the Self-Refine agent."""

    draft: str = ""
    refinement_count: int = 0
    max_refinements: int = 3
    critique_history: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Critic
# ---------------------------------------------------------------------------


class SelfRefineCritic(Critic):
    """Critic that drives the Self-Refine loop.

    Evaluates the current draft quality. If the score is below
    ``quality_threshold`` and refinements remain, returns ``retry``
    with an ``instruction_patch`` prompting the agent to improve.

    Parameters
    ----------
    max_refinements:
        Maximum number of refinement iterations.
    quality_threshold:
        Minimum score (0.0–1.0) to accept the draft. If the model
        hasn't produced a score, the critic uses heuristics based
        on draft length and refinement count.
    """

    def __init__(
        self,
        max_refinements: int = 3,
        quality_threshold: float = 0.7,
    ) -> None:
        self.max_refinements = max_refinements
        self.quality_threshold = quality_threshold

    def evaluate(
        self,
        state: Any,
        decision: CoreDecision[Any],
        results: list[Any],
    ) -> CriticResult:
        refine_state = state if isinstance(state, SelfRefineState) else None
        if refine_state is None:
            return CriticResult(action="continue")

        count = refine_state.refinement_count
        draft = refine_state.draft

        # Heuristic scoring: longer drafts after more refinements score higher
        # Real deployments should use an LLM-based scorer or custom metric
        if not draft:
            score = 0.1
        elif count == 0:
            score = 0.4
        elif count == 1:
            score = 0.6
        else:
            score = min(0.9, 0.5 + count * 0.15)

        # If draft is very short, penalize
        if draft and len(draft.strip()) < 20:
            score = min(score, 0.3)

        if score < self.quality_threshold and count < self.max_refinements:
            return CriticResult(
                action="retry",
                reason=f"Draft quality ({score:.2f}) below threshold ({self.quality_threshold}). "
                       f"Refinement {count + 1}/{self.max_refinements}.",
                score=score,
                instruction_patch=(
                    "Critique the current draft and produce an improved version. "
                    "Address any gaps, inaccuracies, or lack of detail."
                ),
                state_patch={"refinement_count": count + 1},
            )

        # Accept: either score is high enough or we've exhausted refinements
        action = "stop" if refine_state.draft else "continue"
        return CriticResult(
            action=action,
            reason=f"Draft accepted (score={score:.2f}, refinements={count}).",
            score=score,
        )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


_SELF_REFINE_SYSTEM_PROMPT = """\
You are a Self-Refine agent. Your workflow:

1. **Generate**: Produce an initial draft for the given task.
2. **Critique**: Identify weaknesses, gaps, or errors in your draft.
3. **Refine**: Produce an improved version addressing the critique.

When you have a satisfactory final answer, output it as:
FINAL ANSWER: <your answer>

Be thorough and precise. Each refinement should be meaningfully better.
"""


class SelfRefineAgent(AgentModule[SelfRefineState, Dict[str, Any], Any]):
    """Agent that implements the Self-Refine pattern.

    The agent generates a draft, receives critique via the
    SelfRefineCritic, and iteratively refines until the quality
    threshold is met or max refinements are reached.
    """

    def __init__(self, llm: Any = None, **kwargs: Any) -> None:
        super().__init__(
            llm=llm,
            model_parser=ReActTextParser(),
            **kwargs,
        )

    def init_state(self, task: str, **kwargs: Any) -> SelfRefineState:
        max_ref = int(kwargs.get("max_refinements", 3))
        return SelfRefineState(
            task=task,
            max_steps=int(kwargs.get("max_steps", 10)),
            max_refinements=max_ref,
        )

    def build_system_prompt(self, state: SelfRefineState) -> str | None:
        parts = [_SELF_REFINE_SYSTEM_PROMPT]
        if state.refinement_count > 0:
            parts.append(
                f"\nThis is refinement round {state.refinement_count}. "
                f"Improve upon the previous draft."
            )
        return "\n".join(parts)

    def prepare(self, state: SelfRefineState, observation: Dict[str, Any]) -> str:
        lines = [f"Task: {state.task}"]
        if state.draft:
            lines.append(f"\nCurrent draft:\n{state.draft}")
        if state.critique_history:
            lines.append(f"\nPrevious critiques:")
            for c in state.critique_history[-3:]:
                lines.append(f"- {c}")
        return "\n".join(lines)

    def reduce(
        self,
        state: SelfRefineState,
        observation: Dict[str, Any],
        decision: Decision[Any],
        action_results: List[Any],
    ) -> SelfRefineState:
        # Extract text from action results
        result_text = ""
        if action_results:
            for r in action_results:
                if isinstance(r, dict):
                    result_text += r.get("output", r.get("text", str(r)))
                elif isinstance(r, str):
                    result_text += r
        if not result_text and decision.rationale:
            result_text = decision.rationale

        # Check for FINAL ANSWER
        if "FINAL ANSWER:" in result_text:
            answer = result_text.split("FINAL ANSWER:", 1)[1].strip()
            state.draft = answer
            state.final_result = answer
        elif result_text:
            state.draft = result_text

        return state


__all__ = ["SelfRefineAgent", "SelfRefineCritic", "SelfRefineState"]
