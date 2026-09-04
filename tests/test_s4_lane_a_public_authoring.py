"""Executable S4 Lane A public-authoring contract."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import qitos.config.builder as builder
from qitos.cli import main as qit_main
from qitos.config import (
    AgentConfig,
    CredentialRef,
    DatasetItem,
    EnvironmentConfig,
    ModelConfig,
    RuntimeConfig,
    SessionConfig,
    TrajectoryConfig,
    build_agent_composition,
    load_agent_config,
    run_agent_config,
)
from qitos.config.errors import CompositionCleanupError, ConfigSchemaError
from qitos.core.session import PauseSafety, SafeBoundaryKind
from qitos.kit.env import HostEnv


class _FinalModel:
    model = "offline-final"
    qitos_protocol = "react_text_v1"

    def call_raw(self, messages: object, **options: object) -> dict[str, Any]:
        _ = messages, options
        return {"choices": [{"message": {"content": "Final Answer: done"}}]}


class _ActionModel(_FinalModel):
    def call_raw(self, messages: object, **options: object) -> dict[str, Any]:
        _ = messages, options
        return {
            "choices": [
                {
                    "message": {
                        "content": 'Thought: record\nAction: _remember(value="truth")',
                    }
                }
            ]
        }


def _remember(value: str) -> dict[str, str]:
    return {"remembered": value}


class _PauseAfterFirstStep:
    policy_id = "tests.s4.pause_after_first_step"
    supports_pause = True

    def should_pause(self, context: Any) -> bool:
        return context.step_id == 0

    def pause_safety(self, context: Any) -> PauseSafety:
        _ = context
        return PauseSafety(boundary=SafeBoundaryKind.AFTER_MODEL_RESULT)


def _config(tmp_path: Path, *, mode: str = "durable") -> AgentConfig:
    return AgentConfig(
        name="s4-lane-a",
        model=ModelConfig(
            provider="openai-compatible",
            model="offline-final",
            credential=CredentialRef("offline"),
        ),
        dataset=(DatasetItem(task="finish deterministically"),),
        protocol="react_text_v1",
        runtime=RuntimeConfig(
            environment=EnvironmentConfig(
                type="unsafe_host",
                image="",
                workspace=str(tmp_path),
                container_workspace="",
                network="host",
                read_only_root=False,
                cap_drop=False,
                no_new_privileges=False,
                pids_limit=None,
                memory_mb=None,
                cpus=None,
                cleanup_required=False,
            ),
            session=SessionConfig(mode=mode, store="memory"),
        ),
    )


def test_composition_is_context_manager_and_close_is_idempotent(
    tmp_path: Path,
) -> None:
    model = _FinalModel()
    env = HostEnv(workspace_root=str(tmp_path))
    composition = build_agent_composition(
        _config(tmp_path), model_override=model, env_override=env
    )

    with composition as entered:
        assert entered is composition
        session = entered.session()
        result = session.run()
        assert result.state.final_result == "done"

    first = composition.close()
    second = composition.close()
    assert first == second
    assert first["status"] == "closed"
    assert "model_transport" not in first["closed"]
    assert "sandbox" not in first["closed"]


def test_owned_cleanup_failure_is_typed_and_repeatable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingModel(_FinalModel):
        def close(self) -> None:
            raise RuntimeError("private detail")

    monkeypatch.setattr(builder, "build_model", lambda *args, **kwargs: FailingModel())
    composition = build_agent_composition(_config(tmp_path))

    with pytest.raises(CompositionCleanupError) as first:
        composition.close()
    with pytest.raises(CompositionCleanupError) as second:
        composition.close()
    assert first.value is second.value
    assert first.value.to_dict()["failures"] == [
        {"resource": "model_transport", "error_type": "RuntimeError"}
    ]
    assert "private detail" not in str(first.value.to_dict())


def test_context_manager_closes_owned_resources_after_body_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ClosingModel(_FinalModel):
        closed = False

        def close(self) -> None:
            self.closed = True

    model = ClosingModel()
    monkeypatch.setattr(builder, "build_model", lambda *args, **kwargs: model)
    composition = build_agent_composition(_config(tmp_path))

    with pytest.raises(RuntimeError, match="body failure"):
        with composition:
            raise RuntimeError("body failure")
    assert model.closed is True
    assert composition.close()["status"] == "closed"


def test_partial_build_failure_closes_already_owned_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ClosingModel(_FinalModel):
        closed = False

        def close(self) -> None:
            self.closed = True

    model = ClosingModel()
    monkeypatch.setattr(builder, "build_model", lambda *args, **kwargs: model)
    invalid = replace(_config(tmp_path), protocol="not-a-protocol")

    with pytest.raises(Exception, match="protocol"):
        build_agent_composition(invalid)
    assert model.closed is True


def test_declarative_runner_is_session_first_and_ephemeral_is_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    durable_config = _config(tmp_path)
    composition = build_agent_composition(
        durable_config,
        model_override=_FinalModel(),
        env_override=HostEnv(workspace_root=str(tmp_path)),
    )
    monkeypatch.setattr(builder, "build_agent_composition", lambda *a, **k: composition)
    durable = run_agent_config(durable_config, credential_resolver=object())

    assert durable["execution_mode"] == "process_local_session"
    assert durable["session"]["cross_process"] is False
    assert durable["session"]["session_id"].startswith("session_")
    assert durable["session"]["checkpoint_id"].startswith("checkpoint_")
    assert durable["session"]["config_digest"] == durable_config.digest()

    ephemeral_config = _config(tmp_path, mode="ephemeral")
    ephemeral_composition = build_agent_composition(
        ephemeral_config,
        model_override=_FinalModel(),
        env_override=HostEnv(workspace_root=str(tmp_path)),
    )
    monkeypatch.setattr(
        builder, "build_agent_composition", lambda *a, **k: ephemeral_composition
    )
    ephemeral = run_agent_config(ephemeral_config, credential_resolver=object())

    assert ephemeral["execution_mode"] == "ephemeral"
    assert ephemeral["session"]["durable"] is False
    assert set(ephemeral["session"]["unsupported"]) == {
        "pause",
        "restore",
        "steer",
        "fork",
    }


def test_cli_and_programmatic_golden_paths_share_runtime_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import qitos.config

    config = _config(tmp_path)

    def make_composition() -> Any:
        return build_agent_composition(
            config,
            model_override=_FinalModel(),
            env_override=HostEnv(workspace_root=str(tmp_path)),
        )

    with make_composition() as programmatic:
        session = programmatic.session("same contract")
        programmatic_result = session.run()
        programmatic_facts = {
            "agent": type(programmatic.agent),
            "engine": type(programmatic.engine),
            "runtime": type(programmatic.runtime),
            "config_digest": programmatic.runtime.launch_metadata["config_digest"],
            "tool_policy": programmatic.runtime.launch_metadata["tool_use_policy"],
            "sandbox": programmatic.runtime.launch_metadata["sandbox"],
            "event_sink": type(programmatic.runtime.event_sink),
            "checkpoint": session.current_head.checkpoint_id.value,
        }

    cli_facts: dict[str, Any] = {}

    def cli_composition(*args: Any, **kwargs: Any) -> Any:
        _ = args, kwargs
        composition = make_composition()
        original_session = composition.session

        def capture_session(*session_args: Any, **session_kwargs: Any) -> Any:
            created = original_session(*session_args, **session_kwargs)
            cli_facts.update(
                {
                    "agent": type(composition.agent),
                    "engine": type(composition.engine),
                    "runtime": type(composition.runtime),
                    "config_digest": composition.runtime.launch_metadata[
                        "config_digest"
                    ],
                    "tool_policy": composition.runtime.launch_metadata[
                        "tool_use_policy"
                    ],
                    "sandbox": composition.runtime.launch_metadata["sandbox"],
                    "event_sink": type(composition.runtime.event_sink),
                }
            )
            return created

        composition.session = capture_session
        return composition

    monkeypatch.setattr(qitos.config, "load_agent_config", lambda path: config)
    monkeypatch.setattr(builder, "build_agent_composition", cli_composition)
    assert qit_main(
        ["run", "--config", "logical-agent.yaml", "--task", "same contract"]
    ) == 0
    cli_payload = json.loads(capsys.readouterr().out)

    assert programmatic_result.state.final_result == cli_payload["final_result"]
    assert cli_payload["execution_mode"] == "process_local_session"
    assert cli_payload["session"]["checkpoint_id"].startswith("checkpoint_")
    assert cli_facts == {
        key: value for key, value in programmatic_facts.items() if key != "checkpoint"
    }


def test_config_has_json_safe_owner_extension_slots(tmp_path: Path) -> None:
    path = tmp_path / "agent.yaml"
    path.write_text(
        """schema: qitos.agent
