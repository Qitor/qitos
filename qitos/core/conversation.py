"""Provider-neutral persistent conversation transaction contracts.

This module owns the first layer of the v4 model I/O contract.  It deliberately
does not know how an Engine selects a request view or how a provider encodes it.
"""

from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Union,
)
from uuid import uuid4

from .history import HistoryMessage
from .multimodal import ContentBlock, normalize_content_block
from .tool_result import (
    ToolResult,
    ToolResultContractError,
    ToolResultStatus as _ToolResultStatus,
)


EXCHANGE_LOG_SCHEMA_VERSION = "qitos.exchange_log.v2"
CONTINUATION_REDACTED_DIAGNOSTIC_VERSION = (
    "qitos.exchange_log.diagnostic.continuation_redacted.v1"
)


class ArgumentParseStatus(str, Enum):
    """The boundary reached while decoding raw tool-call arguments."""

    NOT_ATTEMPTED = "not_attempted"
    PARSED = "parsed"
    MALFORMED_RAW = "malformed_raw"
    PARSED_INVALID = "parsed_invalid"


class ConversationValidationError(ValueError):
    """Base class for mechanically checkable conversation contract failures."""

    code = "conversation_validation_error"

    def __init__(
        self,
        message: str,
        *,
        item_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        call_id: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.item_id = item_id
        self.batch_id = batch_id
        self.call_id = call_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "item_id": self.item_id,
            "batch_id": self.batch_id,
            "call_id": self.call_id,
        }


class UnsupportedSchemaVersionError(ConversationValidationError):
    code = "unsupported_schema_version"


class InvalidExchangeItemError(ConversationValidationError):
    code = "invalid_exchange_item"


class DuplicateItemIdError(ConversationValidationError):
    code = "duplicate_item_id"


class DuplicateCallIdError(ConversationValidationError):
    code = "duplicate_call_id"


class UnknownCallIdError(ConversationValidationError):
    code = "unknown_call_id"


class DuplicateToolResultError(ConversationValidationError):
    code = "duplicate_tool_result"


class ToolBatchMismatchError(ConversationValidationError):
    code = "tool_batch_mismatch"


class IncompleteToolBatchError(ConversationValidationError):
    code = "incomplete_tool_batch"


class UnsafeHistoryConversionError(ConversationValidationError):
    code = "unsafe_history_conversion"


class UnsupportedReasoningReplayError(UnsafeHistoryConversionError):
    code = "unsupported_reasoning_replay"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _require_id(value: str, label: str, *, item_id: Optional[str] = None) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InvalidExchangeItemError(
            f"{label} must be a non-empty string", item_id=item_id
        )


def _content_block(value: Any) -> ContentBlock:
    metadata: Dict[str, Any] = {}
    if isinstance(value, ContentBlock):
        metadata = _isolated_copy(value.metadata)
    elif isinstance(value, Mapping):
        raw_metadata = value.get("metadata")
        if isinstance(raw_metadata, Mapping):
            metadata = _isolated_copy(dict(raw_metadata))
    normalized = normalize_content_block(value)
    return ContentBlock(
        type=str(normalized.get("type") or "text"),
        text=normalized.get("text"),
        url=normalized.get("url"),
        data=normalized.get("data"),
        path=normalized.get("path"),
        mime_type=normalized.get("mime_type"),
        detail=normalized.get("detail"),
        metadata=metadata,
    )


def _content_blocks(value: Any) -> List[ContentBlock]:
    if isinstance(value, list):
        return [_content_block(block) for block in value]
    if isinstance(value, Mapping) and value.get("type"):
        return [_content_block(value)]
    return [_content_block(str(value or ""))]


def _content_payload(blocks: Sequence[ContentBlock]) -> Any:
    if len(blocks) == 1 and blocks[0].type == "text":
        return str(blocks[0].text or "")
    return [copy.deepcopy(block.to_dict()) for block in blocks]


def _isolated_copy(value: Any) -> Any:
    """Return a defensive copy for an ExchangeLog ownership boundary."""

    try:
        return copy.deepcopy(value)
    except Exception as exc:
        raise InvalidExchangeItemError(
            "exchange values must support defensive copying"
        ) from exc


def _validate_content(blocks: Sequence[ContentBlock], *, item_id: str) -> None:
    for block in blocks:
        _require_id(block.type, "content block type", item_id=item_id)


def _enum_value(enum_type: Any, value: Any, label: str) -> Any:
    try:
        return enum_type(str(value))
    except ValueError as exc:
        raise InvalidExchangeItemError(
            f"unsupported {label}: {value!r}"
        ) from exc


@dataclass(frozen=True)
class CallIdentity:
    """A call ID qualified by the provider/API scope that allocated it."""

    provider_scope: str
    call_id: str

    def validate(self) -> None:
        _require_id(self.provider_scope, "provider_scope")
        _require_id(self.call_id, "call_id")

    def key(self) -> tuple[str, str]:
        return (self.provider_scope, self.call_id)


@dataclass(frozen=True)
class OpaqueContinuationAttachment:
    """Provider-owned continuation state that the framework must not interpret."""

    attachment_id: str
    provider_scope: str
    api_mode: str
    opaque_payload: Any
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        _require_id(self.attachment_id, "attachment_id")
        _require_id(self.provider_scope, "provider_scope")
        _require_id(self.api_mode, "api_mode")

    def to_persistence_dict(self) -> Dict[str, Any]:
        return {
            "attachment_id": self.attachment_id,
            "provider_scope": self.provider_scope,
            "api_mode": self.api_mode,
            "opaque_payload": copy.deepcopy(self.opaque_payload),
            "metadata": copy.deepcopy(self.metadata),
        }

    def to_continuation_redacted_dict(self) -> Dict[str, Any]:
        """Redact only opaque continuation bytes for diagnostic inspection."""

        return {
            "attachment_id": self.attachment_id,
            "provider_scope": self.provider_scope,
            "api_mode": self.api_mode,
            "opaque_payload": {"redacted": True},
            "metadata": copy.deepcopy(self.metadata),
        }


@dataclass(frozen=True)
class AssistantContent:
    block: ContentBlock
    kind: str = field(default="content", init=False)


@dataclass(frozen=True)
class ReasoningReference:
    """A reference to reasoning state; never the signed/encrypted content itself."""

    provider_scope: str
    reference_id: str
    attachment_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    kind: str = field(default="reasoning_reference", init=False)

    def validate(self) -> None:
        _require_id(self.provider_scope, "provider_scope")
        _require_id(self.reference_id, "reference_id")


@dataclass(frozen=True)
class ReasoningBlock:
    """Ordered provider reasoning fact without treating it as assistant text.

    `summary` is optional provider-authored visible reasoning. Signed,
    encrypted, or otherwise opaque bytes stay in the correlated continuation
    attachment and never enter this field.
    """

    provider_scope: str
    reference_id: str
    block_type: str
    summary: Optional[str] = None
    attachment_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    kind: str = field(default="reasoning_block", init=False)

    def validate(self) -> None:
        _require_id(self.provider_scope, "provider_scope")
        _require_id(self.reference_id, "reference_id")
        _require_id(self.block_type, "block_type")
        if self.summary is not None and not isinstance(self.summary, str):
            raise InvalidExchangeItemError("reasoning block summary must be a string")


