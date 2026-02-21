"""Pass-through critic implementation."""

from __future__ import annotations

from typing import Any, Dict

from qitos.core.decision import Decision
from qitos.engine.critic import Critic


class PassThroughCritic(Critic):
    def evaluate(self, state: Any, decision: Decision[Any], results: list[Any]) -> Dict[str, Any]:
        return {"action": "continue", "reason": "pass", "score": 1.0}


__all__ = ["PassThroughCritic"]
