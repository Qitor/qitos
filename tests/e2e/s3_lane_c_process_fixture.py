"""Fresh-process fixture for Lane C logical scheduler restoration."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from dataclasses import dataclass
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).parents[2]))

from qitos.checkpoint import SqliteCheckpointStore
from qitos.core.action import Action
from qitos.core.agent_module import AgentModule
from qitos.core.decision import Decision
from qitos.core.session import (
    ResolverNamespace,
    ResolverReference,
    ResolverRegistry,
)
from qitos.core.state import StateSchema
from qitos.core.tool_registry import ToolRegistry
from qitos.core.tool import tool
from qitos.core.work_graph import WorkGraph
from qitos.engine import Engine
from qitos.engine.runtime import DEFAULT_CHECKPOINT_REFERENCE, RuntimeComposition
from qitos.engine.work_runtime import DurableWorkRuntime, WorkDispatch


@dataclass
class LaneCState(StateSchema):
    pass


class LaneCAgent(AgentModule[LaneCState, dict[str, Any], Action]):
    name = "lane_c_parent"

    def __init__(self) -> None:
        registry = ToolRegistry()

        @tool(name="noop")
        def noop() -> str:
            return "ok"

        registry.register(noop)
        super().__init__(tool_registry=registry)

    def init_state(self, task: str, **kwargs: Any) -> LaneCState:
        return LaneCState(task=task)

    def decide(self, state, observation):
        if state.current_step == 0:
            return Decision.act([Action(name="noop", args={})])
        return Decision.final("unused")

    def reduce(self, state, observation, decision):
        return state


LaneCState.__module__ = "s3_lane_c_process_fixture"


class Handle:
    def __init__(self, worker_ref: str) -> None:
        self.worker_ref = worker_ref
        self.callback: Callable[[Any, BaseException | None], None] | None = None

    def add_terminal_callback(self, callback) -> None:
        self.callback = callback

    def request_cancel(self) -> bool:
        return False

    def finish(self) -> None:
        assert self.callback is not None
        self.callback({"ok": True}, None)


class Scheduler:
    scheduler_id = "tests.clean_process"

    def __init__(self) -> None:
        self.handles: dict[str, Handle] = {}
        self.dispatch_count = 0

    def dispatch(self, request: WorkDispatch) -> Handle:
        self.dispatch_count += 1
        handle = Handle(f"process:{request.operation_id}")
        self.handles[handle.worker_ref] = handle
        return handle

    def reattach(self, request: WorkDispatch, worker_ref: str):
        del request
        return self.handles.get(worker_ref)

    def close(self) -> None:
        pass


class PauseFirst:
    policy_id = "tests.clean_process.pause_first"
    supports_pause = True

    def should_pause(self, context) -> bool:
        return context.step_id == 0

    def pause_safety(self, context):
        from qitos.core.session import PauseSafety, SafeBoundaryKind

        return PauseSafety(boundary=SafeBoundaryKind.AFTER_MODEL_RESULT)


def create() -> None:
    store = SqliteCheckpointStore(os.environ["QITOS_S3_C_DB"])
    scheduler = Scheduler()
    runtime = RuntimeComposition(
        checkpoint_store=store,
        lifecycle_policy=PauseFirst(),
        work_runtime=DurableWorkRuntime(scheduler),
    )
    session = Engine(LaneCAgent(), runtime=runtime).session("lane c process loss")
    session.run()
    completed = session.spawn("lane_c_parent", task="completed", operation_id="spawn:completed")
    scheduler.handles[completed.worker_ref].finish()
    session.spawn("lane_c_parent", task="missing", operation_id="spawn:missing")
    session.spawn("lane_c_parent", task="unknown", operation_id="spawn:unknown")
    graph = WorkGraph.from_canonical_dict(session.inspect().work_graph or {})
    # A different scheduler instance cannot reattach the third logical worker.
    DurableWorkRuntime(Scheduler()).recover(
        graph, persist=lambda: session._commit_work_graph_value(graph)
    )
    # Keep the second receipt dispatched to exercise clean-process recovery.
    graph.operation_receipts[1] = graph.operation_receipts[1].__class__(
        **{**graph.operation_receipts[1].__dict__, "state": "dispatched", "outcome_unknown": False}
    )
    session._commit_work_graph_value(graph)
    print(json.dumps({"session_id": session.session_id.value}))
    store.close()


def restore() -> None:
    store = SqliteCheckpointStore(os.environ["QITOS_S3_C_DB"])
    session_id = os.environ["QITOS_S3_C_SESSION"]
    head = store.get_session_head(session_id)
    assert head is not None
    snapshot = store.get_session_snapshot(head.snapshot_id)
    assert snapshot is not None
    agent = LaneCAgent()
    registry = ResolverRegistry()
    registry.register_resource(DEFAULT_CHECKPOINT_REFERENCE, store)
    for raw in snapshot.payload["resolver_references"]:
        reference = ResolverReference.from_dict(raw)
        if reference.namespace is ResolverNamespace.AGENT:
            registry.register_resource(reference, agent)
        elif reference.namespace is ResolverNamespace.TOOL_REGISTRY:
            registry.register_resource(reference, agent.tool_registry)
    scheduler = Scheduler()
    runtime = RuntimeComposition(
        checkpoint_store=store,
        resolvers=registry,
        work_runtime=DurableWorkRuntime(scheduler),
    )
    session = Engine.restore(session_id, runtime=runtime)
    session.recover_work()
    graph = WorkGraph.from_canonical_dict(session.inspect().work_graph or {})
    print(json.dumps({
        "states": {item.operation_id: item.state for item in graph.operation_receipts},
        "unknown": {item.operation_id: item.outcome_unknown for item in graph.operation_receipts},
        "dispatch_count": scheduler.dispatch_count,
    }, sort_keys=True))
    store.close()


if __name__ == "__main__":
    {"create": create, "restore": restore}[os.environ["QITOS_S3_C_PHASE"]]()