agent: {name: extension-agent}
model:
  provider: openai-compatible
  model: offline
  credential: {ref: offline}
tools: {preset: none, include: [], options: {}, policy: disabled}
runtime:
  environment: {type: unsafe_host, workspace: .}
  session: {mode: durable, store: memory}
budgets: {max_steps: 2, max_runtime_seconds: 10, max_requests: 2}
context: {}
memory: {provider: third-party-memory, policy: bounded}
compaction: {provider: third-party-compactor, threshold: 12}
lifecycle: {policy: cooperative}
failure_policy: {provider: typed, tool: fail_closed}
""",
        encoding="utf-8",
    )
    config = load_agent_config(path)
    composition = build_agent_composition(
        config,
        model_override=_FinalModel(),
        env_override=HostEnv(workspace_root=str(tmp_path)),
    )
    try:
        slots = composition.runtime.launch_metadata["extension_slots"]
        assert slots["memory"]["provider"] == "third-party-memory"
        assert slots["compaction"]["provider"] == "third-party-compactor"
        assert slots["lifecycle"]["policy"] == "cooperative"
        assert slots["failure_policy"]["tool"] == "fail_closed"
    finally:
        composition.close()

    unsafe = replace(config, memory={"factory": lambda: None})
    with pytest.raises(ConfigSchemaError):
        unsafe.canonical_json()


def test_sqlite_pause_clean_restore_and_fork_use_one_session_truth(
    tmp_path: Path,
) -> None:
    config = replace(
        _config(tmp_path),
        tools=(f"{__name__}._remember",),
        tool_use_policy="auto",
        runtime=replace(
            _config(tmp_path).runtime,
            session=SessionConfig(
                mode="durable",
                store="sqlite",
                path=str(tmp_path / "sessions.sqlite3"),
            ),
            trajectory=TrajectoryConfig(enabled=False),
        ),
    )
    with build_agent_composition(
        config,
        model_override=_ActionModel(),
        env_override=HostEnv(workspace_root=str(tmp_path)),
    ) as first:
        first.runtime.lifecycle_policy = _PauseAfterFirstStep()
        parent = first.session("read once and finish")
        parent.run()
        assert parent.lifecycle.value == "paused"
        paused_checkpoint = parent.current_head.checkpoint_id.value
        child = parent.fork(operation_id="fork_1234567890abcdef")
        assert child.session_id != parent.session_id
        assert child.lifecycle.value == "paused"
        parent_id = parent.session_id.value

    with build_agent_composition(
        config,
        model_override=_FinalModel(),
        env_override=HostEnv(workspace_root=str(tmp_path)),
    ) as second:
        restored = second.restore(parent_id)
        result = restored.run()
        assert result.state.final_result == "done"
        assert restored.lifecycle.value == "completed"
        assert restored.current_head.checkpoint_id.value != paused_checkpoint
        assert restored.inspect().head == restored.current_head


@pytest.mark.parametrize("operation", ["pause", "steer"])
def test_cli_rejects_fake_live_process_control(
    operation: str, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = [
        "session",
        operation,
        "--config",
        "unused.yaml",
        "--session-id",
        "session_example",
    ]
    if operation == "steer":
        arguments.extend(["--text", "new direction"])
    assert qit_main(arguments) == 3
    assert "live_session_control_unsupported" in capsys.readouterr().err


def test_cli_help_advertises_session_family(capsys: pytest.CaptureFixture[str]) -> None:
    assert qit_main(["--help"]) == 0
    assert "session" in capsys.readouterr().out


def test_cli_inspects_terminal_session_without_claiming_live_control(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import qitos.config

    config = replace(_config(tmp_path), runtime=replace(
        _config(tmp_path).runtime, session=SessionConfig(
            store="sqlite", path=str(tmp_path / "inspect.sqlite3"))))
    composition = build_agent_composition(
        config,
        model_override=_FinalModel(),
        env_override=HostEnv(workspace_root=str(tmp_path)),
    )
    session = composition.session("complete before inspection")
    session.run()
    monkeypatch.setattr(qitos.config, "load_agent_config", lambda path: config)
    monkeypatch.setattr(
        qitos.config, "build_agent_composition", lambda *args, **kwargs: composition
    )

    assert qit_main(
        [
            "session",
            "inspect",
            "--config",
            "logical-agent.yaml",
            "--session-id",
            session.session_id.value,
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["session_id"] == session.session_id.value
    assert payload["lifecycle"] == "completed"
    assert payload["config_digest"] == config.digest()
    assert "session.restore" in payload["capabilities"]


def test_cli_resumes_sqlite_session_with_restore_time_steering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import qitos.config

    config = replace(
        _config(tmp_path),
        runtime=replace(
            _config(tmp_path).runtime,
            session=SessionConfig(
                mode="durable",
                store="sqlite",
                path=str(tmp_path / "cli-resume.sqlite3"),
            ),
        ),
    )
    with build_agent_composition(
        config,
        model_override=_ActionModel(),
        env_override=HostEnv(workspace_root=str(tmp_path)),
    ) as first:
        first.runtime.lifecycle_policy = _PauseAfterFirstStep()
        paused = first.session("pause for CLI resume")
        paused.run()
        session_id = paused.session_id.value

    resumed = build_agent_composition(
        config,
        model_override=_FinalModel(),
        env_override=HostEnv(workspace_root=str(tmp_path)),
    )
    monkeypatch.setattr(qitos.config, "load_agent_config", lambda path: config)
    monkeypatch.setattr(
        qitos.config, "build_agent_composition", lambda *args, **kwargs: resumed
    )
    assert qit_main(
        [
            "session",
            "resume",
            "--config",
            "logical-agent.yaml",
            "--session-id",
            session_id,
            "--steering",
            "finish now",
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["session_id"] == session_id
    assert payload["lifecycle"] == "completed"
    assert payload["steering_mode"] == "restore_time"


def test_cli_forks_a_persisted_sqlite_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import qitos.config

    config = replace(
        _config(tmp_path),
        runtime=replace(
            _config(tmp_path).runtime,
            session=SessionConfig(
                mode="durable",
                store="sqlite",
                path=str(tmp_path / "cli-fork.sqlite3"),
            ),
        ),
    )
    with build_agent_composition(
        config,
        model_override=_ActionModel(),
        env_override=HostEnv(workspace_root=str(tmp_path)),
    ) as first:
        first.runtime.lifecycle_policy = _PauseAfterFirstStep()
        parent = first.session("pause for CLI fork")
        parent.run()
        session_id = parent.session_id.value

    restored = build_agent_composition(
        config,
        model_override=_FinalModel(),
        env_override=HostEnv(workspace_root=str(tmp_path)),
    )
    monkeypatch.setattr(qitos.config, "load_agent_config", lambda path: config)
    monkeypatch.setattr(
        qitos.config, "build_agent_composition", lambda *args, **kwargs: restored
    )
    assert qit_main(
        [
            "session",
            "fork",
            "--config",
            "logical-agent.yaml",
            "--session-id",
            session_id,
        ]
    ) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_session_id"] == session_id
    assert payload["session_id"] != session_id
    assert payload["checkpoint_id"].startswith("checkpoint_")


def test_lane_a_manifest_binds_committed_paths_and_digests() -> None:
    root = Path(__file__).resolve().parents[1]
    fixture_root = root / "tests" / "fixtures" / "s4" / "lane_a"
    manifest = json.loads((fixture_root / "producer-manifest.json").read_text())
    assert manifest["source_commit"] == "65718ee782065e7dccc3b3d0a5e7ea9a318b5411"
    for artifact in manifest["artifacts"]:
        path = root / artifact["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]

    rendered = "\n".join(
        path.read_text(encoding="utf-8")
        for path in fixture_root.iterdir()
        if path.is_file()
    )
    assert "/Users/" not in rendered
    assert "HostEnv" not in (
        fixture_root / "programmatic-golden-path.py"
    ).read_text(encoding="utf-8")
