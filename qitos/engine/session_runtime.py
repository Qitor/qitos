"""Durable Session facade delegating execution to the canonical Engine loop."""

from __future__ import annotations

import threading
import hashlib
import json
import time
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
        with self._lock:
            head = self._require_head()
            snapshot = self._load_snapshot(head)
            state = self._engine.current_state
            task: str | Task = self._engine._active_task_obj or self._engine._active_task
            if state is None:
                state, task, step_id = self._restore_core_state(snapshot)
            else:
                step_id = int(getattr(state, "current_step", 0))
            return self._submit_steering(
                text,
                state=state,
                task=task,
                step_id=step_id,
            )

    def submit_work(
        self,
        operation: str,
        payload: Mapping[str, Any],
        *,
        operation_id: str | None = None,
    ) -> Any:
        """Submit one durable logical operation through the composed scheduler."""
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
            descriptor = self._prepare_work_descriptor(
                graph=graph,
                operation=operation,
                operation_id=operation_id,
                payload=canonical,
            )
            return runtime.submit(
                graph=graph,
                descriptor=descriptor,
                persist=self._commit_work_graph,
                generation=self.current_head.generation.value,
            )
        except Exception:
            durable_declaration = any(
                item.operation_id == operation_id for item in graph.operation_receipts
            )
            if not durable_declaration:
                restored = WorkGraph.from_canonical_dict(before)
                setattr(self._engine, "_qitos_work_graph", restored)
            raise

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
        if existing is not None and existing.descriptor is not None:
            return WorkDescriptor.from_dict(existing.descriptor)
        if operation not in {"handoff", "delegate", "spawn", "fan_out", "join"}:
            raise ValueError(f"unsupported durable operation {operation!r}")
        head = self._require_head()
        if self._work_item_id not in graph.work_items:
            lifecycle = _work_lifecycle(SessionLifecycle(head.lifecycle))
            graph.add_work_item(
                WorkItem(
                    work_item_id=self._work_item_id,
                    session_ref=self._session_id,
                    task_ref=f"task:{_stable_digest(str(self._engine._active_task))[:24]}",
                    lifecycle=lifecycle,
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
                self.fork(
                    operation_id=f"fork_{_stable_digest(f'{operation_id}:{index}')[:32]}"
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
        for index, child in enumerate(child_sessions):
            spec = specs[index]
            agent_name = str(spec.get("agent") or getattr(self._engine.agent, "name", "agent"))
            agent_ref = _agent_reference(agent_name)
            destination_resolved = _resolver_available(self._runtime, agent_ref)
            target_agent_id = self._agent_id if destination_resolved else AgentIdentity.generate()
            budget = BudgetAllocation(
                allocation_id=f"budget:{operation_id}:{index}",
                parent_work_item_id=self._work_item_id,
                child_work_item_id=child.work_item_id,
                limits=dict(spec.get("budget") or {}),
            )
            capabilities = CapabilityAllocation(
                allocation_id=f"capability:{operation_id}:{index}",
                parent_work_item_id=self._work_item_id,
                child_work_item_id=child.work_item_id,
                capabilities=list(spec.get("capabilities") or []),
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
        log = getattr(self._engine, "_qitos_exchange_log", None)
        if not isinstance(log, ExchangeLog):
            log = ExchangeLog(log_id=f"transfer_log:{self._session_id.value}")
        conversation = ConversationSnapshotComponent.from_exchange_log(log)
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
            self._commit_snapshot(
                state=state,
                task=task,
                lifecycle=lifecycle,
                step_id=step_id,
                expected_head=head,
                pause_safety=pause_safety,
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
            state, task, next_step = self._restore_core_state(snapshot)
            self._restore_runtime_components(
                snapshot, state=state, task=task, step_id=next_step
            )
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
            self._engine._active_state = state
            self._engine._active_task_obj = task if isinstance(task, Task) else None
            self._engine._active_task = (
                task.objective if isinstance(task, Task) else str(task)
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
            self._engine._qitos_tool_batch_snapshot = None
            self._commit_snapshot(
                state=result.state,
                task=task,
                lifecycle=terminal,
                step_id=int(getattr(result.state, "current_step", next_step)),
                expected_head=current,
            )
            return result

    def fork(
        self,
        snapshot: SessionSnapshot | SnapshotIdentity | str | None = None,
        *,
        operation_id: Optional[str] = None,
    ) -> "Session":
        """Create an isolated durable child from one verified immutable snapshot."""
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
        if not lifecycle_allows(source.lifecycle, SessionOperation.FORK):
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
