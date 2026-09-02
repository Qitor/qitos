from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional

import pytest

from qitos.core.conversation import (
    ArgumentParseStatus,
    AssistantContent,
    AssistantItem,
    CallIdentity,
    ExchangeLog,
    ReasoningBlock,
    ToolCall,
    UserItem,
)
from qitos.core.model_response import ModelResponse
from qitos.core.multimodal import ContentBlock
from qitos.core.request_view import RequestTarget, RequestView
from qitos.models.anthropic import AnthropicModel
from qitos.models.codec import (
    CodecCapabilityError,
    CodecLossError,
    CodecReport,
    ProviderCapabilities,
    ProviderFailure,
    report_for_request,
    validate_codec_result,
)
from qitos.config.credentials import SecretValue
from qitos.models.gemini import GeminiModel
from qitos.models.litellm import LiteLLMModel
from qitos.models.local import (
    LMStudioModel,
    OllamaGenerateModel,
    OllamaModel,
    VLLMModel,
)
from qitos.models.openai import OpenAIModel
from qitos.models.provider import (
    ContinuationResolution,
    ProviderAdapter,
    ProviderDecodedResponse,
    execute_provider_request,
    normalize_provider_failure,
)


def _request(target: RequestTarget, *, reasoning: bool = False) -> RequestView:
    log = ExchangeLog(log_id=f"log_{target.provider}_{target.api_mode}")
    log.append(
        UserItem(
            item_id="user_1",
            exchange_id="exchange_1",
            content=[ContentBlock(type="text", text="inspect")],
        )
    )
    if reasoning:
        log.append(
            AssistantItem(
                item_id="assistant_reasoning",
                exchange_id="exchange_reasoning",
                parts=[
                    ReasoningBlock(
                        provider_scope=(
                            f"{target.provider}:{target.api_mode}"
                        ),
                        reference_id="reasoning_existing",
                        block_type="provider_summary",
                        summary="visible provider summary",
                    )
                ],
            )
        )
    return RequestView.from_exchange_log(
        log,
        target=target,
        instructions=[{"role": "system", "content": "Be precise."}],
    )


def _offline_model(model_type: type, api_mode: str) -> Any:
    model = object.__new__(model_type)
    model.model = "fixture-model"
    model.api_mode = api_mode
    model.context_window = 4096
    return model


@pytest.mark.parametrize(
    ("model_type", "api_mode", "payload_key"),
    [
        (OpenAIModel, "chat_completions", "messages"),
        (OpenAIModel, "responses", "messages"),
        (AnthropicModel, "messages", "messages"),
        (GeminiModel, "generate_content", "contents"),
        (LiteLLMModel, "chat_completions", "messages"),
        (OllamaModel, "chat", "messages"),
    ],
)
def test_official_adapters_use_the_same_declared_codec_contract(
    model_type: type, api_mode: str, payload_key: str
) -> None:
    model = _offline_model(model_type, api_mode)
    target = RequestTarget.from_model(model)
    capabilities = ProviderCapabilities.from_model(model)
    codec = model.qitos_provider_codec()

    payload, report = codec.encode(
        _request(target),
        capabilities=capabilities,
        transport=target,
    )

    assert payload_key in payload
    assert report.target == target
    assert report.lossless is True
    assert report.codec_id == codec.codec_id
    assert ProviderCapabilities.from_dict(capabilities.to_dict()) == capabilities
    assert CodecReport.from_dict(report.to_dict()) == report


