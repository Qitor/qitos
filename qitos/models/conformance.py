"""Reusable structural conformance checks for third-party provider adapters.

The runner deliberately depends only on extension-facing contracts.  It never
reads Engine state, provider credentials, endpoints, SDK response objects, or
adapter-private attributes, and its report contains capability and digest
facts rather than request/response bodies.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from ..core.conversation import AssistantContent, ReasoningBlock, ReasoningReference
from ..core.request_view import RequestView
from .codec import CodecReport, ProviderCapabilities, ProviderFailure
from .provider import (
    ProviderAdapter,
    ProviderDecodedResponse,
    ProviderTransaction,
    execute_provider_request,
    normalize_provider_failure,
)


PROVIDER_CONFORMANCE_SCHEMA_VERSION = "qitos.provider_conformance/v1"
_SENSITIVE_KEY = re.compile(
    r"(?:^|[_-])(?:authorization|api[_-]?key|credential|password|secret|cookie|"
    r"headers?|access[_-]?token|refresh[_-]?token)(?:$|[_-])",
    re.IGNORECASE,
)


class ProviderConformanceError(AssertionError):
    """A structural provider extension failed a declared conformance fact."""


@dataclass(frozen=True)
class ProviderConformanceCase:
    request: RequestView
    sample_response: Any
    expected_part_kinds: tuple[str, ...] = ()
    expect_parallel_tools: bool = False
    expect_reasoning: bool = False
    expect_multimodal: bool = False
    expect_continuation: bool = False
    expect_usage: bool = False
    exercise_transport: bool = False
    exercise_stream: bool = False
    allow_loss: bool = False


@dataclass(frozen=True)
class ProviderConformanceReport:
    target_digest: str
    codec_id: str
    codec_version: str
    capability_digest: str
    checks: tuple[str, ...]
    transaction: Optional[ProviderTransaction] = None
    schema_version: str = PROVIDER_CONFORMANCE_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Return a secret-free report; the optional transaction is excluded."""

        return {
            "schema_version": self.schema_version,
            "target_digest": self.target_digest,
            "codec_id": self.codec_id,
            "codec_version": self.codec_version,
            "capability_digest": self.capability_digest,
            "checks": list(self.checks),
        }


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _assert_projection_safe(value: Any, path: str = "payload") -> None:
    if value is None or type(value) in {str, bool, int, float}:
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_projection_safe(item, f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProviderConformanceError(
                    "provider projection contains a non-string key"
                )
            if _SENSITIVE_KEY.search(key):
                raise ProviderConformanceError(
                    "provider codec projection contains credential material"
                )
            _assert_projection_safe(item, f"{path}.[field]")
        return
    raise ProviderConformanceError(
        f"{path} contains a non-JSON transport value"
    )


def _assert_decoded_semantics(
    decoded: ProviderDecodedResponse,
    capabilities: ProviderCapabilities,
    case: ProviderConformanceCase,
) -> None:
    kinds = tuple(part.kind for part in decoded.parts)
    if case.expected_part_kinds and kinds != case.expected_part_kinds:
        raise ProviderConformanceError("decoded assistant part order is incorrect")
    tool_count = sum(part.kind == "tool_call" for part in decoded.parts)
    if case.expect_parallel_tools:
        if not capabilities.supports_parallel_tool_calls or tool_count < 2:
            raise ProviderConformanceError(
                "parallel tool-call declaration or decode is inconsistent"
            )
    reasoning_present = any(
        isinstance(part, (ReasoningBlock, ReasoningReference))
        for part in decoded.parts
    )
    if case.expect_reasoning and (
        not capabilities.supports_reasoning_output or not reasoning_present
    ):
        raise ProviderConformanceError(
            "reasoning output declaration or decode is inconsistent"
        )
    multimodal_present = any(
        isinstance(part, AssistantContent) and part.block.type != "text"
        for part in decoded.parts
    )
    if case.expect_multimodal and (
        not capabilities.supports_multimodal_input or not multimodal_present
    ):
        raise ProviderConformanceError(
            "multimodal declaration or decode is inconsistent"
        )
    if case.expect_continuation and (
        not capabilities.supports_continuation
        or decoded.continuation_payload is None
    ):
        raise ProviderConformanceError(
            "continuation declaration or decode is inconsistent"
        )
    if case.expect_usage and (
        not capabilities.supports_usage or decoded.usage is None
    ):
        raise ProviderConformanceError("usage declaration or decode is inconsistent")


def run_provider_conformance(
    adapter: ProviderAdapter,
    case: ProviderConformanceCase,
) -> ProviderConformanceReport:
    """Run deterministic encode/decode and optional transport conformance.

    Only capabilities declared by the adapter are tested.  Provider-specific
    behaviors are opt-in facts on ``ProviderConformanceCase``.
    """

    capabilities = ProviderCapabilities.from_model(adapter)
    if capabilities.target != case.request.target:
        raise ProviderConformanceError("adapter and request targets differ")
    persisted_capabilities = ProviderCapabilities.from_dict(
        capabilities.to_dict()
    )
    if persisted_capabilities != capabilities:
        raise ProviderConformanceError("capabilities do not round-trip")
    codec = adapter.qitos_provider_codec()
    payload, codec_report = codec.encode(
        case.request,
        capabilities=capabilities,
        transport=case.request.target,
        allow_loss=case.allow_loss,
    )
    _assert_projection_safe(payload)
    if CodecReport.from_dict(codec_report.to_dict()) != codec_report:
        raise ProviderConformanceError("codec report does not round-trip")
    if RequestView.from_dict(case.request.to_dict()) != case.request:
        raise ProviderConformanceError("request view does not round-trip")
    decoded = codec.decode(case.sample_response, request=case.request)
    if not isinstance(decoded, ProviderDecodedResponse):
        raise ProviderConformanceError(
            "codec decode must return ProviderDecodedResponse"
        )
    _assert_decoded_semantics(decoded, capabilities, case)

    transaction: Optional[ProviderTransaction] = None
    stream_deltas: list[str] = []
    if case.exercise_stream:
        if not capabilities.supports_streaming:
            raise ProviderConformanceError(
                "stream conformance requested for an undeclared capability"
            )
        transaction = execute_provider_request(
            adapter,
            case.request,
            allow_loss=case.allow_loss,
            stream_callback=stream_deltas.append,
        )
        if not stream_deltas:
            raise ProviderConformanceError("declared stream emitted no deltas")
    elif case.exercise_transport:
        transaction = execute_provider_request(
            adapter,
            case.request,
            allow_loss=case.allow_loss,
        )

    checks = [
        "adapter_structure",
        "capability_vocabulary",
        "encode",
        "safe_projection",
        "decode",
        "message_order",
        "canonical_serialization_isolation",
        "loss_policy",
    ]
    if case.expect_parallel_tools:
        checks.append("parallel_tool_calls")
    if case.expect_reasoning:
        checks.append("reasoning")
    if case.expect_multimodal:
        checks.append("multimodal")
    if case.expect_continuation:
        checks.append("continuation")
    if case.expect_usage:
        checks.append("usage")
    if case.exercise_transport:
        checks.append("transport")
    if case.exercise_stream:
        checks.append("streaming")
    return ProviderConformanceReport(
        target_digest=_digest(case.request.target.to_dict()),
        codec_id=str(codec.codec_id),
        codec_version=str(codec.codec_version),
        capability_digest=_digest(capabilities.to_dict()),
        checks=tuple(checks),
        transaction=transaction,
    )


def run_provider_failure_conformance(
    adapter: ProviderAdapter,
    error: BaseException,
) -> ProviderFailure:
    """Verify that adapter failure normalization is typed and non-echoing."""

    capabilities = ProviderCapabilities.from_model(adapter)
    normalized = adapter.qitos_normalize_failure(error, report=None)
    if not isinstance(normalized, ProviderFailure):
        normalized = normalize_provider_failure(
            error,
            target=capabilities.target,
        )
    rendered = json.dumps(normalized.to_dict(), ensure_ascii=False, sort_keys=True)
    raw = str(error)
    if raw and raw in rendered:
        raise ProviderConformanceError("provider failure echoed raw exception text")
    return normalized


__all__ = [
    "PROVIDER_CONFORMANCE_SCHEMA_VERSION",
    "ProviderConformanceError",
    "ProviderConformanceCase",
    "ProviderConformanceReport",
    "run_provider_conformance",
    "run_provider_failure_conformance",
]
