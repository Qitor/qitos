"""Executable structural provider consumer for S4 Lane B.

This fixture intentionally inherits no QitOS provider implementation and uses
no Engine private state.  It is safe to execute offline.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Mapping, Optional

from qitos.core.conversation import (
    ArgumentParseStatus,
    AssistantContent,
    CallIdentity,
    ReasoningBlock,
    ToolCall,
)
from qitos.core.multimodal import ContentBlock
from qitos.core.request_view import RequestTarget, RequestView
from qitos.models.codec import (
    CodecReport,
    ProviderCapabilities,
    ProviderFailure,
    report_for_request,
    validate_codec_result,
)
from qitos.models.provider import (
    ContinuationResolution,
    InMemoryContinuationResolver,
    ProviderDecodedResponse,
    normalize_provider_failure,
)


class ExampleSemanticCodec:
    codec_id = "x.example.semantic"
    codec_version = "v1"

    def encode(
        self,
        request: RequestView,
        *,
        capabilities: Optional[ProviderCapabilities] = None,
        transport: Optional[RequestTarget] = None,
        allow_loss: bool = False,
    ) -> tuple[Dict[str, Any], CodecReport]:
        if capabilities is None or transport != request.target:
            raise ValueError("declared target and capabilities are required")
        report = report_for_request(
            request,
            capabilities,
            codec_id=self.codec_id,
            codec_version=self.codec_version,
            reasoning="native_item_continuation",
            continuation=(
                "resolver_required" if request.continuation else "not_requested"
            ),
            supported=request.capability_requirements,
            multimodal_conversion=("ordered_blocks->semantic_parts",),
            tool_schema_conversion=("function->semantic_function",),
        )
        return validate_codec_result(
            {
                "instructions": list(request.instructions),
                "turns": list(request.selected_items),
                "context": list(request.context_contributions),
                "tool_schemas": list(request.tool_schemas),
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
        updated = dict(payload)
        updated["continuation"] = resolution.payload
        return updated, replace(report, continuation="applied")

    def decode(
        self,
        response: Any,
        *,
        request: RequestView,
    ) -> ProviderDecodedResponse:
        if not isinstance(response, Mapping) or response.get("kind") != "semantic":
            raise ValueError("response envelope is malformed")
        scope = f"{request.target.provider}:{request.target.api_mode}"
        batch_id = f"batch_{request.request_id}"
        parts = (
            ReasoningBlock(
                provider_scope=scope,
                reference_id="reasoning-example",
                block_type="signed_summary",
                summary="bounded summary",
                attachment_id="continuation-example",
            ),
            AssistantContent(ContentBlock(type="text", text="working")),
            AssistantContent(
                ContentBlock(
                    type="image_base64",
                    data="AA==",
                    mime_type="image/png",
                )
            ),
            ToolCall(
                identity=CallIdentity(scope, "call-example-first"),
                batch_id=batch_id,
                name="first",
                raw_arguments="{}",
                parsed_arguments={},
                parse_status=ArgumentParseStatus.PARSED,
            ),
            ToolCall(
                identity=CallIdentity(scope, "call-example-second"),
                batch_id=batch_id,
                name="second",
                raw_arguments="{}",
                parsed_arguments={},
                parse_status=ArgumentParseStatus.PARSED,
            ),
        )
        return ProviderDecodedResponse(
            parts=parts,
            usage={
                "prompt_tokens": 7,
                "completion_tokens": 5,
                "total_tokens": 12,
            },
            finish_reason="tool_calls",
            model_name=request.target.model,
            provider_metadata={"request_id": "logical-example-receipt"},
            continuation_payload={"signed_state": "opaque-example"},
            continuation_attachment_id="continuation-example",
        )


class ExampleSemanticAdapter:
    model = "example-model"

    def __init__(self) -> None:
        self.qitos_continuation_resolver = InMemoryContinuationResolver(
            "continuation:example"
        )

    def qitos_request_target(self) -> RequestTarget:
        return RequestTarget("example", self.model, "example-wire", "semantic")

    def qitos_provider_capabilities(self) -> Mapping[str, Any]:
        return {
            "api_style": "compatibility",
            "supported_features": (
                "text",
                "multimodal",
                "tool_calls",
                "tool_results",
                "tool_schemas",
                "parallel_tool_calls",
                "artifact_references",
                "reasoning",
                "continuation",
                "streaming",
                "ordered_interleaving",
                "provider_metadata",
                "steering",
            ),
            "reasoning_modes": (
                "preserve_if_supported",
                "native_item_continuation",
                "drop",
            ),
            "multimodal_types": ("text", "image_base64"),
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
            "max_input_units": 32_768,
            "max_output_units": 10_240,
        }

    def qitos_provider_codec(self) -> ExampleSemanticCodec:
        return ExampleSemanticCodec()

    def qitos_transport(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if not payload.get("turns"):
            raise ValueError("turns are required")
        return example_response()

    def qitos_stream_transport(
        self,
        payload: Mapping[str, Any],
        *,
        on_delta: Any = None,
    ) -> Mapping[str, Any]:
        if not payload.get("turns"):
            raise ValueError("turns are required")
        if callable(on_delta):
            on_delta("work")
            on_delta("ing")
        return example_response()

    def qitos_normalize_failure(
        self,
        error: BaseException,
        *,
        report: Optional[CodecReport] = None,
    ) -> ProviderFailure:
        return normalize_provider_failure(
            error,
            target=self.qitos_request_target(),
            report=report,
        )


def example_response() -> Mapping[str, Any]:
    return {"kind": "semantic", "receipt": "logical-example-receipt"}

