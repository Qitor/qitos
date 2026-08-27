"""Normalized model response container used by the Engine runtime."""

from __future__ import annotations

import dataclasses
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, cast


def _sanitize(value: Any) -> Any:
    if value is not None and dataclasses.is_dataclass(value):
        return {
            str(k): _sanitize(v)
            for k, v in asdict(cast(Any, value)).items()
        }
    if isinstance(value, dict):
        return {str(k): _sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _sanitize_native_item(value: Any) -> Any:
    """Sanitize provider items while omitting opaque reasoning continuation data."""
    if value is not None and dataclasses.is_dataclass(value):
        value = asdict(cast(Any, value))
    if isinstance(value, dict):
        return {
            str(key): _sanitize_native_item(item)
            for key, item in value.items()
            if str(key) != "encrypted_content"
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
            "usage": _sanitize(self.usage) if isinstance(self.usage, dict) else None,
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
        if self.reasoning_content:
            d["reasoning_content"] = self.reasoning_content
        if self.reasoning_fields:
            d["reasoning_fields"] = {
                str(key): str(value)
                for key, value in self.reasoning_fields.items()
                if isinstance(value, str) and value.strip()
            }
        if self.reasoning_source:
            d["reasoning_source"] = str(self.reasoning_source)
        return d


__all__ = ["ModelResponse"]
