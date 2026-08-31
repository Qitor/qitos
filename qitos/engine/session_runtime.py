"""Durable Session facade delegating execution to the canonical Engine loop."""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any, Iterable, Mapping, Optional, TYPE_CHECKING

from ..checkpoint.session import (
    ATOMIC_SESSION_COMMIT,
    CheckpointCapabilityError,
    CheckpointConflictError,
    CheckpointPersistenceError,
    CheckpointSessionError,
    CheckpointSessionErrorCode,
    SessionHeadRecord,
    SessionSnapshotCommit,
)
from ..checkpoint.durability import DurabilityMode
from ..core.session import (
    AgentIdentity,
    AgentStateSnapshotComponent,
    CheckpointIdentity,
    ComponentSlot,
    HeadGeneration,
    PauseReceipt,
    PersistenceReceiptStatus,
    ResolverNamespace,
    ResolverReference,
    RunIdentity,
    SessionContractError,
    SessionErrorCode,
    SessionHead,
    SessionIdentity,
    SessionLifecycle,
    SessionOperation,
    SessionSnapshot,
    SnapshotComponent,
    SnapshotIdentity,
    SnapshotTiming,
    TraceLineageSnapshotComponent,
    lifecycle_allows,
    lifecycle_can_transition,
)
from ..core.state import StateSchema
from ..core.task import Task
from .runtime import (
    RuntimeComposition,
    RuntimeSnapshotContext,
    SessionLifecycleEvent,
    resolve_runtime_resources,
)

if TYPE_CHECKING:
    from .engine import Engine, EngineResult


@dataclass(frozen=True)
class SessionInspection:
    """Read-only inspection result backed by the current durable head."""

    head: SessionHead
    lifecycle: SessionLifecycle
    capabilities: tuple[str, ...]
    snapshot_integrity: str


