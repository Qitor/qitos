"""ReAct-style editor-integrated reference agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from qitos import Action, AgentModule, Decision, StateSchema, ToolRegistry
from qitos.kit.tool.editor import EditorToolSet


@dataclass
class ReActEditorState(StateSchema):
    target_path: str = ""
    target_content: str = ""
    stage: str = "init"  # init -> created -> viewed -> done
    last_observation: Optional[Dict[str, Any]] = None
    logs: List[str] = field(default_factory=list)


class ReActEditorAgent(AgentModule[ReActEditorState, Dict[str, Any], Action]):
    """Deterministic ReAct flow for editor operations."""

    def __init__(self, workspace_root: str):
        registry = ToolRegistry()
        registry.include(EditorToolSet(workspace_root=workspace_root))
        super().__init__(tool_registry=registry)

    def init_state(self, task: str, **kwargs: Any) -> ReActEditorState:
        path = kwargs.get("path", "react_notes.txt")
        content = kwargs.get("content", "hello from react editor")
        return ReActEditorState(task=task, target_path=path, target_content=content, max_steps=6)

    def observe(self, state: ReActEditorState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "task": state.task,
            "stage": state.stage,
            "last_observation": state.last_observation,
            "target_path": state.target_path,
        }

    def decide(self, state: ReActEditorState, observation: Dict[str, Any]) -> Decision[Action]:
        if state.stage == "done":
            return Decision.final(state.final_result or "done")

        if state.stage == "init":
            return Decision.act(
                actions=[Action(name="create", args={"path": state.target_path, "file_text": state.target_content})],
                rationale="Need to create file first",
            )

        if state.stage == "created":
            return Decision.act(
                actions=[Action(name="view", args={"path": state.target_path})],
                rationale="Verify file content",
            )

        if state.stage == "viewed":
            obs = state.last_observation or {}
            stdout = str(obs.get("stdout", ""))
            if state.target_content in stdout:
                return Decision.final(f"verified:{state.target_path}")
            return Decision.final("verification_failed")

        return Decision.final("unsupported_stage")

    def reduce(
        self,
        state: ReActEditorState,
        observation: Dict[str, Any],
        decision: Decision[Action],
        action_results: List[Any],
    ) -> ReActEditorState:
        if decision.rationale:
            state.logs.append(decision.rationale)

        if not action_results:
            return state

        first = action_results[0]
        if isinstance(first, dict):
            state.last_observation = first

        if state.stage == "init":
            state.stage = "created"
            return state

        if state.stage == "created":
            state.stage = "viewed"
            return state

        return state
