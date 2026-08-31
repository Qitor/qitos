"""Offline fresh-process Session restoration through canonical checkpoints."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
from typing import Any

from qitos.checkpoint import SqliteCheckpointStore
from qitos.core.action import Action
from qitos.core.agent_module import AgentModule
from qitos.core.decision import Decision
from qitos.core.state import StateSchema
from qitos.core.tool import tool
from qitos.core.tool_registry import ToolRegistry
from qitos.engine import Engine
from qitos.engine.runtime import LifecyclePolicy, RuntimeComposition


@dataclass
class ProcessState(StateSchema):
    committed_effects: int = 0


# Pytest and a direct Python import use different module aliases for this test
# file. The fixture declares one stable logical producer module for both.
ProcessState.__module__ = "s2_lane_a_fixture"


class ProcessAgent(AgentModule[ProcessState, dict[str, Any], Action]):
    name = "process_continuity"

    def __init__(self) -> None:
        registry = ToolRegistry()

        @tool(name="durable_effect")
        def durable_effect() -> int:
            path = Path(os.environ["QITOS_S2_COUNTER_PATH"])
            count = int(path.read_text(encoding="utf-8"))
            path.write_text(str(count + 1), encoding="utf-8")
            return count + 1

        registry.register(durable_effect)
        super().__init__(tool_registry=registry)

    def init_state(self, task: str, **kwargs: Any) -> ProcessState:
        return ProcessState(task=task, max_steps=3)

    def decide(self, state, observation):
        if state.current_step == 0:
            return Decision.act([Action(name="durable_effect", args={})])
        return Decision.final("restored")

    def reduce(self, state, observation, decision):
        if decision.mode == "act":
            state.committed_effects += 1
        elif decision.mode == "final":
            state.final_result = decision.final_answer
        return state


class PauseInParent(LifecyclePolicy):
    policy_id = "tests.process_pause"

    def should_pause(self, context) -> bool:
        return context.step_id == 0


def _child_script() -> str:
    return r'''
import json
import os
import sys
from qitos.checkpoint import SqliteCheckpointStore
from qitos.core.session import ResolverNamespace, ResolverReference, ResolverRegistry
from qitos.engine import Engine
from qitos.engine.runtime import DEFAULT_CHECKPOINT_REFERENCE, RuntimeComposition
sys.path.insert(0, os.path.join(os.getcwd(), "tests", "e2e"))
from test_session_core_process_restore import ProcessAgent

store = SqliteCheckpointStore(os.environ["QITOS_S2_DB_PATH"])
session_id = os.environ["QITOS_S2_SESSION_ID"]
head = store.get_session_head(session_id)
snapshot = store.get_session_snapshot(head.snapshot_id)
agent = ProcessAgent()
registry = ResolverRegistry()
registry.register_resource(DEFAULT_CHECKPOINT_REFERENCE, store)
for raw in snapshot.payload["resolver_references"]:
    reference = ResolverReference.from_dict(raw)
    if reference.namespace is ResolverNamespace.AGENT:
        registry.register_resource(reference, agent)
    elif reference.namespace is ResolverNamespace.TOOL_REGISTRY:
        registry.register_resource(reference, agent.tool_registry)
runtime = RuntimeComposition(checkpoint_store=store, resolvers=registry)
session = Engine.restore(session_id, runtime=runtime)
new_run_id = session.run_id.value
result = session.run(steering="new constraint")
print(json.dumps({
    "run_id": new_run_id,
    "lifecycle": session.lifecycle.value,
    "effects": result.state.committed_effects,
    "result": result.state.final_result,
    "counter": int(open(os.environ["QITOS_S2_COUNTER_PATH"], encoding="utf-8").read()),
}))
store.close()
'''


def test_fresh_process_restore_uses_no_live_parent_object(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "session.db"
    counter_path = tmp_path / "effect-count.txt"
    counter_path.write_text("0", encoding="utf-8")
    monkeypatch.setenv("QITOS_S2_COUNTER_PATH", str(counter_path))
    store = SqliteCheckpointStore(str(db_path))
    runtime = RuntimeComposition(
        checkpoint_store=store,
        lifecycle_policy=PauseInParent(),
    )
    parent = Engine(ProcessAgent(), runtime=runtime).session("perform one effect")
    parent_run_id = parent.run_id.value
    parent.run()
    session_id = parent.session_id.value
    assert counter_path.read_text(encoding="utf-8") == "1"
    store.close()

    env = dict(os.environ)
    env["QITOS_S2_DB_PATH"] = str(db_path)
    env["QITOS_S2_SESSION_ID"] = session_id
    completed = subprocess.run(
        [sys.executable, "-c", _child_script()],
        cwd=str(Path(__file__).parents[2]),
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload == {
        "run_id": payload["run_id"],
        "lifecycle": "completed",
        "effects": 1,
        "result": "restored",
        "counter": 1,
    }
    assert payload["run_id"] != parent_run_id
