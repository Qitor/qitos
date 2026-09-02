"""The sole runtime composition root for :class:`AgentConfig`."""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..checkpoint import InMemoryCheckpointStore, SqliteCheckpointStore
from ..core.action import Action, ActionExecutionPolicy
from ..core.agent_module import AgentModule
from ..core.decision import Decision
from ..core.spec import RunSpec
from ..core.state import StateSchema
from ..core.tool_registry import ToolRegistry
from ..engine.engine import Engine
from ..engine.runtime import RuntimeComposition
from ..engine.states import RuntimeBudget
from ..kit.env.docker_env import DockerEnv
from ..kit.env.host_env import HostEnv
from ..kit.env.sandbox import (
    DockerSandboxBackend,
    SandboxBackend,
    SandboxBackendError,
    SandboxCapabilityMismatch,
    SandboxCleanupFailure,
    SandboxUnavailable,
    UnsafeHostBackend,
    assert_sandbox_backend_conformance,
)
from ..kit.toolset.env_coding import EnvCodingToolSet
from ..models.base import ModelFactory
from ..models.profile_registry import infer_default_protocol
from ..protocols import get_protocol, list_protocols
from .credentials import CredentialResolution, CredentialResolver
from .errors import (
    CompositionError,
    ProtocolParserMismatchError,
    SandboxCleanupError,
    SandboxUnavailableError,
    UnsupportedProtocolError,
)
from .loader import AgentConfig, ModelConfig


_PROVIDER_ALIASES = {
    "openai_compatible": "openai-compatible",
    "openai-compatible": "openai-compatible",
    "azure": "azure",
    "anthropic": "anthropic",
    "gemini": "gemini",
    "google": "gemini",
    "litellm": "litellm",
    "ollama": "ollama",
    "lmstudio": "lmstudio",
    "local": "ollama",
}


@dataclass
class ConfiguredAgentState(StateSchema):
    observations: list[str] = field(default_factory=list)


class ConfiguredAgent(AgentModule[ConfiguredAgentState, Dict[str, Any], Action]):
    """Small canonical AgentModule used by declarative launches."""

    def __init__(
        self,
        *,
        name: str,
        llm: Any,
        tool_registry: ToolRegistry,
        protocol: str,
        parser: Any,
        tool_use_policy: str,
        native_tool_calls_required: bool,
        config_digest: str,
    ) -> None:
        super().__init__(
            tool_registry=tool_registry,
            llm=llm,
            model_parser=parser,
            model_protocol=protocol,
            tool_use_policy=tool_use_policy,
            native_tool_calls_required=native_tool_calls_required,
            agent_config_digest=config_digest,
        )
        self.name = name

    def init_state(self, task: str, **kwargs: Any) -> ConfiguredAgentState:
        return ConfiguredAgentState(
            task=task,
            max_steps=int(kwargs.get("max_steps", 10)),
        )

    def base_persona_prompt(self, state: ConfiguredAgentState) -> str:
        _ = state
        return (
            "You are a QitOS coding agent. Use only the declared tools and the "
            "configured workspace environment. Never assume host access."
        )

    def task_policy_prompt(self, state: ConfiguredAgentState) -> str:
        return f"Complete this task and verify the result: {state.task}"

    def prepare(self, state: ConfiguredAgentState) -> str:
        recent = "\n".join(state.observations[-8:])
        return (
            f"Task: {state.task}\nStep: {state.current_step}/{state.max_steps}"
            + (f"\nRecent observations:\n{recent}" if recent else "")
        )

    def reduce(
        self,
        state: ConfiguredAgentState,
        observation: Dict[str, Any],
        decision: Decision[Action],
    ) -> ConfiguredAgentState:
        _ = decision
        for item in list(observation.get("action_results", []) or []):
            state.observations.append(str(item)[:4000])
        state.observations = state.observations[-24:]
        return state


