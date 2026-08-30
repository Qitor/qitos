"""Immutable request, continuation, context, and conversation-component contracts.

`ExchangeLog` remains the only canonical conversation truth.  The records in
this module are deterministic, provider-neutral projections for one model
request or one checkpoint-v2 snapshot component.  They never own a provider
client, credential, SDK object, artifact body, or long-term memory store.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Iterable, Literal, Mapping, Optional, Protocol, Sequence

from .artifact import ArtifactRef
from .conversation import (
    AssistantContent,
    AssistantItem,
    ConversationValidationError,
    ExchangeLog,
    ReasoningReference,
    SteeringItem,
    ToolResultItem,
    _item_to_dict,
    history_messages_to_exchange_log,
)
from .history import HistoryMessage
from .multimodal import ContentBlock
from .session import ContinuationIdentity, SnapshotComponentCodec


REQUEST_VIEW_SCHEMA_VERSION = "qitos.request_view/v1"
CONVERSATION_COMPONENT_SCHEMA_VERSION = "qitos.conversation_component/v1"
REQUEST_BUILDER_VERSION = "qitos.exchange_request_builder/v1"


class RequestContractError(ConversationValidationError):
    """Base error for stable request and snapshot-component contracts."""

    code = "request_contract_error"


class UnsupportedRequestVersionError(RequestContractError):
    code = "unsupported_request_version"


class UnsafeRequestBoundaryError(RequestContractError):
    code = "unsafe_request_boundary"


class MissingArtifactError(RequestContractError):
    code = "missing_artifact"


class IncompatibleContinuationError(RequestContractError):
    code = "incompatible_continuation"


class UnsafeSnapshotComponentError(RequestContractError):
    code = "unsafe_snapshot_component"


_HOST_PATH = re.compile(
    r"(?:^|[\s=])(?:/Users/|/home/|/var/folders/|[A-Za-z]:\\)", re.IGNORECASE
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _strict_json(value: Any, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        import math

        if not math.isfinite(value):
            raise RequestContractError(f"{path} must contain only finite numbers")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _strict_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RequestContractError(f"{path} keys must be strings")
            _strict_json(item, f"{path}.{key}")
        return
    raise RequestContractError(
        f"{path} contains non-JSON value {type(value).__name__}"
    )


def _json_text(value: Any, path: str) -> str:
    _strict_json(value, path)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _json_value(value: str) -> Any:
    return json.loads(value)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json_text(value, "digest_input").encode("utf-8")).hexdigest()


def _non_empty(value: str, path: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise RequestContractError(f"{path} must be a non-empty string")
    return text


def _logical_reference(value: str, path: str) -> str:
    text = _non_empty(value, path)
    if _HOST_PATH.search(text):
        raise RequestContractError(f"{path} must be a logical reference, not a host path")
    return text


def _strict_object(
    value: Any,
    *,
    path: str,
    fields: frozenset[str],
    required: Optional[frozenset[str]] = None,
) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(k, str) for k in value):
        raise RequestContractError(f"{path} must be an object with string keys")
    data = dict(value)
    unknown = sorted(set(data) - fields)
    if unknown:
        raise RequestContractError(f"{path} has unknown field {unknown[0]!r}")
    missing = sorted((required or fields) - set(data))
    if missing:
        raise RequestContractError(f"{path} is missing field {missing[0]!r}")
    return data


@dataclass(frozen=True)
class RequestTarget:
    provider: str
    model: str
    transport: str
    api_mode: str

    def __post_init__(self) -> None:
        for name in ("provider", "model", "transport", "api_mode"):
            object.__setattr__(self, name, _non_empty(getattr(self, name), name))

    def to_dict(self) -> Dict[str, str]:
        return {
            "provider": self.provider,
            "model": self.model,
            "transport": self.transport,
            "api_mode": self.api_mode,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "RequestTarget":
        data = _strict_object(
            value,
            path="request.target",
            fields=frozenset({"provider", "model", "transport", "api_mode"}),
        )
        return cls(**data)

    @classmethod
    def from_model(cls, model: Any) -> "RequestTarget":
        """Infer transport identity from a configured model adapter."""

        return _target_from_model(model)


@dataclass(frozen=True)
class ReasoningPolicy:
    mode: Literal[
        "preserve_if_supported",
        "drop",
        "inline_replay",
        "signed_block_replay",
        "native_item_continuation",
    ] = "preserve_if_supported"
    allow_loss: bool = False

    def __post_init__(self) -> None:
        allowed = {
            "preserve_if_supported",
            "drop",
            "inline_replay",
            "signed_block_replay",
            "native_item_continuation",
        }
        if self.mode not in allowed:
            raise RequestContractError(f"unsupported reasoning policy: {self.mode!r}")

    def to_dict(self) -> Dict[str, Any]:
        return {"mode": self.mode, "allow_loss": self.allow_loss}


@dataclass(frozen=True)
class ContextBudget:
    max_input_units: int = 120_000
    reserved_output_units: int = 8_000
    unit: Literal["characters", "tokens"] = "characters"
    protected_recent_exchanges: int = 1

    def __post_init__(self) -> None:
        if self.max_input_units <= 0:
            raise RequestContractError("max_input_units must be positive")
        if self.reserved_output_units < 0:
            raise RequestContractError("reserved_output_units cannot be negative")
        if self.reserved_output_units >= self.max_input_units:
            raise RequestContractError("reserved_output_units must be below max_input_units")
        if self.protected_recent_exchanges < 0:
            raise RequestContractError("protected_recent_exchanges cannot be negative")

    @property
    def available_input_units(self) -> int:
        return self.max_input_units - self.reserved_output_units

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_input_units": self.max_input_units,
            "reserved_output_units": self.reserved_output_units,
            "available_input_units": self.available_input_units,
            "unit": self.unit,
            "protected_recent_exchanges": self.protected_recent_exchanges,
        }


@dataclass(frozen=True)
class ContinuationRef:
    reference_id: ContinuationIdentity
    resolver_key: str
    provider: str
    model: str
    api_mode: str
    attachment_id: Optional[str] = None
    payload_digest: Optional[str] = None
    expires_at: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.reference_id, ContinuationIdentity):
            raise RequestContractError(
                "reference_id must use the canonical ContinuationIdentity type"
            )
        object.__setattr__(self, "resolver_key", _logical_reference(self.resolver_key, "resolver_key"))
        for name in ("provider", "model", "api_mode"):
            object.__setattr__(self, name, _non_empty(getattr(self, name), name))
        if self.payload_digest is not None and not _SHA256.fullmatch(self.payload_digest):
            raise RequestContractError("payload_digest must be a lowercase SHA-256 digest")

    def assert_compatible(self, target: RequestTarget) -> None:
        if (
            self.provider != target.provider
            or self.model != target.model
            or self.api_mode != target.api_mode
        ):
            raise IncompatibleContinuationError(
                "continuation reference is scoped to another provider/model/API mode"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reference_id": self.reference_id.to_dict(),
            "resolver_key": self.resolver_key,
            "provider": self.provider,
            "model": self.model,
            "api_mode": self.api_mode,
            "attachment_id": self.attachment_id,
            "payload_digest": self.payload_digest,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "ContinuationRef":
        fields = frozenset(
            {
                "reference_id",
                "resolver_key",
                "provider",
                "model",
                "api_mode",
                "attachment_id",
                "payload_digest",
                "expires_at",
            }
        )
        data = _strict_object(value, path="continuation", fields=fields)
        data["reference_id"] = ContinuationIdentity.from_dict(data["reference_id"])
        return cls(**data)


@dataclass(frozen=True)
class ContextContribution:
    contribution_id: str
    source: str
    content: Any = field(repr=False, compare=False)
    priority: int = 0
    requested_placement: str = "developer"
    persistence_horizon: str = "request"
    sensitivity: str = "internal"
    model_visible: bool = True
    runtime_context_visibility: str = "model"
    required: bool = False
    revision: Optional[str] = None
    _content_json: str = field(init=False, repr=False)
    digest: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "contribution_id", _non_empty(self.contribution_id, "contribution_id"))
        object.__setattr__(self, "source", _non_empty(self.source, "source"))
        content_json = _json_text(self.content, "context.content")
        object.__setattr__(self, "_content_json", content_json)
        object.__setattr__(self, "content", None)
        object.__setattr__(self, "digest", hashlib.sha256(content_json.encode("utf-8")).hexdigest())

    @property
    def content_value(self) -> Any:
        return _json_value(self._content_json)

    def to_dict(self, *, include_content: bool = True) -> Dict[str, Any]:
        payload = {
            "contribution_id": self.contribution_id,
            "source": self.source,
            "digest": self.digest,
            "priority": self.priority,
            "requested_placement": self.requested_placement,
            "persistence_horizon": self.persistence_horizon,
            "sensitivity": self.sensitivity,
            "model_visible": self.model_visible,
            "runtime_context_visibility": self.runtime_context_visibility,
            "required": self.required,
            "revision": self.revision,
        }
        if include_content:
            payload["content"] = self.content_value
        return payload

    @classmethod
    def from_dict(cls, value: Any) -> "ContextContribution":
        fields = frozenset(
            {
                "contribution_id",
                "source",
                "content",
                "digest",
                "priority",
                "requested_placement",
                "persistence_horizon",
                "sensitivity",
                "model_visible",
                "runtime_context_visibility",
                "required",
                "revision",
            }
        )
        data = _strict_object(value, path="context_contribution", fields=fields)
        expected = data.pop("digest")
        result = cls(**data)
        if result.digest != expected:
            raise RequestContractError("context contribution digest mismatch")
        return result


class ContextContributor(Protocol):
    """Explicit provider of request-scoped context; never a global registry."""

    def contribute(self) -> Sequence[ContextContribution]:
        ...


@dataclass(frozen=True)
class CompactionReceipt:
    receipt_id: str
    input_exchange_ids: tuple[str, ...]
    output_digest: str
    policy_id: str
    declared_losses: tuple[str, ...] = ()
    model_reference: Optional[str] = None

    def __post_init__(self) -> None:
        _non_empty(self.receipt_id, "receipt_id")
        _non_empty(self.policy_id, "policy_id")
        if not _SHA256.fullmatch(self.output_digest):
            raise RequestContractError("compaction output_digest must be SHA-256")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "input_exchange_ids": list(self.input_exchange_ids),
            "output_digest": self.output_digest,
            "policy_id": self.policy_id,
            "declared_losses": list(self.declared_losses),
            "model_reference": self.model_reference,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "CompactionReceipt":
        fields = frozenset(
            {
                "receipt_id",
                "input_exchange_ids",
                "output_digest",
                "policy_id",
                "declared_losses",
                "model_reference",
            }
        )
        data = _strict_object(value, path="compaction_receipt", fields=fields)
        data["input_exchange_ids"] = tuple(data["input_exchange_ids"])
        data["declared_losses"] = tuple(data["declared_losses"])
        return cls(**data)


@dataclass(frozen=True)
class SteeringReceipt:
    receipt_id: str
    sequence: int
    item_id: str
    disposition: Literal["accepted", "queued", "applied", "rejected"]
    boundary_id: str
    reason_code: Optional[str] = None
    applied_once: bool = False

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise RequestContractError("steering sequence cannot be negative")
        if self.disposition == "applied" and not self.applied_once:
            raise RequestContractError("applied steering must be marked applied_once")
        if self.disposition != "applied" and self.applied_once:
            raise RequestContractError("only applied steering may be applied_once")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "sequence": self.sequence,
            "item_id": self.item_id,
            "disposition": self.disposition,
            "boundary_id": self.boundary_id,
            "reason_code": self.reason_code,
            "applied_once": self.applied_once,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "SteeringReceipt":
        fields = frozenset(
            {
                "receipt_id",
                "sequence",
                "item_id",
                "disposition",
                "boundary_id",
                "reason_code",
                "applied_once",
            }
        )
        return cls(**_strict_object(value, path="steering_receipt", fields=fields))


@dataclass(frozen=True)
class SelectionReport:
    selected_item_ids: tuple[str, ...]
    omitted_item_ids: tuple[str, ...]
    selected_exchange_ids: tuple[str, ...]
    omitted_exchange_ids: tuple[str, ...]
    selected_categories: tuple[str, ...]
    omitted_categories: tuple[str, ...]
    selected_context_ids: tuple[str, ...]
    omitted_context_ids: tuple[str, ...]
    total_units: int
    selected_units: int
    omitted_units: int
    unit: str
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_item_ids": list(self.selected_item_ids),
            "omitted_item_ids": list(self.omitted_item_ids),
            "selected_exchange_ids": list(self.selected_exchange_ids),
            "omitted_exchange_ids": list(self.omitted_exchange_ids),
            "selected_categories": list(self.selected_categories),
            "omitted_categories": list(self.omitted_categories),
            "selected_context_ids": list(self.selected_context_ids),
            "omitted_context_ids": list(self.omitted_context_ids),
            "total_units": self.total_units,
            "selected_units": self.selected_units,
            "omitted_units": self.omitted_units,
            "unit": self.unit,
            "reasons": list(self.reasons),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "SelectionReport":
        fields = frozenset(
            {
                "selected_item_ids",
                "omitted_item_ids",
                "selected_exchange_ids",
                "omitted_exchange_ids",
                "selected_categories",
                "omitted_categories",
                "selected_context_ids",
                "omitted_context_ids",
                "total_units",
                "selected_units",
                "omitted_units",
                "unit",
                "reasons",
            }
        )
        data = _strict_object(value, path="selection_report", fields=fields)
        for name in fields:
            if name.endswith("_ids") or name in {
                "selected_categories",
                "omitted_categories",
                "reasons",
            }:
                data[name] = tuple(data[name])
        return cls(**data)


def _item_categories(item: Any) -> set[str]:
    categories = {str(item.kind)}
    if isinstance(item, (AssistantItem,)):
        if item.tool_calls():
            categories.add("tool_calls")
            if len(item.tool_calls()) > 1:
                categories.add("parallel_tool_calls")
        if any(isinstance(part, ReasoningReference) for part in item.parts):
            categories.add("reasoning")
        if any(
            isinstance(part, AssistantContent) and part.block.type != "text"
            for part in item.parts
        ):
            categories.add("multimodal")
    if hasattr(item, "content") and any(
        isinstance(block, ContentBlock) and block.type != "text"
        for block in item.content
    ):
        categories.add("multimodal")
    if isinstance(item, ToolResultItem):
        categories.add("tool_results")
        if item.result.artifact_refs:
            categories.add("artifact_references")
    return categories


def _target_from_model(model: Any) -> RequestTarget:
    declaration = getattr(model, "qitos_request_target", None)
    if not callable(declaration):
        raise RequestContractError(
            "model adapter must declare qitos_request_target(); provider names are not inferred"
        )
    target = declaration()
    if isinstance(target, RequestTarget):
        return target
    if isinstance(target, Mapping):
        return RequestTarget.from_dict(target)
    raise RequestContractError("qitos_request_target() returned an invalid target")


@dataclass(frozen=True)
class RequestView:
    """One immutable, deterministic provider-neutral model request view."""

    request_id: str
    target: RequestTarget
    source_log_id: str
    source_log_digest: str
    selected_items_json: tuple[str, ...] = field(repr=False)
    instructions_json: tuple[str, ...] = field(default=(), repr=False)
    tool_schemas_json: tuple[str, ...] = field(default=(), repr=False)
    context_json: tuple[str, ...] = field(default=(), repr=False)
    capability_requirements: tuple[str, ...] = ()
    reasoning_policy: ReasoningPolicy = field(default_factory=ReasoningPolicy)
    continuation: Optional[ContinuationRef] = None
    context_budget: ContextBudget = field(default_factory=ContextBudget)
    selection: SelectionReport = field(
        default_factory=lambda: SelectionReport((), (), (), (), (), (), (), (), 0, 0, 0, "characters")
    )
    compaction_receipts: tuple[CompactionReceipt, ...] = ()
    artifact_refs: tuple[ArtifactRef, ...] = ()
    steering_boundary_json: str = "{}"
    correlation_facts_json: tuple[str, ...] = field(default=(), repr=False)
    provenance_json: str = "{}"
    schema_version: str = REQUEST_VIEW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REQUEST_VIEW_SCHEMA_VERSION:
            raise UnsupportedRequestVersionError(
                f"unsupported request view schema: {self.schema_version!r}"
            )
        if self.continuation is not None:
            self.continuation.assert_compatible(self.target)
        for name, values in (
            ("selected_items", self.selected_items_json),
            ("instructions", self.instructions_json),
            ("tool_schemas", self.tool_schemas_json),
            ("context", self.context_json),
            ("correlation_facts", self.correlation_facts_json),
        ):
            for value in values:
                _strict_json(_json_value(value), name)
        _strict_json(_json_value(self.steering_boundary_json), "steering_boundary")
        _strict_json(_json_value(self.provenance_json), "provenance")

    @property
    def selected_items(self) -> tuple[Dict[str, Any], ...]:
        return tuple(_json_value(value) for value in self.selected_items_json)

    @property
    def instructions(self) -> tuple[Dict[str, Any], ...]:
        return tuple(_json_value(value) for value in self.instructions_json)

    @property
    def tool_schemas(self) -> tuple[Dict[str, Any], ...]:
        return tuple(_json_value(value) for value in self.tool_schemas_json)

    @property
    def context_contributions(self) -> tuple[Dict[str, Any], ...]:
        return tuple(_json_value(value) for value in self.context_json)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "target": self.target.to_dict(),
            "source": {
                "exchange_log_id": self.source_log_id,
                "exchange_log_digest": self.source_log_digest,
            },
            "selected_items": list(self.selected_items),
            "instructions": list(self.instructions),
            "tool_schemas": list(self.tool_schemas),
            "context_contributions": list(self.context_contributions),
            "capability_requirements": list(self.capability_requirements),
            "reasoning_policy": self.reasoning_policy.to_dict(),
            "continuation": self.continuation.to_dict() if self.continuation else None,
            "context_budget": self.context_budget.to_dict(),
            "selection": self.selection.to_dict(),
            "compaction_receipts": [item.to_dict() for item in self.compaction_receipts],
            "artifact_refs": [item.to_dict() for item in self.artifact_refs],
            "steering_boundary": _json_value(self.steering_boundary_json),
            "correlation_facts": [
                _json_value(value) for value in self.correlation_facts_json
            ],
            "provenance": _json_value(self.provenance_json),
        }
        _strict_json(payload, "request_view")
        return payload

    @classmethod
    def from_dict(cls, value: Any) -> "RequestView":
        fields = frozenset(
            {
                "schema_version",
                "request_id",
                "target",
                "source",
                "selected_items",
                "instructions",
                "tool_schemas",
                "context_contributions",
                "capability_requirements",
                "reasoning_policy",
                "continuation",
                "context_budget",
                "selection",
                "compaction_receipts",
                "artifact_refs",
                "steering_boundary",
                "correlation_facts",
                "provenance",
            }
        )
        data = _strict_object(value, path="request_view", fields=fields)
        if data["schema_version"] != REQUEST_VIEW_SCHEMA_VERSION:
            raise UnsupportedRequestVersionError(
                f"unsupported request view schema: {data['schema_version']!r}"
            )
        source = _strict_object(
            data["source"],
            path="request_view.source",
            fields=frozenset({"exchange_log_id", "exchange_log_digest"}),
        )
        budget_data = _strict_object(
            data["context_budget"],
            path="context_budget",
            fields=frozenset(
                {
                    "max_input_units",
                    "reserved_output_units",
                    "available_input_units",
                    "unit",
                    "protected_recent_exchanges",
                }
            ),
        )
        available = budget_data.pop("available_input_units")
        budget = ContextBudget(**budget_data)
        if available != budget.available_input_units:
            raise RequestContractError("context budget available_input_units mismatch")
        policy_data = _strict_object(
            data["reasoning_policy"],
            path="reasoning_policy",
            fields=frozenset({"mode", "allow_loss"}),
        )
        return cls(
            schema_version=data["schema_version"],
            request_id=data["request_id"],
            target=RequestTarget.from_dict(data["target"]),
            source_log_id=source["exchange_log_id"],
            source_log_digest=source["exchange_log_digest"],
            selected_items_json=tuple(
                _json_text(item, "selected_items") for item in data["selected_items"]
            ),
            instructions_json=tuple(
                _json_text(item, "instructions") for item in data["instructions"]
            ),
            tool_schemas_json=tuple(
                _json_text(item, "tool_schemas") for item in data["tool_schemas"]
            ),
            context_json=tuple(
                _json_text(item, "context") for item in data["context_contributions"]
            ),
            capability_requirements=tuple(data["capability_requirements"]),
            reasoning_policy=ReasoningPolicy(**policy_data),
            continuation=(
                ContinuationRef.from_dict(data["continuation"])
                if data["continuation"] is not None
                else None
            ),
            context_budget=budget,
            selection=SelectionReport.from_dict(data["selection"]),
            compaction_receipts=tuple(
                CompactionReceipt.from_dict(item)
                for item in data["compaction_receipts"]
            ),
            artifact_refs=tuple(
                ArtifactRef.from_dict(item) for item in data["artifact_refs"]
            ),
            steering_boundary_json=_json_text(
                data["steering_boundary"], "steering_boundary"
            ),
            correlation_facts_json=tuple(
                _json_text(item, "correlation_facts")
                for item in data["correlation_facts"]
            ),
            provenance_json=_json_text(data["provenance"], "provenance"),
        )

    @classmethod
    def from_exchange_log(
        cls,
        log: ExchangeLog,
        *,
        model: Any = None,
        target: Optional[RequestTarget] = None,
        instructions: Iterable[Mapping[str, Any]] = (),
        tool_schemas: Iterable[Mapping[str, Any]] = (),
        capability_requirements: Iterable[str] = (),
        reasoning_policy: Optional[ReasoningPolicy] = None,
        continuation: Optional[ContinuationRef] = None,
        context_budget: Optional[ContextBudget] = None,
        context_contributions: Iterable[ContextContribution] = (),
        compaction_receipts: Iterable[CompactionReceipt] = (),
        artifact_refs: Iterable[ArtifactRef] = (),
        available_artifact_ids: Optional[Iterable[str]] = None,
    ) -> "RequestView":
        log.assert_ready_for_model_transaction()
        resolved_target = target or _target_from_model(model)
        if continuation is not None:
            continuation.assert_compatible(resolved_target)
        budget = context_budget or ContextBudget()
        policy = reasoning_policy or ReasoningPolicy()
        instruction_values = [dict(instruction) for instruction in instructions]
        for index, instruction in enumerate(instruction_values):
            role = str(instruction.get("role") or "")
            if role not in {"system", "developer", "user"}:
                raise RequestContractError(
                    f"instructions[{index}].role must be system/developer/user"
                )
            _strict_json(instruction, f"instructions[{index}]")
        schema_values = [dict(schema) for schema in tool_schemas]
        for index, schema in enumerate(schema_values):
            _strict_json(schema, f"tool_schemas[{index}]")

        references = tuple(artifact_refs)
        available = set(available_artifact_ids or ())
        for reference in references:
            if reference.required and reference.artifact_id not in available:
                raise MissingArtifactError(
                    f"required artifact {reference.artifact_id!r} is unresolved"
                )

        persisted = log.to_persistence_dict()
        source_digest = _digest(persisted)
        projected_by_id: Dict[str, Dict[str, Any]] = {}
        items = list(log.items)
        for exchange_item in items:
            projected_by_id[exchange_item.item_id] = _item_to_dict(
                exchange_item,
                redact_continuation=True,
                result_projection="model",
            )

        exchange_order: list[str] = []
        exchange_items: Dict[str, list[Any]] = {}
        for exchange_item in items:
            if exchange_item.exchange_id not in exchange_items:
                exchange_order.append(exchange_item.exchange_id)
                exchange_items[exchange_item.exchange_id] = []
            exchange_items[exchange_item.exchange_id].append(exchange_item)
        group_units = {
            exchange_id: len(
                _json_text(
                    [
                        projected_by_id[exchange_item.item_id]
                        for exchange_item in exchange_items[exchange_id]
                    ],
                    f"exchange.{exchange_id}",
                )
            )
            for exchange_id in exchange_order
        }
        instruction_units = len(_json_text(instruction_values, "instructions"))
        schema_units = len(_json_text(schema_values, "tool_schemas"))

        contributions = sorted(
            tuple(context_contributions),
            key=lambda contribution: (
                -contribution.priority,
                contribution.contribution_id,
            ),
        )
        selected_context: list[ContextContribution] = []
        omitted_context: list[ContextContribution] = []
        used = instruction_units + schema_units
        for contribution in contributions:
            units = len(contribution._content_json)
            if not contribution.model_visible:
                omitted_context.append(contribution)
                continue
            if used + units <= budget.available_input_units:
                selected_context.append(contribution)
                used += units
            elif contribution.required:
                raise UnsafeRequestBoundaryError(
                    f"required context {contribution.contribution_id!r} exceeds budget"
                )
            else:
                omitted_context.append(contribution)

        protected = set(
            exchange_order[-budget.protected_recent_exchanges :]
            if budget.protected_recent_exchanges
            else ()
        )
        selected_exchange_set: set[str] = set()
        for exchange_id in reversed(exchange_order):
            units = group_units[exchange_id]
            if exchange_id in protected or used + units <= budget.available_input_units:
                if used + units > budget.available_input_units:
                    raise UnsafeRequestBoundaryError(
                        "protected recent exchange exceeds the request context budget"
                    )
                selected_exchange_set.add(exchange_id)
                used += units
        selected_exchange_ids = tuple(
            exchange_id
            for exchange_id in exchange_order
            if exchange_id in selected_exchange_set
        )
        omitted_exchange_ids = tuple(
            exchange_id
            for exchange_id in exchange_order
            if exchange_id not in selected_exchange_set
        )
        selected_items = [
            exchange_item
            for exchange_item in items
            if exchange_item.exchange_id in selected_exchange_set
        ]
        omitted_items = [
            exchange_item
            for exchange_item in items
            if exchange_item.exchange_id not in selected_exchange_set
        ]
        selected_categories = sorted(
            {
                category
                for exchange_item in selected_items
                for category in _item_categories(exchange_item)
            }
        )
        omitted_categories = sorted(
            {
                category
                for exchange_item in omitted_items
                for category in _item_categories(exchange_item)
            }
        )
        total_units = (
            instruction_units
            + schema_units
            + sum(group_units.values())
            + sum(len(contribution._content_json) for contribution in contributions)
        )
        selection = SelectionReport(
            selected_item_ids=tuple(
                exchange_item.item_id for exchange_item in selected_items
            ),
            omitted_item_ids=tuple(
                exchange_item.item_id for exchange_item in omitted_items
            ),
            selected_exchange_ids=selected_exchange_ids,
            omitted_exchange_ids=omitted_exchange_ids,
            selected_categories=tuple(selected_categories),
            omitted_categories=tuple(omitted_categories),
            selected_context_ids=tuple(
                contribution.contribution_id for contribution in selected_context
            ),
            omitted_context_ids=tuple(
                contribution.contribution_id for contribution in omitted_context
            ),
            total_units=total_units,
            selected_units=used,
            omitted_units=max(0, total_units - used),
            unit=budget.unit,
            reasons=("exchange_safe_budget_selection",),
        )
        correlations: list[Dict[str, Any]] = []
        for exchange_item in selected_items:
            if (
                not isinstance(exchange_item, AssistantItem)
                or not exchange_item.tool_calls()
            ):
                continue
            batch_id = str(exchange_item.batch_id)
            correlations.append(
                {
                    "batch_id": batch_id,
                    "declaration_order": [
                        call.identity.call_id for call in exchange_item.tool_calls()
                    ],
                    "completion_order": [
                        result.identity.call_id
                        for result in log.results_for_batch(batch_id)
                    ],
                    "provider_scopes": [
                        call.identity.provider_scope
                        for call in exchange_item.tool_calls()
                    ],
                }
            )
        steering_ids = [
            exchange_item.item_id
            for exchange_item in selected_items
            if isinstance(exchange_item, SteeringItem)
        ]
        steering_boundary = {
            "state": "safe",
            "open_batch_id": None,
            "applied_item_ids": steering_ids,
            "queued_item_ids": [],
        }
        requirements = set(str(requirement) for requirement in capability_requirements)
        requirements.update(
            category
            for category in selected_categories
            if category
            in {
                "multimodal",
                "parallel_tool_calls",
                "reasoning",
                "tool_calls",
                "tool_results",
            }
        )
        if continuation is not None:
            requirements.add("continuation")
        provisional = {
            "schema_version": REQUEST_VIEW_SCHEMA_VERSION,
            "target": resolved_target.to_dict(),
            "source_digest": source_digest,
            "selection": selection.to_dict(),
            "instructions": instruction_values,
            "tool_schemas": schema_values,
            "context": [
                contribution.to_dict() for contribution in selected_context
            ],
            "continuation": continuation.to_dict() if continuation else None,
        }
        request_id = f"request_{_digest(provisional)[:24]}"
        result = cls(
            request_id=request_id,
            target=resolved_target,
            source_log_id=log.log_id,
            source_log_digest=source_digest,
            selected_items_json=tuple(
                _json_text(
                    projected_by_id[exchange_item.item_id], "selected_item"
                )
                for exchange_item in selected_items
            ),
            instructions_json=tuple(
                _json_text(instruction, "instruction")
                for instruction in instruction_values
            ),
            tool_schemas_json=tuple(
                _json_text(schema, "tool_schema") for schema in schema_values
            ),
            context_json=tuple(
                _json_text(contribution.to_dict(), "context")
                for contribution in selected_context
            ),
            capability_requirements=tuple(sorted(requirements)),
            reasoning_policy=policy,
            continuation=continuation,
            context_budget=budget,
            selection=selection,
            compaction_receipts=tuple(compaction_receipts),
            artifact_refs=references,
            steering_boundary_json=_json_text(steering_boundary, "steering_boundary"),
            correlation_facts_json=tuple(
                _json_text(correlation, "correlation")
                for correlation in correlations
            ),
            provenance_json=_json_text(
                {
                    "builder_version": REQUEST_BUILDER_VERSION,
                    "source": "ExchangeLog",
                    "source_schema_version": log.schema_version,
                    "ownership": "derived_ephemeral",
                },
                "provenance",
            ),
        )
        return cls.from_dict(result.to_dict())


def submit_steering(
    log: ExchangeLog,
    text: str,
    *,
    sequence: int,
    boundary_id: str,
    exchange_id: str,
    session_status: str = "running",
) -> SteeringReceipt:
    """Submit plain-text steering without exposing internal item construction."""

    item_id = f"steering_{sequence}_{_digest({'text': text})[:12]}"
    receipt_id = f"steering_receipt_{sequence}_{_digest({'item_id': item_id})[:12]}"
    if session_status in {"completed", "failed", "cancelled"}:
        return SteeringReceipt(
            receipt_id=receipt_id,
            sequence=sequence,
            item_id=item_id,
            disposition="rejected",
            boundary_id=boundary_id,
            reason_code=f"session_{session_status}",
        )
    item = SteeringItem(
        item_id=item_id,
        exchange_id=exchange_id,
        content=[ContentBlock(type="text", text=str(text))],
        metadata={"source": "session.steer", "sequence": sequence},
    )
    queued = log.open_batch_id() is not None
    log.queue_steering(item)
    return SteeringReceipt(
        receipt_id=receipt_id,
        sequence=sequence,
        item_id=item_id,
        disposition="queued" if queued else "applied",
        boundary_id=boundary_id,
        applied_once=not queued,
    )


def reconcile_steering_receipts(
    log: ExchangeLog, receipts: Iterable[SteeringReceipt], *, boundary_id: str
) -> tuple[SteeringReceipt, ...]:
    """Derive exact-once applied receipts after a safe boundary or restore."""

    committed_ids = {item.item_id for item in log.items if isinstance(item, SteeringItem)}
    queued_ids = {item.item_id for item in log.queued_steering}
    result: list[SteeringReceipt] = []
    seen_sequences: set[int] = set()
    for receipt in sorted(tuple(receipts), key=lambda item: item.sequence):
        if receipt.sequence in seen_sequences:
            raise RequestContractError("steering receipt sequence must be unique")
        seen_sequences.add(receipt.sequence)
        if receipt.disposition == "queued" and receipt.item_id in committed_ids:
            result.append(
                replace(
                    receipt,
                    disposition="applied",
                    boundary_id=boundary_id,
                    applied_once=True,
                )
            )
        elif receipt.disposition == "queued" and receipt.item_id not in queued_ids:
            raise RequestContractError("queued steering receipt has no matching log item")
        else:
            result.append(receipt)
    return tuple(result)


def _component_without_digest(component: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in component.items() if key != "digest"}


@dataclass(frozen=True)
class ConversationSnapshotComponent:
    """Lane B producer embedded by Lane A's checkpoint-v2 snapshot envelope."""

    exchange_log_json: str = field(repr=False)
    steering_receipts: tuple[SteeringReceipt, ...] = ()
    continuation_refs: tuple[ContinuationRef, ...] = ()
    context_selection: Optional[SelectionReport] = None
    compaction_receipts: tuple[CompactionReceipt, ...] = ()
    artifact_refs: tuple[ArtifactRef, ...] = ()
    reconstruction_requirements: tuple[str, ...] = (
        "exchange_log_reader",
        "continuation_resolver",
        "artifact_resolver",
    )
    schema_version: str = CONVERSATION_COMPONENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CONVERSATION_COMPONENT_SCHEMA_VERSION:
            raise UnsupportedRequestVersionError(
                f"unsupported conversation component: {self.schema_version!r}"
            )
        log = ExchangeLog.from_dict(_json_value(self.exchange_log_json))
        queued_ids = {item.item_id for item in log.queued_steering}
        receipt_queued_ids = {
            item.item_id for item in self.steering_receipts if item.disposition == "queued"
        }
        if queued_ids != receipt_queued_ids:
            raise UnsafeSnapshotComponentError(
                "queued steering and receipt identities must match exactly"
            )
        attachments = [
            attachment
            for item in log.items
            if isinstance(item, AssistantItem)
            for attachment in item.continuation_attachments
        ]
        refs_by_attachment = {
            item.attachment_id: item
            for item in self.continuation_refs
            if item.attachment_id is not None
        }
        for attachment in attachments:
            ref = refs_by_attachment.get(attachment.attachment_id)
            if ref is None or attachment.opaque_payload != {
                "resolver_ref": ref.reference_id.to_dict()
            }:
                raise UnsafeSnapshotComponentError(
                    "snapshot continuation attachments must contain resolver references only"
                )

    @property
    def exchange_log(self) -> ExchangeLog:
        return ExchangeLog.from_dict(_json_value(self.exchange_log_json))

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "exchange_log": _json_value(self.exchange_log_json),
            "steering_receipts": [item.to_dict() for item in self.steering_receipts],
            "continuation_refs": [item.to_dict() for item in self.continuation_refs],
            "context_selection": (
                self.context_selection.to_dict() if self.context_selection else None
            ),
            "compaction_receipts": [item.to_dict() for item in self.compaction_receipts],
            "artifact_refs": [item.to_dict() for item in self.artifact_refs],
            "reconstruction_requirements": list(self.reconstruction_requirements),
        }
        payload["digest"] = _digest(payload)
        return payload

    @classmethod
    def from_exchange_log(
        cls,
        log: ExchangeLog,
        *,
        steering_receipts: Iterable[SteeringReceipt] = (),
        continuation_refs: Iterable[ContinuationRef] = (),
        context_selection: Optional[SelectionReport] = None,
        compaction_receipts: Iterable[CompactionReceipt] = (),
        artifact_refs: Iterable[ArtifactRef] = (),
        reconstruction_requirements: Optional[Iterable[str]] = None,
    ) -> "ConversationSnapshotComponent":
        return cls(
            exchange_log_json=_json_text(log.to_persistence_dict(), "exchange_log"),
            steering_receipts=tuple(steering_receipts),
            continuation_refs=tuple(continuation_refs),
            context_selection=context_selection,
            compaction_receipts=tuple(compaction_receipts),
            artifact_refs=tuple(artifact_refs),
            reconstruction_requirements=tuple(
                reconstruction_requirements
                or ("exchange_log_reader", "continuation_resolver", "artifact_resolver")
            ),
        )

    @classmethod
    def from_dict(cls, value: Any) -> "ConversationSnapshotComponent":
        fields = frozenset(
            {
                "schema_version",
                "exchange_log",
                "steering_receipts",
                "continuation_refs",
                "context_selection",
                "compaction_receipts",
                "artifact_refs",
                "reconstruction_requirements",
                "digest",
            }
        )
        data = _strict_object(value, path="conversation_component", fields=fields)
        if data["schema_version"] != CONVERSATION_COMPONENT_SCHEMA_VERSION:
            raise UnsupportedRequestVersionError(
                f"unsupported conversation component: {data['schema_version']!r}"
            )
        if data["digest"] != _digest(_component_without_digest(data)):
            raise UnsafeSnapshotComponentError("conversation component digest mismatch")
        return cls(
            schema_version=data["schema_version"],
            exchange_log_json=_json_text(data["exchange_log"], "exchange_log"),
            steering_receipts=tuple(
                SteeringReceipt.from_dict(item) for item in data["steering_receipts"]
            ),
            continuation_refs=tuple(
                ContinuationRef.from_dict(item) for item in data["continuation_refs"]
            ),
            context_selection=(
                SelectionReport.from_dict(data["context_selection"])
                if data["context_selection"] is not None
                else None
            ),
            compaction_receipts=tuple(
                CompactionReceipt.from_dict(item)
                for item in data["compaction_receipts"]
            ),
            artifact_refs=tuple(
                ArtifactRef.from_dict(item) for item in data["artifact_refs"]
            ),
            reconstruction_requirements=tuple(data["reconstruction_requirements"]),
        )


