"""Model-ready SWE-Agent minimal closed loop template."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from qitos import Action, AgentModule, Decision, StateSchema, ToolRegistry
from qitos.kit.parser import ReActTextParser
from qitos.kit.planning import append_log, format_action
from qitos.kit.prompts import SWE_AGENT_SYSTEM_PROMPT, render_prompt
from qitos.kit.tool.editor import EditorToolSet
from qitos.kit.tool.shell import RunCommand
from qitos.models import Model


@dataclass
class SWEState(StateSchema):
    scratchpad: List[str] = field(default_factory=list)
    file_path: str = "buggy_module.py"
    expected_snippet: str = "return a + b"
    test_command: str = ""
    phase: str = "analyze"
    last_test: Optional[Dict[str, Any]] = None


class SWEAgentMini(AgentModule[SWEState, Dict[str, Any], Action]):
    def __init__(self, llm: Model, workspace_root: str):
        registry = ToolRegistry()
        registry.include(EditorToolSet(workspace_root=workspace_root))
        registry.register(RunCommand(cwd=workspace_root))
        super().__init__(tool_registry=registry, llm=llm, model_parser=ReActTextParser())

    def init_state(self, task: str, **kwargs: Any) -> SWEState:
        return SWEState(
            task=task,
            file_path=kwargs.get("file_path", "buggy_module.py"),
            expected_snippet=kwargs.get("expected_snippet", "return a + b"),
            test_command=kwargs.get(
                "test_command",
                'python -c "import buggy_module; assert buggy_module.add(20, 22) == 42"',
            ),
            max_steps=int(kwargs.get("max_steps", 12)),
        )

    def observe(self, state: SWEState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task": state.task,
            "file_path": state.file_path,
            "phase": state.phase,
            "expected_snippet": state.expected_snippet,
            "test_command": state.test_command,
            "scratchpad": list(state.scratchpad),
            "memory": env_view.get("memory", {}),
        }

    def decide(self, state: SWEState, observation: Dict[str, Any]) -> Decision[Action]:
        return None

    def build_system_prompt(self, state: SWEState) -> str | None:
        tool_schema = self.tool_registry.get_tool_descriptions() if self.tool_registry is not None else ""
        return render_prompt(SWE_AGENT_SYSTEM_PROMPT, {"tool_schema": tool_schema})

    def prepare(self, state: SWEState, observation: Dict[str, Any]) -> str:
        lines = [
            f"Task: {state.task}",
            f"Target file: {state.file_path}",
            f"Expected patch snippet: {state.expected_snippet}",
            f"Test command: {state.test_command}",
            f"Phase: {state.phase}",
        ]
        if state.scratchpad:
            lines.append("Scratchpad:")
            lines.extend(str(x) for x in state.scratchpad[-10:])
        memory = observation.get("memory") or {}
        if isinstance(memory, dict) and memory.get("summary"):
            lines.append("Memory Summary:")
            lines.append(str(memory["summary"]))
        return "\n".join(lines)

    def reduce(
        self,
        state: SWEState,
        observation: Dict[str, Any],
        decision: Decision[Action],
        action_results: List[Any],
    ) -> SWEState:
        if decision.rationale:
            append_log(state, "scratchpad", f"Thought: {decision.rationale}", max_items=24)
        if decision.actions:
            append_log(state, "scratchpad", f"Action: {format_action(decision.actions[0])}", max_items=24)
        if action_results:
            append_log(state, "scratchpad", f"Observation: {action_results[0]}", max_items=24)
            if isinstance(action_results[0], dict) and "returncode" in action_results[0]:
                state.last_test = action_results[0]
        return state
