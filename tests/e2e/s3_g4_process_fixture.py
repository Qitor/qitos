"""Deterministic create/crash/restore fixture for the S3 G4 gate."""

from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import threading
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).parents[2]))

from qitos.checkpoint import SqliteCheckpointStore
from qitos.core.action import Action
from qitos.core.agent_module import AgentModule
from qitos.core.decision import Decision
from qitos.core.session import (
    PauseSafety,
    ResolverNamespace,
    ResolverReference,
    ResolverRegistry,
    SafeBoundaryKind,
)
from qitos.core.state import StateSchema
from qitos.core.tool import tool
from qitos.core.tool_registry import ToolRegistry
from qitos.core.tool_result import ToolResult
from qitos.core.work_graph import WorkDescriptor, WorkGraph
from qitos.engine import Engine
from qitos.engine.runtime import DEFAULT_CHECKPOINT_REFERENCE, RuntimeComposition
from qitos.engine.work_runtime import (
    DurableWorkRuntime,
    SchedulerHandle,
    WorkDispatch,
    WorkRuntimeError,
    WorkRuntimePolicy,
)
from qitos.kit.tool.agent.durable_adapter import submit_durable_work
from qitos.qita._cli_app import main as qita_main
from qitos.tracing.sinks import TrajectoryStoreEventSink
from qitos.tracing.journal_store import JournalTrajectoryStore


@dataclass
class G4State(StateSchema):
    pass


class G4Agent(AgentModule[G4State, dict[str, Any], Action]):
    name = "g4-agent"

    def __init__(self) -> None:
        registry = ToolRegistry()

        @tool(name="barrier")
        def barrier() -> str:
            return "released"

        registry.register(barrier)
        super().__init__(tool_registry=registry)

    def init_state(self, task: str, **kwargs: Any) -> G4State:
        return G4State(task=task, max_steps=4)

    def decide(self, state: G4State, observation: dict[str, Any]) -> Decision[Action]:
        if state.current_step == 0:
            return Decision.act([Action(name="barrier", args={})])
        return Decision.final("done")

    def reduce(self, state: G4State, observation: Any, decision: Any) -> G4State:
        return state


G4State.__module__ = "s3_g4_process_fixture"


class PauseFirst:
    policy_id = "tests.g4.pause_first"
    supports_pause = True

    def should_pause(self, context: Any) -> bool:
        return context.step_id == 0

    def pause_safety(self, context: Any) -> PauseSafety:
        return PauseSafety(boundary=SafeBoundaryKind.AFTER_MODEL_RESULT)


class Handle:
    def __init__(self, worker_ref: str) -> None:
        self.worker_ref = worker_ref
        self.callback: Callable[[Any, BaseException | None], None] | None = None
        self.ready = threading.Event()
        self.finished = threading.Event()

    def add_terminal_callback(
        self, callback: Callable[[Any, BaseException | None], None]
    ) -> None:
        self.callback = callback
        self.ready.set()

    def request_cancel(self) -> bool:
        return False

    def finish(self) -> None:
        assert self.ready.wait(timeout=5)
        assert self.callback is not None
        self.callback({"ok": True}, None)
        self.finished.set()


class Scheduler:
    scheduler_id = "tests.g4.scheduler"

    def __init__(self, *, admit_queued: bool) -> None:
        self.admit_queued = admit_queued
        self.requests: list[WorkDispatch] = []
        self.handles: dict[str, Handle] = {}

    def dispatch(self, request: WorkDispatch) -> SchedulerHandle:
        if request.operation_id == "delegate:queued" and not self.admit_queued:
            raise WorkRuntimeError(
                "queue_capacity_exceeded",
                "deterministic queued admission",
                operation_id=request.operation_id,
            )
        self.requests.append(request)
        handle = Handle(f"g4:{request.operation_id}:{request.attempt}")
        self.handles[handle.worker_ref] = handle
        return handle

    def reattach(
        self, request: WorkDispatch, worker_ref: str
    ) -> SchedulerHandle | None:
        return self.handles.get(worker_ref)

    def close(self) -> None:
        return None


