"""A small replaceable coding policy, not a second agent execution loop."""

from dataclasses import dataclass, field
import json

from qitos.core.agent_module import AgentModule
from qitos.core.state import StateSchema
from qitos.kit.toolset.env_coding import read_file, write_file, edit_file, run_command
from .extension import verification_tools


@dataclass
class CodingState(StateSchema):
    observations: list[dict] = field(default_factory=list)


class CodingAgent(AgentModule):
    def init_state(self, task, **kwargs):
        return CodingState(task=task, max_steps=self.config.get("max_steps", 80))

    def base_persona_prompt(self, state):
        return (
            "Inspect, change and test a real multi-file project. Use the four native "
            "read/write/edit/command tools; do not invent a framework executor. "
            "Read AGENTS.md first. Commands run only in the configured Docker Env."
        )

    def task_policy_prompt(self, state):
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
        state.observations.extend(
            item.to_model_dict(max_chars=6000) for item in observation.action_results
        )
        state.observations = state.observations[-8:]
        return state

    # docs:end design


def build_factory(task, **resources):
    def factory(*, config, model, tool_registry, protocol, parser):
        for tool in (
            read_file,
            write_file,
            edit_file,
            run_command,
            *verification_tools(task),
        ):
            tool_registry.register(tool)
        return CodingAgent(
            llm=model,
            tool_registry=tool_registry,
            model_protocol=protocol.id,
            max_steps=config.max_steps,
            model_parser=parser,
        )

    return factory
