"""Strict canonical AgentConfig and composition-root tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qitos.config import (
    AgentConfig,
    CredentialRef,
    DatasetItem,
    FakeCredentialResolver,
    ModelConfig,
    build_model,
    build_agent_composition,
    build_run_spec,
    build_tool_registry,
    load_agent_config,
    resolve_env_vars,
)
from qitos.config.errors import (
    ConfigSchemaError,
    ConfigSyntaxError,
    MissingEnvironmentVariableError,
    ProtocolParserMismatchError,
    UnknownConfigFieldError,
    UnsafeHostConfigurationError,
)


CANONICAL = """
schema: qitos.agent
agent:
  name: test-agent
  protocol: react_text_v1
  parser: auto
  seed: 7
model:
  provider: openai_compatible
  model: test-model
  base_url: https://example.invalid/v1/chat/completions
  credential:
    ref: test-credential
  api_mode: chat_completions
  context_window: 32768
  request:
    temperature: 0.2
    top_p: 0.9
    max_tokens: 512
    timeout_seconds: 30
    extra_body:
      chat_template_kwargs:
        thinking: false
tools:
  preset: env_coding
  include: []
  options: {}
  policy: auto
runtime:
  environment:
    type: unsafe_host
    workspace: .
  session:
    enabled: false
    store: memory
  trajectory:
    enabled: false
    output: ./runs
    privacy: private
budgets:
  max_steps: 4
  max_runtime_seconds: 60
  max_requests: 8
context: {}
metadata:
  purpose: test
dataset:
  - task: verify fixture
    expected: done
