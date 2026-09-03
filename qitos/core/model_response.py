"""Normalized model response container used by the Engine runtime."""

from __future__ import annotations

import dataclasses
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, cast

from .diagnostics import redact_diagnostic_value


_SECRET_USAGE_KEY = re.compile(
    r"(?:authorization|api[_-]?key|credential|password|secret|cookie|headers?|"
    r"access[_-]?token|refresh[_-]?token|private[_-]?key)",
    re.IGNORECASE,
)


def _sanitize(value: Any) -> Any:
    if value is not None and dataclasses.is_dataclass(value):
        return {
            str(k): _sanitize(v)
            for k, v in asdict(cast(Any, value)).items()
        }
    return redact_diagnostic_value(value)


def _sanitize_usage(value: Any, *, depth: int = 0) -> Any:
    """Preserve numeric usage facts without treating ``*_tokens`` as secrets."""

    if depth > 8:
        return "[redacted]"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else "[redacted]"
    if isinstance(value, str):
        return redact_diagnostic_value(value)
    if isinstance(value, Mapping):
        result: Dict[str, Any] = {}
        for raw_key, nested in list(value.items())[:64]:
            if not isinstance(raw_key, str):
                continue
            if _SECRET_USAGE_KEY.search(raw_key):
                result[f"[redacted_key_{len(result) + 1}]"] = "[redacted]"
                continue
            result[raw_key[:64]] = _sanitize_usage(nested, depth=depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [_sanitize_usage(item, depth=depth + 1) for item in value[:64]]
    return "[redacted]"


def _sanitize_native_item(value: Any) -> Any:
    """Sanitize provider items while omitting opaque reasoning continuation data."""
    if value is not None and dataclasses.is_dataclass(value):
        value = asdict(cast(Any, value))
    if isinstance(value, dict):
        if value.get("type") in {"reasoning", "thinking"}:
            safe = {
                key: value[key]
                for key in ("type", "id", "status")
                if key in value
            }
            safe["reasoning_payload_present"] = any(
                value.get(key) not in (None, "", [], {})
                for key in (
                    "content",
                    "encrypted_content",
                    "reasoning",
                    "signature",
                    "summary",
                    "text",
                    "thinking",
                    "thought_signature",
                )
            )
            return redact_diagnostic_value(safe)
        return {
            str(key): _sanitize_native_item(item)
            for key, item in value.items()
            if str(key)
            not in {
                "encrypted_content",
                "signature",
                "thought_signature",
            }
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_native_item(item) for item in value]
    return _sanitize(value)


@dataclass
class ModelResponse:
    text: str
    raw: Any = None
    usage: Optional[Dict[str, Any]] = None
    finish_reason: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    model_name: Optional[str] = None
    provider: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    native_items: Optional[List[Dict[str, Any]]] = None
    # ``reasoning_content`` is the compatibility-facing primary native
    # reasoning channel. OpenAI-compatible providers also commonly use the
    # ``reasoning`` field, preserved verbatim in ``reasoning_fields``.
    reasoning_content: Optional[str] = None
    reasoning_fields: Dict[str, str] = field(default_factory=dict)
    reasoning_source: Optional[str] = None

    def to_summary_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "text": str(self.text or ""),
            "usage": (
                _sanitize_usage(self.usage) if isinstance(self.usage, dict) else None
            ),
            "finish_reason": (
                str(self.finish_reason) if self.finish_reason is not None else None
            ),
            "tool_calls": (
                _sanitize(self.tool_calls)
                if isinstance(self.tool_calls, list)
                else None
            ),
            "model_name": str(self.model_name) if self.model_name is not None else None,
            "provider": str(self.provider) if self.provider is not None else None,
            "metadata": (
                _sanitize(self.metadata) if isinstance(self.metadata, dict) else {}
            ),
            "native_items": (
                _sanitize_native_item(self.native_items)
                if isinstance(self.native_items, list)
                else None
            ),
        }
        if self.reasoning_content or self.reasoning_fields:
            d["reasoning"] = {
                "present": True,
                "source": (
                    str(self.reasoning_source)
                    if self.reasoning_source is not None
                    else None
                ),
                "field_names": sorted(
                    str(key)
                    for key, value in self.reasoning_fields.items()
                    if isinstance(value, str) and value.strip()
                ),
            }
        return d


__all__ = ["ModelResponse"]