@dataclass(frozen=True)
class ToolCall:
    identity: CallIdentity
    batch_id: str
    name: str
    raw_arguments: str
    parsed_arguments: Optional[Dict[str, Any]] = None
    parse_status: ArgumentParseStatus = ArgumentParseStatus.NOT_ATTEMPTED
    parse_error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    kind: str = field(default="tool_call", init=False)

    def validate(self) -> None:
        self.identity.validate()
        _require_id(self.batch_id, "batch_id")
        _require_id(self.name, "tool name")
        if not isinstance(self.raw_arguments, str):
            raise InvalidExchangeItemError(
                "raw_arguments must be a string",
                batch_id=self.batch_id,
                call_id=self.identity.call_id,
            )
        if self.parse_status is ArgumentParseStatus.PARSED:
            if not isinstance(self.parsed_arguments, dict):
                raise InvalidExchangeItemError(
                    "parse_status='parsed' requires parsed_arguments",
                    batch_id=self.batch_id,
                    call_id=self.identity.call_id,
                )
            if self.parse_error:
                raise InvalidExchangeItemError(
                    "parse_status='parsed' cannot carry parse_error",
                    batch_id=self.batch_id,
                    call_id=self.identity.call_id,
                )
        elif self.parsed_arguments is not None:
            raise InvalidExchangeItemError(
                "parsed_arguments require parse_status='parsed'",
                batch_id=self.batch_id,
                call_id=self.identity.call_id,
            )


AssistantPart = Union[
    AssistantContent,
    ReasoningReference,
    ReasoningBlock,
    ToolCall,
]


@dataclass(frozen=True)
class UserItem:
    item_id: str
    exchange_id: str
    content: List[ContentBlock]
    metadata: Dict[str, Any] = field(default_factory=dict)
    kind: str = field(default="user", init=False)

    def validate(self) -> None:
        _require_id(self.item_id, "item_id", item_id=self.item_id)
        _require_id(self.exchange_id, "exchange_id", item_id=self.item_id)
        _validate_content(self.content, item_id=self.item_id)


@dataclass(frozen=True)
class SteeringItem:
    item_id: str
    exchange_id: str
    content: List[ContentBlock]
    metadata: Dict[str, Any] = field(default_factory=dict)
    kind: str = field(default="steering", init=False)

    def validate(self) -> None:
        _require_id(self.item_id, "item_id", item_id=self.item_id)
        _require_id(self.exchange_id, "exchange_id", item_id=self.item_id)
        _validate_content(self.content, item_id=self.item_id)


@dataclass(frozen=True)
class AssistantItem:
    item_id: str
    exchange_id: str
    parts: List[AssistantPart]
    continuation_attachments: List[OpaqueContinuationAttachment] = field(
        default_factory=list
    )
    metadata: Dict[str, Any] = field(default_factory=dict)
    kind: str = field(default="assistant", init=False)

    def validate(self) -> None:
        _require_id(self.item_id, "item_id", item_id=self.item_id)
        _require_id(self.exchange_id, "exchange_id", item_id=self.item_id)
        attachment_ids: set[str] = set()
        calls = self.tool_calls()
        batch_ids = {call.batch_id for call in calls}
        if len(batch_ids) > 1:
            raise ToolBatchMismatchError(
                "one assistant item cannot declare calls from multiple batches",
                item_id=self.item_id,
            )
        for part in self.parts:
            if isinstance(part, AssistantContent):
                _validate_content([part.block], item_id=self.item_id)
                continue
            part.validate()
        for attachment in self.continuation_attachments:
            attachment.validate()
            if attachment.attachment_id in attachment_ids:
                raise InvalidExchangeItemError(
                    "duplicate continuation attachment ID", item_id=self.item_id
                )
            attachment_ids.add(attachment.attachment_id)
        for part in self.parts:
            if isinstance(part, (ReasoningReference, ReasoningBlock)) and part.attachment_id:
                if part.attachment_id not in attachment_ids:
                    raise InvalidExchangeItemError(
                        "reasoning reference points to an unknown attachment",
                        item_id=self.item_id,
                    )

    def tool_calls(self) -> List[ToolCall]:
        return [part for part in self.parts if isinstance(part, ToolCall)]

    @property
    def batch_id(self) -> Optional[str]:
        calls = self.tool_calls()
        return calls[0].batch_id if calls else None


@dataclass(frozen=True)
class ToolResultItem:
    """Conversation correlation and closure facts around one canonical result."""

    item_id: str
    exchange_id: str
    identity: CallIdentity
    batch_id: str
    result: ToolResult
    synthetic: bool = False
    closure_reason: Optional[str] = None
    kind: str = field(default="tool_result", init=False)

    def validate(self) -> None:
        _require_id(self.item_id, "item_id", item_id=self.item_id)
        _require_id(self.exchange_id, "exchange_id", item_id=self.item_id)
        self.identity.validate()
        _require_id(self.batch_id, "batch_id", item_id=self.item_id)
        if not isinstance(self.result, ToolResult):
            raise InvalidExchangeItemError(
                "tool result item must contain canonical ToolResult",
                item_id=self.item_id,
                batch_id=self.batch_id,
                call_id=self.identity.call_id,
            )
        try:
            self.result.to_persistence_dict()
        except ToolResultContractError as exc:
            raise InvalidExchangeItemError(
                f"invalid canonical ToolResult: {exc}",
                item_id=self.item_id,
                batch_id=self.batch_id,
                call_id=self.identity.call_id,
            ) from exc
        if self.synthetic and not self.closure_reason:
            raise InvalidExchangeItemError(
                "synthetic closure requires closure_reason",
                item_id=self.item_id,
                batch_id=self.batch_id,
                call_id=self.identity.call_id,
            )
        if self.result.error_code == "missing_worker" and not self.synthetic:
            raise InvalidExchangeItemError(
                "missing_worker must be an explicit synthetic closure",
                item_id=self.item_id,
                batch_id=self.batch_id,
                call_id=self.identity.call_id,
            )
        if (
            self.result.action_id is not None
            and self.result.action_id != self.identity.call_id
        ):
            raise ToolBatchMismatchError(
                "canonical result action_id does not match call identity",
                item_id=self.item_id,
                batch_id=self.batch_id,
                call_id=self.identity.call_id,
            )


ExchangeItem = Union[UserItem, SteeringItem, AssistantItem, ToolResultItem]


