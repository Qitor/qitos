"""Explicit composition boundary for the canonical Engine runtime."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Protocol, Sequence, runtime_checkable

from ..checkpoint.durability import DurabilityMode
from ..checkpoint.memory_store import InMemoryCheckpointStore
from ..checkpoint.store import CheckpointStore
from ..core.session import (
    CORE_SNAPSHOT_COMPONENT_CODECS,
    PauseSafety,
    ResolvedResource,
    ResolverNamespace,
    ResolverReference,
    ResolverRegistry,
    SafeBoundaryKind,
    SessionLifecycle,
    SnapshotComponentCodec,
    SnapshotComponentRegistry,
)


AGENT_CAPABILITY = "agent.module"
MODEL_CAPABILITY = "model.call"
TOOL_REGISTRY_CAPABILITY = "tools.execute"
ENVIRONMENT_CAPABILITY = "environment.observe"
CHECKPOINT_STORE_CAPABILITY = "checkpoint.session"
EVENT_SINK_CAPABILITY = "runtime.events"
PROVIDER_CONTINUATION_CAPABILITY = "provider.continuation"
ARTIFACT_RESOLVER_CAPABILITY = "artifact.resolve"
DEFAULT_CHECKPOINT_REFERENCE = ResolverReference(
    ResolverNamespace.CHECKPOINT_STORE,
    "default:session",
    CHECKPOINT_STORE_CAPABILITY,
)


@dataclass(frozen=True)
class RuntimeSnapshotContext:
    """Live capture/restore context supplied to component owners."""

    engine: Any
    state: Any
    task: Any
    lifecycle: SessionLifecycle
    step_id: int
    restoring: bool = False


@dataclass(frozen=True)
class SessionLifecycleEvent:
    """Explicit lifecycle/head fact delivered to a composed runtime sink."""

    session_id: str
    run_id: str
    snapshot_id: str
    checkpoint_id: str
    generation: int
    lifecycle: str
    durability: str = "persisted"
    captured_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@runtime_checkable
class RuntimeSnapshotComponent(Protocol):
    """Semantic-owner bridge between runtime facts and one snapshot codec."""

    codec: SnapshotComponentCodec

    def capture(self, context: RuntimeSnapshotContext) -> Any:
        ...

    def restore(self, value: Any, context: RuntimeSnapshotContext) -> None:
        ...


class LifecyclePolicy:
    """Replaceable cooperative lifecycle policy; never a worker scheduler."""

    policy_id = "qitos.lifecycle.cooperative"
    supports_pause = True

    def should_pause(self, context: RuntimeSnapshotContext) -> bool:
        return False

    def pause_safety(self, context: RuntimeSnapshotContext) -> PauseSafety:
        executor = getattr(context.engine, "executor", None)
        batch = getattr(context.engine, "_qitos_tool_batch_snapshot", None)
        if executor is None or not callable(getattr(executor, "request_pause", None)):
            return PauseSafety(boundary=SafeBoundaryKind.AFTER_MODEL_RESULT)
        receipt = executor.request_pause(0.0)
        attempts = tuple(getattr(receipt, "attempts", ()) or ())
        unresolved = sum(
            bool(getattr(item, "outcome_unknown", False)) for item in attempts
        )
        return PauseSafety(
            boundary=(
                SafeBoundaryKind.AFTER_TOOL_RESULT
                if batch is not None
                else SafeBoundaryKind.AFTER_MODEL_RESULT
            ),
            completed_slots_recorded=True,
            open_slots_recorded=True,
            framework_workers_quiesced=bool(
                getattr(receipt, "migratable", False)
            ),
            unresolved_effect_count=int(unresolved),
        )


@runtime_checkable
class ContextModelRuntime(Protocol):
    """B-owned binding seam consumed by the existing Engine model runtime."""

    capability_id: str

    def bind(self, engine: Any) -> None:
        ...


@dataclass(frozen=True)
class RuntimeCompositionConfig:
    """Strict JSON-safe description of a process-local composition root."""

    schema_version: str = "qitos.engine.runtime_composition/v1"
    durability_mode: str = DurabilityMode.SYNC.value
    lifecycle_policy: str = LifecyclePolicy.policy_id
    capabilities: tuple[str, ...] = ()
    resolver_references: tuple[Mapping[str, Any], ...] = ()
    snapshot_component_schemas: tuple[str, ...] = ()
    tool_execution_policy: Mapping[str, Any] = field(default_factory=dict)
    context_model_runtime: Optional[str] = None

    def __post_init__(self) -> None:
        payload = asdict(self)
        try:
            json.dumps(payload, allow_nan=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("Runtime composition config must be strict JSON.") from exc

    def to_dict(self) -> dict[str, Any]:
        return json.loads(
            json.dumps(asdict(self), allow_nan=False, sort_keys=True)
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RuntimeCompositionConfig":
        return cls(
            schema_version=str(payload.get("schema_version", "")),
            durability_mode=str(payload.get("durability_mode", "")),
            lifecycle_policy=str(payload.get("lifecycle_policy", "")),
            capabilities=tuple(payload.get("capabilities", ())),
            resolver_references=tuple(payload.get("resolver_references", ())),
            snapshot_component_schemas=tuple(
                payload.get("snapshot_component_schemas", ())
            ),
            tool_execution_policy=dict(payload.get("tool_execution_policy", {})),
            context_model_runtime=payload.get("context_model_runtime"),
        )


@dataclass
class RuntimeComposition:
    """Process-local Engine components plus their serializable description."""

    checkpoint_store: Optional[CheckpointStore] = None
    resolvers: ResolverRegistry = field(default_factory=ResolverRegistry)
    durability_mode: DurabilityMode = DurabilityMode.SYNC
    lifecycle_policy: LifecyclePolicy = field(default_factory=LifecyclePolicy)
    snapshot_components: tuple[RuntimeSnapshotComponent, ...] = ()
    event_sink: Any = None
    event_sink_failure_policy: Any = None
    event_sink_view: Any = None
    tool_execution_policy: Any = None
    context_model_runtime: Optional[ContextModelRuntime] = None
    event_sink_reports: list[Any] = field(default_factory=list, init=False)
    _event_dispatcher: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        from ._snapshot_components import DEFAULT_RUNTIME_SNAPSHOT_COMPONENTS
        from ..tracing.sinks import (
            EventSink,
            EventSinkDispatcher,
            FailurePolicy,
        )
        from ..tracing.trajectory import PrivacyView

        if not isinstance(self.resolvers, ResolverRegistry):
            self.resolvers = ResolverRegistry(self.resolvers)  # type: ignore[arg-type]
        configured = tuple(self.snapshot_components)
        configured_slots = {component.codec.slot for component in configured}
        defaults = tuple(
            component
            for component in DEFAULT_RUNTIME_SNAPSHOT_COMPONENTS
            if component.codec.slot not in configured_slots
        )
        self.snapshot_components = defaults + configured
        for component in self.snapshot_components:
            if (
                not hasattr(component, "codec")
                or not callable(getattr(component, "capture", None))
                or not callable(getattr(component, "restore", None))
            ):
                raise TypeError(
                    "snapshot_components must implement RuntimeSnapshotComponent"
                )
        if not isinstance(self.lifecycle_policy, LifecyclePolicy):
            required = ("supports_pause", "should_pause", "pause_safety")
            if any(not hasattr(self.lifecycle_policy, name) for name in required):
                raise TypeError("lifecycle_policy does not implement the runtime seam")
        if self.event_sink_failure_policy is None:
            self.event_sink_failure_policy = FailurePolicy.REQUIRED
        elif not isinstance(self.event_sink_failure_policy, FailurePolicy):
            self.event_sink_failure_policy = FailurePolicy(
                self.event_sink_failure_policy
            )
        if self.event_sink_view is None:
            self.event_sink_view = PrivacyView.REDACTED_PUBLIC
        elif not isinstance(self.event_sink_view, PrivacyView):
            self.event_sink_view = PrivacyView(self.event_sink_view)
        if self.event_sink is not None:
            if not isinstance(self.event_sink, EventSink):
                raise TypeError("event_sink must implement qitos.tracing.sinks.EventSink")
            dispatcher = EventSinkDispatcher()
            dispatcher.add_sink(
                self.event_sink,
                failure_policy=self.event_sink_failure_policy,
                view=self.event_sink_view,
            )
            self._event_dispatcher = dispatcher
        if self.context_model_runtime is not None and (
            not hasattr(self.context_model_runtime, "capability_id")
            or not callable(getattr(self.context_model_runtime, "bind", None))
        ):
            raise TypeError("context_model_runtime must implement bind(engine)")

    @classmethod
    def from_resolvers(
        cls,
        resolvers: ResolverRegistry | Mapping[ResolverNamespace, Any],
        **kwargs: Any,
    ) -> "RuntimeComposition":
        registry = (
            resolvers.copy()
            if isinstance(resolvers, ResolverRegistry)
            else ResolverRegistry(resolvers)
        )
        resolved = registry.resolve(DEFAULT_CHECKPOINT_REFERENCE)
        if not isinstance(resolved.resource, CheckpointStore):
            raise TypeError("checkpoint resolver must return CheckpointStore")
        return cls(
            checkpoint_store=resolved.resource,
            resolvers=registry,
            **kwargs,
        )

    def ensure_checkpoint_store(self) -> CheckpointStore:
        """Install the default local reference store only when Session is used."""
        if self.checkpoint_store is None:
            self.checkpoint_store = InMemoryCheckpointStore()
        self.resolvers.register_resource(
            DEFAULT_CHECKPOINT_REFERENCE,
            self.checkpoint_store,
        )
        return self.checkpoint_store

    @property
    def component_registry(self) -> SnapshotComponentRegistry:
        codecs: list[SnapshotComponentCodec] = list(CORE_SNAPSHOT_COMPONENT_CODECS)
        codecs.extend(component.codec for component in self.snapshot_components)
        return SnapshotComponentRegistry(codecs)

    def capabilities(self) -> frozenset[str]:
        capabilities = {
            "session.create",
            "session.run",
            "session.inspect",
            "session.restore",
            "session.current_head",
            "session.snapshot_commit",
        }
        if (
            bool(getattr(self.lifecycle_policy, "supports_pause", False))
            and self.durability_mode is DurabilityMode.SYNC
        ):
            capabilities.add("session.pause.cooperative")
        if self.checkpoint_store is not None:
            capabilities.update(self.checkpoint_store.session_capabilities())
        if self.event_sink is not None:
            capabilities.add(EVENT_SINK_CAPABILITY)
        if self.context_model_runtime is not None:
            capabilities.add(str(self.context_model_runtime.capability_id))
        return frozenset(capabilities)

    def publish_event(self, event: Any, *, engine: Any = None) -> Any:
        """Bridge a runtime fact through the single public EventSink seam."""
        if self._event_dispatcher is None:
            return None
        from ..tracing.adapters import (
            runtime_event_to_records,
            session_lifecycle_event_to_record,
        )

        if isinstance(event, SessionLifecycleEvent):
            records: tuple[Any, ...] = (
                session_lifecycle_event_to_record(event),
            )
        else:
            handle = getattr(engine, "_session_handle", None)
            records = runtime_event_to_records(
                event,
                run_id=str(getattr(engine, "_active_run_id", "") or "runtime"),
                session_id=(
                    handle.session_id.value if handle is not None else None
                ),
                agent_id=str(getattr(getattr(engine, "agent", None), "name", ""))
                or None,
            )
        reports = []
        for record in records:
            report = self._event_dispatcher.receive(record)
            self.event_sink_reports.append(report)
            reports.append(report)
        return tuple(reports)

    def flush_events(self) -> Any:
        if self._event_dispatcher is None:
            return None
        report = self._event_dispatcher.flush()
        self.event_sink_reports.append(report)
        return report

    def bind_engine_resources(self, engine: Any) -> tuple[ResolverReference, ...]:
        """Bind explicit local defaults and return logical persisted references."""
        store = self.ensure_checkpoint_store()
        references: list[ResolverReference] = [DEFAULT_CHECKPOINT_REFERENCE]

        agent_reference = ResolverReference(
            ResolverNamespace.AGENT,
            f"agent:{_logical_id(getattr(engine.agent, 'name', 'agent'))}",
            AGENT_CAPABILITY,
        )
        self.resolvers.register_resource(agent_reference, engine.agent)
        references.append(agent_reference)

        model = getattr(engine.agent, "llm", None)
        if model is not None:
            model_reference = ResolverReference(
                ResolverNamespace.MODEL,
                f"model:{_logical_id(getattr(model, 'model', type(model).__name__))}",
                MODEL_CAPABILITY,
            )
            self.resolvers.register_resource(model_reference, model)
            references.append(model_reference)

        tools = getattr(engine, "tool_registry", None)
        if tools is not None and (
            not hasattr(tools, "__len__") or len(tools) > 0
        ):
            tools_reference = ResolverReference(
                ResolverNamespace.TOOL_REGISTRY,
                "tools:active",
                TOOL_REGISTRY_CAPABILITY,
            )
            self.resolvers.register_resource(tools_reference, tools)
            references.append(tools_reference)

        environment = getattr(engine, "env", None)
        if environment is not None:
            environment_reference = ResolverReference(
                ResolverNamespace.ENVIRONMENT,
                "environment:active",
                ENVIRONMENT_CAPABILITY,
            )
            self.resolvers.register_resource(environment_reference, environment)
            references.append(environment_reference)

        agent_config = dict(getattr(engine.agent, "config", {}) or {})
        continuation_resolver = agent_config.get(
            "continuation_resolver",
            getattr(model, "qitos_continuation_resolver", None),
        )
        if continuation_resolver is not None:
            continuation_reference = ResolverReference(
                ResolverNamespace.PROVIDER_CONTINUATION,
                str(
                    getattr(
                        continuation_resolver,
                        "resolver_key",
                        "continuation:active",
                    )
                ),
                PROVIDER_CONTINUATION_CAPABILITY,
            )
            self.resolvers.register_resource(
                continuation_reference,
                continuation_resolver,
            )
            references.append(continuation_reference)

        artifact_resolver = agent_config.get("artifact_resolver")
        if artifact_resolver is not None:
            artifact_reference = ResolverReference(
                ResolverNamespace.ARTIFACT_STORE,
                str(getattr(artifact_resolver, "resolver_key", "artifact:active")),
                ARTIFACT_RESOLVER_CAPABILITY,
            )
            self.resolvers.register_resource(artifact_reference, artifact_resolver)
            references.append(artifact_reference)

        if self.event_sink is not None:
            sink_reference = ResolverReference(
                ResolverNamespace.RUNTIME_EVENT_SINK,
                "events:active",
                EVENT_SINK_CAPABILITY,
            )
            self.resolvers.register_resource(sink_reference, self.event_sink)
            references.append(sink_reference)

        if store is not self.checkpoint_store:  # pragma: no cover - defensive
            raise RuntimeError("checkpoint composition changed during binding")
        return tuple(references)

    def export_config(
        self, references: Sequence[ResolverReference] = ()
    ) -> RuntimeCompositionConfig:
        policy = self.tool_execution_policy
        if policy is None:
            policy_payload: Mapping[str, Any] = {}
        elif hasattr(policy, "to_dict"):
            policy_payload = dict(policy.to_dict())
        elif hasattr(policy, "__dataclass_fields__"):
            policy_payload = _json_safe(asdict(policy))
        else:
            policy_payload = {"policy": type(policy).__name__}
        return RuntimeCompositionConfig(
            durability_mode=self.durability_mode.value,
            lifecycle_policy=str(
                getattr(self.lifecycle_policy, "policy_id", type(self.lifecycle_policy).__name__)
            ),
            capabilities=tuple(sorted(self.capabilities())),
            resolver_references=tuple(reference.to_dict() for reference in references),
            snapshot_component_schemas=tuple(
                sorted(component.codec.schema_version for component in self.snapshot_components)
            ),
            tool_execution_policy=policy_payload,
            context_model_runtime=(
                str(self.context_model_runtime.capability_id)
                if self.context_model_runtime is not None
                else None
            ),
        )


def resolve_runtime_resources(
    registry: ResolverRegistry,
    references: Iterable[ResolverReference],
) -> dict[ResolverNamespace, ResolvedResource]:
    """Resolve every declared runtime reference with typed capability checks."""
    resolved: dict[ResolverNamespace, ResolvedResource] = {}
    for reference in references:
        resolved[reference.namespace] = registry.resolve(reference)
    return resolved


def _logical_id(value: Any) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]+", "-", str(value or "default")).strip("-.")
    return (cleaned or "default")[:96]


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [_json_safe(item) for item in value]
        return sorted(items, key=repr) if isinstance(value, (set, frozenset)) else items
    raise ValueError("Runtime policy contains a non-JSON value.")


__all__ = [
    "AGENT_CAPABILITY",
    "ARTIFACT_RESOLVER_CAPABILITY",
    "CHECKPOINT_STORE_CAPABILITY",
    "ContextModelRuntime",
    "DEFAULT_CHECKPOINT_REFERENCE",
    "ENVIRONMENT_CAPABILITY",
    "EVENT_SINK_CAPABILITY",
    "LifecyclePolicy",
    "MODEL_CAPABILITY",
    "PROVIDER_CONTINUATION_CAPABILITY",
    "RuntimeComposition",
    "RuntimeCompositionConfig",
    "RuntimeSnapshotComponent",
    "RuntimeSnapshotContext",
    "SessionLifecycleEvent",
    "TOOL_REGISTRY_CAPABILITY",
    "resolve_runtime_resources",
]
