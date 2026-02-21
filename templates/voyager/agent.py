"""Model-ready Voyager-style template with reflection + tool library."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from qitos import Action, AgentModule, Decision, StateSchema, ToolRegistry, tool
from qitos.kit.parser import ReActTextParser
from qitos.kit.planning import append_log, format_action
from qitos.kit.prompts import VOYAGER_SYSTEM_PROMPT, render_prompt
from qitos.kit.tool.library import InMemoryToolLibrary, ToolArtifact
from qitos.models import Model


@dataclass
class VoyagerState(StateSchema):
    scratchpad: List[str] = field(default_factory=list)
    reflection_log: List[str] = field(default_factory=list)
    used_tools: List[str] = field(default_factory=list)


class VoyagerAgent(AgentModule[VoyagerState, Dict[str, Any], Action]):
    def __init__(self, llm: Model, tool_library: Optional[InMemoryToolLibrary] = None):
        registry = ToolRegistry()

        @tool(name="add")
        def add(a: int, b: int) -> int:
            return a + b

        @tool(name="multiply")
        def multiply(a: int, b: int) -> int:
            return a * b

        registry.register(add)
        registry.register(multiply)

        super().__init__(tool_registry=registry, llm=llm, model_parser=ReActTextParser())
        self.tool_library = tool_library or InMemoryToolLibrary()

    def init_state(self, task: str, **kwargs: Any) -> VoyagerState:
        return VoyagerState(task=task, max_steps=int(kwargs.get("max_steps", 8)))

    def observe(self, state: VoyagerState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        retrieved = self.tool_library.search("math", top_k=3)
        return {
            "task": state.task,
            "step": state.current_step,
            "retrieved_tools": [a.name for a in retrieved],
            "scratchpad": list(state.scratchpad),
            "reflection_log": list(state.reflection_log),
            "memory": env_view.get("memory", {}),
        }

    def decide(self, state: VoyagerState, observation: Dict[str, Any]) -> Decision[Action]:
        return None

    def build_system_prompt(self, state: VoyagerState) -> str | None:
        tool_schema = self.tool_registry.get_tool_descriptions() if self.tool_registry is not None else ""
        return render_prompt(VOYAGER_SYSTEM_PROMPT, {"tool_schema": tool_schema})

    def prepare(self, state: VoyagerState, observation: Dict[str, Any]) -> str:
        lines = [f"Task: {state.task}", f"Step: {state.current_step}"]
        retrieved = observation.get("retrieved_tools") or []
        if retrieved:
            lines.append(f"Retrieved Tools: {retrieved}")
        if state.reflection_log:
            lines.append("Recent Reflections:")
            lines.extend(str(x) for x in state.reflection_log[-5:])
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
        state: VoyagerState,
        observation: Dict[str, Any],
        decision: Decision[Action],
        action_results: List[Any],
    ) -> VoyagerState:
        if decision.rationale:
            append_log(state, "scratchpad", f"Thought: {decision.rationale}", max_items=24)
        if decision.actions:
            action_repr = format_action(decision.actions[0])
            append_log(state, "scratchpad", f"Action: {action_repr}", max_items=24)
            state.used_tools.append(action_repr)
        if action_results:
            append_log(state, "scratchpad", f"Observation: {action_results[0]}", max_items=24)
            reflection = f"Task '{state.task}' got observation '{action_results[0]}'"
            state.reflection_log.append(reflection)
            self.tool_library.add_or_update(
                ToolArtifact(
                    name=f"memory_{state.current_step}",
                    description="Episode reflection",
                    source=reflection,
                    summary="tool usage reflection",
                    tags=["math", "reflection"],
                )
            )
        return state