class Session:
    """Scoped client for one durable Session identity.

    The facade stores identifiers and cooperative control only. Agent state is
    reconstructed from the canonical snapshot and executed by ``Engine.run``.
    """

    def __init__(
        self,
        *,
        engine: "Engine[Any, Any, Any]",
        session_id: SessionIdentity,
        run_id: RunIdentity,
        agent_id: AgentIdentity,
        references: Iterable[ResolverReference],
        created_at: str,
        state_type: type[StateSchema],
    ) -> None:
        self._engine = engine
        self._runtime = engine.runtime
        self._store = self._runtime.ensure_checkpoint_store()
        self._session_id = session_id
        self._run_id = run_id
        self._agent_id = agent_id
        self._references = tuple(references)
        self._created_at = created_at
        self._state_type = state_type
        self._pause_requested = threading.Event()
        self._lock = threading.RLock()
        self._lifecycle = SessionLifecycle.CREATED
        self._pause_receipt: Optional[PauseReceipt] = None
        self._parent_run_id: Optional[RunIdentity] = None

    @property
    def session_id(self) -> SessionIdentity:
        return self._session_id

    @property
    def run_id(self) -> RunIdentity:
        return self._run_id

    @property
    def lifecycle(self) -> SessionLifecycle:
        head = self._require_head()
        return SessionLifecycle(head.lifecycle)

    @property
    def current_head(self) -> SessionHead:
        return _core_head(self._require_head())

    def capabilities(self) -> frozenset[str]:
        return self._runtime.capabilities()

    def inspect(self) -> SessionInspection:
        head = self._require_head()
        record = self._store.get_session_snapshot(head.snapshot_id)
        if record is None:
            raise _session_error(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Session head points to a missing immutable snapshot.",
                recoverable=False,
            )
        snapshot = SessionSnapshot.from_dict(
            record.payload,
            component_registry=self._runtime.component_registry,
        )
        return SessionInspection(
            head=_core_head(head),
            lifecycle=SessionLifecycle(head.lifecycle),
            capabilities=tuple(sorted(self.capabilities())),
            snapshot_integrity=snapshot.integrity.digest,
        )

    def pause(self) -> PauseReceipt:
        """Request cooperative pause; durable status is returned at a boundary."""
        if "session.pause.cooperative" not in self.capabilities():
            raise _session_error(
                SessionErrorCode.UNSUPPORTED_CAPABILITY,
                "The composed executor does not support cooperative pause.",
                recoverable=True,
                metadata={"capability": "session.pause.cooperative"},
            )
        with self._lock:
            head = self._require_head()
            lifecycle = SessionLifecycle(head.lifecycle)
            if not lifecycle_allows(lifecycle, SessionOperation.PAUSE):
                raise _invalid_operation(lifecycle, SessionOperation.PAUSE)
            self._pause_requested.set()
            self._lifecycle = SessionLifecycle.PAUSE_REQUESTED
            receipt = PauseReceipt(
                session_id=self._session_id,
                run_id=self._run_id,
                status=PersistenceReceiptStatus.ACCEPTED,
                lifecycle=SessionLifecycle.PAUSING,
                expected_generation=HeadGeneration(head.generation),
                actual_generation=HeadGeneration(head.generation),
            )
            self._pause_receipt = receipt
            return receipt

    request_pause = pause

    def run(self, *, steering: Optional[str] = None) -> "EngineResult[Any]":
        """Run or resume through the one canonical Engine loop."""
        with self._lock:
            head = self._require_head()
            lifecycle = SessionLifecycle(head.lifecycle)
            allowed = lifecycle_allows(lifecycle, SessionOperation.RUN) or (
                lifecycle is SessionLifecycle.RESTORING
            )
            if not allowed:
                raise _invalid_operation(lifecycle, SessionOperation.RUN)
            snapshot = self._load_snapshot(head)
            state, task, next_step = self._restore_core_state(snapshot)
            self._transition(SessionLifecycle.RUNNING)
            self._commit_snapshot(
                state=state,
                task=task,
                lifecycle=SessionLifecycle.RUNNING,
                step_id=next_step,
                expected_head=head,
            )
            self._engine._session_handle = self
            self._engine._session_run_id = self._run_id.value

        try:
            result = self._engine.run(
                task,
                _resume_state=state,
                _resume_step=next_step,
                _session_steering=steering,
            )
        except Exception:
            with self._lock:
                self._transition(SessionLifecycle.FAILED)
                current = self._require_head()
                self._commit_snapshot(
                    state=state,
                    task=task,
                    lifecycle=SessionLifecycle.FAILED,
                    step_id=int(getattr(state, "current_step", next_step)),
                    expected_head=current,
                )
            raise
        finally:
            self._engine._session_handle = None
            self._engine._session_run_id = ""

        with self._lock:
            if (
                self._pause_receipt is not None
                and self._pause_receipt.status is PersistenceReceiptStatus.PERSISTED
            ):
                return result
            terminal = _terminal_lifecycle(result)
            self._transition(terminal)
            current = self._require_head()
            self._commit_snapshot(
                state=result.state,
                task=task,
                lifecycle=terminal,
                step_id=int(getattr(result.state, "current_step", next_step)),
                expected_head=current,
            )
            return result

    def commit_snapshot(self) -> SessionHead:
        """Advanced explicit commit of the Engine's current safe state."""
        state = self._engine.current_state
        if state is None:
            raise _session_error(
                SessionErrorCode.UNSAFE_PAUSE_BOUNDARY,
                "Engine has no active state to snapshot.",
                recoverable=True,
            )
        head = self._require_head()
        self._commit_snapshot(
            state=state,
            task=self._engine._active_task_obj or self._engine._active_task,
            lifecycle=SessionLifecycle(head.lifecycle),
            step_id=int(getattr(state, "current_step", 0)),
            expected_head=head,
        )
        return self.current_head

    def _on_safe_boundary(
        self, *, state: StateSchema, task: str | Task, step_id: int
    ) -> bool:
        """Engine callback after a complete step and before the next operation."""
        context = RuntimeSnapshotContext(
            engine=self._engine,
            state=state,
            task=task,
            lifecycle=SessionLifecycle.PAUSING,
            step_id=step_id,
        )
        policy_request = bool(self._runtime.lifecycle_policy.should_pause(context))
        if not self._pause_requested.is_set() and not policy_request:
            return False
        if not bool(getattr(self._runtime.lifecycle_policy, "supports_pause", False)):
            raise _session_error(
                SessionErrorCode.UNSUPPORTED_CAPABILITY,
                "The composed executor cannot pause at this boundary.",
                recoverable=True,
                metadata={"capability": "session.pause.cooperative"},
            )
        safety = self._runtime.lifecycle_policy.pause_safety(context)
        safety.require_migratable()
        with self._lock:
            head = self._require_head()
            if self._lifecycle is SessionLifecycle.RUNNING:
                self._lifecycle = SessionLifecycle.PAUSE_REQUESTED
            self._lifecycle = SessionLifecycle.PAUSING
            if int(getattr(state, "current_step", 0)) <= step_id:
                state.advance_step()
            try:
                self._commit_snapshot(
                    state=state,
                    task=task,
                    lifecycle=SessionLifecycle.PAUSED,
                    step_id=step_id + 1,
                    expected_head=head,
                    pause_safety=safety,
                )
            except CheckpointConflictError as exc:
                self._pause_receipt = PauseReceipt(
                    session_id=self._session_id,
                    run_id=self._run_id,
                    status=PersistenceReceiptStatus.CONFLICT,
                    lifecycle=SessionLifecycle.PAUSING,
                    expected_generation=HeadGeneration(head.generation),
                    actual_generation=HeadGeneration(
                        self._require_head().generation
                    ),
                    error_code=SessionErrorCode.GENERATION_CONFLICT,
                )
                raise _translate_checkpoint_error(exc) from exc
            except (CheckpointPersistenceError, CheckpointSessionError) as exc:
                self._pause_receipt = PauseReceipt(
                    session_id=self._session_id,
                    run_id=self._run_id,
                    status=PersistenceReceiptStatus.FAILED,
                    lifecycle=SessionLifecycle.PAUSING,
                    expected_generation=HeadGeneration(head.generation),
                    actual_generation=HeadGeneration(head.generation),
                    error_code=SessionErrorCode.PERSISTENCE_FAILED,
                )
                raise _translate_checkpoint_error(exc) from exc
            persisted = self._require_head()
            self._pause_receipt = PauseReceipt(
                session_id=self._session_id,
                run_id=self._run_id,
                status=PersistenceReceiptStatus.PERSISTED,
                lifecycle=SessionLifecycle.PAUSED,
                expected_generation=HeadGeneration(head.generation),
                actual_generation=HeadGeneration(persisted.generation),
                snapshot_id=SnapshotIdentity(persisted.snapshot_id),
                checkpoint_id=CheckpointIdentity(persisted.checkpoint_id),
            )
            self._lifecycle = SessionLifecycle.PAUSED
            self._pause_requested.clear()
            return True

    @classmethod
    def _create(
        cls,
        engine: "Engine[Any, Any, Any]",
        task: str | Task,
        session_id: Optional[SessionIdentity] = None,
    ) -> "Session":
        runtime = engine.runtime
        if runtime.durability_mode is not DurabilityMode.SYNC:
            raise _session_error(
                SessionErrorCode.UNSUPPORTED_CAPABILITY,
                "Durable Session heads require synchronous atomic persistence.",
                recoverable=True,
                metadata={"capability": ATOMIC_SESSION_COMMIT},
            )
        store = runtime.ensure_checkpoint_store()
        if ATOMIC_SESSION_COMMIT not in store.session_capabilities():
            raise CheckpointCapabilityError(ATOMIC_SESSION_COMMIT)
        task_text = task.objective if isinstance(task, Task) else str(task)
        state = engine.agent.init_state(task_text)
        if not isinstance(state, StateSchema):
            raise TypeError("Session runtime requires StateSchema state")
        references = runtime.bind_engine_resources(engine)
        session = cls(
            engine=engine,
            session_id=session_id or SessionIdentity.generate(),
            run_id=RunIdentity.generate(),
            agent_id=AgentIdentity.generate(),
            references=references,
            created_at=_utc_now(),
            state_type=type(state),
        )
        session._commit_snapshot(
            state=state,
            task=task,
            lifecycle=SessionLifecycle.CREATED,
            step_id=0,
            expected_head=None,
        )
        return session

    @classmethod
    def _restore(
        cls,
        engine_type: type["Engine[Any, Any, Any]"],
        session_id: SessionIdentity,
        runtime: RuntimeComposition,
    ) -> "Session":
        store = runtime.ensure_checkpoint_store()
        if runtime.durability_mode is not DurabilityMode.SYNC:
            raise _session_error(
                SessionErrorCode.UNSUPPORTED_CAPABILITY,
                "Durable Session restoration requires synchronous atomic persistence.",
                recoverable=True,
                metadata={"capability": ATOMIC_SESSION_COMMIT},
            )
        head = store.get_session_head(session_id.value)
        if head is None:
            raise _session_error(
                SessionErrorCode.SESSION_NOT_FOUND,
                "Session head was not found.",
                recoverable=True,
            )
        lifecycle = SessionLifecycle(head.lifecycle)
        if not lifecycle_allows(lifecycle, SessionOperation.RESTORE):
            raise _invalid_operation(lifecycle, SessionOperation.RESTORE)
        record = store.get_session_snapshot(head.snapshot_id)
        if record is None:
            raise _session_error(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Session head points to a missing immutable snapshot.",
                recoverable=False,
            )
        snapshot = SessionSnapshot.from_dict(
            record.payload,
            component_registry=runtime.component_registry,
        )
        resolved = resolve_runtime_resources(runtime.resolvers, snapshot.resolver_references)
        agent_resource = resolved.get(ResolverNamespace.AGENT)
        if agent_resource is None:
            raise _session_error(
                SessionErrorCode.MISSING_RESOLVER,
                "Snapshot does not declare a resolvable agent.",
                recoverable=True,
            )
        agent = agent_resource.resource
        model = resolved.get(ResolverNamespace.MODEL)
        tools = resolved.get(ResolverNamespace.TOOL_REGISTRY)
        environment = resolved.get(ResolverNamespace.ENVIRONMENT)
        if model is not None:
            agent.llm = model.resource
        if tools is not None:
            agent.tool_registry = tools.resource

        progress = _component_payload(snapshot, ComponentSlot.ENGINE_PROGRESS.value)
        budget_payload = _component_payload(
            snapshot, ComponentSlot.BUDGET_CAPABILITY.value
        )
        from .states import RuntimeBudget

        budget = RuntimeBudget(
            max_steps=int(budget_payload.get("max_steps", 10)),
            max_runtime_seconds=budget_payload.get("max_runtime_seconds"),
            max_tokens=budget_payload.get("max_tokens"),
        )
        engine = engine_type(
            agent=agent,
            budget=budget,
            env=environment.resource if environment is not None else None,
            runtime=runtime,
        )
        task = _task_from_progress(progress)
        task_text = task.objective if isinstance(task, Task) else str(task)
        template = agent.init_state(task_text)
        if not isinstance(template, StateSchema):
            raise TypeError("Session runtime requires StateSchema state")
        agent_component = _agent_state(snapshot)
        expected_type = _state_schema_id(type(template))
        if agent_component.state_schema != expected_type:
            raise _session_error(
                SessionErrorCode.RESOLVER_TYPE_MISMATCH,
                "Resolved agent state schema does not match the snapshot.",
                recoverable=True,
                metadata={"expected_capability": agent_component.state_schema},
            )
        state = type(template).from_dict(dict(agent_component.state))
        trace = _trace_lineage(snapshot)
        session = cls(
            engine=engine,
            session_id=session_id,
            run_id=RunIdentity.generate(),
            agent_id=agent_component.agent_id,
            references=snapshot.resolver_references,
            created_at=snapshot.created_at,
            state_type=type(template),
        )
        session._parent_run_id = trace.run_id
        session._lifecycle = lifecycle
        context = RuntimeSnapshotContext(
            engine=engine,
            state=state,
            task=task,
            lifecycle=SessionLifecycle.RESTORING,
            step_id=int(progress.get("next_step", state.current_step)),
            restoring=True,
        )
        for component_owner in runtime.snapshot_components:
            component = next(
                (
                    item
                    for item in snapshot.components
                    if item.owner == component_owner.codec.owner
                    and item.slot == component_owner.codec.slot
                ),
                None,
            )
            if component is not None:
                component_owner.restore(component.decode(runtime.component_registry), context)
        session._transition(SessionLifecycle.RESTORING)
        session._commit_snapshot(
            state=state,
            task=task,
            lifecycle=SessionLifecycle.RESTORING,
            step_id=context.step_id,
            expected_head=head,
            expected_owner_run_id=head.owner_run_id,
        )
        return session

    def _restore_core_state(
        self, snapshot: SessionSnapshot
    ) -> tuple[StateSchema, str | Task, int]:
        progress = _component_payload(snapshot, ComponentSlot.ENGINE_PROGRESS.value)
        task = _task_from_progress(progress)
        component = _agent_state(snapshot)
        expected_type = _state_schema_id(self._state_type)
        if component.state_schema != expected_type:
            raise _session_error(
                SessionErrorCode.RESOLVER_TYPE_MISMATCH,
                "Resolved state type does not match the snapshot.",
                recoverable=True,
            )
        state = self._state_type.from_dict(dict(component.state))
        return state, task, int(progress.get("next_step", state.current_step))

    def _load_snapshot(self, head: SessionHeadRecord) -> SessionSnapshot:
        record = self._store.get_session_snapshot(head.snapshot_id)
        if record is None:
            raise _session_error(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Session head points to a missing immutable snapshot.",
                recoverable=False,
            )
        return SessionSnapshot.from_dict(
            record.payload,
            component_registry=self._runtime.component_registry,
        )

    def _commit_snapshot(
        self,
        *,
        state: StateSchema,
        task: str | Task,
        lifecycle: SessionLifecycle,
        step_id: int,
        expected_head: Optional[SessionHeadRecord],
        expected_owner_run_id: Optional[str] = None,
        pause_safety: Any = None,
    ) -> SessionHeadRecord:
        generation = 0 if expected_head is None else expected_head.generation + 1
        snapshot_id = SnapshotIdentity.generate()
        checkpoint_id = CheckpointIdentity.generate()
        context = RuntimeSnapshotContext(
            engine=self._engine,
            state=state,
            task=task,
            lifecycle=lifecycle,
            step_id=step_id,
        )
        components = list(
            self._core_components(
                state=state,
                task=task,
                lifecycle=lifecycle,
                step_id=step_id,
                pause_safety=pause_safety,
            )
        )
        for component_owner in self._runtime.snapshot_components:
            components.append(
                SnapshotComponent.from_value(
                    component_owner.codec,
                    component_owner.capture(context),
                )
            )
        now = _utc_now()
        snapshot = SessionSnapshot.create(
            snapshot_id=snapshot_id,
            session_id=self._session_id,
            head_generation=HeadGeneration(generation),
            lifecycle=lifecycle,
            created_at=self._created_at,
            timing=SnapshotTiming(
                captured_at=now,
                pause_requested_at=(
                    now
                    if lifecycle in {SessionLifecycle.PAUSING, SessionLifecycle.PAUSED}
                    else None
                ),
                safe_boundary_at=(
                    now if lifecycle is SessionLifecycle.PAUSED else None
                ),
            ),
            components=components,
            resolver_references=self._references,
            component_registry=self._runtime.component_registry,
        )
        request = SessionSnapshotCommit(
            session_id=self._session_id.value,
            snapshot_id=snapshot_id.value,
            checkpoint_id=checkpoint_id.value,
            owner_run_id=self._run_id.value,
            lifecycle=lifecycle.value,
            payload=snapshot.to_dict(),
            expected_generation=(
                expected_head.generation if expected_head is not None else None
            ),
            expected_checkpoint_id=(
                expected_head.checkpoint_id if expected_head is not None else None
            ),
            expected_owner_run_id=(
                expected_owner_run_id
                or (expected_head.owner_run_id if expected_head is not None else None)
            ),
        )
        receipt = self._store.commit_session_snapshot(request)
        self._lifecycle = lifecycle
        if self._runtime.event_sink is not None:
            self._runtime.event_sink.emit(
                SessionLifecycleEvent(
                    session_id=receipt.session_id,
                    run_id=receipt.owner_run_id,
                    snapshot_id=receipt.snapshot_id,
                    checkpoint_id=receipt.checkpoint_id,
                    generation=receipt.generation,
                    lifecycle=receipt.lifecycle,
                )
            )
        return self._require_head()

    def _core_components(
        self,
        *,
        state: StateSchema,
        task: str | Task,
        lifecycle: SessionLifecycle,
        step_id: int,
        pause_safety: Any,
    ) -> tuple[SnapshotComponent, ...]:
        from ..core.session import CORE_SNAPSHOT_COMPONENT_CODECS

        codecs = {codec.slot: codec for codec in CORE_SNAPSHOT_COMPONENT_CODECS}
        agent_state = AgentStateSnapshotComponent(
            agent_id=self._agent_id,
            state_schema=_state_schema_id(type(state)),
            state=state.to_dict(),
        )
        progress = {
            "task": _task_payload(task),
            "next_step": int(step_id),
            "lifecycle": lifecycle.value,
            "engine_config": self._engine.export_config().to_dict(),
            "runtime_composition": self._runtime.export_config(
                self._references
            ).to_dict(),
            "pause_safety": (
                _json_value(asdict(pause_safety)) if pause_safety is not None else None
            ),
        }
        budget = {
            "max_steps": int(self._engine.budget.max_steps),
            "max_runtime_seconds": self._engine.budget.max_runtime_seconds,
            "max_tokens": self._engine.budget.max_tokens,
            "token_usage": int(getattr(self._engine, "_token_usage", 0)),
        }
        trace = TraceLineageSnapshotComponent(
            run_id=self._run_id,
            trace_complete=lifecycle is not SessionLifecycle.RUNNING,
            parent_run_id=self._parent_run_id,
        )
        return (
            SnapshotComponent.from_value(
                codecs[ComponentSlot.AGENT_STATE.value], agent_state
            ),
            SnapshotComponent.from_value(
                codecs[ComponentSlot.ENGINE_PROGRESS.value], progress
            ),
            SnapshotComponent.from_value(
                codecs[ComponentSlot.BUDGET_CAPABILITY.value], budget
            ),
            SnapshotComponent.from_value(
                codecs[ComponentSlot.TRACE_LINEAGE.value], trace
            ),
        )

    def _require_head(self) -> SessionHeadRecord:
        head = self._store.get_session_head(self._session_id.value)
        if head is None:
            raise _session_error(
                SessionErrorCode.SESSION_NOT_FOUND,
                "Session head was not found.",
                recoverable=True,
            )
        return head

    def _transition(self, target: SessionLifecycle) -> None:
        current = self._lifecycle
        if current == target:
            return
        if not lifecycle_can_transition(current, target):
            raise _invalid_operation(current, SessionOperation.RUN)
        self._lifecycle = target


