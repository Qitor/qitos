"""Durable spawn/delegate/fan-out/join with real child Session execution.

The local scheduler resolves only this tutorial's Agent; no distributed service.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import time

from qitos.core.work_graph import WorkGraph
from qitos.engine.work_runtime import DurableWorkRuntime, LocalWorkScheduler
from dataclasses import replace
from qitos.config import build_agent_composition
from session_walkthrough import FakeProvider, PauseAfterTool, add, configuration


def compose(root, *, pause=False, finish=False):
    config = configuration(root)
    config = replace(config, budgets=replace(config.budgets, max_requests=16),
                     lifecycle={"policy": "pause"})
    result = build_agent_composition(config, model_override=FakeProvider(finish=finish),
                                     extensions={"pause": PauseAfterTool})
    result.tool_registry.register(add)
    return result


def wait(session, operation):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        graph = WorkGraph.from_canonical_dict(session.inspect().work_graph)
        receipt = next(item for item in graph.operation_receipts if item.operation_id == operation.operation_id)
        if receipt.state in {"completed", "failed", "outcome_unknown"}:
            assert receipt.state == "completed", receipt.state
            return graph
        time.sleep(0.02)
    raise AssertionError("child deadline exceeded; inspect before retrying")


def run(root):
    root.mkdir(parents=True, exist_ok=False)

    class Resolver:
        resolver_id = "tutorial.arithmetic.worker"

        def resolve(self, descriptor):
            def execute():
                for identity in (() if descriptor.operation == "join" else descriptor.child_session_ids):
                    subprocess.run([sys.executable, __file__, "--root", str(root), "--child", identity],
                                   check=True, capture_output=True, text=True, timeout=20)
                return {"children": list(descriptor.child_session_ids)}
            return execute

    with compose(root, pause=True) as composition:
        composition.runtime.work_runtime = DurableWorkRuntime(LocalWorkScheduler(Resolver(), max_workers=2))
        parent = composition.session("Compute, then ask independent arithmetic workers")
        parent.run()
        assert parent.lifecycle.value == "paused"
        delegated = parent.delegate("arithmetic", task="Explain the addition")
        wait(parent, delegated)
        spawned = parent.spawn("arithmetic", task="Check the sum")
        wait(parent, spawned)
        batch = parent.fan_out([{"agent": "arithmetic", "task": "Check 20", "budget": {"model_requests": 2}},
                                {"agent": "arithmetic", "task": "Check 22", "budget": {"model_requests": 2}}])
        wait(parent, batch)
        joined = parent.join([delegated.operation_id, spawned.operation_id, batch.operation_id], policy="all")
        graph = wait(parent, joined)
        assert graph.joins[-1].state == "closed"
        assert len(graph.completions) == 4
        print("durable children=4; join=closed; parent retains ownership")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--child")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.child:
        with compose(root, finish=True, pause=True) as composition:
            result = composition.restore(args.child).run()
            assert result.state.final_result == "arithmetic complete"
    else:
        run(root)
