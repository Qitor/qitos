"""The sole runtime composition root for :class:`AgentConfig`."""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

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
from ..kit.parser.react_parser import ReActTextParser
from ..kit.toolset.env_coding import EnvCodingToolSet
from ..models.base import ModelFactory
from .credentials import CredentialResolution, CredentialResolver
from .errors import CompositionError
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
    ) -> None:
        super().__init__(
            tool_registry=tool_registry,
            llm=llm,
            model_parser=ReActTextParser(),
            model_protocol=None if protocol == "auto" else protocol,
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

    def close(self) -> None:
        close_env = getattr(self.env, "close", None)
        if callable(close_env):
            close_env()
        store = self.runtime.checkpoint_store
        close_store = getattr(store, "close", None)
        if callable(close_store):
            close_store()


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
    environment = config.runtime.environment
    workspace = str(Path(environment.workspace).expanduser().resolve())
    if environment.type == "host":
        return HostEnv(workspace_root=workspace)
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
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--pids-limit=256",
        "--memory=2g",
        "--cpus=2",
        "--ulimit=nofile=1024:1024",
        "--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=256m",
        f"--user={os.getuid()}:{os.getgid()}",
        "--env=HOME=/tmp/qitos-home",
        f"--label=qitos.config.digest={config.digest()}",
    ]
    if environment.read_only_root:
        extra.append("--read-only")
    return DockerEnv(
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


def build_runtime(config: AgentConfig) -> RuntimeComposition:
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
    return RuntimeComposition(checkpoint_store=store)


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
    tools = build_tool_registry(config)
    env = env_override if env_override is not None else build_environment(config)
    runtime = build_runtime(config)
    agent = ConfiguredAgent(
        name=config.name,
        llm=model,
        tool_registry=tools,
        protocol=config.protocol,
    )
    budget_config = config.budgets
    budget = RuntimeBudget(
        max_steps=config.max_steps,
        max_runtime_seconds=(
            budget_config.max_runtime_seconds if budget_config else 600.0
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
        context_config=config.context,
    )
    return AgentComposition(
        config=config,
        model=model,
        tool_registry=tools,
        env=env,
        runtime=runtime,
        agent=agent,
        engine=engine,
        credential_receipt=receipt,
    )


def run_agent_config(
    config: AgentConfig,
    *,
    credential_resolver: CredentialResolver,
    task: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute the canonical config through its composed AgentModule + Engine."""
    objective = str(task or (config.dataset[0].task if config.dataset else "")).strip()
    if not objective:
        raise CompositionError("a launch task is required", field="dataset")
    composition = build_agent_composition(
        config, credential_resolver=credential_resolver
    )
    try:
        result = composition.engine.run(objective)
        return {
            "config_digest": config.digest(),
            "run_id": result.run_id,
            "stop_reason": result.state.stop_reason,
            "final_result": result.state.final_result,
            "step_count": result.step_count,
            "tool_calls": result.tool_calls_by_name,
            "credential": composition.credential_receipt,
        }
    finally:
        composition.close()


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