@pytest.mark.parametrize(
    ("model_type", "api_mode", "response"),
    [
        (
            OpenAIModel,
            "chat_completions",
            {
                "choices": [
                    {
                        "message": {
                            "content": "working",
                            "tool_calls": [
                                {
                                    "id": "call_chat",
                                    "type": "function",
                                    "function": {"name": "read", "arguments": "{}"},
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "model": "fixture-model",
            },
        ),
        (
            OpenAIModel,
            "responses",
            ModelResponse(
                text="working",
                finish_reason="completed",
                model_name="fixture-model",
                metadata={"id": "resp_fixture", "status": "completed"},
                native_items=[
                    {
                        "type": "reasoning",
                        "id": "reasoning_responses",
                        "summary": [{"type": "summary_text", "text": "summary"}],
                        "encrypted_content": "opaque-fixture",
                    },
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "working"}],
                    },
                    {
                        "type": "function_call",
                        "call_id": "call_responses",
                        "name": "read",
                        "arguments": "{}",
                    },
                ],
            ),
        ),
        (
            AnthropicModel,
            "messages",
            {
                "id": "msg_fixture",
                "model": "fixture-model",
                "stop_reason": "tool_use",
                "content": [
                    {"type": "thinking", "thinking": "summary", "signature": "opaque"},
                    {"type": "text", "text": "working"},
                    {"type": "tool_use", "id": "call_anthropic", "name": "read", "input": {}},
                ],
            },
        ),
        (
            GeminiModel,
            "generate_content",
            {
                "candidates": [
                    {
                        "index": 0,
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {"thought": True, "text": "summary", "thoughtSignature": "opaque"},
                                {"text": "working"},
                                {"functionCall": {"id": "call_gemini", "name": "read", "args": {}}},
                            ]
                        },
                    }
                ]
            },
        ),
        (
            LiteLLMModel,
            "chat_completions",
            {
                "choices": [
                    {
                        "message": {
                            "content": "working",
                            "tool_calls": [
                                {
                                    "id": "call_litellm",
                                    "type": "function",
                                    "function": {"name": "read", "arguments": "{}"},
                                }
                            ],
                        }
                    }
                ]
            },
        ),
        (
            OllamaModel,
            "chat",
            {
                "model": "fixture-model",
                "done": True,
                "prompt_eval_count": 4,
                "eval_count": 2,
                "message": {
                    "content": "working",
                    "tool_calls": [
                        {"function": {"name": "read", "arguments": {}}}
                    ],
                },
            },
        ),
    ],
)
def test_official_response_decoders_preserve_order_and_tool_identity(
    model_type: type, api_mode: str, response: Any
) -> None:
    model = _offline_model(model_type, api_mode)
    request = _request(RequestTarget.from_model(model))
    decoded = model.qitos_provider_codec().decode(response, request=request)

    assert any(isinstance(part, AssistantContent) for part in decoded.parts)
    assert any(isinstance(part, ToolCall) for part in decoded.parts)
    calls = [part for part in decoded.parts if isinstance(part, ToolCall)]
    assert all(call.identity.call_id for call in calls)
    assert all(call.parse_status is ArgumentParseStatus.PARSED for call in calls)
    if api_mode in {"responses", "messages", "generate_content"}:
        assert any(isinstance(part, ReasoningBlock) for part in decoded.parts)
        assert decoded.continuation_payload is not None


