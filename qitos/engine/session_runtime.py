"""Durable Session facade delegating execution to the canonical Engine loop."""

from __future__ import annotations

import threading
import hashlib
import json
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any, cast, Iterable, Mapping, Optional, TYPE_CHECKING
from uuid import uuid4

from ..checkpoint.session import (
    ATOMIC_SESSION_COMMIT,
    ATOMIC_SESSION_FORK,
    CheckpointCapabilityError,
    CheckpointConflictError,
    CheckpointPersistenceError,
    CheckpointSessionError,
    CheckpointSessionErrorCode,
    SessionHeadRecord,
    SessionForkReceipt,
    SessionForkRequest,
    SessionSnapshotCommit,
)
from ..checkpoint.durability import DurabilityMode
from ..core.tool_result import ToolResult
from ..core.session import (
    AgentIdentity,
    AgentStateSnapshotComponent,
    CheckpointIdentity,
    ComponentSlot,
    HeadGeneration,
    ForkLineageSnapshotComponent,
    PauseReceipt,
    PauseSafety,
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
    SafeBoundaryKind,
    SnapshotComponent,
    SnapshotIdentity,
    SnapshotTiming,
    TraceLineageSnapshotComponent,
    WorkItemIdentity,
    AttemptIdentity,
    lifecycle_allows,
    lifecycle_can_transition,
)
from ..core.action import Action
from ..core.conversation import (
    ExchangeLog,
    ToolBatchBuilder,
    ToolResultItem,
)
from ..core.decision import Decision
from ..core.request_view import (
    ConversationSnapshotComponent,
    RequestView,
    SteeringReceipt,
    reconcile_steering_receipts,
    submit_steering,
)
from ..core.context_transfer import ContextTransferPlan, execute_context_transfer
from ..core.work_graph import (
    BudgetAllocation,
    CapabilityAllocation,
    JoinPolicy,
    WorkDescriptor,
    WorkGraph,
    WorkGraphSnapshotComponent,
    WorkItem,
    WorkLifecycle,
    WorkOwner,
)
from ..core.tool_runtime import ToolBatchSnapshot, ToolTerminalReceipt
from ..core.state import StateSchema
from ..core.task import Task
from .runtime import (
    AGENT_CAPABILITY,
    RuntimeComposition,
    RuntimeSnapshotContext,
    SessionLifecycleEvent,
    resolve_runtime_resources,
)
from ._snapshot_components import clear_session_runtime

if TYPE_CHECKING:
    from .engine import Engine, EngineResult