class ExchangeLog:
    """Append-only persistent exchange facts and queued safe-boundary steering."""

    def __init__(
        self,
        log_id: Optional[str] = None,
        *,
        items: Optional[Iterable[ExchangeItem]] = None,
        queued_steering: Optional[Iterable[SteeringItem]] = None,
        schema_version: str = EXCHANGE_LOG_SCHEMA_VERSION,
    ) -> None:
        self.log_id = _new_id("log") if log_id is None else log_id
        self.schema_version = schema_version
        self._items = [_isolated_copy(item) for item in (items or [])]
        self._queued_steering = [
            _isolated_copy(item) for item in (queued_steering or [])
        ]
        self.validate()

    @property
    def items(self) -> tuple[ExchangeItem, ...]:
        """An isolated snapshot of committed persistent items."""
        return tuple(_isolated_copy(item) for item in self._items)

    @property
    def queued_steering(self) -> tuple[SteeringItem, ...]:
        """An isolated snapshot of steering waiting for the open batch boundary."""
        return tuple(_isolated_copy(item) for item in self._queued_steering)

    def append(self, item: ExchangeItem) -> Optional["ToolBatchBuilder"]:
        self.validate()
        owned_item = _isolated_copy(item)
        open_batch = self.open_batch_id()
        if open_batch is not None:
            if isinstance(owned_item, SteeringItem):
                self._ensure_new_item_id(owned_item.item_id)
                owned_item.validate()
                self._queued_steering.append(owned_item)
                self.validate()
                return None
            raise IncompleteToolBatchError(
                "an incomplete tool batch blocks the next persistent item",
                item_id=owned_item.item_id,
                batch_id=open_batch,
            )
        self._ensure_new_item_id(owned_item.item_id)
        owned_item.validate()
        if isinstance(owned_item, ToolResultItem):
            raise InvalidExchangeItemError(
                "tool results must be committed by ToolBatchBuilder",
                item_id=owned_item.item_id,
                batch_id=owned_item.batch_id,
                call_id=owned_item.identity.call_id,
            )
        self._items.append(owned_item)
        try:
            self.validate()
        except Exception:
            self._items.pop()
            raise
        if isinstance(owned_item, AssistantItem) and owned_item.tool_calls():
            return ToolBatchBuilder(self, str(owned_item.batch_id))
        return None

    def queue_steering(self, item: SteeringItem) -> None:
        if self.open_batch_id() is None:
            self.append(item)
            return
        owned_item = _isolated_copy(item)
        self._ensure_new_item_id(owned_item.item_id)
        owned_item.validate()
        self._queued_steering.append(owned_item)
        self.validate()

    def validate(self) -> None:
        if self.schema_version != EXCHANGE_LOG_SCHEMA_VERSION:
            raise UnsupportedSchemaVersionError(
                f"unsupported exchange schema: {self.schema_version!r}"
            )
        _require_id(self.log_id, "log_id")
        item_ids: set[str] = set()
        call_keys: set[tuple[str, str]] = set()
        declarations: Dict[str, List[ToolCall]] = {}
        declaration_positions: Dict[str, int] = {}
        declaration_exchange_ids: Dict[str, str] = {}
        results: Dict[str, List[ToolResultItem]] = {}
        result_keys: set[tuple[str, str]] = set()

        for position, item in enumerate(self._items):
            item.validate()
            if item.item_id in item_ids:
                raise DuplicateItemIdError(
                    f"duplicate item ID: {item.item_id}", item_id=item.item_id
                )
            item_ids.add(item.item_id)
            if isinstance(item, AssistantItem):
                calls = item.tool_calls()
                if not calls:
                    continue
                batch_id = str(item.batch_id)
                if batch_id in declarations:
                    raise ToolBatchMismatchError(
                        f"batch {batch_id!r} has multiple assistant declarations",
                        item_id=item.item_id,
                        batch_id=batch_id,
                    )
                declarations[batch_id] = calls
                declaration_positions[batch_id] = position
                declaration_exchange_ids[batch_id] = item.exchange_id
                for call in calls:
                    key = call.identity.key()
                    if key in call_keys:
                        raise DuplicateCallIdError(
                            "duplicate call ID within provider scope",
                            item_id=item.item_id,
                            batch_id=batch_id,
                            call_id=call.identity.call_id,
                        )
                    call_keys.add(key)
            elif isinstance(item, ToolResultItem):
                if item.batch_id not in declarations:
                    raise UnknownCallIdError(
                        "tool result has no preceding assistant declaration",
                        item_id=item.item_id,
                        batch_id=item.batch_id,
                        call_id=item.identity.call_id,
                    )
                declared = {
                    call.identity.key(): call
                    for call in declarations[item.batch_id]
                }
                key = item.identity.key()
                if key not in declared:
                    raise UnknownCallIdError(
                        "tool result references an undeclared call",
                        item_id=item.item_id,
                        batch_id=item.batch_id,
                        call_id=item.identity.call_id,
                    )
                declared_call = declared[key]
                if (
                    item.result.tool_name is not None
                    and item.result.tool_name != declared_call.name
                ):
                    raise ToolBatchMismatchError(
                        "canonical result tool_name does not match declaration",
                        item_id=item.item_id,
                        batch_id=item.batch_id,
                        call_id=item.identity.call_id,
                    )
                if item.exchange_id != declaration_exchange_ids[item.batch_id]:
                    raise ToolBatchMismatchError(
                        "tool result exchange_id must match its declaration",
                        item_id=item.item_id,
                        batch_id=item.batch_id,
                        call_id=item.identity.call_id,
                    )
                if key in result_keys:
                    raise DuplicateToolResultError(
                        "a declared call has more than one result",
                        item_id=item.item_id,
                        batch_id=item.batch_id,
                        call_id=item.identity.call_id,
                    )
                result_keys.add(key)
                results.setdefault(item.batch_id, []).append(item)

        for queued in self._queued_steering:
            queued.validate()
            if queued.item_id in item_ids:
                raise DuplicateItemIdError(
                    f"duplicate item ID: {queued.item_id}", item_id=queued.item_id
                )
            item_ids.add(queued.item_id)

        open_batches: List[str] = []
        for batch_id, calls in declarations.items():
            batch_results = results.get(batch_id, [])
            if len(batch_results) < len(calls):
                open_batches.append(batch_id)
                continue
            last_result_position = max(
                index
                for index, item in enumerate(self._items)
                if isinstance(item, ToolResultItem) and item.batch_id == batch_id
            )
            if last_result_position <= declaration_positions[batch_id]:
                raise ToolBatchMismatchError(
                    "tool results must follow their assistant declaration",
                    batch_id=batch_id,
                )
        if len(open_batches) > 1:
            raise IncompleteToolBatchError(
                "an ExchangeLog cannot contain multiple open tool batches",
                batch_id=open_batches[0],
            )
        if self.queued_steering and not open_batches:
            raise InvalidExchangeItemError(
                "queued steering is only valid while a tool batch is open"
            )
        if open_batches:
            open_batch = open_batches[0]
            open_position = declaration_positions[open_batch]
            for item in self._items[open_position + 1 :]:
                if not (
                    isinstance(item, ToolResultItem)
                    and item.batch_id == open_batch
                ):
                    raise IncompleteToolBatchError(
                        "normal items cannot follow an incomplete tool batch",
                        item_id=item.item_id,
                        batch_id=open_batch,
                    )

    def _ensure_new_item_id(self, item_id: str) -> None:
        known = {item.item_id for item in self._items}
        known.update(item.item_id for item in self._queued_steering)
        if item_id in known:
            raise DuplicateItemIdError(
                f"duplicate item ID: {item_id}", item_id=item_id
            )

    def declared_calls(self, batch_id: str) -> List[ToolCall]:
        for item in self._items:
            if isinstance(item, AssistantItem) and item.batch_id == batch_id:
                return _isolated_copy(item.tool_calls())
        raise ToolBatchMismatchError(
            f"unknown tool batch: {batch_id!r}", batch_id=batch_id
        )

    def results_for_batch(self, batch_id: str) -> List[ToolResultItem]:
        return _isolated_copy([
            item
            for item in self._items
            if isinstance(item, ToolResultItem) and item.batch_id == batch_id
        ])

    def results_for_batch_in_declaration_order(
        self, batch_id: str
    ) -> List[ToolResultItem]:
        """Derive results in call declaration order without rewriting facts."""

        results = {
            result.identity.key(): result
            for result in self.results_for_batch(batch_id)
        }
        return [
            results[call.identity.key()]
            for call in self.declared_calls(batch_id)
            if call.identity.key() in results
        ]

    def open_batch_id(self) -> Optional[str]:
        declarations: List[tuple[str, int]] = []
        counts: Dict[str, int] = {}
        for item in self._items:
            if isinstance(item, AssistantItem) and item.tool_calls():
                declarations.append((str(item.batch_id), len(item.tool_calls())))
            elif isinstance(item, ToolResultItem):
                counts[item.batch_id] = counts.get(item.batch_id, 0) + 1
        for batch_id, expected in declarations:
            if counts.get(batch_id, 0) < expected:
                return batch_id
        return None

    def assert_ready_for_model_transaction(self) -> None:
        self.validate()
        batch_id = self.open_batch_id()
        if batch_id is not None:
            missing = [
                call.identity.call_id
                for call in self.declared_calls(batch_id)
                if call.identity.key()
                not in {
                    result.identity.key()
                    for result in self.results_for_batch(batch_id)
                }
            ]
            raise IncompleteToolBatchError(
                f"tool batch is incomplete; missing results: {missing}",
                batch_id=batch_id,
            )

    def request(self, **kwargs: Any) -> Any:
        """Derive one immutable provider-neutral request view.

        The import remains local so the persistent conversation layer does not
        depend on request-selection mechanics during module initialization.
        `RequestView` is ephemeral and this method never mutates the log.
        """

        from .request_view import RequestView

        return RequestView.from_exchange_log(self, **kwargs)

    def to_persistence_dict(self) -> Dict[str, Any]:
        self.validate()
        payload = {
            "schema_version": self.schema_version,
            "log_id": self.log_id,
            "items": [
                _item_to_dict(item, redact_continuation=False)
                for item in self._items
            ],
            "queued_steering": [
                _item_to_dict(item, redact_continuation=False)
                for item in self._queued_steering
            ],
        }
        try:
            json.dumps(payload, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise InvalidExchangeItemError(
                "persistence payload must be JSON-serializable"
            ) from exc
        return payload

    def to_continuation_redacted_diagnostic_dict(self) -> Dict[str, Any]:
        """Return a diagnostic view; metadata and other secrets are unchanged."""

        self.validate()
        return {
            "schema_version": self.schema_version,
            "projection_version": CONTINUATION_REDACTED_DIAGNOSTIC_VERSION,
            "projection_policy": {
                "opaque_continuation": "redacted",
                "all_other_fields": "unchanged_not_privacy_filtered",
            },
            "log_id": self.log_id,
            "items": [
                _item_to_dict(item, redact_continuation=True)
                for item in self._items
            ],
            "queued_steering": [
                _item_to_dict(item, redact_continuation=True)
                for item in self._queued_steering
            ],
        }

    def to_model_dict(self) -> Dict[str, Any]:
        """Project canonical results through ToolResult's public model view."""

        self.validate()
        return {
            "schema_version": self.schema_version,
            "log_id": self.log_id,
            "items": [
                _item_to_dict(
                    item,
                    redact_continuation=True,
                    result_projection="model",
                )
                for item in self._items
            ],
            "queued_steering": [
                _item_to_dict(
                    item,
                    redact_continuation=True,
                    result_projection="model",
                )
                for item in self._queued_steering
            ],
        }

    def to_trace_safe_dict(self) -> Dict[str, Any]:
        """Project canonical results through ToolResult's trace-safe view."""

        self.validate()
        return {
            "schema_version": self.schema_version,
            "log_id": self.log_id,
            "items": [
                _item_to_dict(
                    item,
                    redact_continuation=True,
                    result_projection="trace_safe",
                )
                for item in self._items
            ],
            "queued_steering": [
                _item_to_dict(
                    item,
                    redact_continuation=True,
                    result_projection="trace_safe",
                )
                for item in self._queued_steering
            ],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExchangeLog":
        try:
            data = _validate_persistence_payload(payload)
            version = data["schema_version"]
            log = cls(
                log_id=data["log_id"],
                items=[_item_from_dict(item) for item in data["items"]],
                queued_steering=[
                    _steering_from_dict(item) for item in data["queued_steering"]
                ],
                schema_version=version,
            )
            log.validate()
            return log
        except ConversationValidationError:
            raise
        except (KeyError, TypeError, ValueError, ToolResultContractError) as exc:
            raise InvalidExchangeItemError(
                f"invalid exchange persistence payload: {exc}"
            ) from exc


class ToolBatchBuilder:
    """Persist terminal results immediately and close an active tool batch."""

    def __init__(self, exchange_log: ExchangeLog, batch_id: str) -> None:
        exchange_log.validate()
        self.exchange_log = exchange_log
        self.batch_id = batch_id
        self.calls = exchange_log.declared_calls(batch_id)
        self._results: Dict[tuple[str, str], ToolResultItem] = {
            result.identity.key(): result
            for result in exchange_log.results_for_batch(batch_id)
        }
        if exchange_log.open_batch_id() != batch_id:
            raise ToolBatchMismatchError(
                "batch is not the active open batch", batch_id=batch_id
            )

    @property
    def missing_calls(self) -> List[ToolCall]:
        return [
            call for call in self.calls if call.identity.key() not in self._results
        ]

    @property
    def exchange_id(self) -> str:
        """The stable exchange identity shared by the declaration and results."""
        return self._exchange_id()

    def record_result(self, result: ToolResultItem) -> bool:
        owned_result = _isolated_copy(result)
        owned_result.validate()
        if self.exchange_log.open_batch_id() != self.batch_id:
            raise ToolBatchMismatchError(
                "batch is no longer the active open batch", batch_id=self.batch_id
            )
        self._results = {
            persisted.identity.key(): persisted
            for persisted in self.exchange_log.results_for_batch(self.batch_id)
        }
        if owned_result.batch_id != self.batch_id:
            raise ToolBatchMismatchError(
                "result batch does not match the active builder",
                item_id=owned_result.item_id,
                batch_id=owned_result.batch_id,
                call_id=owned_result.identity.call_id,
            )
        if owned_result.exchange_id != self._exchange_id():
            raise ToolBatchMismatchError(
                "result exchange_id does not match the assistant declaration",
                item_id=owned_result.item_id,
                batch_id=owned_result.batch_id,
                call_id=owned_result.identity.call_id,
            )
        declared = {call.identity.key() for call in self.calls}
        key = owned_result.identity.key()
        if key not in declared:
            raise UnknownCallIdError(
                "result references an undeclared call",
                item_id=owned_result.item_id,
                batch_id=self.batch_id,
                call_id=owned_result.identity.call_id,
            )
        if key in self._results:
            raise DuplicateToolResultError(
                "a declared call cannot receive two results",
                item_id=owned_result.item_id,
                batch_id=self.batch_id,
                call_id=owned_result.identity.call_id,
            )
        self.exchange_log._ensure_new_item_id(owned_result.item_id)

        original_items = list(self.exchange_log._items)
        original_steering = list(self.exchange_log._queued_steering)
        self.exchange_log._items.append(owned_result)
        self._results[key] = owned_result
        closed = not self.missing_calls
        if closed:
            self.exchange_log._items.extend(self.exchange_log._queued_steering)
            self.exchange_log._queued_steering = []
        try:
            self.exchange_log.validate()
        except Exception:
            self.exchange_log._items = original_items
            self.exchange_log._queued_steering = original_steering
            self._results.pop(key, None)
            raise
        return closed

    def close_missing(
        self,
        *,
        status: _ToolResultStatus,
        reason: str,
        source: str = "qitos.tool_batch_builder",
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        if status == "success":
            raise InvalidExchangeItemError(
                "synthetic closure cannot report success", batch_id=self.batch_id
            )
        for call in list(self.missing_calls):
            error_kind: Literal["policy", "execution"] = (
                "policy" if status == "skipped" else "execution"
            )
            result = ToolResultItem(
                item_id=_new_id("tool_result"),
                exchange_id=self._exchange_id(),
                identity=call.identity,
                batch_id=self.batch_id,
                result=ToolResult(
                    status=status,
                    tool_name=call.name,
                    action_id=call.identity.call_id,
                    error=message or f"Tool call closed synthetically: {reason}",
                    error_kind=error_kind,
                    error_code=reason,
                    provenance={
                        "source": source,
                        "synthetic": True,
                        "closure_reason": reason,
                        "details": dict(details or {}),
                    },
                ),
                synthetic=True,
                closure_reason=reason,
            )
            self.record_result(result)

    def _exchange_id(self) -> str:
        for item in self.exchange_log._items:
            if isinstance(item, AssistantItem) and item.batch_id == self.batch_id:
                return item.exchange_id
        raise ToolBatchMismatchError(
            "batch assistant declaration disappeared", batch_id=self.batch_id
        )


def _part_to_dict(part: AssistantPart) -> Dict[str, Any]:
    if isinstance(part, AssistantContent):
        return {"kind": part.kind, "block": copy.deepcopy(part.block.to_dict())}
    if isinstance(part, ReasoningReference):
        return {
            "kind": part.kind,
            "provider_scope": part.provider_scope,
            "reference_id": part.reference_id,
            "attachment_id": part.attachment_id,
            "metadata": copy.deepcopy(part.metadata),
        }
    if isinstance(part, ReasoningBlock):
        return {
            "kind": part.kind,
            "provider_scope": part.provider_scope,
            "reference_id": part.reference_id,
            "block_type": part.block_type,
            "summary": part.summary,
            "attachment_id": part.attachment_id,
            "metadata": copy.deepcopy(part.metadata),
        }
    return {
        "kind": part.kind,
        "provider_scope": part.identity.provider_scope,
        "call_id": part.identity.call_id,
        "batch_id": part.batch_id,
        "name": part.name,
        "raw_arguments": part.raw_arguments,
        "parsed_arguments": copy.deepcopy(part.parsed_arguments),
        "parse_status": part.parse_status.value,
        "parse_error": part.parse_error,
        "metadata": copy.deepcopy(part.metadata),
    }


def _part_from_dict(payload: Any) -> AssistantPart:
    if not isinstance(payload, Mapping):
        raise InvalidExchangeItemError("assistant part must be an object")
    kind = str(payload.get("kind") or "")
    if kind == "content":
        return AssistantContent(_content_block(payload.get("block", {})))
    if kind == "reasoning_reference":
        return ReasoningReference(
            provider_scope=str(payload.get("provider_scope") or ""),
            reference_id=str(payload.get("reference_id") or ""),
            attachment_id=(
                str(payload["attachment_id"])
                if payload.get("attachment_id") is not None
                else None
            ),
            metadata=dict(payload.get("metadata") or {}),
        )
    if kind == "reasoning_block":
        return ReasoningBlock(
            provider_scope=str(payload.get("provider_scope") or ""),
            reference_id=str(payload.get("reference_id") or ""),
            block_type=str(payload.get("block_type") or ""),
            summary=(
                str(payload["summary"])
                if payload.get("summary") is not None
                else None
            ),
            attachment_id=(
                str(payload["attachment_id"])
                if payload.get("attachment_id") is not None
                else None
            ),
            metadata=dict(payload.get("metadata") or {}),
        )
    if kind == "tool_call":
        parsed = payload.get("parsed_arguments")
        raw_arguments = payload.get("raw_arguments")
        if not isinstance(raw_arguments, str):
            raise InvalidExchangeItemError("raw_arguments must be a string")
        return ToolCall(
            identity=CallIdentity(
                provider_scope=str(payload.get("provider_scope") or ""),
                call_id=str(payload.get("call_id") or ""),
            ),
            batch_id=str(payload.get("batch_id") or ""),
            name=str(payload.get("name") or ""),
            raw_arguments=raw_arguments,
            parsed_arguments=dict(parsed) if isinstance(parsed, Mapping) else None,
            parse_status=_enum_value(
                ArgumentParseStatus,
                payload.get("parse_status") or "not_attempted",
                "argument parse status",
            ),
            parse_error=(
                str(payload["parse_error"])
                if payload.get("parse_error") is not None
                else None
            ),
            metadata=dict(payload.get("metadata") or {}),
        )
    raise InvalidExchangeItemError(f"unsupported assistant part kind: {kind!r}")


def _item_to_dict(
    item: ExchangeItem,
    *,
    redact_continuation: bool,
    result_projection: str = "persistence",
) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "kind": item.kind,
        "item_id": item.item_id,
        "exchange_id": item.exchange_id,
    }
    if not isinstance(item, ToolResultItem):
        base["metadata"] = copy.deepcopy(item.metadata)
    if isinstance(item, (UserItem, SteeringItem)):
        base["content"] = [copy.deepcopy(block.to_dict()) for block in item.content]
    elif isinstance(item, AssistantItem):
        base["parts"] = [_part_to_dict(part) for part in item.parts]
        base["continuation_attachments"] = [
            attachment.to_continuation_redacted_dict()
            if redact_continuation
            else attachment.to_persistence_dict()
            for attachment in item.continuation_attachments
        ]
    else:
        if result_projection == "model":
            canonical_result = item.result.to_model_dict()
        elif result_projection == "trace_safe":
            canonical_result = item.result.to_trace_safe_dict()
        else:
            canonical_result = item.result.to_persistence_dict()
        base.update(
            {
                "provider_scope": item.identity.provider_scope,
                "call_id": item.identity.call_id,
                "batch_id": item.batch_id,
                "result": canonical_result,
                "synthetic": item.synthetic,
                "closure_reason": item.closure_reason,
            }
        )
    return base


_TOP_LEVEL_FIELDS = frozenset(
    {"schema_version", "log_id", "items", "queued_steering"}
)
_CONTENT_FIELDS = frozenset(
    {"type", "text", "url", "data", "path", "mime_type", "detail", "metadata"}
)
_ITEM_FIELDS = {
    "user": frozenset({"kind", "item_id", "exchange_id", "content", "metadata"}),
    "steering": frozenset(
        {"kind", "item_id", "exchange_id", "content", "metadata"}
    ),
    "assistant": frozenset(
        {
            "kind",
            "item_id",
            "exchange_id",
            "parts",
            "continuation_attachments",
            "metadata",
        }
    ),
    "tool_result": frozenset(
        {
            "kind",
            "item_id",
            "exchange_id",
            "provider_scope",
            "call_id",
            "batch_id",
            "result",
            "synthetic",
            "closure_reason",
        }
    ),
}
_PART_FIELDS = {
    "content": frozenset({"kind", "block"}),
    "reasoning_reference": frozenset(
        {"kind", "provider_scope", "reference_id", "attachment_id", "metadata"}
    ),
    "reasoning_block": frozenset(
        {
            "kind",
            "provider_scope",
            "reference_id",
            "block_type",
            "summary",
            "attachment_id",
            "metadata",
        }
    ),
    "tool_call": frozenset(
        {
            "kind",
            "provider_scope",
            "call_id",
            "batch_id",
            "name",
            "raw_arguments",
            "parsed_arguments",
            "parse_status",
            "parse_error",
            "metadata",
        }
    ),
}
_ATTACHMENT_FIELDS = frozenset(
    {"attachment_id", "provider_scope", "api_mode", "opaque_payload", "metadata"}
)


def _strict_object(value: Any, path: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidExchangeItemError(f"{path} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise InvalidExchangeItemError(f"{path} keys must be strings")
    return dict(value)


def _strict_fields(
    value: Any,
    *,
    path: str,
    allowed: frozenset[str],
    required: frozenset[str] = frozenset(),
) -> Dict[str, Any]:
    data = _strict_object(value, path)
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise InvalidExchangeItemError(
            f"{path} has unknown field {unknown[0]!r}"
        )
    missing = sorted(required - set(data))
    if missing:
        raise InvalidExchangeItemError(
            f"{path} is missing required field {missing[0]!r}"
        )
    return data


def _strict_string(value: Any, path: str, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if not isinstance(value, str):
        raise InvalidExchangeItemError(f"{path} must be a string")


def _strict_json(
    value: Any,
    path: str,
    *,
    _active: Optional[set[int]] = None,
    _counter: Optional[list[int]] = None,
    _depth: int = 0,
) -> None:
    active = _active if _active is not None else set()
    counter = _counter if _counter is not None else [0]
    if _depth > 64:
        raise InvalidExchangeItemError(f"{path} exceeds the JSON depth limit")
    counter[0] += 1
    if counter[0] > 100_000:
        raise InvalidExchangeItemError(f"{path} exceeds the JSON node limit")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidExchangeItemError(f"{path} must be finite")
        return
    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in active:
            raise InvalidExchangeItemError(f"{path} contains a JSON cycle")
        active.add(identity)
        try:
            for index, item in enumerate(value):
                _strict_json(
                    item,
                    f"{path}[{index}]",
                    _active=active,
                    _counter=counter,
                    _depth=_depth + 1,
                )
        finally:
            active.remove(identity)
        return
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            raise InvalidExchangeItemError(f"{path} contains a JSON cycle")
        active.add(identity)
        try:
            for key, item in value.items():
                if not isinstance(key, str):
                    raise InvalidExchangeItemError(f"{path} keys must be strings")
                _strict_json(
                    item,
                    f"{path}.[field]",
                    _active=active,
                    _counter=counter,
                    _depth=_depth + 1,
                )
        finally:
            active.remove(identity)
        return
    raise InvalidExchangeItemError(
        f"{path} contains non-JSON value {type(value).__name__}"
    )


def _validate_content_payload(value: Any, path: str) -> None:
    if not isinstance(value, list):
        raise InvalidExchangeItemError(f"{path} must be an array")
    for index, block in enumerate(value):
        block_path = f"{path}[{index}]"
        data = _strict_fields(
            block,
            path=block_path,
            allowed=_CONTENT_FIELDS,
            required=frozenset({"type"}),
        )
        _strict_string(data["type"], f"{block_path}.type")
        if "metadata" in data:
            _strict_object(data["metadata"], f"{block_path}.metadata")
        for field_name in _CONTENT_FIELDS - {"type", "metadata"}:
            if field_name in data:
                _strict_string(
                    data[field_name],
                    f"{block_path}.{field_name}",
                    optional=True,
                )


def _validate_part_payload(value: Any, path: str) -> None:
    data = _strict_object(value, path)
    kind = data.get("kind")
    if not isinstance(kind, str) or kind not in _PART_FIELDS:
        raise InvalidExchangeItemError(f"{path}.kind is unsupported")
    required = {
        "content": frozenset({"kind", "block"}),
        "reasoning_reference": frozenset(
            {"kind", "provider_scope", "reference_id", "metadata"}
        ),
        "reasoning_block": frozenset(
            {
                "kind",
                "provider_scope",
                "reference_id",
                "block_type",
                "summary",
                "metadata",
            }
        ),
        "tool_call": frozenset(
            {
                "kind",
                "provider_scope",
                "call_id",
                "batch_id",
                "name",
                "raw_arguments",
                "parsed_arguments",
                "parse_status",
                "parse_error",
                "metadata",
            }
        ),
    }[kind]
    data = _strict_fields(
        data,
        path=path,
        allowed=_PART_FIELDS[kind],
        required=required,
    )
    if kind == "content":
        _validate_content_payload([data["block"]], f"{path}.block_array")
        return
    for field_name in ("provider_scope", "reference_id", "block_type"):
        if field_name in data:
            _strict_string(data[field_name], f"{path}.{field_name}")
    if "attachment_id" in data:
        _strict_string(data["attachment_id"], f"{path}.attachment_id", optional=True)
    if "summary" in data:
        _strict_string(data["summary"], f"{path}.summary", optional=True)
    if kind == "tool_call":
        for field_name in ("call_id", "batch_id", "name", "raw_arguments", "parse_status"):
            _strict_string(data[field_name], f"{path}.{field_name}")
        _strict_string(data["parse_error"], f"{path}.parse_error", optional=True)
        parsed = data["parsed_arguments"]
        if parsed is not None:
            _strict_object(parsed, f"{path}.parsed_arguments")
    _strict_object(data["metadata"], f"{path}.metadata")


def _validate_attachment_payload(value: Any, path: str) -> None:
    data = _strict_fields(
        value,
        path=path,
        allowed=_ATTACHMENT_FIELDS,
        required=_ATTACHMENT_FIELDS,
    )
    for field_name in ("attachment_id", "provider_scope", "api_mode"):
        _strict_string(data[field_name], f"{path}.{field_name}")
    _strict_object(data["metadata"], f"{path}.metadata")


def _validate_item_payload(value: Any, path: str) -> Dict[str, Any]:
    initial = _strict_object(value, path)
    kind = initial.get("kind")
    if not isinstance(kind, str) or kind not in _ITEM_FIELDS:
        raise InvalidExchangeItemError(f"{path}.kind is unsupported")
    data = _strict_fields(
        initial,
        path=path,
        allowed=_ITEM_FIELDS[kind],
        required=_ITEM_FIELDS[kind],
    )
    for field_name in ("item_id", "exchange_id"):
        _strict_string(data[field_name], f"{path}.{field_name}")
    if kind in {"user", "steering"}:
        _validate_content_payload(data["content"], f"{path}.content")
        _strict_object(data["metadata"], f"{path}.metadata")
    elif kind == "assistant":
        if not isinstance(data["parts"], list):
            raise InvalidExchangeItemError(f"{path}.parts must be an array")
        for index, part in enumerate(data["parts"]):
            _validate_part_payload(part, f"{path}.parts[{index}]")
        attachments = data["continuation_attachments"]
        if not isinstance(attachments, list):
            raise InvalidExchangeItemError(
                f"{path}.continuation_attachments must be an array"
            )
        for index, attachment in enumerate(attachments):
            _validate_attachment_payload(
                attachment, f"{path}.continuation_attachments[{index}]"
            )
        _strict_object(data["metadata"], f"{path}.metadata")
    else:
        for field_name in ("provider_scope", "call_id", "batch_id"):
            _strict_string(data[field_name], f"{path}.{field_name}")
        if not isinstance(data["synthetic"], bool):
            raise InvalidExchangeItemError(f"{path}.synthetic must be boolean")
        _strict_string(
            data["closure_reason"], f"{path}.closure_reason", optional=True
        )
        _strict_object(data["result"], f"{path}.result")
    return data


def _validate_persistence_payload(payload: Any) -> Dict[str, Any]:
    data = _strict_fields(
        payload,
        path="exchange_log",
        allowed=_TOP_LEVEL_FIELDS,
        required=_TOP_LEVEL_FIELDS,
    )
    version = data["schema_version"]
    _strict_string(version, "exchange_log.schema_version")
    if version != EXCHANGE_LOG_SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            f"unsupported exchange schema: {version!r}"
        )
    _strict_string(data["log_id"], "exchange_log.log_id")
    for field_name in ("items", "queued_steering"):
        values = data[field_name]
        if not isinstance(values, list):
            raise InvalidExchangeItemError(
                f"exchange_log.{field_name} must be an array"
            )
        for index, item in enumerate(values):
            _validate_item_payload(item, f"exchange_log.{field_name}[{index}]")
    _strict_json(data, "exchange_log")
    return data


def _attachment_from_dict(payload: Any) -> OpaqueContinuationAttachment:
    if not isinstance(payload, Mapping):
        raise InvalidExchangeItemError("continuation attachment must be an object")
    return OpaqueContinuationAttachment(
        attachment_id=str(payload.get("attachment_id") or ""),
        provider_scope=str(payload.get("provider_scope") or ""),
        api_mode=str(payload.get("api_mode") or ""),
        opaque_payload=copy.deepcopy(payload.get("opaque_payload")),
        metadata=dict(payload.get("metadata") or {}),
    )


def _steering_from_dict(payload: Any) -> SteeringItem:
    item = _item_from_dict(payload)
    if not isinstance(item, SteeringItem):
        raise InvalidExchangeItemError(
            "queued_steering may contain only steering items"
        )
    return item


def _item_from_dict(payload: Any) -> ExchangeItem:
    if not isinstance(payload, Mapping):
        raise InvalidExchangeItemError("exchange item must be an object")
    kind = str(payload.get("kind") or "")
    item_id = str(payload.get("item_id") or "")
    exchange_id = str(payload.get("exchange_id") or "")
    metadata = dict(payload.get("metadata") or {})
    if kind == "user":
        return UserItem(
            item_id=item_id,
            exchange_id=exchange_id,
            content=_content_blocks(payload.get("content", [])),
            metadata=metadata,
        )
    if kind == "steering":
        return SteeringItem(
            item_id=item_id,
            exchange_id=exchange_id,
            content=_content_blocks(payload.get("content", [])),
            metadata=metadata,
        )
    if kind == "assistant":
        parts = payload.get("parts")
        attachments = payload.get("continuation_attachments", [])
        if not isinstance(parts, list) or not isinstance(attachments, list):
            raise InvalidExchangeItemError(
                "assistant parts and continuation_attachments must be lists"
            )
        return AssistantItem(
            item_id=item_id,
            exchange_id=exchange_id,
            parts=[_part_from_dict(part) for part in parts],
            continuation_attachments=[
                _attachment_from_dict(attachment) for attachment in attachments
            ],
            metadata=metadata,
        )
    if kind == "tool_result":
        return ToolResultItem(
            item_id=item_id,
            exchange_id=exchange_id,
            identity=CallIdentity(
                provider_scope=str(payload.get("provider_scope") or ""),
                call_id=str(payload.get("call_id") or ""),
            ),
            batch_id=str(payload.get("batch_id") or ""),
            result=ToolResult.from_value(payload["result"]),
            synthetic=payload["synthetic"],
            closure_reason=payload["closure_reason"],
        )
    raise InvalidExchangeItemError(f"unsupported exchange item kind: {kind!r}")


def _legacy_tool_call(
    payload: Mapping[str, Any],
    *,
    message_index: int,
    call_index: int,
    batch_id: str,
    provider_scope: str,
) -> ToolCall:
    function = payload.get("function")
    if not isinstance(function, Mapping):
        raise UnsafeHistoryConversionError(
            "legacy assistant tool call has no function object"
        )
    name = str(function.get("name") or "").strip()
    if not name:
        raise UnsafeHistoryConversionError(
            "legacy assistant tool call has no function name"
        )
    call_id = str(payload.get("id") or "").strip()
    metadata = {
        key: copy.deepcopy(value)
        for key, value in payload.items()
        if key not in {"id", "type", "function"}
    }
    if not call_id:
        call_id = f"legacy_call_{message_index}_{call_index}"
        metadata["call_id_synthesized"] = True
    arguments = function.get("arguments", "{}")
    parse_error: Optional[str] = None
    parsed: Optional[Dict[str, Any]] = None
    if isinstance(arguments, Mapping):
        parsed = dict(arguments)
        raw = json.dumps(parsed, ensure_ascii=False, sort_keys=True)
        status = ArgumentParseStatus.PARSED
        metadata["raw_arguments_synthesized"] = True
    elif isinstance(arguments, str):
        raw = arguments
        try:
            decoded = json.loads(arguments or "{}")
        except json.JSONDecodeError as exc:
            status = ArgumentParseStatus.MALFORMED_RAW
            parse_error = str(exc)
        else:
            if isinstance(decoded, dict):
                parsed = decoded
                status = ArgumentParseStatus.PARSED
            else:
                status = ArgumentParseStatus.PARSED_INVALID
                parse_error = "decoded arguments are not an object"
    else:
        raw = str(arguments)
        status = ArgumentParseStatus.PARSED_INVALID
        parse_error = "legacy arguments are neither a string nor an object"
    explicit_status = payload.get("qitos_parse_status")
    explicit_parsed = payload.get("qitos_parsed_arguments")
    if explicit_status is not None:
        status = ArgumentParseStatus(str(explicit_status))
        parsed = dict(explicit_parsed) if isinstance(explicit_parsed, Mapping) else None
        parse_error = (
            str(payload["qitos_parse_error"])
            if payload.get("qitos_parse_error") is not None
            else None
        )
    return ToolCall(
        identity=CallIdentity(provider_scope=provider_scope, call_id=call_id),
        batch_id=batch_id,
        name=name,
        raw_arguments=raw,
        parsed_arguments=parsed,
        parse_status=status,
        parse_error=parse_error,
        metadata=metadata,
    )


def history_messages_to_exchange_log(
    messages: Iterable[HistoryMessage],
    *,
    provider_scope: str = "legacy:history",
    log_id: Optional[str] = None,
) -> ExchangeLog:
    """Convert the representable `HistoryMessage` subset without changing it."""

    log = ExchangeLog(log_id=log_id or _new_id("legacy_log"))
    active_builder: Optional[ToolBatchBuilder] = None
    for index, message in enumerate(messages):
        if not isinstance(message, HistoryMessage):
            raise UnsafeHistoryConversionError(
                "history adapter accepts HistoryMessage instances only"
            )
        role = str(message.role or "").strip().lower()
        exchange_id = f"legacy_exchange_{int(message.step_id)}"
        item_id = f"legacy_item_{index}"
        metadata = copy.deepcopy(message.metadata)
        metadata["_history_step_id"] = int(message.step_id)
        if role == "user":
            item_type = str(metadata.get("qitos_item_type") or "")
            cls = SteeringItem if item_type == "steering" else UserItem
            log.append(
                cls(
                    item_id=item_id,
                    exchange_id=exchange_id,
                    content=_content_blocks(message.content),
                    metadata=metadata,
                )
            )
            continue
        if role == "assistant":
            parts: List[AssistantPart] = [
                AssistantContent(block)
                for block in _content_blocks(message.content)
                if block.type != "text" or str(block.text or "")
            ]
            batch_id = f"legacy_batch_{index}"
            for call_index, raw_call in enumerate(message.tool_calls):
                if not isinstance(raw_call, Mapping):
                    raise UnsafeHistoryConversionError(
                        "legacy tool call must be an object", item_id=item_id
                    )
                parts.append(
                    _legacy_tool_call(
                        raw_call,
                        message_index=index,
                        call_index=call_index,
                        batch_id=batch_id,
                        provider_scope=provider_scope,
                    )
                )
            if message.tool_calls and message.content not in (None, "", []):
                metadata["legacy_order_synthesized"] = "content_before_tool_calls"
            attachments: List[OpaqueContinuationAttachment] = []
            if message.native_items:
                attachments.append(
                    OpaqueContinuationAttachment(
                        attachment_id=f"legacy_native_{index}",
                        provider_scope=provider_scope,
                        api_mode=str(metadata.get("api_mode") or "legacy"),
                        opaque_payload=copy.deepcopy(message.native_items),
                        metadata={"source": "HistoryMessage.native_items"},
                    )
                )
            builder = log.append(
                AssistantItem(
                    item_id=item_id,
                    exchange_id=exchange_id,
                    parts=parts,
                    continuation_attachments=attachments,
                    metadata=metadata,
                )
            )
            active_builder = builder
            continue
        if role == "tool":
            if active_builder is None:
                raise UnknownCallIdError(
                    "legacy tool result has no open assistant batch",
                    item_id=item_id,
                    call_id=message.tool_call_id,
                )
            call_id = str(message.tool_call_id or "").strip()
            if not call_id:
                raise UnsafeHistoryConversionError(
                    "legacy tool result has no tool_call_id", item_id=item_id
                )
            legacy_status = str(
                metadata.get("qitos_result_status") or "success"
            )
            status_map = {
                "succeeded": "success",
                "failed": "error",
                "permission_blocked": "skipped",
                "missing_worker": "error",
            }
            status = status_map.get(legacy_status, legacy_status)
            if status not in {
                "success",
                "error",
                "skipped",
                "timed_out",
                "cancelled",
            }:
                raise UnsafeHistoryConversionError(
                    f"unsupported legacy tool result status: {legacy_status!r}",
                    item_id=item_id,
                )
            synthetic = bool(metadata.get("qitos_synthetic_closure", False))
            closure_reason = (
                str(
                    metadata.get("qitos_closure_reason")
                    or metadata.get("qitos_provenance_reason")
                )
                if (
                    metadata.get("qitos_closure_reason") is not None
                    or metadata.get("qitos_provenance_reason") is not None
                )
                else None
            )
            error_kind = None
            error_code = None
            error = None
            if status != "success":
                error_kind = "policy" if status == "skipped" else "execution"
                error_code = (
                    "missing_worker"
                    if legacy_status == "missing_worker"
                    else str(metadata.get("qitos_error_code") or status)
                )
                error = str(message.content or error_code)
            result = ToolResultItem(
                item_id=item_id,
                exchange_id=active_builder._exchange_id(),
                identity=CallIdentity(provider_scope, call_id),
                batch_id=active_builder.batch_id,
                result=ToolResult(
                    status=status,  # type: ignore[arg-type]
                    output=_content_payload(_content_blocks(message.content)),
                    error=error,
                    error_kind=error_kind,  # type: ignore[arg-type]
                    error_code=error_code,
                    action_id=call_id,
                    metadata=metadata,
                    provenance={
                        "source": str(
                            metadata.get("qitos_provenance_source")
                            or "HistoryMessage"
                        )
                    },
                ),
                synthetic=synthetic,
                closure_reason=closure_reason,
            )
            closed = active_builder.record_result(result)
            if closed:
                active_builder = None
            continue
        raise UnsafeHistoryConversionError(
            f"unsupported HistoryMessage role: {message.role!r}", item_id=item_id
        )
    log.assert_ready_for_model_transaction()
    return log


def exchange_log_to_history_messages(log: ExchangeLog) -> List[HistoryMessage]:
    """Strictly project an ExchangeLog into the legacy message shape."""

    log.assert_ready_for_model_transaction()
    messages: List[HistoryMessage] = []
    projection_items: List[ExchangeItem] = []
    projected_batches: set[str] = set()
    for item in log.items:
        if isinstance(item, ToolResultItem) and item.batch_id in projected_batches:
            continue
        projection_items.append(item)
        if isinstance(item, AssistantItem) and item.batch_id is not None:
            projection_items.extend(
                log.results_for_batch_in_declaration_order(item.batch_id)
            )
            projected_batches.add(item.batch_id)

    for index, item in enumerate(projection_items):
        metadata = (
            copy.deepcopy(item.result.metadata)
            if isinstance(item, ToolResultItem)
            else copy.deepcopy(item.metadata)
        )
        step_id = int(metadata.pop("_history_step_id", index))
        if isinstance(item, UserItem):
            messages.append(
                HistoryMessage(
                    role="user",
                    step_id=step_id,
                    content=_content_payload(item.content),
                    metadata=metadata,
                )
            )
            continue
        if isinstance(item, SteeringItem):
            metadata["qitos_item_type"] = "steering"
            messages.append(
                HistoryMessage(
                    role="user",
                    step_id=step_id,
                    content=_content_payload(item.content),
                    metadata=metadata,
                )
            )
            continue
        if isinstance(item, AssistantItem):
            seen_call = False
            blocks: List[ContentBlock] = []
            calls: List[Dict[str, Any]] = []
            for part in item.parts:
                if isinstance(part, (ReasoningReference, ReasoningBlock)):
                    raise UnsupportedReasoningReplayError(
                        "HistoryMessage cannot safely represent reasoning parts",
                        item_id=item.item_id,
                    )
                if isinstance(part, AssistantContent):
                    if seen_call:
                        raise UnsafeHistoryConversionError(
                            "HistoryMessage cannot preserve content after a tool call",
                            item_id=item.item_id,
                        )
                    blocks.append(part.block)
                    continue
                seen_call = True
                calls.append(
                    {
                        "id": part.identity.call_id,
                        "type": "function",
                        "function": {
                            "name": part.name,
                            "arguments": part.raw_arguments,
                        },
                        "qitos_parse_status": part.parse_status.value,
                        "qitos_parsed_arguments": copy.deepcopy(
                            part.parsed_arguments
                        ),
                        "qitos_parse_error": part.parse_error,
                    }
                )
            native_items: List[Dict[str, Any]] = []
            for attachment in item.continuation_attachments:
                payload = attachment.opaque_payload
                if not isinstance(payload, list) or not all(
                    isinstance(native, dict) for native in payload
                ):
                    raise UnsafeHistoryConversionError(
                        "HistoryMessage.native_items cannot preserve this opaque payload",
                        item_id=item.item_id,
                    )
                native_items.extend(copy.deepcopy(payload))
            content = _content_payload(blocks) if blocks else None
            messages.append(
                HistoryMessage(
                    role="assistant",
                    step_id=step_id,
                    content=content,
                    tool_calls=calls,
                    metadata=metadata,
                    native_items=native_items,
                )
            )
            continue
        model_view = item.result.to_model_dict()
        provenance_source = item.result.provenance.get("source")
        metadata.update(
            {
                "qitos_result_status": item.result.status,
                "qitos_error_code": item.result.error_code,
                "qitos_synthetic_closure": item.synthetic,
                "qitos_closure_reason": item.closure_reason,
                "qitos_provenance_source": provenance_source,
            }
        )
        content = model_view["model_output"] or model_view["error"] or ""
        messages.append(
            HistoryMessage(
                role="tool",
                step_id=step_id,
                content=content,
                tool_call_id=item.identity.call_id,
                metadata=metadata,
            )
        )
    return messages


__all__ = [
    "EXCHANGE_LOG_SCHEMA_VERSION",
    "CONTINUATION_REDACTED_DIAGNOSTIC_VERSION",
    "ArgumentParseStatus",
    "ConversationValidationError",
    "UnsupportedSchemaVersionError",
    "InvalidExchangeItemError",
    "DuplicateItemIdError",
    "DuplicateCallIdError",
    "UnknownCallIdError",
    "DuplicateToolResultError",
    "ToolBatchMismatchError",
    "IncompleteToolBatchError",
    "UnsafeHistoryConversionError",
    "UnsupportedReasoningReplayError",
    "CallIdentity",
    "OpaqueContinuationAttachment",
    "AssistantContent",
    "ReasoningReference",
    "ReasoningBlock",
    "ToolCall",
    "UserItem",
    "SteeringItem",
    "AssistantItem",
    "ToolResultItem",
    "ExchangeItem",
    "ExchangeLog",
    "ToolBatchBuilder",
    "history_messages_to_exchange_log",
    "exchange_log_to_history_messages",
]
