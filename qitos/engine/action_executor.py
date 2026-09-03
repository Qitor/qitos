"""Action executor for QitOS."""

from __future__ import annotations

import asyncio
import inspect
import threading
import time
from concurrent.futures import (
    FIRST_COMPLETED,
    ThreadPoolExecutor,
    TimeoutError as FuturesTimeoutError,
    wait,
)
from typing import Any, Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING, cast

from ..core.action import Action, ActionExecutionPolicy, ActionResult, ActionStatus
from ..core.env import Env
from ..core.interceptor import InterceptorChain, InterceptorContext
from ..core.state import StateSchema
from ..core.tool_result import ToolResult, ToolResultContractError
from ..core.tool_runtime import (
    PartialBatchCallback,
    TerminalResultCallback,
    ToolBatchExecution,
    ToolBatchSnapshot,
    ToolEffectPolicy,
    ToolTerminalReceipt,
)
from ..core.tool import (
    BaseTool,
    ToolPermissionContext,
    ToolPermissionDecision,
    ToolValidationResult,
)
from .states import RuntimePhase
from .tool_runtime import (
    ReferenceEffectPolicy,
    ToolBatchLedger,
    apply_effect_receipt,
    lifecycle_receipt_for,
    lifecycle_spec_for,
)

if TYPE_CHECKING:
    from ._protocol import _EngineProtocol
    from .cancellation import CancelToken


