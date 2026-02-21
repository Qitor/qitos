"""Plan-and-Act editor-integrated reference agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from qitos import Action, AgentModule, Decision, StateSchema, ToolRegistry
from qitos.kit.tool.editor import EditorToolSet


@dataclass
class PlanActEditorState(StateSchema):
    plan_steps: List[str] = field(default_factory=list)
    cursor: int = 0
    target_path: str = "plan_act_notes.txt"
    target_content: str = "hello from plan-act editor"
    last_observation: Optional[Dict[str, Any]] = None


class PlanActEditorAgent(AgentModule[PlanActEditorState, Dict[str, Any], Action]):
    """Deterministic plan-and-act flow over editor tools."""

    def __init__(self, workspace_root: str):
        registry = ToolRegistry()
        registry.include(EditorToolSet(workspace_root=workspace_root))
        super().__init__(tool_registry=registry)

    def init_state(self, task: str, **kwargs: Any) -> PlanActEditorState:
        return PlanActEditorState(
            task=task,
            target_path=kwargs.get("path", "plan_act_notes.txt"),
            target_content=kwargs.get("content", "hello from plan-act editor"),
            max_steps=8,
        )

    def observe(self, state: PlanActEditorState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task": state.task,
            "plan_steps": list(state.plan_steps),
            "cursor": state.cursor,
            "last_observation": state.last_observation,
        }

    def decide(self, state: PlanActEditorState, observation: Dict[str, Any]) -> Decision[Action]:
        if not state.plan_steps:
            state.plan_steps = [
                "create_file",
                "view_file",
                "verify_content",
            ]
            state.plan.steps = list(state.plan_steps)
            state.plan.cursor = 0
            state.plan.status = "executing"
            return Decision.wait(rationale="Plan generated")

        if state.cursor >= len(state.plan_steps):
            return Decision.final(state.final_result or "done")

        current = state.plan_steps[state.cursor]

        if current == "create_file":
            return Decision.act(
                actions=[Action(name="create", args={"path": state.target_path, "file_text": state.target_content})],
                rationale="Execute plan step create_file",
            )

        if current == "view_file":
            return Decision.act(
                actions=[Action(name="view", args={"path": state.target_path})],
                rationale="Execute plan step view_file",
            )

        if current == "verify_content":
            obs = state.last_observation or {}
            stdout = str(obs.get("stdout", ""))
            if state.target_content in stdout:
                return Decision.final(f"verified:{state.target_path}")
            return Decision.final("verification_failed")

        return Decision.final("unsupported_plan_step")

    def reduce(
        self,
        state: PlanActEditorState,
        observation: Dict[str, Any],
        decision: Decision[Action],
        action_results: List[Any],
    ) -> PlanActEditorState:
        if decision.mode == "wait":
            return state

        if action_results:
            first = action_results[0]
            if isinstance(first, dict):
                state.last_observation = first
            state.cursor += 1
            state.plan.cursor = state.cursor
            state.plan.steps = list(state.plan_steps)

        if state.cursor >= len(state.plan_steps) and state.plan_steps:
            state.plan.status = "completed"

        return state
