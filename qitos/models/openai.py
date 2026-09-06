"""
OpenAI Model Implementation

OpenAI API-based model calling implementation.
Supports environment variable configuration: OPENAI_API_KEY, OPENAI_BASE_URL
"""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Iterator, List, Mapping, Optional, cast

from ..core.conversation import (
    ArgumentParseStatus,
    AssistantContent,
    CallIdentity,
    ReasoningBlock,
    ToolCall,
)
from ..core.model_response import ModelResponse
from ..core.request_view import RequestView
from ..core.tool import RetryPolicy
from ..core.multimodal import (
    ContentBlock,
    content_to_text,
    ensure_data_url,
    file_to_data_url,
    has_nontext_content,
    normalize_content_block,
    normalize_messages,
)
from ._openai_responses import (
    _async_responses_completion,
    _async_responses_stream,
    _normalize_api_mode,
    _responses_completion,
    _responses_stream,
)
from .base import Model, ModelStreamChunk
from .codec import (
    CodecReport,
    ProviderCapabilities,
    ProviderFailure,
    _request_tool_options,
    report_for_request,
    validate_codec_result,
)
from .provider import (
    ContinuationResolution,
    LegacyMessageCodec,
    ProviderDecodedResponse,
    decode_openai_like_response,
    request_view_to_compat_messages,
)


GLM_TOKENIZER_ENV_VARS = ("QITOS_GLM_TOKENIZER_PATH", "GLM_TOKENIZER_PATH")


def _openai_client_options(model: Any) -> Dict[str, Any]:
    options: Dict[str, Any] = {
        "api_key": model.api_key,
        "base_url": model.base_url,
        "timeout": model.timeout,
        # Admission owns request accounting. Hidden SDK retries would issue
        # additional requests without another durable budget reservation.
        "max_retries": 0,
    }
    headers = dict(getattr(model, "default_headers", {}) or {})
    if headers:
        options["default_headers"] = headers
    return options