@dataclass
class AgentComposition:
    """Process-local objects composed from one canonical config."""

    config: AgentConfig
    model: Any
    tool_registry: ToolRegistry
    env: Any
    runtime: RuntimeComposition
    agent: ConfiguredAgent
    engine: Engine[Any, Any, Any]
    credential_receipt: Dict[str, Any]
    sandbox_backend: Any = None
    sandbox_receipt: Dict[str, Any] = field(default_factory=dict)
    trajectory_path: Optional[Path] = None

    def close(self) -> None:
        failure: Optional[Exception] = None
        try:
            self.runtime.flush_events()
        except Exception as exc:
            failure = exc
        sink = self.runtime.event_sink
        close_sink = getattr(sink, "close", None)
        if callable(close_sink):
            try:
                close_sink()
            except Exception as exc:
                failure = failure or exc
        sink_store = getattr(sink, "_store", None)
        close_trajectory_store = getattr(sink_store, "close", None)
        if callable(close_trajectory_store):
            try:
                close_trajectory_store()
            except Exception as exc:
                failure = failure or exc
        if self.sandbox_backend is not None:
            try:
                cleanup = self.sandbox_backend.cleanup()
                self.sandbox_receipt = cleanup.to_dict()
            except SandboxCleanupFailure as exc:
                failure = SandboxCleanupError(
                    "configured sandbox cleanup failed",
                    field="runtime.environment",
                )
                failure.__cause__ = exc
        else:
            close_env = getattr(self.env, "close", None)
            if callable(close_env):
                try:
                    close_env()
                except Exception as exc:
                    failure = failure or exc
        store = self.runtime.checkpoint_store
        close_store = getattr(store, "close", None)
        if callable(close_store):
            try:
                close_store()
            except Exception as exc:
                failure = failure or exc
        if failure is not None:
            raise failure


def _runtime_base_url(value: str) -> str:
    url = str(value or "").rstrip("/")
    for suffix in ("/chat/completions", "/responses"):
        if url.endswith(suffix):
            return url[: -len(suffix)]
    return url


def build_model(
    config: ModelConfig,
    *,
    credential_resolver: Optional[CredentialResolver] = None,
) -> Any:
    """Create a model through ModelFactory with explicit credential authority."""
    provider_key = _PROVIDER_ALIASES.get(config.provider, config.provider)
    resolution: Optional[CredentialResolution] = None
    if config.credential is not None:
        if credential_resolver is None:
            raise CompositionError(
                "model credential reference requires an explicit resolver",
                field="model.credential.ref",
            )
        resolution = credential_resolver.resolve(config.credential)
        api_key = resolution.secret.reveal_for_composition()
    elif config.api_key:
        api_key = config.api_key
    else:
        raise CompositionError(
            "model construction requires a credential reference and resolver",
            field="model.credential",
        )

    params: Dict[str, Any] = {
        "model": config.model or config.model_name,
        "api_key": api_key,
        "temperature": config.request.temperature,
        "max_tokens": config.request.max_tokens,
        "timeout": max(1, int(config.request.timeout_seconds)),
    }
    if config.base_url:
        params["base_url"] = _runtime_base_url(config.base_url)
    if provider_key in {
        "openai",
        "openai-compatible",
        "async-openai",
        "async-openai-compatible",
    }:
        params["api_mode"] = config.api_mode
        params["default_request_kwargs"] = dict(config.request.extra_body)
    if config.context_window is not None:
        params["context_window"] = config.context_window
    model = ModelFactory.create(provider_key, **params)
    if resolution is not None:
        setattr(model, "qitos_credential_receipt", resolution.receipt())
    return model


def build_run_spec(config: AgentConfig) -> RunSpec:
    model_name = config.model.model or config.model.model_name or "unknown"
    return RunSpec.infer(
        model_name=model_name,
        prompt_protocol=config.protocol,
        seed=config.seed,
        environment={
            "environment_type": config.runtime.environment.type,
            "config_digest": config.digest(),
        },
        metadata={
            "agent_config_schema": config.schema,
            "agent_config_digest": config.digest(),
        },
    )


def build_tool_registry(config: AgentConfig) -> ToolRegistry:
    registry = ToolRegistry()
    if config.tool_use_policy == "disabled":
        return registry
    if config.tool_preset == "env_coding":
        registry.include_toolset(EnvCodingToolSet())
    elif config.tool_preset not in {"", "none"}:
        raise CompositionError(
            "unknown declarative tool preset", field="tools.preset"
        )
    for tool_path in config.tools:
        _register_tool_by_path(registry, tool_path)
    return registry


def build_environment(config: AgentConfig) -> Any:
    env, _, _ = _build_environment_with_receipt(config)
    return env


