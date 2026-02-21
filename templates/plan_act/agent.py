"""Model-ready PlanAct template on top of AgentModule."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from qitos import Action, AgentModule, Decision, StateSchema, ToolRegistry, tool
from qitos.kit.parser import ReActTextParser
from qitos.kit.planning import PlanCursor, append_log, format_action, parse_numbered_plan, set_final
from qitos.kit.prompts import PLAN_DRAFT_PROMPT, PLAN_EXEC_SYSTEM_PROMPT, render_prompt
from qitos.models import Model


@dataclass
class PlanActState(StateSchema):
    plan_steps: List[str] = field(default_factory=list)
    plan_cursor_local: int = 0
    scratchpad: List[str] = field(default_factory=list)


class PlanActAgent(AgentModule[PlanActState, Dict[str, Any], Action]):
    def __init__(self, llm: Model):
        registry = ToolRegistry()

        @tool(name="add", description="Add two integers")
        def add(a: int, b: int) -> int:
            return a + b

        @tool(name="multiply", description="Multiply two integers")
        def multiply(a: int, b: int) -> int:
            return a * b

        registry.register(add)
        registry.register(multiply)

        super().__init__(tool_registry=registry, llm=llm, model_parser=ReActTextParser())
        self.cursor = PlanCursor(plan_field="plan_steps", cursor_field="plan_cursor_local")

    def init_state(self, task: str, **kwargs: Any) -> PlanActState:
        return PlanActState(task=task, max_steps=int(kwargs.get("max_steps", 10)))

    def observe(self, state: PlanActState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task": state.task,
            "plan_steps": list(state.plan_steps),
            "plan_cursor": state.plan_cursor_local,
            "scratchpad": list(state.scratchpad),
            "memory": env_view.get("memory", {}),
        }

    def decide(self, state: PlanActState, observation: Dict[str, Any]) -> Decision[Action]:
        if not state.plan_steps:
            raw = self.llm([
                {"role": "system", "content": "You are a strict planner. Return numbered plan only."},
                {"role": "user", "content": render_prompt(PLAN_DRAFT_PROMPT, {"task": state.task})},
            ])
            steps = parse_numbered_plan(str(raw))
            if not steps:
                return Decision.final("failed_to_plan")
            self.cursor.init(state, steps)
            append_log(state, "scratchpad", f"Plan: {steps}", max_items=16)
            return Decision.wait(rationale="plan ready")

        current = self.cursor.current(state)
        if current is None:
            return Decision.final(state.final_result or "done")

        return None

    def build_system_prompt(self, state: PlanActState) -> str | None:
        tool_schema = self.tool_registry.get_tool_descriptions() if self.tool_registry is not None else ""
        return render_prompt(PLAN_EXEC_SYSTEM_PROMPT, {"tool_schema": tool_schema})

    def prepare(self, state: PlanActState, observation: Dict[str, Any]) -> str:
        current = self.cursor.current(state)
        lines = [
            f"Task: {state.task}",
            f"Current Plan Step: {current or 'none'}",
            f"Plan Cursor: {state.plan_cursor_local}",
        ]
        if state.scratchpad:
            lines.append("Scratchpad:")
            lines.extend(str(x) for x in state.scratchpad[-8:])
        memory = observation.get("memory") or {}
        if isinstance(memory, dict) and memory.get("summary"):
            lines.append("Memory Summary:")
            lines.append(str(memory["summary"]))
        return "\n".join(lines)

    def reduce(
        self,
        state: PlanActState,
        observation: Dict[str, Any],
        decision: Decision[Action],
        action_results: List[Any],
    ) -> PlanActState:
        if decision.rationale:
            append_log(state, "scratchpad", f"Thought: {decision.rationale}", max_items=16)
        if decision.actions:
            append_log(state, "scratchpad", f"Action: {format_action(decision.actions[0])}", max_items=16)
        if action_results:
            append_log(state, "scratchpad", f"Observation: {action_results[0]}", max_items=16)
            set_final(state, str(action_results[0]))
            self.cursor.advance(state)
        return state
