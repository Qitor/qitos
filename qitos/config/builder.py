"""The sole runtime composition root for :class:`AgentConfig`."""

from __future__ import annotations

import importlib
import os
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

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
    CompositionCleanupError,
    CompositionClosedError,
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
            "You are a QitOS agent. Use only the declared tools and the "
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
    """Resource-owning composition root for the existing Engine and Session."""

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
    _owns_model: bool = field(default=True, repr=False)
    _owns_environment: bool = field(default=True, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)
    _close_receipt: Dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    _close_error: Optional[CompositionCleanupError] = field(
        default=None, init=False, repr=False
    )
    _close_lock: Any = field(
        default_factory=threading.RLock, init=False, repr=False
    )

    def __enter__(self) -> "AgentComposition":
        with self._close_lock:
            if self._closed:
                raise CompositionClosedError(
                    "agent composition is already closed",
                    field="composition",
                )
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        _ = exc_type, exc, traceback
        self.close()

    def session(self, task: Optional[str] = None, *, session_id: Any = None) -> Any:
        """Create the existing durable Session from this composition."""
        self._require_open()
        if self.config.runtime.session.mode != "durable":
            raise CompositionError(
                "ephemeral composition does not provide durable Session controls",
                field="runtime.session.mode",
            )
        objective = str(
            task or (self.config.dataset[0].task if self.config.dataset else "")
        ).strip()
        if not objective:
            raise CompositionError("a launch task is required", field="dataset")
        configured_id = self.config.runtime.session.session_id or None
        return self.engine.session(objective, session_id=session_id or configured_id)

    def restore(self, session_id: Any = None) -> Any:
        """Restore with this composition's resolver registry and canonical Engine."""
        self._require_open()
        if self.config.runtime.session.mode != "durable":
            raise CompositionError(
                "ephemeral execution cannot be restored",
                field="runtime.session.mode",
            )
        identity = session_id or self.config.runtime.session.session_id
        if not identity:
            raise CompositionError(
                "restore requires a Session identity",
                field="runtime.session.session_id",
            )
        self.runtime.bind_engine_resources(self.engine)
        return Engine.restore(identity, runtime=self.runtime)

    def _require_open(self) -> None:
        if self._closed:
            raise CompositionClosedError(
                "agent composition is closed", field="composition"
            )

    def fork(self, session_id: Any, snapshot: Any = None, *, operation_id: Optional[str] = None) -> Any:
        """Fork immutable persisted state without claiming the source owner."""
        from ..core.session import SessionIdentity
        from ..engine.session_runtime import Session

        self._require_open()
        if self.config.runtime.session.mode != "durable":
            raise CompositionError("ephemeral sessions cannot fork", field="runtime.session.mode")
        identity = session_id if isinstance(session_id, SessionIdentity) else SessionIdentity(session_id)
        return Session._fork_persisted(self.engine, identity, snapshot, operation_id=operation_id)

    def close(self) -> Dict[str, Any]:
        """Close every framework-owned resource once and return a stable receipt."""
        with self._close_lock:
            if self._closed:
                if self._close_error is not None:
                    raise self._close_error
                return dict(self._close_receipt)
            receipt, failures = _cleanup_composed_resources(
                runtime=self.runtime,
                sandbox_backend=(
                    self.sandbox_backend if self._owns_environment else None
                ),
                model=self.model if self._owns_model else None,
            )
            if receipt.get("sandbox"):
                self.sandbox_receipt = dict(receipt["sandbox"])
            self._closed = True
            self._close_receipt = receipt
            if failures:
                self._close_error = CompositionCleanupError(
                    "one or more agent composition resources failed to close",
                    failures=failures,
                )
                raise self._close_error
            return dict(receipt)


def _cleanup_composed_resources(
    *, runtime: Optional[RuntimeComposition], sandbox_backend: Any, model: Any
) -> tuple[Dict[str, Any], list[Dict[str, str]]]:
    receipt: Dict[str, Any] = {"status": "closed", "closed": []}
    failures: list[Dict[str, str]] = []

    def invoke(name: str, resource: Any, method_name: str = "close") -> Any:
        if resource is None:
            return None
        method = getattr(resource, method_name, None)
        if not callable(method):
            return None
        try:
            value = method()
            receipt["closed"].append(name)
            return value
        except Exception as exc:
            failures.append(
                {"resource": name, "error_type": type(exc).__name__}
            )
            return None

    if runtime is not None:
        invoke("work_runtime", getattr(runtime, "work_runtime", None))
        for component in getattr(runtime, "snapshot_components", ()):
            if callable(getattr(component, "close", None)):
                invoke(f"snapshot_owner:{component.codec.slot}", component)
        invoke("event_dispatcher", runtime, "flush_events")
        sink = runtime.event_sink
        invoke("event_sink", sink)
        invoke("trajectory_store", getattr(sink, "_store", None))
        invoke("checkpoint_store", runtime.checkpoint_store)
    if sandbox_backend is not None:
        cleanup = invoke("sandbox", sandbox_backend, "cleanup")
        if cleanup is not None and hasattr(cleanup, "to_dict"):
            receipt["sandbox"] = cleanup.to_dict()
    invoke("model_transport", model)
    if failures:
        receipt["status"] = "cleanup_failed"
        receipt["failures"] = list(failures)
    return receipt, failures


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