class AcmeCodec:
    codec_id = "x.acme.semantic"
    codec_version = "v1"

    def encode(
        self,
        request: RequestView,
        *,
        capabilities: Optional[ProviderCapabilities] = None,
        transport: Optional[RequestTarget] = None,
        allow_loss: bool = False,
    ) -> tuple[Dict[str, Any], CodecReport]:
        assert capabilities is not None
        assert transport == request.target
        report = report_for_request(
            request,
            capabilities,
            codec_id=self.codec_id,
            codec_version=self.codec_version,
            reasoning="preserved",
            continuation="not_requested",
            supported=request.capability_requirements,
        )
        return validate_codec_result(
            {"turns": list(request.selected_items)},
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
        self, response: Any, *, request: RequestView
    ) -> ProviderDecodedResponse:
        _ = response
        scope = f"{request.target.provider}:{request.target.api_mode}"
        return ProviderDecodedResponse(
            parts=(
                ReasoningBlock(
                    provider_scope=scope,
                    reference_id="acme_reasoning",
                    block_type="acme_plan",
                    summary="safe summary",
                ),
                AssistantContent(ContentBlock(type="text", text="working")),
                ToolCall(
                    identity=CallIdentity(scope, "call_acme_1"),
                    batch_id=f"batch_{request.request_id}",
                    name="first",
                    raw_arguments="{}",
                    parsed_arguments={},
                    parse_status=ArgumentParseStatus.PARSED,
                ),
                ToolCall(
                    identity=CallIdentity(scope, "call_acme_2"),
                    batch_id=f"batch_{request.request_id}",
                    name="second",
                    raw_arguments="{}",
                    parsed_arguments={},
                    parse_status=ArgumentParseStatus.PARSED,
                ),
            ),
            usage={"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            finish_reason="tool_calls",
            model_name=request.target.model,
            provider_metadata={"receipt": "logical-acme-receipt"},
        )


class AcmeAdapter:
    model = "acme-model"
    qitos_continuation_resolver = None

    def qitos_request_target(self) -> RequestTarget:
        return RequestTarget("acme", self.model, "acme-wire", "semantic")

    def qitos_provider_capabilities(self) -> Mapping[str, Any]:
        return {
            "supported_features": (
                "text",
                "tool_calls",
                "parallel_tool_calls",
                "reasoning",
                "streaming",
                "x.acme.semantic_batch",
            ),
            "reasoning_modes": ("preserve_if_supported", "drop"),
            "multimodal_types": ("text",),
            "supports_parallel_tool_calls": True,
            "supports_tool_schemas": False,
            "supports_continuation": False,
            "max_input_units": 4096,
        }

    def qitos_provider_codec(self) -> AcmeCodec:
        return AcmeCodec()

    def qitos_transport(self, payload: Mapping[str, Any]) -> Any:
        assert payload["turns"]
        return {"accepted": True}

    def qitos_stream_transport(
        self, payload: Mapping[str, Any], *, on_delta: Any = None
    ) -> Any:
        assert payload["turns"]
        if callable(on_delta):
            on_delta("work")
            on_delta("ing")
        return {"accepted": True}

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


def test_independent_third_party_adapter_passes_full_transaction_conformance() -> None:
    adapter = AcmeAdapter()
    assert isinstance(adapter, ProviderAdapter)
    request = _request(adapter.qitos_request_target())
    streamed: list[str] = []

    transaction = execute_provider_request(
        adapter, request, stream_callback=streamed.append
    )

    assert streamed == ["work", "ing"]
    assert transaction.codec_report.lossless is True
    assert [part.kind for part in transaction.assistant_item.parts] == [
        "reasoning_block",
        "content",
        "tool_call",
        "tool_call",
    ]
    assert [call.identity.call_id for call in transaction.assistant_item.tool_calls()] == [
        "call_acme_1",
        "call_acme_2",
    ]
    assert transaction.model_response.raw is None
    assert transaction.model_response.text == "working"


def test_request_transform_is_replaceable_and_transport_options_are_isolated() -> None:
    class CaptureAdapter(AcmeAdapter):
        def __init__(self) -> None:
            self.payload: Optional[Mapping[str, Any]] = None

        def qitos_transport(self, payload: Mapping[str, Any]) -> Any:
            self.payload = payload
            return {"accepted": True}

    class FixtureTransform:
        transform_id = "x.fixture.request_transform/v1"

        def transform(
            self,
            payload: Mapping[str, Any],
            *,
            request: RequestView,
            report: CodecReport,
        ) -> tuple[Dict[str, Any], CodecReport]:
            updated = dict(payload)
            updated["request_receipt"] = request.request_id
            return updated, replace(
                report, warnings=report.warnings + (self.transform_id,)
            )

    adapter = CaptureAdapter()
    transaction = execute_provider_request(
        adapter,
        _request(adapter.qitos_request_target()),
        transport_options={"tool_choice": "auto"},
        request_transform=FixtureTransform(),
    )

    assert adapter.payload is not None
    assert adapter.payload["options"] == {"tool_choice": "auto"}
    assert adapter.payload["request_receipt"] == transaction.request.request_id
    assert transaction.codec_report.warnings[-1] == (
        "x.fixture.request_transform/v1"
    )


def test_transport_boundary_materializes_nested_immutable_options_and_isolates_ownership() -> None:
    class CaptureAdapter(AcmeAdapter):
        def __init__(self) -> None:
            self.payload: Optional[Mapping[str, Any]] = None

        def qitos_transport(self, payload: Mapping[str, Any]) -> Any:
            self.payload = payload
            return {"accepted": True}

    mutable = {"flags": [True, False]}
    options = MappingProxyType(
        {
            "chat_template_kwargs": MappingProxyType(
                {"enable_thinking": False, "nested": mutable}
            ),
            "mixed": (1, [2, MappingProxyType({"value": True})]),
        }
    )
    adapter = CaptureAdapter()

    execute_provider_request(
        adapter,
        _request(adapter.qitos_request_target()),
        transport_options=options,
    )

    assert adapter.payload is not None
    projected = adapter.payload["options"]
    assert type(projected) is dict
    assert type(projected["chat_template_kwargs"]) is dict
    assert type(projected["mixed"]) is list
    assert projected["chat_template_kwargs"]["enable_thinking"] is False
    mutable["flags"].append(True)
    assert projected["chat_template_kwargs"]["nested"]["flags"] == [True, False]
    projected["chat_template_kwargs"]["nested"]["flags"].append(False)
    assert mutable["flags"] == [True, False, True]


@pytest.mark.parametrize(
    ("invalid", "category"),
    [
        ({1: "value"}, "non_string_key"),
        ({"value": float("nan")}, "non_finite_number"),
        ({"value": float("inf")}, "non_finite_number"),
        ({"value": {"item"}}, "unsupported_type"),
        ({"value": frozenset({"item"})}, "unsupported_type"),
        ({"value": b"bytes"}, "unsupported_type"),
        ({"value": object()}, "unsupported_type"),
        ({"value": lambda: None}, "unsupported_type"),
        ({"value": SecretValue("private-value")}, "unsupported_type"),
    ],
)
def test_transport_boundary_rejects_non_json_values_without_echo(
    invalid: Any, category: str
) -> None:
    adapter = AcmeAdapter()

    with pytest.raises(CodecCapabilityError) as caught:
        execute_provider_request(
            adapter,
            _request(adapter.qitos_request_target()),
            transport_options=invalid,
        )

    assert caught.value.code == "codec_transport_options_invalid"
    assert category in str(caught.value)
    assert "private-value" not in str(caught.value)
    assert "SecretValue" not in str(caught.value)


def test_transport_boundary_rejects_cycles_depth_nodes_and_sensitive_paths() -> None:
    adapter = AcmeAdapter()
    cycle: list[Any] = []
    cycle.append(cycle)
    deep: Any = None
    for _ in range(66):
        deep = [deep]
    oversized = [None] * 10001

    for invalid, category in (
        ({"cycle": cycle}, "cycle_detected"),
        ({"deep": deep}, "depth_limit_exceeded"),
        ({"oversized": oversized}, "node_limit_exceeded"),
        ({"sk-private-value": object()}, "unsupported_type"),
    ):
        with pytest.raises(CodecCapabilityError) as caught:
            execute_provider_request(
                adapter,
                _request(adapter.qitos_request_target()),
                transport_options=invalid,
            )
        rendered = str(caught.value)
        assert caught.value.code == "codec_transport_options_invalid"
        assert category in rendered
        assert "sk-private-value" not in rendered


def test_codec_loss_rejects_by_default_and_explicit_acceptance_has_report() -> None:
    model = _offline_model(OpenAIModel, "chat_completions")
    target = RequestTarget.from_model(model)
    request = _request(target, reasoning=True)
    codec = model.qitos_provider_codec()
    capabilities = ProviderCapabilities.from_model(model)

    with pytest.raises((CodecCapabilityError, CodecLossError)):
        codec.encode(request, capabilities=capabilities, transport=target)

    _, report = codec.encode(
        request,
        capabilities=capabilities,
        transport=target,
        allow_loss=True,
    )
    assert report.lossless is False
    assert "assistant.reasoning" in report.lossy_fields


def test_provider_failure_is_sanitized_and_carries_codec_report() -> None:
    class SecretTransport(AcmeAdapter):
        def qitos_transport(self, payload: Mapping[str, Any]) -> Any:
            _ = payload
            error = RuntimeError(
                "sk-secret https://localhost:9443 /Users/example/private"
            )
            error.status_code = 503  # type: ignore[attr-defined]
            raise error

    adapter = SecretTransport()
    with pytest.raises(ProviderFailure) as caught:
        execute_provider_request(adapter, _request(adapter.qitos_request_target()))

    rendered = json.dumps(caught.value.to_dict(), ensure_ascii=False)
    assert caught.value.retryable is True
    assert caught.value.codec_report is not None
    assert "sk-secret" not in rendered
    assert "localhost" not in rendered
    assert "/Users/" not in rendered


def test_stable_provider_matrix_matches_official_adapter_declarations() -> None:
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "s2"
        / "lane_b"
        / "provider-capability-matrix.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    model_types = {
        "OpenAIModel": OpenAIModel,
        "AnthropicModel": AnthropicModel,
        "GeminiModel": GeminiModel,
        "LiteLLMModel": LiteLLMModel,
        "OllamaModel": OllamaModel,
        "OllamaGenerateModel": OllamaGenerateModel,
        "LMStudioModel": LMStudioModel,
        "VLLMModel": VLLMModel,
    }

    assert fixture["schema_version"] == "qitos.s2.lane_b.provider_matrix/v1"
    for row in fixture["rows"]:
        model = _offline_model(model_types[row["adapter"]], row["api_mode"])
        capabilities = ProviderCapabilities.from_model(model)
        codec = model.qitos_provider_codec()
        assert codec.codec_id == row["codec"]
        assert list(capabilities.supported_features) == row["features"]
        assert list(capabilities.reasoning_modes) == row["reasoning_modes"]
        assert capabilities.supports_continuation is row["continuation"]