def restore_session(
    engine_type: type["Engine[Any, Any, Any]"],
    session_id: SessionIdentity | str,
    *,
    resolvers: Any = None,
    runtime: Optional[RuntimeComposition] = None,
) -> Session:
    """Restore one Session using a caller-owned composition root."""
    identity = (
        session_id
        if isinstance(session_id, SessionIdentity)
        else SessionIdentity(str(session_id))
    )
    if runtime is None:
        if resolvers is None:
            raise _session_error(
                SessionErrorCode.MISSING_RESOLVER,
                "Fresh-process restoration requires explicit resolvers.",
                recoverable=True,
                metadata={"namespace": ResolverNamespace.CHECKPOINT_STORE.value},
            )
        runtime = RuntimeComposition.from_resolvers(resolvers)
    elif resolvers is not None:
        raise ValueError("Pass runtime or resolvers, not both")
    return Session._restore(engine_type, identity, runtime)


def _core_head(record: SessionHeadRecord) -> SessionHead:
    return SessionHead(
        session_id=SessionIdentity(record.session_id),
        snapshot_id=SnapshotIdentity(record.snapshot_id),
        checkpoint_id=CheckpointIdentity(record.checkpoint_id),
        generation=HeadGeneration(record.generation),
        owner_run_id=RunIdentity(record.owner_run_id),
    )


