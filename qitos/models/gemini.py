"""
Native Google Gemini API model implementation.

This adapter talks to the official Gemini `generateContent` endpoint directly.
"""

from __future__ import annotations

import os
import json
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import quote

import requests

from .base import Model, ModelFactory
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


class GeminiGenerateContentCodec(LegacyMessageCodec):
    codec_id = "qitos.google.generate_content"
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
        contents: list[Dict[str, Any]] = []
        losses: list[str] = []
        for instruction in request.instructions:
            value = str(instruction.get("content") or "")
            if instruction.get("role") in {"system", "developer"}:
                system_parts.append(value)
            else:
                contents.append({"role": "user", "parts": [{"text": value}]})
        for contribution in request.context_contributions:
            value = json.dumps(
                contribution.get("content"), ensure_ascii=False, sort_keys=True
            )
            if contribution.get("requested_placement") in {"system", "developer"}:
                system_parts.append(value)
            else:
                contents.append({"role": "user", "parts": [{"text": value}]})
        for item in request.selected_items:
            kind = item.get("kind")
            if kind in {"user", "steering"}:
                parts = []
                for block in item.get("content") or []:
                    block_type = block.get("type")
                    if block_type == "text":
                        parts.append({"text": block.get("text", "")})
                    elif block_type == "image_base64":
                        parts.append(
                            {
                                "inlineData": {
                                    "mimeType": block.get("mime_type", "image/png"),
                                    "data": block.get("data", ""),
                                }
                            }
                        )
                    elif block_type == "image_url":
                        parts.append(
                            {
                                "fileData": {
                                    "mimeType": block.get("mime_type", "image/png"),
                                    "fileUri": block.get("url", ""),
                                }
                            }
                        )
                    else:
                        losses.append(f"multimodal.{block_type}")
                contents.append({"role": "user", "parts": parts})
            elif kind == "assistant":
                parts = []
                for part in item.get("parts") or []:
                    part_kind = part.get("kind")
                    if part_kind == "content":
                        block = part.get("block") or {}
                        if block.get("type") == "text":
                            parts.append({"text": block.get("text", "")})
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
                                "Gemini functionCall requires parsed object arguments"
                            )
                        parts.append(
                            {
                                "functionCall": {
                                    "name": part.get("name"),
                                    "args": parsed,
                                }
                            }
                        )
                contents.append({"role": "model", "parts": parts})
            elif kind == "tool_result":
                result = item.get("result") or {}
                output = result.get("model_output")
                if output is None:
                    output = {"error": result.get("error") or "tool_error"}
                elif not isinstance(output, dict):
                    output = {"result": output}
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "functionResponse": {
                                    "name": result.get("tool_name") or "tool",
                                    "response": output,
                                }
                            }
                        ],
                    }
                )
        declarations = []
        for schema in request.tool_schemas:
            function = schema.get("function") if schema.get("type") == "function" else schema
            if not isinstance(function, dict) or not function.get("name"):
                raise CodecCapabilityError("Gemini tool schema is malformed")
            declarations.append(
                {
                    "name": function.get("name"),
                    "description": function.get("description", ""),
                    "parameters": function.get(
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
                "native_item_continuation"
                if request.continuation is not None
                else ("dropped" if "assistant.reasoning" in losses else "not_present")
            ),
            continuation=(
                "resolver_required" if request.continuation else "not_requested"
            ),
            supported=request.capability_requirements,
            multimodal_conversion=(
                "image_base64->inlineData",
                "image_url->fileData",
            ),
            tool_schema_conversion=("function->functionDeclarations",),
            lossy_fields=losses,
        )
        payload: Dict[str, Any] = {
            "contents": contents,
            "systemInstruction": (
                {"parts": [{"text": "\n\n".join(system_parts)}]}
                if system_parts
                else None
            ),
            "tools": (
                [{"functionDeclarations": declarations}] if declarations else []
            ),
        }
        return validate_codec_result(payload, report, allow_loss=allow_loss)

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
        restored_parts = value.get("signed_parts") if isinstance(value, dict) else None
        if not isinstance(restored_parts, list):
            raise CodecCapabilityError(
                "Gemini continuation must resolve to signed_parts"
            )
        updated = dict(payload)
        contents = [dict(item) for item in updated.get("contents") or []]
        target_index = next(
            (
                index
                for index in range(len(contents) - 1, -1, -1)
                if contents[index].get("role") == "model"
            ),
            None,
        )
        if target_index is None:
            raise CodecCapabilityError(
                "Gemini continuation has no model turn to restore"
            )
        contents[target_index]["parts"] = [dict(item) for item in restored_parts] + list(
            contents[target_index].get("parts") or []
        )
        updated["contents"] = contents
        return updated, CodecReport.from_dict(
            {**report.to_dict(), "continuation": "applied", "lossless": report.lossless}
        )

    def decode(
        self, response: Any, *, request: RequestView
    ) -> ProviderDecodedResponse:
        if not isinstance(response, dict):
            raise CodecCapabilityError("Gemini response must be a JSON object")
        candidates = response.get("candidates") or []
        if not candidates or not isinstance(candidates[0], dict):
            raise CodecCapabilityError("Gemini response has no candidate")
        candidate = candidates[0]
        content = candidate.get("content") or {}
        provider_scope = f"{request.target.provider}:{request.target.api_mode}"
        attachment_id = f"continuation_attachment_{request.request_id}"
        parts: list[Any] = []
        signed_parts: list[Dict[str, Any]] = []
        batch_id = f"batch_{request.request_id}"
        for index, part in enumerate(content.get("parts") or []):
            if not isinstance(part, dict):
                continue
            signature = part.get("thoughtSignature")
            if part.get("thought") is True or signature is not None:
                parts.append(
                    ReasoningBlock(
                        provider_scope=provider_scope,
                        reference_id=f"reasoning_{request.request_id}_{index}",
                        block_type="gemini_thought",
                        summary=(
                            str(part.get("text"))
                            if part.get("text") is not None
                            else None
                        ),
                        attachment_id=attachment_id,
                    )
                )
                signed_parts.append(dict(part))
                continue
            if part.get("text") is not None:
                parts.append(
                    AssistantContent(
                        ContentBlock(type="text", text=str(part.get("text") or ""))
                    )
                )
                continue
            function_call = part.get("functionCall")
            if isinstance(function_call, dict):
                parsed = function_call.get("args")
                if not isinstance(parsed, dict):
                    parsed = {}
                call_id = str(
                    function_call.get("id")
                    or f"call_{request.request_id}_{index}"
                )
                parts.append(
                    ToolCall(
                        identity=CallIdentity(provider_scope, call_id),
                        batch_id=batch_id,
                        name=str(function_call.get("name") or ""),
                        raw_arguments=json.dumps(parsed, ensure_ascii=False, sort_keys=True),
                        parsed_arguments=dict(parsed),
                        parse_status=ArgumentParseStatus.PARSED,
                        metadata={
                            "thought_signature_present": signature is not None
                        },
                    )
                )
                if signature is not None:
                    signed_parts.append(dict(part))
        usage = response.get("usageMetadata")
        usage_mapping = None
        if isinstance(usage, dict):
            usage_mapping = {
                "prompt_tokens": usage.get("promptTokenCount"),
                "completion_tokens": usage.get("candidatesTokenCount"),
                "total_tokens": usage.get("totalTokenCount"),
            }
        return ProviderDecodedResponse(
            parts=tuple(parts),
            usage=usage_mapping,
            finish_reason=(
                str(candidate.get("finishReason"))
                if candidate.get("finishReason") is not None
                else None
            ),
            model_name=request.target.model,
            provider_metadata={
                "candidate_index": candidate.get("index", 0),
                "finish_message": candidate.get("finishMessage"),
            },
            continuation_payload=(
                {"signed_parts": signed_parts} if signed_parts else None
            ),
            continuation_attachment_id=(attachment_id if signed_parts else None),
        )


class GeminiModel(Model):
    """
    Google Gemini native REST model.

    Environment variables:
    - GEMINI_API_KEY or GOOGLE_API_KEY
    - GEMINI_BASE_URL (optional, default https://generativelanguage.googleapis.com/v1beta)
    """

    qitos_provider_id = "google"
    qitos_transport_id = "gemini"
    qitos_api_mode = "generate_content"
    qitos_capabilities_by_api_mode = {
        "generate_content": {
            "api_style": "generate_content",
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
                "native_item_continuation",
                "drop",
            ),
            "multimodal_types": ("text", "image_url", "image_base64"),
            "supports_native_tool_calls": True,
            "supports_parallel_tool_calls": True,
            "supports_tool_schemas": True,
            "supports_tool_choice": False,
            "supports_multimodal_input": True,
            "supports_reasoning_input": True,
            "supports_reasoning_output": True,
            "supports_continuation": True,
            "supports_stateless_replay": True,
            "supports_streaming": False,
            "supports_usage": True,
            "supports_cancellation": False,
            "supports_structured_output": False,
        }
    }

    def qitos_provider_codec(self) -> GeminiGenerateContentCodec:
        return GeminiGenerateContentCodec()

    def qitos_transport(self, payload: Mapping[str, Any]) -> Any:
        request_payload: Dict[str, Any] = {
            "contents": list(payload.get("contents") or []),
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
            },
        }
        if payload.get("systemInstruction"):
            request_payload["systemInstruction"] = payload["systemInstruction"]
        if payload.get("tools"):
            request_payload["tools"] = payload["tools"]
        response = None
        try:
            response = requests.post(
                f"{self.base_url}/models/{quote(self.model, safe='')}:generateContent",
                params={"key": self.api_key},
                json=request_payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()
            self._set_last_usage(self._usage_from_response(result))
            return result
        finally:
            from ._stream import close_owned

            close_owned(response)

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
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
        self.api_key = (
            api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        )
        resolved_base_url = base_url or os.getenv(
            "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
        )
        self.base_url = str(resolved_base_url).rstrip("/")
        self.timeout = timeout
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY or GOOGLE_API_KEY not set. Please set one or pass api_key."
            )

    def _call_api(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        payload: Dict[str, Any] = {
            "contents": self._gemini_contents(messages),
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
            },
        }
        _ = kwargs
        system_text = self._system_text(messages)
        if system_text:
            payload["systemInstruction"] = {"parts": [{"text": system_text}]}

        response = None
        try:
            response = requests.post(
                f"{self.base_url}/models/{quote(self.model, safe='')}:generateContent",
                params={"key": self.api_key},
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()
            self._set_last_usage(self._usage_from_response(result))
            return self._parse_response(result)
        except requests.HTTPError as exc:
            raise self.qitos_normalize_failure(exc) from None
        except Exception as exc:
            raise self.qitos_normalize_failure(exc) from None

        finally:
            from ._stream import close_owned

            close_owned(response)

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

    def _gemini_contents(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        contents: List[Dict[str, Any]] = []
        for msg in messages:
            role = str(msg.get("role", ""))
            if role == "system":
                continue
            gemini_role = "model" if role == "assistant" else "user"
            text = str(msg.get("content", ""))
            contents.append({"role": gemini_role, "parts": [{"text": text}]})
        return contents

    def _parse_response(self, response: Dict[str, Any]) -> str:
        candidates = list(response.get("candidates") or [])
        if not candidates:
            prompt_feedback = response.get("promptFeedback")
            if isinstance(prompt_feedback, dict) and prompt_feedback:
                from ._stream import refusal_failure

                raise refusal_failure(self)
            return ""

        content = candidates[0].get("content") or {}
        parts = list(content.get("parts") or [])
        texts: List[str] = []
        actions: List[str] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            text = str(part.get("text", "")).strip()
            if text:
                texts.append(text)
                continue
            function_call = part.get("functionCall")
            if isinstance(function_call, dict):
                name = str(function_call.get("name", "")).strip()
                args = function_call.get("args", {})
                if name:
                    if not isinstance(args, dict):
                        args = {"input": args}
                    actions.append(self.format_action(name, args))
        if actions:
            return "\n".join(actions)
        return "\n".join(texts).strip()

    def _usage_from_response(
        self, response: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        usage = response.get("usageMetadata")
        if not isinstance(usage, dict):
            return None
        prompt_tokens = usage.get("promptTokenCount")
        completion_tokens = usage.get("candidatesTokenCount")
        total_tokens = usage.get("totalTokenCount")
        if prompt_tokens is None and completion_tokens is None and total_tokens is None:
            return None
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }


ModelFactory.register("gemini")(GeminiModel)
ModelFactory.register("google")(GeminiModel)


__all__ = ["GeminiModel"]
