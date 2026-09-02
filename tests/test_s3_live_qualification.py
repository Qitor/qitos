"""Canonical-config live qualification runner tests."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "qualify_s3_live.py"


def _module():
    spec = importlib.util.spec_from_file_location("qualify_s3_live", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _config(path: Path, *, profile: str, credential: str, workspace: Path) -> Path:
    path.write_text(
        f"""schema: qitos.agent
agent:
  name: {profile}
  protocol: react_text_v1
model:
  provider: openai_compatible
  model: test-model
  base_url: https://example.invalid/v1/chat/completions
  credential:
    ref: {credential}
  request:
    temperature: 0.0
    max_tokens: 128
    timeout_seconds: 10
tools:
  preset: env_coding
runtime:
  environment:
    type: docker
    image: openclaw:staged
    workspace: {workspace}
    network: none
    read_only_root: true
  session:
    enabled: true
    store: sqlite
    path: {workspace / 'sessions.sqlite3'}
budgets:
  max_steps: 4
  max_runtime_seconds: 60
  max_requests: 12
dataset:
  - task: inspect fixture with read_file, then finish
""",
        encoding="utf-8",
    )
    return path


def test_configs_are_the_only_profile_source(tmp_path: Path) -> None:
    module = _module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "fixture.py").write_text("VALUE = 1\n", encoding="utf-8")
    paths = [
        _config(
            tmp_path / f"{index}.yaml",
            profile=f"profile-{index}",
            credential=f"credential-{index}",
            workspace=workspace,
        )
        for index in range(3)
    ]

    profiles = module.load_profiles(paths)

    assert [item.profile_id for item in profiles] == [
        "profile-0",
        "profile-1",
        "profile-2",
    ]
    assert [item.credential_ref for item in profiles] == [
        "credential-0",
        "credential-1",
        "credential-2",
    ]
    assert all(len(item.config.digest()) == 64 for item in profiles)


def test_live_flag_blocks_before_credentials_are_read(tmp_path: Path) -> None:
    module = _module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "fixture.py").write_text("VALUE = 1\n", encoding="utf-8")
    profile = module.load_profiles(
        [
            _config(
                tmp_path / "agent.yaml",
                profile="profile",
                credential="credential",
                workspace=workspace,
            )
        ]
    )

    result = module.qualify(
        profile,
        live=False,
        source_commit="1" * 40,
        credentials_path=tmp_path / "must-not-be-read.yaml",
        generated_at="2026-09-01T00:00:00+00:00",
        execute_offline_gates=False,
        enforce_current_source=False,
    )

    assert result["offline"]["count"] == 16
    assert result["decision"]["g4_live"] == "live_flag_required"
    assert result["totals"]["requests"] == 0
    assert result["profiles"] == []
    assert result["privacy"]["scan_passed"] is True
    module.verify_evidence(result)


def test_offline_gate_ledger_has_all_required_reachable_gates(tmp_path: Path) -> None:
    module = _module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "fixture.py").write_text("VALUE = 1\n", encoding="utf-8")
    profiles = module.load_profiles(
        [
            _config(
                tmp_path / "agent.yaml",
                profile="profile",
                credential="credential",
                workspace=workspace,
            )
        ]
    )

    report = module.run_offline_gates(profiles, execute_external=False)

    assert report["status"] == "passed"
    assert report["count"] == 16
    assert report["gates"][-1] == {
        "index": 16,
        "name": "privacy_path_and_cleanup_failures",
        "status": "passed",
    }


def test_profile_ids_and_credential_refs_must_be_distinct(tmp_path: Path) -> None:
    module = _module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "fixture.py").write_text("VALUE = 1\n", encoding="utf-8")
    paths = [
        _config(
            tmp_path / f"{index}.yaml",
            profile="duplicate",
            credential=f"credential-{index}",
            workspace=workspace,
        )
        for index in range(2)
    ]
    with pytest.raises(module.QualificationConfigurationError, match="distinct"):
        module.load_profiles(paths)


def test_private_evidence_must_be_outside_repository(tmp_path: Path) -> None:
    module = _module()
    with pytest.raises(module.QualificationConfigurationError, match="outside"):
        module._validate_private_dir(ROOT / "private-live-evidence")

    outside = module._validate_private_dir(tmp_path / "private")
    assert outside.is_dir()
    assert outside.stat().st_mode & 0o777 == 0o700


def test_private_round_receipt_is_exclusive_and_immutable(tmp_path: Path) -> None:
    module = _module()
    receipt = tmp_path / "s3-g4-l3-round.json"
    first = {"qualification_round_id": "s3-g4-l3-round", "requests": 0}

    module._write_json(receipt, first, mode=0o600, exclusive=True)

    assert json.loads(receipt.read_text(encoding="utf-8")) == first
    assert receipt.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        module._write_json(
            receipt,
            {"qualification_round_id": "s3-g4-l3-round", "requests": 1},
            mode=0o600,
            exclusive=True,
        )
    assert json.loads(receipt.read_text(encoding="utf-8")) == first


def test_live_runner_has_no_private_provider_payload_preflight() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "def _native_calls" not in source
    assert 'tool_choice="required"' not in source
    assert "_call(model" not in source


def test_privacy_scan_rejects_values_paths_endpoints_and_auth_markers() -> None:
    module = _module()
    report = module._privacy_report(
        {
            "value": (
                "Bearer top-secret https://example.invalid/v1/chat/completions "
                "/Users/private/file"
            )
        },
        ["top-secret"],
    )

    assert report["scan_passed"] is False
    assert report["credential_values_absent"] is False
    assert report["raw_endpoints_absent"] is False
    assert report["host_paths_absent"] is False

    endpoint_only = module._privacy_report(
        {"location": "https://example.invalid/v1"},
        [],
    )
    assert endpoint_only["scan_passed"] is False


def test_evidence_digest_detects_mutation(tmp_path: Path) -> None:
    module = _module()
    payload = {
        "runner_digest": module._sha256_bytes(SCRIPT.read_bytes()),
        "decision": {"g4_live": "live_flag_required"},
    }
    payload["evidence_digest"] = module._evidence_digest(payload)
    module.verify_evidence(payload)
    payload["decision"]["g4_live"] = "passed"
    with pytest.raises(module.QualificationConfigurationError, match="evidence"):
        module.verify_evidence(payload)


def test_missing_local_credential_is_typed_before_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    profile = module.load_profiles(
        [
            _config(
                tmp_path / "agent.yaml",
                profile="profile",
                credential="missing",
                workspace=workspace,
            )
        ]
    )
    credentials = tmp_path / "credentials.yaml"
    credentials.write_text("credentials:\n  present: value\n", encoding="utf-8")
    credentials.chmod(0o600)
    sandbox_called = False

    def fail_if_called(*args: object, **kwargs: object) -> object:
        nonlocal sandbox_called
        sandbox_called = True
        raise AssertionError("sandbox must not start")

    monkeypatch.setattr(
        "qitos.kit.env.docker_qualification.qualify_docker_environment",
        fail_if_called,
    )
    result = module.qualify(
        profile,
        live=True,
        source_commit="1" * 40,
        credentials_path=credentials,
        execute_offline_gates=False,
        enforce_current_source=False,
    )

    assert result["decision"]["g4_live"] == "configuration_error"
    assert result["profiles"][0]["error_code"] == "configuration_error"
    assert result["totals"]["requests"] == 0
    assert sandbox_called is False


def test_provider_failure_taxonomy_and_attempt_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    profile = module.load_profiles(
        [
            _config(
                tmp_path / "agent.yaml",
                profile="profile",
                credential="credential",
                workspace=workspace,
            )
        ]
    )[0]

    class TimeoutModel:
        qitos_credential_receipt: dict[str, object] = {}

        def call_raw(self, messages: object, **kwargs: object) -> object:
            raise TimeoutError("bounded timeout")

    monkeypatch.setattr("qitos.config.builder.build_model", lambda *args, **kwargs: TimeoutModel())
    receipt = module._preflight_profile(profile, object())

    assert receipt["status"] == "failed"
    assert receipt["error_code"] == "timeout"
    assert receipt["requests"] == 1


def test_live_workflow_builds_two_child_fan_out_transfers_and_join(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = _config(
        tmp_path / "agent.yaml",
        profile="profile",
        credential="credential",
        workspace=workspace,
    )
    profile = module.load_profiles([path])[0]
    from qitos.config.builder import build_agent_composition as real_build
    from qitos.config import EnvironmentConfig
    from qitos.kit.env import HostEnv
    model_calls = 0

    def fake_build(config: object, **kwargs: object) -> object:
        class FakeModel:
            model = "fake"

            def call_raw(self, messages: object, **options: object) -> object:
                nonlocal model_calls
                _ = messages, options
                model_calls += 1
                if model_calls == 1:
                    return {
                        "choices": [
                            {
                                "finish_reason": "tool_calls",
                                "message": {"content": None, "tool_calls": []},
                            }
                        ]
                    }
                return {
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "read-parent",
                                        "type": "function",
                                        "function": {
                                            "name": "read_file",
                                            "arguments": '{"path":"README.md"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }

        unsafe_config = replace(
            config,
            runtime=replace(
                config.runtime,
                environment=EnvironmentConfig(
                    type="unsafe_host",
                    image="",
                    workspace=str(workspace),
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
            ),
        )
        return real_build(
            unsafe_config,
            model_override=FakeModel(),
            env_override=HostEnv(workspace_root=str(workspace)),
        )

    monkeypatch.setattr("qitos.config.builder.build_agent_composition", fake_build)
    seen: list[str] = []
    remaining_limits: list[int] = []

    def fake_restore(**kwargs: object) -> dict[str, object]:
        session_id = str(kwargs["session_id"])
        seen.append(session_id)
        remaining_limits.append(int(kwargs["max_requests"]))
        return {
            "session_id": session_id,
            "status": "passed",
            "requests": 1,
            "tool_calls": {"read_file": 1},
            "credential": {"resolver": "local_file"},
            "sandbox": {"cleanup": "passed"},
        }

    monkeypatch.setattr(module, "_run_restore_subprocess", fake_restore)
    monkeypatch.setattr(
        module,
        "_verify_live_artifacts",
        lambda *args, **kwargs: {"status": "passed"},
    )
    monkeypatch.setattr(
        module,
        "_close_live_parent_join",
        lambda *args, **kwargs: {
            "status": "passed",
            "state": "closed",
            "generation": 2,
            "duplicate_disposition": "duplicate_ignored",
            "sandbox_cleanup": True,
        },
    )
    receipt = module._live_restore_workflows(
        profile, credentials_path=tmp_path / "not-read.yaml"
    )
    repeated = module._live_restore_workflows(
        profile, credentials_path=tmp_path / "not-read.yaml"
    )

    assert receipt["status"] == "passed"
    assert repeated["status"] == "passed"
    assert receipt["multi_agent"]["child_count"] == 2
    assert repeated["multi_agent"]["child_count"] == 2
    assert receipt["multi_agent"]["context_transfer_receipts"] == 2
    assert receipt["multi_agent"]["fan_out_lineage_distinct"] is True
    assert receipt["multi_agent"]["join"]["state"] == "closed"
    assert receipt["multi_agent"]["join"]["generation"] == 2
    assert len(seen) == 6
    assert remaining_limits[:3] == sorted(remaining_limits[:3], reverse=True)
    assert remaining_limits[3:] == sorted(remaining_limits[3:], reverse=True)
    assert len(set(remaining_limits[:3])) == 3
    assert len(set(remaining_limits[3:])) == 3
    assert model_calls >= 5


def test_exception_error_projection_preserves_session_code_without_echo() -> None:
    module = _module()
    from qitos.core.session import (
        SessionContractError,
        SessionErrorCode,
    )

    error = SessionContractError(
        SessionErrorCode.DUPLICATE_FORK_OPERATION,
        "Bearer rejected-secret /Users/private/launch.yaml",
        recoverable=False,
        remediation="do not echo",
    )

    projected = module._exception_error_code(error, "workflow_failure")

    assert projected == "duplicate_fork_operation"
    assert "rejected-secret" not in projected
    assert "/Users/" not in projected


def test_live_workflow_preserves_codec_root_failure_before_pause_or_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    profile = module.load_profiles(
        [
            _config(
                tmp_path / "agent.yaml",
                profile="profile",
                credential="credential",
                workspace=workspace,
            )
        ]
    )[0]
    from qitos.config import EnvironmentConfig
    from qitos.config.builder import build_agent_composition as real_build
    from qitos.kit.env import HostEnv

    dispatches = 0

    class FakeModel:
        model = "fake"
        default_request_kwargs = {"chat_template_kwargs": {"invalid": object()}}

        def call_raw(self, messages: object, **options: object) -> object:
            nonlocal dispatches
            _ = messages, options
            dispatches += 1
            return "Final Answer: unreachable"

    def fake_build(config: object, **kwargs: object) -> object:
        unsafe_config = replace(
            config,
            runtime=replace(
                config.runtime,
                environment=EnvironmentConfig(
                    type="unsafe_host",
                    image="",
                    workspace=str(workspace),
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
            ),
        )
        return real_build(
            unsafe_config,
            model_override=FakeModel(),
            env_override=HostEnv(workspace_root=str(workspace)),
        )

    monkeypatch.setattr("qitos.config.builder.build_agent_composition", fake_build)

    receipt = module._live_restore_workflows(
        profile,
        credentials_path=tmp_path / "not-read.yaml",
    )

    assert receipt["status"] == "failed"
    assert receipt["error_code"] == "codec_transport_options_invalid"
    assert receipt["root_error_code"] == "codec_transport_options_invalid"
    assert receipt["lifecycle_consequence"] == "failed"
    assert receipt["pause_reached"] is False
    assert receipt["provider_request_sent"] is False
    assert receipt["requests"] == 0
    assert dispatches == 0


def test_restore_subprocess_preserves_typed_failure_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    completed = subprocess.CompletedProcess(
        args=["restore-worker"],
        returncode=1,
        stdout=json.dumps(
            {
                "session_id": "session-safe",
                "status": "failed",
                "error_code": "protocol_error",
                "requests": 2,
            }
        ),
        stderr="private provider detail",
    )
    calls: list[list[str]] = []

    def fake_run(args: list[str], **kwargs: object) -> object:
        calls.append(args)
        return completed

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    receipt = module._run_restore_subprocess(
        config_path=tmp_path / "agent.yaml",
        credentials_path=tmp_path / "credentials.yaml",
        session_id="session-safe",
        max_requests=2,
    )

    assert receipt == {
        "session_id": "session-safe",
        "status": "failed",
        "error_code": "protocol_error",
        "requests": 2,
        "request_count_exact": True,
    }
    assert "private provider detail" not in json.dumps(receipt)
    assert calls[0][-2:] == ["--max-requests", "2"]


def test_step_budget_failure_keeps_typed_root_cause() -> None:
    module = _module()

    class State:
        final_result = None
        stop_reason = "budget_steps"

    class Result:
        error_code = None
        state = State()

    assert (
        module._engine_result_error_code(Result())
        == "engine_step_budget_exhausted"
    )


def test_pause_policy_targets_first_successful_boundary_per_session() -> None:
    module = _module()
    policy = module._PauseFirstSuccessfulBoundary()

    class Identity:
        def __init__(self, value: str) -> None:
            self.value = value

    class Handle:
        def __init__(self, value: str) -> None:
            self.session_id = Identity(value)

    class EngineStub:
        def __init__(self, value: str) -> None:
            self._session_handle = Handle(value)

    class Context:
        def __init__(self, value: str, step_id: int) -> None:
            self.engine = EngineStub(value)
            self.step_id = step_id

    recovered = Context("session-recovered", 4)
    assert policy.should_pause(recovered) is True
    policy.pause_safety(recovered)
    assert policy.should_pause(Context("session-recovered", 5)) is False
    assert policy.should_pause(Context("session-parent", 0)) is True


def test_model_request_counter_fails_before_exceeding_limit() -> None:
    module = _module()

    class Model:
        def call_raw(self) -> str:
            return "ok"

    model = Model()
    counter = module._count_model_requests(model, max_attempts=1)

    assert model.call_raw() == "ok"
    with pytest.raises(module.QualificationError) as exc_info:
        model.call_raw()

    assert exc_info.value.code == "request_budget_exhausted"
    assert counter == {"attempts": 1}


def test_primary_failure_stops_parity_and_capability_profiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "fixture.py").write_text("VALUE = 1\n", encoding="utf-8")
    profile_ids = ("sii-glm-5-2", "sii-dsv4", "sii-qwen3-8-27b")
    profiles = module.load_profiles(
        [
            _config(
                tmp_path / f"{index}.yaml",
                profile=profile_id,
                credential=f"credential-{index}",
                workspace=workspace,
            )
            for index, profile_id in enumerate(profile_ids)
        ]
    )
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    credentials = private / "credentials.yaml"
    credentials.write_text(
        "credentials:\n"
        "  credential-0: private-zero\n"
        "  credential-1: private-one\n"
        "  credential-2: private-two\n",
        encoding="utf-8",
    )
    credentials.chmod(0o600)

    class PassedSandbox:
        status = "passed"

        def to_dict(self) -> dict[str, object]:
            return {"status": "passed"}

    monkeypatch.setattr(
        "qitos.kit.env.docker_qualification.qualify_docker_environment",
        lambda *args, **kwargs: PassedSandbox(),
    )
    monkeypatch.setattr(
        module,
        "_prepare_coding_fixture",
        lambda profile: {"status": "prepared"},
    )
    called: list[str] = []

    def failed_primary(profile: object, **kwargs: object) -> dict[str, object]:
        _ = kwargs
        called.append(profile.profile_id)
        return {
            "status": "failed",
            "requests": 1,
            "error_code": "provider_timeout",
        }

    monkeypatch.setattr(module, "_live_restore_workflows", failed_primary)
    result = module.qualify(
        profiles,
        live=True,
        source_commit="1" * 40,
        credentials_path=credentials,
        execute_offline_gates=False,
        enforce_current_source=False,
    )

    assert called == ["sii-glm-5-2"]
    assert result["profiles"][0]["status"] == "failed"
    assert result["profiles"][1]["status"] == "not_started"
    assert result["profiles"][2]["status"] == "not_started"
    assert result["decision"]["g4_live"] == "provider_timeout"


def test_informational_smoke_accepts_one_glm_without_promoting_capability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_path = _config(
        tmp_path / "glm.yaml",
        profile="sii-glm-5-2",
        credential="credential-glm",
        workspace=workspace,
    )
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "max_requests: 12", "max_requests: 3"
        ),
        encoding="utf-8",
    )
    profiles = module.load_profiles([config_path])
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    credentials = private / "credentials.yaml"
    credentials.write_text(
        "credentials:\n  credential-glm: private-value\n",
        encoding="utf-8",
    )
    credentials.chmod(0o600)

    class PassedSandbox:
        status = "passed"

        def to_dict(self) -> dict[str, object]:
            return {"status": "passed"}

    monkeypatch.setattr(
        "qitos.kit.env.docker_qualification.qualify_docker_environment",
        lambda *args, **kwargs: PassedSandbox(),
    )
    monkeypatch.setattr(
        module,
        "_informational_smoke_profile",
        lambda *args, **kwargs: {
            "profile_id": "sii-glm-5-2",
            "status": "provider_unavailable",
            "requests": 1,
            "framework_invariant_failure": False,
        },
    )

    result = module.qualify(
        profiles,
        live=True,
        source_commit="1" * 40,
        credentials_path=credentials,
        execute_offline_gates=False,
        enforce_current_source=False,
        informational_smoke=True,
    )

    assert result["totals"]["requests"] == 1
    assert result["decision"]["live_agent_capability_matrix"] == "informational"
    assert result["decision"]["glm_smoke"] == "provider_unavailable"
    assert result["decision"]["s3_status"] == "unchanged"
    assert result["decision"]["s4_ready"] is False


def test_informational_smoke_preserves_typed_root_when_runner_boundary_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_path = _config(
        tmp_path / "glm.yaml",
        profile="sii-glm-5-2",
        credential="credential-glm",
        workspace=workspace,
    )
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "max_requests: 12", "max_requests: 3"
        ),
        encoding="utf-8",
    )
    profiles = module.load_profiles([config_path])
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    credentials = private / "credentials.yaml"
    credentials.write_text(
        "credentials:\n  credential-glm: private-value\n",
        encoding="utf-8",
    )
    credentials.chmod(0o600)

    class PassedSandbox:
        status = "passed"

        def to_dict(self) -> dict[str, object]:
            return {"status": "passed"}

    class TypedProviderFailure(RuntimeError):
        error_code = "provider_connection_failed"

    monkeypatch.setattr(
        "qitos.kit.env.docker_qualification.qualify_docker_environment",
        lambda *args, **kwargs: PassedSandbox(),
    )
    monkeypatch.setattr(
        module,
        "_informational_smoke_profile",
        lambda *args, **kwargs: (_ for _ in ()).throw(TypedProviderFailure()),
    )

    result = module.qualify(
        profiles,
        live=True,
        source_commit="1" * 40,
        credentials_path=credentials,
        execute_offline_gates=False,
        enforce_current_source=False,
        informational_smoke=True,
    )

    receipt = result["profiles"][0]
    assert receipt["root_error_code"] == "provider_connection_failed"
    assert receipt["root_error_code"] != "informational_smoke_runtime_failed"
    assert receipt["framework_invariant_failure"] is True


def test_informational_outcome_separates_external_provider_failure() -> None:
    module = _module()

    assert module._informational_outcome(
        "provider_connection_failed", framework_invariant_failure=False
    ) == "provider_unavailable"
    assert module._informational_outcome(
        "provider_connection_failed", framework_invariant_failure=True
    ) == "framework_invariant_failure"