def _component_payload(snapshot: SessionSnapshot, slot: str) -> Mapping[str, Any]:
    component = next(
        (item for item in snapshot.components if item.slot == slot),
        None,
    )
    if component is None:
        raise _session_error(
            SessionErrorCode.MISSING_REQUIRED_COMPONENT,
            "Session snapshot is missing a required runtime component.",
            recoverable=False,
            metadata={"slot": slot},
        )
    decoded = component.decode(snapshot_component_registry(snapshot))
    if isinstance(decoded, Mapping):
        return decoded
    raise _session_error(
        SessionErrorCode.CORRUPT_SNAPSHOT,
        "Runtime component did not decode to an object.",
        recoverable=False,
    )


def snapshot_component_registry(snapshot: SessionSnapshot) -> Any:
    # Core components have fixed owner codecs. Custom decoding is performed by
    # Session with the composed registry before this helper is reached.
    from ..core.session import CORE_SNAPSHOT_COMPONENT_REGISTRY

    return CORE_SNAPSHOT_COMPONENT_REGISTRY


def _agent_state(snapshot: SessionSnapshot) -> AgentStateSnapshotComponent:
    component = next(
        (
            item
            for item in snapshot.components
            if item.slot == ComponentSlot.AGENT_STATE.value
            and item.owner == "qitos.session"
        ),
        None,
    )
    if component is None:
        raise _session_error(
            SessionErrorCode.MISSING_REQUIRED_COMPONENT,
            "Session snapshot is missing agent state.",
            recoverable=False,
        )
    from ..core.session import CORE_SNAPSHOT_COMPONENT_REGISTRY

    decoded = component.decode(CORE_SNAPSHOT_COMPONENT_REGISTRY)
    if not isinstance(decoded, AgentStateSnapshotComponent):
        raise _session_error(
            SessionErrorCode.CORRUPT_SNAPSHOT,
            "Agent state component decoded to an incompatible type.",
            recoverable=False,
        )
    return decoded


