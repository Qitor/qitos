"""Reference mechanics behind :class:`ActionExecutor`'s runtime seam."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import replace
from typing import Any, Callable, Dict, Optional, Sequence
from uuid import uuid4

from ..core.action import Action
from ..core.session import AttemptIdentity
from ..core.tool import BaseTool
from ..core.tool_result import ToolResult
from ..core.tool_runtime import (
    TOOL_LIFECYCLE_MATRIX,
    TerminalDisposition,
    ToolBatchSnapshot,
    ToolEffectDeclaration,
    ToolEffectPolicy,
    ToolEffectReceipt,
    ToolLifecycleReceipt,
    ToolLifecycleSpec,
    ToolLifecycleState,
    ToolResourceKind,
    ToolSlotSnapshot,
    ToolTerminalReceipt,
)


class ReferenceEffectPolicy(ToolEffectPolicy):
    """Conservative effect policy driven only by declared and terminal facts."""

    def declare(
        self,
        action: Action,
        tool: Optional[BaseTool],
        runtime_context: Dict[str, Any],
    ) -> Optional[ToolEffectDeclaration]:
        spec = getattr(tool, "spec", None) if tool is not None else None
        declaration = getattr(spec, "effect", None)
        if declaration is None:
            return None
        if callable(declaration):
            declaration = declaration(dict(action.args), dict(runtime_context))
        if declaration is None:
            return None
        if not isinstance(declaration, ToolEffectDeclaration):
            raise TypeError("effect declaration factory returned an unsupported value")
        if declaration.idempotency_key:
            return declaration
        identity_payload = {
            "effect_ref": declaration.effect_ref,
            "action_name": action.name,
            "action_id": action.action_id,
            "args": action.args,
            "batch_id": runtime_context.get("batch_id"),
            "slot_id": runtime_context.get("slot_id"),
        }
        digest = hashlib.sha256(
            json.dumps(
                identity_payload, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        return ToolEffectDeclaration(
            effect_ref=declaration.effect_ref,
            idempotency_key=f"idem:{digest}",
            metadata=declaration.metadata,
        )

    def finalize(
        self,
        declaration: Optional[ToolEffectDeclaration],
        result: ToolResult,
        *,
        dispatched: bool,
    ) -> ToolEffectReceipt:
        # Lifecycle uncertainty outranks the absence of a declared side effect:
        # retrying while the original worker is live can still duplicate the
        # tool invocation itself, and an unknown remote outcome must be
        # reconciled before a new attempt is safe.
        if result.worker_still_running:
            return ToolEffectReceipt(
                declaration=declaration,
                state="unknown" if declaration is not None else "no_effect_declared",
                retry_disposition="blocked_worker_running",
                reconciliation_required=declaration is not None,
                outcome_unknown=declaration is not None,
            )
        if result.outcome_unknown:
            return ToolEffectReceipt(
                declaration=declaration,
                state=(
                    "reconciliation_required"
                    if declaration is not None
                    else "no_effect_declared"
                ),
                retry_disposition="requires_reconciliation",
                reconciliation_required=True,
                outcome_unknown=True,
            )
        if result.effect_state != "no_effect_declared":
            effective = declaration
            if effective is None:
                effective = ToolEffectDeclaration(
                    effect_ref=result.effect_ref or "effect:runtime",
                    idempotency_key=result.idempotency_ref,
                )
            return ToolEffectReceipt(
                declaration=effective,
                state=result.effect_state,
                retry_disposition=result.retry_disposition,
                reconciliation_required=result.reconciliation_required,
                outcome_unknown=result.outcome_unknown,
            )
        if declaration is None:
            disposition = result.retry_disposition
            if disposition == "not_evaluated":
                disposition = "retryable" if result.recoverable else "non_retryable"
            return ToolEffectReceipt(
                declaration=None,
                state="no_effect_declared",
                retry_disposition=disposition,
            )
        if not dispatched:
            return ToolEffectReceipt(
                declaration=declaration,
                state="rejected",
                retry_disposition=(
                    "retryable" if result.recoverable else "non_retryable"
                ),
            )
        if result.status == "success":
            return ToolEffectReceipt(
                declaration=declaration,
                state="committed",
                retry_disposition="non_retryable",
            )
        return ToolEffectReceipt(
            declaration=declaration,
            state="reconciliation_required",
            retry_disposition="requires_reconciliation",
            reconciliation_required=True,
            outcome_unknown=True,
        )


def apply_effect_receipt(
    result: ToolResult, receipt: ToolEffectReceipt
) -> ToolResult:
    """Return one canonical result carrying the policy's typed effect facts."""
    return replace(
        result,
        effect_ref=receipt.effect_ref,
        effect_state=receipt.state,
        idempotency_ref=receipt.idempotency_ref,
        retry_disposition=receipt.retry_disposition,
        reconciliation_required=receipt.reconciliation_required,
        outcome_unknown=receipt.outcome_unknown,
    )


