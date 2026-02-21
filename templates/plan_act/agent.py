"""Plan-and-Act reference agent on top of AgentModule."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from qitos import Action, AgentModule, Decision, StateSchema, ToolRegistry, tool


@dataclass
class PlanActState(StateSchema):
    work_plan: List[Tuple[str, int, int]] = field(default_factory=list)
    plan_cursor_local: int = 0
    intermediate: Optional[int] = None
    execution_log: List[str] = field(default_factory=list)


class PlanActAgent(AgentModule[PlanActState, Dict[str, Any], Action]):
    def __init__(self):
        registry = ToolRegistry()

        class MathToolSet:
            name = "math"
            version = "1.0"

            def setup(self, context: Dict[str, Any]) -> None:
                return None

            def teardown(self, context: Dict[str, Any]) -> None:
                return None

            @tool(name="add", description="Add two integers")
            def add(self, a: int, b: int) -> int:
                return a + b

            @tool(name="multiply", description="Multiply two integers")
            def multiply(self, a: int, b: int) -> int:
                return a * b

            def tools(self) -> List[Any]:
                return [self.add, self.multiply]

        registry.register_toolset(MathToolSet(), namespace="")
        super().__init__(toolkit=registry)

    def init_state(self, task: str, **kwargs: Any) -> PlanActState:
        return PlanActState(task=task, max_steps=int(kwargs.get("max_steps", 8)))

    def observe(self, state: PlanActState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task": state.task,
            "plan": list(state.work_plan),
            "cursor": state.plan_cursor_local,
            "intermediate": state.intermediate,
        }

    def decide(self, state: PlanActState, observation: Dict[str, Any]) -> Decision[Action]:
        if not state.work_plan:
            plan = self._build_plan(state.task)
            if not plan:
                return Decision.final("unsupported task", rationale="Unable to create plan")

            state.work_plan = plan
            state.execution_log.append(f"Plan generated: {plan}")
            return Decision.wait(rationale="Plan generated")

        if state.plan_cursor_local >= len(state.work_plan):
            if state.intermediate is None:
                return Decision.final("unsupported task", rationale="No computed result")
            return Decision.final(str(state.intermediate), rationale="All planned steps complete")

        op, left, right = state.work_plan[state.plan_cursor_local]

        # If step references PREV, replace left operand by intermediate.
        a = state.intermediate if left == -999999 else left
        b = right

        if a is None:
            return Decision.final("unsupported task", rationale="Missing intermediate value")

        action_name = "add" if op == "+" else "multiply"
        return Decision.act(actions=[Action(name=action_name, args={"a": int(a), "b": int(b)})])

    def reduce(
        self,
        state: PlanActState,
        observation: Dict[str, Any],
        decision: Decision[Action],
        action_results: List[Any],
    ) -> PlanActState:
        if decision.rationale:
            state.execution_log.append(decision.rationale)

        if action_results:
            value = int(action_results[0])
            state.intermediate = value
            state.execution_log.append(f"Step {state.plan_cursor_local} -> {value}")
            state.plan_cursor_local += 1

        return state

    def _build_plan(self, task: str) -> List[Tuple[str, int, int]]:
        text = task.lower().strip()

        # supported pattern: "compute A + B then * C"
        m = re.search(r"(-?\d+)\s*\+\s*(-?\d+)\s*then\s*\*\s*(-?\d+)", text)
        if m:
            a = int(m.group(1))
            b = int(m.group(2))
            c = int(m.group(3))
            # Use sentinel -999999 to mean PREV in left operand.
            return [("+", a, b), ("*", -999999, c)]

        return []