def _session_store_path(config: AgentConfig) -> Path:
    if config.runtime.session.path:
        return Path(config.runtime.session.path).expanduser().resolve()
    root = config.runtime.data_root
    if not root:
        workspace = config.runtime.environment.workspace
        if workspace and workspace != ".":
            root = str(Path(workspace).expanduser().resolve() / ".qitos")
    if not root:
        raise CompositionError(
            "durable Session requires an explicit runtime data root or project workspace",
            field="runtime.data_root",
        )
    return Path(root).expanduser().resolve() / "sessions.sqlite3"


def _open_session_store(config: AgentConfig, *, read_only: bool = False) -> Any:
    session = config.runtime.session
    if not session.enabled:
        if read_only:
            raise CompositionError("ephemeral Session has no persisted head", field="runtime.session.mode")
        return None
    if session.store == "memory":
        if read_only:
            raise CompositionError("memory store is process-local", field="runtime.session.store")
        return InMemoryCheckpointStore()
    if session.store != "sqlite":
        raise CompositionError("unsupported Session store", field="runtime.session.store")
    path = _session_store_path(config)
    try:
        if not read_only:
            path.parent.mkdir(parents=True, exist_ok=True)
        return SqliteCheckpointStore(str(path), read_only=read_only)
    except (OSError, sqlite3.Error):
        raise CompositionError("Session store is unavailable", field="runtime.session.path") from None


def _inspect_persisted_session(config: AgentConfig, session_id: str) -> Dict[str, Any]:
    from ..checkpoint.session import verify_snapshot_payload_integrity
    from ..core.session import SessionContractError, SessionErrorCode

    with _open_session_store(config, read_only=True) as store:
        head = store.get_session_head(session_id)
        if head is None:
            raise SessionContractError(
                error_code=SessionErrorCode.SESSION_NOT_FOUND,
                message="Session head was not found.", recoverable=True,
                remediation="verify Session identity and store location",
            )
        snapshot = store.get_session_snapshot(head.snapshot_id)
        if snapshot is None:
            raise CompositionError("persisted Session snapshot is missing", field="runtime.session")
        verify_snapshot_payload_integrity(snapshot.payload)
        progress: Dict[str, Any] = next(
            (item["payload"] for item in snapshot.payload["components"]
             if item["slot"] == "engine_progress"), {},
        )
        metadata = progress.get("runtime_composition", {}).get("launch_metadata", {})
        capabilities = set(store.session_capabilities())
        capabilities.update({"session.inspect", "session.restore", "session.fork"})
        return {
            "session_id": head.session_id, "lifecycle": head.lifecycle,
            "checkpoint_id": head.checkpoint_id, "snapshot_id": head.snapshot_id,
            "generation": head.generation, "capabilities": sorted(capabilities),
            "config_digest": metadata.get("config_digest"),
            "live_process_control": False, "restore_time_steering": True,
            "store": {"kind": "sqlite", "path": str(_session_store_path(config)),
                      "cross_process": True},
        }


