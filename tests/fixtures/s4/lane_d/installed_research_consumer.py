"""Offline research/tool consumer with fake provider and evaluator extension."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qitos import AgentModule, Decision, Engine, ModelResponse, StateSchema, ToolRegistry
from qitos.core.task import Task
from qitos.evaluate import (
    EvaluationContext,
    EvaluationResult,
    EvaluatorRegistry,
    TrajectoryEvaluator,
)
from qitos.tracing.trajectory import RecordKind, Trajectory, TrajectoryRecord


class FakeProvider:
    model = "offline-fake-provider"

    def __call__(self, messages: list[dict[str, Any]]) -> str:
        assert messages
        return "offline research result"


@dataclass
class ResearchState(StateSchema):
    provider_text: str = ""


class ResearchAgent(AgentModule[ResearchState, dict[str, Any], dict[str, Any]]):
    def __init__(self) -> None:
        super().__init__(tool_registry=ToolRegistry(), llm=FakeProvider())

    def init_state(self, task: str, **kwargs: Any) -> ResearchState:
        return ResearchState(task=task, max_steps=2)

    def interpret_model_response(
        self,
        state: ResearchState,
        observation: dict[str, Any],
        response: ModelResponse,
    ) -> Decision[dict[str, Any]]:
        state.provider_text = response.text
        return Decision.final(response.text)

    def reduce(
        self,
        state: ResearchState,
        observation: dict[str, Any],
        decision: Decision[dict[str, Any]],
    ) -> ResearchState:
        return state


class StopEvaluator(TrajectoryEvaluator):
    name = "consumer.stop"

    def evaluate(self, context: EvaluationContext) -> EvaluationResult:
        assert context.view is not None
        success = any(record.kind == RecordKind.STOP for record in context.view.records)
        return EvaluationResult(name=self.name, success=success, score=float(success))


def main() -> None:
    result = Engine(ResearchAgent()).session("summarize offline evidence").run()
    assert result.state.final_result == "offline research result"
    view = Trajectory(
        records=(
            TrajectoryRecord.create(
                RecordKind.STOP,
                record_id="research-stop",
                run_id="research-run",
                payload={"reason": "final"},
            ).with_sequence(0),
        )
    )
    evaluated = EvaluatorRegistry([StopEvaluator()]).evaluate(
        "consumer.stop",
        EvaluationContext(
            task=Task(id="research", objective="evaluate"),
            view=view,
        ),
    )
    assert evaluated.success
    print("installed_research_consumer=passed")


if __name__ == "__main__":
    main()
