from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from qitos.core.conversation import ExchangeLog, UserItem
from qitos.core.multimodal import ContentBlock
from qitos.core.session import ContinuationIdentity
from qitos.core.request_view import (
    ContextContribution,
    ContinuationRef,
    RequestTarget,
    RequestView,
)
from qitos.models.codec import (
    CodecCapabilityError,
    CodecError,
    CodecLossError,
    CodecReport,
    ProviderCapabilities,
    ProviderCodec,
    ProviderFailure,
    capability_mismatches,
    report_for_request,
    validate_codec_result,
)


def _request(*, continuation: bool = False) -> RequestView:
    log = ExchangeLog(log_id="codec_log")
    log.append(
        UserItem(
            item_id="codec_user",
            exchange_id="codec_exchange",
            content=[ContentBlock(type="text", text="hello")],
        )
    )
    target = RequestTarget("openai", "fixture-model", "openai", "responses")
    reference = (
        ContinuationRef(
            reference_id=ContinuationIdentity(
                "continuation_30000000000000000000000000000001"
            ),
            resolver_key="continuation:codec",
            provider="openai",
            model="fixture-model",
            api_mode="responses",
        )
        if continuation
        else None
    )
    return RequestView.from_exchange_log(
        log,
        target=target,
        continuation=reference,
        context_contributions=[
            ContextContribution(
                contribution_id="codec_context",
                source="declared",
                content={"text": "context"},
            )
        ],
    )


def _capabilities(*, continuation: bool = True) -> ProviderCapabilities:
    features = ["text"]
    if continuation:
        features.append("continuation")
    return ProviderCapabilities(
        target=RequestTarget("openai", "fixture-model", "openai", "responses"),
        supported_features=tuple(features),
        reasoning_modes=("preserve_if_supported", "native_item_continuation", "drop"),
        multimodal_types=("text", "image_url"),
        supports_parallel_tool_calls=True,
        supports_tool_schemas=True,
        supports_continuation=continuation,
    )


def _capability_constructor_fields() -> dict[str, Any]:
    return {
        "target": RequestTarget("fixture", "model", "transport", "api"),
        "supported_features": ("text",),
        "reasoning_modes": ("drop",),
        "multimodal_types": ("text",),
        "supports_parallel_tool_calls": False,
        "supports_tool_schemas": False,
        "supports_continuation": False,
        "max_input_units": 4096,
    }


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("supported_features", "text"),
        ("supported_features", {"text": True}),
        ("supported_features", {"text"}),
        ("supported_features", ("text", 1)),
        ("supported_features", ()),
        ("supported_features", ("text", "text")),
        ("supported_features", ("text", "unknown_feature")),
        ("reasoning_modes", ("unknown_mode",)),
        ("multimodal_types", ("unknown_media",)),
        ("supports_parallel_tool_calls", "true"),
        ("supports_tool_schemas", 1),
        ("supports_continuation", []),
        ("max_input_units", 0),
        ("max_input_units", -1),
        ("max_input_units", 1.5),
        ("max_input_units", "4096"),
        ("max_input_units", True),
    ],
)
def test_provider_capabilities_constructor_fails_closed(
    field_name: str,
    invalid_value: Any,
) -> None:
    fields = _capability_constructor_fields()
    fields[field_name] = invalid_value

    with pytest.raises(CodecError):
        ProviderCapabilities(**fields)


def test_provider_capabilities_constructor_shape_errors_are_typed() -> None:
    with pytest.raises(CodecError):
        ProviderCapabilities()

    fields = _capability_constructor_fields()
    with pytest.raises(CodecError):
        ProviderCapabilities(**fields, unsupported_toggle=True)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("supported_features", "text"),
        ("reasoning_modes", {"drop": True}),
        ("multimodal_types", ["text", 1]),
        ("supports_parallel_tool_calls", 1),
        ("supports_tool_schemas", "false"),
        ("supports_continuation", 0),
        ("max_input_units", -10),
    ],
)
def test_provider_capabilities_persisted_reader_normalizes_malformed_inputs(
    field_name: str,
    invalid_value: Any,
) -> None:
    payload = _capabilities().to_dict()
    payload[field_name] = invalid_value

    with pytest.raises(CodecError):
        ProviderCapabilities.from_dict(payload)


class _MalformedCapabilityAdapter:
    model = "fixture-model"

    def __init__(self, declaration: Any) -> None:
        self.declaration = declaration

    def qitos_request_target(self) -> RequestTarget:
        return RequestTarget("fixture", self.model, "fixture", "api")

    def qitos_provider_capabilities(self) -> Any:
        if isinstance(self.declaration, Exception):
            raise self.declaration
        return self.declaration


