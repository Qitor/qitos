"""LiteLLM model adapter."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Mapping, Optional

from .base import Model, ModelFactory
from .provider import LegacyMessageCodec


class LiteLLMChatCodec(LegacyMessageCodec):
    """Conservative meta-provider codec; backend-specific features stay off."""

    codec_id = "qitos.litellm.chat_completions"
    codec_version = "v1"


class LiteLLMModel(Model):
    """
    LiteLLM-native model adapter.

    Environment variables:
    - LITELLM_MODEL
    - LITELLM_API_KEY (optional)
    - LITELLM_API_BASE (optional)
    - LITELLM_API_VERSION (optional)
    - LITELLM_PROVIDER (optional)
    """

    qitos_provider_id = "litellm"
    qitos_transport_id = "litellm"
    qitos_api_mode = "chat_completions"
    qitos_capabilities_by_api_mode = {
        "chat_completions": {
            "api_style": "chat_completions",
            "supported_features": ("text",),
            "reasoning_modes": ("drop",),
            "multimodal_types": ("text",),
            "supports_native_tool_calls": False,
            "supports_parallel_tool_calls": False,
            "supports_tool_schemas": False,
            "supports_tool_choice": False,
            "supports_multimodal_input": False,
            "supports_reasoning_input": False,
            "supports_reasoning_output": False,
            "supports_continuation": False,
            "supports_stateless_replay": True,
            "supports_streaming": False,
            "supports_usage": True,
            "supports_cancellation": False,
            "supports_structured_output": False,
        }
    }

    def qitos_provider_codec(self) -> LiteLLMChatCodec:
        return LiteLLMChatCodec()

    def qitos_transport(self, payload: Mapping[str, Any]) -> Any:
        try:
            import litellm
        except ImportError as exc:
            from ._stream import failure

            raise failure(self, exc, sent=False) from None
        request_kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": list(payload.get("messages") or []),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "num_retries": 0,
        }
        if self.api_key:
            request_kwargs["api_key"] = self.api_key
        if self.api_base:
            request_kwargs["api_base"] = self.api_base
        if self.api_version:
            request_kwargs["api_version"] = self.api_version
        if self.custom_llm_provider:
            request_kwargs["custom_llm_provider"] = self.custom_llm_provider
        request_kwargs.update(dict(payload.get("options") or {}))
        response = litellm.completion(**request_kwargs)
        self._set_last_usage(self._usage_from_response(response))
        return response

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        api_version: Optional[str] = None,
        custom_llm_provider: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: int = 60,
        context_window: Optional[int] = None,
    ):
        super().__init__(
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            context_window=context_window,
        )
        self.api_key = api_key or os.getenv("LITELLM_API_KEY")
        self.api_base = api_base or os.getenv("LITELLM_API_BASE")
        self.api_version = api_version or os.getenv("LITELLM_API_VERSION")
        self.custom_llm_provider = custom_llm_provider or os.getenv("LITELLM_PROVIDER")
        self.timeout = timeout

    def _call_api(self, messages: List[Dict[str, Any]], **call_kwargs: Any) -> str:
        try:
            import litellm
        except ImportError as exc:
            raise self.qitos_normalize_failure(exc) from None

        request_kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "num_retries": 0,
        }
        if self.api_key:
            request_kwargs["api_key"] = self.api_key
        if self.api_base:
            request_kwargs["api_base"] = self.api_base
        if self.api_version:
            request_kwargs["api_version"] = self.api_version
        if self.custom_llm_provider:
            request_kwargs["custom_llm_provider"] = self.custom_llm_provider
        request_kwargs.update(call_kwargs)

        try:
            response = litellm.completion(**request_kwargs)
            self._set_last_usage(self._usage_from_response(response))
            return self._parse_response(response)
        except Exception as exc:
            raise self.qitos_normalize_failure(exc) from None

    def _parse_response(self, response: Any) -> str:
        choice = self._get_choice(response)
        if choice is None:
            return ""
        message = self._choice_message(choice)
        if not message:
            return ""
        tool_calls = self._message_value(message, "tool_calls")
        if tool_calls:
            return self._format_tool_calls(tool_calls)
        content = self._message_value(message, "content")
        return str(content or "").strip()

    def _usage_from_response(self, response: Any) -> Optional[Dict[str, Any]]:
        usage = getattr(response, "usage", None)
        if usage is None and isinstance(response, dict):
            usage = response.get("usage")
        if usage is None:
            return None
        if isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            total_tokens = usage.get("total_tokens")
        else:
            prompt_tokens = getattr(usage, "prompt_tokens", None)
            completion_tokens = getattr(usage, "completion_tokens", None)
            total_tokens = getattr(usage, "total_tokens", None)
        if prompt_tokens is None and completion_tokens is None and total_tokens is None:
            return None
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

    def _get_choice(self, response: Any) -> Any:
        if isinstance(response, dict):
            choices = response.get("choices") or []
            return choices[0] if choices else None
        choices = getattr(response, "choices", None) or []
        return choices[0] if choices else None

    def _choice_message(self, choice: Any) -> Any:
        if isinstance(choice, dict):
            return choice.get("message")
        return getattr(choice, "message", None)

    def _message_value(self, message: Any, key: str) -> Any:
        if isinstance(message, dict):
            return message.get(key)
        return getattr(message, key, None)

    def _format_tool_calls(self, tool_calls: Any) -> str:
        items = list(tool_calls or [])
        parts: List[str] = []
        for index, call in enumerate(items):
            function = (
                call.get("function")
                if isinstance(call, dict)
                else getattr(call, "function", None)
            )
            name = ""
            raw_args: Any = {}
            if isinstance(function, dict):
                name = str(function.get("name", ""))
                raw_args = function.get("arguments") or "{}"
            elif function is not None:
                name = str(getattr(function, "name", ""))
                raw_args = getattr(function, "arguments", "{}")
            try:
                args = (
                    json.loads(raw_args)
                    if isinstance(raw_args, str)
                    else dict(raw_args or {})
                )
            except Exception:
                args = {"raw_args": raw_args}
            prefix = f"Action {index + 1}: " if len(items) > 1 else "Action: "
            line = f"{prefix}{name}"
            if args:
                args_str = ", ".join(
                    f'{k}="{v}"' if isinstance(v, str) else f"{k}={v}"
                    for k, v in args.items()
                )
                line += f"({args_str})"
            parts.append(line)
        return "\n".join(parts)


ModelFactory.register("litellm")(LiteLLMModel)


__all__ = ["LiteLLMModel"]
