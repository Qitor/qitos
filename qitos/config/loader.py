"""Strict canonical YAML loader for declarative QitOS agent launches."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Sequence

import yaml

from .credentials import CredentialRef
from .errors import (
    ConfigSchemaError,
    ConfigSourceError,
    ConfigSyntaxError,
    MissingEnvironmentVariableError,
    UnknownConfigFieldError,
)


CANONICAL_SCHEMA = "qitos.agent"
COMPATIBLE_SCHEMA_REVISIONS = frozenset({"qitos.agent/v1"})
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

TOOL_USE_POLICIES = frozenset(
    {"auto", "required_for_next_decision", "required_before_final", "disabled"}
)


@dataclass(frozen=True)
class ModelRequestConfig:
    temperature: float = 0.2
    top_p: Optional[float] = None
    max_tokens: int = 2048
    timeout_seconds: float = 180.0
    retries: int = 0
    extra_body: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "extra_body", _deep_freeze(self.extra_body))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
            "retries": self.retries,
            "extra_body": _json_safe(self.extra_body, "model.request.extra_body"),
        }


@dataclass(frozen=True)
class ModelConfig:
    provider: str = "openai"
    model: str = ""
    model_name: str = ""
    credential: Optional[CredentialRef] = None
    base_url: str = ""
    context_window: Optional[int] = None
    api_mode: str = "chat_completions"
    request: ModelRequestConfig = field(default_factory=ModelRequestConfig)
    # Programmatic compatibility only. Canonical YAML rejects ``api_key`` and
    # canonical serialization never contains the value.
    api_key: str = field(default="", repr=False, compare=False)
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None

    def __post_init__(self) -> None:
        request = self.request
        if self.temperature is not None:
            request = replace(request, temperature=float(self.temperature))
        else:
            object.__setattr__(self, "temperature", request.temperature)
        if self.max_tokens is not None:
            request = replace(request, max_tokens=int(self.max_tokens))
        else:
            object.__setattr__(self, "max_tokens", request.max_tokens)
        object.__setattr__(self, "request", request)

    def to_dict(self) -> Dict[str, Any]:
        """Return the canonical, secret-free model mapping."""
        return {
            "provider": self.provider,
            "model": self.model or self.model_name,
            "base_url": self.base_url,
            "credential": self.credential.to_dict() if self.credential else None,
            "api_mode": self.api_mode,
            "context_window": self.context_window,
            "request": self.request.to_dict(),
        }


@dataclass(frozen=True)
class DatasetItem:
    task: str
    expected: Any = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "expected", _deep_freeze(self.expected))
        object.__setattr__(self, "metadata", _deep_freeze(self.metadata))


@dataclass(frozen=True)
class EnvironmentConfig:
    type: str = "docker"
    image: str = "python:3.12-slim"
    workspace: str = "."
    container_workspace: str = "/workspace"
    network: str = "none"
    read_only_root: bool = True
    cap_drop: bool = True
    no_new_privileges: bool = True
    pids_limit: Optional[int] = 256
    memory_mb: Optional[int] = 2048
    cpus: Optional[float] = 2.0
    cleanup_required: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "image": self.image,
            "workspace": self.workspace,
            "container_workspace": self.container_workspace,
            "network": self.network,
            "read_only_root": self.read_only_root,
            "cap_drop": self.cap_drop,
            "no_new_privileges": self.no_new_privileges,
            "pids_limit": self.pids_limit,
            "memory_mb": self.memory_mb,
            "cpus": self.cpus,
            "cleanup_required": self.cleanup_required,
        }


@dataclass(frozen=True)
class SessionConfig:
    mode: str = "durable"
    enabled: Optional[bool] = None
    store: str = "sqlite"
    path: str = ""
    session_id: str = ""
    restore: bool = False

    def __post_init__(self) -> None:
        mode = self.mode
        if self.enabled is not None:
            legacy_mode = "durable" if self.enabled else "ephemeral"
            if mode != "durable" and mode != legacy_mode:
                raise ConfigSchemaError(
                    "runtime.session.mode conflicts with legacy enabled",
                    field="runtime.session",
                )
            mode = legacy_mode
        if mode not in {"durable", "ephemeral"}:
            raise ConfigSchemaError(
                "runtime.session.mode must be durable or ephemeral",
                field="runtime.session.mode",
            )
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "enabled", mode == "durable")
        if mode == "ephemeral" and self.restore:
            raise ConfigSchemaError(
                "ephemeral sessions cannot be restored",
                field="runtime.session.restore",
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "store": self.store,
            "path": self.path,
            "session_id": self.session_id,
            "restore": self.restore,
        }


@dataclass(frozen=True)
class TrajectoryConfig:
    enabled: bool = True
    output: str = ""
    privacy: str = "private"
    failure_policy: str = "required"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "output": self.output,
            "privacy": self.privacy,
            "failure_policy": self.failure_policy,
        }


@dataclass(frozen=True)
class RuntimeConfig:
    environment: EnvironmentConfig = field(default_factory=EnvironmentConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    trajectory: TrajectoryConfig = field(default_factory=TrajectoryConfig)
    data_root: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "environment": self.environment.to_dict(),
            "session": self.session.to_dict(),
            "trajectory": self.trajectory.to_dict(),
            "data_root": self.data_root,
        }


@dataclass(frozen=True)
class BudgetConfig:
    max_steps: int = 10
    max_runtime_seconds: float = 600.0
    max_requests: int = 12

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_steps": self.max_steps,
            "max_runtime_seconds": self.max_runtime_seconds,
            "max_requests": self.max_requests,
        }


@dataclass(frozen=True)
class AgentConfig:
    """The one canonical declarative agent launch configuration."""

    name: str = "agent"
    max_steps: int = 10
    model: ModelConfig = field(default_factory=ModelConfig)
    dataset: Sequence[DatasetItem] = field(default_factory=tuple)
    tools: Sequence[str] = field(default_factory=tuple)
    tool_preset: str = "none"
    tool_options: Mapping[str, Any] = field(default_factory=dict)
    tool_use_policy: str = "auto"
    protocol: str = "auto"
    parser: str = "auto"
    environment: Mapping[str, Any] = field(default_factory=dict)
    seed: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)
    context: Mapping[str, Any] = field(default_factory=dict)
    memory: Mapping[str, Any] = field(default_factory=dict)
    compaction: Mapping[str, Any] = field(default_factory=dict)
    lifecycle: Mapping[str, Any] = field(default_factory=dict)
    failure_policy: Mapping[str, Any] = field(default_factory=dict)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    budgets: Optional[BudgetConfig] = None
    schema: str = CANONICAL_SCHEMA
    source: Mapping[str, Any] = field(default_factory=dict)
    compatibility: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    loss: Sequence[Mapping[str, Any]] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.budgets is None:
            object.__setattr__(
                self, "budgets", BudgetConfig(max_steps=int(self.max_steps))
            )
        else:
            object.__setattr__(self, "max_steps", int(self.budgets.max_steps))
        if self.tool_use_policy not in TOOL_USE_POLICIES:
            raise ConfigSchemaError(
                "tools.policy has an unsupported value", field="tools.policy"
            )
        object.__setattr__(self, "dataset", tuple(self.dataset))
        object.__setattr__(self, "tools", tuple(self.tools))
        for name in (
            "tool_options",
            "environment",
            "metadata",
            "context",
            "memory",
            "compaction",
            "lifecycle",
            "failure_policy",
            "source",
        ):
            object.__setattr__(self, name, _deep_freeze(getattr(self, name)))
        object.__setattr__(
            self,
            "compatibility",
            tuple(_deep_freeze(item) for item in self.compatibility),
        )
        object.__setattr__(
            self, "loss", tuple(_deep_freeze(item) for item in self.loss)
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return deterministic JSON/YAML-safe canonical launch data."""
        budgets = self.budgets or BudgetConfig(max_steps=self.max_steps)
        payload = {
            "schema": self.schema,
            "agent": {
                "name": self.name,
                "protocol": self.protocol,
                "parser": self.parser,
                "seed": self.seed,
            },
            "model": self.model.to_dict(),
            "tools": {
                "preset": self.tool_preset,
                "include": list(self.tools),
                "options": _json_safe(self.tool_options, "tools.options"),
                "policy": self.tool_use_policy,
            },
            "runtime": self.runtime.to_dict(),
            "budgets": budgets.to_dict(),
            "context": _json_safe(self.context, "context"),
            "memory": _json_safe(self.memory, "memory"),
            "compaction": _json_safe(self.compaction, "compaction"),
            "lifecycle": _json_safe(self.lifecycle, "lifecycle"),
            "failure_policy": _json_safe(
                self.failure_policy, "failure_policy"
            ),
            "metadata": _json_safe(self.metadata, "metadata"),
            "dataset": [
                {
                    "task": item.task,
                    "expected": _json_safe(item.expected, "dataset.expected"),
                    "metadata": _json_safe(item.metadata, "dataset.metadata"),
                }
                for item in self.dataset
            ],
        }
        return _json_safe(payload, "config")

    def canonical_json(self) -> str:
        return json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    def digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def sanitized_dict(self) -> Dict[str, Any]:
        """Return a public diagnostic projection with private locations omitted."""
        credential_ref = self.model.credential.ref if self.model.credential else ""
        environment = self.runtime.environment
        session = self.runtime.session
        return {
            "schema": self.schema,
            "config_digest": self.digest(),
            "source_digest": str(self.source.get("sha256", "")),
            "model": {
                "provider": self.model.provider,
                "model": self.model.model or self.model.model_name,
                "api_mode": self.model.api_mode,
                "endpoint_digest": _stable_digest(self.model.base_url),
                "credential_reference_digest": _stable_digest(credential_ref),
                "request_policy_digest": _stable_digest(self.model.request.to_dict()),
            },
            "tools": {
                "preset": self.tool_preset,
                "include": list(self.tools),
                "policy": self.tool_use_policy,
            },
            "protocol": self.protocol,
            "runtime": {
                "environment_type": environment.type,
                "image_digest": _stable_digest(environment.image),
                "sandbox_policy_digest": _stable_digest(
                    {
                        "type": environment.type,
                        "network": environment.network,
                        "read_only_root": environment.read_only_root,
                        "container_workspace": environment.container_workspace,
                    }
                ),
                "workspace_digest": _stable_digest(environment.workspace),
                "session": {
                    "mode": session.mode,
                    "enabled": session.enabled,
                    "store": session.store,
                    "restore": session.restore,
                },
                "trajectory": {
                    "enabled": self.runtime.trajectory.enabled,
                    "privacy": self.runtime.trajectory.privacy,
                },
            },
            "budgets": (self.budgets or BudgetConfig()).to_dict(),
            "omitted": [
                "credential_value",
                "credential_store_path",
                "endpoint",
                "host_workspace_path",
                "session_store_path",
                "trajectory_output_path",
                "request_headers",
                "provider_payload",
            ],
            "compatibility": _json_safe(self.compatibility, "compatibility"),
            "loss": _json_safe(self.loss, "loss"),
        }

    def receipt(self) -> Dict[str, Any]:
        """Return the stable, sanitized launch receipt."""
        return self.sanitized_dict()


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _deep_freeze(value: Any) -> Any:
    """Recursively isolate caller data and expose immutable loaded state."""
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _stable_digest(value: Any) -> str:
    rendered = json.dumps(
        _json_safe(value, "digest"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _construct_unique_mapping(
    loader: yaml.SafeLoader, node: yaml.nodes.MappingNode, deep: bool = False
) -> Dict[Any, Any]:
    mapping: Dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConfigSyntaxError("configuration contains a duplicate mapping key")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def resolve_env_vars(
    value: Any,
    *,
    strict: bool = True,
    compatibility_receipts: Optional[List[Dict[str, Any]]] = None,
) -> Any:
    """Explicit environment interpolation compatibility adapter."""
    receipts = compatibility_receipts if compatibility_receipts is not None else []
    if isinstance(value, str):
        def _replace(match: re.Match[str]) -> str:
            variable = match.group(1)
            resolved = os.environ.get(variable)
            if resolved is not None:
                receipts.append(
                    {
                        "code": "ambient_environment_interpolation",
                        "variable": variable,
                        "loss": "value_not_persisted",
                    }
                )
                return resolved
            if strict:
                raise MissingEnvironmentVariableError(
                    "required environment reference is missing", field=variable
                )
            receipts.append(
                {
                    "code": "missing_environment_substituted_empty",
                    "variable": variable,
                    "warning": True,
                }
            )
            return ""

        return _ENV_PATTERN.sub(_replace, value)
    if isinstance(value, dict):
        return {
            key: resolve_env_vars(
                item, strict=strict, compatibility_receipts=receipts
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            resolve_env_vars(item, strict=strict, compatibility_receipts=receipts)
            for item in value
        ]
    return value


def load_agent_config(
    path: str | Path,
    *,
    compatibility: bool = False,
    environment_interpolation: bool = False,
) -> AgentConfig:
    """Load one strict canonical configuration from YAML."""
    source_path = Path(path)
    try:
        raw_bytes = source_path.read_bytes()
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise ConfigSourceError("unable to read agent configuration") from exc
    try:
        raw = yaml.load(raw_bytes.decode("utf-8"), Loader=_UniqueKeyLoader)
    except ConfigSyntaxError:
        raise
    except (UnicodeError, yaml.YAMLError) as exc:
        raise ConfigSyntaxError("agent configuration is not valid strict YAML") from exc
    if not isinstance(raw, dict):
        raise ConfigSchemaError("agent configuration root must be a mapping")
    if not all(isinstance(key, str) for key in raw):
        raise ConfigSchemaError("agent configuration keys must be strings")

    receipts: List[Dict[str, Any]] = []
    if environment_interpolation:
        raw = resolve_env_vars(raw, strict=True, compatibility_receipts=receipts)
    elif _contains_env_reference(raw):
        raise ConfigSchemaError(
            "ambient environment interpolation is compatibility-only",
            remediation="use model.credential.ref and a CredentialResolver",
        )

    source = {
        "kind": "yaml",
        "name": source_path.name,
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
    }
    schema = raw.get("schema")
    if schema == CANONICAL_SCHEMA:
        config = _parse_canonical_config(raw)
        runtime_raw = raw.get("runtime")
        if isinstance(runtime_raw, Mapping):
            session_raw = runtime_raw.get("session")
            if isinstance(session_raw, Mapping) and "enabled" in session_raw:
                receipts.append(
                    {
                        "code": "session_enabled_compatibility",
                        "warning": True,
                        "replacement": "runtime.session.mode",
                    }
                )
    elif schema in COMPATIBLE_SCHEMA_REVISIONS:
        normalized, revision_receipts = _normalize_schema_revision(raw)
        config = _parse_canonical_config(normalized)
        receipts.extend(revision_receipts)
        receipts.append(
            {
                "code": "agent_schema_revision_compatibility",
                "revision": str(schema).rsplit("/", 1)[-1],
                "warning": True,
                "canonical_schema": CANONICAL_SCHEMA,
            }
        )
    elif compatibility:
        config = _parse_legacy_config(raw)
        receipts.append(
            {
                "code": "legacy_flat_agent_config",
                "warning": True,
                "loss": "legacy_fields_normalized",
            }
        )
    else:
        raise ConfigSchemaError(
            f"schema must equal {CANONICAL_SCHEMA!r}", field="schema"
        )
    config = replace(
        config,
        schema=CANONICAL_SCHEMA,
        runtime=replace(config.runtime, data_root=(
            config.runtime.data_root or str(source_path.resolve().parent / ".qitos")
        )),
        source=source,
        compatibility=tuple(config.compatibility) + tuple(receipts),
    )
    config.canonical_json()
    return config


def _parse_canonical_config(raw: Mapping[str, Any]) -> AgentConfig:
    _exact_keys(
        raw,
        required={"schema", "agent", "model", "tools", "runtime", "budgets"},
        optional={
            "context",
            "memory",
            "compaction",
            "lifecycle",
            "failure_policy",
            "metadata",
            "dataset",
        },
        field="config",
    )
    agent = _mapping(raw["agent"], "agent")
    _exact_keys(
        agent,
        required={"name"},
        optional={"protocol", "parser", "seed"},
        field="agent",
    )
    model = _parse_model(_mapping(raw["model"], "model"))
    tools = _mapping(raw["tools"], "tools")
    _exact_keys(
        tools,
        required=set(),
        optional={"preset", "include", "options", "policy"},
        field="tools",
    )
    include = _string_list(tools.get("include", []), "tools.include")
    runtime = _parse_runtime(_mapping(raw["runtime"], "runtime"))
    budgets = _parse_budgets(_mapping(raw["budgets"], "budgets"))
    return AgentConfig(
        schema=CANONICAL_SCHEMA,
        name=_string(agent["name"], "agent.name", non_empty=True),
        max_steps=budgets.max_steps,
        model=model,
        dataset=_parse_dataset(raw.get("dataset", [])),
        tools=include,
        tool_preset=_string(
            tools.get("preset", "none"), "tools.preset", non_empty=True
        ),
        tool_options=_mapping(tools.get("options", {}), "tools.options"),
        tool_use_policy=_tool_use_policy(tools.get("policy", "auto")),
        protocol=_string(
            agent.get("protocol", "auto"), "agent.protocol", non_empty=True
        ),
        parser=_string(agent.get("parser", "auto"), "agent.parser", non_empty=True),
        seed=_integer(agent.get("seed", 0), "agent.seed", minimum=0),
        metadata=_mapping(raw.get("metadata", {}), "metadata"),
        context=_parse_context(_mapping(raw.get("context", {}), "context")),
        memory=_extension_slot(raw.get("memory", {}), "memory"),
        compaction=_extension_slot(raw.get("compaction", {}), "compaction"),
        lifecycle=_extension_slot(raw.get("lifecycle", {}), "lifecycle"),
        failure_policy=_extension_slot(
            raw.get("failure_policy", {}), "failure_policy"
        ),
        runtime=runtime,
        budgets=budgets,
    )


def _normalize_schema_revision(
    raw: Mapping[str, Any],
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Copy one supported persisted revision into the canonical reader shape."""
    normalized = dict(raw)
    receipts: List[Dict[str, Any]] = []
    runtime = normalized.get("runtime")
    if isinstance(runtime, Mapping):
        runtime_copy = dict(runtime)
        environment = runtime_copy.get("environment")
        if isinstance(environment, Mapping) and environment.get("type") == "host":
            environment_copy = dict(environment)
            environment_copy["type"] = "unsafe_host"
            for field_name in (
                "image",
                "container_workspace",
                "network",
                "read_only_root",
                "cap_drop",
                "no_new_privileges",
                "pids_limit",
                "memory_mb",
                "cpus",
                "cleanup_required",
            ):
                environment_copy.pop(field_name, None)
            runtime_copy["environment"] = environment_copy
            normalized["runtime"] = runtime_copy
            receipts.append(
                {
                    "code": "host_environment_renamed_unsafe_host",
                    "warning": True,
                    "safety": "unisolated_host_execution",
                }
            )
    normalized["schema"] = CANONICAL_SCHEMA
    return normalized, receipts


def _parse_context(raw: Mapping[str, Any]) -> Dict[str, Any]:
    bool_fields = {
        "enabled",
        "reactive_compact",
        "tool_call_loop_detection_enabled",
        "strict_overflow",
        "show_ui",
    }
    int_fields = {
        "min_safety_reserve_tokens",
        "default_context_window",
        "tool_result_max_chars",
        "tool_result_per_message_max_chars",
        "conversation_max_rounds",
        "loop_max_repeats",
        "max_handoffs",
    }
    ratio_fields = {
        "warning_ratio",
        "compact_ratio",
        "target_utilization",
        "safety_reserve_ratio",
    }
    optional_int_fields = {"safety_reserve_tokens"}
    _exact_keys(
        raw,
        required=set(),
        optional=bool_fields | int_fields | ratio_fields | optional_int_fields,
        field="context",
    )
    output: Dict[str, Any] = {}
    for name, value in raw.items():
        if name in bool_fields:
            output[name] = _boolean(value, f"context.{name}")
        elif name in int_fields:
            output[name] = _integer(value, f"context.{name}", minimum=1)
        elif name in ratio_fields:
            number = _number(value, f"context.{name}", minimum=0.0)
            if number > 1.0:
                raise ConfigSchemaError(
                    f"context.{name} must be at most 1.0", field=f"context.{name}"
                )
            output[name] = number
        elif value is None:
            output[name] = None
        else:
            output[name] = _integer(value, f"context.{name}", minimum=1)
    return output


def _extension_slot(value: Any, field_name: str) -> Dict[str, Any]:
    """Validate an owner-defined extension slot without interpreting its shape."""
    mapping = _mapping(value, field_name)
    return _json_safe(mapping, field_name)


def _parse_model(raw: Mapping[str, Any]) -> ModelConfig:
    _exact_keys(
        raw,
        required={"provider", "model", "credential"},
        optional={"base_url", "api_mode", "context_window", "request"},
        field="model",
    )
    credential = _mapping(raw["credential"], "model.credential")
    _exact_keys(
        credential, required={"ref"}, optional=set(), field="model.credential"
    )
    request = _mapping(raw.get("request", {}), "model.request")
    _exact_keys(
        request,
        required=set(),
        optional={
            "temperature",
            "top_p",
            "max_tokens",
            "timeout_seconds",
            "retries",
            "extra_body",
        },
        field="model.request",
    )
    top_p_raw = request.get("top_p")
    top_p = (
        None
        if top_p_raw is None
        else _number(
            top_p_raw, "model.request.top_p", minimum=0.0, maximum=1.0
        )
    )
    retries = _integer(request.get("retries", 0), "model.request.retries", minimum=0)
    if retries != 0:
        raise ConfigSchemaError(
            "model.request.retries currently supports only zero",
            field="model.request.retries",
        )
    request_config = ModelRequestConfig(
        temperature=_number(
            request.get("temperature", 0.2),
            "model.request.temperature",
            minimum=0.0,
        ),
        top_p=top_p,
        max_tokens=_integer(
            request.get("max_tokens", 2048),
            "model.request.max_tokens",
            minimum=1,
        ),
        timeout_seconds=_number(
            request.get("timeout_seconds", 180.0),
            "model.request.timeout_seconds",
            minimum=0.001,
        ),
        retries=retries,
        extra_body=_mapping(
            request.get("extra_body", {}), "model.request.extra_body"
        ),
    )
    context_raw = raw.get("context_window")
    context_window = (
        None
        if context_raw is None
        else _integer(context_raw, "model.context_window", minimum=1)
    )
    api_mode = _string(
        raw.get("api_mode", "chat_completions"),
        "model.api_mode",
        non_empty=True,
    )
    if api_mode not in {"chat_completions", "responses"}:
        raise ConfigSchemaError(
            "model.api_mode has an unsupported value", field="model.api_mode"
        )
    return ModelConfig(
        provider=_string(raw["provider"], "model.provider", non_empty=True),
        model=_string(raw["model"], "model.model", non_empty=True),
        credential=CredentialRef(
            _string(
                credential["ref"], "model.credential.ref", non_empty=True
            )
        ),
        base_url=_string(raw.get("base_url", ""), "model.base_url"),
        context_window=context_window,
        api_mode=api_mode,
        request=request_config,
    )


def _parse_runtime(raw: Mapping[str, Any]) -> RuntimeConfig:
    _exact_keys(
        raw,
        required={"environment"},
        optional={"session", "trajectory", "data_root"},
        field="runtime",
    )
    environment = _mapping(raw["environment"], "runtime.environment")
    _exact_keys(
        environment,
        required={"type", "workspace"},
        optional={
            "image",
            "container_workspace",
            "network",
            "read_only_root",
            "cap_drop",
            "no_new_privileges",
            "pids_limit",
            "memory_mb",
            "cpus",
            "cleanup_required",
        },
        field="runtime.environment",
    )
    env_type = _string(
        environment["type"], "runtime.environment.type", non_empty=True
    )
    if env_type not in {"unsafe_host", "docker"}:
        raise ConfigSchemaError(
            "runtime.environment.type must be unsafe_host or docker",
            field="runtime.environment.type",
        )
    if env_type == "unsafe_host":
        _validate_unsafe_host_environment(environment)
    session = _mapping(raw.get("session", {}), "runtime.session")
    _exact_keys(
        session,
        required=set(),
        optional={"mode", "enabled", "store", "path", "session_id", "restore"},
        field="runtime.session",
    )
    trajectory = _mapping(raw.get("trajectory", {}), "runtime.trajectory")
    _exact_keys(
        trajectory,
        required=set(),
        optional={"enabled", "output", "privacy", "failure_policy"},
        field="runtime.trajectory",
    )
    privacy = _string(
        trajectory.get("privacy", "private"),
        "runtime.trajectory.privacy",
        non_empty=True,
    )
    if privacy not in {"private", "public_redacted"}:
        raise ConfigSchemaError(
            "runtime.trajectory.privacy has an unsupported value",
            field="runtime.trajectory.privacy",
        )
    failure_policy = _string(
        trajectory.get("failure_policy", "required"),
        "runtime.trajectory.failure_policy",
        non_empty=True,
    )
    if failure_policy not in {"required", "optional"}:
        raise ConfigSchemaError(
            "runtime.trajectory.failure_policy has an unsupported value",
            field="runtime.trajectory.failure_policy",
        )
    session_mode = _string(
        session.get("mode", "durable"),
        "runtime.session.mode",
        non_empty=True,
    )
    legacy_enabled = (
        _boolean(session["enabled"], "runtime.session.enabled")
        if "enabled" in session
        else None
    )
    if "mode" in session and legacy_enabled is not None:
        legacy_mode = "durable" if legacy_enabled else "ephemeral"
        if session_mode != legacy_mode:
            raise ConfigSchemaError(
                "runtime.session.mode conflicts with legacy enabled",
                field="runtime.session",
            )
    session_store = _string(
        session.get("store", "sqlite"),
        "runtime.session.store",
        non_empty=True,
    )
    session_path = _string(session.get("path", ""), "runtime.session.path")
    if session_store not in {"memory", "sqlite"}:
        raise ConfigSchemaError(
            "runtime.session.store must be memory or sqlite",
            field="runtime.session.store",
        )
    effective_mode = (
        ("durable" if legacy_enabled else "ephemeral")
        if legacy_enabled is not None
        else session_mode
    )
    if effective_mode == "ephemeral" and (
        session.get("restore", False) or session.get("session_id", "")
    ):
        raise ConfigSchemaError(
            "ephemeral execution cannot declare restore or a Session identity",
            field="runtime.session",
        )
    environment_defaults: Dict[str, Any] = (
        {
            "image": "",
            "container_workspace": "",
            "network": "host",
            "read_only_root": False,
            "cap_drop": False,
            "no_new_privileges": False,
            "pids_limit": None,
            "memory_mb": None,
            "cpus": None,
            "cleanup_required": False,
        }
        if env_type == "unsafe_host"
        else {
            "image": "python:3.12-slim",
            "container_workspace": "/workspace",
            "network": "none",
            "read_only_root": True,
            "cap_drop": True,
            "no_new_privileges": True,
            "pids_limit": 256,
            "memory_mb": 2048,
            "cpus": 2.0,
            "cleanup_required": True,
        }
    )
    return RuntimeConfig(
        data_root=_string(raw.get("data_root", ""), "runtime.data_root"),
        environment=EnvironmentConfig(
            type=env_type,
            image=_string(
                environment.get("image", environment_defaults["image"]),
                "runtime.environment.image",
            ),
            workspace=_string(
                environment["workspace"],
                "runtime.environment.workspace",
                non_empty=True,
            ),
            container_workspace=_string(
                environment.get(
                    "container_workspace", environment_defaults["container_workspace"]
                ),
                "runtime.environment.container_workspace",
                non_empty=env_type == "docker",
            ),
            network=_string(
                environment.get("network", environment_defaults["network"]),
                "runtime.environment.network",
                non_empty=True,
            ),
            read_only_root=_boolean(
                environment.get(
                    "read_only_root", environment_defaults["read_only_root"]
                ),
                "runtime.environment.read_only_root",
            ),
            cap_drop=_boolean(
                environment.get("cap_drop", environment_defaults["cap_drop"]),
                "runtime.environment.cap_drop",
            ),
            no_new_privileges=_boolean(
                environment.get(
                    "no_new_privileges",
                    environment_defaults["no_new_privileges"],
                ),
                "runtime.environment.no_new_privileges",
            ),
            pids_limit=_optional_integer(
                environment.get("pids_limit", environment_defaults["pids_limit"]),
                "runtime.environment.pids_limit",
                minimum=1,
            ),
            memory_mb=_optional_integer(
                environment.get("memory_mb", environment_defaults["memory_mb"]),
                "runtime.environment.memory_mb",
                minimum=64,
            ),
            cpus=_optional_number(
                environment.get("cpus", environment_defaults["cpus"]),
                "runtime.environment.cpus",
                minimum=0.01,
            ),
            cleanup_required=_boolean(
                environment.get(
                    "cleanup_required", environment_defaults["cleanup_required"]
                ),
                "runtime.environment.cleanup_required",
            ),
        ),
        session=SessionConfig(
            mode=session_mode,
            enabled=legacy_enabled,
            store=session_store,
            path=session_path,
            session_id=_string(
                session.get("session_id", ""), "runtime.session.session_id"
            ),
            restore=_boolean(
                session.get("restore", False), "runtime.session.restore"
            ),
        ),
        trajectory=TrajectoryConfig(
            enabled=_boolean(
                trajectory.get("enabled", True), "runtime.trajectory.enabled"
            ),
            output=_string(
                trajectory.get("output", ""),
                "runtime.trajectory.output",
            ),
            privacy=privacy,
            failure_policy=failure_policy,
        ),
    )


def _parse_budgets(raw: Mapping[str, Any]) -> BudgetConfig:
    _exact_keys(
        raw,
        required={"max_steps"},
        optional={"max_runtime_seconds", "max_requests"},
        field="budgets",
    )
    return BudgetConfig(
        max_steps=_integer(raw["max_steps"], "budgets.max_steps", minimum=1),
        max_runtime_seconds=_number(
            raw.get("max_runtime_seconds", 600.0),
            "budgets.max_runtime_seconds",
            minimum=0.001,
        ),
        max_requests=_integer(
            raw.get("max_requests", 12), "budgets.max_requests", minimum=1
        ),
    )


def _tool_use_policy(value: Any) -> str:
    policy = _string(value, "tools.policy", non_empty=True)
    if policy not in TOOL_USE_POLICIES:
        raise ConfigSchemaError(
            "tools.policy has an unsupported value", field="tools.policy"
        )
    return policy


def _validate_unsafe_host_environment(environment: Mapping[str, Any]) -> None:
    unsupported_claims = {
        "image",
        "container_workspace",
        "network",
        "read_only_root",
        "cap_drop",
        "no_new_privileges",
        "pids_limit",
        "memory_mb",
        "cpus",
        "cleanup_required",
    } & set(environment)
    if unsupported_claims:
        from .errors import UnsafeHostConfigurationError

        raise UnsafeHostConfigurationError(
            "unsafe_host cannot declare sandbox-only constraints: "
            + ", ".join(sorted(unsupported_claims)),
            field="runtime.environment",
            remediation="select a conforming sandbox backend or remove the claims",
        )


def _parse_dataset(value: Any) -> List[DatasetItem]:
    if not isinstance(value, list):
        raise ConfigSchemaError("dataset must be a list", field="dataset")
    output: List[DatasetItem] = []
    for index, item in enumerate(value):
        field_name = f"dataset[{index}]"
        if isinstance(item, str):
            output.append(DatasetItem(task=item))
            continue
        mapping = _mapping(item, field_name)
        _exact_keys(
            mapping,
            required={"task"},
            optional={"expected", "metadata"},
            field=field_name,
        )
        output.append(
            DatasetItem(
                task=_string(
                    mapping["task"], f"{field_name}.task", non_empty=True
                ),
                expected=mapping.get("expected"),
                metadata=_mapping(
                    mapping.get("metadata", {}), f"{field_name}.metadata"
                ),
            )
        )
    return output


def _parse_legacy_config(raw: Mapping[str, Any]) -> AgentConfig:
    allowed = {
        "name",
        "max_steps",
        "model",
        "dataset",
        "tools",
        "protocol",
        "parser",
        "environment",
        "seed",
        "metadata",
    }
    _exact_keys(raw, required=set(), optional=allowed, field="config")
    model_raw = _mapping(raw.get("model", {}), "model")
    model_allowed = {
        "provider",
        "model",
        "model_name",
        "api_key",
        "base_url",
        "temperature",
        "max_tokens",
        "context_window",
        "api_mode",
    }
    _exact_keys(model_raw, required=set(), optional=model_allowed, field="model")
    api_key = _string(model_raw.get("api_key", ""), "model.api_key")
    model = ModelConfig(
        provider=_string(
            model_raw.get("provider", "openai"),
            "model.provider",
            non_empty=True,
        ),
        model=_string(
            model_raw.get("model", model_raw.get("model_name", "")),
            "model.model",
        ),
        model_name=_string(
            model_raw.get("model_name", ""), "model.model_name"
        ),
        credential=CredentialRef("inline-compatibility") if api_key else None,
        api_key=api_key,
        base_url=_string(model_raw.get("base_url", ""), "model.base_url"),
        temperature=_number(
            model_raw.get("temperature", 0.7), "model.temperature"
        ),
        max_tokens=_integer(
            model_raw.get("max_tokens", 2048), "model.max_tokens", minimum=1
        ),
        context_window=(
            None
            if model_raw.get("context_window") is None
            else _integer(
                model_raw["context_window"], "model.context_window", minimum=1
            )
        ),
        api_mode=_string(
            model_raw.get("api_mode", "chat_completions"),
            "model.api_mode",
            non_empty=True,
        ),
    )
    max_steps = _integer(raw.get("max_steps", 10), "max_steps", minimum=1)
    return AgentConfig(
        name=_string(raw.get("name", "agent"), "name", non_empty=True),
        max_steps=max_steps,
        model=model,
        dataset=_parse_dataset(raw.get("dataset", [])),
        tools=_string_list(raw.get("tools", []), "tools"),
        protocol=_string(
            raw.get("protocol", "auto"), "protocol", non_empty=True
        ),
        parser=_string(raw.get("parser", "auto"), "parser", non_empty=True),
        environment=_mapping(raw.get("environment", {}), "environment"),
        seed=_integer(raw.get("seed", 0), "seed", minimum=0),
        metadata=_mapping(raw.get("metadata", {}), "metadata"),
        budgets=BudgetConfig(max_steps=max_steps),
    )


def _exact_keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str],
    field: str,
) -> None:
    keys = set(value)
    unknown = sorted(keys - required - optional)
    if unknown:
        raise UnknownConfigFieldError(
            f"{field} contains unknown fields: {', '.join(unknown)}", field=field
        )
    missing = sorted(required - keys)
    if missing:
        raise ConfigSchemaError(
            f"{field} is missing required fields: {', '.join(missing)}",
            field=field,
        )


def _mapping(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise ConfigSchemaError(
            f"{field_name} must be a string-keyed mapping", field=field_name
        )
    return dict(value)


def _string(value: Any, field_name: str, *, non_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ConfigSchemaError(
            f"{field_name} must be a string", field=field_name
        )
    if non_empty and not value.strip():
        raise ConfigSchemaError(
            f"{field_name} must not be empty", field=field_name
        )
    return value


def _string_list(value: Any, field_name: str) -> List[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ConfigSchemaError(
            f"{field_name} must be a list of non-empty strings", field=field_name
        )
    return list(value)


def _boolean(value: Any, field_name: str) -> bool:
    if type(value) is not bool:
        raise ConfigSchemaError(
            f"{field_name} must be a boolean", field=field_name
        )
    return value


def _integer(
    value: Any, field_name: str, *, minimum: Optional[int] = None
) -> int:
    if type(value) is not int:
        raise ConfigSchemaError(
            f"{field_name} must be an integer", field=field_name
        )
    if minimum is not None and value < minimum:
        raise ConfigSchemaError(
            f"{field_name} must be >= {minimum}", field=field_name
        )
    return value


def _optional_integer(
    value: Any, field_name: str, *, minimum: Optional[int] = None
) -> Optional[int]:
    if value is None:
        return None
    return _integer(value, field_name, minimum=minimum)


def _number(
    value: Any,
    field_name: str,
    *,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    if type(value) not in {int, float} or not math.isfinite(float(value)):
        raise ConfigSchemaError(
            f"{field_name} must be a finite number", field=field_name
        )
    result = float(value)
    if minimum is not None and result < minimum:
        raise ConfigSchemaError(
            f"{field_name} must be >= {minimum}", field=field_name
        )
    if maximum is not None and result > maximum:
        raise ConfigSchemaError(
            f"{field_name} must be <= {maximum}", field=field_name
        )
    return result


def _optional_number(
    value: Any, field_name: str, *, minimum: Optional[float] = None
) -> Optional[float]:
    if value is None:
        return None
    return _number(value, field_name, minimum=minimum)


def _contains_env_reference(value: Any) -> bool:
    if isinstance(value, str):
        return bool(_ENV_PATTERN.search(value))
    if isinstance(value, dict):
        return any(_contains_env_reference(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_env_reference(item) for item in value)
    return False


def _json_safe(value: Any, field_name: str) -> Any:
    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ConfigSchemaError(
                f"{field_name} contains a non-finite number", field=field_name
            )
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, field_name) for item in value]
    if isinstance(value, Mapping) and all(
        isinstance(key, str) for key in value
    ):
        return {
            key: _json_safe(item, f"{field_name}.{key}")
            for key, item in value.items()
        }
    raise ConfigSchemaError(
        f"{field_name} is not JSON/YAML safe", field=field_name
    )


__all__ = [
    "AgentConfig",
    "BudgetConfig",
    "CANONICAL_SCHEMA",
    "COMPATIBLE_SCHEMA_REVISIONS",
    "DatasetItem",
    "EnvironmentConfig",
    "ModelConfig",
    "ModelRequestConfig",
    "RuntimeConfig",
    "SessionConfig",
    "TrajectoryConfig",
    "TOOL_USE_POLICIES",
    "load_agent_config",
    "resolve_env_vars",
]
