"""Tracing configuration: mode enum and redaction support."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict

from .models import SpanData


class TracingMode(str, Enum):
    """Controls the verbosity and behaviour of the tracing system.

    - ENABLED: full tracing with all span data.
    - ENABLED_WITHOUT_DATA: traces and spans are emitted, but sensitive
      payload fields are redacted.
    - DISABLED: no traces or spans are created; factories return NoOp
      sentinels.
    """

    ENABLED = "enabled"
    ENABLED_WITHOUT_DATA = "enabled_without_data"
    DISABLED = "disabled"


# Fields that should be replaced with "__redacted__" when running under
# ENABLED_WITHOUT_DATA mode.
_REDACTED_FIELDS = frozenset(
    {
        "tool_args",
        "input_content",
        "output_content",
        "model_response",
        "api_key",
        "authorization",
        "token",
        "secret",
        "password",
        "access_token",
        "refresh_token",
        "private_key",
        "credentials",
    }
)

_REDACTED_MARKER = "__redacted__"


class RedactingSpanData(SpanData):
    """Wrapper that redacts sensitive fields when *export()* is called.

    This is used internally by the provider when the tracing mode is
    ``ENABLED_WITHOUT_DATA``.  It delegates attribute access to the
    wrapped *span_data* object so that normal code paths continue to
    work, but the serialized representation hides secrets.
    """

    def __init__(self, span_data: Any) -> None:
        self._span_data = span_data

    # -- delegate attribute access -----------------------------------------

    def __getattr__(self, name: str) -> Any:
        return getattr(self._span_data, name)

    # -- export with redaction ---------------------------------------------

    def export(self) -> Dict[str, Any]:
        raw = self._span_data.export()
        return _redact_dict(raw)

    # -- properties that the tracing infrastructure reads directly ----------

    @property
    def type(self) -> str:  # noqa: A003 – matches SpanData.type
        return self._span_data.type


def _redact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of *data* with redacted fields replaced."""
    redacted: Dict[str, Any] = {}
    for key, value in data.items():
        if key in _REDACTED_FIELDS:
            redacted[key] = _REDACTED_MARKER
        elif isinstance(value, dict):
            redacted[key] = _redact_dict(value)
        elif isinstance(value, list):
            redacted[key] = [_redact_dict(v) if isinstance(v, dict) else v for v in value]
        else:
            redacted[key] = value
    return redacted