def lifecycle_spec_for(tool: Optional[BaseTool]) -> ToolLifecycleSpec:
    spec = getattr(tool, "spec", None) if tool is not None else None
    adapter = getattr(spec, "lifecycle_adapter", None)
    if adapter is not None:
        adapter_spec = getattr(adapter, "spec", None)
        if not isinstance(adapter_spec, ToolLifecycleSpec):
            raise TypeError("lifecycle adapter must publish ToolLifecycleSpec")
        return adapter_spec
    kind = getattr(spec, "lifecycle", ToolResourceKind.SYNC_FUNCTION)
    if not isinstance(kind, ToolResourceKind):
        kind = ToolResourceKind(kind)
    return TOOL_LIFECYCLE_MATRIX[kind]


def lifecycle_receipt_for(
    *,
    result: ToolResult,
    attempt_id: AttemptIdentity,
    spec: ToolLifecycleSpec,
    owner_generation: int,
) -> ToolLifecycleReceipt:
    metadata = result.metadata
    raw_started = metadata.get("started_at", time.time())
    started_at = float(raw_started) if isinstance(raw_started, (int, float)) else time.time()
    raw_ended = metadata.get("ended_at")
    completed_at: Optional[float] = (
        float(raw_ended) if isinstance(raw_ended, (int, float)) else time.time()
    )
    state = ToolLifecycleState.TERMINAL
    if result.worker_still_running:
        state = ToolLifecycleState.WORKER_STILL_RUNNING
        completed_at = None
    elif result.outcome_unknown:
        state = ToolLifecycleState.OUTCOME_UNKNOWN
    elif result.status == "cancelled":
        state = ToolLifecycleState.CANCELLED
    return ToolLifecycleReceipt(
        attempt_id=attempt_id,
        spec=spec,
        state=state,
        owner_generation=owner_generation,
        started_at=started_at,
        completed_at=completed_at,
        worker_still_running=result.worker_still_running,
        outcome_unknown=result.outcome_unknown,
    )