def _build_environment_with_receipt(
    config: AgentConfig,
) -> Tuple[Any, Any, Dict[str, Any]]:
    environment = config.runtime.environment
    workspace = str(Path(environment.workspace).expanduser().resolve())
    if environment.type == "unsafe_host":
        env = HostEnv(workspace_root=workspace)
        backend: SandboxBackend = UnsafeHostBackend(
            env, config_digest=config.digest()
        )
        receipt = backend.prepare()
        assert_sandbox_backend_conformance(backend)
        return env, backend, receipt.to_dict()
    if not environment.image:
        raise CompositionError(
            "docker environment requires an image", field="runtime.environment.image"
        )
    if environment.network != "none":
        raise CompositionError(
            "declarative coding sandbox requires network=none",
            field="runtime.environment.network",
        )
    extra = [
        f"--pids-limit={int(environment.pids_limit or 0)}",
        f"--memory={int(environment.memory_mb or 0)}m",
        f"--cpus={float(environment.cpus or 0)}",
        "--ulimit=nofile=1024:1024",
        "--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=256m",
        f"--user={os.getuid()}:{os.getgid()}",
        "--env=HOME=/tmp/qitos-home",
        f"--label=qitos.config.digest={config.digest()}",
    ]
    if environment.cap_drop:
        extra.append("--cap-drop=ALL")
    if environment.no_new_privileges:
        extra.append("--security-opt=no-new-privileges:true")
    if environment.read_only_root:
        extra.append("--read-only")
    env = DockerEnv(
        workspace_root=environment.container_workspace,
        image=environment.image,
        host_workspace=workspace,
        auto_create=True,
        remove_on_close=True,
        network="none",
        extra_run_args=extra,
        container_env={},
        strict_workspace=True,
    )
    backend = DockerSandboxBackend(env, config_digest=config.digest())
    try:
        receipt = backend.prepare()
        capabilities = assert_sandbox_backend_conformance(backend)
    except SandboxCleanupFailure as exc:
        raise SandboxCleanupError(
            "partially prepared sandbox cleanup failed",
            field="runtime.environment",
        ) from exc
    except SandboxUnavailable as exc:
        raise SandboxUnavailableError(
            "configured sandbox backend is unavailable",
            field="runtime.environment.type",
            remediation="start Docker and make the configured image available",
        ) from exc
    except (SandboxCapabilityMismatch, SandboxBackendError) as exc:
        raise CompositionError(
            "configured sandbox backend failed capability attestation",
            field="runtime.environment",
        ) from exc
    if not capabilities.safe_for_executable_tools:
        raise CompositionError(
            "configured sandbox backend is not safe for executable tools",
            field="runtime.environment",
        )
    return env, backend, receipt.to_dict()


def build_runtime(
    config: AgentConfig, *, sandbox_receipt: Optional[Dict[str, Any]] = None
) -> RuntimeComposition:
    session = config.runtime.session
    store: Any = None
    if session.enabled:
        if session.store == "sqlite":
            if not session.path:
                raise CompositionError(
                    "sqlite session store requires a path",
                    field="runtime.session.path",
                )
            path = Path(session.path).expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            store = SqliteCheckpointStore(str(path))
        elif session.store == "memory":
            store = InMemoryCheckpointStore()
        else:
            raise CompositionError(
                "runtime.session.store must be memory or sqlite",
                field="runtime.session.store",
            )
    event_sink: Any = None
    event_store: Any = None
    event_view: Any = None
    event_failure_policy: Any = None
    trajectory_path: Optional[Path] = None
    if config.runtime.trajectory.enabled:
        from ..tracing.sinks import FailurePolicy, TrajectoryStoreEventSink
        from ..tracing.store import JsonTrajectoryStore
        from ..tracing.trajectory import PrivacyView, RecordKind, RecordRole, TrajectoryRecord

        output = Path(config.runtime.trajectory.output).expanduser().resolve()
        trajectory_path = output if output.suffix == ".json" else output / "trajectory.json"
        event_store = JsonTrajectoryStore(trajectory_path)
        event_sink = TrajectoryStoreEventSink(event_store)
        event_view = (
            PrivacyView.RAW_PRIVATE
            if config.runtime.trajectory.privacy == "private"
            else PrivacyView.REDACTED_PUBLIC
        )
        event_failure_policy = (
            FailurePolicy.REQUIRED
            if config.runtime.trajectory.failure_policy == "required"
            else FailurePolicy.OPTIONAL
        )
        event_store.append(
            TrajectoryRecord.create(
                RecordKind.LIFECYCLE,
                role=RecordRole.CANONICAL_RUNTIME_FACT,
                phase="CONFIG_LOADED",
                payload={
                    "schema": config.schema,
                    "config_digest": config.digest(),
                    "tool_use_policy": config.tool_use_policy,
                },
            )
        )
        if sandbox_receipt:
            event_store.append(
                TrajectoryRecord.create(
                    RecordKind.LIFECYCLE,
                    role=RecordRole.CANONICAL_RUNTIME_FACT,
                    phase="SANDBOX_PREPARED",
                    payload=dict(sandbox_receipt),
                )
            )
    runtime = RuntimeComposition(
        checkpoint_store=store,
        event_sink=event_sink,
        event_sink_failure_policy=event_failure_policy,
        event_sink_view=event_view,
        launch_metadata={
            "agent_config_schema": config.schema,
            "config_digest": config.digest(),
            "protocol": config.protocol,
            "parser": config.parser,
            "tool_use_policy": config.tool_use_policy,
            "native_tool_calls_required": bool(
                config.tool_options.get("native_tool_calls_required", False)
            ),
            "trajectory_enabled": config.runtime.trajectory.enabled,
            "sandbox": dict(sandbox_receipt or {}),
        },
    )
    setattr(runtime, "trajectory_path", trajectory_path)
    return runtime


