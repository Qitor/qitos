"""Internal stream validation and resource ownership shared by adapters."""
from __future__ import annotations

import inspect
import json
from dataclasses import replace
from typing import Any

from .codec import ProviderFailure
from .provider import normalize_provider_failure
from ..core.request_view import RequestTarget


def failure(
    model: Any, error: BaseException, *, sent: bool = True,
    partial_text_characters: int = 0,
) -> ProviderFailure:
    normalized = normalize_provider_failure(
        error, target=RequestTarget.from_dict(model.qitos_request_target())
    )
    actual_sent = normalized.provider_request_sent if isinstance(error, ProviderFailure) else sent
    details = {**normalized.redacted_details, "transport_attempts": int(actual_sent)}
    if partial_text_characters:
        details["partial_text_characters"] = partial_text_characters
    return replace(normalized, provider_request_sent=actual_sent, redacted_details=details)


def protocol_failure(model: Any) -> ProviderFailure:
    target = model.qitos_request_target()
    return ProviderFailure(
        category="stream", message="Provider stream violated its terminal contract.",
        provider=target["provider"], api_mode=target["api_mode"],
        error_code="provider_stream_protocol_error", stage="stream",
        provider_request_sent=True,
    )


def refusal_failure(model: Any) -> ProviderFailure:
    target = model.qitos_request_target()
    return ProviderFailure(
        category="provider_refusal", message="Provider refused the request.",
        provider=target["provider"], api_mode=target["api_mode"],
        error_code="provider_refusal", stage="provider_rejection", provider_request_sent=True,
    )


def close_owned(resource: Any) -> None:
    close = getattr(resource, "close", None)
    if callable(close):
        close()


async def aclose_owned(resource: Any) -> None:
    close = getattr(resource, "aclose", None) or getattr(resource, "close", None)
    if callable(close):
        result = close()
        if inspect.isawaitable(result):
            await result


def validate_calls(model: Any, calls: Any, reason: str) -> None:
    if not calls:
        return
    if reason not in {"tool_calls", "function_call", "tool_use", "completed"}:
        raise protocol_failure(model)
    for call in calls:
        function = call.get("function") or {}
        try:
            arguments = json.loads(function.get("arguments", ""))
        except (ValueError, TypeError):
            raise protocol_failure(model) from None
        if not isinstance(arguments, dict) or not call.get("id") or not function.get("name"):
            raise protocol_failure(model)


class ChatStream:
    """One chat choice; delay success until trailing usage and EOF validate."""

    def __init__(self, model: Any):
        self.model = model
        self.reason: str | None = None
        self.usage: dict[str, Any] | None = None
        self.calls: dict[int, dict[str, Any]] = {}

    def feed(self, chunk: Any) -> str:
        usage = self.model._usage_from_response(chunk)
        if usage is not None:
            if self.usage is not None and self.usage != usage:
                raise protocol_failure(self.model)
            self.usage = usage
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            return ""
        choice = choices[0]
        delta = choice.delta
        if getattr(delta, "refusal", None):
            raise refusal_failure(self.model)
        text = getattr(delta, "content", None) or ""
        tools = getattr(delta, "tool_calls", None) or []
        reason = getattr(choice, "finish_reason", None)
        if self.reason is not None and (text or tools or reason not in {None, self.reason}):
            raise protocol_failure(self.model)
        for item in tools:
            index = getattr(item, "index", None)
            if not isinstance(index, int) or index < 0:
                raise protocol_failure(self.model)
            call = self.calls.setdefault(index, {
                "id": None, "type": "function", "function": {"name": "", "arguments": ""},
            })
            if getattr(item, "id", None):
                call["id"] = item.id
            function = getattr(item, "function", None)
            if function:
                if getattr(function, "name", None):
                    call["function"]["name"] += function.name
                call["function"]["arguments"] += getattr(function, "arguments", None) or ""
        if reason is not None:
            self.reason = str(reason)
        return str(text)

    def finish(self) -> Any:
        from .base import ModelStreamChunk

        if self.reason is None:
            raise protocol_failure(self.model)
        calls = [self.calls[key] for key in sorted(self.calls)]
        validate_calls(self.model, calls, self.reason)
        self.model._set_last_usage(self.usage)
        return ModelStreamChunk(
            text="", done=True, usage=self.usage, tool_calls=calls or None,
            event_metadata={"finish_reason": self.reason},
        )
