"""Complete offline Session tutorial. Only trusted arithmetic tools run on host.

Run: python session_walkthrough.py create --root ./lesson
Then: python session_walkthrough.py restore --root ./lesson
No model credentials, network requests, shell tools, or sandbox claims.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path

from qitos.config import (
    AgentConfig, BudgetConfig, CredentialRef, EnvironmentConfig, ModelConfig, RuntimeConfig,
    SessionConfig, TrajectoryConfig, build_agent_composition,
)
from qitos.core.function_tool_decorator import function_tool
from qitos.engine.runtime import LifecyclePolicy
from qitos.qita.reader import default_reader
from qitos.tracing.exporter import CanonicalTrajectoryExporter
from qitos.tracing.trajectory import PrivacyView


@function_tool(read_only=True, concurrency_safe=True)
def add(a: int, b: int) -> int:
    """Add two integers without external effects."""
    return a + b


class FakeProvider:
    """A deterministic teaching double, not evidence of model intelligence."""
    model = "tutorial-fake"
    qitos_protocol = "react_text_v1"

    def __init__(self, *, finish: bool = False):
        self.finish = finish

    def call_raw(self, messages, **options):
        content = ("Final Answer: arithmetic complete" if self.finish else
                   'Thought: compute\nAction: add(a=20, b=22)')
        self.finish = True
        return {"choices": [{"message": {"content": content}}]}


class PauseAfterTool(LifecyclePolicy):
    policy_id = "tutorial.pause_after_tool"

    def should_pause(self, context):
        return context.step_id == 0


def configuration(root: Path) -> AgentConfig:
    """Explicit unisolated host mode, with no file or command tool registered."""
    return AgentConfig(
        name="arithmetic", protocol="react_text_v1", tool_preset="none",
        model=ModelConfig(provider="openai_compatible", model="tutorial-fake",
                          credential=CredentialRef("tutorial-unused")),
        budgets=BudgetConfig(max_steps=4, max_requests=4, max_runtime_seconds=30),
        runtime=RuntimeConfig(
            data_root=str(root / "data"),
            environment=EnvironmentConfig(
                type="unsafe_host", image="", workspace=str(root),
                container_workspace="", network="host", read_only_root=False,
                cap_drop=False, no_new_privileges=False, pids_limit=None,
                memory_mb=None, cpus=None, cleanup_required=False,
            ),
            session=SessionConfig(store="sqlite", path=str(root / "sessions.sqlite3")),
            trajectory=TrajectoryConfig(output=str(root / "trajectory.journal")),
        ),
    )


def compose(root: Path, *, finish: bool = False, pause: bool = False):
    config = configuration(root)
    if pause:
        config = replace(config, lifecycle={"policy": "pause"})
    composition = build_agent_composition(
        config, model_override=FakeProvider(finish=finish),
        extensions={"pause": PauseAfterTool},
    )
    composition.tool_registry.register(add)
    return composition


def create(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    if (root / "control.json").exists():
        raise ValueError("lesson already exists; choose a new --root")
    with compose(root, pause=True) as composition:
        session = composition.session("Compute 20 + 22")
        result = session.run()
        assert session.lifecycle.value == "paused"
        assert result.records[0].action_results[0].output == 42
        document = composition.config.to_dict()
        # Host configuration accepts only host-relevant fields, not Docker claims.
        document["runtime"]["environment"] = {"type": "unsafe_host", "workspace": str(root)}
        (root / "agent.json").write_text(json.dumps(document), encoding="utf-8")
        control = {"session_id": session.session_id.value}
        (root / "control.json").write_text(json.dumps(control), encoding="utf-8")
        print(json.dumps({**control, "lifecycle": "paused", "tool_output": 42}))


def restore(root: Path):
    control = json.loads((root / "control.json").read_text(encoding="utf-8"))
    # Reuse the same configuration digest, including the lifecycle policy.
    with compose(root, finish=True, pause=True) as composition:
        store = composition.runtime.checkpoint_store
        parent_head = store.get_session_head(control["session_id"])
        child = composition.fork(control["session_id"])
        assert store.get_session_head(control["session_id"]) == parent_head
        assert child.session_id.value != control["session_id"]
        child.run(steering="Finish the independent arithmetic explanation.")
        assert store.get_session_head(control["session_id"]) == parent_head
        session = composition.restore(control["session_id"])
        result = session.run(steering="State the result concisely.")
        assert result.state.final_result == "arithmetic complete"
        trajectory = default_reader(root).read_session(
            session.session_id.value, view=PrivacyView.RAW_PRIVATE,
        )
        assert trajectory.records
        assert any(record.kind.value == "steering" for record in trajectory.records)
        exporter = CanonicalTrajectoryExporter()
        exported = exporter.export(trajectory, view=PrivacyView.REDACTED_PUBLIC)
        assert len(exporter.reimport(exported).records) == len(trajectory.records)
        (root / "public-trajectory.json").write_bytes(exported.data)
        control["run_id"] = result.run_id
        (root / "control.json").write_text(json.dumps(control), encoding="utf-8")
        print(json.dumps({"session_id": session.session_id.value,
                          "child_session_id": child.session_id.value,
                          "final_result": result.state.final_result,
                          "records": len(trajectory.records),
                          "public_export_lossless": exported.loss.is_lossless}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("create", "restore"))
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    {"create": create, "restore": restore}[args.phase](args.root.resolve())


if __name__ == "__main__":
    main()
