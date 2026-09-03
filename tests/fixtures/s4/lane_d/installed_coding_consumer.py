"""Offline coding/tool consumer using installed public and extension APIs only."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qitos import Action, AgentModule, Decision, Engine, StateSchema, ToolRegistry, tool
from qitos.qita import ReadOnlyInspection
from qitos.tracing.journal_store import JournalTrajectoryStore
from qitos.tracing.readers import StoreTrajectoryReader
from qitos.tracing.trajectory import RecordKind, TrajectoryRecord


@dataclass
class CodingState(StateSchema):
    outputs: list[str] = field(default_factory=list)


class CodingAgent(AgentModule[CodingState, dict[str, Any], Action]):
    def __init__(self) -> None:
        registry = ToolRegistry()

        @tool(name="inspect_text")
        def inspect_text(text: str) -> dict[str, Any]:
            return {"length": len(text), "contains_agent": "agent" in text}

        registry.register(inspect_text)
        super().__init__(tool_registry=registry)

    def init_state(self, task: str, **kwargs: Any) -> CodingState:
        return CodingState(task=task, max_steps=3)

    def decide(
        self, state: CodingState, observation: dict[str, Any]
    ) -> Decision[Action]:
        if state.current_step == 0:
            return Decision.act(
                actions=[Action(name="inspect_text", args={"text": state.task})]
            )
        return Decision.final("coding consumer complete")

    def reduce(
        self,
        state: CodingState,
        observation: dict[str, Any],
        decision: Decision[Action],
    ) -> CodingState:
        state.outputs.extend(
            str(item) for item in observation.get("action_results", [])
        )
        return state


def main() -> None:
    result = Engine(CodingAgent()).session("inspect agent text").run()
    assert result.state.final_result == "coding consumer complete"
    with tempfile.TemporaryDirectory(prefix="qitos-installed-coding-") as temp:
        store = JournalTrajectoryStore(Path(temp) / "trajectory.journal")
        store.append(
            TrajectoryRecord.create(
                RecordKind.RUN,
                record_id="coding-run-record",
                run_id="coding-run",
                session_id="coding-session",
                payload={"status": "completed"},
            )
        )
        inspection = ReadOnlyInspection(StoreTrajectoryReader(store))
        assert inspection.board()[0]["run_id"] == "coding-run"
        store.close()
    print("installed_coding_consumer=passed")


if __name__ == "__main__":
    main()
