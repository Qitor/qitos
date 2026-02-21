"""ReAct-oriented self-reflection critic."""

from __future__ import annotations

from typing import Any, Dict, List

from qitos.core.decision import Decision
from qitos.engine.critic import Critic


class ReActSelfReflectionCritic(Critic):
    """Generate structured reflection notes and control retry/stop."""

    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries

    def evaluate(self, state: Any, decision: Decision[Any], results: List[Any]) -> Dict[str, Any]:
        metadata = getattr(state, "metadata", {}) or {}
        retries = int(metadata.get("reflection_retries", 0))
        reflections = metadata.get("self_reflections", [])
        if not isinstance(reflections, list):
            reflections = []

        error_payloads = [r for r in results if isinstance(r, dict) and r.get("error")]
        if error_payloads:
            reflection = self._build_error_reflection(decision, error_payloads[0])
            reflections.append(reflection)
            metadata["self_reflections"] = reflections
            metadata["reflection_retries"] = retries + 1
            state.metadata = metadata
            if retries < self.max_retries:
                return {
                    "action": "retry",
                    "reason": "react_reflection_retry",
                    "score": 0.2,
                    "details": {"reflection": reflection, "retry": retries + 1},
                }
            return {
                "action": "stop",
                "reason": "react_reflection_exceeded_retries",
                "score": 0.0,
                "details": {"reflection": reflection, "retry": retries + 1},
            }

        if decision.mode == "final" and decision.final_answer:
            reflections.append("Final answer produced. Verify constraints satisfied.")
            metadata["self_reflections"] = reflections[-20:]
            state.metadata = metadata

        return {"action": "continue", "reason": "react_reflection_pass", "score": 1.0}

    def _build_error_reflection(self, decision: Decision[Any], error_item: Dict[str, Any]) -> str:
        action_desc = "no_action"
        if decision.actions:
            action_desc = str(decision.actions[0])
        error_text = str(error_item.get("error", "unknown error"))
        return (
            f"Previous action failed: {action_desc}. "
            f"Observed error: {error_text}. "
            "Next try should adjust tool name/args and keep one atomic tool call."
        )


__all__ = ["ReActSelfReflectionCritic"]
