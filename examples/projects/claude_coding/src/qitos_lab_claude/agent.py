"""A small replaceable coding policy, not a second agent execution loop."""

from dataclasses import dataclass, field
import json

from qitos.core.agent_module import AgentModule
from qitos.core.state import StateSchema
from qitos.core.function_tool_decorator import function_tool
from qitos.core.decision import Decision
from qitos.kit.toolset.env_coding import read_file, write_file, edit_file, run_command
from .extension import verification_tools


@dataclass
class CodingState(StateSchema):
    observations: list[dict] = field(default_factory=list)
    verified: bool = False
    review: dict | None = None


class CodingAgent(AgentModule):
    def __init__(self, *, reviewer=False, **kwargs):
        super().__init__(**kwargs)
        self.reviewer = reviewer

    def init_state(self, task, **kwargs):
        return CodingState(task=task, max_steps=self.config.get("max_steps", 80))

    def base_persona_prompt(self, state):
        if self.reviewer:
            return (
                "You are an independent reviewer in an isolated child Session. Read the changed "
                "source, independently run verify_project, identify concrete defects or missing "
                "coverage, then call submit_review. Do not modify the project. Your conclusion "
                "is advice, not authority to mutate the parent workspace."
            )
        return (
            "Inspect, change and test a real multi-file project. Use the four native "
            "read/write/edit/command tools; do not invent a framework executor. "
            "Read AGENTS.md first. Commands run only in the configured Docker Env."
        )

    def task_policy_prompt(self, state):
        if self.reviewer:
            return "Read every changed module; submit_review with findings and limitations; finish."
        return (
            "Use the installed verify_project extension for independent checks. "
            "A successful shell exit alone is not project completion. If checks fail, "
            "inspect their evidence and correct the cause. Do not edit tests to pass. "
            "After verify_project passes, make no further edits and give a final answer."
        )

    # docs:start design
    def prepare(self, state):
        return json.dumps(
            {"task": state.task, "recent_results": state.observations[-4:]}
        )

    def reduce(self, state, observation, decision):
        for item in observation.action_results:
            output = item.output
            if isinstance(output, dict) and output.get("verified") is True:
                state.verified = True
            if isinstance(output, dict) and "review" in output:
                state.review = output["review"]
            elif item.tool_name in {"write_file", "edit_file", "run_command"}:
                state.verified = False
        state.observations.extend(
            item.to_model_dict(max_chars=6000) for item in observation.action_results
        )
        state.observations = state.observations[-8:]
        return state

    def decide(self, state, observation):
        # Finish through the normal Engine decision boundary with a typed payload.
        if self.reviewer and state.review is not None and state.verified:
            return Decision.final(json.dumps({"review": state.review}))
        return None

    # docs:end design


def build_factory(task, **resources):
    reviewer = resources.get("reviewer", False)

    @function_tool(read_only=True)
    def submit_review(findings: list[str], limitations: list[str]):
        """Return a review to the parent; no parent filesystem authority is granted."""
        return {"review": {"findings": findings, "limitations": limitations}}

    def factory(*, config, model, tool_registry, protocol, parser):
        base = (
            (read_file,)
            if reviewer
            else (read_file, write_file, edit_file, run_command)
        )
        for tool in (*base, *verification_tools(task), submit_review):
            tool_registry.register(tool)
        return CodingAgent(
            llm=model,
            tool_registry=tool_registry,
            model_protocol=protocol.id,
            max_steps=config.max_steps,
            model_parser=parser,
            reviewer=reviewer,
        )

    return factory