def _resolve_protocol_and_parser(config: AgentConfig, model: Any) -> tuple[Any, Any]:
    protocol_id = config.protocol
    if protocol_id == "auto":
        protocol_id = str(getattr(model, "qitos_protocol", "") or "")
        metadata = dict(getattr(model, "qitos_harness_metadata", {}) or {})
        protocol_id = protocol_id or str(metadata.get("protocol") or "")
        if not protocol_id:
            model_name = getattr(model, "model", None) or getattr(
                model, "model_name", None
            )
            protocol_id = infer_default_protocol(
                model_name, fallback="react_text_v1"
            )
    protocol = get_protocol(protocol_id)
    if protocol is None:
        raise UnsupportedProtocolError(
            "configured protocol is not supported",
            field="agent.protocol",
            remediation="select a protocol from qitos.protocols.list_protocols()",
        )
    expected = protocol.parser_factory()
    if config.parser == "auto":
        return protocol, expected
    parser = None
    for candidate_id in list_protocols():
        candidate_protocol = get_protocol(candidate_id)
        if candidate_protocol is None:
            continue
        candidate = candidate_protocol.parser_factory()
        if config.parser in {
            candidate.__class__.__name__,
            str(getattr(candidate, "contract_id", "") or ""),
        }:
            parser = candidate
            break
    if parser is None or parser.__class__ is not expected.__class__:
        raise ProtocolParserMismatchError(
            "configured parser is incompatible with the resolved protocol",
            field="agent.parser",
            remediation=f"use parser: auto for protocol {protocol.id}",
        )
    return protocol, parser


def build_agent_composition(
    config: AgentConfig,
    *,
    credential_resolver: Optional[CredentialResolver] = None,
    model_override: Any = None,
    env_override: Any = None,
) -> AgentComposition:
    """Compose the existing model/tools/Env/runtime/AgentModule/Engine stack."""
    model = (
        model_override
        if model_override is not None
        else build_model(config.model, credential_resolver=credential_resolver)
    )
    receipt = dict(getattr(model, "qitos_credential_receipt", {}) or {})
    protocol, parser = _resolve_protocol_and_parser(config, model)
    tools = build_tool_registry(config)
    if config.tool_use_policy != "auto" and config.tool_use_policy != "disabled" and not tools:
        raise CompositionError(
            "required tool-use policy needs at least one declared tool",
            field="tools.policy",
        )
    sandbox_backend: SandboxBackend
    if env_override is not None:
        env = env_override
        if config.runtime.environment.type == "unsafe_host":
            sandbox_backend = UnsafeHostBackend(
                env, config_digest=config.digest()
            )
        elif isinstance(env, DockerEnv):
            sandbox_backend = DockerSandboxBackend(
                env, config_digest=config.digest()
            )
        else:
            raise CompositionError(
                "an executable launch cannot replace its sandbox with an unattested Env",
                field="runtime.environment.type",
                remediation="inject a conforming sandbox Env or select unsafe_host explicitly",
            )
        sandbox_receipt = sandbox_backend.prepare().to_dict()
        capabilities = assert_sandbox_backend_conformance(sandbox_backend)
        if (
            config.runtime.environment.type != "unsafe_host"
            and not capabilities.safe_for_executable_tools
        ):
            raise CompositionError(
                "injected sandbox did not attest required capabilities",
                field="runtime.environment",
            )
    else:
        env, sandbox_backend, sandbox_receipt = _build_environment_with_receipt(config)
    runtime = None
    try:
        runtime = build_runtime(config, sandbox_receipt=sandbox_receipt)
        agent = ConfiguredAgent(
            name=config.name,
            llm=model,
            tool_registry=tools,
            protocol=protocol.id,
            parser=parser,
            tool_use_policy=config.tool_use_policy,
            native_tool_calls_required=bool(
                config.tool_options.get("native_tool_calls_required", False)
            ),
            config_digest=config.digest(),
        )
        budget_config = config.budgets
        budget = RuntimeBudget(
            max_steps=config.max_steps,
            max_runtime_seconds=(
                budget_config.max_runtime_seconds if budget_config else 600.0
            ),
            max_model_requests=(
                budget_config.max_requests if budget_config else 12
            ),
        )
        policy = ActionExecutionPolicy(
            mode="parallel",
            fail_fast=False,
            max_concurrency=4,
            parallel_tool_names=frozenset(
                {"read_file", "list_files", "grep_file"}
            ),
        )
        engine = Engine(
            agent=agent,
            budget=budget,
            env=env,
            runtime=runtime,
            action_execution_policy=policy,
            auto_approve=True,
            context_config=dict(config.context),
            parser=parser,
            protocol=protocol,
        )
    except Exception:
        if runtime is not None:
            sink = runtime.event_sink
            close_sink = getattr(sink, "close", None)
            if callable(close_sink):
                close_sink()
            sink_store = getattr(sink, "_store", None)
            close_sink_store = getattr(sink_store, "close", None)
            if callable(close_sink_store):
                close_sink_store()
            store = runtime.checkpoint_store
            close_store = getattr(store, "close", None)
            if callable(close_store):
                close_store()
        try:
            sandbox_backend.cleanup()
        except SandboxCleanupFailure as exc:
            raise SandboxCleanupError(
                "configured sandbox cleanup failed after composition error",
                field="runtime.environment",
            ) from exc
        raise
    return AgentComposition(
        config=config,
        model=model,
        tool_registry=tools,
        env=env,
        runtime=runtime,
        agent=agent,
        engine=engine,
        credential_receipt=receipt,
        sandbox_backend=sandbox_backend,
        sandbox_receipt=sandbox_receipt,
        trajectory_path=getattr(runtime, "trajectory_path", None),
    )


