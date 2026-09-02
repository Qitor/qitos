"""Single provider-codec and typed provider-failure contracts.

Concrete codecs live beside their provider transports.  This module defines
only their shared boundary and reporting vocabulary; it does not compile one
provider's payload on behalf of another provider.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, NoReturn, Optional, Protocol, runtime_checkable

from ..core.diagnostics import redact_diagnostic_value, safe_diagnostic_text
from ..core.request_view import RequestTarget, RequestView


CODEC_REPORT_SCHEMA_VERSION = "qitos.codec_report/v2"
_HISTORICAL_CODEC_REPORT_SCHEMA_VERSION = "qitos.codec_report/v1"
PROVIDER_CAPABILITIES_SCHEMA_VERSION = "qitos.provider_capabilities/v1"
PROVIDER_FAILURE_SCHEMA_VERSION = "qitos.provider_failure/v1"

_SUPPORTED_FEATURE_VALUES = frozenset(
    {
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
    }
)
_REASONING_MODE_VALUES = frozenset(
    {
        "preserve_if_supported",
        "drop",
        "inline_replay",
        "signed_block_replay",
        "native_item_continuation",
    }
)
_MULTIMODAL_TYPE_VALUES = frozenset(
    {"text", "image_url", "image_base64", "image_file"}
)
_MISSING_CAPABILITY_FIELD = object()
_PROVIDER_FAILURE_CATEGORIES = frozenset(
    {
        "provider_refusal",
        "provider_exception",
        "malformed_response",
        "unsupported_request",
        "authentication",
        "rate_limit",
        "timeout",
        "transport",
        "cancelled",
    }
)


class CodecError(RuntimeError):
    code = "codec_error"

    def __init__(self, message: str, *, report: Optional["CodecReport"] = None):
        super().__init__(message)
        self.report = report


class CodecCapabilityError(CodecError):
    code = "codec_capability_mismatch"
    diagnostic_code = "provider_capability_loss"


class CodecLossError(CodecError):
    code = "codec_loss_rejected"
    diagnostic_code = "lossy_fallback_not_authorized"


class CodecUnavailableError(CodecError):
    code = "codec_unavailable"


class _JSONMaterializationError(CodecCapabilityError):
    """Typed, non-echoing failure for the provider JSON boundary."""

    def __init__(self, path: str, category: str, *, code: str) -> None:
        self.code = code
        self.field_path = path
        self.category = category
        super().__init__(f"{path}: {category}")


def _safe_path_child(path: str, key: str) -> str:
    safe_key = safe_diagnostic_text(key, fallback="[redacted-key]")
    if (
        safe_key == key
        and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}", key)
    ):
        return f"{path}.{key}"
    return f"{path}.[redacted-key]"


def _materialize_json_transport(
    value: Any,
    path: str,
    *,
    error_code: str,
    max_depth: int = 64,
    max_nodes: int = 10000,
) -> Any:
    """Create one bounded, ownership-isolated JSON tree for provider transport.

    This is the sole recursive thaw/admission implementation used by the codec
    and provider boundary. It accepts immutable ``Mapping`` and tuple inputs
    while rejecting values that JSON cannot faithfully represent.
    """

    active: set[int] = set()
    node_count = 0

    def fail(current_path: str, category: str) -> NoReturn:
        raise _JSONMaterializationError(
            current_path,
            category,
            code=error_code,
        )

    def visit(item: Any, current_path: str, depth: int) -> Any:
        nonlocal node_count
        if depth > max_depth:
            fail(current_path, "depth_limit_exceeded")
        node_count += 1
        if node_count > max_nodes:
            fail(current_path, "node_limit_exceeded")
        if item is None or type(item) in {str, bool, int}:
            return item
        if type(item) is float:
            import math

            if not math.isfinite(item):
                fail(current_path, "non_finite_number")
            return item
        if isinstance(item, Mapping):
            identity = id(item)
            if identity in active:
                fail(current_path, "cycle_detected")
            active.add(identity)
            try:
                result: Dict[str, Any] = {}
                for key, child in item.items():
                    if type(key) is not str:
                        fail(current_path, "non_string_key")
                    child_path = _safe_path_child(current_path, key)
                    result[key] = visit(child, child_path, depth + 1)
                return result
            finally:
                active.remove(identity)
        if isinstance(item, (list, tuple)):
            identity = id(item)
            if identity in active:
                fail(current_path, "cycle_detected")
            active.add(identity)
            try:
                return [
                    visit(child, f"{current_path}[{index}]", depth + 1)
                    for index, child in enumerate(item)
                ]
            finally:
                active.remove(identity)
        fail(current_path, "unsupported_type")

    if max_depth < 0 or max_nodes < 1:
        raise ValueError("JSON materialization limits must be positive")
    return visit(value, path, 0)


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


def _capability_sequence(
    value: Any,
    *,
    field_name: str,
    allowed: frozenset[str],
    allow_namespaced_extensions: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise CodecError(f"{field_name} must be an explicit string sequence")
    if not value:
        raise CodecError(f"{field_name} must not be empty")
    if any(not isinstance(item, str) or not item for item in value):
        raise CodecError(f"{field_name} must contain non-empty strings")
    normalized = tuple(value)
    if len(normalized) != len(set(normalized)):
        raise CodecError(f"{field_name} must not contain duplicates")
    if any(
        item not in allowed
        and not (
            allow_namespaced_extensions
            and re.fullmatch(r"x\.[a-z0-9][a-z0-9_.-]{2,127}", item)
        )
        for item in normalized
    ):
        raise CodecError(f"{field_name} contains an unsupported capability value")
    return normalized


def _capability_bool(value: Any, *, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise CodecError(f"{field_name} must be boolean")
    return value


def _max_input_units(value: Any) -> Optional[int]:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise CodecError("max_input_units must be a positive integer or null")
    return value


@dataclass(frozen=True, init=False)
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

    def __init__(
        self,
        target: Any = _MISSING_CAPABILITY_FIELD,
        supported_features: Any = _MISSING_CAPABILITY_FIELD,
        reasoning_modes: Any = _MISSING_CAPABILITY_FIELD,
        multimodal_types: Any = _MISSING_CAPABILITY_FIELD,
        supports_parallel_tool_calls: Any = _MISSING_CAPABILITY_FIELD,
        supports_tool_schemas: Any = _MISSING_CAPABILITY_FIELD,
        supports_continuation: Any = _MISSING_CAPABILITY_FIELD,
        max_input_units: Any = None,
        schema_version: Any = PROVIDER_CAPABILITIES_SCHEMA_VERSION,
        **unexpected: Any,
    ) -> None:
        required = (
            target,
            supported_features,
            reasoning_modes,
            multimodal_types,
            supports_parallel_tool_calls,
            supports_tool_schemas,
            supports_continuation,
        )
        if unexpected:
            raise CodecError("provider capabilities constructor has unexpected fields")
        if any(value is _MISSING_CAPABILITY_FIELD for value in required):
            raise CodecError("provider capabilities constructor is missing required fields")
        for field_name, value in (
            ("target", target),
            ("supported_features", supported_features),
            ("reasoning_modes", reasoning_modes),
            ("multimodal_types", multimodal_types),
            ("supports_parallel_tool_calls", supports_parallel_tool_calls),
            ("supports_tool_schemas", supports_tool_schemas),
            ("supports_continuation", supports_continuation),
            ("max_input_units", max_input_units),
            ("schema_version", schema_version),
        ):
            object.__setattr__(self, field_name, value)
        self.__post_init__()

    def __post_init__(self) -> None:
        if self.schema_version != PROVIDER_CAPABILITIES_SCHEMA_VERSION:
            raise CodecError("unsupported provider capabilities schema")
        if not isinstance(self.target, RequestTarget):
            raise CodecError("provider capabilities target must be RequestTarget")
        object.__setattr__(
            self,
            "supported_features",
            _capability_sequence(
                self.supported_features,
                field_name="supported_features",
                allowed=_SUPPORTED_FEATURE_VALUES,
                allow_namespaced_extensions=True,
            ),
        )
        object.__setattr__(
            self,
            "reasoning_modes",
            _capability_sequence(
                self.reasoning_modes,
                field_name="reasoning_modes",
                allowed=_REASONING_MODE_VALUES,
            ),
        )
        object.__setattr__(
            self,
            "multimodal_types",
            _capability_sequence(
                self.multimodal_types,
                field_name="multimodal_types",
                allowed=_MULTIMODAL_TYPE_VALUES,
            ),
        )
        for field_name in (
            "supports_parallel_tool_calls",
            "supports_tool_schemas",
            "supports_continuation",
        ):
            object.__setattr__(
                self,
                field_name,
                _capability_bool(getattr(self, field_name), field_name=field_name),
            )
        object.__setattr__(self, "max_input_units", _max_input_units(self.max_input_units))

    @classmethod
    def from_model(cls, model: Any) -> "ProviderCapabilities":
        """Read the explicit capability declaration owned by a model adapter."""

        try:
            target = RequestTarget.from_model(model)
        except Exception as exc:
            raise CodecCapabilityError(
                "model adapter request target declaration is invalid"
            ) from exc
        try:
            declaration = getattr(model, "qitos_provider_capabilities", None)
        except Exception as exc:
            raise CodecCapabilityError(
                "model adapter capability declaration is unavailable"
            ) from exc
        if not callable(declaration):
            raise CodecCapabilityError(
                "model adapter must declare qitos_provider_capabilities()"
            )
        try:
            declared = declaration()
        except Exception as exc:
            raise CodecCapabilityError(
                "model adapter capability declaration failed"
            ) from exc
        if isinstance(declared, cls):
            if declared.target != target:
                raise CodecCapabilityError(
                    "provider capability declaration target does not match adapter target"
                )
            return declared
        if not isinstance(declared, Mapping):
            raise CodecCapabilityError("provider capability declaration must be an object")
        fields = {
            "supported_features",
            "reasoning_modes",
            "multimodal_types",
            "supports_parallel_tool_calls",
            "supports_tool_schemas",
            "supports_continuation",
            "max_input_units",
        }
        try:
            data = _object(
                declared,
                path="provider_capability_declaration",
                fields=frozenset(fields),
            )
            return cls(target=target, **data)
        except CodecError as exc:
            raise CodecCapabilityError(
                "model adapter capability declaration is invalid"
            ) from exc
        except Exception as exc:
            raise CodecCapabilityError(
                "model adapter capability declaration is invalid"
            ) from exc

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
        try:
            data = _object(value, path="provider_capabilities", fields=fields)
            data["target"] = RequestTarget.from_dict(data["target"])
            return cls(**data)
        except CodecError:
            raise
        except Exception as exc:
            raise CodecError("provider capabilities record is invalid") from exc


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
    protocol_id: str = "unknown"
    tool_use_policy: str = "auto"
    tool_use_satisfied: bool = False
    schema_version: str = CODEC_REPORT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CODEC_REPORT_SCHEMA_VERSION:
            raise CodecError(f"unsupported codec report: {self.schema_version!r}")
        if self.fallback not in {"none", "stateless_replay"}:
            raise CodecError(f"unsupported codec fallback: {self.fallback!r}")
        if self.tool_use_policy not in {
            "auto",
            "required_for_next_decision",
            "required_before_final",
            "disabled",
        }:
            raise CodecError("unsupported codec tool-use policy")

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
            "protocol_id": self.protocol_id,
            "tool_use_policy": self.tool_use_policy,
            "tool_use_satisfied": self.tool_use_satisfied,
            "lossless": self.lossless,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "CodecReport":
        base_fields = frozenset(
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
        policy_fields = frozenset(
            {"protocol_id", "tool_use_policy", "tool_use_satisfied"}
        )
        schema_version = (
            value.get("schema_version") if isinstance(value, Mapping) else None
        )
        if schema_version == _HISTORICAL_CODEC_REPORT_SCHEMA_VERSION:
            fields = base_fields
            required = base_fields
        elif schema_version == CODEC_REPORT_SCHEMA_VERSION:
            fields = base_fields | policy_fields
            required = fields
        else:
            raise CodecError(f"unsupported codec report: {schema_version!r}")
        data = _object(
            value,
            path="codec_report",
            fields=fields,
            required=required,
        )
        reported_lossless = data.pop("lossless")
        data.setdefault("protocol_id", "unknown")
        data.setdefault("tool_use_policy", "auto")
        data.setdefault("tool_use_satisfied", False)
        data["schema_version"] = CODEC_REPORT_SCHEMA_VERSION
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
    codec_report: Optional[CodecReport] = None
    schema_version: str = PROVIDER_FAILURE_SCHEMA_VERSION
    remediation: str = field(init=False)
    correlation_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if self.schema_version != PROVIDER_FAILURE_SCHEMA_VERSION:
            raise CodecError("unsupported provider failure schema")
        if not isinstance(self.retryable, bool):
            raise CodecError("provider failure retryable must be boolean")
        if self.status_code is not None and (
            not isinstance(self.status_code, int)
            or isinstance(self.status_code, bool)
            or not 100 <= self.status_code <= 599
        ):
            raise CodecError("provider failure status_code is invalid")
        if not isinstance(self.redacted_details, Mapping):
            raise CodecError("provider failure details must be an object")
        if self.codec_report is not None and not isinstance(
            self.codec_report, CodecReport
        ):
            raise CodecError("provider failure codec_report must be CodecReport")
        safe_category = safe_diagnostic_text(
            self.category,
            fallback="provider_exception",
        )
        category_was_redacted = safe_category != self.category
        if safe_category not in _PROVIDER_FAILURE_CATEGORIES and not re.fullmatch(
            r"x\.[a-z0-9][a-z0-9_.-]{2,127}", safe_category
        ):
            raise CodecError("provider failure category is unsupported")
        safe_message = safe_diagnostic_text(
            self.message,
            fallback="Provider request failed; inspect the typed category and retryability.",
        )
        safe_provider = safe_diagnostic_text(self.provider, fallback="[redacted]")
        safe_api_mode = safe_diagnostic_text(self.api_mode, fallback="[redacted]")
        safe_error_code = (
            safe_diagnostic_text(self.error_code, fallback="[redacted]")
            if self.error_code is not None
            else None
        )
        safe_details = redact_diagnostic_value(self.redacted_details)
        if not isinstance(safe_details, dict):
            raise CodecError("provider failure details must be an object")
        remediation_by_category = {
            "provider_refusal": "Review the request against the provider policy.",
            "provider_exception": "Retry only when retryable or inspect provider health.",
            "malformed_response": "Inspect provider codec compatibility.",
            "unsupported_request": "Change the request policy or configured provider capabilities.",
            "authentication": "Check the provider credential configuration outside request data.",
            "rate_limit": "Retry according to the provider retry guidance.",
            "timeout": "Retry only when the operation is safe and retryable.",
            "transport": "Inspect provider health and network reachability.",
            "cancelled": "Start a new request only if the session is still running.",
        }
        remediation = (
            "Inspect the typed provider failure and codec report."
            if category_was_redacted
            else remediation_by_category.get(
                safe_category,
                "Inspect the typed provider failure and codec report.",
            )
        )
        correlation_material = {
            "category": safe_category,
            "message": safe_message,
            "provider": safe_provider,
            "api_mode": safe_api_mode,
            "retryable": self.retryable,
            "status_code": self.status_code,
            "error_code": safe_error_code,
            "redacted_details": safe_details,
            "codec_report": (
                self.codec_report.to_dict() if self.codec_report is not None else None
            ),
        }
        correlation_digest = hashlib.sha256(
            json.dumps(
                correlation_material,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        object.__setattr__(self, "category", safe_category)
        object.__setattr__(self, "message", safe_message)
        object.__setattr__(self, "provider", safe_provider)
        object.__setattr__(self, "api_mode", safe_api_mode)
        object.__setattr__(self, "error_code", safe_error_code)
        object.__setattr__(self, "redacted_details", safe_details)
        object.__setattr__(self, "remediation", remediation)
        object.__setattr__(self, "correlation_digest", correlation_digest)
        _materialize_json_transport(
            safe_details,
            "provider_failure.redacted_details",
            error_code="provider_failure_details_invalid",
        )
        Exception.__init__(self, safe_message)

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
            "remediation": self.remediation,
            "correlation_digest": self.correlation_digest,
            "redacted_details": json.loads(
                json.dumps(dict(self.redacted_details), allow_nan=False)
            ),
            "codec_report": (
                self.codec_report.to_dict() if self.codec_report is not None else None
            ),
        }


def validate_codec_result(
    payload: Dict[str, Any],
    report: CodecReport,
    *,
    allow_loss: bool = False,
) -> tuple[Dict[str, Any], CodecReport]:
    """Validate ownership/JSON/loss boundaries shared by every codec."""

    report.assert_acceptable(allow_loss=allow_loss)
    isolated = _materialize_json_transport(
        payload,
        "provider_payload",
        error_code="codec_payload_invalid",
    )
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
    if (
        "reasoning" in request.capability_requirements
        and request.reasoning_policy.mode not in capabilities.reasoning_modes
    ):
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
        protocol_id=request.protocol_id,
        tool_use_policy=request.tool_use_policy,
        tool_use_satisfied=request.tool_use_satisfied,
    )


def _request_tool_options(request: RequestView) -> Dict[str, Any]:
    """Project the provider-neutral tool-use policy into transport options."""
    if request.tool_use_policy == "disabled":
        return {}
    options: Dict[str, Any] = {}
    if request.tool_schemas:
        options["tools"] = list(request.tool_schemas)
    if (
        request.tool_use_policy
        in {"required_for_next_decision", "required_before_final"}
        and not request.tool_use_satisfied
    ):
        options["tool_choice"] = "required"
    return options


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
