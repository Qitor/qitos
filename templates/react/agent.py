"""Model-ready ReAct template on top of AgentModule."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from qitos import Action, AgentModule, Decision, StateSchema, ToolRegistry, tool
from qitos.kit.parser import ReActTextParser
from qitos.kit.planning import append_log, format_action
from qitos.kit.prompts import REACT_SYSTEM_PROMPT, render_prompt
from qitos.models import Model


@dataclass
class ReActState(StateSchema):
    scratchpad: List[str] = field(default_factory=list)


class ReActAgent(AgentModule[ReActState, Dict[str, Any], Action]):
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

    def init_state(self, task: str, **kwargs: Any) -> ReActState:
        return ReActState(task=task, max_steps=int(kwargs.get("max_steps", 8)))

    def observe(self, state: ReActState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task": state.task,
            "step": state.current_step,
            "scratchpad": list(state.scratchpad),
            "memory": env_view.get("memory", {}),
        }

    def decide(self, state: ReActState, observation: Dict[str, Any]) -> Decision[Action]:
        return None

    def build_system_prompt(self, state: ReActState) -> str | None:
        tool_schema = self.tool_registry.get_tool_descriptions() if self.tool_registry is not None else ""
        return render_prompt(REACT_SYSTEM_PROMPT, {"tool_schema": tool_schema})

    def prepare(self, state: ReActState, observation: Dict[str, Any]) -> str:
        lines = [f"Task: {observation.get('task', '')}", f"Step: {observation.get('step', 0)}"]
        scratchpad = observation.get("scratchpad") or []
        if scratchpad:
            lines.append("Scratchpad:")
            lines.extend(str(x) for x in scratchpad[-8:])
        memory = observation.get("memory") or {}
        if isinstance(memory, dict):
            summary = memory.get("summary", "")
            if summary:
                lines.append("Memory Summary:")
                lines.append(str(summary))
        return "\n".join(lines)

    def reduce(
        self,
        state: ReActState,
        observation: Dict[str, Any],
        decision: Decision[Action],
        action_results: List[Any],
    ) -> ReActState:
        if decision.rationale:
            append_log(state, "scratchpad", f"Thought: {decision.rationale}", max_items=16)
        if decision.actions:
            for action in decision.actions:
                append_log(state, "scratchpad", f"Action: {format_action(action)}", max_items=16)
        if action_results:
            append_log(state, "scratchpad", f"Observation: {action_results[0]}", max_items=16)
        return state
