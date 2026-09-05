"""Provider extension boundary and one model-transaction executor.

Providers own their codecs and transports.  This module only coordinates the
closed extension protocol, continuation resolution, typed failure boundary,
and the deliberately isolated legacy callable adapter.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Sequence, runtime_checkable

from ..core.conversation import (
    ArgumentParseStatus,
    AssistantContent,
    AssistantItem,
    AssistantPart,
    CallIdentity,
    OpaqueContinuationAttachment,
    ReasoningBlock,
    ReasoningReference,
    ToolCall,
)
from ..core.model_response import ModelResponse
from ..core.multimodal import ContentBlock
from ..core.diagnostics import redact_diagnostic_value
from ..core.request_view import ContinuationRef, RequestTarget, RequestView
from ..core.session import ContinuationIdentity
from .codec import (
    CodecCapabilityError,
    CodecReport,
    ProviderCapabilities,
    ProviderCodec,
    ProviderFailure,
    _materialize_json_transport,
    _request_tool_options,
    report_for_request,
    validate_codec_result,
)


def _json_copy(value: Any, path: str) -> Any:
    return _materialize_json_transport(
        value,
        path,
        error_code="codec_json_value_invalid",
    )


def _digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _usage_facts(value: Optional[Mapping[str, Any]]) -> Optional[Dict[str, int]]:
    if value is None:
        return None
    aliases = {
        "prompt_tokens": ("prompt_tokens", "input_tokens"),
        "completion_tokens": ("completion_tokens", "output_tokens"),
        "total_tokens": ("total_tokens",),
    }
    result: Dict[str, int] = {}
    for canonical, names in aliases.items():
        present = [value[name] for name in names if name in value and value[name] is not None]
        if not present:
            continue
        selected = present[0]
        if (
            not isinstance(selected, int)
            or isinstance(selected, bool)
            or selected < 0
        ):
            raise CodecCapabilityError("provider usage facts are invalid")
        result[canonical] = selected
    if "total_tokens" not in result and {
        "prompt_tokens",
        "completion_tokens",
    } <= set(result):
        result["total_tokens"] = (
            result["prompt_tokens"] + result["completion_tokens"]
        )
    if "total_tokens" in result:
        known_parts = result.get("prompt_tokens", 0) + result.get(
            "completion_tokens", 0
        )
        if known_parts and result["total_tokens"] < known_parts:
            raise CodecCapabilityError("provider usage total is inconsistent")
    return result or None


@dataclass(frozen=True)
class ContinuationResolution:
    status: str
    payload: Any = field(default=None, repr=False, compare=False)
    payload_digest: Optional[str] = None
    expires_at: Optional[str] = None
    reason_code: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in {"resolved", "missing", "expired"}:
            raise CodecCapabilityError("continuation resolution status is invalid")
        if self.status == "resolved":
            isolated = _json_copy(self.payload, "continuation payload")
            digest = _digest(isolated)
            if self.payload_digest is not None and self.payload_digest != digest:
                raise CodecCapabilityError("continuation payload digest mismatch")
            object.__setattr__(self, "payload", isolated)
            object.__setattr__(self, "payload_digest", digest)
        elif self.payload is not None:
            raise CodecCapabilityError("unresolved continuation cannot carry payload")


@runtime_checkable
class ContinuationResolver(Protocol):
    resolver_key: str

    def resolve(self, reference: ContinuationRef) -> ContinuationResolution:
        ...

    def capture(
        self,
        *,
        target: RequestTarget,
        payload: Any,
        attachment_id: str,
        expires_at: Optional[str] = None,
    ) -> ContinuationRef:
        ...


class InMemoryContinuationResolver:
    """Process-local default resolver; snapshots persist only its logical refs."""

    def __init__(self, resolver_key: str = "continuation:qitos-memory") -> None:
        self.resolver_key = str(resolver_key)
        self._values: Dict[str, ContinuationResolution] = {}

    def resolve(self, reference: ContinuationRef) -> ContinuationResolution:
        if reference.resolver_key != self.resolver_key:
            return ContinuationResolution(
                status="missing", reason_code="resolver_key_mismatch"
            )
        value = self._values.get(reference.reference_id.value)
        if value is None:
            return ContinuationResolution(
                status="missing", reason_code="continuation_not_found"
            )
        expires_at = reference.expires_at or value.expires_at
        if expires_at is not None:
            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expiry <= datetime.now(timezone.utc):
                return ContinuationResolution(
                    status="expired",
                    expires_at=expires_at,
                    reason_code="continuation_expired",
                )
        if (
            reference.payload_digest is not None
            and value.payload_digest != reference.payload_digest
        ):
            return ContinuationResolution(
                status="missing", reason_code="continuation_digest_mismatch"
            )
        return value

    def capture(
        self,
        *,
        target: RequestTarget,
        payload: Any,
        attachment_id: str,
        expires_at: Optional[str] = None,
    ) -> ContinuationRef:
        isolated = _json_copy(payload, "continuation payload")
        resolution = ContinuationResolution(
            status="resolved",
            payload=isolated,
            expires_at=expires_at,
        )
        identity = ContinuationIdentity.generate()
        self._values[identity.value] = resolution
        return ContinuationRef(
            reference_id=identity,
            resolver_key=self.resolver_key,
            provider=target.provider,
            model=target.model,
            api_mode=target.api_mode,
            attachment_id=attachment_id,
            payload_digest=resolution.payload_digest,
            expires_at=expires_at,
        )


@dataclass(frozen=True)
class ProviderDecodedResponse:
    parts: tuple[AssistantPart, ...]
    usage: Optional[Mapping[str, Any]] = None
    finish_reason: Optional[str] = None
    model_name: Optional[str] = None
    provider_metadata: Mapping[str, Any] = field(default_factory=dict)
    continuation_payload: Any = field(default=None, repr=False, compare=False)
    continuation_attachment_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.usage is not None and not isinstance(self.usage, Mapping):
            raise CodecCapabilityError("provider usage must be an object")
        safe_usage = _usage_facts(self.usage)
        safe_metadata = redact_diagnostic_value(dict(self.provider_metadata))
        if not isinstance(safe_metadata, dict):
            raise CodecCapabilityError("provider metadata must be an object")
        safe_metadata = _json_copy(safe_metadata, "provider metadata")
        object.__setattr__(self, "usage", safe_usage)
        object.__setattr__(self, "provider_metadata", safe_metadata)
        if self.continuation_payload is not None:
            object.__setattr__(
                self,
                "continuation_payload",
                _json_copy(self.continuation_payload, "continuation payload"),
            )


class ConversationProviderCodec(ProviderCodec, Protocol):
    def decode(
        self, response: Any, *, request: RequestView
    ) -> ProviderDecodedResponse:
        ...

    def apply_continuation(
        self,
        payload: Dict[str, Any],
        resolution: ContinuationResolution,
        *,
        request: RequestView,
        report: CodecReport,
    ) -> tuple[Dict[str, Any], CodecReport]:
        ...


@runtime_checkable
class RequestTransform(Protocol):
    """Optional JSON-only transform between codec output and transport."""

    transform_id: str

    def transform(
        self,
        payload: Mapping[str, Any],
        *,
        request: RequestView,
        report: CodecReport,
    ) -> tuple[Dict[str, Any], CodecReport]:
        ...


@runtime_checkable
class ProviderAdapter(Protocol):
    def qitos_request_target(self) -> Mapping[str, str] | RequestTarget:
        ...

    def qitos_provider_capabilities(self) -> Mapping[str, Any] | ProviderCapabilities:
        ...

    def qitos_provider_codec(self) -> ConversationProviderCodec:
        ...

    def qitos_transport(self, payload: Mapping[str, Any]) -> Any:
        ...

    def qitos_stream_transport(
        self,
        payload: Mapping[str, Any],
        *,
        on_delta: Any = None,
    ) -> Any:
        ...

    def qitos_normalize_failure(
        self,
        error: BaseException,
        *,
        report: Optional[CodecReport] = None,
    ) -> ProviderFailure:
        ...


@dataclass(frozen=True)
class ProviderTransaction:
    request: RequestView
    codec_report: CodecReport
    assistant_item: AssistantItem
    model_response: ModelResponse
    continuation_refs: tuple[ContinuationRef, ...] = ()


def safe_exception_status(error: BaseException) -> Optional[int]:
    for candidate in (
        getattr(error, "status_code", None),
        getattr(getattr(error, "response", None), "status_code", None),
        getattr(error, "code", None),
    ):
        if isinstance(candidate, int) and not isinstance(candidate, bool):
            if 100 <= candidate <= 599:
                return candidate
    return None


def normalize_provider_failure(
    error: BaseException,
    *,
    target: RequestTarget,
    report: Optional[CodecReport] = None,
) -> ProviderFailure:
    """Normalize without reflecting raw response, endpoint, headers, or text."""

    if isinstance(error, ProviderFailure):
        if report is None or error.codec_report is not None:
            return error
        return replace(error, codec_report=report)
    status = safe_exception_status(error)
    error_name = error.__class__.__name__.lower()
    retryable = bool(
        status in {408, 409, 425, 429, 500, 502, 503, 504}
        or any(token in error_name for token in ("timeout", "connection", "ratelimit"))
    )
    if status in {401, 403} or "auth" in error_name:
        category = "authentication"
        code = "provider_authentication_failed"
        stage = "authentication"
    elif status == 429 or "ratelimit" in error_name or "rate_limit" in error_name:
        category = "rate_limit"
        code = "provider_rate_limited"
        stage = "rate_limit"
    elif status == 408 or "timeout" in error_name:
        category = "timeout"
        code = "provider_timeout"
        stage = "timeout"
    elif "decode" in error_name:
        category = "decode"
        code = "provider_response_decode_failed"
        stage = "decode"
    elif "cancel" in error_name:
        category = "cancellation"
        code = "provider_request_cancelled"
        stage = "cancellation"
    elif any(token in error_name for token in ("connection", "transport")):
        category = "connection"
        code = "provider_connection_failed"
        stage = "connection"
    elif status in {400, 404, 409, 422}:
        category = "provider_rejection"
        code = "provider_request_rejected"
        stage = "provider_rejection"
    elif status is not None and status >= 500:
        category = "provider_server"
        code = "provider_server_error"
        stage = "provider_server"
    else:
        category = "transport"
        code = "provider_connection_failed"
        stage = "transport"
    return ProviderFailure(
        category=category,
        message="Provider request failed at the sanitized transport boundary.",
        provider=target.provider,
        api_mode=target.api_mode,
        retryable=retryable,
        status_code=status,
        error_code=code,
        redacted_details={"exception_type": error.__class__.__name__},
        codec_report=report,
        stage=stage,
        provider_request_sent=True,
    )


def execute_provider_request(
    adapter: ProviderAdapter,
    request: RequestView,
    *,
    allow_loss: bool = False,
    continuation_resolver: Optional[ContinuationResolver] = None,
    stream_callback: Any = None,
    transport_options: Optional[Mapping[str, Any]] = None,
    request_transform: Optional[RequestTransform] = None,
    request_admission: Optional[Callable[[], None]] = None,
    cancellation_check: Optional[Callable[[], bool]] = None,
) -> ProviderTransaction:
    """Execute exactly one RequestView through its declared provider adapter."""

    capabilities = ProviderCapabilities.from_model(adapter)
    if capabilities.target != request.target:
        raise CodecCapabilityError(
            "provider adapter target does not match RequestView target"
        )
    codec = adapter.qitos_provider_codec()
    if not isinstance(codec, ProviderCodec):
        raise CodecCapabilityError("provider adapter returned an invalid codec")
    payload: Dict[str, Any]
    report: Optional[CodecReport] = None
    try:
        payload, report = codec.encode(
            request,
            capabilities=capabilities,
            transport=request.target,
            allow_loss=allow_loss,
        )
    except CodecCapabilityError:
        raise
    except ProviderFailure as failure:
        raise replace(
            failure,
            stage="encode",
            provider_request_sent=False,
        ) from None
    except BaseException as exc:
        raise ProviderFailure(
            category="provider_exception",
            message="Provider request encoding failed.",
            provider=request.target.provider,
            api_mode=request.target.api_mode,
            error_code="codec_encode_failed",
            redacted_details={"exception_type": exc.__class__.__name__},
            codec_report=report,
            stage="encode",
            provider_request_sent=False,
        ) from None

    try:
        if request.continuation is not None:
            resolver = continuation_resolver
            if resolver is None:
                raise ProviderFailure(
                    category="unsupported_request",
                    message="Continuation resolver is required for this request.",
                    provider=request.target.provider,
                    api_mode=request.target.api_mode,
                    error_code="continuation_resolver_missing",
                    codec_report=report,
                )
            resolution = resolver.resolve(request.continuation)
            if resolution.status != "resolved":
                if not allow_loss:
                    raise ProviderFailure(
                        category="unsupported_request",
                        message="Continuation could not be resolved without loss.",
                        provider=request.target.provider,
                        api_mode=request.target.api_mode,
                        error_code=(
                            resolution.reason_code or "continuation_unavailable"
                        ),
                        codec_report=report,
                    )
                report = replace(
                    report,
                    continuation="fallback_to_stateless_replay",
                    fallback="stateless_replay",
                    lossy_fields=tuple(
                        sorted(set(report.lossy_fields) | {"continuation.state"})
                    ),
                    warnings=report.warnings
                    + ("continuation unavailable; explicit stateless replay",),
                )
            else:
                payload, report = codec.apply_continuation(
                    payload,
                    resolution,
                    request=request,
                    report=report,
                )
        if transport_options is not None:
            updated_payload = dict(payload)
            options = dict(updated_payload.get("options") or {})
            options.update(
                _materialize_json_transport(
                    transport_options,
                    "transport_options",
                    error_code="codec_transport_options_invalid",
                )
            )
            updated_payload["options"] = options
            payload = updated_payload
        if request_transform is not None:
            if not isinstance(request_transform, RequestTransform):
                raise CodecCapabilityError("request transform is invalid")
            payload, report = request_transform.transform(
                payload,
                request=request,
                report=report,
            )
        payload, report = validate_codec_result(
            payload, report, allow_loss=allow_loss
        )
    except CodecCapabilityError:
        raise
    except ProviderFailure as failure:
        raise replace(
            failure,
            stage="projection",
            provider_request_sent=False,
        ) from None
    except BaseException as exc:
        raise ProviderFailure(
            category="unsupported_request",
            message="Provider request projection failed.",
            provider=request.target.provider,
            api_mode=request.target.api_mode,
            error_code="request_projection_failed",
            redacted_details={"exception_type": exc.__class__.__name__},
            codec_report=report,
            stage="projection",
            provider_request_sent=False,
        ) from None

    use_stream = stream_callback is not None
    if use_stream and not capabilities.supports_streaming:
        raise CodecCapabilityError(
            "provider adapter does not declare streaming support",
            report=report,
        )

    def assert_not_cancelled() -> None:
        if cancellation_check is None:
            return
        try:
            cancelled = cancellation_check()
        except BaseException as exc:
            raise ProviderFailure(
                category="cancellation",
                message="Cancellation state could not be inspected safely.",
                provider=request.target.provider,
                api_mode=request.target.api_mode,
                error_code="provider_cancellation_check_failed",
                redacted_details={"exception_type": exc.__class__.__name__},
                codec_report=report,
                stage="cancellation",
                provider_request_sent=False,
            ) from None
        if not isinstance(cancelled, bool):
            raise ProviderFailure(
                category="cancellation",
                message="Cancellation state must be boolean.",
                provider=request.target.provider,
                api_mode=request.target.api_mode,
                error_code="provider_cancellation_state_invalid",
                codec_report=report,
                stage="cancellation",
                provider_request_sent=False,
            )
        if cancelled:
            raise ProviderFailure(
                category="cancellation",
                message="Provider request was cancelled before transport.",
                provider=request.target.provider,
                api_mode=request.target.api_mode,
                error_code="provider_request_cancelled",
                codec_report=report,
                stage="cancellation",
                provider_request_sent=False,
            )

    assert_not_cancelled()
    if request_admission is not None:
        try:
            request_admission()
        except ProviderFailure as failure:
            raise replace(
                failure,
                stage="admission",
                provider_request_sent=False,
                codec_report=failure.codec_report or report,
            ) from None
        except BaseException as exc:
            raise ProviderFailure(
                category="admission",
                message="Provider request admission failed.",
                provider=request.target.provider,
                api_mode=request.target.api_mode,
                error_code="provider_request_admission_failed",
                redacted_details={"exception_type": exc.__class__.__name__},
                codec_report=report,
                stage="admission",
                provider_request_sent=False,
            ) from None
    assert_not_cancelled()

    try:
        if use_stream:
            raw_response = adapter.qitos_stream_transport(
                payload, on_delta=stream_callback
            )
        else:
            raw_response = adapter.qitos_transport(payload)
    except ProviderFailure as failure:
        raise replace(
            failure,
            codec_report=failure.codec_report or report,
        ) from None
    except BaseException as exc:
        try:
            normalized = adapter.qitos_normalize_failure(exc, report=report)
        except BaseException:
            normalized = None
        if not isinstance(normalized, ProviderFailure):
            normalized = normalize_provider_failure(
                exc, target=request.target, report=report
            )
        raise replace(
            normalized,
            stage="stream" if use_stream else normalized.stage,
            provider_request_sent=True,
        ) from None

    try:
        decoded = codec.decode(raw_response, request=request)
        if not isinstance(decoded, ProviderDecodedResponse):
            raise TypeError("codec decode result is not ProviderDecodedResponse")
    except ProviderFailure as failure:
        raise replace(
            failure,
            stage="decode",
            provider_request_sent=True,
        ) from None
    except BaseException as exc:
        malformed = isinstance(exc, (CodecCapabilityError, ValueError, TypeError))
        raise ProviderFailure(
            category=(
                "malformed_structured_response"
                if malformed
                else "provider_exception"
            ),
            message="Provider response could not be decoded safely.",
            provider=request.target.provider,
            api_mode=request.target.api_mode,
            error_code=(
                "provider_response_malformed"
                if malformed
                else "provider_response_decode_failed"
            ),
            redacted_details={"exception_type": exc.__class__.__name__},
            codec_report=report,
            stage="malformed_structured_response" if malformed else "decode",
            provider_request_sent=True,
        ) from None

    try:
        resolver = continuation_resolver
        refs: tuple[ContinuationRef, ...] = ()
        attachments: list[OpaqueContinuationAttachment] = []
        if decoded.continuation_payload is not None:
            attachment_id = decoded.continuation_attachment_id or (
                f"continuation_attachment_{request.request_id}"
            )
            if resolver is None:
                resolver = getattr(adapter, "qitos_continuation_resolver", None)
            if resolver is None or not isinstance(resolver, ContinuationResolver):
                raise ProviderFailure(
                    category="unsupported_request",
                    message="Provider returned continuation state but no resolver is configured.",
                    provider=request.target.provider,
                    api_mode=request.target.api_mode,
                    error_code="continuation_capture_unavailable",
                    codec_report=report,
                )
            try:
                reference = resolver.capture(
                    target=request.target,
                    payload=decoded.continuation_payload,
                    attachment_id=attachment_id,
                )
            except ProviderFailure as failure:
                raise replace(
                    failure,
                    stage="decode",
                    provider_request_sent=True,
                    codec_report=failure.codec_report or report,
                ) from None
            except BaseException as exc:
                raise ProviderFailure(
                    category="decode",
                    message="Provider continuation could not be captured safely.",
                    provider=request.target.provider,
                    api_mode=request.target.api_mode,
                    error_code="continuation_capture_failed",
                    redacted_details={"exception_type": exc.__class__.__name__},
                    codec_report=report,
                    stage="decode",
                    provider_request_sent=True,
                ) from None
            refs = (reference,)
            attachments.append(
                OpaqueContinuationAttachment(
                    attachment_id=attachment_id,
                    provider_scope=(
                        f"{request.target.provider}:{request.target.api_mode}"
                    ),
                    api_mode=request.target.api_mode,
                    opaque_payload={"resolver_ref": reference.reference_id.to_dict()},
                    metadata={"payload_digest": reference.payload_digest},
                )
            )
        item = AssistantItem(
            item_id=f"assistant_{_digest({'request': request.request_id, 'parts': [_part_identity(p) for p in decoded.parts]})[:24]}",
            exchange_id=f"exchange_{request.request_id}",
            parts=list(decoded.parts),
            continuation_attachments=attachments,
            metadata={
                "provider": request.target.provider,
                "model": request.target.model,
                "api_mode": request.target.api_mode,
                "finish_reason": decoded.finish_reason,
                "provider_metadata": dict(decoded.provider_metadata),
            },
        )
        item.validate()
        response = model_response_from_assistant(
            item,
            usage=decoded.usage,
            finish_reason=decoded.finish_reason,
            model_name=decoded.model_name or request.target.model,
            provider=request.target.provider,
            request_id=request.request_id,
            codec_report=report,
        )
        return ProviderTransaction(
            request=request,
            codec_report=report,
            assistant_item=item,
            model_response=response,
            continuation_refs=refs,
        )
    except ProviderFailure as failure:
        # Once transport was invoked, later failures cannot release admission.
        raise replace(
            failure,
            stage="decode",
            provider_request_sent=True,
            codec_report=failure.codec_report or report,
        ) from None
    except BaseException:
        raise ProviderFailure(
            category="decode",
            message="Provider response could not be finalized safely.",
            provider=request.target.provider,
            api_mode=request.target.api_mode,
            error_code="provider_response_finalization_failed",
            codec_report=report,
            stage="decode",
            provider_request_sent=True,
        ) from None


def _part_identity(part: AssistantPart) -> Dict[str, Any]:
    if isinstance(part, AssistantContent):
        return {"kind": part.kind, "block": part.block.to_dict()}
    if isinstance(part, ToolCall):
        return {
            "kind": part.kind,
            "call_id": part.identity.call_id,
            "name": part.name,
            "raw_arguments": part.raw_arguments,
        }
    return {
        "kind": part.kind,
        "reference_id": part.reference_id,
        "provider_scope": part.provider_scope,
    }


def model_response_from_assistant(
    item: AssistantItem,
    *,
    usage: Optional[Mapping[str, Any]],
    finish_reason: Optional[str],
    model_name: str,
    provider: str,
    request_id: str,
    codec_report: CodecReport,
) -> ModelResponse:
    text_parts: list[str] = []
    tool_calls: list[Dict[str, Any]] = []
    reasoning_references: list[Dict[str, Any]] = []
    for part in item.parts:
        if isinstance(part, AssistantContent):
            if part.block.type == "text" and part.block.text:
                text_parts.append(part.block.text)
        elif isinstance(part, ToolCall):
            tool_calls.append(
                {
                    "id": part.identity.call_id,
                    "type": "function",
                    "function": {
                        "name": part.name,
                        "arguments": part.raw_arguments,
                    },
                }
            )
        elif isinstance(part, (ReasoningReference, ReasoningBlock)):
            reasoning_references.append(
                {
                    "kind": part.kind,
                    "reference_id": part.reference_id,
                    "provider_scope": part.provider_scope,
                }
            )
    return ModelResponse(
        text="".join(text_parts),
        raw=None,
        usage=dict(usage) if isinstance(usage, Mapping) else None,
        finish_reason=finish_reason,
        tool_calls=tool_calls or None,
        model_name=model_name,
        provider=provider,
        metadata={
            "request_id": request_id,
            "assistant_item_id": item.item_id,
            "codec_report": codec_report.to_dict(),
            "reasoning_references": reasoning_references,
        },
        native_items=None,
    )


def content_payload(blocks: Sequence[Mapping[str, Any]]) -> Any:
    normalized = [dict(block) for block in blocks]
    if len(normalized) == 1 and normalized[0].get("type") == "text":
        return str(normalized[0].get("text") or "")
    return normalized


def context_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping) and set(value) == {"text"}:
        return str(value.get("text") or "")
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def request_view_to_compat_messages(
    request: RequestView,
) -> tuple[List[Dict[str, Any]], tuple[str, ...]]:
    """Strict compatibility projection; never a canonical history writer."""

    messages: List[Dict[str, Any]] = []
    losses: list[str] = []
    for instruction in request.instructions:
        messages.append(
            {
                "role": str(instruction.get("role") or "system"),
                "content": instruction.get("content", ""),
            }
        )
    for contribution in request.context_contributions:
        role = str(contribution.get("requested_placement") or "developer")
        if role not in {"system", "developer", "user"}:
            role = "developer"
        messages.append(
            {"role": role, "content": context_text(contribution.get("content"))}
        )
    projected_batches: set[str] = set()
    for item in request.selected_items:
        kind = item.get("kind")
        if kind in {"user", "steering"}:
            messages.append(
                {"role": "user", "content": content_payload(item.get("content") or [])}
            )
            continue
        if kind == "assistant":
            parts = list(item.get("parts") or [])
            blocks: list[Mapping[str, Any]] = []
            calls: list[Dict[str, Any]] = []
            native_items: list[Dict[str, Any]] = []
            seen_call = False
            for part in parts:
                part_kind = part.get("kind")
                if part_kind == "content":
                    if seen_call:
                        losses.append("assistant.ordered_interleaving")
                    block = part.get("block")
                    if isinstance(block, Mapping):
                        blocks.append(block)
                elif part_kind in {"reasoning_reference", "reasoning_block"}:
                    metadata = part.get("metadata") or {}
                    native_item = (
                        metadata.get("native_item")
                        if isinstance(metadata, Mapping)
                        else None
                    )
                    if isinstance(native_item, Mapping):
                        native_items.append(dict(native_item))
                    else:
                        losses.append("assistant.reasoning")
                elif part_kind == "tool_call":
                    seen_call = True
                    calls.append(
                        {
                            "id": part.get("call_id"),
                            "type": "function",
                            "function": {
                                "name": part.get("name"),
                                "arguments": part.get("raw_arguments", "{}"),
                            },
                        }
                    )
                    metadata = part.get("metadata") or {}
                    native_item = (
                        metadata.get("native_item")
                        if isinstance(metadata, Mapping)
                        else None
                    )
                    if isinstance(native_item, Mapping):
                        native_items.append(dict(native_item))
                    if part.get("batch_id"):
                        projected_batches.add(str(part["batch_id"]))
            message: Dict[str, Any] = {
                "role": "assistant",
                "content": content_payload(blocks) if blocks else None,
            }
            if calls:
                message["tool_calls"] = calls
            if native_items:
                message["native_items"] = native_items
            messages.append(message)
            continue
        if kind == "tool_result":
            result = item.get("result") or {}
            output = result.get("model_output")
            if output is None:
                output = result.get("error") or ""
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": item.get("call_id"),
                    "content": context_text(output),
                }
            )
    return messages, tuple(sorted(set(losses)))


class LegacyMessageCodec:
    """Explicit compatibility codec for callable models without S2 adapters."""

    codec_id = "qitos.compatibility.messages"
    codec_version = "v1"

    def encode(
        self,
        request: RequestView,
        *,
        capabilities: Optional[ProviderCapabilities] = None,
        transport: Optional[RequestTarget] = None,
        allow_loss: bool = False,
    ) -> tuple[Dict[str, Any], CodecReport]:
        resolved = capabilities or legacy_capabilities(request.target)
        if transport is not None and transport != request.target:
            raise CodecCapabilityError("legacy codec transport mismatch")
        messages, losses = request_view_to_compat_messages(request)
        report = report_for_request(
            request,
            resolved,
            codec_id=self.codec_id,
            codec_version=self.codec_version,
            reasoning=("dropped" if losses else "not_present"),
            continuation=("rejected" if request.continuation else "not_requested"),
            supported=request.capability_requirements,
            lossy_fields=losses,
            warnings=("legacy callable compatibility adapter",),
        )
        if allow_loss and "assistant.reasoning" in losses:
            report = replace(
                report,
                unsupported=tuple(
                    item
                    for item in report.unsupported
                    if item != "reasoning" and not item.startswith("reasoning:")
                ),
            )
        options = _request_tool_options(request)
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
        _ = payload
        _ = resolution
        _ = request
        _ = report
        raise CodecCapabilityError("legacy message codec cannot apply continuation")

    def decode(
        self, response: Any, *, request: RequestView
    ) -> ProviderDecodedResponse:
        return decode_openai_like_response(response, request=request)


def legacy_capabilities(target: RequestTarget) -> ProviderCapabilities:
    return ProviderCapabilities(
        target=target,
        api_style="messages",
        supported_features=(
            "text",
            "multimodal",
            "tool_calls",
            "tool_results",
            "tool_schemas",
            "parallel_tool_calls",
            "artifact_references",
            "reasoning",
            "ordered_interleaving",
        ),
        reasoning_modes=("preserve_if_supported", "drop"),
        multimodal_types=("text", "image_url", "image_base64", "image_file"),
        supports_native_tool_calls=True,
        supports_parallel_tool_calls=True,
        supports_tool_schemas=True,
        supports_tool_choice=True,
        supports_multimodal_input=True,
        supports_reasoning_input=True,
        supports_reasoning_output=True,
        supports_continuation=False,
        supports_stateless_replay=True,
        supports_streaming=False,
        supports_usage=True,
        supports_cancellation=False,
        supports_structured_output=False,
    )


class LegacyCallableAdapter:
    def __init__(self, model: Any) -> None:
        self.model_object = model
        model_name = str(
            getattr(model, "model", None)
            or getattr(model, "model_name", None)
            or model.__class__.__name__
        )
        provider_name = str(
            getattr(model, "provider", None) or "legacy-callable"
        )
        self._target = RequestTarget(
            provider_name, model_name, "compatibility", "messages"
        )
        self.qitos_continuation_resolver = InMemoryContinuationResolver()

    def qitos_request_target(self) -> RequestTarget:
        return self._target

    def qitos_provider_capabilities(self) -> Mapping[str, Any]:
        result = legacy_capabilities(self._target).to_dict()
        result.pop("schema_version")
        result.pop("target")
        if callable(getattr(self.model_object, "stream", None)):
            result["supported_features"] = tuple(
                list(result["supported_features"]) + ["streaming"]
            )
            result["supports_streaming"] = True
        return result

    def qitos_provider_codec(self) -> LegacyMessageCodec:
        return LegacyMessageCodec()

    def qitos_transport(self, payload: Mapping[str, Any]) -> Any:
        messages = list(payload.get("messages") or [])
        options = dict(payload.get("options") or {})
        call_raw = getattr(self.model_object, "call_raw", None)
        if callable(call_raw):
            return call_raw(messages, **options)
        return self.model_object(messages, **options)

    def qitos_stream_transport(
        self,
        payload: Mapping[str, Any],
        *,
        on_delta: Any = None,
    ) -> Any:
        stream = getattr(self.model_object, "stream", None)
        if not callable(stream):
            return self.qitos_transport(payload)
        messages = list(payload.get("messages") or [])
        options = dict(payload.get("options") or {})
        text_parts: list[str] = []
        usage = None
        tool_calls = None
        native_items = None
        for chunk in stream(messages, **options):
            text = str(getattr(chunk, "text", "") or "")
            if text:
                text_parts.append(text)
                if callable(on_delta):
                    on_delta(text)
            if getattr(chunk, "done", False):
                usage = getattr(chunk, "usage", None)
                tool_calls = getattr(chunk, "tool_calls", None)
                native_items = getattr(chunk, "native_items", None)
        return ModelResponse(
            text="".join(text_parts),
            usage=usage if isinstance(usage, dict) else None,
            finish_reason="stop",
            tool_calls=tool_calls if isinstance(tool_calls, list) else None,
            model_name=self._target.model,
            provider=self._target.provider,
            native_items=native_items if isinstance(native_items, list) else None,
        )

    def qitos_normalize_failure(
        self,
        error: BaseException,
        *,
        report: Optional[CodecReport] = None,
    ) -> ProviderFailure:
        return normalize_provider_failure(error, target=self._target, report=report)


def adapter_for_model(model: Any) -> ProviderAdapter:
    if isinstance(model, ProviderAdapter):
        try:
            RequestTarget.from_model(model)
            ProviderCapabilities.from_model(model)
            model.qitos_provider_codec()
        except Exception:
            pass
        else:
            return model
    return LegacyCallableAdapter(model)


def request_target_for_model(model: Any) -> RequestTarget:
    return RequestTarget.from_model(adapter_for_model(model))


def decode_openai_like_response(
    response: Any, *, request: RequestView
) -> ProviderDecodedResponse:
    """Decode dict/SDK chat responses while copying only allowlisted fields."""

    if isinstance(response, ProviderDecodedResponse):
        return response
    if isinstance(response, ModelResponse):
        text = response.text
        tool_calls = response.tool_calls or []
        native_items = response.native_items or []
        usage = response.usage
        finish_reason = response.finish_reason
        model_name = response.model_name
        metadata = dict(response.metadata or {})
        reasoning_fields = dict(response.reasoning_fields or {})
    elif isinstance(response, str):
        text = response
        tool_calls = []
        native_items = []
        usage = None
        finish_reason = None
        model_name = request.target.model
        metadata = {}
        reasoning_fields = {}
    else:
        if isinstance(response, Mapping):
            recognized = any(
                key in response
                for key in ("choices", "message", "content", "tool_calls")
            )
        else:
            recognized = any(
                hasattr(response, key)
                for key in ("choices", "message", "content", "tool_calls")
            )
        if not recognized:
            raise ProviderFailure(
                category="malformed_response",
                message="Provider response did not match the declared codec envelope.",
                provider=request.target.provider,
                api_mode=request.target.api_mode,
                error_code="provider_response_envelope_invalid",
            )
        choice = _first_choice(response)
        message = _field(choice, "message") if choice is not None else None
        if message is None:
            message = _field(response, "message", response)
        text = _field(message, "content", "") or ""
        tool_calls = list(_field(message, "tool_calls", []) or [])
        native_items = []
        usage = _usage_mapping(_field(response, "usage"))
        finish_reason = (
            _field(choice, "finish_reason")
            if choice is not None
            else _field(response, "finish_reason")
        )
        model_name = _field(response, "model", request.target.model)
        metadata = {
            key: value
            for key in ("id", "created")
            if (value := _field(response, key)) is not None
        }
        reasoning_fields = {
            key: str(value)
            for key in ("reasoning_content", "reasoning")
            if (value := _field(message, key)) is not None and str(value).strip()
        }
    parts: list[AssistantPart] = []
    provider_scope = f"{request.target.provider}:{request.target.api_mode}"
    batch_id = f"batch_{request.request_id}"
    native_call_ids: set[str] = set()
    native_text_parts: list[str] = []
    parsed: Optional[Dict[str, Any]]
    parse_error: Optional[str]
    for index, raw_item in enumerate(native_items):
        if not isinstance(raw_item, Mapping):
            continue
        kind = str(raw_item.get("type") or "")
        if kind == "reasoning":
            summary_parts = [
                str(summary.get("text"))
                for summary in raw_item.get("summary") or []
                if isinstance(summary, Mapping) and summary.get("text")
            ]
            native_item = {
                key: _json_copy(raw_item[key], f"native reasoning {key}")
                for key in ("type", "id", "summary", "status")
                if key in raw_item
            }
            parts.append(
                ReasoningBlock(
                    provider_scope=provider_scope,
                    reference_id=str(
                        raw_item.get("id")
                        or f"reasoning_{request.request_id}_{index}"
                    ),
                    block_type="native_reasoning",
                    summary="".join(summary_parts) or None,
                    metadata={"native_item": native_item},
                )
            )
            continue
        if kind == "message":
            for block in raw_item.get("content") or []:
                if not isinstance(block, Mapping):
                    continue
                if block.get("type") not in {"output_text", "text"}:
                    continue
                value = str(block.get("text") or "")
                if value:
                    native_text_parts.append(value)
                    parts.append(
                        AssistantContent(ContentBlock(type="text", text=value))
                    )
            continue
        if kind != "function_call":
            continue
        call_id = str(
            raw_item.get("call_id")
            or raw_item.get("id")
            or f"call_{request.request_id}_{index}"
        )
        native_call_ids.add(call_id)
        raw_arguments = str(raw_item.get("arguments") or "{}")
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
        native_item = {
            "type": "function_call",
            "call_id": call_id,
            "name": str(raw_item.get("name") or ""),
            "arguments": raw_arguments,
        }
        if raw_item.get("id") is not None:
            native_item["id"] = str(raw_item["id"])
        parts.append(
            ToolCall(
                identity=CallIdentity(provider_scope, call_id),
                batch_id=batch_id,
                name=str(raw_item.get("name") or ""),
                raw_arguments=raw_arguments,
                parsed_arguments=parsed,
                parse_status=parse_status,
                parse_error=parse_error,
                metadata={"native_item": native_item},
            )
        )
    for key, value in reasoning_fields.items():
        parts.append(
            ReasoningBlock(
                provider_scope=provider_scope,
                reference_id=f"reasoning_{_digest({'request': request.request_id, 'field': key, 'value': value})[:24]}",
                block_type=key,
                summary=str(value),
                metadata={"source_field": key},
            )
        )
    if isinstance(text, list):
        for block in text:
            if isinstance(block, Mapping):
                block_type = str(block.get("type") or "text")
                block_text = block.get("text")
                if block_text is not None:
                    parts.append(
                        AssistantContent(
                            ContentBlock(type=block_type, text=str(block_text))
                        )
                    )
    elif str(text) and str(text) != "".join(native_text_parts):
        parts.append(AssistantContent(ContentBlock(type="text", text=str(text))))
    for index, raw_call in enumerate(tool_calls):
        call_id = str(_field(raw_call, "id") or f"call_{request.request_id}_{index}")
        if call_id in native_call_ids:
            continue
        function = _field(raw_call, "function", {})
        name = str(_field(function, "name") or "")
        raw_arguments_value = _field(function, "arguments", "{}")
        if isinstance(raw_arguments_value, Mapping):
            parsed = dict(raw_arguments_value)
            raw_arguments = json.dumps(parsed, ensure_ascii=False, sort_keys=True)
            parse_status = ArgumentParseStatus.PARSED
            parse_error = None
        else:
            raw_arguments = str(raw_arguments_value or "{}")
            try:
                parsed_value = json.loads(raw_arguments)
            except (TypeError, json.JSONDecodeError) as exc:
                parsed = None
                parse_status = ArgumentParseStatus.MALFORMED_RAW
                parse_error = exc.__class__.__name__
            else:
                if isinstance(parsed_value, dict):
                    parsed = parsed_value
                    parse_status = ArgumentParseStatus.PARSED
                    parse_error = None
                else:
                    parsed = None
                    parse_status = ArgumentParseStatus.PARSED_INVALID
                    parse_error = "arguments_not_object"
        parts.append(
            ToolCall(
                identity=CallIdentity(provider_scope, call_id),
                batch_id=batch_id,
                name=name,
                raw_arguments=raw_arguments,
                parsed_arguments=parsed,
                parse_status=parse_status,
                parse_error=parse_error,
            )
        )
    return ProviderDecodedResponse(
        parts=tuple(parts),
        usage=usage,
        finish_reason=(str(finish_reason) if finish_reason is not None else None),
        model_name=(str(model_name) if model_name is not None else None),
        provider_metadata=metadata,
    )


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _first_choice(response: Any) -> Any:
    choices = _field(response, "choices", []) or []
    return choices[0] if isinstance(choices, Sequence) and choices else None


def _usage_mapping(usage: Any) -> Optional[Dict[str, Any]]:
    if usage is None:
        return None
    if isinstance(usage, Mapping):
        source = usage
    else:
        source = {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }
    result = {
        str(key): value
        for key, value in source.items()
        if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
        and isinstance(value, int)
    }
    return result or None


__all__ = [
    "ContinuationResolution",
    "ContinuationResolver",
    "InMemoryContinuationResolver",
    "ProviderDecodedResponse",
    "ConversationProviderCodec",
    "RequestTransform",
    "ProviderAdapter",
    "ProviderTransaction",
    "execute_provider_request",
    "normalize_provider_failure",
    "request_view_to_compat_messages",
    "LegacyMessageCodec",
    "LegacyCallableAdapter",
    "adapter_for_model",
    "request_target_for_model",
    "decode_openai_like_response",
]
