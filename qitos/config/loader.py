"""Strict canonical YAML loader for declarative QitOS agent launches."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import yaml

from .credentials import CredentialRef
from .errors import (
    ConfigSchemaError,
    ConfigSourceError,
    ConfigSyntaxError,
    MissingEnvironmentVariableError,
    UnknownConfigFieldError,
)


CANONICAL_SCHEMA = "qitos.agent/v1"
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass
class ModelRequestConfig:
    temperature: float = 0.2
    top_p: Optional[float] = None
    max_tokens: int = 2048
    timeout_seconds: float = 180.0
    retries: int = 0
    extra_body: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
            "retries": self.retries,
            "extra_body": _json_safe(self.extra_body, "model.request.extra_body"),
        }


@dataclass
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
        if self.temperature is not None:
            self.request.temperature = float(self.temperature)
        else:
            self.temperature = self.request.temperature
        if self.max_tokens is not None:
            self.request.max_tokens = int(self.max_tokens)
        else:
            self.max_tokens = self.request.max_tokens

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


@dataclass
class DatasetItem:
    task: str
    expected: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EnvironmentConfig:
    type: str = "host"
    image: str = ""
    workspace: str = "."
    container_workspace: str = "/workspace"
    network: str = "none"
    read_only_root: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SessionConfig:
    enabled: bool = False
    store: str = "memory"
    path: str = ""
    session_id: str = ""
    restore: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TrajectoryConfig:
    enabled: bool = True
    output: str = "./runs"
    privacy: str = "private"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RuntimeConfig:
    environment: EnvironmentConfig = field(default_factory=EnvironmentConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    trajectory: TrajectoryConfig = field(default_factory=TrajectoryConfig)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "environment": self.environment.to_dict(),
            "session": self.session.to_dict(),
            "trajectory": self.trajectory.to_dict(),
        }


@dataclass
class BudgetConfig:
    max_steps: int = 10
    max_runtime_seconds: float = 600.0
    max_requests: int = 12

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentConfig:
    """The one canonical declarative agent launch configuration."""

    name: str = "agent"
    max_steps: int = 10
    model: ModelConfig = field(default_factory=ModelConfig)
    dataset: List[DatasetItem] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    tool_preset: str = "none"
    tool_options: Dict[str, Any] = field(default_factory=dict)
    protocol: str = "auto"
    parser: str = "auto"
    environment: Dict[str, Any] = field(default_factory=dict)
    seed: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    budgets: Optional[BudgetConfig] = None
    schema: str = CANONICAL_SCHEMA
    source: Dict[str, Any] = field(default_factory=dict)
    compatibility: List[Dict[str, Any]] = field(default_factory=list)
    loss: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.budgets is None:
            self.budgets = BudgetConfig(max_steps=int(self.max_steps))
        else:
            self.max_steps = int(self.budgets.max_steps)

    def to_dict(self) -> Dict[str, Any]:
        """Return deterministic JSON/YAML-safe canonical launch data."""
        budgets = self.budgets or BudgetConfig(max_steps=self.max_steps)
        budgets.max_steps = int(self.max_steps)
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
            },
            "runtime": self.runtime.to_dict(),
            "budgets": budgets.to_dict(),
            "context": _json_safe(self.context, "context"),
            "metadata": _json_safe(self.metadata, "metadata"),
            "dataset": [
                {
                    "task": item.task,
                    "expected": _json_safe(item.expected, "dataset.expected"),
                    "metadata": _json_safe(item.metadata, "dataset.metadata"),
                }
                for item in self.dataset
            ],
            "source": _json_safe(self.source, "source"),
            "compatibility": _json_safe(self.compatibility, "compatibility"),
            "loss": _json_safe(self.loss, "loss"),
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
    if raw.get("schema") == CANONICAL_SCHEMA:
        config = _parse_canonical_config(raw)
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
    config.source = source
    config.compatibility.extend(receipts)
    config.canonical_json()
    return config


def _parse_canonical_config(raw: Mapping[str, Any]) -> AgentConfig:
    _exact_keys(
        raw,
        required={"schema", "agent", "model", "tools", "runtime", "budgets"},
        optional={"context", "metadata", "dataset"},
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
        optional={"preset", "include", "options"},
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
        protocol=_string(
            agent.get("protocol", "auto"), "agent.protocol", non_empty=True
        ),
        parser=_string(agent.get("parser", "auto"), "agent.parser", non_empty=True),
        seed=_integer(agent.get("seed", 0), "agent.seed", minimum=0),
        metadata=_mapping(raw.get("metadata", {}), "metadata"),
        context=_parse_context(_mapping(raw.get("context", {}), "context")),
        runtime=runtime,
        budgets=budgets,
    )


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
        optional={"session", "trajectory"},
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
        },
        field="runtime.environment",
    )
    env_type = _string(
        environment["type"], "runtime.environment.type", non_empty=True
    )
    if env_type not in {"host", "docker"}:
        raise ConfigSchemaError(
            "runtime.environment.type must be host or docker",
            field="runtime.environment.type",
        )
    session = _mapping(raw.get("session", {}), "runtime.session")
    _exact_keys(
        session,
        required=set(),
        optional={"enabled", "store", "path", "session_id", "restore"},
        field="runtime.session",
    )
    trajectory = _mapping(raw.get("trajectory", {}), "runtime.trajectory")
    _exact_keys(
        trajectory,
        required=set(),
        optional={"enabled", "output", "privacy"},
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
    return RuntimeConfig(
        environment=EnvironmentConfig(
            type=env_type,
            image=_string(
                environment.get("image", ""), "runtime.environment.image"
            ),
            workspace=_string(
                environment["workspace"],
                "runtime.environment.workspace",
                non_empty=True,
            ),
            container_workspace=_string(
                environment.get("container_workspace", "/workspace"),
                "runtime.environment.container_workspace",
                non_empty=True,
            ),
            network=_string(
                environment.get("network", "none"),
                "runtime.environment.network",
                non_empty=True,
            ),
            read_only_root=_boolean(
                environment.get("read_only_root", True),
                "runtime.environment.read_only_root",
            ),
        ),
        session=SessionConfig(
            enabled=_boolean(
                session.get("enabled", False), "runtime.session.enabled"
            ),
            store=_string(
                session.get("store", "memory"),
                "runtime.session.store",
                non_empty=True,
            ),
            path=_string(session.get("path", ""), "runtime.session.path"),
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
                trajectory.get("output", "./runs"),
                "runtime.trajectory.output",
                non_empty=True,
            ),
            privacy=privacy,
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
    if isinstance(value, list):
        return [_json_safe(item, field_name) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item, field_name) for item in value]
    if isinstance(value, dict) and all(
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
    "DatasetItem",
    "EnvironmentConfig",
    "ModelConfig",
    "ModelRequestConfig",
    "RuntimeConfig",
    "SessionConfig",
    "TrajectoryConfig",
    "load_agent_config",
    "resolve_env_vars",
]