def _relocate_chat_template_kwargs(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Move provider-specific generation kwargs into ``extra_body``.

    The OpenAI Python SDK does not accept ``chat_template_kwargs`` as a
    top-level parameter.  vLLM-compatible serving endpoints expect it inside
    ``extra_body`` instead.  Calling code that merges ``default_request_kwargs``
    often places it at the top level, so we relocate it here.
    """
    result = dict(kwargs)
    extra_body = dict(result.pop("extra_body", None) or {})
    ctk = result.pop("chat_template_kwargs", None)
    if isinstance(ctk, dict) and ctk:
        extra_body["chat_template_kwargs"] = ctk
    # ``do_sample`` is accepted by vLLM/SGLang-style endpoints but not by the
    # OpenAI Python SDK's typed method signature. Passing it at top level made
    # the whole native-tool request fail with TypeError and silently fall back
    # to a schema-less text call. Preserve provider semantics through the SDK's
    # supported extra_body escape hatch.
    do_sample = result.pop("do_sample", None)
    if do_sample is not None:
        extra_body["do_sample"] = do_sample
    if extra_body:
        result["extra_body"] = extra_body
    return result


def _new_client(model: Any, *, asynchronous: bool = False) -> Any:
    from ._stream import failure

    try:
        import openai
        if isinstance(model, AzureOpenAIModel):
            return openai.AzureOpenAI(
                api_key=model.api_key, azure_endpoint=model.endpoint,
                api_version=model.api_version, timeout=model.timeout,
                max_retries=0,
                default_headers=model.default_headers or None,
            )
        factory = openai.AsyncOpenAI if asynchronous else openai.OpenAI
        return factory(**_openai_client_options(model))
    except Exception as exc:
        raise failure(model, exc, sent=False) from None


def _chat_stream_payload(model: Any, messages: List[Dict[str, Any]], options: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "model": model.model, "messages": _to_openai_messages(messages),
        "temperature": model.temperature, "max_tokens": model.max_tokens,
        "stream": True, "stream_options": {"include_usage": True},
    }
    payload.update(options)
    return payload


def _is_forced_tool_choice(tool_choice: Any) -> bool:
    if isinstance(tool_choice, str):
        return tool_choice.strip().lower() == "required"
    return isinstance(tool_choice, dict)


def _disable_thinking_for_forced_tool_choice(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    if not _is_forced_tool_choice(kwargs.get("tool_choice")):
        return kwargs
    result = dict(kwargs)
    if "enable_thinking" in result:
        result["enable_thinking"] = False
    if "thinking" in result:
        result["thinking"] = {"type": "disabled"}
    extra_body = result.get("extra_body")
    if isinstance(extra_body, dict):
        patched_extra = dict(extra_body)
        if "enable_thinking" in patched_extra:
            patched_extra["enable_thinking"] = False
        if "thinking" in patched_extra:
            patched_extra["thinking"] = {"type": "disabled"}
        result["extra_body"] = patched_extra
    return result


def _to_openai_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = normalize_messages(messages)
    out: List[Dict[str, Any]] = []
    for message in normalized:
        role = str(message.get("role") or "user").strip() or "user"
        content = message.get("content")
        payload: Dict[str, Any] = {"role": role}
        for key, value in message.items():
            if key in {"role", "content", "native_items"}:
                continue
            payload[key] = value
        if isinstance(content, list):
            if has_nontext_content(message):
                payload["content"] = _to_openai_content_blocks(content)
            else:
                text_blocks = [
                    str(normalize_content_block(block).get("text") or "")
                    for block in content
                    if str(normalize_content_block(block).get("type") or "text")
                    == "text"
                ]
                payload["content"] = "\n".join(part for part in text_blocks if part)
        elif content is None and role == "assistant" and payload.get("tool_calls"):
            payload["content"] = None
        else:
            payload["content"] = str(content or "")
        out.append(payload)
    return out


def _to_openai_content_blocks(content: List[Any]) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    for raw in content:
        block = normalize_content_block(raw)
        block_type = str(block.get("type") or "text")
        if block_type == "text":
            blocks.append({"type": "text", "text": str(block.get("text") or "")})
            continue
        detail = str(block.get("detail") or "").strip()
        if block_type == "image_url":
            image_url: Dict[str, Any] = {"url": str(block.get("url") or "")}
            if detail:
                image_url["detail"] = detail
            blocks.append({"type": "image_url", "image_url": image_url})
            continue
        if block_type == "image_base64":
            mime_type = str(block.get("mime_type") or "image/png")
            image_url = {"url": ensure_data_url(str(block.get("data") or ""), mime_type=mime_type)}
            if detail:
                image_url["detail"] = detail
            blocks.append({"type": "image_url", "image_url": image_url})
            continue
        if block_type == "image_file":
            path = str(block.get("path") or "")
            mime_type = str(block.get("mime_type") or "")
            image_url = {
                "url": file_to_data_url(path, mime_type=mime_type or None)
            }
            if detail:
                image_url["detail"] = detail
            blocks.append({"type": "image_url", "image_url": image_url})
            continue
        blocks.append({"type": "text", "text": str(block)})
    return blocks


def _is_glm_model_name(model: str) -> bool:
    normalized = str(model or "").strip().lower()
    return normalized.startswith("glm-") or normalized.startswith("zai-org/glm-")


def _glm_tokenizer_path() -> Optional[str]:
    for name in GLM_TOKENIZER_ENV_VARS:
        value = os.getenv(name, "").strip()
        if value and Path(value).exists():
            return value
    return None


@lru_cache(maxsize=4)
def _load_glm_tokenizer(path: str) -> Any:
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(
        path,
        trust_remote_code=True,
        local_files_only=True,
    )


def _tokenizer_count_result(value: Any) -> Optional[int]:
    if isinstance(value, int):
        return int(value)
    if isinstance(value, list):
        return len(value)
    getter = getattr(value, "get", None)
    if callable(getter):
        ids = getter("input_ids")
        if isinstance(ids, list):
            return len(ids)
    return None


def _normalize_messages_for_tokenizer(payload: List[Any]) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            messages.append({"role": "user", "content": str(item)})
            continue
        role = str(item.get("role") or "user").strip() or "user"
        content = content_to_text(item.get("content"))
        extras: Dict[str, Any] = {}
        for key in ("tool_calls", "tool_call_id", "name"):
            if key in item and item.get(key) not in (None, "", []):
                extras[key] = item.get(key)
        if extras:
            content = (
                content
                + "\n"
                + json.dumps(extras, ensure_ascii=False, sort_keys=True)
            ).strip()
        messages.append({"role": role, "content": content})
    return messages


class OpenAIChatCodec(LegacyMessageCodec):
    """Chat Completions codec; reasoning replay is loss-explicit."""

    _preserve_chat_reasoning = True
    codec_id = "qitos.openai.chat_completions"
    codec_version = "v1"


class OpenAIResponsesCodec(LegacyMessageCodec):
    """Responses codec preserving ordered native items and continuation."""

    codec_id = "qitos.openai.responses"
    codec_version = "v1"

    def encode(
        self,
        request: RequestView,
        *,
        capabilities: Optional[ProviderCapabilities] = None,
        transport: Optional[Any] = None,
        allow_loss: bool = False,
    ) -> tuple[Dict[str, Any], CodecReport]:
        resolved = capabilities or ProviderCapabilities.from_model(transport)
        messages, projected_losses = request_view_to_compat_messages(request)
        losses = list(projected_losses)
        reasoning = "not_present"
        if "assistant.reasoning" in losses:
            if request.continuation is not None:
                losses.remove("assistant.reasoning")
                reasoning = "native_item_continuation"
            else:
                reasoning = "dropped"
        options = _request_tool_options(request)
        report = report_for_request(
            request,
            resolved,
            codec_id=self.codec_id,
            codec_version=self.codec_version,
            reasoning=reasoning,
            continuation=(
                "resolver_required" if request.continuation else "not_requested"
            ),
            supported=request.capability_requirements,
            lossy_fields=losses,
        )
        return validate_codec_result(
            {"messages": messages, "options": options},
            report,
            allow_loss=allow_loss,
        )

    def apply_continuation(
        self,
        payload: Dict[str, Any],
        resolution: ContinuationResolution,
        *,
        request: RequestView,
        report: CodecReport,
    ) -> tuple[Dict[str, Any], CodecReport]:
        _ = request
        updated = dict(payload)
        options = dict(updated.get("options") or {})
        continuation = resolution.payload
        response_id = (
            continuation.get("response_id")
            if isinstance(continuation, dict)
            else continuation
        )
        if not isinstance(response_id, str) or not response_id.strip():
            from .codec import CodecCapabilityError

            raise CodecCapabilityError(
                "OpenAI Responses continuation must resolve to response_id"
            )
        options["previous_response_id"] = response_id
        updated["options"] = options
        return updated, CodecReport.from_dict(
            {**report.to_dict(), "continuation": "applied", "lossless": report.lossless}
        )

    def decode(
        self, response: Any, *, request: RequestView
    ) -> ProviderDecodedResponse:
        if not isinstance(response, ModelResponse) or not response.native_items:
            return decode_openai_like_response(response, request=request)
        provider_scope = f"{request.target.provider}:{request.target.api_mode}"
        attachment_id = f"continuation_attachment_{request.request_id}"
        parts: list[Any] = []
        continuation_items: list[Dict[str, Any]] = []
        batch_id = f"batch_{request.request_id}"
        for index, item in enumerate(response.native_items):
            if not isinstance(item, dict):
                continue
            kind = str(item.get("type") or "")
            if kind == "reasoning":
                summary_parts = []
                for summary in item.get("summary") or []:
                    if isinstance(summary, dict) and summary.get("text"):
                        summary_parts.append(str(summary["text"]))
                parts.append(
                    ReasoningBlock(
                        provider_scope=provider_scope,
                        reference_id=str(
                            item.get("id")
                            or f"reasoning_{request.request_id}_{index}"
                        ),
                        block_type="responses_reasoning",
                        summary="".join(summary_parts) or None,
                        attachment_id=attachment_id,
                        metadata={"status": item.get("status")},
                    )
                )
                continuation_items.append(dict(item))
                continue
            if kind == "message":
                for block in item.get("content") or []:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") in {"output_text", "text"}:
                        parts.append(
                            AssistantContent(
                                ContentBlock(
                                    type="text", text=str(block.get("text") or "")
                                )
                            )
                        )
                continue
            if kind == "function_call":
                raw_arguments = str(item.get("arguments") or "{}")
                parse_error: Optional[str]
                try:
                    parsed_value = json.loads(raw_arguments)
                except json.JSONDecodeError as exc:
                    parsed = None
                    parse_status = ArgumentParseStatus.MALFORMED_RAW
                    parse_error = exc.__class__.__name__
                else:
                    parsed = parsed_value if isinstance(parsed_value, dict) else None
                    parse_status = (
                        ArgumentParseStatus.PARSED
                        if parsed is not None
                        else ArgumentParseStatus.PARSED_INVALID
                    )
                    parse_error = None if parsed is not None else "arguments_not_object"
                parts.append(
                    ToolCall(
                        identity=CallIdentity(
                            provider_scope,
                            str(
                                item.get("call_id")
                                or f"call_{request.request_id}_{index}"
                            ),
                        ),
                        batch_id=batch_id,
                        name=str(item.get("name") or ""),
                        raw_arguments=raw_arguments,
                        parsed_arguments=parsed,
                        parse_status=parse_status,
                        parse_error=parse_error,
                        metadata={
                            "response_item_id": item.get("id"),
                            "status": item.get("status"),
                        },
                    )
                )
        if not parts:
            return decode_openai_like_response(response, request=request)
        response_id = response.metadata.get("id")
        continuation_payload = (
            {"response_id": response_id, "native_reasoning": continuation_items}
            if isinstance(response_id, str) and response_id
            else None
        )
        return ProviderDecodedResponse(
            parts=tuple(parts),
            usage=response.usage,
            finish_reason=response.finish_reason,
            model_name=response.model_name,
            provider_metadata={
                key: value
                for key, value in response.metadata.items()
                if key in {"id", "status", "previous_response_id", "api_mode"}
            },
            continuation_payload=continuation_payload,
            continuation_attachment_id=(
                attachment_id if continuation_payload is not None else None
            ),
        )


class OpenAIModel(Model):
    """
    OpenAI model calling implementation

    Environment variable configuration:
    - OPENAI_API_KEY: OpenAI API key
    - OPENAI_BASE_URL: OpenAI API base URL (optional, default https://api.openai.com/v1)

    Output format:
    - If model returns tool_calls: Convert to "Action: tool_name(args)" format
    - If model returns content: Return directly
    - Supports function calling format

    Example:
        llm = OpenAIModel(model="gpt-4")
        result = llm([{"role": "user", "content": "Help me search for Python tutorials"}])
        # Returns: "Action: search(query='Python tutorials')"
    """

    qitos_provider_id = "openai"
    qitos_transport_id = "openai"
    qitos_api_mode = "chat_completions"
    qitos_capabilities_by_api_mode = {
        "chat_completions": {
            "api_style": "chat_completions",
            "supported_features": (
                "text", "multimodal", "tool_calls", "tool_results", "tool_schemas",
                "parallel_tool_calls", "artifact_references",
                "streaming", "ordered_interleaving", "provider_metadata",
            ),
            "reasoning_modes": ("drop",),
            "multimodal_types": ("text", "image_url", "image_base64", "image_file"),
            "supports_native_tool_calls": True,
            "supports_parallel_tool_calls": True,
            "supports_tool_schemas": True,
            "supports_tool_choice": True,
            "supports_multimodal_input": True,
            "supports_reasoning_input": False,
            "supports_reasoning_output": False,
            "supports_continuation": False,
            "supports_stateless_replay": True,
            "supports_streaming": True,
            "supports_usage": True,
            "supports_cancellation": False,
            "supports_structured_output": True,
        },
        "responses": {
            "api_style": "responses",
            "supported_features": (
                "text", "multimodal", "tool_calls", "tool_results", "tool_schemas",
                "parallel_tool_calls", "artifact_references", "reasoning", "continuation",
                "streaming", "ordered_interleaving", "provider_metadata",
            ),
            "reasoning_modes": ("preserve_if_supported", "native_item_continuation", "drop"),
            "multimodal_types": ("text", "image_url", "image_base64", "image_file"),
            "supports_native_tool_calls": True,
            "supports_parallel_tool_calls": True,
            "supports_tool_schemas": True,
            "supports_tool_choice": True,
            "supports_multimodal_input": True,
            "supports_reasoning_input": True,
            "supports_reasoning_output": True,
            "supports_continuation": True,
            "supports_stateless_replay": True,
            "supports_streaming": True,
            "supports_usage": True,
            "supports_cancellation": False,
            "supports_structured_output": True,
        },
    }

    def qitos_provider_codec(self) -> Any:
        if str(getattr(self, "api_mode", self.qitos_api_mode)) == "responses":
            return OpenAIResponsesCodec()
        return OpenAIChatCodec()

    def __init__(
        self,
        model: str = "gpt-4",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: int = 60,
        context_window: Optional[int] = None,
        default_request_kwargs: Optional[Dict[str, Any]] = None,
        default_headers: Optional[Dict[str, str]] = None,
        api_mode: str = "chat_completions",
    ):
        """
        Initialize OpenAI model

        Args:
            model: Model name, default gpt-4
            api_key: API key, default read from environment variable
            base_url: API base URL, default read from environment variable
            system_prompt: System prompt
            temperature: Temperature parameter (0.0-1.0)
            max_tokens: Maximum output token count
            timeout: Request timeout (seconds)
            context_window: Total model context window
            default_request_kwargs: Extra kwargs merged into every API call
            default_headers: Extra HTTP headers sent by the OpenAI client
            api_mode: OpenAI transport, ``chat_completions`` or ``responses``
        """
        super().__init__(
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            context_window=context_window,
        )

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        )
        self.timeout = timeout
        self.default_request_kwargs = default_request_kwargs or {}
        self.default_headers = dict(default_headers or {})
        self.api_mode = _normalize_api_mode(api_mode)

        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY not set. Please set environment variable or pass api_key parameter."
            )

    def _call_api(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        response = self.call_raw(messages, **kwargs)
        if isinstance(response, ModelResponse):
            return response.text
        return self._parse_response(response)

    def _parse_response(self, response) -> str:
        """
        Parse OpenAI response and convert to target format

        Args:
            response: OpenAI API response object

        Returns:
            Text in parse_tool_calls compatible format
        """
        choice = response.choices[0]
        message = choice.message

        # Prioritize processing tool_calls
        if message.tool_calls:
            return self._format_tool_calls(message.tool_calls)

        # Return content
        if message.content:
            return message.content.strip()

        return ""

    def _chat_completion(
        self, client: Any, messages: List[Dict[str, Any]], **kwargs: Any
    ) -> Any:
        safe_kwargs = _relocate_chat_template_kwargs({**self.default_request_kwargs, **kwargs})
        response = client.chat.completions.create(
            model=self.model,
            messages=cast(Any, _to_openai_messages(messages)),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            **safe_kwargs,
        )
        self._set_last_usage(self._usage_from_response(response))
        return response

    def call_raw(self, messages: List[Dict[str, Any]], **kwargs: Any) -> Any:
        from ._stream import close_owned

        self._last_usage = None
        client = _new_client(self, asynchronous=False)
        try:
            if self.api_mode == "responses":
                return _responses_completion(
                    self, client, messages, provider=str(self.qitos_provider_id),
                    **_relocate_chat_template_kwargs({**self.default_request_kwargs, **kwargs}),
                )
            return self._chat_completion(client, messages, **kwargs)
        finally:
            close_owned(client, model=self)

    def stream(self, messages: List[Dict[str, Any]], **kwargs: Any) -> Iterator[ModelStreamChunk]:
        """Stream with explicit terminal validation and owned-resource cleanup."""
        from ._stream import ChatStream, close_owned, failure

        self._last_usage = None
        client = response = None
        sent = False
        partial_text_characters = 0
        state = None
        try:
            client = _new_client(self)
            safe = _relocate_chat_template_kwargs({**self.default_request_kwargs, **kwargs})
            sent = True
            if self.api_mode == "responses":
                nested = _responses_stream(
                    self, client, messages, provider=str(self.qitos_provider_id), **safe
                )
                try:
                    for chunk in nested:
                        partial_text_characters += len(chunk.text)
                        yield chunk
                finally:
                    close_owned(nested)
                return
            sent = False
            payload = _chat_stream_payload(self, messages, safe)
            sent = True
            response = client.chat.completions.create(**payload)
            state = ChatStream(self)
            for raw in response:
                text = state.feed(raw)
                if text:
                    partial_text_characters += len(text)
                    yield ModelStreamChunk(text=text)
            yield state.finish()
        except Exception as exc:
            raise failure(self, exc, sent=sent,
                          partial_text_characters=partial_text_characters, stream_state=state) from None
        finally:
            try:
                close_owned(response, client, model=self)
            except ProviderFailure as exc:
                raise failure(self, exc, sent=sent,
                              partial_text_characters=partial_text_characters, stream_state=state) from None

    def _usage_from_response(self, response: Any) -> Optional[Dict[str, Any]]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)
        if prompt_tokens is None and isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            total_tokens = usage.get("total_tokens")
        if prompt_tokens is None and completion_tokens is None and total_tokens is None:
            return None
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

    def _format_tool_calls(self, tool_calls) -> str:
        """
        Convert OpenAI tool_calls format to parse_tool_calls compatible format

        Args:
            tool_calls: OpenAI tool_calls list

        Returns:
            Formatted tool call text
        """
        parts = []

        for i, call in enumerate(tool_calls):
            function = call.function
            name = function.name
            args = function.arguments

            try:
                args_dict = json.loads(args) if args else {}
            except json.JSONDecodeError:
                args_dict = {"raw_args": args}

            if len(tool_calls) > 1:
                parts.append(f"Action {i + 1}: {name}")
            else:
                parts.append(f"Action: {name}")

            if args_dict:
                args_str = ", ".join(
                    f'{k}="{v}"' if isinstance(v, str) else f"{k}={v}"
                    for k, v in args_dict.items()
                )
                parts[-1] += f"({args_str})"

        return "\n".join(parts)

    def supports_tool_schema_delivery(
        self, delivery: str, protocol: Any = None
    ) -> bool:
        _ = protocol
        return str(delivery or "prompt_injection") in {
            "prompt_injection",
            "api_parameter",
            "hybrid",
        }

    def build_tool_schema_request_options(
        self,
        tool_schema_payload: Optional[List[Dict[str, Any]]],
        *,
        protocol: Any = None,
        delivery: str = "prompt_injection",
    ) -> Dict[str, Any]:
        _ = protocol
        if str(delivery or "prompt_injection") not in {"api_parameter", "hybrid"}:
            return {}
        if not tool_schema_payload:
            return {}
        return {"tools": tool_schema_payload}

    def supports_multimodal_input(self) -> bool:
        return True


class OpenAICompatibleModel(Model):
    """
    OpenAI compatible interface model

    Supports any service compatible with OpenAI API format, such as:
    - Azure OpenAI
    - Anthropic (via compatible endpoints)
    - LM Studio
    - LocalAI
    - Tongyi Qianwen
    - Zhipu AI

    Example:
        llm = OpenAICompatibleModel(
            model="qwen-turbo",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
    """

    qitos_provider_id = "openai-compatible"
    qitos_transport_id = "openai"
    qitos_api_mode = "chat_completions"
    qitos_capabilities_by_api_mode = OpenAIModel.qitos_capabilities_by_api_mode

    def qitos_provider_codec(self) -> Any:
        if self.api_mode == "responses":
            return OpenAIResponsesCodec()
        return OpenAIChatCodec()

    def __init__(
        self,
        model: str = "default",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: int = 60,
        context_window: Optional[int] = None,
        default_request_kwargs: Optional[Dict[str, Any]] = None,
        default_headers: Optional[Dict[str, str]] = None,
        api_mode: str = "chat_completions",
        retry: Optional["RetryPolicy"] = None,
    ):
        """
        Initialize compatible model

        Args:
            model: Model name
            api_key: API key
            base_url: API base URL
            system_prompt: System prompt
            temperature: Temperature parameter
            max_tokens: Maximum output token count
            timeout: Request timeout
            context_window: Total model context window
            default_request_kwargs: Extra kwargs merged into every API call
                (e.g. {"chat_template_kwargs": {"thinking": True}})
            default_headers: Extra HTTP headers sent by the OpenAI client
            api_mode: OpenAI transport, ``chat_completions`` or ``responses``
            retry: Optional explicit RetryPolicy for transient provider
                errors (default: no model-layer retries)
        """
        super().__init__(
            model=model,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            context_window=context_window,
            retry=retry,
        )

        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or "dummy-key"
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "")
        self.timeout = timeout
        self.default_request_kwargs = default_request_kwargs or {}
        self.default_headers = dict(default_headers or {})
        self.api_mode = _normalize_api_mode(api_mode)

        if not self.base_url:
            raise ValueError(
                "OPENAI_BASE_URL not set. Please set environment variable or pass base_url parameter."
            )

    def count_tokens(self, messages_or_text: Any) -> Optional[int]:
        if self._should_use_glm_tokenizer():
            value = self._count_tokens_with_glm_tokenizer(messages_or_text)
            if isinstance(value, int) and value >= 0:
                return value
        return super().count_tokens(messages_or_text)

    def _should_use_glm_tokenizer(self) -> bool:
        metadata = dict(getattr(self, "qitos_harness_metadata", {}) or {})
        if str(metadata.get("family_preset") or "").strip().lower() == "glm":
            return True
        return _is_glm_model_name(self.model)

    def _count_tokens_with_glm_tokenizer(self, payload: Any) -> Optional[int]:
        path = _glm_tokenizer_path()
        if not path:
            return None
        try:
            tokenizer = _load_glm_tokenizer(path)
        except Exception:
            return None

        try:
            if isinstance(payload, list):
                messages = _normalize_messages_for_tokenizer(payload)
                encoded = tokenizer.apply_chat_template(
                    messages,
                    tokenize=True,
                    add_generation_prompt=False,
                )
                return _tokenizer_count_result(encoded)
            text = self._stringify_token_payload(payload)
            encoded = tokenizer.encode(text, add_special_tokens=False)
            return _tokenizer_count_result(encoded)
        except Exception:
            return None

    def _call_api(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        response = self.call_raw(messages, **kwargs)
        if isinstance(response, ModelResponse):
            return response.text
        return self._parse_response(response)

    def _parse_response(self, response) -> str:
        """
        Parse response
        """
        choice = response.choices[0]
        message = choice.message

        if message.tool_calls:
            return self._format_tool_calls(message.tool_calls)

        if message.content:
            return message.content.strip()

        return ""

    def supports_tool_schema_delivery(
        self, delivery: str, protocol: Any = None
    ) -> bool:
        _ = protocol
        return str(delivery or "prompt_injection") in {
            "prompt_injection",
            "api_parameter",
            "hybrid",
        }

    def build_tool_schema_request_options(
        self,
        tool_schema_payload: Optional[List[Dict[str, Any]]],
        *,
        protocol: Any = None,
        delivery: str = "prompt_injection",
    ) -> Dict[str, Any]:
        _ = protocol
        if str(delivery or "prompt_injection") not in {"api_parameter", "hybrid"}:
            return {}
        if not tool_schema_payload:
            return {}
        return {"tools": tool_schema_payload}

    def supports_multimodal_input(self) -> bool:
        return True

    def _format_tool_calls(self, tool_calls) -> str:
        """
        Format tool calls
        """
        import json

        parts = []

        for i, call in enumerate(tool_calls):
            function = call.function
            name = function.name
            args = function.arguments or "{}"

            try:
                args_dict = json.loads(args)
            except json.JSONDecodeError:
                args_dict = {"raw": args}

            if len(tool_calls) > 1:
                parts.append(f"Action {i + 1}: {name}")
            else:
                parts.append(f"Action: {name}")

            if args_dict:
                args_str = ", ".join(
                    f'{k}="{v}"' if isinstance(v, str) else f"{k}={v}"
                    for k, v in args_dict.items()
                )
                parts[-1] += f"({args_str})"

        return "\n".join(parts)

    def _chat_completion(
        self, client: Any, messages: List[Dict[str, Any]], **kwargs: Any
    ) -> Any:
        safe_kwargs = _disable_thinking_for_forced_tool_choice(
            _relocate_chat_template_kwargs({**self.default_request_kwargs, **kwargs})
        )
        response = client.chat.completions.create(
            model=self.model,
            messages=cast(Any, _to_openai_messages(messages)),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            **safe_kwargs,
        )
        self._set_last_usage(self._usage_from_response(response))
        return response

    def call_raw(self, messages: List[Dict[str, Any]], **kwargs: Any) -> Any:
        from ._stream import close_owned

        self._last_usage = None
        client = _new_client(self, asynchronous=False)
        try:
            if self.api_mode == "responses":
                return _responses_completion(
                    self, client, messages, provider=str(self.qitos_provider_id),
                    **_relocate_chat_template_kwargs({**self.default_request_kwargs, **kwargs}),
                )
            return self._chat_completion(client, messages, **kwargs)
        finally:
            close_owned(client, model=self)

    def _usage_from_response(self, response: Any) -> Optional[Dict[str, Any]]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)
        if prompt_tokens is None and isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            total_tokens = usage.get("total_tokens")
        if prompt_tokens is None and completion_tokens is None and total_tokens is None:
            return None
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

    def stream(self, messages: List[Dict[str, Any]], **kwargs: Any) -> Iterator[ModelStreamChunk]:
        """Stream with explicit terminal validation and owned-resource cleanup."""
        from ._stream import ChatStream, close_owned, failure

        self._last_usage = None
        client = response = None
        sent = False
        partial_text_characters = 0
        state = None
        try:
            client = _new_client(self)
            safe = _relocate_chat_template_kwargs({**self.default_request_kwargs, **kwargs})
            sent = True
            if self.api_mode == "responses":
                nested = _responses_stream(
                    self, client, messages, provider=str(self.qitos_provider_id), **safe
                )
                try:
                    for chunk in nested:
                        partial_text_characters += len(chunk.text)
                        yield chunk
                finally:
                    close_owned(nested)
                return
            sent = False
            payload = _chat_stream_payload(self, messages, safe)
            sent = True
            response = client.chat.completions.create(**payload)
            state = ChatStream(self)
            for raw in response:
                text = state.feed(raw)
                if text:
                    partial_text_characters += len(text)
                    yield ModelStreamChunk(text=text)
            yield state.finish()
        except Exception as exc:
            raise failure(self, exc, sent=sent,
                          partial_text_characters=partial_text_characters, stream_state=state) from None
        finally:
            try:
                close_owned(response, client, model=self)
            except ProviderFailure as exc:
                raise failure(self, exc, sent=sent,
                              partial_text_characters=partial_text_characters, stream_state=state) from None


class AzureOpenAIModel(OpenAICompatibleModel):
    """
    Azure OpenAI model implementation

    Specifically optimized for Azure OpenAI service

    Environment variable configuration:
    - AZURE_OPENAI_API_KEY: Azure API key
    - AZURE_OPENAI_ENDPOINT: Azure endpoint URL
    - AZURE_OPENAI_DEPLOYMENT: Deployment name
    - AZURE_OPENAI_API_VERSION: API version (default 2024-02-15-preview)

    Example:
        llm = AzureOpenAIModel(
            deployment="gpt-4",
            api_version="2024-02-15-preview"
        )
    """

    qitos_provider_id = "azure-openai"

    def qitos_provider_capabilities(self) -> Dict[str, Any]:
        capabilities = super().qitos_provider_capabilities()
        capabilities["supported_features"] = tuple(
            feature
            for feature in capabilities["supported_features"]
            if feature != "streaming"
        )
        return capabilities

    def qitos_transport(self, payload: Mapping[str, Any]) -> Any:
        return self.call_raw(list(payload.get("messages") or []), **dict(payload.get("options") or {}))

    def __init__(
        self,
        deployment: Optional[str] = None,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        api_version: str = "2024-02-15-preview",
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        timeout: int = 60,
        context_window: Optional[int] = None,
    ):
        """
        Initialize Azure OpenAI model

        Args:
            deployment: Deployment name (used as model)
            api_key: API key, default read from environment variable
            endpoint: Endpoint URL, default read from environment variable
            api_version: API version
            system_prompt: System prompt
            temperature: Temperature parameter
            max_tokens: Maximum output token count
            timeout: Request timeout
            context_window: Total model context window
        """
        api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY")
        endpoint = endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")

        if not endpoint:
            raise ValueError(
                "AZURE_OPENAI_ENDPOINT not set. Please set environment variable or pass endpoint parameter."
            )

        base_url = (
            f"{endpoint.rstrip('/')}/openai/deployments/{deployment or 'default'}"
        )

        super().__init__(
            model=deployment or "azure",
            api_key=api_key,
            base_url=base_url,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            context_window=context_window,
        )

        self.api_version = api_version
        self.deployment = deployment
        self.endpoint = endpoint

    def _call_api(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        response = self.call_raw(messages, **kwargs)
        if isinstance(response, ModelResponse):
            return response.text
        return self._parse_response(response)


class AsyncOpenAICompatibleModel(OpenAICompatibleModel):
    """
    Async version of OpenAICompatibleModel using openai.AsyncOpenAI.

    Supports any service compatible with the OpenAI API format.
    Use ``await model.acall(messages)`` for non-blocking calls.

    Example::

        llm = AsyncOpenAICompatibleModel(
            model="qwen-turbo",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        result = await llm.acall([{"role": "user", "content": "Hello"}])
    """

    async def _acall_api(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        response = await self.acall_raw(messages, **kwargs)
        if isinstance(response, ModelResponse):
            return response.text
        return self._parse_response(response)

    async def _achat_completion(
        self, client: Any, messages: List[Dict[str, Any]], **kwargs: Any
    ) -> Any:
        safe_kwargs = _disable_thinking_for_forced_tool_choice(
            _relocate_chat_template_kwargs({**self.default_request_kwargs, **kwargs})
        )
        response = await client.chat.completions.create(
            model=self.model,
            messages=cast(Any, _to_openai_messages(messages)),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            **safe_kwargs,
        )
        self._set_last_usage(self._usage_from_response(response))
        return response

    async def acall_raw(self, messages: List[Dict[str, Any]], **kwargs: Any) -> Any:
        from ._stream import aclose_owned

        self._last_usage = None
        client = _new_client(self, asynchronous=True)
        try:
            if self.api_mode == "responses":
                return await _async_responses_completion(
                    self, client, messages, provider=str(self.qitos_provider_id),
                    **_relocate_chat_template_kwargs({**self.default_request_kwargs, **kwargs}),
                )
            return await self._achat_completion(client, messages, **kwargs)
        finally:
            await aclose_owned(client, model=self)

    async def astream(self, messages: List[Dict[str, Any]], **kwargs: Any) -> AsyncIterator[ModelStreamChunk]:
        """Stream with explicit terminal validation and owned-resource cleanup."""
        from ._stream import ChatStream, aclose_owned, failure

        self._last_usage = None
        client = response = nested = None
        sent = False
        partial_text_characters = 0
        state = None
        try:
            client = _new_client(self, asynchronous=True)
            safe = _relocate_chat_template_kwargs({**self.default_request_kwargs, **kwargs})
            sent = True
            if self.api_mode == "responses":
                nested = _async_responses_stream(
                    self, client, messages, provider=str(self.qitos_provider_id), **safe
                )
                async for chunk in nested:
                    partial_text_characters += len(chunk.text)
                    yield chunk
                return
            sent = False
            payload = _chat_stream_payload(self, messages, safe)
            sent = True
            response = await client.chat.completions.create(**payload)
            state = ChatStream(self)
            async for raw in response:
                text = state.feed(raw)
                if text:
                    partial_text_characters += len(text)
                    yield ModelStreamChunk(text=text)
            yield state.finish()
        except Exception as exc:
            raise failure(self, exc, sent=sent,
                          partial_text_characters=partial_text_characters, stream_state=state) from None
        finally:
            try:
                await aclose_owned(nested, response, client, model=self)
            except ProviderFailure as exc:
                raise failure(self, exc, sent=sent,
                              partial_text_characters=partial_text_characters, stream_state=state) from None


class AsyncOpenAIModel(OpenAIModel):
    """
    Async version of OpenAIModel using openai.AsyncOpenAI.

    Example::

        llm = AsyncOpenAIModel(model="gpt-4")
        result = await llm.acall([{"role": "user", "content": "Hello"}])
    """

    async def _acall_api(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        response = await self.acall_raw(messages, **kwargs)
        if isinstance(response, ModelResponse):
            return response.text
        return self._parse_response(response)

    async def _achat_completion(
        self, client: Any, messages: List[Dict[str, Any]], **kwargs: Any
    ) -> Any:
        safe_kwargs = _relocate_chat_template_kwargs({**self.default_request_kwargs, **kwargs})
        response = await client.chat.completions.create(
            model=self.model,
            messages=cast(Any, _to_openai_messages(messages)),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            **safe_kwargs,
        )
        self._set_last_usage(self._usage_from_response(response))
        return response

    async def acall_raw(self, messages: List[Dict[str, Any]], **kwargs: Any) -> Any:
        from ._stream import aclose_owned

        self._last_usage = None
        client = _new_client(self, asynchronous=True)
        try:
            if self.api_mode == "responses":
                return await _async_responses_completion(
                    self, client, messages, provider=str(self.qitos_provider_id),
                    **_relocate_chat_template_kwargs({**self.default_request_kwargs, **kwargs}),
                )
            return await self._achat_completion(client, messages, **kwargs)
        finally:
            await aclose_owned(client, model=self)

    async def astream(self, messages: List[Dict[str, Any]], **kwargs: Any) -> AsyncIterator[ModelStreamChunk]:
        """Stream with explicit terminal validation and owned-resource cleanup."""
        from ._stream import ChatStream, aclose_owned, failure

        self._last_usage = None
        client = response = nested = None
        sent = False
        partial_text_characters = 0
        state = None
        try:
            client = _new_client(self, asynchronous=True)
            safe = _relocate_chat_template_kwargs({**self.default_request_kwargs, **kwargs})
            sent = True
            if self.api_mode == "responses":
                nested = _async_responses_stream(
                    self, client, messages, provider=str(self.qitos_provider_id), **safe
                )
                async for chunk in nested:
                    partial_text_characters += len(chunk.text)
                    yield chunk
                return
            sent = False
            payload = _chat_stream_payload(self, messages, safe)
            sent = True
            response = await client.chat.completions.create(**payload)
            state = ChatStream(self)
            async for raw in response:
                text = state.feed(raw)
                if text:
                    partial_text_characters += len(text)
                    yield ModelStreamChunk(text=text)
            yield state.finish()
        except Exception as exc:
            raise failure(self, exc, sent=sent,
                          partial_text_characters=partial_text_characters, stream_state=state) from None
        finally:
            try:
                await aclose_owned(nested, response, client, model=self)
            except ProviderFailure as exc:
                raise failure(self, exc, sent=sent,
                              partial_text_characters=partial_text_characters, stream_state=state) from None


# Register to factory
from .base import ModelFactory

ModelFactory.register("openai")(OpenAIModel)
ModelFactory.register("azure")(AzureOpenAIModel)
ModelFactory.register("openai-compatible")(OpenAICompatibleModel)
ModelFactory.register("async-openai")(AsyncOpenAIModel)
ModelFactory.register("async-openai-compatible")(AsyncOpenAICompatibleModel)