@dataclass(frozen=True)
class SessionInspection:
    """Read-only inspection result backed by the current durable head."""

    head: SessionHead
    lifecycle: SessionLifecycle
    capabilities: tuple[str, ...]
    snapshot_integrity: str
    budget: Mapping[str, Any]
    work_graph: Optional[Mapping[str, Any]]
    last_request_view: Optional[RequestView]
    task: str
    tool_batch: Optional[ToolBatchSnapshot]


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
        work_item_id: WorkItemIdentity,
        attempt_id: AttemptIdentity,
        fork_receipt: Optional[SessionForkReceipt] = None,
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
        self._work_item_id = work_item_id
        self._attempt_id = attempt_id
        self._fork_receipt = fork_receipt
        self._pause_requested = threading.Event()
        self._lock = threading.RLock()
        self._lifecycle = SessionLifecycle.CREATED
        self._pause_receipt: Optional[PauseReceipt] = None
        self._quiescence_receipt: Any = None
        self._parent_run_id: Optional[RunIdentity] = None
        self._work_fork_snapshot: Optional[SnapshotIdentity] = None

    @property
    def session_id(self) -> SessionIdentity:
        return self._session_id

    @property
    def run_id(self) -> RunIdentity:
        return self._run_id

    @property
    def work_item_id(self) -> WorkItemIdentity:
        return self._work_item_id

    @property
    def attempt_id(self) -> AttemptIdentity:
        return self._attempt_id

    @property
    def fork_receipt(self) -> Optional[SessionForkReceipt]:
        return self._fork_receipt

    @property
    def lifecycle(self) -> SessionLifecycle:
        head = self._require_head()
        return SessionLifecycle(head.lifecycle)

    @property
    def current_head(self) -> SessionHead:
        return _core_head(self._require_head())

    def capabilities(self) -> frozenset[str]:
        return self._runtime.capabilities()

    @contextmanager
    def _bound_runtime_cache(self) -> Any:
        """Bind this Session's head to the reusable Engine for one operation."""

        with self._engine._session_runtime_lock:
            clear_session_runtime(self._engine)
            try:
                head = self._require_head()
                snapshot = self._load_snapshot(head)
                state, task, step_id = self._restore_core_state(snapshot)
                self._restore_budget(snapshot)
                self._restore_runtime_components(
                    snapshot, state=state, task=task, step_id=step_id
                )
                self._engine._session_handle = self
                self._engine._session_run_id = self._run_id.value
                self._engine._active_state = state
                self._engine._active_task_obj = (
                    task if isinstance(task, Task) else None
                )
                self._engine._active_task = (
                    task.objective if isinstance(task, Task) else str(task)
                )
                yield getattr(self._engine, "_qitos_work_graph", None)
            finally:
                clear_session_runtime(self._engine)

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
        conversation_item = next(
            (item for item in snapshot.components if item.slot == "conversation"),
            None,
        )
        conversation = (
            conversation_item.decode(self._runtime.component_registry)
            if conversation_item is not None
            else None
        )
        work_graph_item = next(
            (item for item in snapshot.components if item.slot == "work_graph"),
            None,
        )
        tool_batch_item = next(
            (item for item in snapshot.components if item.slot == "tool_batch"),
            None,
        )
        work_graph_component = (
            work_graph_item.decode(self._runtime.component_registry)
            if work_graph_item is not None
            else None
        )
        progress = _component_payload(
            snapshot, ComponentSlot.ENGINE_PROGRESS.value
        )
        inspected_task = _task_from_progress(progress)
        return SessionInspection(
            head=_core_head(head),
            lifecycle=SessionLifecycle(head.lifecycle),
            capabilities=tuple(sorted(self.capabilities())),
            snapshot_integrity=snapshot.integrity.digest,
            budget=dict(
                _component_payload(
                    snapshot, ComponentSlot.BUDGET_CAPABILITY.value
                )
            ),
            work_graph=(
                dict(work_graph_component.graph)
                if isinstance(work_graph_component, WorkGraphSnapshotComponent)
                and work_graph_component.graph is not None
                else None
            ),
            last_request_view=(
                conversation.last_request_view
                if isinstance(conversation, ConversationSnapshotComponent)
                else None
            ),
            task=(
                inspected_task.objective
                if isinstance(inspected_task, Task)
                else str(inspected_task)
            ),
            tool_batch=(
                tool_batch_item.decode(self._runtime.component_registry)
                if tool_batch_item is not None
                else None
            ),
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
            executor = getattr(self._engine, "executor", None)
            if executor is not None and callable(
                getattr(executor, "request_pause", None)
            ):
                self._quiescence_receipt = executor.request_pause(0.0)
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

    def steer(self, text: str) -> SteeringReceipt:
        """Durably submit one canonical steering item to this Session."""
        if self._engine._session_handle is self:
            with self._lock:
                state = self._engine.current_state
                task: str | Task = (
                    self._engine._active_task_obj or self._engine._active_task
                )
                if state is None:
                    head = self._require_head()
                    snapshot = self._load_snapshot(head)
                    state, task, step_id = self._restore_core_state(snapshot)
                else:
                    step_id = int(getattr(state, "current_step", 0))
                return self._submit_steering(
                    text, state=state, task=task, step_id=step_id
                )
        with self._engine._session_runtime_lock:
            clear_session_runtime(self._engine)
            try:
                with self._lock:
                    head = self._require_head()
                    snapshot = self._load_snapshot(head)
                    state, task, step_id = self._restore_core_state(snapshot)
                    self._restore_budget(snapshot)
                    self._restore_runtime_components(
                        snapshot, state=state, task=task, step_id=step_id
                    )
                    self._engine._session_handle = self
                    self._engine._session_run_id = self._run_id.value
                    self._engine._active_state = state
                    self._engine._active_task_obj = (
                        task if isinstance(task, Task) else None
                    )
                    self._engine._active_task = (
                        task.objective if isinstance(task, Task) else str(task)
                    )
                    return self._submit_steering(
                        text,
                        state=state,
                        task=task,
                        step_id=step_id,
                    )
            finally:
                clear_session_runtime(self._engine)

    def submit_work(
        self,
        operation: str,
        payload: Mapping[str, Any],
        *,
        operation_id: str | None = None,
    ) -> Any:
        """Submit one durable logical operation through the composed scheduler."""
        if self._engine._session_handle is self:
            return self._submit_work_bound(
                operation, payload, operation_id=operation_id
            )
        with self._engine._session_runtime_lock:
            clear_session_runtime(self._engine)
            try:
                head = self._require_head()
                snapshot = self._load_snapshot(head)
                state, task, step_id = self._restore_core_state(snapshot)
                self._restore_budget(snapshot)
                self._restore_runtime_components(
                    snapshot, state=state, task=task, step_id=step_id
                )
                self._engine._session_handle = self
                self._engine._session_run_id = self._run_id.value
                self._engine._active_state = state
                self._engine._active_task_obj = (
                    task if isinstance(task, Task) else None
                )
                self._engine._active_task = (
                    task.objective if isinstance(task, Task) else str(task)
                )
                return self._submit_work_bound(
                    operation, payload, operation_id=operation_id
                )
            finally:
                clear_session_runtime(self._engine)

    def _submit_work_bound(
        self,
        operation: str,
        payload: Mapping[str, Any],
        *,
        operation_id: str | None = None,
    ) -> Any:
        runtime = getattr(self._runtime, "work_runtime", None)
        if runtime is None:
            raise _session_error(
                SessionErrorCode.UNSUPPORTED_CAPABILITY,
                "The composed runtime has no durable work scheduler.",
                recoverable=True,
                metadata={"capability": "work.scheduler.durable"},
            )
        graph = getattr(self._engine, "_qitos_work_graph", None)
        if graph is None:
            graph = WorkGraph(f"work_graph:{self._session_id.value}")
            setattr(self._engine, "_qitos_work_graph", graph)
        canonical = json.loads(json.dumps(dict(payload), sort_keys=True, allow_nan=False))
        if operation_id is None:
            operation_id = f"{operation}:{uuid4().hex}"
        before = graph.to_persistence_dict()
        try:
            existing_operation = next(
                (
                    item for item in graph.operation_receipts
                    if item.operation_id == operation_id
                ),
                None,
            )
            if existing_operation is None:
                self._ensure_work_root(graph, operation_id)
            declaration = runtime.declare(
                graph=graph,
                descriptor=self._declaration_descriptor(
                    graph=graph,
                    operation=operation,
                    operation_id=operation_id,
                    payload=canonical,
                ),
                persist=lambda: self._commit_work_graph_value(graph),
                generation=self.current_head.generation.value,
            )
            if declaration.state not in {"declared", "dispatchable"}:
                return declaration
            declared = graph.to_persistence_dict()
            descriptor = self._prepare_work_descriptor(
                graph=graph,
                operation=operation,
                operation_id=operation_id,
                payload=canonical,
            )
            try:
                return runtime.submit(
                    graph=graph,
                    descriptor=descriptor,
                    persist=lambda: self._commit_work_graph_value(graph),
                    generation=self.current_head.generation.value,
                )
            except Exception:
                current = next(
                    (
                        item for item in graph.operation_receipts
                        if item.operation_id == operation_id
                    ),
                    None,
                )
                if current is not None and current.state == "declared":
                    setattr(
                        self._engine,
                        "_qitos_work_graph",
                        WorkGraph.from_canonical_dict(declared),
                    )
                raise
        except Exception:
            durable_declaration = any(
                item.operation_id == operation_id for item in graph.operation_receipts
            )
            if not durable_declaration:
                restored = WorkGraph.from_canonical_dict(before)
                setattr(self._engine, "_qitos_work_graph", restored)
            raise

    def recover_work(self) -> tuple[Any, ...]:
        """Resume declared/queued work through this restored Session composition."""
        if self._engine._session_handle is self:
            return self._recover_work_bound()
        with self._engine._session_runtime_lock:
            clear_session_runtime(self._engine)
            try:
                head = self._require_head()
                snapshot = self._load_snapshot(head)
                state, task, step_id = self._restore_core_state(snapshot)
                self._restore_budget(snapshot)
                self._restore_runtime_components(
                    snapshot, state=state, task=task, step_id=step_id
                )
                self._engine._session_handle = self
                self._engine._session_run_id = self._run_id.value
                self._engine._active_state = state
                self._engine._active_task_obj = (
                    task if isinstance(task, Task) else None
                )
                self._engine._active_task = (
                    task.objective if isinstance(task, Task) else str(task)
                )
                return self._recover_work_bound()
            finally:
                clear_session_runtime(self._engine)

    def _recover_work_bound(self) -> tuple[Any, ...]:
        runtime = getattr(self._runtime, "work_runtime", None)
        graph = getattr(self._engine, "_qitos_work_graph", None)
        if runtime is None or graph is None:
            return ()

        def prepare(declaration: WorkDescriptor) -> WorkDescriptor:
            before = graph.to_persistence_dict()
            try:
                return self._prepare_work_descriptor(
                    graph=graph,
                    operation=declaration.operation,
                    operation_id=declaration.operation_id,
                    payload=declaration.task_input,
                )
            except Exception:
                restored = WorkGraph.from_canonical_dict(before)
                graph.__dict__.clear()
                graph.__dict__.update(restored.__dict__)
                raise

        return runtime.recover(
            graph,
            persist=lambda: self._commit_work_graph_value(graph),
            prepare=prepare,
        )

    def _ensure_work_root(self, graph: WorkGraph, operation_id: str) -> None:
        if self._work_item_id not in graph.work_items:
            head = self._require_head()
            graph.add_work_item(
                WorkItem(
                    work_item_id=self._work_item_id,
                    session_ref=self._session_id,
                    task_ref=f"task:{_stable_digest(str(self._engine._active_task))[:24]}",
                    lifecycle=_work_lifecycle(SessionLifecycle(head.lifecycle)),
                    owner=WorkOwner(self._agent_id, 0),
                )
            )
        elif graph.work_items[self._work_item_id].owner.agent_id != self._agent_id:
            from .work_runtime import WorkRuntimeError

            raise WorkRuntimeError(
                "superseded_owner",
                "the Session is no longer the authoritative work owner",
                operation_id=operation_id,
            )

    def _declaration_descriptor(
        self,
        *,
        graph: WorkGraph,
        operation: str,
        operation_id: str,
        payload: Mapping[str, Any],
    ) -> WorkDescriptor:
        if operation not in {"handoff", "delegate", "spawn", "fan_out", "join"}:
            raise ValueError(f"unsupported durable operation {operation!r}")
        tasks = payload.get("tasks", []) if operation == "fan_out" else []
        width = len(tasks) if isinstance(tasks, list) else 1
        checkpoint = ResolverReference(
            ResolverNamespace.CHECKPOINT_STORE,
            "default:session",
            "checkpoint.session",
        )
        return WorkDescriptor(
            operation_id=operation_id,
            operation=operation,
            parent_session_id=self._session_id.value,
            parent_work_item_id=self._work_item_id.value,
            child_session_ids=[],
            child_work_item_ids=[],
            agent_refs=[],
            task_input=dict(payload),
            fork_receipts=[],
            transfer_receipts=[],
            budget_allocations=[],
            capability_allocations=[],
            artifact_refs=[],
            resolver_requirements=[checkpoint.to_dict()],
            graph_depth=_graph_depth(graph, self._work_item_id),
            fan_out_width=max(1, width),
        )

    def _prepare_work_descriptor(
        self,
        *,
        graph: WorkGraph,
        operation: str,
        operation_id: str,
        payload: Mapping[str, Any],
    ) -> WorkDescriptor:
        existing = next(
            (item for item in graph.operation_receipts if item.operation_id == operation_id),
            None,
        )
        if (
            existing is not None
            and existing.state != "declared"
            and existing.descriptor is not None
        ):
            return WorkDescriptor.from_dict(existing.descriptor)
        if operation not in {"handoff", "delegate", "spawn", "fan_out", "join"}:
            raise ValueError(f"unsupported durable operation {operation!r}")
        self._ensure_work_root(graph, operation_id)

        child_sessions: list[Session] = []
        specs: list[Mapping[str, Any]] = []
        if operation in {"delegate", "spawn"}:
            specs = [payload]
        elif operation == "fan_out":
            raw_specs = payload.get("tasks", [])
            if not isinstance(raw_specs, list):
                raise ValueError("fan_out tasks must be an array")
            specs = [dict(item) for item in raw_specs]
        for index, spec in enumerate(specs):
            child_sessions.append(
                self._fork_or_recover(
                    f"fork_{_stable_digest(f'{operation_id}:{index}')[:32]}"
                )
            )

        agent_refs: list[dict[str, Any]] = []
        fork_receipts: list[dict[str, Any]] = []
        transfer_receipts: list[dict[str, Any]] = []
        budget_allocations: list[dict[str, Any]] = []
        capability_allocations: list[dict[str, Any]] = []
        child_work_ids: list[WorkItemIdentity] = []
        referenced_child_session_ids: list[str] = []
        prepared_children: list[WorkItem] = []
        parent_request_remaining = (
            max(
                0,
                int(self._engine.budget.max_model_requests)
                - int(getattr(self._engine, "_model_requests_consumed", 0))
                - int(getattr(self._engine, "_model_requests_reserved", 0)),
            )
            if self._engine.budget.max_model_requests is not None
            else None
        )
        for index, child in enumerate(child_sessions):
            spec = specs[index]
            agent_name = str(spec.get("agent") or getattr(self._engine.agent, "name", "agent"))
            agent_ref = _agent_reference(agent_name)
            destination_resolved = _resolver_available(self._runtime, agent_ref)
            target_agent_id = self._agent_id if destination_resolved else AgentIdentity.generate()
            declared_budget = dict(spec.get("budget") or {})
            budget = BudgetAllocation(
                allocation_id=f"budget:{operation_id}:{index}",
                parent_work_item_id=self._work_item_id,
                child_work_item_id=child.work_item_id,
                limits=self._effective_child_budget(
                    declared_budget,
                    parent_request_remaining=parent_request_remaining,
                ),
            )
            capabilities = CapabilityAllocation(
                allocation_id=f"capability:{operation_id}:{index}",
                parent_work_item_id=self._work_item_id,
                child_work_item_id=child.work_item_id,
                capabilities=list(spec.get("capabilities") or []),
            )
            if parent_request_remaining is not None:
                parent_request_remaining -= int(
                    budget.limits.get("model_requests", 0)
                )
            receipt = self._execute_child_transfer(
                operation_id=f"{operation_id}:transfer:{index}",
                operation=operation,
                child=child,
                agent_ref=agent_ref,
                target_agent_id=target_agent_id,
                budget=budget,
                capabilities=capabilities,
                destination_resolved=destination_resolved,
            )
            if receipt.terminal_disposition != "accepted":
                from .work_runtime import WorkRuntimeError

                raise WorkRuntimeError(
                    "context_transfer_rejected",
                    receipt.failure_code or "context transfer was rejected",
                    operation_id=operation_id,
                )
            self._rebase_transferred_child(
                child,
                task=str(spec.get("task") or ""),
                receipt=receipt,
                source_snapshot=self._load_snapshot(self._require_head()),
            )
            child_item = WorkItem(
                work_item_id=child.work_item_id,
                session_ref=child.session_id,
                task_ref=f"task:{_stable_digest(str(spec.get('task', '')))[:24]}",
                lifecycle="paused",
                owner=WorkOwner(target_agent_id, child.current_head.generation.value),
                parent_work_item_id=self._work_item_id,
                detached=operation == "spawn",
                budget_allocation_ref=budget.allocation_id,
                capability_allocation_ref=capabilities.allocation_id,
                context_transfer_ref=receipt.receipt_id,
            )
            if operation == "delegate":
                graph.add_delegation(
                    delegation_id=f"delegate:{operation_id}:{index}",
                    edge_id=f"edge:{operation_id}:{index}",
                    parent_work_item_id=self._work_item_id,
                    child=child_item,
                )
            elif operation == "spawn":
                graph.add_spawn(
                    spawn_id=f"spawn:{operation_id}:{index}",
                    edge_id=f"edge:{operation_id}:{index}",
                    parent_work_item_id=self._work_item_id,
                    child=child_item,
                    supervision_policy=getattr(
                        self._runtime.work_runtime.policy,
                        "supervisor_policy",
                        "parent_until_detached",
                    ),
                )
            child_work_ids.append(child.work_item_id)
            prepared_children.append(child_item)
            if operation != "fan_out":
                graph.add_budget_allocation(budget)
                graph.add_capability_allocation(capabilities)
            agent_refs.append(agent_ref.to_dict())
            if child.fork_receipt is None:
                raise RuntimeError("forked child is missing its durable receipt")
            fork_receipts.append(child.fork_receipt.to_dict())
            transfer_receipts.append(receipt.to_dict())
            budget_allocations.append(_allocation_payload(budget))
            capability_allocations.append(_allocation_payload(capabilities))

        allocated_requests = sum(
            int(item.get("limits", {}).get("model_requests", 0))
            for item in budget_allocations
        )
        self._engine._model_requests_reserved = int(
            getattr(self._engine, "_model_requests_reserved", 0)
        ) + allocated_requests

        if operation == "fan_out":
            graph.add_fan_out(
                group_id=f"fan_out:{operation_id}",
                parent_work_item_id=self._work_item_id,
                children=prepared_children,
            )
            for item in budget_allocations:
                graph.add_budget_allocation(_budget_allocation(item))
            for item in capability_allocations:
                graph.add_capability_allocation(_capability_allocation(item))

        if operation == "handoff":
            target = str(payload.get("target") or "")
            agent_ref = _agent_reference(target)
            if not _resolver_available(self._runtime, agent_ref):
                from .work_runtime import WorkRuntimeError

                raise WorkRuntimeError(
                    "missing_destination_resolver",
                    "handoff destination agent is unavailable",
                    operation_id=operation_id,
                )
            target_agent_id = AgentIdentity.generate()
            budget = BudgetAllocation(
                f"budget:{operation_id}:handoff",
                self._work_item_id,
                self._work_item_id,
                {},
            )
            capabilities = CapabilityAllocation(
                f"capability:{operation_id}:handoff",
                self._work_item_id,
                self._work_item_id,
                [],
            )
            receipt = self._execute_child_transfer(
                operation_id=f"{operation_id}:transfer",
                operation=operation,
                child=None,
                agent_ref=agent_ref,
                target_agent_id=target_agent_id,
                budget=budget,
                capabilities=capabilities,
                destination_resolved=True,
            )
            if receipt.terminal_disposition != "accepted":
                from .work_runtime import WorkRuntimeError

                raise WorkRuntimeError(
                    "context_transfer_rejected",
                    receipt.failure_code or "context transfer was rejected",
                    operation_id=operation_id,
                )
            graph.transfer_owner(
                self._work_item_id,
                expected_generation=graph.work_items[self._work_item_id].owner.generation,
                to_agent_id=target_agent_id,
                transfer_id=f"ownership:{operation_id}",
                context_transfer_ref=receipt.receipt_id,
            )
            agent_refs.append(agent_ref.to_dict())
            transfer_receipts.append(receipt.to_dict())

        if operation == "join":
            for child_operation in payload.get("children", []):
                child_receipt = next(
                    (
                        item for item in graph.operation_receipts
                        if item.operation_id == str(child_operation)
                    ),
                    None,
                )
                if child_receipt is None or child_receipt.descriptor is None:
                    raise ValueError("join child operation is not durable")
                child_work_ids.extend(
                    WorkItemIdentity(item)
                    for item in WorkDescriptor.from_dict(
                        child_receipt.descriptor
                    ).child_work_item_ids
                )
                referenced_child_session_ids.extend(
                    WorkDescriptor.from_dict(
                        child_receipt.descriptor
                    ).child_session_ids
                )
            graph.declare_join(
                join_id=f"join:{operation_id}",
                parent_work_item_id=self._work_item_id,
                child_work_item_ids=child_work_ids,
                policy=cast(JoinPolicy, str(payload.get("policy", "all"))),
                quorum=payload.get("quorum"),
                reducer_ref=payload.get("reducer_ref"),
                reducer_digest=payload.get("reducer_digest"),
            )

        requirements = list(agent_refs)
        requirements.append(
            ResolverReference(
                ResolverNamespace.CHECKPOINT_STORE,
                "default:session",
                "checkpoint.session",
            ).to_dict()
        )
        return WorkDescriptor(
            operation_id=operation_id,
            operation=operation,
            parent_session_id=self._session_id.value,
            parent_work_item_id=self._work_item_id.value,
            child_session_ids=(
                [item.session_id.value for item in child_sessions]
                + referenced_child_session_ids
            ),
            child_work_item_ids=[item.value for item in child_work_ids],
            agent_refs=agent_refs,
            task_input=dict(payload),
            fork_receipts=fork_receipts,
            transfer_receipts=transfer_receipts,
            budget_allocations=budget_allocations,
            capability_allocations=capability_allocations,
            artifact_refs=[],
            resolver_requirements=requirements,
            graph_depth=_graph_depth(graph, self._work_item_id),
            fan_out_width=max(1, len(child_sessions)),
        )

    def _effective_child_budget(
        self,
        declared: Mapping[str, Any],
        *,
        parent_request_remaining: Optional[int],
    ) -> dict[str, Any]:
        """Intersect the one child declaration with every active authority."""

        result = dict(declared)
        requested = result.get("model_requests")
        if requested is None:
            requested = self._engine.budget.max_model_requests
        if requested is None:
            return result
        if not isinstance(requested, int) or isinstance(requested, bool) or requested < 0:
            raise ValueError("child model_requests budget must be a non-negative integer")
        ceilings = [requested]
        if parent_request_remaining is not None:
            ceilings.append(max(0, int(parent_request_remaining)))
        policy = self._runtime.work_runtime.policy
        runtime_ceiling = dict(policy.budget_ceiling or {}).get("model_requests")
        if runtime_ceiling is not None:
            ceilings.append(int(runtime_ceiling))
        result["model_requests"] = min(ceilings)
        return result

    def _execute_child_transfer(
        self,
        *,
        operation_id: str,
        operation: str,
        child: Optional["Session"],
        agent_ref: ResolverReference,
        target_agent_id: AgentIdentity,
        budget: BudgetAllocation,
        capabilities: CapabilityAllocation,
        destination_resolved: bool,
    ) -> Any:
        head = self._require_head()
        snapshot = self._load_snapshot(head)
        state, _, _ = self._restore_core_state(snapshot)
        component = next(
            (item for item in snapshot.components if item.slot == "conversation"),
            None,
        )
        conversation = (
            component.decode(self._runtime.component_registry)
            if component is not None
            else ConversationSnapshotComponent.from_exchange_log(
                ExchangeLog(log_id=f"transfer_log:{self._session_id.value}")
            )
        )
        if not isinstance(conversation, ConversationSnapshotComponent):
            raise TypeError("source conversation snapshot is invalid")
        policy_digest = _stable_digest("context.none")
        projector_digest = _stable_digest("projector.none")
        plan = ContextTransferPlan.create(
            operation_id=operation_id,
            operation_kind=operation,
            source_session_id=self._session_id,
            source_run_id=self._run_id,
            source_work_item_id=self._work_item_id,
            source_snapshot_id=snapshot.snapshot_id,
            source_head_generation=head.generation,
            source_head_digest=snapshot.integrity.digest,
            destination_agent_id=target_agent_id,
            destination_agent_ref=agent_ref,
            destination_provider="qitos.local",
            destination_model="qitos.agent",
            destination_api_mode="offline",
            context_policy="none",
            context_policy_ref="context.none",
            context_policy_digest=policy_digest,
            budget_request=budget,
            capability_request=capabilities,
            source_schema_id="state.qitos",
            destination_schema_id="state.qitos",
            state_projector_ref="projector.none",
            state_projector_digest=projector_digest,
            state_projector_capability="state.project.none",
            required_components=("authority",),
        )
        requested_capabilities = set(capabilities.capabilities)
        runtime_ceiling = set(self._runtime.work_runtime.policy.capability_ceiling)
        caller_capabilities = (
            requested_capabilities & runtime_ceiling
            if runtime_ceiling
            else requested_capabilities
        )
        capability_authorities = {
            "parent_grant": requested_capabilities,
            "destination_policy": requested_capabilities,
            "tool_environment": requested_capabilities,
            "artifact_access": requested_capabilities,
            "caller_transfer_policy": caller_capabilities,
        }
        requested_budget = dict(budget.limits)
        runtime_budget = dict(
            self._runtime.work_runtime.policy.budget_ceiling or requested_budget
        )
        budget_authorities = {
            "parent_grant": requested_budget,
            "destination_policy": requested_budget,
            "tool_environment": requested_budget,
            "artifact_access": requested_budget,
            "caller_transfer_policy": runtime_budget,
        }
        receipt = execute_context_transfer(
            plan,
            conversation=conversation,
            observed_source_head_digest=snapshot.integrity.digest,
            source_state=state.to_dict(),
            projector=None,
            capability_authorities=capability_authorities,
            budget_authorities=budget_authorities,
            destination_codec_capabilities=(),
            available_artifact_ids=(),
            authorized_artifact_ids=(),
            destination_agent_resolved=destination_resolved,
            evaluated_at=_utc_now(),
        )
        if child is not None and receipt.plan.budget_request.child_work_item_id != child.work_item_id:
            raise RuntimeError("transfer receipt child identity mismatched its fork")
        return receipt

    def _rebase_transferred_child(
        self,
        child: "Session",
        *,
        task: str,
        receipt: Any,
        source_snapshot: SessionSnapshot,
    ) -> None:
        """Replace forked parent input with the explicit transfer projection."""

        source_component_item = next(
            (item for item in source_snapshot.components if item.slot == "conversation"),
            None,
        )
        source_log = (
            source_component_item.decode(self._runtime.component_registry).exchange_log
            if source_component_item is not None
            else ExchangeLog(log_id=f"transfer_source:{self._session_id.value}")
        )
        source_payload = source_log.to_persistence_dict()
        selected_ids = set(receipt.selected_item_ids)
        queued_ids = {
            str(item.get("item_id")) for item in receipt.queued_steering
        }
        child_log = ExchangeLog.from_dict(
            {
                "schema_version": source_payload["schema_version"],
                "log_id": f"session_log_{child.session_id.value}",
                "items": [
                    item
                    for item in source_payload["items"]
                    if item.get("item_id") in selected_ids
                ],
                "queued_steering": [
                    item
                    for item in source_payload["queued_steering"]
                    if item.get("item_id") in queued_ids
                ],
            }
        )
        parent_graph = getattr(self._engine, "_qitos_work_graph", None)
        parent_state, parent_task, parent_step = self._restore_core_state(
            source_snapshot
        )
        try:
            clear_session_runtime(self._engine)
            granted = receipt.granted_budget
            limit = (
                granted.limits.get("model_requests")
                if granted is not None
                else None
            )
            self._engine.budget.max_model_requests = (
                int(limit) if limit is not None else None
            )
            self._engine._model_requests_consumed = 0
            self._engine._model_requests_reserved = 0
            self._engine._token_usage = 0
            self._engine._qitos_exchange_log = child_log
            setattr(
                self._engine,
                "_qitos_conversation_component",
                ConversationSnapshotComponent.from_exchange_log(child_log),
            )
            setattr(
                self._engine,
                "_qitos_work_graph",
                WorkGraph(f"work_graph:{child.session_id.value}"),
            )
            child_state = self._engine.agent.init_state(task)
            if not isinstance(child_state, StateSchema):
                raise TypeError("transferred child requires StateSchema state")
            child_head = child._require_head()
            child._commit_snapshot(
                state=child_state,
                task=task,
                lifecycle=SessionLifecycle.PAUSED,
                step_id=0,
                expected_head=child_head,
                expected_owner_run_id=child.run_id.value,
                pause_safety=PauseSafety(
                    boundary=SafeBoundaryKind.AFTER_MODEL_RESULT,
                    completed_slots_recorded=True,
                    open_slots_recorded=True,
                    framework_workers_quiesced=True,
                    unresolved_effect_count=0,
                ),
            )
        finally:
            clear_session_runtime(self._engine)
            self._restore_budget(source_snapshot)
            self._restore_runtime_components(
                source_snapshot,
                state=parent_state,
                task=parent_task,
                step_id=parent_step,
            )
            if isinstance(parent_graph, WorkGraph):
                setattr(self._engine, "_qitos_work_graph", parent_graph)
            self._engine._session_handle = self
            self._engine._session_run_id = self._run_id.value
            self._engine._active_state = parent_state
            self._engine._active_task_obj = (
                parent_task if isinstance(parent_task, Task) else None
            )
            self._engine._active_task = (
                parent_task.objective
                if isinstance(parent_task, Task)
                else str(parent_task)
            )

    def delegate(
        self, agent: str, *, task: str, operation_id: str | None = None
    ) -> Any:
        return self.submit_work(
            "delegate", {"agent": str(agent), "task": str(task)}, operation_id=operation_id
        )

    def spawn(
        self, agent: str, *, task: str, operation_id: str | None = None
    ) -> Any:
        return self.submit_work(
            "spawn", {"agent": str(agent), "task": str(task)}, operation_id=operation_id
        )

    def fan_out(
        self, specs: Iterable[Mapping[str, Any]], *, operation_id: str | None = None
    ) -> Any:
        tasks = [dict(item) for item in specs]
        runtime_policy = getattr(
            getattr(self._runtime, "work_runtime", None), "policy", None
        )
        maximum = int(getattr(runtime_policy, "maximum_children_per_operation", 64))
        if not tasks or len(tasks) > maximum:
            raise ValueError("fan_out child count exceeds the runtime admission bound")
        return self.submit_work("fan_out", {"tasks": tasks}, operation_id=operation_id)

    def handoff(
        self, agent: str, *, rationale: str = "handoff", operation_id: str | None = None
    ) -> Any:
        return self.submit_work(
            "handoff",
            {"target": str(agent), "rationale": str(rationale)},
            operation_id=operation_id,
        )

    def join(
        self,
        children: Iterable[str],
        *,
        policy: str = "all",
        quorum: int | None = None,
        reducer_ref: str | None = None,
        reducer_digest: str | None = None,
        operation_id: str | None = None,
    ) -> Any:
        return self.submit_work(
            "join",
            {
                "children": list(children),
                "policy": policy,
                "quorum": quorum,
                "reducer_ref": reducer_ref,
                "reducer_digest": reducer_digest,
            },
            operation_id=operation_id,
        )

    def _commit_work_graph(self) -> None:
        with self._lock:
            graph = getattr(self._engine, "_qitos_work_graph", None)
            if not isinstance(graph, WorkGraph):
                return
            head = self._require_head()
            snapshot = self._load_snapshot(head)
            state = self._engine.current_state
            task: str | Task = self._engine._active_task_obj or self._engine._active_task
            if state is None:
                state, task, step_id = self._restore_core_state(snapshot)
            else:
                step_id = int(getattr(state, "current_step", 0))
            lifecycle = SessionLifecycle(head.lifecycle)
            pause_safety = None
            if lifecycle is SessionLifecycle.PAUSED:
                raw_safety = _component_payload(
                    snapshot, ComponentSlot.ENGINE_PROGRESS.value
                ).get("pause_safety")
                if isinstance(raw_safety, Mapping):
                    pause_safety = PauseSafety(
                        boundary=SafeBoundaryKind(raw_safety["boundary"]),
                        completed_slots_recorded=raw_safety[
                            "completed_slots_recorded"
                        ],
                        open_slots_recorded=raw_safety["open_slots_recorded"],
                        framework_workers_quiesced=raw_safety[
                            "framework_workers_quiesced"
                        ],
                        unresolved_effect_count=raw_safety[
                            "unresolved_effect_count"
                        ],
                    )
            committed_head = self._commit_snapshot(
                state=state,
                task=task,
                lifecycle=lifecycle,
                step_id=step_id,
                expected_head=head,
                expected_owner_run_id=self._run_id.value,
                pause_safety=pause_safety,
            )
            self._publish_work_graph_facts(graph, committed_head)

    def _commit_work_graph_value(self, graph: WorkGraph) -> None:
        """Persist a captured logical graph even after its worker was unbound."""

        self._collect_child_completions(graph)

        if (
            self._engine._session_handle is self
            and getattr(self._engine, "_qitos_work_graph", None) is graph
        ):
            self._commit_work_graph()
            return
        with self._bound_runtime_cache():
            setattr(self._engine, "_qitos_work_graph", graph)
            self._commit_work_graph()

    def _collect_child_completions(self, graph: WorkGraph) -> None:
        """Read verified child heads; scheduler return values are not completion truth."""
        completed = {item.work_item_id for item in graph.completions}
        for identity, work in tuple(graph.work_items.items()):
            if work.parent_work_item_id != self._work_item_id or identity in completed:
                continue
            head = self._store.get_session_head(work.session_ref.value)
            if head is None or head.lifecycle not in {"completed", "failed", "cancelled"}:
                continue
            snapshot = self._load_snapshot(head)
            lineage = _fork_lineage(snapshot, required=True)
            agent = _agent_state(snapshot)
            if (lineage.work_item_id != identity or lineage.source_session_id != self._session_id
                    or agent.agent_id != work.owner.agent_id):
                raise _session_error(SessionErrorCode.INVALID_IDENTITY_RELATIONSHIP,
                                     "Child completion identity does not match its durable declaration.",
                                     recoverable=False)
            outcome = ToolResult(
                status="success" if head.lifecycle == "completed" else "cancelled" if head.lifecycle == "cancelled" else "error",
                output={"session_id": head.session_id, "snapshot_id": head.snapshot_id,
                        "checkpoint_id": head.checkpoint_id, "generation": head.generation,
                        "final_result": agent.state.get("final_result"),
                        "stop_reason": agent.state.get("stop_reason")},
                error=None if head.lifecycle == "completed" else "child Session terminated without success",
                error_kind=None if head.lifecycle == "completed" else "execution",
                error_code=None if head.lifecycle == "completed" else f"child_session_{head.lifecycle}",
            )
            graph.record_completion(completion_id=f"session_terminal:{head.checkpoint_id}", work_item_id=identity,
                                    owner_generation=work.owner.generation, outcome=outcome)
        for join in tuple(graph.joins):
            for completion in tuple(graph.completions):
                if completion.work_item_id in join.child_work_item_ids:
                    graph.accept_join_result(join.join_id, completion.work_item_id)

    def _publish_work_graph_facts(self, graph: WorkGraph, head: Any) -> None:
        """Project durable graph state into the canonical trajectory seam."""
        if self._runtime.event_sink is None:
            return
        from ..tracing.work_graph_reader import work_graph_event_record

        head_generation = int(getattr(head.generation, "value", head.generation))
        head_snapshot_id = str(
            getattr(head.snapshot_id, "value", head.snapshot_id)
        )
        head_checkpoint_id = str(
            getattr(head.checkpoint_id, "value", head.checkpoint_id)
        )
        record_provenance = {
            "source": "durable_work_graph",
            "graph_id": graph.graph_id,
            "head_generation": head_generation,
        }

        def publish(
            event_type: str,
            *,
            operation_id: str,
            payload: Mapping[str, Any],
            work_item_id: Optional[str] = None,
            parent_work_item_id: Optional[str] = None,
            attempt_id: Optional[str] = None,
            owner_generation: Optional[int] = None,
        ) -> None:
            self._runtime.publish_record(
                work_graph_event_record(
                    event_type,
                    session_id=self._session_id.value,
                    run_id=self._run_id.value,
                    operation_id=operation_id,
                    producer_authority="qitos.engine.session_runtime",
                    record_provenance=record_provenance,
                    payload=payload,
                    work_item_id=work_item_id,
                    parent_work_item_id=parent_work_item_id,
                    attempt_id=attempt_id,
                    owner_generation=owner_generation,
                )
            )

        for item in graph.work_items.values():
            allocation = next(
                (
                    candidate
                    for candidate in graph.budget_allocations
                    if candidate.allocation_id == item.budget_allocation_ref
                ),
                None,
            )
            publish(
                "work_declared",
                operation_id=f"graph:{graph.graph_id}:generation:{head_generation}",
                work_item_id=item.work_item_id.value,
                parent_work_item_id=(
                    item.parent_work_item_id.value
                    if item.parent_work_item_id is not None
                    else None
                ),
                owner_generation=item.owner.generation,
                payload={
                    "lifecycle": item.lifecycle,
                    "owner_id": item.owner.agent_id.value,
                    "detached": item.detached,
                    "effective_budget": (
                        dict(allocation.limits) if allocation is not None else {}
                    ),
                    "authoritative_head": {
                        "snapshot_id": head_snapshot_id,
                        "checkpoint_id": head_checkpoint_id,
                        "generation": head_generation,
                    },
                },
            )
        for delegation in graph.delegations:
            publish(
                "delegate_declared",
                operation_id=delegation.delegation_id,
                work_item_id=delegation.child_work_item_id.value,
                parent_work_item_id=delegation.parent_work_item_id.value,
                payload={
                    "operation": "delegate",
                    "await_child": delegation.await_child,
                },
            )
        for spawn in graph.spawns:
            publish(
                "spawn_declared",
                operation_id=spawn.spawn_id,
                work_item_id=spawn.child_work_item_id.value,
                parent_work_item_id=spawn.parent_work_item_id.value,
                payload={
                    "operation": "spawn",
                    "supervision_policy": spawn.supervision_policy,
                },
            )
        for group in graph.fan_out_groups:
            publish(
                "fan_out_declared",
                operation_id=group.group_id,
                work_item_id=group.parent_work_item_id.value,
                payload={
                    "operation": "fan_out",
                    "expected_child_ids": [
                        child.value for child in group.child_work_item_ids
                    ],
                },
            )
        for operation in graph.operation_receipts:
            if operation.descriptor is None:
                continue
            descriptor = WorkDescriptor.from_dict(operation.descriptor)
            for index, child_id in enumerate(descriptor.child_work_item_ids):
                if index < len(descriptor.transfer_receipts):
                    transfer = descriptor.transfer_receipts[index]
                    publish(
                        "context_transferred",
                        operation_id=f"{operation.operation_id}:transfer:{index}",
                        work_item_id=child_id,
                        parent_work_item_id=descriptor.parent_work_item_id,
                        payload={
                            "receipt_id": transfer.get("receipt_id"),
                            "terminal_disposition": transfer.get(
                                "terminal_disposition"
                            ),
                            "failure_code": transfer.get("failure_code"),
                            "effective_budget": dict(
                                (
                                    transfer.get("granted_budget") or {}
                                ).get("limits")
                                or {}
                            ),
                        },
                    )
        for ownership in graph.transfers:
            publish(
                "ownership_transfer_committed",
                operation_id=ownership.transfer_id,
                work_item_id=ownership.work_item_id.value,
                owner_generation=ownership.committed_generation,
                payload={
                    "from_owner_id": ownership.from_agent_id.value,
                    "to_owner_id": ownership.to_agent_id.value,
                    "context_transfer_ref": ownership.context_transfer_ref,
                },
            )
        for join in graph.joins:
            event_type = "join_closed" if join.state == "closed" else "join_declared"
            publish(
                event_type,
                operation_id=join.join_id,
                work_item_id=join.parent_work_item_id.value,
                payload={
                    "policy": join.policy,
                    "expected_child_ids": [
                        child.value for child in join.child_work_item_ids
                    ],
                    "accepted_child_ids": [
                        child.value for child in join.accepted_child_ids
                    ],
                    "outstanding_child_ids": [
                        child.value for child in join.outstanding_child_ids
                    ],
                    "discarded_child_ids": [
                        child.value for child in join.discarded_child_ids
                    ],
                },
            )
        for cancellation in graph.cancellations:
            item = graph.work_items[cancellation.work_item_id]
            publish(
                "cancellation_requested",
                operation_id=cancellation.cancellation_id,
                work_item_id=cancellation.work_item_id.value,
                attempt_id=f"cancel:{cancellation.cancellation_id}",
                owner_generation=item.owner.generation,
                payload={"propagation": cancellation.propagation},
            )
        for detachment in graph.detachments:
            publish(
                "child_detached",
                operation_id=detachment.detachment_id,
                work_item_id=detachment.child_work_item_id.value,
                parent_work_item_id=detachment.parent_work_item_id.value,
                payload={"supervisor_ref": detachment.supervisor_ref},
            )

    def _submit_steering(
        self,
        text: str,
        *,
        state: StateSchema,
        task: str | Task,
        step_id: int,
    ) -> SteeringReceipt:
        engine = self._engine
        log = getattr(engine, "_qitos_exchange_log", None)
        if not isinstance(log, ExchangeLog):
            log = ExchangeLog(log_id=f"session_log_{self._session_id.value}")
            engine._qitos_exchange_log = log
        receipts = tuple(getattr(engine, "_qitos_steering_receipts", ()) or ())
        sequence = max((item.sequence for item in receipts), default=-1) + 1
        lifecycle = SessionLifecycle(self._require_head().lifecycle)
        boundary_id = log.open_batch_id() or f"before_model_{step_id}"
        receipt = submit_steering(
            log,
            str(text),
            sequence=sequence,
            boundary_id=boundary_id,
            exchange_id=f"steering_exchange_{sequence}",
            session_status=lifecycle.value,
        )
        engine._qitos_steering_receipts = receipts + (receipt,)
        if receipt.disposition == "rejected":
            return receipt
        head = self._require_head()
        self._commit_snapshot(
            state=state,
            task=task,
            lifecycle=lifecycle,
            step_id=step_id,
            expected_head=head,
        )
        return receipt

    def run(self, *, steering: Optional[str] = None) -> "EngineResult[Any]":
        """Run or resume through the one canonical Engine loop."""
        from .interrupt import _clear_resume_values, _reset_interrupt_context

        with self._engine._session_runtime_lock:
            # Legacy step-resume values are not authorization for this Session.
            _clear_resume_values()
            _reset_interrupt_context()
            clear_session_runtime(self._engine)
            try:
                with self._lock:
                    head = self._require_head()
                    if head.owner_run_id != self._run_id.value:
                        raise _session_error(
                            SessionErrorCode.SUPERSEDED_OWNER,
                            "A superseded Session owner cannot run this head.",
                            recoverable=False,
                            metadata={"owner_run_id": self._run_id.value},
                        )
                    lifecycle = SessionLifecycle(head.lifecycle)
                    allowed = lifecycle_allows(lifecycle, SessionOperation.RUN) or (
                        lifecycle is SessionLifecycle.RESTORING
                    )
                    if not allowed:
                        raise _invalid_operation(lifecycle, SessionOperation.RUN)
                    snapshot = self._load_snapshot(head)
                    if _agent_state(snapshot).agent_id != self._agent_id:
                        raise _session_error(SessionErrorCode.SUPERSEDED_OWNER,
                                             "The Session's work ownership has transferred.", recoverable=False)
                    state, task, next_step = self._restore_core_state(snapshot)
                    if str(getattr(state, "stop_reason", "")) == "interrupt":
                        raise _session_error(
                            SessionErrorCode.UNSUPPORTED_CAPABILITY,
                            "Durable interactive approval requires a supported approval resolver.",
                            recoverable=True,
                            metadata={"capability": "session.approval.resume"},
                        )
                    self._restore_budget(snapshot)
                    self._restore_runtime_components(
                        snapshot, state=state, task=task, step_id=next_step
                    )
                    self._engine._session_handle = self
                    self._engine._session_run_id = self._run_id.value
                    self._engine._active_state = state
                    self._engine._active_task_obj = (
                        task if isinstance(task, Task) else None
                    )
                    self._engine._active_task = (
                        task.objective if isinstance(task, Task) else str(task)
                    )
                    self._transition(SessionLifecycle.RUNNING)
                    self._commit_snapshot(
                        state=state,
                        task=task,
                        lifecycle=SessionLifecycle.RUNNING,
                        step_id=next_step,
                        expected_head=head,
                    )

                try:
                    next_step = self._recover_tool_batch(
                        state=state,
                        task=task,
                        step_id=next_step,
                    )
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

                with self._lock:
                    if not (
                        self._pause_receipt is not None
                        and self._pause_receipt.status
                        is PersistenceReceiptStatus.PERSISTED
                    ):
                        terminal = _terminal_lifecycle(result)
                        if terminal is SessionLifecycle.WAITING_INPUT:
                            self._transition(SessionLifecycle.PAUSE_REQUESTED)
                            self._transition(SessionLifecycle.PAUSING)
                        self._transition(terminal)
                        current = self._require_head()
                        safety = None
                        if terminal is SessionLifecycle.WAITING_INPUT:
                            safety = self._runtime.lifecycle_policy.pause_safety(RuntimeSnapshotContext(
                                engine=self._engine, state=result.state, task=task,
                                lifecycle=terminal, step_id=int(result.state.current_step), session=self,
                            ))
                            safety.require_migratable()
                        else:
                            self._engine._qitos_tool_batch_snapshot = None
                        self._commit_snapshot(
                            state=result.state,
                            task=task,
                            lifecycle=terminal,
                            step_id=int(
                                getattr(result.state, "current_step", next_step)
                            ),
                            expected_head=current,
                            pause_safety=safety,
                        )
                    return result
            finally:
                clear_session_runtime(self._engine)

    def _fork_or_recover(self, operation_id: str) -> "Session":
        receipt = self._store.get_session_fork(operation_id)
        if receipt is None:
            if self._engine._session_handle is self and self._lifecycle is SessionLifecycle.RUNNING:
                if self._work_fork_snapshot is None:
                    raise _session_error(SessionErrorCode.UNSAFE_PAUSE_BOUNDARY,
                                         "Child work requires a recorded pre-action boundary.", recoverable=True)
                return self._fork_snapshot(self._work_fork_snapshot, operation_id=operation_id, work_source=True)
            return self.fork(operation_id=operation_id)
        if receipt.source_session_id != self._session_id.value:
            raise _session_error(
                SessionErrorCode.DUPLICATE_FORK_OPERATION,
                "Fork operation belongs to a different source Session.",
                recoverable=False,
            )
        source_record = self._store.get_session_snapshot(receipt.source_snapshot_id)
        child_record = self._store.get_session_snapshot(receipt.child_snapshot_id)
        child_head = self._store.get_session_head(receipt.child_session_id)
        if source_record is None or child_record is None or child_head is None:
            raise _session_error(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Committed fork receipt points to missing durable state.",
                recoverable=False,
            )
        if child_head.generation != receipt.owner_generation:
            raise _session_error(
                SessionErrorCode.SUPERSEDED_OWNER,
                "Prepared fork child was already advanced by another owner.",
                recoverable=False,
            )
        source = SessionSnapshot.from_dict(
            source_record.payload,
            component_registry=self._runtime.component_registry,
        )
        child_snapshot = SessionSnapshot.from_dict(
            child_record.payload,
            component_registry=self._runtime.component_registry,
        )
        child = Session(
            engine=self._engine,
            session_id=SessionIdentity(receipt.child_session_id),
            run_id=RunIdentity(receipt.child_run_id),
            agent_id=_agent_state(source).agent_id,
            references=child_snapshot.resolver_references,
            created_at=child_snapshot.created_at,
            state_type=self._state_type,
            work_item_id=WorkItemIdentity(receipt.child_work_item_id),
            attempt_id=AttemptIdentity(receipt.child_attempt_id),
            fork_receipt=receipt,
        )
        child._parent_run_id = _trace_lineage(source).run_id
        child._lifecycle = SessionLifecycle.RESTORING
        return child

    @classmethod
    def _fork_persisted(
        cls,
        engine: "Engine[Any, Any, Any]",
        session_id: SessionIdentity,
        snapshot: SessionSnapshot | SnapshotIdentity | str | None = None,
        *,
        operation_id: Optional[str] = None,
    ) -> "Session":
        """Bind a read-only source facade; only canonical fork may write a child."""
        store = engine.runtime.ensure_checkpoint_store()
        head = store.get_session_head(session_id.value)
        if head is None:
            raise _session_error(SessionErrorCode.SESSION_NOT_FOUND,
                                 "Source Session was not found.", recoverable=True)
        record = store.get_session_snapshot(head.snapshot_id)
        if record is None:
            raise _session_error(SessionErrorCode.SNAPSHOT_NOT_FOUND,
                                 "Source snapshot was not found.", recoverable=True)
        source = SessionSnapshot.from_dict(
            record.payload, component_registry=engine.runtime.component_registry,
        )
        progress = _component_payload(source, ComponentSlot.ENGINE_PROGRESS.value)
        task = _task_from_progress(progress)
        template = engine.agent.init_state(task.objective if isinstance(task, Task) else str(task))
        agent_state = _agent_state(source)
        if not isinstance(template, StateSchema) or _state_schema_id(type(template)) != agent_state.state_schema:
            raise _session_error(SessionErrorCode.RESOLVER_TYPE_MISMATCH,
                                 "Source state schema does not match composition.", recoverable=True)
        lineage = _fork_lineage(source, required=True)
        facade = cls(
            engine=engine, session_id=session_id, run_id=RunIdentity(head.owner_run_id),
            agent_id=agent_state.agent_id, references=source.resolver_references,
            created_at=source.created_at, state_type=type(template),
            work_item_id=lineage.work_item_id, attempt_id=lineage.attempt_id,
        )
        # No restore, owner claim, source commit, or source component activation.
        return facade.fork(snapshot or source.snapshot_id, operation_id=operation_id)

    def fork(
        self,
        snapshot: SessionSnapshot | SnapshotIdentity | str | None = None,
        *,
        operation_id: Optional[str] = None,
    ) -> "Session":
        """Create an isolated durable child from one verified immutable snapshot."""
        return self._fork_snapshot(snapshot, operation_id=operation_id)

    def _capture_work_fork_boundary(self, state: StateSchema, task: str | Task, step_id: int) -> None:
        """Pin a quiescent immutable source before any tool in the batch starts."""
        self._work_fork_snapshot = None
        context = RuntimeSnapshotContext(engine=self._engine, state=state, task=task,
                                         lifecycle=SessionLifecycle.RUNNING, step_id=step_id, session=self)
        safety = self._runtime.lifecycle_policy.pause_safety(context)
        if not safety.migratable:
            return
        head = self._commit_snapshot(state=state, task=task, lifecycle=SessionLifecycle.RUNNING,
                                     step_id=step_id, expected_head=self._require_head(), pause_safety=safety)
        self._work_fork_snapshot = SnapshotIdentity(head.snapshot_id)

    def _fork_snapshot(
        self, snapshot: SessionSnapshot | SnapshotIdentity | str | None = None, *,
        operation_id: Optional[str] = None, work_source: bool = False,
    ) -> "Session":
        """Sole child-snapshot implementation shared by public fork and work."""
        if ATOMIC_SESSION_FORK not in self._store.session_capabilities():
            raise _session_error(
                SessionErrorCode.UNSUPPORTED_CAPABILITY,
                "Checkpoint store does not support atomic Session fork.",
                recoverable=True,
                metadata={"capability": ATOMIC_SESSION_FORK},
            )
        source_head = self._require_head()
        supplied_snapshot = snapshot if isinstance(snapshot, SessionSnapshot) else None
        if snapshot is None:
            source_snapshot_id = source_head.snapshot_id
        elif isinstance(snapshot, SessionSnapshot):
            source_snapshot_id = snapshot.snapshot_id.value
        elif isinstance(snapshot, SnapshotIdentity):
            source_snapshot_id = snapshot.value
        else:
            source_snapshot_id = SnapshotIdentity(str(snapshot)).value
        source_record = self._store.get_session_snapshot(source_snapshot_id)
        if source_record is None:
            raise _session_error(
                SessionErrorCode.SNAPSHOT_NOT_FOUND,
                "Source Session snapshot was not found.",
                recoverable=True,
            )
        if source_record.session_id != self._session_id.value:
            raise _session_error(
                SessionErrorCode.SNAPSHOT_SESSION_MISMATCH,
                "Source snapshot does not belong to this Session.",
                recoverable=False,
            )
        source = SessionSnapshot.from_dict(
            source_record.payload,
            component_registry=self._runtime.component_registry,
        )
        if supplied_snapshot is not None and (
            supplied_snapshot.canonical_json() != source.canonical_json()
        ):
            raise _session_error(
                SessionErrorCode.CORRUPT_SNAPSHOT,
                "Explicit snapshot differs from its persisted immutable record.",
                recoverable=False,
            )
        pinned_work_source = (work_source and source.snapshot_id == self._work_fork_snapshot
                              and source.lifecycle is SessionLifecycle.RUNNING)
        if not pinned_work_source and not lifecycle_allows(source.lifecycle, SessionOperation.FORK):
            raise _invalid_operation(source.lifecycle, SessionOperation.FORK)
        _require_fork_safe(source, self._runtime.component_registry)
        source_lineage = _fork_lineage(source, required=True)

        fork_id = operation_id or f"fork_{uuid4().hex}"
        child_session = SessionIdentity.generate()
        child_run = RunIdentity.generate()
        child_work = WorkItemIdentity.generate()
        child_attempt = AttemptIdentity.generate()
        child_snapshot_id = SnapshotIdentity.generate()
        child_checkpoint_id = CheckpointIdentity.generate()
        child_lineage = ForkLineageSnapshotComponent(
            work_item_id=child_work,
            attempt_id=child_attempt,
            source_session_id=self._session_id,
            source_snapshot_id=source.snapshot_id,
            source_checkpoint_id=CheckpointIdentity(source_record.checkpoint_id),
            source_work_item_id=source_lineage.work_item_id,
            fork_operation_id=fork_id,
        )
        from ..core.session import CORE_SNAPSHOT_COMPONENT_CODECS

        codecs = {codec.slot: codec for codec in CORE_SNAPSHOT_COMPONENT_CODECS}
        source_progress = dict(
            _component_payload(source, ComponentSlot.ENGINE_PROGRESS.value)
        )
        source_progress["lifecycle"] = SessionLifecycle.PAUSED.value
        source_progress["pause_safety"] = {
            "boundary": "after_model_result",
            "completed_slots_recorded": True,
            "open_slots_recorded": True,
            "framework_workers_quiesced": True,
            "unresolved_effect_count": 0,
        }
        components = [
            item
            for item in source.components
            if item.slot not in {
                ComponentSlot.ENGINE_PROGRESS.value,
                ComponentSlot.TRACE_LINEAGE.value,
                ComponentSlot.FORK_LINEAGE.value,
            }
        ]
        components.extend(
            (
                SnapshotComponent.from_value(
                    codecs[ComponentSlot.ENGINE_PROGRESS.value], source_progress
                ),
                SnapshotComponent.from_value(
                    codecs[ComponentSlot.TRACE_LINEAGE.value],
                    TraceLineageSnapshotComponent(
                        run_id=child_run,
                        trace_complete=True,
                        parent_run_id=_trace_lineage(source).run_id,
                    ),
                ),
                SnapshotComponent.from_value(
                    codecs[ComponentSlot.FORK_LINEAGE.value], child_lineage
                ),
            )
        )
        now = _utc_now()
        child_snapshot = SessionSnapshot.create(
            snapshot_id=child_snapshot_id,
            session_id=child_session,
            head_generation=HeadGeneration(0),
            lifecycle=SessionLifecycle.PAUSED,
            created_at=now,
            timing=SnapshotTiming(
                captured_at=now,
                pause_requested_at=now,
                safe_boundary_at=now,
            ),
            components=components,
            resolver_references=source.resolver_references,
            artifact_refs=source.artifact_refs,
            component_registry=self._runtime.component_registry,
        )
        request = SessionForkRequest(
            operation_id=fork_id,
            source_session_id=self._session_id.value,
            source_snapshot_id=source.snapshot_id.value,
            source_checkpoint_id=source_record.checkpoint_id,
            source_work_item_id=source_lineage.work_item_id.value,
            child_work_item_id=child_work.value,
            child_attempt_id=child_attempt.value,
            child_commit=SessionSnapshotCommit(
                session_id=child_session.value,
                snapshot_id=child_snapshot_id.value,
                checkpoint_id=child_checkpoint_id.value,
                owner_run_id=child_run.value,
                lifecycle=SessionLifecycle.PAUSED.value,
                payload=child_snapshot.to_dict(),
            ),
        )
        try:
            receipt = self._store.fork_session_snapshot(request)
        except CheckpointSessionError as exc:
            raise _translate_checkpoint_error(exc) from exc
        child = Session(
            engine=self._engine,
            session_id=SessionIdentity(receipt.child_session_id),
            run_id=RunIdentity(receipt.child_run_id),
            agent_id=_agent_state(source).agent_id,
            references=source.resolver_references,
            created_at=child_snapshot.created_at,
            state_type=self._state_type,
            work_item_id=WorkItemIdentity(receipt.child_work_item_id),
            attempt_id=AttemptIdentity(receipt.child_attempt_id),
            fork_receipt=receipt,
        )
        child._parent_run_id = _trace_lineage(source).run_id
        # The durable child remains paused until run commits its first head;
        # this process-local facade has already reconstructed the owner view.
        child._lifecycle = SessionLifecycle.RESTORING
        return child

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

    def _persist_tool_batch(
        self,
        snapshot: ToolBatchSnapshot,
        *,
        state: StateSchema,
        task: str | Task,
        step_id: int,
    ) -> tuple[ToolBatchSnapshot, SessionHeadRecord]:
        """Advance the canonical Session head for one batch-state transition."""
        with self._lock:
            head = self._require_head()
            if head.owner_run_id != self._run_id.value:
                raise _session_error(
                    SessionErrorCode.SUPERSEDED_OWNER,
                    "A superseded Session owner cannot persist a tool terminal.",
                    recoverable=False,
                    metadata={"owner_run_id": self._run_id.value},
                )
            durable = replace(
                snapshot,
                slots=tuple(
                    replace(slot, durability_status="persisted")
                    if slot.terminal and slot.durability_status == "pending"
                    else slot
                    for slot in snapshot.slots
                ),
            )
            previous = getattr(self._engine, "_qitos_tool_batch_snapshot", None)
            self._engine._qitos_tool_batch_snapshot = durable
            try:
                persisted = self._commit_snapshot(
                    state=state,
                    task=task,
                    lifecycle=SessionLifecycle.RUNNING,
                    step_id=step_id,
                    expected_head=head,
                    expected_owner_run_id=self._run_id.value,
                )
            except CheckpointSessionError as exc:
                self._engine._qitos_tool_batch_snapshot = previous
                raise _translate_checkpoint_error(exc) from exc
            return durable, persisted

    def _record_tool_conversation_terminal(
        self, receipt: ToolTerminalReceipt
    ) -> None:
        conversation = getattr(self._engine, "_qitos_exchange_log", None)
        if not isinstance(conversation, ExchangeLog):
            return
        open_batch = conversation.open_batch_id()
        if open_batch != receipt.batch_snapshot.batch_id:
            return
        builder = ToolBatchBuilder(conversation, open_batch)
        call = next(
            (
                item
                for item in builder.calls
                if item.identity.call_id == receipt.slot.slot_id
                or item.identity.call_id == receipt.slot.action_id
            ),
            None,
        )
        if call is None:
            raise ValueError("tool terminal has no matching conversation call")
        item_digest = hashlib.sha256(
            (
                f"{open_batch}:{call.identity.call_id}:"
                f"{receipt.slot.attempt_id.value}"
            ).encode("utf-8")
        ).hexdigest()[:24]
        builder.record_result(
            ToolResultItem(
                item_id=f"tool_result_{item_digest}",
                exchange_id=builder.exchange_id,
                identity=call.identity,
                batch_id=open_batch,
                result=receipt.result,
                synthetic=receipt.result.error_code == "missing_worker",
                closure_reason=(
                    "missing_worker"
                    if receipt.result.error_code == "missing_worker"
                    else None
                ),
            )
        )
        self._engine._qitos_exchange_log = conversation
        if conversation.open_batch_id() is None:
            receipts = tuple(
                getattr(self._engine, "_qitos_steering_receipts", ()) or ()
            )
            self._engine._qitos_steering_receipts = reconcile_steering_receipts(
                conversation,
                receipts,
                boundary_id=f"closed_{open_batch}",
            )

    def _recover_tool_batch(
        self,
        *,
        state: StateSchema,
        task: str | Task,
        step_id: int,
    ) -> int:
        snapshot = getattr(self._engine, "_qitos_tool_batch_snapshot", None)
        if not isinstance(snapshot, ToolBatchSnapshot):
            return step_id
        if self._engine.executor is None:
            raise _session_error(
                SessionErrorCode.MISSING_RESOLVER,
                "Incomplete tool batch recovery requires its tool registry.",
                recoverable=True,
            )

        def _terminal(receipt: ToolTerminalReceipt) -> None:
            self._record_tool_conversation_terminal(receipt)
            durable, _ = self._persist_tool_batch(
                receipt.batch_snapshot,
                state=state,
                task=task,
                step_id=step_id,
            )
            self._engine._qitos_tool_batch_snapshot = durable

        execution = self._engine.executor.resume_batch(
            snapshot,
            terminal_callback=_terminal,
            partial_batch_callback=lambda current: None,
            env=self._engine.env,
            state=state,
        )
        closed = getattr(self._engine, "_qitos_tool_batch_snapshot", None)
        if not isinstance(closed, ToolBatchSnapshot):
            closed = execution.snapshot
        if not closed.closed:
            return step_id

        actions = [
            Action.from_dict(dict(slot.action_payload))
            for slot in sorted(closed.slots, key=lambda item: item.declaration_index)
        ]
        payload = closed.decision_payload
        decision = Decision.act(
            actions,
            rationale=payload.get("rationale"),
            meta=dict(payload.get("meta") or {}),
        )
        from .states import StepRecord

        record = StepRecord(step_id=step_id, decision=decision, actions=actions)
        results = list(closed.results_in_declaration_order)
        record.action_results = results
        observation = self._engine._build_observation_after_action(
            state,
            step_id,
            time.monotonic(),
            decision,
            [item.to_dict() for item in results],
        )
        record.observation = observation
        commit_results = getattr(self._engine.agent, "commit_action_results", None)
        if callable(commit_results):
            commit_results(state, actions, results, step_id=step_id)
        self._engine._run_reduce(state, observation, decision, record)
        if int(getattr(state, "current_step", 0)) <= step_id:
            state.advance_step()
        self._engine._qitos_tool_batch_snapshot = None
        self._commit_snapshot(
            state=state,
            task=task,
            lifecycle=SessionLifecycle.RUNNING,
            step_id=step_id + 1,
            expected_head=self._require_head(),
            expected_owner_run_id=self._run_id.value,
        )
        return step_id + 1

    def _on_safe_boundary(
        self,
        *,
        state: StateSchema,
        task: str | Task,
        step_id: int,
        advance_step: bool = True,
    ) -> bool:
        """Engine callback after a complete step and before the next operation."""
        context = RuntimeSnapshotContext(
            engine=self._engine,
            state=state,
            task=task,
            lifecycle=SessionLifecycle.PAUSING,
            step_id=step_id,
            session=self,
            owner_id=self._agent_id.value,
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
            if advance_step and int(getattr(state, "current_step", 0)) <= step_id:
                state.advance_step()
            batch = getattr(self._engine, "_qitos_tool_batch_snapshot", None)
            if isinstance(batch, ToolBatchSnapshot) and batch.closed:
                self._engine._qitos_tool_batch_snapshot = None
            try:
                self._commit_snapshot(
                    state=state,
                    task=task,
                    lifecycle=SessionLifecycle.PAUSED,
                    step_id=step_id + 1 if advance_step else step_id,
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
        with engine._session_runtime_lock:
            clear_session_runtime(engine)
            engine._token_usage = 0
            engine._model_requests_consumed = 0
            engine._model_requests_reserved = 0
            try:
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
                    work_item_id=WorkItemIdentity.generate(),
                    attempt_id=AttemptIdentity.generate(),
                )
                session._commit_snapshot(
                    state=state,
                    task=task,
                    lifecycle=SessionLifecycle.CREATED,
                    step_id=0,
                    expected_head=None,
                )
                return session
            finally:
                clear_session_runtime(engine)

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
        continuation = resolved.get(ResolverNamespace.PROVIDER_CONTINUATION)
        artifacts = resolved.get(ResolverNamespace.ARTIFACT_STORE)
        if continuation is not None or artifacts is not None:
            config = dict(getattr(agent, "config", {}) or {})
            if continuation is not None:
                config["continuation_resolver"] = continuation.resource
            if artifacts is not None:
                config["artifact_resolver"] = artifacts.resource
            agent.config = config

        progress = _component_payload(snapshot, ComponentSlot.ENGINE_PROGRESS.value)
        persisted_runtime = progress.get("runtime_composition")
        persisted_launch = (
            persisted_runtime.get("launch_metadata")
            if isinstance(persisted_runtime, Mapping)
            else None
        )
        expected_digest = (
            str(persisted_launch.get("config_digest") or "")
            if isinstance(persisted_launch, Mapping)
            else ""
        )
        actual_digest = str(runtime.launch_metadata.get("config_digest") or "")
        if expected_digest and expected_digest != actual_digest:
            raise _session_error(
                SessionErrorCode.CONFIG_DIGEST_MISMATCH,
                "Restored composition does not match the persisted agent config.",
                recoverable=True,
                metadata={
                    "expected_config_digest": expected_digest,
                    "actual_config_digest": actual_digest or "missing",
                },
            )
        budget_payload = _component_payload(
            snapshot, ComponentSlot.BUDGET_CAPABILITY.value
        )
        from .states import RuntimeBudget

        budget = RuntimeBudget(
            max_steps=int(budget_payload.get("max_steps", 10)),
            max_runtime_seconds=budget_payload.get("max_runtime_seconds"),
            max_tokens=budget_payload.get("max_tokens"),
            max_model_requests=budget_payload.get("max_model_requests"),
        )
        execution_options: dict[str, Any] = {}
        saved_options = progress.get("execution_options")
        if saved_options is not None:
            from ..core.action import ActionExecutionPolicy
            from .states import ContextConfig
            try:
                if (not isinstance(saved_options, Mapping)
                        or set(saved_options) != {"auto_approve", "context_config", "action_execution_policy"}
                        or not isinstance(saved_options["auto_approve"], bool)):
                    raise ValueError("invalid execution options")
                policy = dict(saved_options["action_execution_policy"])
                names = policy.get("parallel_tool_names")
                if names is not None:
                    if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
                        raise ValueError("invalid parallel admission restriction")
                    policy["parallel_tool_names"] = frozenset(names)
                if (policy.get("mode") not in {"serial", "parallel"}
                        or not isinstance(policy.get("fail_fast"), bool)
                        or type(policy.get("max_concurrency")) is not int
                        or policy["max_concurrency"] < 1):
                    raise ValueError("invalid execution policy")
                execution_options = {
                    "auto_approve": saved_options["auto_approve"],
                    "context_config": ContextConfig(**dict(saved_options["context_config"])),
                    "action_execution_policy": ActionExecutionPolicy(**policy),
                }
            except (KeyError, TypeError, ValueError):
                raise _session_error(SessionErrorCode.INCOMPATIBLE_CHECKPOINT,
                                     "Persisted execution policy is invalid.", recoverable=False) from None
        engine = engine_type(
            agent=agent,
            budget=budget,
            env=environment.resource if environment is not None else None,
            runtime=runtime,
            **execution_options,
        )
        task = _task_from_progress(progress)
        task_text = task.objective if isinstance(task, Task) else str(task)
        template = agent.init_state(task_text)
        if not isinstance(template, StateSchema):
            raise TypeError("Session runtime requires StateSchema state")
        agent_component = _agent_state(snapshot)
        fork_lineage = _fork_lineage(snapshot)
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
            work_item_id=fork_lineage.work_item_id,
            attempt_id=AttemptIdentity.generate(),
            fork_receipt=(
                store.get_session_fork(fork_lineage.fork_operation_id)
                if fork_lineage.fork_operation_id is not None
                and ATOMIC_SESSION_FORK in store.session_capabilities()
                else None
            ),
        )
        session._parent_run_id = trace.run_id
        session._lifecycle = lifecycle
        engine._token_usage = int(budget_payload.get("token_usage", 0))
        engine._model_requests_consumed = int(
            budget_payload.get("model_requests_consumed", 0)
        )
        engine._model_requests_reserved = int(
            budget_payload.get("model_requests_reserved", 0)
        )
        context = RuntimeSnapshotContext(
            engine=engine,
            state=state,
            task=task,
            lifecycle=SessionLifecycle.RESTORING,
            step_id=int(progress.get("next_step", state.current_step)),
            restoring=True,
            session=session,
            snapshot=snapshot,
            generation=head.generation + 1,
            owner_id=session._agent_id.value,
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
        clear_session_runtime(engine)
        return session

    def _restore_runtime_components(
        self,
        snapshot: SessionSnapshot,
        *,
        state: StateSchema,
        task: str | Task,
        step_id: int,
    ) -> None:
        context = RuntimeSnapshotContext(
            engine=self._engine,
            state=state,
            task=task,
            lifecycle=SessionLifecycle(self._require_head().lifecycle),
            step_id=step_id,
            restoring=True,
            session=self,
            snapshot=snapshot,
            generation=self._require_head().generation,
            owner_id=self._agent_id.value,
        )
        for component_owner in self._runtime.snapshot_components:
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
                component_owner.restore(
                    component.decode(self._runtime.component_registry), context
                )

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

    def _restore_budget(self, snapshot: SessionSnapshot) -> None:
        payload = _component_payload(snapshot, ComponentSlot.BUDGET_CAPABILITY.value)
        self._engine.budget.max_steps = int(payload.get("max_steps", 10))
        self._engine.budget.max_runtime_seconds = payload.get("max_runtime_seconds")
        self._engine.budget.max_tokens = payload.get("max_tokens")
        self._engine.budget.max_model_requests = payload.get("max_model_requests")
        self._engine._token_usage = int(payload.get("token_usage", 0))
        self._engine._model_requests_consumed = int(
            payload.get("model_requests_consumed", 0)
        )
        self._engine._model_requests_reserved = int(
            payload.get("model_requests_reserved", 0)
        )

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
        self._reconcile_handoff(lifecycle)
        generation = 0 if expected_head is None else expected_head.generation + 1
        snapshot_id = SnapshotIdentity.generate()
        checkpoint_id = CheckpointIdentity.generate()
        context = RuntimeSnapshotContext(
            engine=self._engine,
            state=state,
            task=task,
            lifecycle=lifecycle,
            step_id=step_id,
            session=self,
            generation=generation,
            owner_id=self._agent_id.value,
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
            resolver_references=self._snapshot_references(),
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
            self._runtime.publish_event(
                SessionLifecycleEvent(
                    session_id=receipt.session_id,
                    run_id=receipt.owner_run_id,
                    snapshot_id=receipt.snapshot_id,
                    checkpoint_id=receipt.checkpoint_id,
                    generation=receipt.generation,
                    lifecycle=receipt.lifecycle,
                ),
                engine=self._engine,
            )
            # The persisted conversation owns steering. Publish only newly
            # committed dispositions, including queued -> applied transitions.
            prior_steering: dict[str, Any] = {}
            if expected_head is not None:
                old_snapshot = self._load_snapshot(expected_head)
                old_conversation = next((item for item in old_snapshot.components
                                         if item.slot == "conversation"), None)
                if old_conversation is not None:
                    prior_steering = {item["receipt_id"]: item for item in
                                      old_conversation.payload.get("steering_receipts", ())}
            conversation = next((item for item in snapshot.components if item.slot == "conversation"), None)
            if conversation is not None:
                from .states import RuntimePhase
                for steering in conversation.payload.get("steering_receipts", ()):
                    if prior_steering.get(steering["receipt_id"]) != steering:
                        self._engine._emit(step_id, RuntimePhase.DECIDE, payload={
                            "stage": "steering_receipt", "steering_receipt": dict(steering),
                            "snapshot_id": receipt.snapshot_id, "owner_generation": receipt.generation,
                        })
        return self._require_head()

    def _reconcile_handoff(self, lifecycle: SessionLifecycle) -> None:
        """Record destination facts in the same owner-fenced snapshot commit."""
        graph = getattr(self._engine, "_qitos_work_graph", None)
        if not isinstance(graph, WorkGraph):
            return
        work = graph.work_items.get(self._work_item_id)
        if work is None or work.owner.agent_id != self._agent_id:
            return
        transfers = {item.transfer_id: item for item in graph.transfers}
        for index, operation in enumerate(graph.operation_receipts):
            transfer = transfers.get(f"ownership:{operation.operation_id}")
            if (operation.operation != "handoff" or transfer is None
                    or transfer.to_agent_id != self._agent_id
                    or operation.state in {"completed", "failed", "cancelled"}):
                continue
            state = lifecycle.value
            terminal = state in {"completed", "failed", "cancelled"}
            if not terminal:
                state = "running" if state == "running" else "ownership_committed"
            graph.operation_receipts[index] = replace(
                operation, state=state, outcome_unknown=False,
                admission_state="closed" if terminal else "admitted",
                terminal_receipt_ref=(
                    f"session:{self._session_id.value}:{self._run_id.value}:{state}"
                    if terminal else None
                ),
            )

    def _snapshot_references(self) -> tuple[ResolverReference, ...]:
        graph = getattr(self._engine, "_qitos_work_graph", None)
        if isinstance(graph, WorkGraph):
            for operation in reversed(graph.operation_receipts):
                if operation.operation == "handoff" and operation.descriptor is not None:
                    descriptor = WorkDescriptor.from_dict(operation.descriptor)
                    if descriptor.agent_refs:
                        target = ResolverReference.from_dict(descriptor.agent_refs[0])
                        return tuple(target if ref.namespace is ResolverNamespace.AGENT else ref
                                     for ref in self._references)
        return self._references

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
        from ..core.action import ActionExecutionPolicy

        codecs = {codec.slot: codec for codec in CORE_SNAPSHOT_COMPONENT_CODECS}
        graph = getattr(self._engine, "_qitos_work_graph", None)
        work = graph.work_items.get(self._work_item_id) if isinstance(graph, WorkGraph) else None
        agent_state = AgentStateSnapshotComponent(
            agent_id=work.owner.agent_id if work is not None else self._agent_id,
            state_schema=_state_schema_id(type(state)),
            state=state.to_dict(),
        )
        last_runtime_error = getattr(self._engine, "_last_runtime_error", None)
        executor = self._engine.executor
        execution_policy = executor.policy if executor is not None else ActionExecutionPolicy()
        progress = {
            "task": _task_payload(task),
            "next_step": int(step_id),
            "lifecycle": lifecycle.value,
            "engine_config": self._engine.export_config().to_dict(),
            "execution_options": {
                "auto_approve": self._engine.auto_approve,
                "context_config": asdict(self._engine.context_config),
                "action_execution_policy": {
                    "mode": execution_policy.mode,
                    "fail_fast": execution_policy.fail_fast,
                    "max_concurrency": execution_policy.max_concurrency,
                    "parallel_tool_names": (
                        sorted(execution_policy.parallel_tool_names)
                        if execution_policy.parallel_tool_names is not None else None
                    ),
                },
            },
            "runtime_composition": self._runtime.export_config(
                self._snapshot_references()
            ).to_dict(),
            "pause_safety": (
                _json_value(asdict(pause_safety)) if pause_safety is not None else None
            ),
            "terminal_failure": (
                _json_value(dict(last_runtime_error))
                if lifecycle is SessionLifecycle.FAILED
                and isinstance(last_runtime_error, Mapping)
                else None
            ),
        }
        budget = {
            "max_steps": int(self._engine.budget.max_steps),
            "max_runtime_seconds": self._engine.budget.max_runtime_seconds,
            "max_tokens": self._engine.budget.max_tokens,
            "token_usage": int(getattr(self._engine, "_token_usage", 0)),
            "max_model_requests": self._engine.budget.max_model_requests,
            "model_requests_consumed": int(
                getattr(self._engine, "_model_requests_consumed", 0)
            ),
            "model_requests_reserved": int(
                getattr(self._engine, "_model_requests_reserved", 0)
            ),
        }
        trace = TraceLineageSnapshotComponent(
            run_id=self._run_id,
            trace_complete=lifecycle is not SessionLifecycle.RUNNING,
            parent_run_id=self._parent_run_id,
        )
        fork_lineage = ForkLineageSnapshotComponent(
            work_item_id=self._work_item_id,
            attempt_id=self._attempt_id,
            source_session_id=(
                SessionIdentity(self._fork_receipt.source_session_id)
                if self._fork_receipt is not None
                else None
            ),
            source_snapshot_id=(
                SnapshotIdentity(self._fork_receipt.source_snapshot_id)
                if self._fork_receipt is not None
                else None
            ),
            source_checkpoint_id=(
                CheckpointIdentity(self._fork_receipt.source_checkpoint_id)
                if self._fork_receipt is not None
                else None
            ),
            source_work_item_id=(
                WorkItemIdentity(self._fork_receipt.source_work_item_id)
                if self._fork_receipt is not None
                else None
            ),
            fork_operation_id=(
                self._fork_receipt.operation_id
                if self._fork_receipt is not None
                else None
            ),
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
            SnapshotComponent.from_value(
                codecs[ComponentSlot.FORK_LINEAGE.value], fork_lineage
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


def _fork_lineage(
    snapshot: SessionSnapshot, *, required: bool = False
) -> ForkLineageSnapshotComponent:
    component = next(
        (
            item
            for item in snapshot.components
            if item.slot == ComponentSlot.FORK_LINEAGE.value
            and item.owner == "qitos.session"
        ),
        None,
    )
    if component is None:
        if required:
            raise _session_error(
                SessionErrorCode.INCOMPATIBLE_CHECKPOINT,
                "Source snapshot predates explicit work/fork lineage.",
                recoverable=False,
            )
        return ForkLineageSnapshotComponent(
            work_item_id=WorkItemIdentity.generate(),
            attempt_id=AttemptIdentity.generate(),
        )
    from ..core.session import CORE_SNAPSHOT_COMPONENT_REGISTRY

    decoded = component.decode(CORE_SNAPSHOT_COMPONENT_REGISTRY)
    if not isinstance(decoded, ForkLineageSnapshotComponent):
        raise _session_error(
            SessionErrorCode.CORRUPT_SNAPSHOT,
            "Fork lineage component decoded to an incompatible type.",
            recoverable=False,
        )
    return decoded


def _require_fork_safe(snapshot: SessionSnapshot, registry: Any) -> None:
    progress = _component_payload(snapshot, ComponentSlot.ENGINE_PROGRESS.value)
    if snapshot.lifecycle in {
        SessionLifecycle.RUNNING,
        SessionLifecycle.PAUSED,
        SessionLifecycle.WAITING_INPUT,
    }:
        safety = progress.get("pause_safety")
        safe = (
            isinstance(safety, Mapping)
            and safety.get("boundary") != "in_flight_operation"
            and safety.get("completed_slots_recorded") is True
            and safety.get("open_slots_recorded") is True
            and safety.get("framework_workers_quiesced") is True
            and safety.get("unresolved_effect_count") == 0
        )
        if not safe:
            raise _session_error(
                SessionErrorCode.UNSAFE_PAUSE_BOUNDARY,
                "Only a recorded migratable snapshot can be forked.",
                recoverable=True,
            )
    batch_component = next(
        (
            item
            for item in snapshot.components
            if item.slot == ComponentSlot.PARTIAL_PARALLEL_BATCH.value
        ),
        None,
    )
    if batch_component is None:
        return
    batch = batch_component.decode(registry)
    if not isinstance(batch, ToolBatchSnapshot):
        return
    unresolved = any(
        bool(slot.lifecycle and not slot.lifecycle.migratable)
        or bool(slot.effect and slot.effect.outcome_unknown)
        for slot in batch.slots
    )
    if unresolved:
        raise _session_error(
            SessionErrorCode.UNRESOLVED_EFFECT,
            "Snapshot contains an unresolved worker or external effect.",
            recoverable=True,
        )


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
    if reason == "interrupt":
        return SessionLifecycle.WAITING_INPUT
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
        CheckpointSessionErrorCode.SNAPSHOT_NOT_FOUND: SessionErrorCode.SNAPSHOT_NOT_FOUND,
        CheckpointSessionErrorCode.SNAPSHOT_SESSION_MISMATCH: SessionErrorCode.SNAPSHOT_SESSION_MISMATCH,
        CheckpointSessionErrorCode.DUPLICATE_FORK_OPERATION: SessionErrorCode.DUPLICATE_FORK_OPERATION,
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


def _stable_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _agent_reference(name: str) -> ResolverReference:
    logical = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", name.strip()).strip("-:") or "agent"
    return ResolverReference(
        ResolverNamespace.AGENT,
        f"agent:{logical[:112]}",
        AGENT_CAPABILITY,
    )


def _resolver_available(runtime: RuntimeComposition, reference: ResolverReference) -> bool:
    try:
        runtime.resolvers.resolve(reference)
    except SessionContractError:
        return False
    return True


def _allocation_payload(value: BudgetAllocation | CapabilityAllocation) -> dict[str, Any]:
    if isinstance(value, BudgetAllocation):
        return {
            "allocation_id": value.allocation_id,
            "parent_work_item_id": value.parent_work_item_id.to_dict(),
            "child_work_item_id": value.child_work_item_id.to_dict(),
            "limits": dict(value.limits),
            "reclaim_policy": value.reclaim_policy,
        }
    return {
        "allocation_id": value.allocation_id,
        "parent_work_item_id": value.parent_work_item_id.to_dict(),
        "child_work_item_id": value.child_work_item_id.to_dict(),
        "capabilities": list(value.capabilities),
    }


def _budget_allocation(payload: Mapping[str, Any]) -> BudgetAllocation:
    return BudgetAllocation(
        allocation_id=str(payload["allocation_id"]),
        parent_work_item_id=WorkItemIdentity.from_dict(payload["parent_work_item_id"]),
        child_work_item_id=WorkItemIdentity.from_dict(payload["child_work_item_id"]),
        limits=dict(payload["limits"]),
        reclaim_policy=payload.get("reclaim_policy", "return_unused"),
    )


def _capability_allocation(payload: Mapping[str, Any]) -> CapabilityAllocation:
    return CapabilityAllocation(
        allocation_id=str(payload["allocation_id"]),
        parent_work_item_id=WorkItemIdentity.from_dict(payload["parent_work_item_id"]),
        child_work_item_id=WorkItemIdentity.from_dict(payload["child_work_item_id"]),
        capabilities=list(payload["capabilities"]),
    )


def _work_lifecycle(lifecycle: SessionLifecycle) -> WorkLifecycle:
    if lifecycle in {SessionLifecycle.CREATED, SessionLifecycle.RESTORING}:
        return "created"
    if lifecycle in {
        SessionLifecycle.RUNNING,
        SessionLifecycle.PAUSE_REQUESTED,
        SessionLifecycle.PAUSING,
    }:
        return "running"
    if lifecycle is SessionLifecycle.WAITING_INPUT:
        return "waiting_input"
    if lifecycle is SessionLifecycle.PAUSED:
        return "paused"
    if lifecycle is SessionLifecycle.COMPLETED:
        return "completed"
    if lifecycle is SessionLifecycle.CANCELLED:
        return "cancelled"
    return "failed"


def _graph_depth(graph: WorkGraph, work_item_id: WorkItemIdentity) -> int:
    depth = 0
    current = graph.work_items.get(work_item_id)
    while current is not None and current.parent_work_item_id is not None:
        depth += 1
        current = graph.work_items.get(current.parent_work_item_id)
    return depth


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_schema_id(state_type: type[Any]) -> str:
    raw = f"python.{state_type.__module__}.{state_type.__qualname__}".lower()
    return re.sub(r"[^a-z0-9_.:-]+", "-", raw)[:95]


__all__ = ["Session", "SessionInspection", "restore_session"]
