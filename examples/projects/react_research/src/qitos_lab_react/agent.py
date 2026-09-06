"""Evidence-driven policy: the framework owns requests, tools and Session."""

from dataclasses import dataclass, field
import json

from qitos.core.agent_module import AgentModule
from qitos.core.state import StateSchema
from qitos.core.function_tool_decorator import function_tool


@dataclass
class ResearchState(StateSchema):
    evidence: list[dict] = field(default_factory=list)
    plan: list[str] = field(default_factory=list)
    plan_version: int = 0
    phase: str = "execute"


class ResearchAgent(AgentModule):
    def init_state(self, task, **kwargs):
        return ResearchState(task=task, max_steps=self.config.get("max_steps", 80))

    def base_persona_prompt(self, state):
        return (
            "You are an evidence-driven research agent. Inspect the actual input files. "
            "Distinguish preliminary claims from verified evidence. Do calculations "
            "with tools. Correct mistaken assumptions when observations disagree."
        )

    def task_policy_prompt(self, state):
        return (
            "Produce report.json containing conclusion (string), metrics (object of numbers), "
            "citations (list of exact input filenames), and limitations (list of strings). "
            "Cite at least three relevant sources. Read before concluding. Use submit_report "
            "to submit the full JSON as a string, then give a concise final answer. "
            "Do not claim evidence that you did not inspect."
        )

    # docs:start design
    def prepare(self, state):
        return json.dumps(
            {
                "task": state.task,
                "phase": state.phase,
                "plan": state.plan,
                "plan_version": state.plan_version,
                "recent_results": state.evidence[-4:],
            },
            ensure_ascii=False,
        )

    def reduce(self, state, observation, decision):
        for item in observation.action_results:
            state.evidence.append(item.to_model_dict(max_chars=6000))
        state.evidence = state.evidence[-8:]
        return state

    # docs:end design


def build_factory(task, **resources):
    @function_tool(read_only=True)
    def submit_report(report_json: str):
        """Submit the complete report JSON; independent evaluation runs afterwards."""
        value = json.loads(report_json)
        if not isinstance(value, dict):
            raise ValueError("report_must_be_object")
        return {"submitted_report": value}

    def factory(*, config, model, tool_registry, protocol, parser):
        tool_registry.register(submit_report)
        return ResearchAgent(
            llm=model,
            tool_registry=tool_registry,
            model_protocol=protocol.id,
            max_steps=config.max_steps,
            model_parser=parser,
        )

    return factory