def _trace_lineage(snapshot: SessionSnapshot) -> TraceLineageSnapshotComponent:
    component = next(
        (
            item
            for item in snapshot.components
            if item.slot == ComponentSlot.TRACE_LINEAGE.value
            and item.owner == "qitos.session"
        ),
        None,
    )
    if component is None:
        raise _session_error(
            SessionErrorCode.MISSING_REQUIRED_COMPONENT,
            "Session snapshot is missing trace lineage.",
            recoverable=False,
        )
    from ..core.session import CORE_SNAPSHOT_COMPONENT_REGISTRY

    decoded = component.decode(CORE_SNAPSHOT_COMPONENT_REGISTRY)
    if not isinstance(decoded, TraceLineageSnapshotComponent):
        raise _session_error(
            SessionErrorCode.CORRUPT_SNAPSHOT,
            "Trace lineage component decoded to an incompatible type.",
            recoverable=False,
        )
    return decoded


def _task_payload(task: str | Task) -> dict[str, Any]:
    if isinstance(task, Task):
        return {"kind": "task", "value": task.to_dict()}
    return {"kind": "text", "value": str(task)}


def _task_from_progress(progress: Mapping[str, Any]) -> str | Task:
    payload = progress.get("task")
    if not isinstance(payload, Mapping) or set(payload) != {"kind", "value"}:
        raise _session_error(
            SessionErrorCode.CORRUPT_SNAPSHOT,
            "Session task component is invalid.",
            recoverable=False,
        )
    if payload["kind"] == "text" and isinstance(payload["value"], str):
        return payload["value"]
    if payload["kind"] == "task" and isinstance(payload["value"], Mapping):
        return Task.from_dict(dict(payload["value"]))
    raise _session_error(
        SessionErrorCode.CORRUPT_SNAPSHOT,
        "Session task component kind is unsupported.",
        recoverable=False,
    )


