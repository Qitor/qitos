"""Critic interfaces for verifier-guided runtime loops."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from .decision import Decision


class Critic(ABC):
    @abstractmethod
    def evaluate(self, state: Any, decision: Decision[Any], results: list[Any]) -> Dict[str, Any]:
        """Return a structured critic decision dict.

        Supported keys (by convention):
        - action: "continue" | "stop" | "retry"
        - reason: str
        - score: float
        - details: dict
        """


class PassThroughCritic(Critic):
    def evaluate(self, state: Any, decision: Decision[Any], results: list[Any]) -> Dict[str, Any]:
        return {"action": "continue", "reason": "pass", "score": 1.0}


__all__ = ["Critic", "PassThroughCritic"]
