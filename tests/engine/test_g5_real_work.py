"""Real canonical child Sessions must drive WorkGraph completion and joins."""
import time

import pytest

from qitos.engine.engine import Engine
from qitos.engine.runtime import RuntimeComposition
from qitos.engine.work_runtime import DurableWorkRuntime, LocalWorkScheduler
from qitos.core.work_graph import WorkGraph
from test_work_runtime import _Agent, _PauseAtFirstBoundary


@pytest.mark.parametrize("operation", ["spawn", "delegate", "fan_out"])
def test_model_adapter_declares_real_children_during_session_run(operation):
    from qitos.core.action import Action
    from qitos.core.decision import Decision
    from qitos.core.agent_spec import AgentRegistry, AgentSpec
    from qitos.kit.tool.agent.durable_adapter import SpawnTool
    from qitos.kit.tool.delegate import DelegateTool
    from qitos.kit.tool.fanout import FanOutTool
    from test_work_runtime import IndependentSchedulerFake

    scheduler = IndependentSchedulerFake()
    runtime = RuntimeComposition(work_runtime=DurableWorkRuntime(scheduler))
    registry = AgentRegistry()
    tools = {"spawn": SpawnTool(), "delegate": DelegateTool(AgentSpec(name="parent", description="child", agent=_Agent()), registry),
             "fan_out": FanOutTool(registry)}
    selected = tools[operation]
    selected.spec.timeout_s = .5
    payload = {"tasks": [{"agent": "parent", "task": "child"}] } if operation == "fan_out" else {"agent": "parent", "task": "child"}
    if operation == "delegate":
        payload.pop("agent")

    class Agent(_Agent):
        def __init__(self):
            super().__init__()
            self.tool_registry.register(selected)

        def decide(self, state, observation):
            if state.current_step == 0:
                return Decision.act([Action(selected.name, payload)])
            return Decision.final(answer="done")

    session = Engine(Agent(), runtime=runtime).session("model adapter parent")
    try:
        result = session.run()
        assert result.records[0].action_results[0].status == "success", result.records[0].action_results
        graph = WorkGraph.from_canonical_dict(session.inspect().work_graph)
        assert len(scheduler.requests) == 1
        descriptor = scheduler.requests[0].descriptor
        assert len(descriptor.child_session_ids) == 1
        child_head = runtime.checkpoint_store.get_session_head(descriptor.child_session_ids[0])
        assert child_head is not None and child_head.session_id != session.session_id.value
        assert len(graph.work_items) == 2
    finally:
        runtime.work_runtime.close()


@pytest.mark.parametrize("child_fails", [False, True])
@pytest.mark.parametrize("operation", ["spawn", "delegate", "fan_out"])
def test_real_child_session_completion_closes_durable_join(child_fails, operation):
    root = RuntimeComposition(lifecycle_policy=_PauseAtFirstBoundary())

    class Resolver:
        resolver_id = "g5.real_child"

        def resolve(self, descriptor):
            def run():
                if descriptor.operation != "join":
                    for identity in descriptor.child_session_ids:
                        child_runtime = RuntimeComposition(checkpoint_store=root.checkpoint_store,
                                                           resolvers=root.resolvers.copy())
                        child = Engine.restore(identity, runtime=child_runtime)
                        child.run()
                return {"child_session_ids": descriptor.child_session_ids}
            return run

    root.work_runtime = DurableWorkRuntime(LocalWorkScheduler(Resolver(), max_workers=1))
    class Agent(_Agent):
        def decide(self, state, observation):
            if child_fails and state.task == "child task":
                raise RuntimeError("controlled child failure")
            return super().decide(state, observation)

    session = Engine(Agent(), runtime=root).session("parent")
    session.run()

    def wait(operation_id):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            graph = WorkGraph.from_canonical_dict(session.inspect().work_graph)
            found = next(item for item in graph.operation_receipts if item.operation_id == operation_id)
            if found.state in {"completed", "failed"}:
                assert found.state == "completed"
                return graph
            time.sleep(.01)
        raise AssertionError("bounded child operation did not complete")

    try:
        specification = {"agent": "parent", "task": "child task"}
        payload = {"tasks": [specification]} if operation == "fan_out" else specification
        child = session.submit_work(operation, payload, operation_id=operation + ":g5-real")
        wait(child.operation_id)
        joined = session.join([child.operation_id], operation_id="join:g5-real")
        graph = wait(joined.operation_id)
        assert len(graph.completions) == 1
        assert graph.completions[0].outcome["status"] == ("error" if child_fails else "success")
        assert graph.joins[0].state == "closed"
        assert len(graph.joins[0].accepted_child_ids) == 1
    finally:
        root.work_runtime.close()
