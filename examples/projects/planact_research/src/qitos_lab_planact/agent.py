"""Evidence-driven policy: the framework owns requests, tools and Session."""

from dataclasses import dataclass, field
import json
from typing import Any, Dict, Optional

from qitos.core.agent_module import AgentModule
from qitos.core.state import StateSchema
from qitos.core.function_tool_decorator import function_tool
from qitos.core.tool_result import ToolResult


@dataclass
class ResearchState(StateSchema):
    evidence: list[dict] = field(default_factory=list)
    plan: list[str] = field(default_factory=list)
    plan_version: int = 0
    phase: str = "execute"


class ResearchAgent(AgentModule):
    def __init__(self, *, dynamic=True, **kwargs):
        super().__init__(**kwargs)
        self.dynamic = dynamic

    def init_state(self, task, **kwargs):
        return ResearchState(
            task=task, max_steps=self.config.get("max_steps", 80), phase="plan"
        )

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
        role = (
            "Planner: use revise_plan alone to update the remaining high-level plan. "
            "Include concrete verification criteria. Do not execute an environment action this turn."
            if state.phase == "plan"
            else "Executor: ground the current plan in actual tools and observations. "
            "A tool succeeding does not by itself verify a research claim."
        )
        return (
            role
            + "\n"
            + json.dumps(
                {
                    "task": state.task,
                    "phase": state.phase,
                    "plan": state.plan,
                    "plan_version": state.plan_version,
                    "recent_results": state.evidence[-4:],
                },
                ensure_ascii=False,
            )
        )

    def reduce(self, state, observation, decision):
        planned = False
        for item in observation.action_results:
            state.evidence.append(item.to_model_dict(max_chars=6000))
            output = item.output
            if isinstance(output, dict) and "remaining_plan" in output:
                # Even multiple proposals in one batch cannot change the static
                # control after its first accepted plan. State owns acceptance.
                if not self.dynamic and state.plan_version:
                    continue
                state.plan = output["remaining_plan"]
                state.plan_version += 1
                state.phase = "execute"
                planned = True
        if not planned and decision.actions and self.dynamic:
            state.phase = "plan"
        state.evidence = state.evidence[-8:]
        return state

    # docs:end design


def build_factory(task, **resources):
    dynamic = resources.get("variant") != "static"

    @function_tool(read_only=True)
    def revise_plan(
        steps: list[str],
        evidence: str,
        runtime_context: Optional[Dict[str, Any]] = None,
    ):
        """Declare remaining high-level steps and the evidence behind this revision."""
        state = (runtime_context or {}).get("state")
        if not dynamic and getattr(state, "plan_version", 0) > 0:
            return ToolResult(
                status="error",
                error_kind="policy",
                error_code="static_plan_locked",
                error="The static control keeps its first accepted plan.",
                tool_name="revise_plan",
                recoverable=False,
            )
        if not steps or len(steps) > 12 or any(not step.strip() for step in steps):
            raise ValueError("invalid_remaining_plan")
        return {"remaining_plan": steps, "revision_evidence": evidence}

    @function_tool(read_only=True)
    def submit_report(report_json: str):
        """Submit the complete report JSON; independent evaluation runs afterwards."""
        value = json.loads(report_json)
        if not isinstance(value, dict):
            raise ValueError("report_must_be_object")
        return {"submitted_report": value}

    def factory(*, config, model, tool_registry, protocol, parser):
        tool_registry.register(submit_report)
        tool_registry.register(revise_plan)
        return ResearchAgent(
            llm=model,
            tool_registry=tool_registry,
            model_protocol=protocol.id,
            max_steps=config.max_steps,
            model_parser=parser,
            dynamic=resources.get("variant") != "static",
        )

    return factory