"""


def _write(path: Path, text: str = CANONICAL) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_load_canonical_config_and_source_identity(tmp_path: Path) -> None:
    config = load_agent_config(_write(tmp_path / "agent.yaml"))

    assert config.name == "test-agent"
    assert config.max_steps == 4
    assert config.model.credential == CredentialRef("test-credential")
    assert config.tool_preset == "env_coding"
    assert config.runtime.environment.type == "unsafe_host"
    assert config.dataset[0].task == "verify fixture"
    assert config.source["name"] == "agent.yaml"
    assert len(config.source["sha256"]) == 64
    assert config.runtime.session.mode == "ephemeral"
    assert any(
        item["code"] == "session_enabled_compatibility"
        for item in config.compatibility
    )


def test_session_defaults_to_durable_and_ephemeral_is_named(tmp_path: Path) -> None:
    durable = CANONICAL.replace(
        "enabled: false\n    store: memory", "mode: durable\n    store: memory"
    )
    config = load_agent_config(_write(tmp_path / "durable.yaml", durable))
    assert config.runtime.session.mode == "durable"
    assert config.runtime.session.enabled is True
    assert not any(
        item["code"] == "session_enabled_compatibility"
        for item in config.compatibility
    )

    ephemeral = durable.replace("mode: durable", "mode: ephemeral")
    config = load_agent_config(_write(tmp_path / "ephemeral.yaml", ephemeral))
    assert config.runtime.session.mode == "ephemeral"
    assert config.runtime.session.enabled is False


@pytest.mark.parametrize(
    "session_text",
    [
        "mode: unknown\n    store: memory",
        "mode: durable\n    store: unsupported",
        "mode: ephemeral\n    store: memory\n    restore: true",
        "mode: ephemeral\n    store: memory\n    session_id: session_bad",
        "mode: durable\n    enabled: false\n    store: memory",
    ],
)
def test_session_configuration_fails_closed(
    tmp_path: Path, session_text: str
) -> None:
    invalid = CANONICAL.replace(
        "enabled: false\n    store: memory", session_text
    )
    with pytest.raises(ConfigSchemaError):
        load_agent_config(_write(tmp_path / "invalid-session.yaml", invalid))


def test_canonical_serialization_is_stable_json_safe_and_secret_free(
    tmp_path: Path,
) -> None:
    config = load_agent_config(_write(tmp_path / "agent.yaml"))
    first = config.canonical_json()
    second = config.canonical_json()

    assert first == second
    assert config.digest() == config.digest()
    payload = json.loads(first)
    assert payload["model"]["credential"] == {"ref": "test-credential"}
    assert "api_key" not in first
    assert "secret" not in first.lower()


def test_loaded_config_is_deeply_immutable_and_digest_is_format_independent(
    tmp_path: Path,
) -> None:
    first = load_agent_config(_write(tmp_path / "first.yaml"))
    second_text = CANONICAL.replace("metadata:\n  purpose: test", "metadata: {purpose: test}")
    second = load_agent_config(_write(tmp_path / "second.yaml", second_text))

    assert first.digest() == second.digest()
    with pytest.raises(TypeError):
        first.metadata["purpose"] = "changed"  # type: ignore[index]
    with pytest.raises(TypeError):
        first.model.request.extra_body["new"] = True  # type: ignore[index]
    with pytest.raises(AttributeError):
        first.tools.append("unsafe")  # type: ignore[attr-defined]


def test_v1_schema_is_reader_only_and_writes_canonical_identity(tmp_path: Path) -> None:
    legacy = CANONICAL.replace("schema: qitos.agent", "schema: qitos.agent/v1")
    config = load_agent_config(_write(tmp_path / "legacy.yaml", legacy))

    assert config.schema == "qitos.agent"
    assert json.loads(config.canonical_json())["schema"] == "qitos.agent"
    assert any(
        item["code"] == "agent_schema_revision_compatibility"
        for item in config.compatibility
    )


def test_unsafe_host_rejects_unenforceable_sandbox_claims(tmp_path: Path) -> None:
    invalid = CANONICAL.replace(
        "type: unsafe_host\n    workspace: .",
        "type: unsafe_host\n    workspace: .\n    network: none",
    )
    with pytest.raises(UnsafeHostConfigurationError) as caught:
        load_agent_config(_write(tmp_path / "invalid.yaml", invalid))
    assert caught.value.code == "unsafe_host_constraint_rejected"


def test_explicit_protocol_parser_mismatch_is_typed(tmp_path: Path) -> None:
    mismatch = CANONICAL.replace("parser: auto", "parser: JsonDecisionParser")
    config = load_agent_config(_write(tmp_path / "mismatch.yaml", mismatch))
    from qitos.kit.env import HostEnv

    with pytest.raises(ProtocolParserMismatchError) as caught:
        build_agent_composition(
            config,
            model_override=object(),
            env_override=HostEnv(workspace_root=str(tmp_path)),
        )
    assert caught.value.code == "protocol_parser_mismatch"


def test_sanitized_receipt_uses_digests_and_omits_private_locations(
    tmp_path: Path,
) -> None:
    config = load_agent_config(_write(tmp_path / "agent.yaml"))
    receipt = config.receipt()
    rendered = json.dumps(receipt, sort_keys=True)

    assert receipt == config.sanitized_dict()
    assert receipt["config_digest"] == config.digest()
    assert len(receipt["model"]["endpoint_digest"]) == 64
    assert len(receipt["model"]["credential_reference_digest"]) == 64
    assert "https://example.invalid" not in rendered
    assert str(tmp_path) not in rendered
    assert "test-credential" not in rendered


@pytest.mark.parametrize(
    "text",
    [
        CANONICAL + "unknown: true\n",
        CANONICAL.replace("  name: test-agent", "  name: test-agent\n  typo: true"),
        CANONICAL.replace("    max_tokens: 512", "    max_tokens: '512'"),
        CANONICAL.replace("  max_steps: 4", "  max_steps: true"),
        CANONICAL.replace("context: {}", "context:\n  unknown_policy: true"),
        CANONICAL.replace("context: {}", "context:\n  warning_ratio: '0.8'"),
    ],
)
def test_unknown_fields_and_ambiguous_types_fail_closed(
    tmp_path: Path, text: str
) -> None:
    with pytest.raises((UnknownConfigFieldError, ConfigSchemaError)):
        load_agent_config(_write(tmp_path / "bad.yaml", text))


def test_duplicate_keys_fail_closed(tmp_path: Path) -> None:
    text = CANONICAL.replace("  name: test-agent", "  name: test-agent\n  name: other")
    with pytest.raises(ConfigSyntaxError):
        load_agent_config(_write(tmp_path / "duplicate.yaml", text))


def test_unsafe_yaml_tag_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ConfigSyntaxError):
        load_agent_config(
            _write(tmp_path / "unsafe.yaml", "!!python/object/apply:os.system ['id']\n")
        )


def test_environment_interpolation_is_not_the_canonical_path(tmp_path: Path) -> None:
    text = CANONICAL.replace("ref: test-credential", "ref: ${QITOS_TEST_CREDENTIAL}")
    with pytest.raises(ConfigSchemaError, match="compatibility-only"):
        load_agent_config(_write(tmp_path / "env.yaml", text))


def test_resolve_env_vars_missing_is_typed_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QITOS_NOT_PRESENT", raising=False)
    with pytest.raises(MissingEnvironmentVariableError):
        resolve_env_vars("${QITOS_NOT_PRESENT}")


def test_resolve_env_vars_compatibility_emits_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QITOS_NOT_PRESENT", raising=False)
    receipts: list[dict[str, object]] = []
    assert (
        resolve_env_vars(
            "x=${QITOS_NOT_PRESENT}",
            strict=False,
            compatibility_receipts=receipts,
        )
        == "x="
    )
    assert receipts == [
        {
            "code": "missing_environment_substituted_empty",
            "variable": "QITOS_NOT_PRESENT",
            "warning": True,
        }
    ]


def test_legacy_flat_config_requires_explicit_compatibility(tmp_path: Path) -> None:
    path = _write(tmp_path / "legacy.yaml", "name: old\nmax_steps: 3\n")
    with pytest.raises(ConfigSchemaError):
        load_agent_config(path)
    config = load_agent_config(path, compatibility=True)
    assert config.name == "old"
    assert config.compatibility[0]["code"] == "legacy_flat_agent_config"


def test_build_model_uses_resolved_secret_only_at_factory_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def _create(provider: str, **params: object) -> object:
        seen.update({"provider": provider, **params})
        return type("Model", (), {})()

    monkeypatch.setattr("qitos.config.builder.ModelFactory.create", _create)
    model = build_model(
        ModelConfig(
            provider="openai_compatible",
            model="demo",
            base_url="https://example.invalid/v1/chat/completions",
            credential=CredentialRef("demo-ref"),
        ),
        credential_resolver=FakeCredentialResolver({"demo-ref": "private-value"}),
    )

    assert seen["provider"] == "openai-compatible"
    assert seen["api_key"] == "private-value"
    assert seen["base_url"] == "https://example.invalid/v1"
    assert getattr(model, "qitos_credential_receipt")["ref"] == "demo-ref"
    assert "private-value" not in repr(getattr(model, "qitos_credential_receipt"))


def test_build_run_spec_contains_config_identity() -> None:
    config = AgentConfig(
        name="test",
        model=ModelConfig(model="gpt-4o"),
        seed=42,
    )
    spec = build_run_spec(config)
    assert spec.seed == 42
    assert spec.metadata["agent_config_digest"] == config.digest()


def test_one_config_composes_matching_model_tools_env_runtime_and_budget(
    tmp_path: Path,
) -> None:
    config = load_agent_config(_write(tmp_path / "agent.yaml"))
    model = object()
    from qitos.kit.env import HostEnv

    env = HostEnv(workspace_root=str(tmp_path))
    composition = build_agent_composition(
        config,
        model_override=model,
        env_override=env,
    )
    try:
        assert composition.config is config
        assert composition.model is model
        assert composition.agent.llm is model
        assert composition.env is env
        assert composition.engine.env is env
        assert composition.engine.runtime is composition.runtime
        assert composition.engine.budget.max_steps == config.budgets.max_steps
        assert set(composition.tool_registry.list_tools()) == {
            "grep_file",
            "edit_file",
            "list_files",
            "poll_process",
            "read_file",
            "run_command",
            "run_test",
            "start_process",
            "terminate_process",
            "write_file",
        }
    finally:
        composition.close()


def test_env_coding_preset_is_the_bounded_runtime_tool_surface() -> None:
    config = AgentConfig(name="test", tool_preset="env_coding")
    registry = build_tool_registry(config)
    assert set(registry.list_tools()) == {
        "grep_file",
        "edit_file",
        "list_files",
        "poll_process",
        "read_file",
        "run_command",
        "run_test",
        "start_process",
        "terminate_process",
        "write_file",
    }


def test_programmatic_config_dataset_remains_available() -> None:
    config = AgentConfig(dataset=[DatasetItem(task="hello", expected="world")])
    assert config.dataset[0].task == "hello"
