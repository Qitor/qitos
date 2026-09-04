"""Real Docker lesson: retained output and opt-in top-level file publication.

Uses a fake provider but real Env tools, Session, artifact store and reader.
Only --publish registers publication authority over report.txt in a new fixture.
"""
import argparse
import hashlib
import json
from pathlib import Path

from qitos.config import (
    AgentConfig, BudgetConfig, EnvironmentConfig, ModelConfig, RuntimeConfig,
    TrajectoryConfig, build_agent_composition,
)
from qitos.core.artifact import ArtifactRef
from notes import PauseAfterTool
from qitos.kit.tool.internal.publication import SandboxPublicationTool
from qitos.qita.reader import default_reader
from qitos.tracing.trajectory import PrivacyView


class FakeProvider:
    model = "sandbox-tutorial-fake"
    qitos_protocol = "json_decision_multi_v1"

    def __init__(self, publish, stage=0):
        self.actions = [
            ("write_file", {"path": "report.txt", "content": "Session, Artifact\n"}),
            ("run_command", {"command": "python3 -c 'print(\"x\" * 20000)'", "timeout": 10}),
        ]
        if publish:
            self.actions.append(("publish_workspace", {}))
        self.stage = stage

    def call_raw(self, messages, **options):
        if self.stage == len(self.actions):
            return {"choices": [{"message": {"content": "Final Answer: sandbox lesson complete"}}]}
        name, args = self.actions[self.stage]
        self.stage += 1
        return {"choices": [{"message": {"content": None, "tool_calls": [{
            "id": f"lesson-{self.stage}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)},
        }]}}]}


def references(value):
    if isinstance(value, dict):
        if value.get("schema_version") == "qitos.artifact_ref/v1":
            yield ArtifactRef.from_dict(value)
        for item in value.values():
            yield from references(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from references(item)


def run(root: Path, image: str, publish: bool):
    root.mkdir(parents=True, exist_ok=False)
    source = root / "source"
    source.mkdir()
    (source / "report.txt").write_text("original\n", encoding="utf-8")
    config = AgentConfig(
        lifecycle={"policy": "pause"},
        name="sandbox-lesson", protocol="json_decision_multi_v1", tool_preset="env_coding",
        model=ModelConfig(provider="openai_compatible", model="sandbox-tutorial-fake"),
        tool_options={"native_tool_calls_required": True},
        budgets=BudgetConfig(max_steps=6, max_requests=6, max_runtime_seconds=60),
        runtime=RuntimeConfig(
            data_root=str(root / "data"),
            trajectory=TrajectoryConfig(output=str(root / "trajectory.journal")),
            environment=EnvironmentConfig(workspace=str(source), image=image,
                                          cpus=0.5, memory_mb=256, pids_limit=32)),
    )
    with build_agent_composition(config, model_override=FakeProvider(publish),
                                 extensions={"pause": PauseAfterTool}) as composition:
        session = composition.session("Write the notes report and retain a large output")
        session.run()
        assert session.lifecycle.value == "paused"
        identity = session.session_id.value
    assert (source / "report.txt").read_text() == "original\n"
    with build_agent_composition(config, model_override=FakeProvider(publish, stage=1),
                                 extensions={"pause": PauseAfterTool}) as composition:
        session = composition.restore(identity)
        if publish:
            composition.tool_registry.register(SandboxPublicationTool(
                composition.env, paths=["report.txt"],
                expected_input_digest=composition.env.input_digest,
            ))
        result = session.run()
        assert result.state.final_result == "sandbox lesson complete", repr(result.state.final_result)
        trajectory = default_reader(root).read_session(session.session_id.value, view=PrivacyView.RAW_PRIVATE)
        artifacts = [ref for record in trajectory.records for ref in references(record.payload)]
        assert artifacts
        for ref in artifacts:
            body = composition.agent.config["artifact_resolver"].resolve(ref).body
            assert body is not None and hashlib.sha256(body).hexdigest() == ref.sha256
        assert (source / "report.txt").read_text() == ("Session, Artifact\n" if publish else "original\n")
    assert composition.env.cleanup_receipt["container_absent"] is True
    assert (source / "report.txt").read_text() == ("Session, Artifact\n" if publish else "original\n")
    print(json.dumps({"docker": True, "published": publish, "artifacts": len(artifacts),
                      "container_absent": True, "session_id": session.session_id.value}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--image", default="python:3.12-slim")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    run(args.root.resolve(), args.image, args.publish)
