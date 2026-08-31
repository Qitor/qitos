"""
Native Anthropic Messages API model implementation.

This adapter talks to Anthropic's `/v1/messages` endpoint directly instead of
going through an OpenAI-compatible proxy.
"""

from __future__ import annotations

import os
import json
from typing import Any, Dict, Iterator, List, Mapping, Optional

import requests

from .base import Model, ModelFactory, ModelStreamChunk
from ..core.conversation import (
    ArgumentParseStatus,
    AssistantContent,
    CallIdentity,
    ReasoningBlock,
    ToolCall,
)
from ..core.multimodal import ContentBlock
from ..core.request_view import RequestView
from .codec import (
    CodecCapabilityError,
    CodecReport,
    ProviderCapabilities,
    report_for_request,
    validate_codec_result,
)
from .provider import (
    ContinuationResolution,
    LegacyMessageCodec,
    ProviderDecodedResponse,
)


class AnthropicMessagesCodec(LegacyMessageCodec):
    codec_id = "qitos.anthropic.messages"
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
        system_parts: list[str] = []
        messages: list[Dict[str, Any]] = []
        losses: list[str] = []
        for instruction in request.instructions:
            content = str(instruction.get("content") or "")
            if instruction.get("role") in {"system", "developer"}:
                system_parts.append(content)
            else:
                messages.append({"role": "user", "content": content})
        for contribution in request.context_contributions:
            content = json.dumps(
                contribution.get("content"), ensure_ascii=False, sort_keys=True
            )
            placement = contribution.get("requested_placement")
            if placement in {"system", "developer"}:
                system_parts.append(content)
            else:
                messages.append({"role": "user", "content": content})
        for item in request.selected_items:
            kind = item.get("kind")
            if kind in {"user", "steering"}:
                blocks: list[Dict[str, Any]] = []
                for block in item.get("content") or []:
                    block_type = block.get("type")
                    if block_type == "text":
                        blocks.append({"type": "text", "text": block.get("text", "")})
                    elif block_type == "image_base64":
                        blocks.append(
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": block.get("mime_type", "image/png"),
                                    "data": block.get("data", ""),
                                },
                            }
                        )
                    else:
                        losses.append(f"multimodal.{block_type}")
                messages.append({"role": "user", "content": blocks})
            elif kind == "assistant":
                blocks = []
                for part in item.get("parts") or []:
                    part_kind = part.get("kind")
                    if part_kind == "content":
                        block = part.get("block") or {}
                        if block.get("type") == "text":
                            blocks.append({"type": "text", "text": block.get("text", "")})
                        else:
                            losses.append(
                                f"assistant.multimodal.{block.get('type')}"
                            )
                    elif part_kind in {"reasoning_reference", "reasoning_block"}:
                        if request.continuation is None:
                            losses.append("assistant.reasoning")
                    elif part_kind == "tool_call":
                        parsed = part.get("parsed_arguments")
                        if not isinstance(parsed, dict):
                            raise CodecCapabilityError(
                                "Anthropic tool_use requires parsed object arguments"
                            )
                        blocks.append(
                            {
                                "type": "tool_use",
                                "id": part.get("call_id"),
                                "name": part.get("name"),
                                "input": parsed,
                            }
                        )
                messages.append({"role": "assistant", "content": blocks})
            elif kind == "tool_result":
                result = item.get("result") or {}
                output = result.get("model_output")
                if output is None:
                    output = result.get("error") or ""
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": item.get("call_id"),
                                "content": (
                                    output
                                    if isinstance(output, str)
                                    else json.dumps(output, ensure_ascii=False)
                                ),
                                "is_error": result.get("status") != "success",
                            }
                        ],
                    }
                )
        tools = []
        for schema in request.tool_schemas:
            function = schema.get("function") if schema.get("type") == "function" else schema
            if not isinstance(function, dict) or not function.get("name"):
                raise CodecCapabilityError("Anthropic tool schema is malformed")
            tools.append(
                {
                    "name": function.get("name"),
                    "description": function.get("description", ""),
                    "input_schema": function.get(
                        "parameters", {"type": "object", "properties": {}}
                    ),
                }
            )
        report = report_for_request(
            request,
            resolved,
            codec_id=self.codec_id,
            codec_version=self.codec_version,
            reasoning=(
                "signed_block_replay"
                if request.continuation is not None
                else ("dropped" if "assistant.reasoning" in losses else "not_present")
            ),
            continuation=(
                "resolver_required" if request.continuation else "not_requested"
            ),
            supported=request.capability_requirements,
            multimodal_conversion=("image_base64->anthropic.image",),
            tool_schema_conversion=("function.parameters->input_schema",),
            lossy_fields=losses,
        )
        return validate_codec_result(
            {
                "system": "\n\n".join(part for part in system_parts if part),
                "messages": messages,
                "tools": tools,
            },
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
        value = resolution.payload
        blocks = value.get("thinking_blocks") if isinstance(value, dict) else None
        if not isinstance(blocks, list):
            raise CodecCapabilityError(
                "Anthropic continuation must resolve to thinking_blocks"
            )
        updated = dict(payload)
        messages = [dict(message) for message in updated.get("messages") or []]
        target_index = next(
            (
                index
                for index in range(len(messages) - 1, -1, -1)
                if messages[index].get("role") == "assistant"
            ),
            None,
        )
        if target_index is None:
            raise CodecCapabilityError(
                "Anthropic continuation has no assistant turn to restore"
            )
        existing = list(messages[target_index].get("content") or [])
        messages[target_index]["content"] = [dict(block) for block in blocks] + existing
        updated["messages"] = messages
        return updated, CodecReport.from_dict(
            {**report.to_dict(), "continuation": "applied", "lossless": report.lossless}
        )

    def decode(
        self, response: Any, *, request: RequestView
    ) -> ProviderDecodedResponse:
        if not isinstance(response, dict):
            raise CodecCapabilityError("Anthropic response must be a JSON object")
        provider_scope = f"{request.target.provider}:{request.target.api_mode}"
        attachment_id = f"continuation_attachment_{request.request_id}"
        thinking_blocks: list[Dict[str, Any]] = []
        parts: list[Any] = []
        batch_id = f"batch_{request.request_id}"
        for index, block in enumerate(response.get("content") or []):
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind == "text":
                parts.append(
                    AssistantContent(
                        ContentBlock(type="text", text=str(block.get("text") or ""))
                    )
                )
            elif kind in {"thinking", "redacted_thinking"}:
                parts.append(
                    ReasoningBlock(
                        provider_scope=provider_scope,
                        reference_id=str(
                            block.get("id")
                            or f"reasoning_{request.request_id}_{index}"
                        ),
                        block_type=str(kind),
                        summary=(
                            str(block.get("thinking"))
                            if block.get("thinking") is not None
                            else None
                        ),
                        attachment_id=attachment_id,
                    )
                )
                thinking_blocks.append(dict(block))
            elif kind == "tool_use":
                raw_input = block.get("input")
                parsed: Dict[str, Any] = (
                    dict(raw_input) if isinstance(raw_input, dict) else {}
                )
                parts.append(
                    ToolCall(
                        identity=CallIdentity(
                            provider_scope,
                            str(block.get("id") or f"call_{request.request_id}_{index}"),
                        ),
                        batch_id=batch_id,
                        name=str(block.get("name") or ""),
                        raw_arguments=json.dumps(parsed, ensure_ascii=False, sort_keys=True),
                        parsed_arguments=dict(parsed),
                        parse_status=ArgumentParseStatus.PARSED,
                    )
                )
        usage = response.get("usage") if isinstance(response.get("usage"), dict) else None
        return ProviderDecodedResponse(
            parts=tuple(parts),
            usage=usage,
            finish_reason=(
                str(response.get("stop_reason"))
                if response.get("stop_reason") is not None
                else None
            ),
            model_name=str(response.get("model") or request.target.model),
            provider_metadata={
                key: response[key]
                for key in ("id", "type", "stop_sequence")
                if key in response
            },
            continuation_payload=(
                {"thinking_blocks": thinking_blocks} if thinking_blocks else None
            ),
            continuation_attachment_id=(attachment_id if thinking_blocks else None),
        )


class AnthropicModel(Model):
    """
    Anthropic Messages API model.

    Environment variables:
    - ANTHROPIC_API_KEY
    - ANTHROPIC_BASE_URL (optional, default https://api.anthropic.com)
    - ANTHROPIC_API_VERSION (optional, default 2023-06-01)
    """

    qitos_provider_id = "anthropic"
    qitos_transport_id = "messages"
    qitos_api_mode = "messages"
    qitos_capabilities_by_api_mode = {
        "messages": {
            "supported_features": (
                "text",
                "multimodal",
                "tool_calls",
                "tool_results",
                "tool_schemas",
                "parallel_tool_calls",
                "reasoning",
                "continuation",
                "ordered_interleaving",
                "provider_metadata",
            ),
            "reasoning_modes": (
                "preserve_if_supported",
                "signed_block_replay",
                "drop",
            ),
            "multimodal_types": ("text", "image_base64"),
            "supports_parallel_tool_calls": True,
            "supports_tool_schemas": True,
            "supports_continuation": True,
        }
    }

    def qitos_provider_codec(self) -> AnthropicMessagesCodec:
        return AnthropicMessagesCodec()

    def qitos_transport(self, payload: Mapping[str, Any]) -> Any:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.api_version,
            "content-type": "application/json",
        }
        request_payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": list(payload.get("messages") or []),
        }
        if payload.get("system"):
            request_payload["system"] = payload["system"]
        if payload.get("tools"):
            request_payload["tools"] = payload["tools"]
        response = requests.post(
            f"{self.base_url}/v1/messages",
            headers=headers,
            json=request_payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        result = response.json()
        self._set_last_usage(self._usage_from_response(result))
        return result

    def __init__(
        self,
        model: str = "claude-3-5-sonnet-latest",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        api_version: str = "2023-06-01",
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
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
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        resolved_base_url = base_url or os.getenv(
            "ANTHROPIC_BASE_URL", "https://api.anthropic.com"
        )
        self.base_url = str(resolved_base_url).rstrip("/")
        self.api_version = api_version or os.getenv(
            "ANTHROPIC_API_VERSION", "2023-06-01"
        )
        self.timeout = timeout
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. Please set it or pass api_key."
            )

    def _call_api(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.api_version,
            "content-type": "application/json",
        }
        _ = kwargs
        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": self._anthropic_messages(messages),
        }
        system_text = self._system_text(messages)
        if system_text:
            payload["system"] = system_text

        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()
            self._set_last_usage(self._usage_from_response(result))
            return self._parse_response(result)
        except requests.HTTPError as exc:
            body = exc.response.text if exc.response is not None else ""
            return f"HTTP Error: {body or str(exc)}"
        except requests.RequestException as exc:
            return f"Connection Error: {str(exc)}"
        except Exception as exc:
            return f"Error: {str(exc)}"

    def _system_text(self, messages: List[Dict[str, Any]]) -> str:
        parts: List[str] = []
        if self.system_prompt:
            parts.append(str(self.system_prompt))
        for msg in messages:
            if str(msg.get("role", "")) == "system":
                content = str(msg.get("content", "")).strip()
                if content:
                    parts.append(content)
        return "\n\n".join(parts).strip()

    def _anthropic_messages(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        converted: List[Dict[str, Any]] = []
        for msg in messages:
            role = str(msg.get("role", ""))
            if role == "system":
                continue
            mapped_role = "assistant" if role == "assistant" else "user"
            converted.append(
                {
                    "role": mapped_role,
                    "content": str(msg.get("content", "")),
                }
            )
        return converted

    def _parse_response(self, response: Dict[str, Any]) -> str:
        blocks = list(response.get("content") or [])
        text_parts: List[str] = []
        tool_parts: List[str] = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            kind = str(block.get("type", "")).strip()
            if kind == "text":
                text = str(block.get("text", "")).strip()
                if text:
                    text_parts.append(text)
            elif kind == "tool_use":
                name = str(block.get("name", "")).strip()
                args = block.get("input", {})
                if name:
                    if not isinstance(args, dict):
                        args = {"input": args}
                    tool_parts.append(self.format_action(name, args))
        if tool_parts:
            return "\n".join(tool_parts)
        return "\n".join(text_parts).strip()

    def _usage_from_response(
        self, response: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        usage = response.get("usage")
        if not isinstance(usage, dict):
            return None
        input_tokens = usage.get("input_tokens")
        cache_creation = usage.get("cache_creation_input_tokens")
        cache_read = usage.get("cache_read_input_tokens")
        output_tokens = usage.get("output_tokens")
        prompt_total = 0
        has_prompt = False
        for value in (input_tokens, cache_creation, cache_read):
            if isinstance(value, int):
                prompt_total += value
                has_prompt = True
        total_tokens = None
        if has_prompt or isinstance(output_tokens, int):
            total_tokens = prompt_total + int(output_tokens or 0)
        return {
            "prompt_tokens": prompt_total if has_prompt else input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": total_tokens,
        }

    def stream(self, messages: List[Dict[str, Any]], **kwargs: Any) -> Iterator[ModelStreamChunk]:
        """Stream Anthropic Messages API response as chunks using SSE."""
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.api_version,
            "content-type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": self._anthropic_messages(messages),
            "stream": True,
        }
        system_text = self._system_text(messages)
        if system_text:
            payload["system"] = system_text
        payload.update(kwargs)

        self._last_usage = None
        try:
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=headers,
                json=payload,
                timeout=self.timeout,
                stream=True,
            )
            response.raise_for_status()

            usage_data = None
            for line in response.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                import json as _json

                try:
                    event = _json.loads(data_str)
                except _json.JSONDecodeError:
                    continue

                event_type = event.get("type", "")

                if event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            yield ModelStreamChunk(text=text, done=False)

                elif event_type == "message_delta":
                    delta = event.get("delta", {})
                    if delta.get("stop_reason"):
                        msg_usage = event.get("usage", {})
                        if msg_usage:
                            output_tokens = msg_usage.get("output_tokens")
                            usage_data = {"completion_tokens": output_tokens}
                        yield ModelStreamChunk(text="", done=True, usage=usage_data)
                        break

                elif event_type == "message_start":
                    msg_data = event.get("message", {})
                    msg_usage = msg_data.get("usage", {})
                    if msg_usage:
                        input_tokens = msg_usage.get("input_tokens")
                        usage_data = {"prompt_tokens": input_tokens}

                elif event_type == "message_stop":
                    yield ModelStreamChunk(text="", done=True, usage=usage_data)
                    break

            if usage_data:
                self._set_last_usage(usage_data)

        except requests.HTTPError as exc:
            body = exc.response.text if exc.response is not None else ""
            yield ModelStreamChunk(text=f"HTTP Error: {body or str(exc)}", done=True)
        except requests.RequestException as exc:
            yield ModelStreamChunk(text=f"Connection Error: {str(exc)}", done=True)
        except Exception as exc:
            yield ModelStreamChunk(text=f"Error: {str(exc)}", done=True)


ModelFactory.register("anthropic")(AnthropicModel)


__all__ = ["AnthropicModel"]
