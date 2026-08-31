from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Mapping, Optional

import pytest

from qitos.core.conversation import AssistantContent, ExchangeLog, UserItem
from qitos.core.multimodal import ContentBlock
from qitos.core.request_view import (
    ContinuationRef,
    IncompatibleContinuationError,
    RequestTarget,
    RequestView,
)
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
    execute_provider_request,
    normalize_provider_failure,
)


TARGET = RequestTarget("continuation", "model-a", "wire", "native")


def _log() -> ExchangeLog:
    log = ExchangeLog(log_id="continuation-log")
    log.append(
        UserItem(
            item_id="continuation-user",
            exchange_id="continuation-exchange",
            content=[ContentBlock(type="text", text="continue")],
        )
    )
    return log


def _request(reference: Optional[ContinuationRef] = None) -> RequestView:
    return RequestView.from_exchange_log(
        _log(), target=TARGET, continuation=reference
    )


class ContinuationCodec:
    codec_id = "x.fixture.continuation"
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
            reasoning="not_requested",
            continuation=(
                "resolver_required" if request.continuation else "not_requested"
            ),
            supported=request.capability_requirements,
        )
        return validate_codec_result(
            {"input": list(request.selected_items)},
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
        updated["native_continuation"] = resolution.payload
        return updated, replace(report, continuation="applied")

    def decode(
        self, response: Any, *, request: RequestView
    ) -> ProviderDecodedResponse:
        _ = request
        assert response["accepted"] is True
        return ProviderDecodedResponse(
            parts=(
                AssistantContent(ContentBlock(type="text", text="continued")),
            ),
            finish_reason="stop",
        )


class ContinuationAdapter:
    qitos_continuation_resolver = None

    def __init__(self) -> None:
        self.last_payload: Optional[Mapping[str, Any]] = None

    def qitos_request_target(self) -> RequestTarget:
        return TARGET

    def qitos_provider_capabilities(self) -> Mapping[str, Any]:
        return {
            "supported_features": ("text", "continuation"),
            "reasoning_modes": ("preserve_if_supported", "drop"),
            "multimodal_types": ("text",),
            "supports_parallel_tool_calls": False,
            "supports_tool_schemas": False,
            "supports_continuation": True,
            "max_input_units": 4096,
        }

    def qitos_provider_codec(self) -> ContinuationCodec:
        return ContinuationCodec()

    def qitos_transport(self, payload: Mapping[str, Any]) -> Any:
        self.last_payload = payload
        return {"accepted": True}

    def qitos_stream_transport(
        self, payload: Mapping[str, Any], *, on_delta: Any = None
    ) -> Any:
        _ = on_delta
        return self.qitos_transport(payload)

    def qitos_normalize_failure(
        self,
        error: BaseException,
        *,
        report: Optional[CodecReport] = None,
    ) -> ProviderFailure:
        return normalize_provider_failure(error, target=TARGET, report=report)


def test_resolver_capture_round_trip_isolated_payload_and_digest() -> None:
    resolver = InMemoryContinuationResolver("continuation:fixture")
    original = {"encrypted": ["opaque"]}
    reference = resolver.capture(
        target=TARGET,
        payload=original,
        attachment_id="continuation-attachment",
    )
    original["encrypted"].append("mutated")

    resolution = resolver.resolve(reference)

    assert resolution.status == "resolved"
    assert resolution.payload == {"encrypted": ["opaque"]}
    assert resolution.payload_digest == reference.payload_digest
    assert "encrypted" not in reference.to_dict()


def test_resolver_reports_missing_expired_and_digest_mismatch() -> None:
    resolver = InMemoryContinuationResolver("continuation:fixture")
    reference = resolver.capture(
        target=TARGET,
        payload={"state": "opaque"},
        attachment_id="continuation-attachment",
    )

    assert resolver.resolve(
        replace(reference, resolver_key="continuation:other")
    ).reason_code == "resolver_key_mismatch"
    assert resolver.resolve(
        replace(reference, payload_digest="b" * 64)
    ).reason_code == "continuation_digest_mismatch"

    expired = resolver.capture(
        target=TARGET,
        payload={"state": "expired"},
        attachment_id="expired-attachment",
        expires_at="2000-01-01T00:00:00Z",
    )
    assert resolver.resolve(expired).status == "expired"


def test_continuation_is_bound_to_provider_model_and_api_mode() -> None:
    resolver = InMemoryContinuationResolver("continuation:fixture")
    reference = resolver.capture(
        target=TARGET,
        payload={"state": "opaque"},
        attachment_id="continuation-attachment",
    )

    with pytest.raises(IncompatibleContinuationError):
        RequestView.from_exchange_log(
            _log(),
            target=RequestTarget("other", "model-a", "wire", "native"),
            continuation=reference,
        )
    with pytest.raises(IncompatibleContinuationError):
        RequestView.from_exchange_log(
            _log(),
            target=RequestTarget("continuation", "model-b", "wire", "native"),
            continuation=reference,
        )
    with pytest.raises(IncompatibleContinuationError):
        RequestView.from_exchange_log(
            _log(),
            target=RequestTarget("continuation", "model-a", "wire", "other"),
            continuation=reference,
        )


def test_transaction_applies_resolved_continuation_before_transport() -> None:
    resolver = InMemoryContinuationResolver("continuation:fixture")
    reference = resolver.capture(
        target=TARGET,
        payload={"state": "opaque"},
        attachment_id="continuation-attachment",
    )
    adapter = ContinuationAdapter()

    transaction = execute_provider_request(
        adapter,
        _request(reference),
        continuation_resolver=resolver,
    )

    assert adapter.last_payload is not None
    assert adapter.last_payload["native_continuation"] == {"state": "opaque"}
    assert transaction.codec_report.continuation == "applied"
    assert transaction.codec_report.lossless is True


def test_unresolved_continuation_rejects_or_records_explicit_stateless_loss() -> None:
    resolver = InMemoryContinuationResolver("continuation:fixture")
    reference = resolver.capture(
        target=TARGET,
        payload={"state": "opaque"},
        attachment_id="continuation-attachment",
    )
    missing = InMemoryContinuationResolver("continuation:fixture")
    adapter = ContinuationAdapter()

    with pytest.raises(ProviderFailure) as caught:
        execute_provider_request(
            adapter,
            _request(reference),
            continuation_resolver=missing,
        )
    assert caught.value.category == "unsupported_request"
    assert caught.value.error_code == "continuation_not_found"

    transaction = execute_provider_request(
        adapter,
        _request(reference),
        continuation_resolver=missing,
        allow_loss=True,
    )
    assert transaction.codec_report.fallback == "stateless_replay"
    assert transaction.codec_report.lossy_fields == ("continuation.state",)
    assert "native_continuation" not in (adapter.last_payload or {})
