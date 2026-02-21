"""Voyager-style deterministic agent with reflection and skill library."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from qitos import Action, AgentModule, Decision, StateSchema, ToolRegistry, tool
from qitos.skills.library import InMemorySkillLibrary, SkillArtifact


@dataclass
class VoyagerState(StateSchema):
    reflection_log: List[str] = field(default_factory=list)
    used_skills: List[str] = field(default_factory=list)
    last_result: Optional[int] = None


class VoyagerAgent(AgentModule[VoyagerState, Dict[str, Any], Action]):
    def __init__(self, skill_library: Optional[InMemorySkillLibrary] = None):
        registry = ToolRegistry()

        @tool(name="add")
        def add(a: int, b: int) -> int:
            return a + b

        @tool(name="multiply")
        def multiply(a: int, b: int) -> int:
            return a * b

        registry.register(add)
        registry.register(multiply)

        super().__init__(toolkit=registry)
        self.skill_library = skill_library or InMemorySkillLibrary()

    def init_state(self, task: str, **kwargs: Any) -> VoyagerState:
        return VoyagerState(task=task, max_steps=4)

    def observe(self, state: VoyagerState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        retrieved = self.skill_library.search("add", top_k=3) + self.skill_library.search("multiply", top_k=3)
        return {
            "task": state.task,
            "step": state.current_step,
            "available_skills": [s.name for s in retrieved],
            "reflection_log": list(state.reflection_log),
        }

    def decide(self, state: VoyagerState, observation: Dict[str, Any]) -> Decision[Action]:
        if state.last_result is not None:
            return Decision.final(str(state.last_result), rationale="Tool result ready")

        parsed = self._parse_task(state.task)
        if parsed is None:
            return Decision.final("unsupported task", rationale="No parse")

        op, a, b = parsed
        if op == "+":
            chosen = self.skill_library.get("skill_add")
            if chosen:
                state.used_skills.append(chosen.name)
            return Decision.act(actions=[Action(name="add", args={"a": a, "b": b})], rationale="Execute add skill")

        chosen = self.skill_library.get("skill_multiply")
        if chosen:
            state.used_skills.append(chosen.name)
        return Decision.act(actions=[Action(name="multiply", args={"a": a, "b": b})], rationale="Execute multiply skill")

    def reduce(
        self,
        state: VoyagerState,
        observation: Dict[str, Any],
        decision: Decision[Action],
        action_results: List[Any],
    ) -> VoyagerState:
        if action_results:
            state.last_result = int(action_results[0])

            reflection = self._reflect(state.task, state.last_result)
            state.reflection_log.append(reflection)

            if "+" in state.task:
                artifact = SkillArtifact(
                    name="skill_add",
                    description="Use add tool for addition tasks",
                    summary="Addition skill",
                    source=reflection,
                    tags=["math", "add"],
                )
            else:
                artifact = SkillArtifact(
                    name="skill_multiply",
                    description="Use multiply tool for multiplication tasks",
                    summary="Multiplication skill",
                    source=reflection,
                    tags=["math", "multiply"],
                )

            self.skill_library.add_or_update(artifact)

        return state

    def _reflect(self, task: str, result: int) -> str:
        return f"Task '{task}' solved with result {result}. Reuse corresponding math tool next time."

    def _parse_task(self, task: str) -> Optional[tuple[str, int, int]]:
        m = re.search(r"(-?\d+)\s*([+*])\s*(-?\d+)", task)
        if not m:
            return None
        return m.group(2), int(m.group(1)), int(m.group(3))
