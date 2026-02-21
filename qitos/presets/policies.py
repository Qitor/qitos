"""Policy presets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from qitos import Action, Decision, Policy


@dataclass
class ArithmeticState:
    task: str
    current_step: int = 0
    final_result: Optional[str] = None
    stop_reason: Optional[str] = None


class ReActArithmeticPolicy(Policy[ArithmeticState, Dict[str, Any], Action]):
    def propose(self, state: ArithmeticState, obs: Dict[str, Any]) -> Decision[Action]:
        if state.final_result is not None:
            return Decision.final(state.final_result)
        if state.current_step == 0:
            return Decision.act([Action(name="add", args={"a": 40, "b": 2})], rationale="preset react")
        return Decision.final(str(state.final_result or "42"))

    def update(
        self,
        state: ArithmeticState,
        obs: Dict[str, Any],
        decision: Decision[Action],
        results: list[Any],
    ) -> ArithmeticState:
        if results:
            state.final_result = str(results[0])
        return state


__all__ = ["ArithmeticState", "ReActArithmeticPolicy"]