class ConversationCompatibilityReader:
    """Isolated reader for supported historical conversation envelopes.

    The current writer is always `ExchangeLog.to_persistence_dict()`.  This
    reader never writes a historical shape and never exposes it as a second
    conversation API.
    """

    HISTORY_ENVELOPE_VERSION = "qitos.history_message_envelope/v1"

    @classmethod
    def read(cls, value: Any) -> ExchangeLog:
        if not isinstance(value, Mapping):
            raise RequestContractError("conversation compatibility input must be an object")
        version = value.get("schema_version")
        if version == "qitos.exchange_log.v2":
            return ExchangeLog.from_dict(value)
        fields = frozenset({"schema_version", "provider_scope", "messages"})
        data = _strict_object(
            value,
            path="history_compatibility_envelope",
            fields=fields,
        )
        if data["schema_version"] != cls.HISTORY_ENVELOPE_VERSION:
            raise UnsupportedRequestVersionError(
                f"unsupported history envelope: {data['schema_version']!r}"
            )
        if not isinstance(data["messages"], list):
            raise RequestContractError("history envelope messages must be an array")
        messages: list[HistoryMessage] = []
        message_fields = frozenset(
            {
                "role",
                "step_id",
                "content",
                "tool_calls",
                "tool_call_id",
                "name",
                "metadata",
                "native_items",
            }
        )
        for index, item in enumerate(data["messages"]):
            message = _strict_object(
                item,
                path=f"history.messages[{index}]",
                fields=message_fields,
            )
            _strict_json(message, f"history.messages[{index}]")
            messages.append(HistoryMessage(**message))
        return history_messages_to_exchange_log(
            messages,
            provider_scope=str(data["provider_scope"]),
        )


