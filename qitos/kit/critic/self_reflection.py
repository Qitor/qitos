"""Self-reflection style critic."""

from __future__ import annotations

from typing import Any, Dict

from qitos.core.decision import Decision
from qitos.engine.critic import Critic


class SelfReflectionCritic(Critic):
    def __init__(self, max_retries: int = 2):
        self.max_retries = max_retries

    def evaluate(self, state: Any, decision: Decision[Any], results: list[Any]) -> Dict[str, Any]:
        metadata = getattr(state, "metadata", {}) or {}
        retries = int(metadata.get("reflection_retries", 0))

        has_error = any(isinstance(r, dict) and r.get("error") for r in results)
        if has_error and retries < self.max_retries:
            metadata["reflection_retries"] = retries + 1
            state.metadata = metadata
            return {
                "action": "retry",
                "reason": "tool_error_retry",
                "score": 0.2,
                "details": {"retries": retries + 1, "max_retries": self.max_retries},
            }

        if has_error:
            return {
                "action": "stop",
                "reason": "tool_error_exceeded_retries",
                "score": 0.0,
            }

        return {"action": "continue", "reason": "reflection_pass", "score": 1.0}


__all__ = ["SelfReflectionCritic"]
