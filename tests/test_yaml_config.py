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
    UnknownConfigFieldError,
)


CANONICAL = """
schema: qitos.agent/v1
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
runtime:
  environment:
    type: host
    workspace: .
    network: none
    read_only_root: true
  session:
    enabled: false
    store: memory
  trajectory:
    enabled: true
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
    assert config.runtime.environment.type == "host"
    assert config.dataset[0].task == "verify fixture"
    assert config.source["name"] == "agent.yaml"
    assert len(config.source["sha256"]) == 64


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
    env = object()
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
            "list_files",
            "read_file",
            "run_command",
            "write_file",
        }
    finally:
        composition.close()


def test_env_coding_preset_is_the_bounded_runtime_tool_surface() -> None:
    config = AgentConfig(name="test", tool_preset="env_coding")
    registry = build_tool_registry(config)
    assert set(registry.list_tools()) == {
        "grep_file",
        "list_files",
        "read_file",
        "run_command",
        "write_file",
    }


def test_programmatic_config_dataset_remains_available() -> None:
    config = AgentConfig(dataset=[DatasetItem(task="hello", expected="world")])
    assert config.dataset[0].task == "hello"
