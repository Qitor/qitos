"""Executable Docker sandbox qualification and one-Env model tool route."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from qitos.config import (
    AgentConfig,
    BudgetConfig,
    CredentialRef,
    EnvironmentConfig,
    ModelConfig,
    RuntimeConfig,
)
from qitos.config.builder import build_agent_composition
from qitos.kit.env.docker_qualification import (
    SandboxIdentity,
    qualify_docker_environment,
)


IMAGE = "openclaw:staged"


def _docker_ready() -> bool:
    if shutil.which("docker") is None:
        return False
    return (
        subprocess.run(
            ["docker", "image", "inspect", IMAGE],
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


def _config(workspace: Path) -> AgentConfig:
    return AgentConfig(
        name="sandbox-test",
        max_steps=5,
        model=ModelConfig(
            provider="openai_compatible",
            model="fake",
            base_url="https://example.invalid/v1",
            credential=CredentialRef("fake"),
        ),
        tool_preset="env_coding",
        protocol="react_text_v1",
        runtime=RuntimeConfig(
            environment=EnvironmentConfig(
                type="docker",
                image=IMAGE,
                workspace=str(workspace),
                container_workspace="/workspace",
                network="none",
                read_only_root=True,
            )
        ),
        budgets=BudgetConfig(
            max_steps=5, max_runtime_seconds=60, max_requests=8
        ),
    )


@pytest.mark.skipif(not _docker_ready(), reason="local qualification image unavailable")
def test_real_docker_qualification_is_inspect_and_probe_backed(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "fixture.py").write_text("VALUE = 41\n", encoding="utf-8")
    config = _config(workspace)

    receipt = qualify_docker_environment(
        config,
        identity=SandboxIdentity(
            session_id="session-test",
            run_id="run-test",
            work_item_id="work-test",
            environment_id="environment-test",
        ),
    )

    assert receipt.status == "passed"
    assert receipt.config_digest == config.digest()
    assert receipt.image_id.startswith("sha256:")
    assert receipt.unexpected_mounts == []
    assert all(receipt.cleanup.values())
    assert receipt.workspace_digest_before == receipt.workspace_digest_after


class _SandboxFakeModel:
    model = "sandbox-fake"
    max_tokens = 256
    context_window = 8192
    qitos_harness_metadata = {
        "tool_policy": {"native_tool_call_preferred": True},
        "parser": "ReActTextParser",
        "protocol": "react_text_v1",
    }

    def __init__(self) -> None:
        self.calls = 0

    def call_raw(
        self, messages: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]:
        _ = messages, kwargs
        call = self.calls
        self.calls += 1
        if call == 0:
            tool_calls = [
                {
                    "id": "read-1",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path":"fixture.py"}',
                    },
                },
                {
                    "id": "grep-1",
                    "type": "function",
                    "function": {
                        "name": "grep_file",
                        "arguments": '{"query":"VALUE","path":"fixture.py"}',
                    },
                },
            ]
        elif call == 1:
            tool_calls = [
                {
                    "id": "write-1",
                    "type": "function",
                    "function": {
                        "name": "write_file",
                        "arguments": '{"path":"result.py","content":"VALUE = 42\\n"}',
                    },
                }
            ]
        elif call == 2:
            tool_calls = [
                {
                    "id": "test-1",
                    "type": "function",
                    "function": {
                        "name": "run_command",
                        "arguments": '{"command":"python3 -c \\"import result; assert result.VALUE == 42\\""}',
                    },
                }
            ]
        else:
            return {"choices": [{"message": {"content": "Final Answer: done"}}]}
        return {
            "choices": [
                {
                    "message": {"content": None, "tool_calls": tool_calls},
                    "finish_reason": "tool_calls",
                }
            ]
        }


@pytest.mark.skipif(not _docker_ready(), reason="local qualification image unavailable")
def test_fake_provider_executes_parallel_read_grep_edit_and_test_in_same_env(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "fixture.py").write_text("VALUE = 41\n", encoding="utf-8")
    config = _config(workspace)
    model = _SandboxFakeModel()
    composition = build_agent_composition(config, model_override=model)
    try:
        result = composition.engine.run("write result.py with VALUE = 42 and test it")
    finally:
        composition.close()

    assert result.state.final_result == "done"
    assert result.tool_calls_by_name == {
        "read_file": 1,
        "grep_file": 1,
        "write_file": 1,
        "run_command": 1,
    }
    assert (workspace / "result.py").read_text(encoding="utf-8") == "VALUE = 42\n"