def test_adapter_capability_failures_are_typed_and_hide_raw_exception() -> None:
    rejected = "sk-proj-synthetic-provider-exception"
    adapter = _MalformedCapabilityAdapter(RuntimeError(rejected))

    with pytest.raises(CodecCapabilityError) as caught:
        ProviderCapabilities.from_model(adapter)

    assert rejected not in str(caught.value)


def test_adapter_declaration_uses_the_same_strict_capability_boundary() -> None:
    declaration = _capability_constructor_fields()
    declaration.pop("target")
    declaration["supports_continuation"] = "true"

    with pytest.raises(CodecCapabilityError):
        ProviderCapabilities.from_model(_MalformedCapabilityAdapter(declaration))


@pytest.mark.parametrize(
    ("model_type", "api_mode"),
    [
        pytest.param("openai", "chat_completions", id="openai-chat"),
        pytest.param("openai", "responses", id="openai-responses"),
        pytest.param("anthropic", "messages", id="anthropic"),
        pytest.param("gemini", "generate_content", id="gemini"),
        pytest.param("litellm", "chat_completions", id="litellm"),
        pytest.param("ollama", "chat", id="ollama"),
    ],
)
def test_declared_provider_matrix_passes_the_same_capability_contract(
    model_type: str,
    api_mode: str,
) -> None:
    from qitos.models.anthropic import AnthropicModel
    from qitos.models.gemini import GeminiModel
    from qitos.models.litellm import LiteLLMModel
    from qitos.models.local import OllamaModel
    from qitos.models.openai import OpenAIModel

    classes = {
        "openai": OpenAIModel,
        "anthropic": AnthropicModel,
        "gemini": GeminiModel,
        "litellm": LiteLLMModel,
        "ollama": OllamaModel,
    }
    model_class = classes[model_type]
    model = object.__new__(model_class)
    model.model = "fixture-model"
    model.api_mode = api_mode
    model.context_window = 4096

    capabilities = ProviderCapabilities.from_model(model)

    assert capabilities.target.api_mode == api_mode
    assert ProviderCapabilities.from_dict(capabilities.to_dict()) == capabilities


class FixtureCodec:
    codec_id = "fixture.responses"
    codec_version = "v1"

    def encode(
        self,
        request: RequestView,
        *,
        capabilities: Optional[ProviderCapabilities] = None,
        transport: Optional[RequestTarget] = None,
        allow_loss: bool = False,
    ) -> tuple[Dict[str, Any], CodecReport]:
        resolved = capabilities or _capabilities()
        assert transport is None or transport == request.target
        payload = {
            "model": request.target.model,
            "input": list(request.selected_items),
            "continuation_ref": (
                request.continuation.reference_id.value if request.continuation else None
            ),
        }
        report = report_for_request(
            request,
            resolved,
            codec_id=self.codec_id,
            codec_version=self.codec_version,
            reasoning="preserved",
            continuation="applied" if request.continuation else "not_requested",
            supported=request.capability_requirements,
        )
        return validate_codec_result(payload, report, allow_loss=allow_loss)


def test_single_codec_protocol_and_lossless_report_round_trip() -> None:
    codec = FixtureCodec()
    assert isinstance(codec, ProviderCodec)
    payload, report = codec.encode(_request(continuation=True))

    assert payload["continuation_ref"] == (
        "continuation_30000000000000000000000000000001"
    )
    assert report.lossless is True
    assert report.continuation == "applied"
    assert report.context_selected == ("codec_context",)
    assert CodecReport.from_dict(report.to_dict()) == report
    assert json.loads(json.dumps(report.to_dict(), allow_nan=False))


def test_capability_mismatch_is_typed_and_not_silent() -> None:
    request = _request(continuation=True)
    report = report_for_request(
        request,
        _capabilities(continuation=False),
        codec_id="fixture.responses",
        codec_version="v1",
        reasoning="preserved",
        continuation="rejected",
    )

    assert capability_mismatches(request, _capabilities(continuation=False)) == (
        "continuation",
    )
    with pytest.raises(CodecCapabilityError) as exc_info:
        validate_codec_result({}, report)
    assert exc_info.value.report is report


def test_lossy_codec_requires_explicit_allow_loss_and_reports_every_loss() -> None:
    request = _request()
    report = report_for_request(
        request,
        _capabilities(),
        codec_id="fixture.lossy",
        codec_version="v1",
        reasoning="dropped",
        continuation="not_requested",
        lossy_fields=("assistant.reasoning", "multimodal.image"),
        warnings=("provider transport cannot represent these fields",),
    )
    with pytest.raises(CodecLossError):
        validate_codec_result({"messages": []}, report)

    payload, accepted = validate_codec_result(
        {"messages": []}, report, allow_loss=True
    )
    assert payload == {"messages": []}
    assert accepted.lossy_fields == (
        "assistant.reasoning",
        "multimodal.image",
    )
    assert accepted.lossless is False


