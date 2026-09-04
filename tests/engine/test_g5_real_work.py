"""Real canonical child Sessions must drive WorkGraph completion and joins."""
import time

from qitos.engine.engine import Engine
from qitos.engine.runtime import RuntimeComposition
from qitos.engine.work_runtime import DurableWorkRuntime, LocalWorkScheduler
from qitos.core.work_graph import WorkGraph
from test_work_runtime import _Agent, _PauseAtFirstBoundary


def test_real_child_session_completion_closes_durable_join():
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
    session = Engine(_Agent(), runtime=root).session("parent")
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
        child = session.spawn("parent", task="child task", operation_id="spawn:g5-real")
        wait(child.operation_id)
        joined = session.join([child.operation_id], operation_id="join:g5-real")
        graph = wait(joined.operation_id)
        assert len(graph.completions) == 1
        assert graph.joins[0].state == "closed"
        assert len(graph.joins[0].accepted_child_ids) == 1
    finally:
        root.work_runtime.close()