def build_runtime(
    config: AgentConfig, *, sandbox_receipt: Optional[Dict[str, Any]] = None
) -> RuntimeComposition:
    store = _open_session_store(config)
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
            "extension_slots": {
                "memory": dict(config.memory),
                "compaction": dict(config.compaction),
                "lifecycle": dict(config.lifecycle),
                "failure_policy": dict(config.failure_policy),
            },
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
    extensions: Optional[Mapping[str, Any]] = None,
) -> AgentComposition:
    """Compose the existing model/tools/Env/runtime/AgentModule/Engine stack."""
    model: Any = None
    runtime: Optional[RuntimeComposition] = None
    sandbox_backend: Any = None
    owns_model = model_override is None
    owns_environment = env_override is None
    try:
        from ._extensions import resolve_extensions
        from ..kit.artifact.store import FileArtifactStore

        services, lifecycle_policy, engine_context = resolve_extensions(config, extensions or {})
        # Preflight persistence before constructing a model or provisioning Env.
        if config.runtime.session.enabled and config.runtime.session.store != "memory":
            preflight_store = _open_session_store(config)
            preflight_store.close()
        model = (
            model_override
            if model_override is not None
            else build_model(config.model, credential_resolver=credential_resolver)
        )
        receipt = dict(getattr(model, "qitos_credential_receipt", {}) or {})
        protocol, parser = _resolve_protocol_and_parser(config, model)
        tools = build_tool_registry(config)
        if (
            config.tool_use_policy not in {"auto", "disabled"}
            and not tools
        ):
            raise CompositionError(
                "required tool-use policy needs at least one declared tool",
                field="tools.policy",
            )
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
            env, sandbox_backend, sandbox_receipt = _build_environment_with_receipt(
                config
            )
        runtime = build_runtime(config, sandbox_receipt=sandbox_receipt)
        runtime.lifecycle_policy = lifecycle_policy
        if "artifact_resolver" not in services:
            services["artifact_resolver"] = FileArtifactStore(_session_store_path(config).parent / "artifacts")
        if isinstance(env, DockerEnv):
            env._artifact_resolver = services["artifact_resolver"]
            if config.runtime.session.mode == "durable":
                from ..kit.env._session_sandbox import SessionSandboxComponent
                runtime.snapshot_components += (SessionSandboxComponent(
                    env, sandbox_backend, runtime.checkpoint_store, services["artifact_resolver"],
                ),)
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
        agent.config.update(services)
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
            fail_fast=config.failure_policy.get("tool") == "fail_closed",
            max_concurrency=int(config.tool_options.get("max_concurrency", 4)),
            parallel_tool_names=None,
        )
        engine = Engine(
            agent=agent,
            budget=budget,
            env=env,
            runtime=runtime,
            action_execution_policy=policy,
            auto_approve=bool(config.tool_options.get("auto_approve", True)),
            context_config=engine_context,
            parser=parser,
            protocol=protocol,
        )
    except Exception as build_error:
        _, failures = _cleanup_composed_resources(
            runtime=runtime,
            sandbox_backend=sandbox_backend if owns_environment else None,
            model=model if owns_model else None,
        )
        if failures:
            raise CompositionCleanupError(
                "agent composition failed and owned resources did not cleanly close",
                failures=failures,
            ) from build_error
        raise
    composition = AgentComposition(
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
        _owns_model=owns_model,
        _owns_environment=owns_environment,
    )
    for component in runtime.snapshot_components:
        if hasattr(component, "on_bind"):
            def bind_owned_environment(engine: Any, env: Any, backend: Any) -> None:
                composition.engine = engine
                composition.env = env
                composition.sandbox_backend = backend
                composition.sandbox_receipt = backend.durability_receipt()
            component.on_bind = bind_owned_environment
    return composition


def run_agent_config(
    config: AgentConfig | str | Path,
    *,
    credential_resolver: Optional[CredentialResolver] = None,
    task: Optional[str] = None,
    ephemeral: Optional[bool] = None,
) -> Dict[str, Any]:
    """Execute one config through Session, or an explicitly ephemeral Engine."""
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
    configured_ephemeral = config.runtime.session.mode == "ephemeral"
    use_ephemeral = configured_ephemeral if ephemeral is None else bool(ephemeral)
    with build_agent_composition(
        config, credential_resolver=credential_resolver
    ) as composition:
        session = None
        if use_ephemeral:
            result = composition.engine.run(objective)
        else:
            session_config = config.runtime.session
            session = (
                composition.restore(session_config.session_id)
                if session_config.restore
                else composition.session(
                    objective, session_id=session_config.session_id or None
                )
            )
            result = session.run()
        payload = {
            "schema": config.schema,
            "config_digest": config.digest(),
            "execution_mode": (
                "ephemeral" if use_ephemeral else
                "process_local_session" if config.runtime.session.store == "memory" else
                "durable_session"
            ),
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
        if session is not None:
            head = session.current_head
            payload["session"] = {
                "session_id": session.session_id.value,
                "run_id": session.run_id.value,
                "work_item_id": session.work_item_id.value,
                "lifecycle": session.lifecycle.value,
                "checkpoint_id": head.checkpoint_id.value,
                "snapshot_id": head.snapshot_id.value,
                "generation": head.generation.value,
                "capabilities": sorted(session.capabilities()),
                "config_digest": config.digest(),
                "cross_process": config.runtime.session.store == "sqlite",
                "store": config.runtime.session.store,
                "store_path": (str(_session_store_path(config))
                               if config.runtime.session.store == "sqlite" else None),
            }
        else:
            payload["session"] = {
                "durable": False,
                "capabilities": [],
                "unsupported": ["pause", "restore", "steer", "fork"],
            }
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
