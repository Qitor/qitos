"""Minimal multimodal/toolset-ready example agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from qitos import Action, AgentModule, Decision, StateSchema, ToolRegistry, tool


@dataclass
class MultimodalState(StateSchema):
    image_uri: Optional[str] = None


class VisionToolSet:
    name = "vision"
    version = "0.1"

    def __init__(self, default_caption: str = "A placeholder caption"):
        self.default_caption = default_caption

    def setup(self, context: Dict[str, Any]) -> None:
        return None

    def teardown(self, context: Dict[str, Any]) -> None:
        return None

    @tool(name="caption")
    def caption(self, image_uri: str) -> str:
        return f"{self.default_caption}: {image_uri}"

    def tools(self) -> List[Any]:
        return [self.caption]


class MultimodalToolSetAgent(AgentModule[MultimodalState, Dict[str, Any], Action]):
    def __init__(self):
        registry = ToolRegistry()
        registry.register_toolset(VisionToolSet())
        super().__init__(toolkit=registry)

    def init_state(self, task: str, **kwargs: Any) -> MultimodalState:
        return MultimodalState(task=task, image_uri=kwargs.get("image_uri"))

    def observe(self, state: MultimodalState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        return {"task": state.task, "image_uri": state.image_uri}

    def decide(self, state: MultimodalState, observation: Dict[str, Any]) -> Decision[Action]:
        if state.image_uri and state.current_step == 0:
            return Decision.act([Action(name="vision.caption", args={"image_uri": state.image_uri})])
        return Decision.final("done")

    def reduce(
        self,
        state: MultimodalState,
        observation: Dict[str, Any],
        decision: Decision[Action],
        action_results: List[Any],
    ) -> MultimodalState:
        if action_results:
            state.final_result = str(action_results[0])
        return state