class ToolBatchLedger:
    """Thread-safe single-writer ledger for one declared action batch."""

    def __init__(
        self,
        actions: Sequence[Action],
        *,
        batch_id: Optional[str] = None,
        owner_generation: int = 0,
    ) -> None:
        if not actions:
            raise ValueError("ToolBatchLedger requires at least one action")
        if (
            not isinstance(owner_generation, int)
            or isinstance(owner_generation, bool)
            or owner_generation < 0
        ):
            raise ValueError("owner_generation must be a non-negative integer")
        self.batch_id = str(batch_id or f"batch:{uuid4().hex}")
        self.owner_generation = owner_generation
        self._lock = threading.Lock()
        self._publication_lock = threading.Lock()
        self._completion_order: list[str] = []
        self._slots: list[ToolSlotSnapshot] = []
        used: set[str] = set()
        for index, action in enumerate(actions):
            candidate = str(action.action_id or f"{self.batch_id}:slot:{index}")
            slot_id = candidate
            if slot_id in used:
                slot_id = f"{candidate}:slot:{index}"
            used.add(slot_id)
            attempt = _attempt_identity(action)
            self._slots.append(
                ToolSlotSnapshot(
                    slot_id=slot_id,
                    declaration_index=index,
                    action_name=action.name,
                    action_id=action.action_id,
                    attempt_id=attempt,
                    owner_generation=owner_generation,
                )
            )

    def snapshot(self) -> ToolBatchSnapshot:
        with self._lock:
            return self._snapshot_unlocked()

    def slot_for_index(self, index: int) -> ToolSlotSnapshot:
        with self._lock:
            return self._slots[index]

    def commit_terminal(
        self,
        *,
        slot_id: str,
        result: ToolResult,
        lifecycle: ToolLifecycleReceipt,
        effect: ToolEffectReceipt,
        owner_generation: int,
        on_committed: Optional[Callable[[ToolTerminalReceipt], None]] = None,
    ) -> ToolTerminalReceipt:
        # Keep commit order and observer publication order identical.  The
        # state lock is released before invoking the observer, while this
        # per-batch publication lock prevents a later terminal from overtaking
        # the earlier receipt at the callback boundary.
        with self._publication_lock:
            receipt = self._commit_terminal(
                slot_id=slot_id,
                result=result,
                lifecycle=lifecycle,
                effect=effect,
                owner_generation=owner_generation,
            )
            if (
                receipt.disposition is TerminalDisposition.COMMITTED
                and on_committed is not None
            ):
                on_committed(receipt)
            return receipt

    def _commit_terminal(
        self,
        *,
        slot_id: str,
        result: ToolResult,
        lifecycle: ToolLifecycleReceipt,
        effect: ToolEffectReceipt,
        owner_generation: int,
    ) -> ToolTerminalReceipt:
        with self._lock:
            index = self._slot_index(slot_id)
            current = self._slots[index]
            if owner_generation != self.owner_generation:
                rejected = replace(
                    result,
                    attempt_id=current.attempt_id,
                    owner_generation=owner_generation,
                    stale_owner=True,
                    late_result=True,
                )
                rejected_slot = replace(
                    current,
                    result=rejected,
                    completion_index=len(self._completion_order),
                )
                return ToolTerminalReceipt(
                    disposition=TerminalDisposition.STALE_OWNER_REJECTED,
                    slot=rejected_slot,
                    lifecycle=lifecycle,
                    effect=effect,
                    batch_snapshot=self._snapshot_unlocked(),
                )
            if current.terminal:
                duplicate_slot = replace(
                    current,
                    result=replace(result, late_result=True),
                )
                return ToolTerminalReceipt(
                    disposition=TerminalDisposition.DUPLICATE_IGNORED,
                    slot=duplicate_slot,
                    lifecycle=lifecycle,
                    effect=effect,
                    batch_snapshot=self._snapshot_unlocked(),
                )
            enriched = replace(
                result,
                attempt_id=current.attempt_id,
                owner_generation=owner_generation,
            )
            completion_index = len(self._completion_order)
            self._slots[index] = replace(
                current,
                result=enriched,
                completion_index=completion_index,
            )
            self._completion_order.append(slot_id)
            partial = self._snapshot_unlocked()
            enriched = replace(enriched, batch_closure=partial.batch_closure())
            committed_slot = replace(self._slots[index], result=enriched)
            self._slots[index] = committed_slot
            snapshot = self._snapshot_unlocked()
            return ToolTerminalReceipt(
                disposition=TerminalDisposition.COMMITTED,
                slot=committed_slot,
                lifecycle=lifecycle,
                effect=effect,
                batch_snapshot=snapshot,
            )

    def _slot_index(self, slot_id: str) -> int:
        for index, slot in enumerate(self._slots):
            if slot.slot_id == slot_id:
                return index
        raise KeyError(f"unknown tool batch slot: {slot_id}")

    def _snapshot_unlocked(self) -> ToolBatchSnapshot:
        terminal_count = sum(slot.terminal for slot in self._slots)
        return ToolBatchSnapshot(
            batch_id=self.batch_id,
            slots=tuple(self._slots),
            completion_order=tuple(self._completion_order),
            closed=terminal_count == len(self._slots),
        )


def _attempt_identity(action: Action) -> AttemptIdentity:
    raw = action.metadata.get("attempt_id") if isinstance(action.metadata, dict) else None
    if isinstance(raw, AttemptIdentity):
        return raw
    if isinstance(raw, dict):
        return AttemptIdentity.from_dict(raw)
    if isinstance(raw, str) and raw.startswith("attempt_"):
        return AttemptIdentity(raw)
    return AttemptIdentity.generate()


__all__ = [
    "ReferenceEffectPolicy",
    "ToolBatchLedger",
    "apply_effect_receipt",
    "lifecycle_receipt_for",
    "lifecycle_spec_for",
]