def _encode_conversation_component(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, ConversationSnapshotComponent):
        raise UnsafeSnapshotComponentError(
            "conversation snapshot codec requires ConversationSnapshotComponent"
        )
    return value.to_dict()


CONVERSATION_SNAPSHOT_COMPONENT_CODEC = SnapshotComponentCodec(
    slot="conversation",
    owner="qitos.conversation",
    schema_version=CONVERSATION_COMPONENT_SCHEMA_VERSION,
    required=True,
    encode=_encode_conversation_component,
    decode=ConversationSnapshotComponent.from_dict,
)


__all__ = [
    "REQUEST_VIEW_SCHEMA_VERSION",
    "CONVERSATION_COMPONENT_SCHEMA_VERSION",
    "CONVERSATION_SNAPSHOT_COMPONENT_CODEC",
    "REQUEST_BUILDER_VERSION",
    "RequestContractError",
    "UnsupportedRequestVersionError",
    "UnsafeRequestBoundaryError",
    "MissingArtifactError",
    "IncompatibleContinuationError",
    "UnsafeSnapshotComponentError",
    "RequestTarget",
    "ReasoningPolicy",
    "ContextBudget",
    "ContinuationRef",
    "ArtifactRef",
    "ContextContribution",
    "ContextContributor",
    "CompactionReceipt",
    "SteeringReceipt",
    "SelectionReport",
    "RequestView",
    "ConversationSnapshotComponent",
    "ConversationCompatibilityReader",
    "submit_steering",
    "reconcile_steering_receipts",
]
