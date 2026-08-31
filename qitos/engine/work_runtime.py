"""Replaceable durable WorkGraph scheduling seam.

Schedulers own process-local workers. The runtime persists only logical
operation receipts in the canonical WorkGraph captured by Session snapshots.
"""

from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

from ..core.work_graph import WorkGraph, WorkGraphContractError, WorkOperationReceipt


class WorkRuntimeError(RuntimeError):
    """Typed scheduler/admission/idempotency failure."""

    def __init__(self, code: str, message: str, *, operation_id: str = "") -> None:
        self.code = str(code)
        self.operation_id = str(operation_id)
        super().__init__(f"{self.code}: {message}")


@dataclass(frozen=True)
class WorkRuntimePolicy:
    maximum_children_per_operation: int = 64
    maximum_graph_depth: int = 32
    maximum_concurrent_children: int = 4
    queue_capacity: int = 64
    admission_behavior: str = "reject"
    timeout_seconds: float | None = 120.0
    cancellation_propagation: str = "request_and_wait"
    supervisor_policy: str = "parent_until_detached"
    retention_policy: str = "retain_terminal_receipt"
    budget_ceiling: Mapping[str, int] | None = None
    capability_ceiling: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for name in (
            "maximum_children_per_operation",
            "maximum_graph_depth",
            "maximum_concurrent_children",
            "queue_capacity",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.admission_behavior not in {"reject", "queue"}:
            raise ValueError("admission_behavior must be reject or queue")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


@dataclass(frozen=True)
class WorkDispatch:
    operation_id: str
    payload_digest: str
    attempt: int
    generation: int


@runtime_checkable
class SchedulerHandle(Protocol):
    worker_ref: str

    def add_terminal_callback(
        self, callback: Callable[[Any, BaseException | None], None]
    ) -> None:
        ...

    def request_cancel(self) -> bool:
        ...


@runtime_checkable
class WorkScheduler(Protocol):
    scheduler_id: str

    def dispatch(
        self, request: WorkDispatch, worker: Callable[[], Any]
    ) -> SchedulerHandle:
        ...

    def reattach(
        self, request: WorkDispatch, worker_ref: str
    ) -> SchedulerHandle | None:
        ...

    def close(self) -> None:
        ...


class _LocalHandle:
    def __init__(self, worker_ref: str, future: Future[Any]) -> None:
        self.worker_ref = worker_ref
        self._future = future

    def add_terminal_callback(
        self, callback: Callable[[Any, BaseException | None], None]
    ) -> None:
        def done(future: Future[Any]) -> None:
            try:
                callback(future.result(), None)
            except BaseException as exc:  # terminal fact, never escapes worker thread
                callback(None, exc)

        self._future.add_done_callback(done)

    def request_cancel(self) -> bool:
        # False means the worker may still be running; it is never a hard-stop claim.
        return bool(self._future.cancel())


class LocalWorkScheduler:
    """Bounded local reference scheduler; futures are never persisted."""

    scheduler_id = "qitos.scheduler.local"

    def __init__(self, *, max_workers: int = 4, queue_capacity: int = 64) -> None:
        if max_workers < 1 or queue_capacity < 1:
            raise ValueError("scheduler bounds must be positive")
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._capacity = threading.BoundedSemaphore(max_workers + queue_capacity)
        self._lock = threading.Lock()
        self._handles: dict[str, _LocalHandle] = {}
        self._closed = False

    def dispatch(self, request: WorkDispatch, worker: Callable[[], Any]) -> SchedulerHandle:
        with self._lock:
            if self._closed:
                raise WorkRuntimeError("scheduler_unavailable", "scheduler is closed", operation_id=request.operation_id)
        if not self._capacity.acquire(blocking=False):
            raise WorkRuntimeError("queue_capacity_exceeded", "scheduler admission capacity is full", operation_id=request.operation_id)

        def run() -> Any:
            try:
                return worker()
            finally:
                self._capacity.release()

        future = self._executor.submit(run)
        handle = _LocalHandle(
            f"{self.scheduler_id}:{request.operation_id}:{request.attempt}", future
        )
        with self._lock:
            self._handles[handle.worker_ref] = handle
        return handle

    def reattach(self, request: WorkDispatch, worker_ref: str) -> SchedulerHandle | None:
        with self._lock:
            return self._handles.get(worker_ref)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown(wait=True, cancel_futures=False)


class DurableWorkRuntime:
    """Idempotent declaration/dispatch protocol over one canonical WorkGraph."""

    capability_id = "work.scheduler.durable"

    def __init__(
        self,
        scheduler: WorkScheduler,
        *,
        policy: WorkRuntimePolicy | None = None,
        child_runner: Callable[[str, Mapping[str, Any]], Any] | None = None,
    ) -> None:
        if not isinstance(scheduler, WorkScheduler):
            raise TypeError("scheduler must implement WorkScheduler")
        self.scheduler = scheduler
        self.policy = policy or WorkRuntimePolicy()
        self.child_runner = child_runner
        self._lock = threading.RLock()
        self._handles: dict[str, SchedulerHandle] = {}

    def run_child(self, operation: str, payload: Mapping[str, Any]) -> Any:
        if self.child_runner is None:
            raise WorkRuntimeError(
                "child_runner_unavailable",
                "the composed runtime has no logical child runner",
            )
        return self.child_runner(operation, payload)

    def submit(
        self,
        *,
        graph: WorkGraph,
        operation_id: str,
        operation: str,
        payload: Mapping[str, Any],
        worker: Callable[[], Any],
        persist: Callable[[], None],
        generation: int = 0,
    ) -> WorkOperationReceipt:
        digest = _payload_digest(payload)
        with self._lock:
            existing = _operation(graph, operation_id)
            if existing is not None:
                if existing.payload_digest != digest or existing.operation != operation:
                    raise WorkRuntimeError(
                        "operation_identity_conflict",
                        "operation identity was reused with a different payload",
                        operation_id=operation_id,
                    )
                return existing
            receipt = WorkOperationReceipt(
                operation_id=operation_id,
                operation=operation,
                payload_digest=digest,
                state="declared",
                generation=generation,
            )
            graph.operation_receipts.append(receipt)
            try:
                persist()
            except Exception:
                graph.operation_receipts.pop()
                raise

            request = WorkDispatch(operation_id, digest, 1, generation)
            try:
                handle = self.scheduler.dispatch(request, worker)
            except WorkRuntimeError:
                # The durable declaration remains eligible for later dispatch.
                self._replace(graph, replace(receipt, state="queued"))
                persist()
                raise
            dispatched = replace(
                receipt,
                state="dispatched",
                attempt=1,
                worker_ref=handle.worker_ref,
            )
            self._replace(graph, dispatched)
            try:
                persist()
            except Exception as exc:
                unknown = replace(dispatched, state="outcome_unknown", outcome_unknown=True)
                self._replace(graph, unknown)
                try:
                    persist()
                except Exception:
                    pass
                raise WorkRuntimeError(
                    "store_commit_failed_after_dispatch",
                    "dispatch began but its receipt could not be committed",
                    operation_id=operation_id,
                ) from exc
            self._handles[operation_id] = handle
            handle.add_terminal_callback(
                lambda result, error: self._terminal(
                    graph, dispatched, result, error, persist
                )
            )
            return dispatched

    def recover(
        self,
        graph: WorkGraph,
        *,
        persist: Callable[[], None],
    ) -> tuple[WorkOperationReceipt, ...]:
        recovered: list[WorkOperationReceipt] = []
        with self._lock:
            original = list(graph.operation_receipts)
            for receipt in tuple(graph.operation_receipts):
                if receipt.state not in {"dispatched", "running"}:
                    continue
                request = WorkDispatch(
                    receipt.operation_id,
                    receipt.payload_digest,
                    receipt.attempt,
                    receipt.generation,
                )
                handle = (
                    self.scheduler.reattach(request, receipt.worker_ref)
                    if receipt.worker_ref is not None
                    else None
                )
                if handle is None:
                    unknown = replace(receipt, state="outcome_unknown", outcome_unknown=True)
                    self._replace(graph, unknown)
                    recovered.append(unknown)
            if recovered:
                try:
                    persist()
                except Exception:
                    graph.operation_receipts[:] = original
                    raise
        return tuple(recovered)

    def request_cancel(
        self,
        graph: WorkGraph,
        operation_id: str,
        *,
        persist: Callable[[], None],
    ) -> WorkOperationReceipt:
        with self._lock:
            receipt = _operation(graph, operation_id)
            if receipt is None:
                raise WorkRuntimeError("operation_not_found", "operation identity is unknown", operation_id=operation_id)
            handle = self._handles.get(operation_id)
            stopped = handle.request_cancel() if handle is not None else False
            state = "cancelled" if stopped else "cancellation_requested_worker_still_running"
            updated = replace(receipt, state=state, outcome_unknown=not stopped)
            self._replace(graph, updated)
            try:
                persist()
            except Exception:
                self._replace(graph, receipt)
                raise
            return updated

    def close(self) -> None:
        self.scheduler.close()

    def _terminal(
        self,
        graph: WorkGraph,
        receipt: WorkOperationReceipt,
        result: Any,
        error: BaseException | None,
        persist: Callable[[], None],
    ) -> None:
        del result  # Result ownership stays with canonical child Task/ToolResult storage.
        with self._lock:
            current = _operation(graph, receipt.operation_id)
            if current is None or current.state.startswith("cancel"):
                return
            terminal = replace(
                current,
                state="failed" if error is not None else "completed",
                terminal_receipt_ref=f"terminal:{current.operation_id}:{current.attempt}",
            )
            self._replace(graph, terminal)
            try:
                persist()
            except Exception:
                self._replace(graph, current)
                raise

    @staticmethod
    def _replace(graph: WorkGraph, receipt: WorkOperationReceipt) -> None:
        for index, current in enumerate(graph.operation_receipts):
            if current.operation_id == receipt.operation_id:
                graph.operation_receipts[index] = receipt
                return
        raise WorkGraphContractError("missing_operation", "operation receipt is absent")


def _operation(graph: WorkGraph, operation_id: str) -> WorkOperationReceipt | None:
    return next(
        (item for item in graph.operation_receipts if item.operation_id == operation_id),
        None,
    )


def _payload_digest(payload: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise WorkRuntimeError("invalid_operation_payload", "payload must be strict JSON") from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


__all__ = [
    "DurableWorkRuntime",
    "LocalWorkScheduler",
    "SchedulerHandle",
    "WorkDispatch",
    "WorkRuntimeError",
    "WorkRuntimePolicy",
    "WorkScheduler",
]
