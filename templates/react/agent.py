"""ReAct-style reference agent on top of AgentModule."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from qitos import Action, AgentModule, Decision, StateSchema, ToolRegistry, tool


@dataclass
class ReActState(StateSchema):
    scratchpad: List[str] = field(default_factory=list)
    pending_action: Optional[Action] = None
    last_tool_result: Optional[Any] = None


class ReActAgent(AgentModule[ReActState, Dict[str, Any], Action]):
    """Deterministic ReAct baseline for arithmetic tasks."""

    def __init__(self):
        registry = ToolRegistry()

        @tool(name="add", description="Add two integers")
        def add(a: int, b: int) -> int:
            return a + b

        @tool(name="multiply", description="Multiply two integers")
        def multiply(a: int, b: int) -> int:
            return a * b

        registry.register(add)
        registry.register(multiply)

        super().__init__(toolkit=registry)

    def init_state(self, task: str, **kwargs: Any) -> ReActState:
        return ReActState(task=task, max_steps=int(kwargs.get("max_steps", 6)))

    def observe(self, state: ReActState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task": state.task,
            "scratchpad": list(state.scratchpad),
            "step": state.current_step,
            "last_tool_result": state.last_tool_result,
        }

    def decide(self, state: ReActState, observation: Dict[str, Any]) -> Decision[Action]:
        if state.last_tool_result is not None:
            return Decision.final(str(state.last_tool_result), rationale="Tool output available")

        parsed = self._parse_task(state.task)
        if parsed is None:
            return Decision.final("unsupported task", rationale="No parseable arithmetic expression")

        op, a, b = parsed
        if op == "+":
            action = Action(name="add", args={"a": a, "b": b}, classification="math")
        else:
            action = Action(name="multiply", args={"a": a, "b": b}, classification="math")

        return Decision.act(actions=[action], rationale=f"Need tool call for {a} {op} {b}")

    def reduce(
        self,
        state: ReActState,
        observation: Dict[str, Any],
        decision: Decision[Action],
        action_results: List[Any],
    ) -> ReActState:
        if decision.rationale:
            state.scratchpad.append(f"Thought: {decision.rationale}")
        if decision.actions:
            for action in decision.actions:
                state.scratchpad.append(f"Action: {action.name}({action.args})")
        if action_results:
            state.last_tool_result = action_results[0]
            state.scratchpad.append(f"Observation: {action_results[0]}")
        return state

    def _parse_task(self, task: str) -> Optional[tuple[str, int, int]]:
        text = task.lower().strip()

        # supported: "compute 2 + 3", "compute 7 * 8"
        match = re.search(r"(-?\d+)\s*([+*])\s*(-?\d+)", text)
        if match:
            a = int(match.group(1))
            op = match.group(2)
            b = int(match.group(3))
            return op, a, b

        return None
