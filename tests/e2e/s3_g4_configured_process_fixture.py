"""Canonical-config fake-provider workflow across two clean processes."""

from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qitos.config import FakeCredentialResolver, load_agent_config
from qitos.config.builder import build_agent_composition
from qitos.core.session import PauseSafety, SafeBoundaryKind
from qitos.engine import Engine
from qitos.qita._cli_app import main as qita_main
from qitos.qita.reader import candidate_file_reader, load_session_payload
from qitos.tracing.trajectory import PrivacyView


class FakeCodingModel:
    model = "fake-configured-coder"
    max_tokens = 10240
    context_window = 32768
    qitos_harness_metadata = {
        "tool_policy": {"native_tool_call_preferred": True},
        "parser": "JsonDecisionParser",
        "protocol": "json_decision_multi_v1",
    }

    def call_raw(
        self, messages: list[dict[str, Any]], **options: Any
    ) -> dict[str, Any]:
        _ = options
        rendered = json.dumps(messages, sort_keys=True)
        if '"name": "read_file"' not in rendered:
            calls = [
                {
                    "id": "configured-read",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path":"calculator.py"}',
                    },
                },
                {
                    "id": "configured-grep",
                    "type": "function",
                    "function": {
                        "name": "grep_file",
                        "arguments": '{"query":"clamp","path":"."}',
                    },
                },
            ]
        elif '"name": "write_file"' not in rendered:
            calls = [
                {
                    "id": "configured-write",
                    "type": "function",
                    "function": {
                        "name": "write_file",
                        "arguments": json.dumps(
                            {
                                "path": "calculator.py",
                                "content": (
                                    "def clamp(value: int, low: int, high: int) -> int:\n"
                                    "    \"\"\"Return value constrained to the inclusive "
                                    "[low, high] interval.\"\"\"\n"
                                    "    return max(low, min(value, high))\n"
                                ),
                            },
                            separators=(",", ":"),
                        ),
                    },
                }
            ]
        elif '"name": "run_command"' not in rendered:
            calls = [
                {
                    "id": "configured-test",
                    "type": "function",
                    "function": {
                        "name": "run_command",
                        "arguments": '{"command":"python3 -m pytest -q"}',
                    },
                }
            ]
        else:
            return {
                "choices": [
                    {"message": {"content": "Final Answer: all three tests pass"}}
                ]
            }
        return {
            "choices": [
                {
                    "message": {"content": None, "tool_calls": calls},
                    "finish_reason": "tool_calls",
                }
            ]
        }


class PauseAfterTest:
    policy_id = "tests.configured.pause_after_test"
    supports_pause = True

    def should_pause(self, context: Any) -> bool:
        return context.step_id == 2

    def pause_safety(self, context: Any) -> PauseSafety:
        _ = context
        return PauseSafety(boundary=SafeBoundaryKind.AFTER_MODEL_RESULT)


def _composition() -> Any:
    config = load_agent_config(os.environ["QITOS_CONFIGURED_CONFIG"])
    composition = build_agent_composition(
        config,
        credential_resolver=FakeCredentialResolver(
            {"offline-qualified": "offline-secret-never-persist"}
        ),
        model_override=FakeCodingModel(),
    )
    composition.runtime.lifecycle_policy = PauseAfterTest()
    return composition


def create() -> None:
    composition = _composition()
    session = composition.engine.session(
        "Read and grep calculator.py, fix clamp, run pytest, pause safely, then finish."
    )
    result = session.run()
    from qitos.core.action import Action
    from qitos.kit.tool.internal.publication import SandboxPublicationTool
    composition.tool_registry.register(SandboxPublicationTool(
        composition.env, paths=["calculator.py"], expected_input_digest=composition.env.input_digest,
    ))
    publication = composition.engine.executor.execute_one(Action("publish_workspace", {}), env=composition.env)
    assert publication.status == "success", publication.to_dict()
    payload = {
        "session_id": session.session_id.value,
        "run_id": result.run_id,
        "lifecycle": session.lifecycle.value,
        "tool_calls": result.tool_calls_by_name,
        "config_digest": composition.config.digest(),
    }
    composition.close()
    payload["sandbox"] = dict(composition.sandbox_receipt)
    Path(os.environ["QITOS_CONFIGURED_CONTROL"]).write_text(
        json.dumps(payload, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(payload, sort_keys=True))


def restore() -> None:
    control = json.loads(
        Path(os.environ["QITOS_CONFIGURED_CONTROL"]).read_text(encoding="utf-8")
    )
    composition = _composition()
    composition.runtime.bind_engine_resources(composition.engine)
    restored = Engine.restore(control["session_id"], runtime=composition.runtime)
    result = restored.run()
    lifecycle = restored.lifecycle.value
    composition.close()
    reader = candidate_file_reader(composition.trajectory_path)
    trajectory = reader.read_session(
        control["session_id"], view=PrivacyView.RAW_PRIVATE
    )
    qita = load_session_payload(reader, control["session_id"])
    timeline_output = io.StringIO()
    with redirect_stdout(timeline_output):
        timeline_code = qita_main(
            [
                "inspect",
                "timeline",
                control["session_id"],
                "--candidate-store",
                str(composition.trajectory_path),
            ]
        )
    timeline = json.loads(timeline_output.getvalue())
    payload = {
        "session_id": control["session_id"],
        "run_id": result.run_id,
        "lifecycle": lifecycle,
        "final_result": result.state.final_result,
        "requests_after_restore": 1,
        "config_digest": composition.config.digest(),
        "trajectory_records": len(trajectory.records),
        "trajectory_kinds": sorted({item.kind.value for item in trajectory.records}),
        "qita_session": (
            qita.get("trajectory_meta", {}).get("session_id")
            == control["session_id"]
        ),
        "qita_timeline": timeline_code == 0 and bool(timeline.get("timeline")),
        "sandbox": dict(composition.sandbox_receipt),
    }
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    {"create": create, "restore": restore}[os.environ["QITOS_CONFIGURED_PHASE"]]()