def test_stateless_continuation_fallback_is_explicit_in_report() -> None:
    request = _request(continuation=True)
    report = report_for_request(
        request,
        _capabilities(),
        codec_id="fixture.responses",
        codec_version="v1",
        reasoning="preserved",
        continuation="fallback_to_stateless_replay",
        fallback="stateless_replay",
        warnings=("continuation resolver returned expired",),
    )
    assert report.fallback == "stateless_replay"
    assert report.continuation == "fallback_to_stateless_replay"


def test_provider_failure_is_typed_and_cannot_be_assistant_text() -> None:
    failure = ProviderFailure(
        category="provider_refusal",
        message="request refused",
        provider="openai",
        api_mode="responses",
        retryable=False,
        status_code=400,
        error_code="content_policy",
        redacted_details={"request_id": "logical-request"},
    )

    assert isinstance(failure, Exception)
    assert not isinstance(failure, str)
    assert failure.to_dict()["category"] == "provider_refusal"
    with pytest.raises(ProviderFailure):
        raise failure


@pytest.mark.parametrize(
    "category",
    ["provider_refusal", "provider_exception", "malformed_response"],
)
def test_provider_failure_categories_remain_stable(category: str) -> None:
    failure = ProviderFailure(
        category=category,
        message="redacted provider failure",
        provider="fixture",
        api_mode="fixture",
    )
    assert failure.to_dict()["category"] == category


def test_codec_report_reader_rejects_unknown_version_field_and_non_json_payload() -> None:
    request = _request()
    report = report_for_request(
        request,
        _capabilities(),
        codec_id="fixture",
        codec_version="v1",
        reasoning="preserved",
        continuation="not_requested",
    )
    unknown = {**report.to_dict(), "unknown": True}
    with pytest.raises(CodecError):
        CodecReport.from_dict(unknown)
    wrong = report.to_dict()
    wrong["schema_version"] = "qitos.codec_report/v999"
    with pytest.raises(CodecError):
        CodecReport.from_dict(wrong)
    with pytest.raises(CodecError):
        validate_codec_result({"bad": object()}, report)
    with pytest.raises(CodecError):
        validate_codec_result({"bad": float("nan")}, report)


class OpenAIResponsesFixtureModel:
    model = "fixture-model"
    api_mode = "responses"
    context_window = 128_000

    def qitos_request_target(self) -> RequestTarget:
        return RequestTarget("declared-fixture", self.model, "fixture", self.api_mode)

    def qitos_provider_capabilities(self) -> dict[str, Any]:
        return {
            "supported_features": (
                "text",
                "multimodal",
                "tool_calls",
                "tool_results",
                "tool_schemas",
                "parallel_tool_calls",
                "reasoning",
                "continuation",
            ),
            "reasoning_modes": (
                "preserve_if_supported",
                "native_item_continuation",
                "drop",
            ),
            "multimodal_types": ("text", "image_url"),
            "supports_parallel_tool_calls": True,
            "supports_tool_schemas": True,
            "supports_continuation": True,
            "max_input_units": self.context_window,
        }

    def supports_tool_schema_delivery(self, delivery: str) -> bool:
        return delivery == "api_parameter"

    def supports_multimodal_input(self) -> bool:
        return True


def test_model_provider_capabilities_are_derived_without_caller_matrix() -> None:
    capabilities = ProviderCapabilities.from_model(OpenAIResponsesFixtureModel())

    assert capabilities.target == RequestTarget(
        "declared-fixture", "fixture-model", "fixture", "responses"
    )
    assert capabilities.supports_continuation is True
    assert capabilities.supports_parallel_tool_calls is True
    assert "multimodal" in capabilities.supported_features
    assert ProviderCapabilities.from_dict(capabilities.to_dict()) == capabilities


def test_stable_fixture_codec_report_is_strictly_readable() -> None:
    fixture_path = (
        Path(__file__).parents[1]
        / "fixtures"
        / "conversation"
        / "request_contracts.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    report = CodecReport.from_dict(fixture["samples"]["codec_report"])
    assert report.lossless is True
    assert report.codec_id == "fixture.responses"

    evidence = json.loads(
        fixture_path.with_name("request-contracts-evidence.json").read_text(
            encoding="utf-8"
        )
    )
    assert evidence["contract_id"] == "qitos.request_contract_bundle"
    assert evidence["contract_version"] == "qitos.request_contract_bundle/v1"
    assert evidence["fixture_path"] == (
        "tests/fixtures/conversation/request_contracts.json"
    )
    assert evidence["qualification_authority"] == "qitos.s1.integration_owner/v1"
    assert evidence["qualified"] is True
    assert evidence["lineage_evidence"] == {
        "status": "explicit",
        "edge_source": "producer_fact",
        "inferred": False,
    }
