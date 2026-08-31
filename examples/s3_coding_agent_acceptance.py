"""Offline coding-agent acceptance over the integrated durable runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from qitos import Action, AgentModule, Decision, Engine, StateSchema, ToolRegistry
from qitos.core.session import PauseSafety, SafeBoundaryKind
from qitos.core.tool import tool
from qitos.engine.runtime import RuntimeComposition
from qitos.engine.work_runtime import DurableWorkRuntime, SchedulerHandle, WorkDispatch


@dataclass
class CodingState(StateSchema):
    summary: str = ""


class OfflineCodingAgent(AgentModule[CodingState, dict[str, Any], Action]):
    name = "offline-coder"

    def __init__(self) -> None:
        registry = ToolRegistry()

        @tool(name="inspect_module")
        def inspect_module() -> str:
            return "module inspected"

        registry.register(inspect_module)
        super().__init__(tool_registry=registry)

    def init_state(self, task: str, **kwargs: Any) -> CodingState:
        return CodingState(task=task, max_steps=3)

    def decide(self, state: CodingState, observation: dict[str, Any]) -> Decision[Action]:
        if state.current_step == 0:
            return Decision.act([Action(name="inspect_module", args={})])
        return Decision.final("offline acceptance")

    def reduce(self, state: CodingState, observation: Any, decision: Any) -> CodingState:
        state.summary = "offline acceptance"
        return state


class PauseAfterInspection:
    policy_id = "example.coding.pause_after_inspection"
    supports_pause = True

    def should_pause(self, context: Any) -> bool:
        return context.step_id == 0

    def pause_safety(self, context: Any) -> PauseSafety:
        return PauseSafety(boundary=SafeBoundaryKind.AFTER_MODEL_RESULT)


class CompletedHandle:
    worker_ref = "example:offline-worker"

    def add_terminal_callback(
        self, callback: Callable[[Any, BaseException | None], None]
    ) -> None:
        callback({"offline": True}, None)

    def request_cancel(self) -> bool:
        return True


class OfflineScheduler:
    scheduler_id = "example.offline.scheduler"

    def dispatch(self, request: WorkDispatch) -> SchedulerHandle:
        return CompletedHandle()

    def reattach(
        self, request: WorkDispatch, worker_ref: str
    ) -> SchedulerHandle | None:
        return None

    def close(self) -> None:
        return None


@dataclass(frozen=True)
class AcceptanceStatus:
    status: str
    code: str
    child_count: int


def current_status() -> AcceptanceStatus:
    runtime = RuntimeComposition(
        lifecycle_policy=PauseAfterInspection(),
        work_runtime=DurableWorkRuntime(OfflineScheduler()),
    )
    session = Engine(OfflineCodingAgent(), runtime=runtime).session("inspect one module")
    session.run()
    child = session.delegate("offline-coder", task="review the recorded summary")
    session.join([child.operation_id], policy="all")
    fresh_runtime = RuntimeComposition(
        checkpoint_store=runtime.checkpoint_store,
        resolvers=runtime.resolvers.copy(),
        lifecycle_policy=PauseAfterInspection(),
        work_runtime=DurableWorkRuntime(OfflineScheduler()),
    )
    restored = Engine.restore(session.session_id, runtime=fresh_runtime)
    restored.inspect()
    return AcceptanceStatus(
        status="completed",
        code="qualified_public_shape",
        child_count=1,
    )


if __name__ == "__main__":
    print(current_status())
