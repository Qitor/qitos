"""Recovery policies and diagnostics for QitOS runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..core.errors import RuntimeErrorInfo, StopReason, classify_exception


@dataclass
class RecoveryDecision:
    handled: bool
    continue_run: bool
    stop_reason: Optional[StopReason] = None
    note: Optional[str] = None
    state_patch: Optional[Dict[str, Any]] = None
    instruction_patch: Optional[str] = None


@dataclass
class FailureDiagnostic:
    step_id: int
    phase: str
    category: str
    message: str
    recoverable: bool
    decision: str
    recommendation: str


@dataclass
class RecoveryTracker:
    diagnostics: List[FailureDiagnostic] = field(default_factory=list)

    def add(self, info: RuntimeErrorInfo, recommendation: str, decision: str) -> None:
        self.diagnostics.append(
            FailureDiagnostic(
                step_id=info.step_id,
                phase=info.phase,
                category=info.category.value,
                message=info.message,
                recoverable=info.recoverable,
                decision=decision,
                recommendation=recommendation,
            )
        )

    def summary(self) -> Dict[str, Any]:
        return {
            "failure_count": len(self.diagnostics),
            "failures": [d.__dict__ for d in self.diagnostics],
        }


class RecoveryPolicy:
    """Default runtime recovery policy."""

    def __init__(self, max_recoveries_per_run: Optional[int] = None):
        if max_recoveries_per_run is None:
            try:
                max_recoveries_per_run = int(
                    os.environ.get("QITOS_MAX_RECOVERIES", "100")
                )
            except (TypeError, ValueError):
                max_recoveries_per_run = 100
        self.max_recoveries_per_run = max_recoveries_per_run
        # CONSECUTIVE recoverable-failure streak (by step contiguity), not a
        # lifetime total: scattered transient blips reset between successful
        # steps and are tolerated for the whole run, while a sustained outage
        # dies cleanly once the streak exceeds the cap (no fake-2h spin).
        self._recoveries = 0
        self._last_step_id: Optional[int] = None
        self._scoped_recovery_key: Optional[str] = None
        self._scoped_recoveries = 0
        self.tracker = RecoveryTracker()

    def reset(self) -> None:
        self._recoveries = 0
        self._last_step_id = None
        self._scoped_recovery_key = None
        self._scoped_recoveries = 0
        self.tracker = RecoveryTracker()

    def handle(
        self, state: Any, phase: str, step_id: int, exc: Exception
    ) -> RecoveryDecision:
        info = classify_exception(exc, phase, step_id)
        recommendation = self._recommendation_for(info.category)

        if not info.recoverable:
            self.tracker.add(info, recommendation, decision="stop")
            return RecoveryDecision(
                handled=True,
                continue_run=False,
                stop_reason=StopReason.UNRECOVERABLE_ERROR,
                note="unrecoverable_stop",
            )

        scoped_limit = info.details.get("max_recoveries")
        has_scoped_limit = (
            isinstance(scoped_limit, int)
            and not isinstance(scoped_limit, bool)
            and scoped_limit >= 0
        )
        scoped_key = info.details.get("code")
        has_scoped_key = isinstance(scoped_key, str) and bool(scoped_key)

        # Update the consecutive-failure streak.
        is_consecutive = (
            self._last_step_id is not None
            and (step_id - self._last_step_id) <= 1
        )
        if is_consecutive:
            self._recoveries += 1
        else:
            self._recoveries = 1

        if has_scoped_limit and has_scoped_key:
            if is_consecutive and self._scoped_recovery_key == scoped_key:
                self._scoped_recoveries += 1
            else:
                self._scoped_recoveries = 1
            self._scoped_recovery_key = scoped_key
        else:
            self._scoped_recovery_key = None
            self._scoped_recoveries = 0
        self._last_step_id = step_id

        global_limit_exhausted = self._recoveries > self.max_recoveries_per_run
        scoped_limit_exhausted = (
            has_scoped_limit
            and has_scoped_key
            and self._scoped_recoveries > scoped_limit
        )
        if global_limit_exhausted or scoped_limit_exhausted:
            self.tracker.add(info, recommendation, decision="stop")
            return RecoveryDecision(
                handled=True,
                continue_run=False,
                stop_reason=StopReason.UNRECOVERABLE_ERROR,
                note="max_recovery_exhausted",
            )

        self.tracker.add(info, recommendation, decision="continue")
        return RecoveryDecision(
            handled=True, continue_run=True, note="recoverable_continue"
        )

    def _recommendation_for(self, category: Any) -> str:
        key = getattr(category, "value", str(category))
        mapping = {
            "tool_error": "Check tool name, arguments, and environment permissions.",
            "parse_error": "Adjust parser or output format constraints.",
            "state_error": "Validate state transitions and required state fields.",
            "model_error": "Check model connectivity/timeout and retry strategy.",
            "system_error": "Inspect runtime configuration and uncaught exceptions.",
        }
        return mapping.get(
            key, "Inspect runtime diagnostics and retry with stricter guards."
        )


def build_failure_report(
    policy: RecoveryPolicy, stop_reason: Optional[str]
) -> Dict[str, Any]:
    summary = policy.tracker.summary()
    summary["stop_reason"] = stop_reason
    return summary