def _runtime(store: SqliteCheckpointStore, scheduler: Scheduler) -> RuntimeComposition:
    trajectory = JournalTrajectoryStore(os.environ["QITOS_G4_CANDIDATE"])
    runtime = RuntimeComposition(
        checkpoint_store=store,
        event_sink=TrajectoryStoreEventSink(trajectory),
        lifecycle_policy=PauseFirst(),
        work_runtime=DurableWorkRuntime(
            scheduler,
            policy=WorkRuntimePolicy(
                maximum_children_per_operation=4,
                maximum_graph_depth=4,
                maximum_concurrent_children=2,
                queue_capacity=4,
                admission_behavior="queue",
                budget_ceiling={"calls": 1},
                capability_ceiling=frozenset({"read"}),
            ),
        ),
    )
    runtime._g4_trajectory_store = trajectory
    return runtime


def _child_ids(receipt: Any) -> list[str]:
    return WorkDescriptor.from_dict(receipt.descriptor).child_work_item_ids


def create() -> None:
    store = SqliteCheckpointStore(os.environ["QITOS_G4_DB"])
    scheduler = Scheduler(admit_queued=False)
    runtime = _runtime(store, scheduler)
    session = Engine(G4Agent(), runtime=runtime).session("g4 parent")
    session.run()

    completed = session.delegate(
        "g4-agent", task="completed child", operation_id="delegate:completed"
    )
    scheduler.handles[completed.worker_ref].finish()
    try:
        session.delegate(
            "g4-agent", task="queued child", operation_id="delegate:queued"
        )
    except WorkRuntimeError as exc:
        assert exc.code == "queue_capacity_exceeded"
    running = session.spawn(
        "g4-agent", task="running child", operation_id="spawn:running"
    )
    fan = session.fan_out(
        [
            {
                "agent": "g4-agent",
                "task": "fan child zero",
                "capabilities": ["read"],
                "budget": {"calls": 1},
            },
            {
                "agent": "g4-agent",
                "task": "fan child one",
                "capabilities": ["read"],
                "budget": {"calls": 1},
            },
        ],
        operation_id="fan_out:partial",
    )
    direct = session.spawn(
        "g4-agent", task="direct parity", operation_id="spawn:direct"
    )
    tool_result = submit_durable_work(
        "spawn",
        {"agent": "g4-agent", "task": "tool parity"},
        {
            "work_runtime": runtime.work_runtime,
            "session": session,
            "slot_id": "tool-parity",
        },
    )
    assert tool_result is not None
    joined = session.join(
        [completed.operation_id, "delegate:queued", running.operation_id],
        policy="quorum",
        quorum=2,
        operation_id="join:g4",
    )
    graph = WorkGraph.from_canonical_dict(session.inspect().work_graph or {})
    completed_child = graph.work_items[next(iter(
        item for item in graph.work_items if item.value == _child_ids(completed)[0]
    ))]
    graph.record_completion(
        completion_id="completion:completed",
        work_item_id=completed_child.work_item_id,
        owner_generation=completed_child.owner.generation,
        outcome=ToolResult(output="completed"),
    )
    graph.accept_join_result("join:join:g4", completed_child.work_item_id)

    running_child = graph.work_items[next(iter(
        item for item in graph.work_items if item.value == _child_ids(running)[0]
    ))]
    queued_receipt = next(
        item for item in graph.operation_receipts
        if item.operation_id == "delegate:queued"
    )
    queued_child_id = _child_ids(queued_receipt)[0]
    queued_child = next(item for item in graph.work_items if item.value == queued_child_id)
    fan_child = next(
        item for item in graph.work_items
        if item.value == _child_ids(fan)[0]
    )
    graph.request_cancel(
        cancellation_id="cancel:propagate",
        work_item_id=running_child.work_item_id,
        expected_generation=running_child.owner.generation,
        propagation="propagate",
    )
    graph.request_cancel(
        cancellation_id="cancel:request-wait",
        work_item_id=queued_child,
        expected_generation=graph.work_items[queued_child].owner.generation,
        propagation="request_and_wait",
    )
    graph.request_cancel(
        cancellation_id="cancel:detach",
        work_item_id=fan_child,
        expected_generation=graph.work_items[fan_child].owner.generation,
        propagation="detach",
    )
    graph.detach_child(
        detachment_id="detach:fan",
        parent_work_item_id=session.work_item_id,
        child_work_item_id=fan_child,
        supervisor_ref="supervisor:external",
    )
    assert WorkDescriptor.from_dict(direct.descriptor).schema_version == (
        WorkDescriptor.from_dict(
            next(
                item.descriptor for item in graph.operation_receipts
                if item.operation_id == "spawn:tool-parity"
            )
        ).schema_version
    )
    assert joined.state in {"dispatched", "completed"}
    session._commit_work_graph_value(graph)
    session.handoff("g4-agent", operation_id="handoff:g4")
    control = {
        "session_id": session.session_id.value,
        "completed_operation": completed.operation_id,
        "running_operation": running.operation_id,
        "join_id": "join:join:g4",
    }
    Path(os.environ["QITOS_G4_CONTROL"]).write_text(
        json.dumps(control), encoding="utf-8"
    )
    os._exit(0)