def run_agent_config(
    config: AgentConfig | str | Path,
    *,
    credential_resolver: Optional[CredentialResolver] = None,
    task: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute the canonical config through its composed AgentModule + Engine."""
    if not isinstance(config, AgentConfig):
        from .credentials import LocalCredentialFileResolver
        from .loader import load_agent_config

        config = load_agent_config(config)
        if credential_resolver is None:
            credential_resolver = LocalCredentialFileResolver(
                Path("~/.config/qitos/credentials.yaml").expanduser(),
                repository_root=Path(__file__).resolve().parents[2],
            )
    if credential_resolver is None:
        raise CompositionError(
            "agent execution requires an explicit credential resolver",
            field="model.credential.ref",
        )
    objective = str(task or (config.dataset[0].task if config.dataset else "")).strip()
    if not objective:
        raise CompositionError("a launch task is required", field="dataset")
    composition = build_agent_composition(
        config, credential_resolver=credential_resolver
    )
    try:
        result = composition.engine.run(objective)
        payload = {
            "schema": config.schema,
            "config_digest": config.digest(),
            "run_id": result.run_id,
            "stop_reason": result.state.stop_reason,
            "final_result": result.state.final_result,
            "step_count": result.step_count,
            "tool_calls": result.tool_calls_by_name,
            "credential": composition.credential_receipt,
            "sandbox": dict(composition.sandbox_receipt),
            "trajectory": {
                "enabled": config.runtime.trajectory.enabled,
                "privacy": config.runtime.trajectory.privacy,
                "config_digest": config.digest(),
            },
        }
    finally:
        composition.close()
    payload["sandbox"] = dict(composition.sandbox_receipt)
    return payload


def _register_tool_by_path(registry: ToolRegistry, dotted_path: str) -> None:
    parts = dotted_path.rsplit(".", 1)
    if len(parts) != 2:
        raise ImportError(
            f"Invalid tool path '{dotted_path}': expected format 'module.function'"
        )
    module_path, func_name = parts
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise ImportError(
            f"Cannot import tool module '{module_path}': {exc}"
        ) from exc
    func = getattr(module, func_name, None)
    if func is None:
        raise ImportError(f"Tool '{func_name}' not found in module '{module_path}'")
    registry.register(func)


__all__ = [
    "AgentComposition",
    "ConfiguredAgent",
    "build_agent_composition",
    "build_environment",
    "build_model",
    "build_run_spec",
    "build_runtime",
    "build_tool_registry",
    "run_agent_config",
]
