"""Critic abstraction for verifier-guided runtime loops."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from ..core.decision import Decision


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


__all__ = ["Critic"]
