"""Explicit opt-in model-layer retry policy (Batch M decision item)."""

from __future__ import annotations

from typing import Any, Dict, List

from qitos.core.tool import RetryPolicy
from qitos.models.base import Model


class _TransientError(Exception):
    pass


class _PermanentError(Exception):
    pass


class _FlakyModel(Model):
    def __init__(self, failures: int = 2, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.failures = failures
        self.attempts = 0

    def _call_api(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        self.attempts += 1
        if self.attempts <= self.failures:
            raise _TransientError("request time out")
        return "Final Answer: recovered"


def test_no_policy_means_no_silent_retries() -> None:
    model = _FlakyModel(failures=1)

    try:
        model([{"role": "user", "content": "hi"}])
    except _TransientError:
        pass
    else:
        raise AssertionError("transient error should propagate")

    assert model.attempts == 1


def test_policy_retries_transient_errors_until_success() -> None:
    model = _FlakyModel(
        failures=2,
        retry=RetryPolicy(
            max_attempts=3,
            backoff_factor=0,
            retryable_exceptions=(_TransientError,),
        ),
    )

    out = model([{"role": "user", "content": "hi"}])

    assert out == "Final Answer: recovered"
    assert model.attempts == 3


def test_policy_stops_after_max_attempts() -> None:
    model = _FlakyModel(
        failures=99,
        retry=RetryPolicy(
            max_attempts=2,
            backoff_factor=0,
            retryable_exceptions=(_TransientError,),
        ),
    )

    try:
        model([{"role": "user", "content": "hi"}])
    except _TransientError:
        pass
    else:
        raise AssertionError("exhausted retries should re-raise")

    assert model.attempts == 2


def test_non_retryable_exceptions_propagate_immediately() -> None:
    class _BrokenModel(Model):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.attempts = 0

        def _call_api(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
            self.attempts += 1
            raise _PermanentError("bad request")

    model = _BrokenModel(
        retry=RetryPolicy(
            max_attempts=5,
            backoff_factor=0,
            retryable_exceptions=(_TransientError,),
        ),
    )

    try:
        model([{"role": "user", "content": "hi"}])
    except _PermanentError:
        pass
    else:
        raise AssertionError("non-retryable error should propagate")

    assert model.attempts == 1


def test_build_model_for_preset_accepts_retry() -> None:
    from qitos.models import build_model_for_preset

    policy = RetryPolicy(max_attempts=2, backoff_factor=0)
    llm = build_model_for_preset(
        family_id="qwen",
        model_name="Qwen/Qwen3-8B",
        api_key="k",
        base_url="https://example.invalid/v1",
        retry=policy,
    )
    assert llm.retry_policy is policy

    default = build_model_for_preset(
        family_id="qwen",
        model_name="Qwen/Qwen3-8B",
        api_key="k",
        base_url="https://example.invalid/v1",
    )
    assert default.retry_policy is None