def _restore_registry(
    store: SqliteCheckpointStore,
    session_id: str,
    runtime: RuntimeComposition,
) -> ResolverRegistry:
    head = store.get_session_head(session_id)
    assert head is not None
    snapshot = store.get_session_snapshot(head.snapshot_id)
    assert snapshot is not None
    agent = G4Agent()
    registry = ResolverRegistry()
    registry.register_resource(DEFAULT_CHECKPOINT_REFERENCE, store)
    for raw in snapshot.payload["resolver_references"]:
        reference = ResolverReference.from_dict(raw)
        if reference.namespace is ResolverNamespace.AGENT:
            registry.register_resource(reference, agent)
        elif reference.namespace is ResolverNamespace.TOOL_REGISTRY:
            registry.register_resource(reference, agent.tool_registry)
        elif reference.namespace is ResolverNamespace.RUNTIME_EVENT_SINK:
            registry.register_resource(reference, runtime.event_sink)
    return registry


def restore() -> None:
    control = json.loads(Path(os.environ["QITOS_G4_CONTROL"]).read_text())
    store = SqliteCheckpointStore(os.environ["QITOS_G4_DB"])
    scheduler = Scheduler(admit_queued=True)
    runtime = _runtime(store, scheduler)
    runtime.resolvers = _restore_registry(store, control["session_id"], runtime)
    session = Engine.restore(control["session_id"], runtime=runtime)
    graph = WorkGraph.from_canonical_dict(session.inspect().work_graph or {})
    before = {item.operation_id: item.state for item in graph.operation_receipts}
    session.recover_work()
    graph = WorkGraph.from_canonical_dict(session.inspect().work_graph or {})
    after = {item.operation_id: item.state for item in graph.operation_receipts}

    queued = next(
        item for item in graph.operation_receipts
        if item.operation_id == "delegate:queued"
    )
    scheduler.handles[queued.worker_ref].finish()
    graph = WorkGraph.from_canonical_dict(session.inspect().work_graph or {})
    queued_child_id = _child_ids(queued)[0]
    queued_child = next(item for item in graph.work_items if item.value == queued_child_id)
    graph.record_completion(
        completion_id="completion:queued",
        work_item_id=queued_child,
        owner_generation=graph.work_items[queued_child].owner.generation,
        outcome=ToolResult(output="queued restored"),
    )
    graph.accept_join_result(control["join_id"], queued_child)
    closed_generation = graph.joins[0].generation
    graph.accept_join_result(control["join_id"], queued_child)
    assert graph.joins[0].generation == closed_generation

    running = next(
        item for item in graph.operation_receipts
        if item.operation_id == control["running_operation"]
    )
    running_child_id = _child_ids(running)[0]
    running_child = next(item for item in graph.work_items if item.value == running_child_id)
    graph.record_completion(
        completion_id="completion:late-running",
        work_item_id=running_child,
        owner_generation=graph.work_items[running_child].owner.generation,
        outcome=ToolResult(output="late reconciled"),
    )
    graph.accept_join_result(control["join_id"], running_child)
    session._commit_work_graph_value(graph)

    candidate = Path(os.environ["QITOS_G4_CANDIDATE"])
    runtime.flush_events()
    graph_output = io.StringIO()
    with redirect_stdout(graph_output):
        graph_code = qita_main([
            "inspect", "graph", control["session_id"],
            "--candidate-store", str(candidate),
        ])
    timeline_output = io.StringIO()
    with redirect_stdout(timeline_output):
        timeline_code = qita_main([
            "inspect", "timeline", control["session_id"],
            "--candidate-store", str(candidate),
        ])
    graph_view = json.loads(graph_output.getvalue())
    timeline_view = json.loads(timeline_output.getvalue())

    descriptors = [
        WorkDescriptor.from_dict(item.descriptor)
        for item in graph.operation_receipts
        if item.descriptor is not None
    ]
    rendered = json.dumps([item.to_dict() for item in descriptors], sort_keys=True)
    result = {
        "before": before,
        "after": after,
        "restore_dispatches": [item.operation_id for item in scheduler.requests],
        "join_state": graph.joins[0].state,
        "join_generation": graph.joins[0].generation,
        "accepted": [item.value for item in graph.joins[0].accepted_child_ids],
        "discarded": [item.value for item in graph.joins[0].discarded_child_ids],
        "owner_transfers": len(graph.transfers),
        "authoritative_owner": graph.work_items[session.work_item_id].owner.agent_id.value,
        "cancellation_policies": sorted(item.propagation for item in graph.cancellations),
        "detachments": len(graph.detachments),
        "fan_out_width": len(graph.fan_out_groups[0].child_work_item_ids),
        "secret_free": all(
            token not in rendered.lower()
            for token in ("password=", "bearer ", "api_key=", "/users/")
        ),
        "qita_graph": graph_code == 0 and graph_view["session_summary"]["work_item_count"] >= 6,
        "qita_timeline": timeline_code == 0 and bool(timeline_view["timeline"]),
    }
    print(json.dumps(result, sort_keys=True))
    runtime._g4_trajectory_store.close()
    store.close()