def test_stable_semantic_and_loss_fixtures_are_strict_json() -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "s2" / "lane_b"
    semantic = json.loads(
        (fixture_dir / "semantic-contracts.json").read_text(encoding="utf-8")
    )
    loss = json.loads(
        (fixture_dir / "unsupported-loss-matrix.json").read_text(
            encoding="utf-8"
        )
    )

    assert semantic["canonical_path"][0] == "exchange_log"
    assert semantic["canonical_path"][-1] == "exchange_log"
    assert semantic["assistant_part_order"] == [
        "reasoning_block",
        "content",
        "tool_call",
        "tool_call",
    ]
    assert loss["default_loss_policy"] == "reject"
    assert {row["outcome"] for row in loss["rows"]} >= {
        "codec_loss_rejected",
        "codec_capability_mismatch",
        "stateless_replay",
        "malformed_response",
    }


def test_lane_b_evidence_binds_fixtures_to_exact_producer_commit() -> None:
    repository = Path(__file__).parent.parent
    fixture_dir = Path(__file__).parent / "fixtures" / "s2" / "lane_b"
    evidence = json.loads(
        (fixture_dir / "evidence.json").read_text(encoding="utf-8")
    )

    assert evidence["schema_version"] == "qitos.s2.lane_b.evidence/v1"
    assert evidence["producer_commit"] == (
        "60e8d94edb9a5f00434095a3489e1e1100185bea"
    )
    for fixture in evidence["fixtures"]:
        contents = (repository / fixture["path"]).read_bytes()
        assert hashlib.sha256(contents).hexdigest() == fixture["sha256"]