class _ConcurrencyTracker:
    """Thread-safe peak-concurrency counter for a single execute() batch."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self.peak = 0

    def enter(self) -> None:
        with self._lock:
            self._active += 1
            if self._active > self.peak:
                self.peak = self._active

    def exit(self) -> None:
        with self._lock:
            self._active -= 1


class ToolWorkerTimeout(TimeoutError):
    """Deadline observation with an honest underlying-worker capability fact."""

    def __init__(
        self,
        message: str,
        *,
        worker_still_running: bool,
        outcome_unknown: bool = False,
    ):
        super().__init__(message)
        self.worker_still_running = bool(worker_still_running)
        self.outcome_unknown = bool(outcome_unknown)


class ToolBatchRecoveryError(RuntimeError):
    """Typed refusal to replay a slot without sufficient safety facts."""

    def __init__(self, code: str, batch_id: str, slot_id: str) -> None:
        self.code = code
        self.batch_id = batch_id
        self.slot_id = slot_id
        super().__init__(f"{code}: batch={batch_id} slot={slot_id}")


class ActionExecutor:
    """Executes normalized actions against a tool registry."""

    def __init__(
        self,
        tool_registry: Any,
        policy: Optional[ActionExecutionPolicy] = None,
        trace_writer: Any = None,
        delegate_depth: int = 0,
        shared_memory: Any = None,
        engine: Optional[_EngineProtocol] = None,
        permission_pipeline: Any = None,
        read_before_write_enforcer: Any = None,
        permission_interaction_callback: Optional[Any] = None,
        interceptor_chain: Optional[InterceptorChain] = None,
        auto_approve: bool = False,
        cancel_token: Optional[CancelToken] = None,
        effect_policy: Optional[ToolEffectPolicy] = None,
        quiescence_barrier: Any = None,
    ):
        self.tool_registry = tool_registry
        self.policy = policy or ActionExecutionPolicy()
        self.trace_writer = trace_writer
        self.delegate_depth = delegate_depth
        self.shared_memory = shared_memory
        self._engine = engine
        self._pipeline = permission_pipeline
        self._rbw_enforcer = read_before_write_enforcer
        self._permission_interaction_callback = permission_interaction_callback
        self._interceptor_chain = interceptor_chain
        self.auto_approve = auto_approve
        self._cancel_token = cancel_token
        self._effect_policy = effect_policy or ReferenceEffectPolicy()
        if quiescence_barrier is None:
            from .cancellation import QuiescenceBarrier

            quiescence_barrier = QuiescenceBarrier()
        self._quiescence_barrier = quiescence_barrier
        self._pause_requested = threading.Event()
        self._stats_lock = threading.Lock()
        # Populated by execute(); consumed by the trace layer.
        self.last_execution_stats: Dict[str, Any] = {}

    # ── Cancellation ───────────────────────────────────────────────────────────

    def _resolve_cancel_token(self) -> Optional[CancelToken]:
        """Prefer an explicit token, else fall back to the owning Engine's."""
        if self._cancel_token is not None:
            return self._cancel_token
        if self._engine is not None:
            return getattr(self._engine, "_cancel_token", None)
        return None

    def _is_cancelled(self) -> bool:
        token = self._resolve_cancel_token()
        if token is None:
            return False
        return bool(getattr(token, "is_cancel_requested", False))

    def execute(
        self, actions: Sequence[Action], env: Optional[Env] = None, state: Any = None
    ) -> List[ActionResult]:
        """Compatibility projection over the canonical batch execution seam."""
        if not actions:
            self._reset_execution_stats()
            return []
        execution = self.execute_batch(actions, env=env, state=state)
        return [
            ActionResult.from_tool_result(result)
            for result in execution.results_in_declaration_order
        ]

    def execute_one(
        self,
        action: Action,
        *,
        terminal_callback: Optional[TerminalResultCallback] = None,
        env: Optional[Env] = None,
        state: Any = None,
        batch_id: Optional[str] = None,
        owner_generation: int = 0,
    ) -> ToolResult:
        """Execute one action through the same canonical batch boundary."""
        execution = self.execute_batch(
            [action],
            terminal_callback=terminal_callback,
            env=env,
            state=state,
            batch_id=batch_id,
            owner_generation=owner_generation,
        )
        return execution.results_in_declaration_order[0]

    def execute_batch(
        self,
        actions: Sequence[Action],
        *,
        terminal_callback: Optional[TerminalResultCallback] = None,
        partial_batch_callback: Optional[PartialBatchCallback] = None,
        env: Optional[Env] = None,
        state: Any = None,
        batch_id: Optional[str] = None,
        owner_generation: int = 0,
    ) -> ToolBatchExecution:
        """Execute a bounded batch and publish every terminal slot immediately."""
        if not actions:
            raise ValueError("execute_batch() requires at least one action")
        self._pause_requested.clear()
        self._reset_execution_stats()
        ledger = ToolBatchLedger(
            actions, batch_id=batch_id, owner_generation=owner_generation
        )
        self._publish_partial(ledger.snapshot(), partial_batch_callback)
        tracker = _ConcurrencyTracker()
        receipts: Dict[str, ToolTerminalReceipt] = {}

        if self._is_cancelled():
            self.last_execution_stats["cancel_source"] = "cancel_token"
            for index, action in enumerate(actions):
                receipt = self._execute_canonical_slot(
                    action,
                    index=index,
                    ledger=ledger,
                    env=env,
                    state=state,
                    tracker=tracker,
                    segment_index=0,
                    terminal_callback=terminal_callback,
                    partial_batch_callback=partial_batch_callback,
                    prevented_status=ActionStatus.CANCELLED,
                    prevented_reason="cancel_token",
                )
                receipts[receipt.slot.slot_id] = receipt
            return self._finish_batch(ledger, receipts, tracker, segments=1)

        segments = (
            [[index] for index in range(len(actions))]
            if getattr(self.policy, "mode", "serial") == "serial"
            else self._segment_actions(actions)
        )
        aborted: Optional[str] = None
        for segment_index, segment in enumerate(segments):
            if aborted is None and self._is_cancelled():
                aborted = "cancel_token"
            if aborted is None and self._pause_requested.is_set():
                aborted = "pause_requested"
            if aborted is not None:
                if aborted == "pause_requested":
                    continue
                for index in segment:
                    receipt = self._execute_canonical_slot(
                        actions[index],
                        index=index,
                        ledger=ledger,
                        env=env,
                        state=state,
                        tracker=tracker,
                        segment_index=segment_index,
                        terminal_callback=terminal_callback,
                        partial_batch_callback=partial_batch_callback,
                        prevented_status=ActionStatus.CANCELLED,
                        prevented_reason=aborted,
                    )
                    receipts[receipt.slot.slot_id] = receipt
                continue

            if len(segment) == 1:
                index = segment[0]
                receipt = self._execute_canonical_slot(
                    actions[index],
                    index=index,
                    ledger=ledger,
                    env=env,
                    state=state,
                    tracker=tracker,
                    segment_index=segment_index,
                    terminal_callback=terminal_callback,
                    partial_batch_callback=partial_batch_callback,
                )
                receipts[receipt.slot.slot_id] = receipt
                if self._should_fail_fast(receipt.result):
                    aborted = "fail_fast"
                continue

            max_workers = min(
                max(1, int(getattr(self.policy, "max_concurrency", 1))),
                len(segment),
            )
            pool = ThreadPoolExecutor(max_workers=max_workers)
            futures: Dict[Any, int] = {}
            try:
                def _parallel_slot(index: int) -> Optional[ToolTerminalReceipt]:
                    if self._pause_requested.is_set():
                        return None
                    return self._execute_canonical_slot(
                        actions[index],
                        index=index,
                        ledger=ledger,
                        env=env,
                        state=state,
                        tracker=tracker,
                        segment_index=segment_index,
                        terminal_callback=terminal_callback,
                        partial_batch_callback=partial_batch_callback,
                    )

                for index in segment:
                    future = pool.submit(_parallel_slot, index)
                    futures[future] = index
                pending = set(futures)
                while pending:
                    done, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        index = futures[future]
                        try:
                            parallel_receipt = future.result()
                        except Exception as exc:  # pragma: no cover - defensive
                            parallel_receipt = self._execute_canonical_slot(
                                actions[index],
                                index=index,
                                ledger=ledger,
                                env=env,
                                state=state,
                                tracker=tracker,
                                segment_index=segment_index,
                                terminal_callback=terminal_callback,
                                partial_batch_callback=partial_batch_callback,
                                prevented_status=ActionStatus.ERROR,
                                prevented_reason=f"missing_worker:{type(exc).__name__}",
                            )
                        if parallel_receipt is None:
                            continue
                        receipt = parallel_receipt
                        receipts[receipt.slot.slot_id] = receipt
                        if aborted is None and self._should_fail_fast(receipt.result):
                            aborted = "fail_fast"
                    if aborted is None and self._is_cancelled():
                        aborted = "cancel_token"
                    if aborted is None and self._pause_requested.is_set():
                        aborted = "pause_requested"
                    if aborted is not None and pending:
                        still_running = set()
                        for future in pending:
                            if future.cancel():
                                if aborted == "pause_requested":
                                    continue
                                index = futures[future]
                                receipt = self._execute_canonical_slot(
                                    actions[index],
                                    index=index,
                                    ledger=ledger,
                                    env=env,
                                    state=state,
                                    tracker=tracker,
                                    segment_index=segment_index,
                                    terminal_callback=terminal_callback,
                                    partial_batch_callback=partial_batch_callback,
                                    prevented_status=ActionStatus.CANCELLED,
                                    prevented_reason=aborted,
                                )
                                receipts[receipt.slot.slot_id] = receipt
                            else:
                                still_running.add(future)
                        pending = still_running
            finally:
                pool.shutdown(wait=True)

        if aborted is not None:
            self.last_execution_stats["cancel_source"] = aborted
        final_snapshot = ledger.snapshot()
        missing_slots = (
            ()
            if aborted == "pause_requested"
            else final_snapshot.missing_slots
        )
        for slot in missing_slots:
            receipt = self._execute_canonical_slot(
                actions[slot.declaration_index],
                index=slot.declaration_index,
                ledger=ledger,
                env=env,
                state=state,
                tracker=tracker,
                segment_index=len(segments),
                terminal_callback=terminal_callback,
                partial_batch_callback=partial_batch_callback,
                prevented_status=ActionStatus.ERROR,
                prevented_reason="missing_worker",
            )
            receipts[receipt.slot.slot_id] = receipt
        return self._finish_batch(
            ledger, receipts, tracker, segments=len(segments)
        )

    def resume_batch(
        self,
        snapshot: ToolBatchSnapshot,
        *,
        terminal_callback: Optional[TerminalResultCallback] = None,
        partial_batch_callback: Optional[PartialBatchCallback] = None,
        env: Optional[Env] = None,
        state: Any = None,
    ) -> ToolBatchExecution:
        """Execute only safe missing slots under the original batch identities."""
        for slot in snapshot.slots:
            result = slot.result
            if result is not None and (
                result.outcome_unknown or result.reconciliation_required
            ):
                raise ToolBatchRecoveryError(
                    "reconciliation_required", snapshot.batch_id, slot.slot_id
                )
        if snapshot.closed:
            return ToolBatchExecution(snapshot=snapshot, terminal_receipts=())

        ledger = ToolBatchLedger.from_snapshot(snapshot)
        actions = {
            slot.declaration_index: Action.from_dict(dict(slot.action_payload))
            for slot in snapshot.slots
        }
        self._reset_execution_stats()
        self._publish_partial(snapshot, partial_batch_callback)
        tracker = _ConcurrencyTracker()
        receipts: Dict[str, ToolTerminalReceipt] = {}
        for slot in snapshot.missing_slots:
            action = actions[slot.declaration_index]
            if not action.idempotent:
                raise ToolBatchRecoveryError(
                    "missing_slot_not_safe_to_retry",
                    snapshot.batch_id,
                    slot.slot_id,
                )
            receipt = self._execute_canonical_slot(
                action,
                index=slot.declaration_index,
                ledger=ledger,
                env=env,
                state=state,
                tracker=tracker,
                segment_index=0,
                terminal_callback=terminal_callback,
                partial_batch_callback=partial_batch_callback,
            )
            receipts[receipt.slot.slot_id] = receipt
        return self._finish_batch(ledger, receipts, tracker, segments=1)

    def _reset_execution_stats(self) -> None:
        self.last_execution_stats = {
            "policy": {
                "mode": getattr(self.policy, "mode", "serial"),
                "fail_fast": bool(getattr(self.policy, "fail_fast", False)),
                "max_concurrency": int(
                    getattr(self.policy, "max_concurrency", 1)
                ),
            },
            "concurrency_peak": 0,
            "segments": 0,
            "cancel_source": None,
            "callback_errors": [],
            "late_completions": [],
        }

    def _finish_batch(
        self,
        ledger: ToolBatchLedger,
        receipts: Dict[str, ToolTerminalReceipt],
        tracker: _ConcurrencyTracker,
        *,
        segments: int,
    ) -> ToolBatchExecution:
        snapshot = ledger.snapshot()
        self.last_execution_stats["concurrency_peak"] = tracker.peak
        self.last_execution_stats["segments"] = segments
        ordered_receipts = tuple(
            receipts[slot_id]
            for slot_id in snapshot.completion_order
            if slot_id in receipts
        )
        return ToolBatchExecution(snapshot=snapshot, terminal_receipts=ordered_receipts)

    def _should_fail_fast(self, result: ToolResult) -> bool:
        return bool(
            getattr(self.policy, "fail_fast", False)
            and result.status in {"error", "timed_out"}
        )

    def _execute_canonical_slot(
        self,
        action: Action,
        *,
        index: int,
        ledger: ToolBatchLedger,
        env: Optional[Env],
        state: Any,
        tracker: _ConcurrencyTracker,
        segment_index: int,
        terminal_callback: Optional[TerminalResultCallback],
        partial_batch_callback: Optional[PartialBatchCallback],
        prevented_status: Optional[ActionStatus] = None,
        prevented_reason: str = "",
    ) -> ToolTerminalReceipt:
        slot = ledger.slot_for_index(index)
        tool = self._resolve_tool(action.name)
        lifecycle_spec = lifecycle_spec_for(tool)
        facts = {
            "batch_id": ledger.batch_id,
            "slot_id": slot.slot_id,
            "attempt_id": slot.attempt_id,
            "owner_generation": ledger.owner_generation,
            "lifecycle": lifecycle_spec,
        }
        try:
            runtime_context = self._build_runtime_context(
                action.name, env=env, state=state, runtime_facts=facts
            )
            declaration = self._effect_policy.declare(
                action, tool, runtime_context
            )
        except Exception as exc:
            runtime_context = dict(facts)
            declaration = None
            prevented_status = ActionStatus.ERROR
            prevented_reason = f"runtime_context_error:{type(exc).__name__}"
        runtime_context.update(
            {
                "effect_ref": declaration.effect_ref if declaration else None,
                "idempotency_key": (
                    declaration.idempotency_key if declaration else None
                ),
                "effect_state": "not_started" if declaration else "no_effect_declared",
            }
        )
        adapter = getattr(getattr(tool, "spec", None), "lifecycle_adapter", None)
        cancel_callback = None
        if adapter is not None:
            def _request_adapter_cancel() -> bool:
                return bool(adapter.request_cancel(slot.attempt_id))

            cancel_callback = _request_adapter_cancel
        self._quiescence_barrier.register(
            slot.attempt_id,
            lifecycle_spec,
            owner_generation=ledger.owner_generation,
            cancel_callback=cancel_callback,
        )

        if prevented_status is None:
            def _late_callback() -> None:
                self._late_worker_completed(
                    slot.attempt_id,
                    owner_generation=ledger.owner_generation,
                    outcome_unknown=declaration is not None,
                )

            action_result = self._execute_one(
                action,
                env=env,
                state=state,
                tracker=tracker,
                segment_index=segment_index,
                runtime_context=runtime_context,
                effect_declared=declaration is not None,
                late_worker_callback=_late_callback,
            )
        elif prevented_status is ActionStatus.ERROR:
            action_result = self._error_result(action, prevented_reason)
            action_result.metadata.update(
                {
                    "segment_index": segment_index,
                    "started": False,
                    "executed": False,
                }
            )
        else:
            action_result = self._terminal_result(
                action,
                prevented_status,
                prevented_reason,
                segment_index=segment_index,
            )

        canonical = self._canonicalize_action_result(action_result)
        dispatched = bool(canonical.metadata.get("executed", False))
        effect_receipt = self._effect_policy.finalize(
            declaration, canonical, dispatched=dispatched
        )
        canonical = apply_effect_receipt(canonical, effect_receipt)
        lifecycle = lifecycle_receipt_for(
            result=canonical,
            attempt_id=slot.attempt_id,
            spec=lifecycle_spec,
            owner_generation=ledger.owner_generation,
        )
        self._quiescence_barrier.mark_terminal(lifecycle)

        def _on_committed(committed: ToolTerminalReceipt) -> None:
            self._publish_terminal(committed, terminal_callback)
            self._publish_partial(
                committed.batch_snapshot, partial_batch_callback
            )

        receipt = ledger.commit_terminal(
            slot_id=slot.slot_id,
            result=canonical,
            lifecycle=lifecycle,
            effect=effect_receipt,
            owner_generation=ledger.owner_generation,
            on_committed=_on_committed,
        )
        return receipt

    def _canonicalize_action_result(self, item: ActionResult) -> ToolResult:
        try:
            result = ToolResult.from_action_result(item)
        except ToolResultContractError as exc:
            return ToolResult.execution_error(
                code=exc.code,
                error=(
                    "Tool returned a value that violates the canonical result "
                    f"contract ({exc.code})."
                ),
                tool_name=item.name,
                action_id=item.action_id,
                attempts=item.attempts,
                latency_ms=item.latency_ms,
                metadata={
                    "source": "tool_result_boundary",
                    "contract_error_code": exc.code,
                    "executed": True,
                },
            )
        output = result.output
        if result.status == "success" and isinstance(output, dict):
            output_status = str(output.get("status") or "").strip().lower()
            if output_status in {"error", "failed", "denied", "needs_user_input"}:
                return ToolResult.semantic_error(
                    code=output_status,
                    error=str(output.get("error") or output.get("message") or output_status),
                    output=output,
                    tool_name=result.tool_name,
                    action_id=result.action_id,
                    model_output=result.model_output,
                    attempts=result.attempts,
                    latency_ms=result.latency_ms,
                    metadata=result.metadata,
                )
        return result

    def _publish_terminal(
        self,
        receipt: ToolTerminalReceipt,
        callback: Optional[TerminalResultCallback],
    ) -> None:
        if callback is None:
            return
        try:
            callback(receipt)
        except Exception as exc:
            with self._stats_lock:
                self.last_execution_stats["callback_errors"].append(
                    {
                        "kind": "terminal",
                        "slot_id": receipt.slot.slot_id,
                        "error_type": type(exc).__name__,
                    }
                )
            raise

    def _publish_partial(
        self,
        snapshot: Any,
        callback: Optional[PartialBatchCallback],
    ) -> None:
        if callback is None:
            return
        try:
            callback(snapshot)
        except Exception as exc:
            with self._stats_lock:
                self.last_execution_stats["callback_errors"].append(
                    {
                        "kind": "partial_batch",
                        "batch_id": snapshot.batch_id,
                        "error_type": type(exc).__name__,
                    }
                )
            raise

    def _late_worker_completed(
        self,
        attempt_id: Any,
        *,
        owner_generation: int,
        outcome_unknown: bool,
    ) -> None:
        self._quiescence_barrier.mark_worker_completed(
            attempt_id,
            owner_generation=owner_generation,
            outcome_unknown=outcome_unknown,
        )
        with self._stats_lock:
            self.last_execution_stats["late_completions"].append(
                {
                    "attempt_id": attempt_id.to_dict(),
                    "owner_generation": owner_generation,
                    "outcome_unknown": outcome_unknown,
                    "terminal_replacement": False,
                }
            )

    def request_pause(self, timeout: float) -> Any:
        """Expose the capability-driven quiescence barrier to session runtime."""
        self._pause_requested.set()
        return self._quiescence_barrier.request_pause(timeout)

    def _is_concurrency_safe(self, tool_name: str) -> bool:
        """Adjudicate whether a tool may run concurrently. Four levels:

        1. ``ActionExecutionPolicy.parallel_tool_names`` — an explicit
           allow-list restricts parallelism to exactly those names
        2. ``needs_approval`` veto — tools needing approval are NEVER safe
        3. explicit ``ToolSpec.concurrency_safe`` is authoritative in both
           directions (True → safe, False → exclusive)
        4. ``read_only`` heuristic fallback — a read-only tool without an
           explicit declaration is safe by default
        """
        allowed = self.policy.parallel_tool_names
        if allowed is not None and tool_name not in allowed:
            return False
        tool = self._resolve_tool(tool_name)
        if tool is not None and hasattr(tool, "spec"):
            spec = tool.spec
            # Tools needing approval are NEVER concurrency safe
            if getattr(spec, "needs_approval", False):
                return False
            concurrency_safe = getattr(spec, "concurrency_safe", None)
            if concurrency_safe is True:
                return True
            if concurrency_safe is False:
                return False
            # A read-only tool without an explicit concurrency declaration is
            # safe by default; an explicit False remains authoritative.
            if getattr(spec, "read_only", False) is True:
                return True
        return False

    def _segment_actions(self, actions: Sequence[Action]) -> List[List[int]]:
        """Split actions into ordered runs separated by exclusive barriers.

        Each returned segment is either a contiguous run of concurrency-safe
        action indices (which may execute in parallel) or a single exclusive
        action index (which acts as a barrier). Segment order always matches
        the model's original call order.
        """
        segments: List[List[int]] = []
        current: List[int] = []
        for idx, action in enumerate(actions):
            if self._is_concurrency_safe(action.name):
                current.append(idx)
                continue
            if current:
                segments.append(current)
                current = []
            segments.append([idx])
        if current:
            segments.append(current)
        return segments

    def _terminal_result(
        self,
        action: Action,
        status: ActionStatus,
        cancel_source: str,
        *,
        segment_index: int = 0,
    ) -> ActionResult:
        """Build a result for an action that was prevented from starting."""
        return ActionResult(
            name=action.name,
            status=status,
            output=None,
            error=f"action {status.value}: {cancel_source}",
            action_id=action.action_id,
            attempts=0,
            latency_ms=0.0,
            metadata={
                **self._tool_meta(action.name),
                "error_category": status.value,
                "cancel_source": cancel_source,
                "segment_index": segment_index,
                "started": False,
                "executed": False,
            },
        )

    def _error_result(self, action: Action, message: str) -> ActionResult:
        """Create an error ActionResult for a failed concurrent execution slot."""
        card = "\n".join(
            [
                "[TOOL_RESULT_MISSING]",
                "",
                f"Tool: `{action.name}`",
                "Code: `TOOL_RESULT_MISSING`",
                "",
                "The executor did not produce a result. No success was inferred.",
                "Retry the call or choose another distinguishable action.",
            ]
        )
        return ActionResult(
            name=action.name,
            status=ActionStatus.ERROR,
            output=card,
            error=message,
            action_id=action.action_id,
            attempts=1,
            latency_ms=0.0,
            metadata={
                "error_category": "concurrent_execution_error",
                "error_code": "TOOL_RESULT_MISSING",
                "recoverable": True,
                "executed": False,
            },
        )

    # ── Timeout resolution ─────────────────────────────────────────────────────

    def _resolve_timeout(
        self, action: Action, tool: Optional[BaseTool]
    ) -> Tuple[Optional[float], str]:
        """Resolve the effective timeout for an action.

        Precedence: ``Action.timeout_s`` override > ``ToolSpec.timeout_s``
        default > no timeout. Returns ``(timeout_s, source)``.
        """
        action_timeout = getattr(action, "timeout_s", None)
        if action_timeout is not None and action_timeout > 0:
            return float(action_timeout), "action"
        if tool is not None:
            spec_timeout = getattr(getattr(tool, "spec", None), "timeout_s", None)
            if spec_timeout is not None and spec_timeout > 0:
                return float(spec_timeout), "tool_spec"
        return None, "none"

    def _resolve_awaitable(self, value: Any, timeout_s: Optional[float]) -> Any:
        """Drive a coroutine/awaitable returned by a tool to completion.

        Async handlers are awaited rather than being handed back as an
        un-awaited coroutine. Raises ``TimeoutError`` when ``timeout_s``
        elapses first.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        else:
            running_loop = True

        if running_loop is not None:
            # The synchronous executor cannot nest an event loop.  The
            # canonical runtime owns one helper thread for the coroutine; MCP
            # and other async tools do not grow a separate executor path.
            pool = ThreadPoolExecutor(max_workers=1)
            future = pool.submit(asyncio.run, value)
            try:
                return future.result(timeout=timeout_s)
            except FuturesTimeoutError as exc:
                raise ToolWorkerTimeout(
                    "async action timed out while its worker may still run",
                    worker_still_running=True,
                    outcome_unknown=True,
                ) from exc
            finally:
                pool.shutdown(wait=False)

        async def _driver() -> Any:
            if timeout_s is not None:
                return await asyncio.wait_for(value, timeout=timeout_s)
            return await value

        try:
            return asyncio.run(_driver())
        except asyncio.TimeoutError as exc:
            raise ToolWorkerTimeout(
                "async action timed out",
                worker_still_running=False,
                outcome_unknown=True,
            ) from exc

    def _call_tool_with_timeout(
        self,
        tool: Optional[BaseTool],
        name: str,
        args: Dict[str, Any],
        runtime_context: Optional[Dict[str, Any]],
        timeout_s: Optional[float],
        late_worker_callback: Optional[Any] = None,
    ) -> Any:
        """Call a tool, enforcing ``timeout_s`` and awaiting async handlers.

        Sync handlers run on a bounded worker thread so the timeout can be
        observed. Python cannot forcibly kill that thread, so a timeout is
        reported as such without claiming the worker was terminated.
        """
        if timeout_s is None:
            output = self._call_tool(tool, name, args, runtime_context=runtime_context)
            if inspect.isawaitable(output):
                output = self._resolve_awaitable(output, None)
            return output

        # NOTE: deliberately not a `with` block — the context manager joins the
        # worker on exit, which would block for the tool's full duration and
        # defeat the timeout. We shut down without waiting and let the orphaned
        # worker finish on its own (reported via `worker_still_running`).
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(
                self._call_tool, tool, name, args, runtime_context=runtime_context
            )
            try:
                output = future.result(timeout=timeout_s)
            except FuturesTimeoutError as exc:
                if late_worker_callback is not None:
                    future.add_done_callback(lambda _future: late_worker_callback())
                raise ToolWorkerTimeout(
                    f"action exceeded timeout of {timeout_s}s",
                    worker_still_running=True,
                ) from exc
            if inspect.isawaitable(output):
                output = self._resolve_awaitable(output, timeout_s)
            return output
        finally:
            pool.shutdown(wait=False)

    def _execute_one(
        self,
        action: Action,
        env: Optional[Env] = None,
        state: Any = None,
        tracker: Optional[_ConcurrencyTracker] = None,
        segment_index: int = 0,
        runtime_context: Optional[Dict[str, Any]] = None,
        effect_declared: bool = False,
        late_worker_callback: Optional[Any] = None,
    ) -> ActionResult:
        if tracker is not None:
            tracker.enter()
        try:
            return self._execute_one_inner(
                action,
                env=env,
                state=state,
                segment_index=segment_index,
                runtime_context=runtime_context,
                effect_declared=effect_declared,
                late_worker_callback=late_worker_callback,
            )
        finally:
            if tracker is not None:
                tracker.exit()

    def _execute_one_inner(
        self,
        action: Action,
        env: Optional[Env] = None,
        state: Any = None,
        segment_index: int = 0,
        runtime_context: Optional[Dict[str, Any]] = None,
        effect_declared: bool = False,
        late_worker_callback: Optional[Any] = None,
    ) -> ActionResult:
        start = time.monotonic()
        started_at = time.time()
        attempts = 0
        last_error = None
        tool_meta = self._tool_meta(action.name)
        runtime_context = runtime_context or self._build_runtime_context(
            action.name, env=env, state=state
        )
        ordering_meta: Dict[str, Any] = {
            "segment_index": segment_index,
            "started_at": started_at,
            "started": True,
        }

        # Resolve per-tool retry_policy and on_failure from tool spec
        _retry_policy = None
        _on_failure = None
        available = (
            [
                str(item)
                for item in list(self.tool_registry.list_tools() or [])
                if str(item)
            ]
            if hasattr(self.tool_registry, "list_tools")
            else []
        )
        # Model-originated tool names are an exact protocol contract. The
        # registry may support aliases for host integrations, but execution
        # must not silently repair casing or parse argument fragments
        # embedded in a malformed name.
        if available and action.name not in available:
            card = "\n".join(
                [
                    "[TOOL:unknown]",
                    "",
                    f"Unknown tool: `{action.name}`",
                    "",
                    "No tool was executed.",
                    "",
                    "Available tools:",
                    ", ".join(f"`{item}`" for item in available),
                    "",
                    "Retry using an exact tool name and its declared schema.",
                ]
            )
            return self._finish_result(
                action=action,
                status=ActionStatus.ERROR,
                start=start,
                attempts=1,
                tool_meta=tool_meta,
                output=card,
                error=f"Unknown tool: {action.name}",
                extra_metadata={
                    "error_category": "tool_not_found",
                    "raw_tool_name": action.name,
                    "available_tools": available,
                    "recoverable": True,
                    "executed": False,
                },
            )
        tool_preview = self._resolve_tool(action.name)
        if tool_preview is not None and hasattr(tool_preview, 'spec'):
            _retry_policy = getattr(tool_preview.spec, 'retry_policy', None)
            _on_failure = getattr(tool_preview.spec, 'on_failure', None)

        # Unified timeout: Action.timeout_s override > ToolSpec.timeout_s default
        _timeout_s, _timeout_source = self._resolve_timeout(action, tool_preview)
        if _timeout_s is not None:
            ordering_meta["timeout_s"] = _timeout_s
            ordering_meta["timeout_source"] = _timeout_source

        structural = (
            tool_preview.validate_structure(action.args)
            if tool_preview is not None
            else ToolValidationResult.ok()
        )
        if not structural.valid:
            return self._finish_result(
                action=action,
                status=ActionStatus.ERROR,
                start=start,
                attempts=0,
                tool_meta=tool_meta,
                error=structural.message or "tool argument structure is invalid",
                extra_metadata={
                    **ordering_meta,
                    "error_category": structural.code or "validation_error",
                    "error_code": structural.code or "validation_error",
                    "validation": {
                        "valid": False,
                        "boundary": "structural",
                        "message": structural.message,
                        "code": structural.code,
                    },
                    "executed": False,
                },
            )

        # 1. Interceptor before_execute — can modify action args
        interceptor_context = InterceptorContext(
            tool_name=action.name,
            tool_args=dict(action.args),
            step_id=getattr(state, "current_step", 0) if state else 0,
            state=self._engine,
            run_id=getattr(self._engine, "_active_run_id", "") if self._engine else "",
        )
        if self._interceptor_chain is not None:
            action = self._interceptor_chain.before_execute(action, interceptor_context)

        rewritten_structural = (
            tool_preview.validate_structure(action.args)
            if tool_preview is not None
            else ToolValidationResult.ok()
        )
        if not rewritten_structural.valid:
            return self._finish_result(
                action=action,
                status=ActionStatus.ERROR,
                start=start,
                attempts=0,
                tool_meta=tool_meta,
                error=(
                    rewritten_structural.message
                    or "interceptor rewrote tool arguments to an invalid shape"
                ),
                extra_metadata={
                    **ordering_meta,
                    "error_category": (
                        rewritten_structural.code or "validation_error"
                    ),
                    "error_code": rewritten_structural.code or "validation_error",
                    "validation": {
                        "valid": False,
                        "boundary": "post_interceptor_structural",
                        "message": rewritten_structural.message,
                        "code": rewritten_structural.code,
                    },
                    "executed": False,
                },
            )

        # 2. Check needs_approval — triggers interrupt() for human approval
        _auto_approved = False
        if tool_preview is not None and hasattr(tool_preview, 'spec'):
            _needs_approval_val = getattr(tool_preview.spec, 'needs_approval', False)
            if _needs_approval_val:
                if callable(_needs_approval_val) and not isinstance(_needs_approval_val, bool):
                    _needs_approval_val = _needs_approval_val(runtime_context, action.args)
            if _needs_approval_val:
                if self.auto_approve:
                    _auto_approved = True
                else:
                    from ..engine.interrupt import interrupt
                    from ..engine.approval import ToolApprovalItem

                    approval_item = ToolApprovalItem(
                        tool_name=action.name,
                        tool_args=action.args,
                        message=f"Tool '{action.name}' requires approval before execution.",
                    )
                    approval = interrupt(approval_item)
                    if approval == "deny":
                        return self._finish_result(
                            action=action,
                            status=ActionStatus.SKIPPED,
                            start=start,
                            attempts=1,
                            tool_meta=tool_meta,
                            output={"status": "denied", "message": "User denied approval"},
                            extra_metadata={"error_category": "approval_denied"},
                        )

        # Compute effective max attempts from retry_policy or fallback to max_retries
        if _retry_policy is not None:
            _max_attempts = _retry_policy.max_attempts
            _backoff_factor = _retry_policy.backoff_factor
            _max_backoff = _retry_policy.max_backoff
            _jitter = _retry_policy.jitter
            _retryable_exceptions = _retry_policy.retryable_exceptions
        else:
            _max_attempts = action.max_retries + 1  # existing behavior
            _backoff_factor = 0
            _max_backoff = 0
            _jitter = False
            _retryable_exceptions = (Exception,)

        any_dispatched = False
        while attempts < _max_attempts:
            attempts += 1
            dispatched = False
            try:
                tool = self._resolve_tool(action.name)
                validation = self._validate(tool, action.args, runtime_context)
                if not validation.valid:
                    return self._finish_result(
                        action=action,
                        status=ActionStatus.ERROR,
                        start=start,
                        attempts=attempts,
                        tool_meta=tool_meta,
                        error=validation.message or "tool input validation failed",
                        extra_metadata={
                            "error_category": validation.code or "validation_error",
                            "validation": {
                                "valid": validation.valid,
                                "message": validation.message,
                                "code": validation.code,
                                "suggested_args": validation.suggested_args,
                            },
                        },
                    )

                # Read-before-write check for file editing tools
                rbw_blocked = self._check_read_before_write(action)
                if rbw_blocked is not None:
                    return rbw_blocked

                permission = self._check_permissions(tool, action.args, runtime_context)
                if permission.decision == "deny":
                    self._dispatch_tool_hook(
                        "on_permission_denied", action.name, action.args,
                        tool_result=None, permission_decision="deny",
                    )
                    return self._finish_result(
                        action=action,
                        status=ActionStatus.SKIPPED,
                        start=start,
                        attempts=attempts,
                        tool_meta=tool_meta,
                        output={
                            "status": "denied",
                            "message": permission.message,
                            "scope": permission.scope,
                        },
                        extra_metadata={
                            "error_category": "permission_denied",
                            "permission": self._permission_payload(permission),
                        },
                    )
                if permission.decision == "ask":
                    # Try interactive resolution if callback is set
                    if self._permission_interaction_callback is not None:
                        try:
                            user_decision = self._permission_interaction_callback(
                                tool_name=action.name,
                                args=action.args,
                                permission=permission,
                            )
                            if user_decision == "allow":
                                permission = ToolPermissionDecision.allow()
                            elif user_decision == "deny":
                                self._dispatch_tool_hook(
                                    "on_permission_denied", action.name, action.args,
                                    tool_result=None, permission_decision="deny",
                                )
                                return self._finish_result(
                                    action=action,
                                    status=ActionStatus.SKIPPED,
                                    start=start,
                                    attempts=attempts,
                                    tool_meta=tool_meta,
                                    output={
                                        "status": "denied",
                                        "message": "User denied permission",
                                        "scope": permission.scope,
                                    },
                                    extra_metadata={
                                        "error_category": "permission_denied",
                                        "permission": self._permission_payload(permission),
                                    },
                                )
                            # else: fall through to SKIPPED
                        except Exception:
                            pass  # Callback failed, fall through to SKIPPED

                    self._dispatch_tool_hook(
                        "on_permission_denied", action.name, action.args,
                        tool_result=None, permission_decision="ask",
                    )
                    return self._finish_result(
                        action=action,
                        status=ActionStatus.SKIPPED,
                        start=start,
                        attempts=attempts,
                        tool_meta=tool_meta,
                        output={
                            "status": "needs_user_input",
                            "message": permission.message,
                            "scope": permission.scope,
                        },
                        extra_metadata={
                            "error_category": "permission_ask",
                            "permission": self._permission_payload(permission),
                        },
                    )

                effective_args = dict(
                    permission.updated_args
                    if permission.updated_args is not None
                    else action.args
                )
                # A permission policy may narrow or rewrite arguments.  Run
                # the complete validation boundary again, not only the JSON
                # shape check, before dispatching the rewritten request.
                final_structural = (
                    tool.validate_structure(effective_args)
                    if tool is not None
                    else ToolValidationResult.ok()
                )
                final_validation = final_structural
                validation_boundary = "final_structural"
                if final_structural.valid:
                    final_validation = self._validate(
                        tool, effective_args, runtime_context
                    )
                    validation_boundary = "post_permission"
                if not final_validation.valid:
                    return self._finish_result(
                        action=action,
                        status=ActionStatus.ERROR,
                        start=start,
                        attempts=attempts,
                        tool_meta=tool_meta,
                        error=(
                            final_validation.message
                            or "rewritten tool arguments are invalid"
                        ),
                        extra_metadata={
                            "error_category": (
                                final_validation.code or "validation_error"
                            ),
                            "error_code": (
                                final_validation.code or "validation_error"
                            ),
                            "validation": {
                                "valid": False,
                                "boundary": validation_boundary,
                                "message": final_validation.message,
                                "code": final_validation.code,
                            },
                            "executed": False,
                        },
                    )
                self._dispatch_tool_hook(
                    "on_before_tool_use", action.name, effective_args,
                    tool_result=None, permission_decision=permission.decision,
                )
                runtime_context["effect_state"] = (
                    "started" if effect_declared else "no_effect_declared"
                )
                dispatched = True
                any_dispatched = True
                output = self._call_tool_with_timeout(
                    tool,
                    action.name,
                    effective_args,
                    runtime_context=runtime_context,
                    timeout_s=_timeout_s,
                    late_worker_callback=late_worker_callback,
                )
                if output is None:
                    card = "\n".join(
                        [
                            "[TOOL_RESULT_MISSING]",
                            "",
                            f"Tool: `{action.name}`",
                            "Code: `TOOL_RESULT_MISSING`",
                            "",
                            "The tool returned no result. No success was inferred.",
                            "Retry the same call or choose another distinguishable action.",
                        ]
                    )
                    return self._finish_result(
                        action=action,
                        status=ActionStatus.ERROR,
                        start=start,
                        attempts=attempts,
                        tool_meta=tool_meta,
                        output=card,
                        error="Tool returned no result",
                        extra_metadata={
                            "error_category": "tool_result_missing",
                            "error_code": "TOOL_RESULT_MISSING",
                            "raw_tool_name": action.name,
                            "recoverable": True,
                            "executed": True,
                        },
                    )
                self._dispatch_tool_hook(
                    "on_after_tool_use", action.name, effective_args,
                    tool_result=output, permission_decision=permission.decision,
                )
                # Track reads / invalidate writes for read-before-write
                self._track_file_access(action.name, effective_args, output)
                normalized_output = self._normalize_output(tool, output)
                latency = (time.monotonic() - start) * 1000
                result_metadata = {
                    **tool_meta,
                    **ordering_meta,
                    "error_category": None,
                    "permission": self._permission_payload(permission),
                    "progress_count": len(runtime_context["progress_events"]),
                    "artifacts": list(runtime_context["artifacts"]),
                    "ended_at": time.time(),
                    "executed": True,
                }
                if _auto_approved:
                    result_metadata["auto_approved"] = True
                    result_metadata["approval_required"] = True
                result = ActionResult(
                    name=action.name,
                    status=ActionStatus.SUCCESS,
                    output=normalized_output,
                    action_id=action.action_id,
                    attempts=attempts,
                    latency_ms=latency,
                    metadata=result_metadata,
                )
                # 6. Interceptor after_execute — can modify result
                if self._interceptor_chain is not None:
                    result = self._interceptor_chain.after_execute(action, result, interceptor_context)
                return result
            except ToolWorkerTimeout as exc:
                # A timeout is a distinct terminal state, never retried: the
                # worker thread may still be running and we must not claim
                # otherwise.
                timed_out_result = self._finish_result(
                    action=action,
                    status=ActionStatus.TIMED_OUT,
                    start=start,
                    attempts=attempts,
                    tool_meta=tool_meta,
                    error=str(exc),
                    extra_metadata={
                        **ordering_meta,
                        "error_category": "timeout",
                        "worker_still_running": exc.worker_still_running,
                        "timeout_outcome_unknown": exc.outcome_unknown,
                        "executed": True,
                        "ended_at": time.time(),
                    },
                )
                if self._interceptor_chain is not None:
                    timed_out_result = self._interceptor_chain.after_execute(
                        action, timed_out_result, interceptor_context
                    )
                return timed_out_result
            except Exception as exc:  # pragma: no cover - defensive path
                last_error = str(exc)
                if effect_declared and dispatched:
                    break
                # Check if this exception type is retryable
                if not isinstance(exc, _retryable_exceptions):
                    break
                # Exponential backoff with optional jitter
                if attempts < _max_attempts and _backoff_factor > 0:
                    import random
                    delay = min(_backoff_factor * (2 ** (attempts - 1)), _max_backoff)
                    if _jitter:
                        delay = delay * (0.5 + random.random())
                    time.sleep(delay)

        error_category = "runtime_error"
        if last_error and "not found" in last_error.lower():
            error_category = "tool_not_found"

        # Call on_failure callback if registered
        if _on_failure is not None:
            try:
                _on_failure(action=action, error=last_error, attempts=attempts)
            except Exception:
                pass  # on_failure must not raise

        error_result = self._finish_result(
            action=action,
            status=ActionStatus.ERROR,
            start=start,
            attempts=attempts,
            tool_meta=tool_meta,
            error=last_error or "unknown action execution error",
            extra_metadata={
                **ordering_meta,
                "error_category": error_category,
                "progress_count": len(runtime_context["progress_events"]),
                "artifacts": list(runtime_context["artifacts"]),
                "ended_at": time.time(),
                "executed": any_dispatched,
            },
        )
        # Interceptor after_execute on error path too
        if self._interceptor_chain is not None:
            error_result = self._interceptor_chain.after_execute(action, error_result, interceptor_context)
        return error_result

    def _finish_result(
        self,
        *,
        action: Action,
        status: ActionStatus,
        start: float,
        attempts: int,
        tool_meta: Dict[str, Any],
        output: Any = None,
        error: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> ActionResult:
        if output is None and error is not None:
            code = str((extra_metadata or {}).get("error_code") or "TOOL_EXECUTION_ERROR")
            output = "\n".join(
                [
                    "[TOOL:error]",
                    "",
                    f"Tool: `{action.name}`",
                    f"Code: `{code}`",
                    "",
                    str(error),
                    "No success was inferred.",
                ]
            )
        latency = (time.monotonic() - start) * 1000
        metadata = dict(tool_meta)
        metadata.update(extra_metadata or {})
        return ActionResult(
            name=action.name,
            status=status,
            output=output,
            error=error,
            action_id=action.action_id,
            attempts=attempts,
            latency_ms=latency,
            metadata=metadata,
        )

    def _build_runtime_context(
        self,
        name: str,
        env: Optional[Env],
        state: Any,
        runtime_facts: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        required_ops = self._required_ops(name)
        permission_context = self._resolve_permission_context(env=env, state=state)
        progress_events: List[Dict[str, Any]] = []
        artifacts: List[Dict[str, Any]] = []

        def _emit_progress(payload: Dict[str, Any]) -> None:
            progress_events.append(dict(payload))

        def _record_artifact(payload: Dict[str, Any]) -> None:
            artifacts.append(dict(payload))

        context = {
            "env": env,
            "state": state,
            "ops": self._resolve_ops(required_ops, env),
            "tool_registry": self.tool_registry,
            "permission_context": permission_context,
            "progress_events": progress_events,
            "artifacts": artifacts,
            "emit_progress": _emit_progress,
            "record_artifact": _record_artifact,
            "delegate_depth": self.delegate_depth,
            "parent_run_id": "",
            "trace_writer": self.trace_writer,
            "shared_memory": self.shared_memory,
            "work_runtime": getattr(
                getattr(self._engine, "runtime", None), "work_runtime", None
            ),
            "session": getattr(self._engine, "_session_handle", None),
            "work_graph": getattr(self._engine, "_qitos_work_graph", None),
        }
        context.update(runtime_facts or {})
        return context

    def _resolve_tool(self, name: str) -> Optional[BaseTool]:
        if hasattr(self.tool_registry, "get"):
            tool = self.tool_registry.get(name)
            if tool is not None:
                return tool
        return None

    def _validate(
        self,
        tool: Optional[BaseTool],
        args: Dict[str, Any],
        runtime_context: Dict[str, Any],
    ) -> ToolValidationResult:
        if tool is None or not hasattr(tool, "validate_input"):
            return ToolValidationResult.ok()
        structural = tool.validate_structure(args)
        if not structural.valid:
            return structural
        result = tool.validate_input(dict(args), runtime_context=runtime_context)
        if isinstance(result, ToolValidationResult):
            return result
        if isinstance(result, dict):
            return ToolValidationResult(
                valid=bool(result.get("valid", result.get("result", True))),
                message=str(result.get("message", "")),
                code=str(result.get("code", result.get("error_code", ""))),
                suggested_args=result.get("suggested_args"),
            )
        if result is False:
            return ToolValidationResult.fail("tool input validation failed")
        return ToolValidationResult.ok()

    def _check_permissions(
        self,
        tool: Optional[BaseTool],
        args: Dict[str, Any],
        runtime_context: Dict[str, Any],
    ) -> ToolPermissionDecision:
        # Use permission pipeline if available
        if self._pipeline is not None:
            tool_spec = getattr(tool, "spec", None) if tool is not None else None
            return self._pipeline.evaluate(
                tool_name=getattr(tool, "name", "") if tool else "",
                args=dict(args),
                tool_spec=tool_spec,
                runtime_context=runtime_context,
            )
        # Fallback: use tool's own permission check
        if tool is None or not hasattr(tool, "check_permissions"):
            return ToolPermissionDecision.allow()
        result = tool.check_permissions(dict(args), runtime_context=runtime_context)
        if isinstance(result, ToolPermissionDecision):
            return result
        if isinstance(result, dict):
            return ToolPermissionDecision(
                decision=str(result.get("decision", "allow")),
                message=str(result.get("message", "")),
                scope=str(result.get("scope", "")),
                updated_args=result.get("updated_args"),
            )
        if result in {"allow", "deny", "ask"}:
            return ToolPermissionDecision(decision=str(result))
        return ToolPermissionDecision.allow()

    def _call_tool(
        self,
        tool: Optional[BaseTool],
        name: str,
        args: Dict[str, Any],
        runtime_context: Optional[Dict[str, Any]] = None,
    ) -> Any:
        if tool is not None:
            return tool.call(args, runtime_context=runtime_context)
        if hasattr(self.tool_registry, "call"):
            return self.tool_registry.call(
                name, runtime_context=runtime_context, **args
            )

        if hasattr(self.tool_registry, "get"):
            fallback = self.tool_registry.get(name)
            if fallback is None:
                raise ValueError(f"Unknown tool: {name}")
            if hasattr(fallback, "call"):
                return fallback.call(args, runtime_context=runtime_context)
            if hasattr(fallback, "execute"):
                return fallback.execute(args, runtime_context=runtime_context)
            if hasattr(fallback, "run"):
                return fallback.run(**args)
            return fallback(**args)

        raise TypeError(
            "Unsupported tool registry. Expected object with call() or get()."
        )

    def _normalize_output(self, tool: Optional[BaseTool], output: Any) -> Any:
        if tool is None:
            return output
        max_chars = getattr(getattr(tool, "spec", None), "result_max_chars", None)
        if not max_chars or max_chars <= 0:
            return output
        if isinstance(output, str):
            return self._truncate_text(output, max_chars)
        if isinstance(output, dict):
            normalized = dict(output)
            for key in ("content", "stdout", "stderr", "result", "summary", "message"):
                value = normalized.get(key)
                if isinstance(value, str):
                    normalized[key] = self._truncate_text(value, max_chars)
            return normalized
        return output

    def _truncate_text(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n... [truncated]"

    def _resolve_permission_context(
        self, env: Optional[Env], state: Any
    ) -> ToolPermissionContext:
        candidate = None
        if state is not None:
            metadata = getattr(state, "metadata", None)
            if isinstance(metadata, dict):
                candidate = metadata.get("tool_permission_context")
        if candidate is None and env is not None:
            candidate = getattr(env, "tool_permission_context", None)
        if isinstance(candidate, ToolPermissionContext):
            return candidate
        if isinstance(candidate, dict):
            return ToolPermissionContext.from_dict(candidate)
        return ToolPermissionContext()

    def _permission_payload(self, decision: ToolPermissionDecision) -> Dict[str, Any]:
        return {
            "decision": decision.decision,
            "message": decision.message,
            "scope": decision.scope,
            "matched_rule": (
                {
                    "effect": decision.matched_rule.effect,
                    "tool_name": decision.matched_rule.tool_name,
                    "tool_family": decision.matched_rule.tool_family,
                    "scope": decision.matched_rule.scope,
                    "message": decision.matched_rule.message,
                }
                if decision.matched_rule is not None
                else None
            ),
        }

    def _required_ops(self, name: str) -> List[str]:
        if hasattr(self.tool_registry, "get"):
            try:
                tool = self.tool_registry.get(name)
                if tool is not None and hasattr(tool, "spec"):
                    spec = getattr(tool, "spec")
                    if hasattr(spec, "required_ops"):
                        value = getattr(spec, "required_ops")
                        if isinstance(value, list):
                            return [str(x) for x in value]
            except Exception:
                return []
        return []

    def _resolve_ops(
        self, required_ops: List[str], env: Optional[Env]
    ) -> Dict[str, Any]:
        if not required_ops:
            return {}
        if env is None:
            raise ValueError(
                f"Tool requires ops {required_ops} but no env was provided"
            )
        out: Dict[str, Any] = {}
        for group in required_ops:
            ops = env.get_ops(group)
            if ops is None:
                raise ValueError(
                    f"Env '{getattr(env, 'name', 'env')}' missing required ops group: {group}"
                )
            out[group] = ops
        return out

    def _tool_meta(self, name: str) -> dict[str, Any]:
        if hasattr(self.tool_registry, "describe_tool"):
            try:
                desc = self.tool_registry.describe_tool(name)
                origin = desc.get("origin", {})
                return {
                    "tool_name": desc.get("name", name),
                    "toolset_name": origin.get("toolset_name"),
                    "toolset_version": origin.get("toolset_version"),
                    "source": origin.get("source", "function"),
                    "lifecycle": desc.get("lifecycle", "sync_function"),
                    "declares_effect": bool(desc.get("declares_effect", False)),
                }
            except Exception:
                pass
        return {
            "tool_name": name,
            "toolset_name": None,
            "toolset_version": None,
            "source": "unknown",
            "lifecycle": "sync_function",
            "declares_effect": False,
        }

    def _dispatch_tool_hook(
        self,
        hook_method: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        tool_result: Any = None,
        permission_decision: Optional[str] = None,
    ) -> None:
        """Dispatch a tool-level hook to all registered engine hooks."""
        if self._engine is None:
            return
        hooks = getattr(self._engine, "hooks", None)
        if not hooks:
            return
        from .hooks import ToolHookContext
        # Native tool-calling executes through ActionExecutor instead of the
        # regular step-hook path.  The old placeholder ``0`` therefore made
        # every tool observation in a rollout appear to have happened at step
        # zero.  ``current_step`` is advanced only after a step has completed,
        # so while a tool is executing it is the authoritative step id.
        active_state = getattr(self._engine, "_active_state", None)
        step_id = int(getattr(active_state, "current_step", 0) or 0)
        ctx = ToolHookContext(
            task="",
            step_id=step_id,
            phase=RuntimePhase.ACT,
            state=cast(StateSchema, active_state),
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=tool_result,
            permission_decision=permission_decision,
        )
        for hook in hooks:
            method = getattr(hook, hook_method, None)
            if method is not None:
                try:
                    method(ctx, self._engine)
                except Exception:
                    pass

    # ── Read-before-write support ──────────────────────────────────────────────

    _WRITE_TOOL_NAMES = frozenset({
        "file_edit_v2", "write_file", "Edit", "Write",
        "str_replace", "insert", "replace_lines", "append_file",
    })

    _READ_TOOL_NAMES = frozenset({
        "file_read_v2", "read_file", "Read", "view",
    })

    def _check_read_before_write(self, action: Action) -> Optional[ActionResult]:
        """Check read-before-write enforcement for file editing tools.

        Returns an ActionResult if the action should be blocked, None otherwise.
        """
        if self._rbw_enforcer is None:
            return None
        if action.name not in self._WRITE_TOOL_NAMES:
            return None

        path = action.args.get("path") or action.args.get("file_path", "")
        if not path:
            return None

        allowed, reason = self._rbw_enforcer.check_write(path)
        if allowed:
            return None

        start = time.monotonic()
        return self._finish_result(
            action=action,
            status=ActionStatus.SKIPPED,
            start=start,
            attempts=1,
            tool_meta=self._tool_meta(action.name),
            output={
                "status": "error",
                "message": reason,
                "error_category": "read_before_write",
            },
            extra_metadata={
                "error_category": "read_before_write",
            },
        )

    def _track_file_access(
        self, tool_name: str, args: Dict[str, Any], output: Any
    ) -> None:
        """Track file reads and invalidate cache on writes for RBW enforcement."""
        if self._rbw_enforcer is None:
            return

        # Record successful file reads
        if tool_name in self._READ_TOOL_NAMES:
            path = args.get("path") or args.get("file_path", "")
            if path and isinstance(output, dict):
                content = output.get("content", "")
                if content:
                    self._rbw_enforcer.record_read(path, content)
                elif isinstance(output, str) and output:
                    self._rbw_enforcer.record_read(path, output)

        # Invalidate cache after successful writes
        if tool_name in self._WRITE_TOOL_NAMES:
            path = args.get("path") or args.get("file_path", "")
            if path:
                self._rbw_enforcer.invalidate(path)
