"""Canonical-config live qualification runner tests."""

from __future__ import annotations

import importlib.util
import sys
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
        f"""schema: qitos.agent/v1
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
        "name": "reachable_g4_live_passed",
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


def test_native_calls_never_parse_assistant_text() -> None:
    module = _module()
    response = {
        "choices": [
            {
                "message": {
                    "content": '{"tool_calls":[{"function":{"name":"fake"}}]}',
                    "tool_calls": None,
                }
            }
        ]
    }
    assert module._native_calls(response) == []


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
    from qitos.kit.env import HostEnv

    def fake_build(config: object, **kwargs: object) -> object:
        class FakeModel:
            model = "fake"

            def call_raw(self, messages: object, **options: object) -> object:
                _ = messages, options
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

        return real_build(
            config,
            model_override=FakeModel(),
            env_override=HostEnv(workspace_root=str(workspace)),
        )

    monkeypatch.setattr("qitos.config.builder.build_agent_composition", fake_build)
    seen: list[str] = []

    def fake_restore(**kwargs: object) -> dict[str, object]:
        session_id = str(kwargs["session_id"])
        seen.append(session_id)
        return {
            "session_id": session_id,
            "status": "passed",
            "requests": 1,
            "tool_calls": {"read_file": 1},
            "credential": {"resolver": "local_file"},
        }

    monkeypatch.setattr(module, "_run_restore_subprocess", fake_restore)
    receipt = module._live_restore_workflows(
        profile, credentials_path=tmp_path / "not-read.yaml"
    )

    assert receipt["status"] == "passed"
    assert receipt["multi_agent"]["child_count"] == 2
    assert receipt["multi_agent"]["context_transfer_receipts"] == 2
    assert receipt["multi_agent"]["fan_out_lineage_distinct"] is True
    assert len(seen) == 3