def prepare_create() -> None:
    store = SqliteCheckpointStore(os.environ["QITOS_G4_DB"])
    runtime = _runtime(store, Scheduler(admit_queued=True))
    session = Engine(G4Agent(), runtime=runtime).session("g4 preparation parent")
    session.run()

    def lose_process_after_fork(**kwargs: Any) -> Any:
        del kwargs
        raise RuntimeError("deterministic loss after fork preparation")

    session._execute_child_transfer = lose_process_after_fork
    try:
        session.delegate(
            "g4-agent",
            task="declared child",
            operation_id="delegate:declared",
        )
    except RuntimeError as exc:
        assert str(exc) == "deterministic loss after fork preparation"
    fork_id = "fork_" + hashlib.sha256(b"delegate:declared:0").hexdigest()[:32]
    assert store.get_session_fork(fork_id) is not None
    graph = WorkGraph.from_canonical_dict(session.inspect().work_graph or {})
    assert graph.operation_receipts[0].state == "declared"
    Path(os.environ["QITOS_G4_CONTROL"]).write_text(
        json.dumps({"session_id": session.session_id.value, "fork_id": fork_id}),
        encoding="utf-8",
    )
    os._exit(0)


def prepare_restore() -> None:
    control = json.loads(Path(os.environ["QITOS_G4_CONTROL"]).read_text())
    store = SqliteCheckpointStore(os.environ["QITOS_G4_DB"])
    scheduler = Scheduler(admit_queued=True)
    runtime = _runtime(store, scheduler)
    runtime.resolvers = _restore_registry(store, control["session_id"], runtime)
    session = Engine.restore(control["session_id"], runtime=runtime)
    before_graph = WorkGraph.from_canonical_dict(session.inspect().work_graph or {})
    before = before_graph.operation_receipts[0]
    recovered = session.recover_work()[0]
    descriptor = WorkDescriptor.from_dict(recovered.descriptor)
    fork = descriptor.fork_receipts[0]
    result = {
        "before": before.state,
        "after": recovered.state,
        "operation_id": recovered.operation_id,
        "dispatches": [item.operation_id for item in scheduler.requests],
        "fork_reused": (
            fork["operation_id"] == control["fork_id"]
            and store.get_session_fork(control["fork_id"]) is not None
        ),
    }
    print(json.dumps(result, sort_keys=True))
    store.close()


if __name__ == "__main__":
    {
        "create": create,
        "restore": restore,
        "prepare_create": prepare_create,
        "prepare_restore": prepare_restore,
    }[os.environ["QITOS_G4_PHASE"]]()