def _terminal_lifecycle(result: "EngineResult[Any]") -> SessionLifecycle:
    reason = str(getattr(result.state, "stop_reason", "") or "")
    if reason.startswith("cancelled"):
        return SessionLifecycle.CANCELLED
    if reason == "unrecoverable_error":
        return SessionLifecycle.FAILED
    return SessionLifecycle.COMPLETED


def _invalid_operation(
    lifecycle: SessionLifecycle, operation: SessionOperation
) -> SessionContractError:
    return _session_error(
        SessionErrorCode.INVALID_LIFECYCLE_OPERATION,
        f"Session operation {operation.value} is invalid while {lifecycle.value}.",
        recoverable=False,
        metadata={"lifecycle": lifecycle.value, "operation": operation.value},
    )


def _translate_checkpoint_error(error: CheckpointSessionError) -> SessionContractError:
    mapping = {
        CheckpointSessionErrorCode.GENERATION_CONFLICT: SessionErrorCode.GENERATION_CONFLICT,
        CheckpointSessionErrorCode.CHECKPOINT_CONFLICT: SessionErrorCode.GENERATION_CONFLICT,
        CheckpointSessionErrorCode.OWNER_CONFLICT: SessionErrorCode.SUPERSEDED_OWNER,
        CheckpointSessionErrorCode.CORRUPT_SNAPSHOT: SessionErrorCode.CORRUPT_SNAPSHOT,
        CheckpointSessionErrorCode.INCOMPATIBLE_CHECKPOINT: SessionErrorCode.INCOMPATIBLE_CHECKPOINT,
        CheckpointSessionErrorCode.PERSISTENCE_FAILED: SessionErrorCode.PERSISTENCE_FAILED,
        CheckpointSessionErrorCode.UNSUPPORTED_CAPABILITY: SessionErrorCode.UNSUPPORTED_CAPABILITY,
        CheckpointSessionErrorCode.SESSION_NOT_FOUND: SessionErrorCode.SESSION_NOT_FOUND,
        CheckpointSessionErrorCode.SNAPSHOT_NOT_FOUND: SessionErrorCode.CORRUPT_SNAPSHOT,
    }
    return _session_error(
        mapping[error.error_code],
        str(error),
        recoverable=error.recoverable,
        metadata=error.metadata,
    )


def _session_error(
    code: SessionErrorCode,
    message: str,
    *,
    recoverable: bool,
    metadata: Optional[Mapping[str, Any]] = None,
) -> SessionContractError:
    return SessionContractError(
        code,
        message,
        recoverable=recoverable,
        remediation="Inspect the Session head, composition capabilities, and resolver bindings.",
        metadata=metadata,
    )


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _json_value(asdict(value))  # type: ignore[arg-type]
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    raise TypeError(f"Runtime value is not JSON-safe: {type(value).__name__}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_schema_id(state_type: type[Any]) -> str:
    raw = f"python.{state_type.__module__}.{state_type.__qualname__}".lower()
    return re.sub(r"[^a-z0-9_.:-]+", "-", raw)[:95]


__all__ = ["Session", "SessionInspection", "restore_session"]
