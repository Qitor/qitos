from __future__ import annotations

from qitos.core.errors import (
    ErrorCategory,
    ModelExecutionError,
    RuntimeErrorInfo,
    classify_exception,
)
from qitos.engine.recovery import RecoveryPolicy


def test_classify_exception_marks_stream_timeout_as_recoverable_model_error() -> None:
    info = classify_exception(RuntimeError("stream timeout"), "DECIDE", 7)

    assert info.category == ErrorCategory.MODEL
    assert info.recoverable is True
    assert info.phase == "DECIDE"
    assert info.step_id == 7


def test_classify_exception_marks_timed_out_message_as_recoverable_model_error() -> None:
    info = classify_exception(RuntimeError("request timed out while streaming"), "PROPOSE", 3)

    assert info.category == ErrorCategory.MODEL
    assert info.recoverable is True


def test_recovery_policy_continues_on_stream_timeout() -> None:
    decision = RecoveryPolicy().handle(state=None, phase="DECIDE", step_id=11, exc=RuntimeError("stream timeout"))

    assert decision.handled is True
    assert decision.continue_run is True
    assert decision.stop_reason is None


def test_recovery_policy_honors_error_scoped_limit_without_changing_global_limit() -> None:
    scoped_policy = RecoveryPolicy(max_recoveries_per_run=3)

    def empty_response_error(step_id: int) -> ModelExecutionError:
        return ModelExecutionError(
            RuntimeErrorInfo(
                category=ErrorCategory.MODEL,
                message="empty model response",
                phase="DECIDE",
                step_id=step_id,
                recoverable=True,
                details={
                    "code": "empty_model_response",
                    "max_recoveries": 1,
                },
            )
        )

    first = scoped_policy.handle(
        state=None, phase="DECIDE", step_id=0, exc=empty_response_error(0)
    )
    second = scoped_policy.handle(
        state=None, phase="DECIDE", step_id=1, exc=empty_response_error(1)
    )

    assert first.continue_run is True
    assert second.continue_run is False
    assert second.note == "max_recovery_exhausted"

    unscoped_policy = RecoveryPolicy(max_recoveries_per_run=3)
    unscoped_decisions = [
        unscoped_policy.handle(
            state=None,
            phase="DECIDE",
            step_id=step_id,
            exc=RuntimeError("stream timeout"),
        )
        for step_id in range(4)
    ]

    assert [item.continue_run for item in unscoped_decisions] == [
        True,
        True,
        True,
        False,
    ]


def test_error_scoped_limit_does_not_count_an_unrelated_recoverable_failure() -> None:
    policy = RecoveryPolicy(max_recoveries_per_run=100)
    timeout = policy.handle(
        state=None,
        phase="DECIDE",
        step_id=0,
        exc=RuntimeError("stream timeout"),
    )

    def empty_response_error(step_id: int) -> ModelExecutionError:
        return ModelExecutionError(
            RuntimeErrorInfo(
                category=ErrorCategory.MODEL,
                message="empty model response",
                phase="DECIDE",
                step_id=step_id,
                recoverable=True,
                details={
                    "code": "empty_model_response",
                    "max_recoveries": 1,
                },
            )
        )

    first_empty = policy.handle(
        state=None,
        phase="DECIDE",
        step_id=1,
        exc=empty_response_error(1),
    )
    second_empty = policy.handle(
        state=None,
        phase="DECIDE",
        step_id=2,
        exc=empty_response_error(2),
    )

    assert timeout.continue_run is True
    assert first_empty.continue_run is True
    assert second_empty.continue_run is False
    assert second_empty.note == "max_recovery_exhausted"
