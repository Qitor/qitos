"""Single provider-codec and typed provider-failure contracts.

Concrete codecs live beside their provider transports.  This module defines
only their shared boundary and reporting vocabulary; it does not compile one
provider's payload on behalf of another provider.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, Optional, Protocol, runtime_checkable

from ..core.request_view import RequestTarget, RequestView


CODEC_REPORT_SCHEMA_VERSION = "qitos.codec_report/v1"
PROVIDER_CAPABILITIES_SCHEMA_VERSION = "qitos.provider_capabilities/v1"
PROVIDER_FAILURE_SCHEMA_VERSION = "qitos.provider_failure/v1"


class CodecError(RuntimeError):
    code = "codec_error"

    def __init__(self, message: str, *, report: Optional["CodecReport"] = None):
        super().__init__(message)
        self.report = report


class CodecCapabilityError(CodecError):
    code = "codec_capability_mismatch"


class CodecLossError(CodecError):
    code = "codec_loss_rejected"


class CodecUnavailableError(CodecError):
    code = "codec_unavailable"


def _strict_json(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        import math

        if not math.isfinite(value):
            raise CodecError(f"{path} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _strict_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CodecError(f"{path} keys must be strings")
            _strict_json(item, f"{path}.{key}")
        return
    raise CodecError(f"{path} contains non-JSON value {type(value).__name__}")


def _object(
    value: Any,
    *,
    path: str,
    fields: frozenset[str],
    required: Optional[frozenset[str]] = None,
) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise CodecError(f"{path} must be an object with string keys")
    data = dict(value)
    unknown = sorted(set(data) - fields)
    if unknown:
        raise CodecError(f"{path} has unknown field {unknown[0]!r}")
    missing = sorted((required or fields) - set(data))
    if missing:
        raise CodecError(f"{path} is missing field {missing[0]!r}")
    return data


@dataclass(frozen=True)
class ProviderCapabilities:
    target: RequestTarget
    supported_features: tuple[str, ...]
    reasoning_modes: tuple[str, ...]
    multimodal_types: tuple[str, ...]
    supports_parallel_tool_calls: bool
    supports_tool_schemas: bool
    supports_continuation: bool
    max_input_units: Optional[int] = None
    schema_version: str = PROVIDER_CAPABILITIES_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PROVIDER_CAPABILITIES_SCHEMA_VERSION:
            raise CodecError(
                f"unsupported provider capabilities schema: {self.schema_version!r}"
            )

    @classmethod
    def from_model(cls, model: Any) -> "ProviderCapabilities":
        """Derive conservative defaults from the configured model/transport."""

        target = RequestTarget.from_model(model)
        supports_tools = False
        probe = getattr(model, "supports_tool_schema_delivery", None)
        if callable(probe):
            try:
                supports_tools = bool(probe("api_parameter"))
            except Exception:
                supports_tools = False
        supports_multimodal = False
        multimodal_probe = getattr(model, "supports_multimodal_input", None)
        if callable(multimodal_probe):
            try:
                supports_multimodal = bool(multimodal_probe())
            except Exception:
                supports_multimodal = False
        responses = target.transport == "openai" and target.api_mode == "responses"
        features = {"text"}
        if supports_tools:
            features.update({"tool_calls", "tool_results", "tool_schemas"})
        if supports_multimodal:
            features.add("multimodal")
        if responses:
            features.update({"reasoning", "continuation"})
        context_window = getattr(model, "context_window", None)
        return cls(
            target=target,
            supported_features=tuple(sorted(features)),
            reasoning_modes=(
                ("preserve_if_supported", "native_item_continuation", "drop")
                if responses
                else ("drop",)
            ),
            multimodal_types=(
                ("text", "image_url", "image_base64", "image_file")
                if supports_multimodal
                else ("text",)
            ),
            supports_parallel_tool_calls=supports_tools,
            supports_tool_schemas=supports_tools,
            supports_continuation=responses,
            max_input_units=(
                int(context_window)
                if isinstance(context_window, int) and context_window > 0
                else None
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "target": self.target.to_dict(),
            "supported_features": list(self.supported_features),
            "reasoning_modes": list(self.reasoning_modes),
            "multimodal_types": list(self.multimodal_types),
            "supports_parallel_tool_calls": self.supports_parallel_tool_calls,
            "supports_tool_schemas": self.supports_tool_schemas,
            "supports_continuation": self.supports_continuation,
            "max_input_units": self.max_input_units,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ProviderCapabilities":
        fields = frozenset(
            {
                "schema_version",
                "target",
                "supported_features",
                "reasoning_modes",
                "multimodal_types",
                "supports_parallel_tool_calls",
                "supports_tool_schemas",
                "supports_continuation",
                "max_input_units",
            }
        )
        data = _object(value, path="provider_capabilities", fields=fields)
        data["target"] = RequestTarget.from_dict(data["target"])
        for name in ("supported_features", "reasoning_modes", "multimodal_types"):
            data[name] = tuple(data[name])
        return cls(**data)


@dataclass(frozen=True)
class CodecReport:
    codec_id: str
    codec_version: str
    request_id: str
    target: RequestTarget
    supported: tuple[str, ...]
    unsupported: tuple[str, ...]
    reasoning: str
    multimodal_conversion: tuple[str, ...]
    tool_schema_conversion: tuple[str, ...]
    continuation: str
    context_selected: tuple[str, ...]
    context_omitted: tuple[str, ...]
    compaction_receipts: tuple[str, ...]
    lossy_fields: tuple[str, ...]
    warnings: tuple[str, ...]
    fallback: str = "none"
    schema_version: str = CODEC_REPORT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CODEC_REPORT_SCHEMA_VERSION:
            raise CodecError(f"unsupported codec report: {self.schema_version!r}")
        if self.fallback not in {"none", "stateless_replay"}:
            raise CodecError(f"unsupported codec fallback: {self.fallback!r}")

    @property
    def lossless(self) -> bool:
        return not self.lossy_fields and not self.unsupported

    def assert_acceptable(self, *, allow_loss: bool = False) -> None:
        if self.unsupported:
            raise CodecCapabilityError(
                f"codec cannot express required capabilities: {list(self.unsupported)}",
                report=self,
            )
        if self.lossy_fields and not allow_loss:
            raise CodecLossError(
                f"codec would lose fields: {list(self.lossy_fields)}",
                report=self,
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "codec_id": self.codec_id,
            "codec_version": self.codec_version,
            "request_id": self.request_id,
            "target": self.target.to_dict(),
            "supported": list(self.supported),
            "unsupported": list(self.unsupported),
            "reasoning": self.reasoning,
            "multimodal_conversion": list(self.multimodal_conversion),
            "tool_schema_conversion": list(self.tool_schema_conversion),
            "continuation": self.continuation,
            "context_selected": list(self.context_selected),
            "context_omitted": list(self.context_omitted),
            "compaction_receipts": list(self.compaction_receipts),
            "lossy_fields": list(self.lossy_fields),
            "warnings": list(self.warnings),
            "fallback": self.fallback,
            "lossless": self.lossless,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "CodecReport":
        fields = frozenset(
            {
                "schema_version",
                "codec_id",
                "codec_version",
                "request_id",
                "target",
                "supported",
                "unsupported",
                "reasoning",
                "multimodal_conversion",
                "tool_schema_conversion",
                "continuation",
                "context_selected",
                "context_omitted",
                "compaction_receipts",
                "lossy_fields",
                "warnings",
                "fallback",
                "lossless",
            }
        )
        data = _object(value, path="codec_report", fields=fields)
        reported_lossless = data.pop("lossless")
        data["target"] = RequestTarget.from_dict(data["target"])
        for name in (
            "supported",
            "unsupported",
            "multimodal_conversion",
            "tool_schema_conversion",
            "context_selected",
            "context_omitted",
            "compaction_receipts",
            "lossy_fields",
            "warnings",
        ):
            data[name] = tuple(data[name])
        result = cls(**data)
        if result.lossless is not reported_lossless:
            raise CodecError("codec report lossless flag is inconsistent")
        return result


@runtime_checkable
class ProviderCodec(Protocol):
    """The only request encoder extension point used by provider adapters."""

    codec_id: str
    codec_version: str

    def encode(
        self,
        request: RequestView,
        *,
        capabilities: Optional[ProviderCapabilities] = None,
        transport: Optional[RequestTarget] = None,
        allow_loss: bool = False,
    ) -> tuple[Dict[str, Any], CodecReport]:
        ...


@dataclass(frozen=True)
class ProviderFailure(Exception):
    """Typed provider boundary; never converted into assistant-authored text."""

    category: str
    message: str
    provider: str
    api_mode: str
    retryable: bool = False
    status_code: Optional[int] = None
    error_code: Optional[str] = None
    redacted_details: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = PROVIDER_FAILURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _strict_json(dict(self.redacted_details), "provider_failure.redacted_details")
        Exception.__init__(self, self.message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "category": self.category,
            "message": self.message,
            "provider": self.provider,
            "api_mode": self.api_mode,
            "retryable": self.retryable,
            "status_code": self.status_code,
            "error_code": self.error_code,
            "redacted_details": json.loads(
                json.dumps(dict(self.redacted_details), allow_nan=False)
            ),
        }


def validate_codec_result(
    payload: Dict[str, Any],
    report: CodecReport,
    *,
    allow_loss: bool = False,
) -> tuple[Dict[str, Any], CodecReport]:
    """Validate ownership/JSON/loss boundaries shared by every codec."""

    _strict_json(payload, "provider_payload")
    report.assert_acceptable(allow_loss=allow_loss)
    isolated = json.loads(json.dumps(payload, ensure_ascii=False, allow_nan=False))
    return isolated, CodecReport.from_dict(report.to_dict())


def capability_mismatches(
    request: RequestView, capabilities: ProviderCapabilities
) -> tuple[str, ...]:
    """Return deterministic missing features for codec report construction."""

    if capabilities.target != request.target:
        return ("target_identity",)
    supported = set(capabilities.supported_features)
    missing = set(request.capability_requirements) - supported
    if request.continuation is not None and not capabilities.supports_continuation:
        missing.add("continuation")
    if (
        "parallel_tool_calls" in request.capability_requirements
        and not capabilities.supports_parallel_tool_calls
    ):
        missing.add("parallel_tool_calls")
    if request.tool_schemas and not capabilities.supports_tool_schemas:
        missing.add("tool_schemas")
    if request.reasoning_policy.mode not in capabilities.reasoning_modes:
        missing.add(f"reasoning:{request.reasoning_policy.mode}")
    return tuple(sorted(missing))


def report_for_request(
    request: RequestView,
    capabilities: ProviderCapabilities,
    *,
    codec_id: str,
    codec_version: str,
    reasoning: str,
    continuation: str,
    supported: Iterable[str] = (),
    multimodal_conversion: Iterable[str] = (),
    tool_schema_conversion: Iterable[str] = (),
    lossy_fields: Iterable[str] = (),
    warnings: Iterable[str] = (),
    fallback: str = "none",
) -> CodecReport:
    """Small provider-side helper for consistent complete reports."""

    return CodecReport(
        codec_id=codec_id,
        codec_version=codec_version,
        request_id=request.request_id,
        target=request.target,
        supported=tuple(sorted(set(supported))),
        unsupported=capability_mismatches(request, capabilities),
        reasoning=reasoning,
        multimodal_conversion=tuple(multimodal_conversion),
        tool_schema_conversion=tuple(tool_schema_conversion),
        continuation=continuation,
        context_selected=request.selection.selected_context_ids,
        context_omitted=request.selection.omitted_context_ids,
        compaction_receipts=tuple(
            item.receipt_id for item in request.compaction_receipts
        ),
        lossy_fields=tuple(lossy_fields),
        warnings=tuple(warnings),
        fallback=fallback,
    )


__all__ = [
    "CODEC_REPORT_SCHEMA_VERSION",
    "PROVIDER_CAPABILITIES_SCHEMA_VERSION",
    "PROVIDER_FAILURE_SCHEMA_VERSION",
    "CodecError",
    "CodecCapabilityError",
    "CodecLossError",
    "CodecUnavailableError",
    "ProviderCapabilities",
    "CodecReport",
    "ProviderCodec",
    "ProviderFailure",
    "validate_codec_result",
    "capability_mismatches",
    "report_for_request",
]
