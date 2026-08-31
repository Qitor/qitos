"""S3 coding-agent DX acceptance shape; blocked until the durable runtime lands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from qitos import AgentModule, Engine, StateSchema


@dataclass
class CodingState(StateSchema):
    summary: str = ""


class OfflineCodingAgent(AgentModule[CodingState, dict[str, Any], dict[str, Any]]):
    """Tiny offline agent used only to type-check the framework acceptance path."""

    def init_state(self, task: str, **kwargs: Any) -> CodingState:
        return CodingState(task=task, max_steps=1)

    def prepare(self, state: CodingState) -> str:
        return state.task

    def reduce(self, state: CodingState, observation: Any, decision: Any) -> CodingState:
        state.summary = "offline acceptance"
        return state


@dataclass(frozen=True)
class AcceptanceStatus:
    status: str
    code: str
    remediation: str


def exercise_public_shape(
    engine_factory: Callable[[AgentModule[Any, Any, Any]], Engine[Any, Any, Any]],
) -> AcceptanceStatus:
    """Exercise the intended public shape once C supplies delegate and join."""
    agent = OfflineCodingAgent()
    engine = engine_factory(agent)
    session = engine.session("inspect one module")

    required = ("delegate", "join")
    if any(not callable(getattr(session, name, None)) for name in required):
        return AcceptanceStatus(
            status="waiting_on_lane_a_b_c",
            code="runtime_not_ready",
            remediation="run after the qualified durable Session runtime is integrated",
        )

    session.run()
    pause = session.pause()
    pause.require_persisted()

    # A new composition root represents a fresh process. It resolves the same
    # durable checkpoint store through caller-owned configuration.
    fresh_engine = engine_factory(agent)
    restored = fresh_engine.restore(session.session_id)
    child = restored.delegate(agent, task="review the recorded summary")
    outcomes = restored.join([child])

    inspection = restored.inspect()
    if not outcomes or inspection.head.session_id != session.session_id:
        return AcceptanceStatus(
            status="blocked",
            code="acceptance_invariant_failed",
            remediation="inspect the durable runtime receipts",
        )
    return AcceptanceStatus(
        status="completed",
        code="qualified_public_shape",
        remediation="none",
    )


def current_status() -> AcceptanceStatus:
    """Do not construct a fake runtime when Lane C has not qualified."""
    return AcceptanceStatus(
        status="waiting_on_lane_a_b_c",
        code="runtime_not_ready",
        remediation="supply the exact Lane A/B/C producer bundle",
    )


if __name__ == "__main__":
    print(current_status())
