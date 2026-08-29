"""Provider-neutral persistent conversation transaction contracts.

This module owns the first layer of the v4 model I/O contract.  It deliberately
does not know how an Engine selects a request view or how a provider encodes it.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Union
from uuid import uuid4

from .history import HistoryMessage
from .multimodal import ContentBlock, normalize_content_block


EXCHANGE_LOG_SCHEMA_VERSION = "qitos.exchange_log.v1"


class ArgumentParseStatus(str, Enum):
    """The boundary reached while decoding raw tool-call arguments."""

    NOT_ATTEMPTED = "not_attempted"
    PARSED = "parsed"
    MALFORMED_RAW = "malformed_raw"
    PARSED_INVALID = "parsed_invalid"


class ToolResultStatus(str, Enum):
    """Terminal states that close one declared tool-call slot."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PERMISSION_BLOCKED = "permission_blocked"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    MISSING_WORKER = "missing_worker"


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
    normalized = normalize_content_block(value)
    return ContentBlock(
        type=str(normalized.get("type") or "text"),
        text=normalized.get("text"),
        url=normalized.get("url"),
        data=normalized.get("data"),
        path=normalized.get("path"),
        mime_type=normalized.get("mime_type"),
        detail=normalized.get("detail"),
        metadata=dict(normalized.get("metadata") or {}),
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
    return [block.to_dict() for block in blocks]


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

    def to_safe_dict(self) -> Dict[str, Any]:
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


AssistantPart = Union[AssistantContent, ReasoningReference, ToolCall]


@dataclass(frozen=True)
class ClosureProvenance:
    """Why and by whom a result slot was closed."""

    source: str
    synthetic: bool = False
    reason: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def validate(self, status: ToolResultStatus) -> None:
        _require_id(self.source, "closure provenance source")
        if self.synthetic and not self.reason:
            raise InvalidExchangeItemError(
                "synthetic closure requires provenance reason"
            )
        if status is ToolResultStatus.MISSING_WORKER and not self.synthetic:
            raise InvalidExchangeItemError(
                "missing_worker must be an explicit synthetic closure"
            )


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
            if isinstance(part, ReasoningReference) and part.attachment_id:
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
    item_id: str
    exchange_id: str
    identity: CallIdentity
    batch_id: str
    status: ToolResultStatus
    content: List[ContentBlock]
    provenance: ClosureProvenance
    metadata: Dict[str, Any] = field(default_factory=dict)
    kind: str = field(default="tool_result", init=False)

    def validate(self) -> None:
        _require_id(self.item_id, "item_id", item_id=self.item_id)
        _require_id(self.exchange_id, "exchange_id", item_id=self.item_id)
        self.identity.validate()
        _require_id(self.batch_id, "batch_id", item_id=self.item_id)
        _validate_content(self.content, item_id=self.item_id)
        self.provenance.validate(self.status)


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
        self._items = list(items or [])
        self._queued_steering = list(queued_steering or [])
        self.validate()

    @property
    def items(self) -> tuple[ExchangeItem, ...]:
        """An immutable view of committed persistent items."""
        return tuple(self._items)

    @property
    def queued_steering(self) -> tuple[SteeringItem, ...]:
        """An immutable view of steering waiting for the open batch boundary."""
        return tuple(self._queued_steering)

    def append(self, item: ExchangeItem) -> Optional["ToolBatchBuilder"]:
        self.validate()
        open_batch = self.open_batch_id()
        if open_batch is not None:
            if isinstance(item, SteeringItem):
                self._ensure_new_item_id(item.item_id)
                self._queued_steering.append(item)
                self.validate()
                return None
            raise IncompleteToolBatchError(
                "an incomplete tool batch blocks the next persistent item",
                item_id=item.item_id,
                batch_id=open_batch,
            )
        self._ensure_new_item_id(item.item_id)
        item.validate()
        if isinstance(item, ToolResultItem):
            raise InvalidExchangeItemError(
                "tool results must be committed by ToolBatchBuilder",
                item_id=item.item_id,
                batch_id=item.batch_id,
                call_id=item.identity.call_id,
            )
        self._items.append(item)
        try:
            self.validate()
        except Exception:
            self._items.pop()
            raise
        if isinstance(item, AssistantItem) and item.tool_calls():
            return ToolBatchBuilder(self, str(item.batch_id))
        return None

    def queue_steering(self, item: SteeringItem) -> None:
        if self.open_batch_id() is None:
            self.append(item)
            return
        self._ensure_new_item_id(item.item_id)
        item.validate()
        self._queued_steering.append(item)
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

        for position, item in enumerate(self.items):
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

        for queued in self.queued_steering:
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
            expected = [call.identity.key() for call in calls]
            actual = [result.identity.key() for result in batch_results]
            if actual != expected:
                raise ToolBatchMismatchError(
                    "persistent tool results must follow declaration order",
                    batch_id=batch_id,
                )
            last_result_position = max(
                index
                for index, item in enumerate(self.items)
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
            for item in self.items[open_position + 1 :]:
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
        known = {item.item_id for item in self.items}
        known.update(item.item_id for item in self.queued_steering)
        if item_id in known:
            raise DuplicateItemIdError(
                f"duplicate item ID: {item_id}", item_id=item_id
            )

    def declared_calls(self, batch_id: str) -> List[ToolCall]:
        for item in self.items:
            if isinstance(item, AssistantItem) and item.batch_id == batch_id:
                return list(item.tool_calls())
        raise ToolBatchMismatchError(
            f"unknown tool batch: {batch_id!r}", batch_id=batch_id
        )

    def results_for_batch(self, batch_id: str) -> List[ToolResultItem]:
        return [
            item
            for item in self.items
            if isinstance(item, ToolResultItem) and item.batch_id == batch_id
        ]

    def open_batch_id(self) -> Optional[str]:
        declarations: List[tuple[str, int]] = []
        counts: Dict[str, int] = {}
        for item in self.items:
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

    def to_persistence_dict(self) -> Dict[str, Any]:
        self.validate()
        payload = {
            "schema_version": self.schema_version,
            "log_id": self.log_id,
            "items": [_item_to_dict(item, safe=False) for item in self.items],
            "queued_steering": [
                _item_to_dict(item, safe=False) for item in self.queued_steering
            ],
        }
        try:
            json.dumps(payload, ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise InvalidExchangeItemError(
                "persistence payload must be JSON-serializable"
            ) from exc
        return payload

    def to_safe_dict(self) -> Dict[str, Any]:
        self.validate()
        return {
            "schema_version": self.schema_version,
            "log_id": self.log_id,
            "items": [_item_to_dict(item, safe=True) for item in self.items],
            "queued_steering": [
                _item_to_dict(item, safe=True) for item in self.queued_steering
            ],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExchangeLog":
        version = str(payload.get("schema_version") or "")
        if version != EXCHANGE_LOG_SCHEMA_VERSION:
            raise UnsupportedSchemaVersionError(
                f"unsupported exchange schema: {version!r}"
            )
        items_payload = payload.get("items")
        queued_payload = payload.get("queued_steering", [])
        if not isinstance(items_payload, list) or not isinstance(queued_payload, list):
            raise InvalidExchangeItemError(
                "items and queued_steering must be lists"
            )
        log = cls(
            log_id=str(payload.get("log_id") or ""),
            items=[_item_from_dict(item) for item in items_payload],
            queued_steering=[
                _steering_from_dict(item) for item in queued_payload
            ],
            schema_version=version,
        )
        log.validate()
        return log


class ToolBatchBuilder:
    """Buffer execution completion and atomically commit results in call order."""

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
        result.validate()
        if result.batch_id != self.batch_id:
            raise ToolBatchMismatchError(
                "result batch does not match the active builder",
                item_id=result.item_id,
                batch_id=result.batch_id,
                call_id=result.identity.call_id,
            )
        if result.exchange_id != self._exchange_id():
            raise ToolBatchMismatchError(
                "result exchange_id does not match the assistant declaration",
                item_id=result.item_id,
                batch_id=result.batch_id,
                call_id=result.identity.call_id,
            )
        declared = {call.identity.key() for call in self.calls}
        key = result.identity.key()
        if key not in declared:
            raise UnknownCallIdError(
                "result references an undeclared call",
                item_id=result.item_id,
                batch_id=self.batch_id,
                call_id=result.identity.call_id,
            )
        if key in self._results:
            raise DuplicateToolResultError(
                "a declared call cannot receive two results",
                item_id=result.item_id,
                batch_id=self.batch_id,
                call_id=result.identity.call_id,
            )
        self.exchange_log._ensure_new_item_id(result.item_id)
        if result.item_id in {item.item_id for item in self._results.values()}:
            raise DuplicateItemIdError(
                f"duplicate item ID: {result.item_id}", item_id=result.item_id
            )
        self._results[key] = result
        if self.missing_calls:
            return False
        self._commit()
        return True

    def close_missing(
        self,
        *,
        status: ToolResultStatus,
        reason: str,
        source: str = "qitos.tool_batch_builder",
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        if status is ToolResultStatus.SUCCEEDED:
            raise InvalidExchangeItemError(
                "synthetic closure cannot report succeeded", batch_id=self.batch_id
            )
        for call in list(self.missing_calls):
            result = ToolResultItem(
                item_id=_new_id("tool_result"),
                exchange_id=self._exchange_id(),
                identity=call.identity,
                batch_id=self.batch_id,
                status=status,
                content=[
                    ContentBlock(
                        type="text",
                        text=message
                        or f"Tool call closed synthetically: {reason}",
                    )
                ],
                provenance=ClosureProvenance(
                    source=source,
                    synthetic=True,
                    reason=reason,
                    details=dict(details or {}),
                ),
            )
            self.record_result(result)

    def _exchange_id(self) -> str:
        for item in self.exchange_log.items:
            if isinstance(item, AssistantItem) and item.batch_id == self.batch_id:
                return item.exchange_id
        raise ToolBatchMismatchError(
            "batch assistant declaration disappeared", batch_id=self.batch_id
        )

    def _commit(self) -> None:
        if self.exchange_log.open_batch_id() != self.batch_id:
            raise ToolBatchMismatchError(
                "batch is no longer the active open batch", batch_id=self.batch_id
            )
        ordered = [self._results[call.identity.key()] for call in self.calls]
        original_items = list(self.exchange_log.items)
        original_steering = list(self.exchange_log.queued_steering)
        self.exchange_log._items.extend(ordered)
        self.exchange_log._items.extend(self.exchange_log.queued_steering)
        self.exchange_log._queued_steering = []
        try:
            self.exchange_log.validate()
        except Exception:
            self.exchange_log._items = original_items
            self.exchange_log._queued_steering = original_steering
            raise


def _part_to_dict(part: AssistantPart) -> Dict[str, Any]:
    if isinstance(part, AssistantContent):
        return {"kind": part.kind, "block": part.block.to_dict()}
    if isinstance(part, ReasoningReference):
        return {
            "kind": part.kind,
            "provider_scope": part.provider_scope,
            "reference_id": part.reference_id,
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


def _item_to_dict(item: ExchangeItem, *, safe: bool) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "kind": item.kind,
        "item_id": item.item_id,
        "exchange_id": item.exchange_id,
        "metadata": copy.deepcopy(item.metadata),
    }
    if isinstance(item, (UserItem, SteeringItem)):
        base["content"] = [block.to_dict() for block in item.content]
    elif isinstance(item, AssistantItem):
        base["parts"] = [_part_to_dict(part) for part in item.parts]
        base["continuation_attachments"] = [
            attachment.to_safe_dict()
            if safe
            else attachment.to_persistence_dict()
            for attachment in item.continuation_attachments
        ]
    else:
        base.update(
            {
                "provider_scope": item.identity.provider_scope,
                "call_id": item.identity.call_id,
                "batch_id": item.batch_id,
                "status": item.status.value,
                "content": [block.to_dict() for block in item.content],
                "provenance": {
                    "source": item.provenance.source,
                    "synthetic": item.provenance.synthetic,
                    "reason": item.provenance.reason,
                    "details": copy.deepcopy(item.provenance.details),
                },
            }
        )
    return base


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
        provenance = payload.get("provenance")
        if not isinstance(provenance, Mapping):
            raise InvalidExchangeItemError("tool result provenance must be an object")
        return ToolResultItem(
            item_id=item_id,
            exchange_id=exchange_id,
            identity=CallIdentity(
                provider_scope=str(payload.get("provider_scope") or ""),
                call_id=str(payload.get("call_id") or ""),
            ),
            batch_id=str(payload.get("batch_id") or ""),
            status=_enum_value(
                ToolResultStatus,
                payload.get("status") or "",
                "tool result status",
            ),
            content=_content_blocks(payload.get("content", [])),
            provenance=ClosureProvenance(
                source=str(provenance.get("source") or ""),
                synthetic=bool(provenance.get("synthetic", False)),
                reason=(
                    str(provenance["reason"])
                    if provenance.get("reason") is not None
                    else None
                ),
                details=dict(provenance.get("details") or {}),
            ),
            metadata=metadata,
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
            status = _enum_value(
                ToolResultStatus,
                metadata.get("qitos_result_status") or "succeeded",
                "tool result status",
            )
            synthetic = bool(metadata.get("qitos_synthetic_closure", False))
            result = ToolResultItem(
                item_id=item_id,
                exchange_id=active_builder._exchange_id(),
                identity=CallIdentity(provider_scope, call_id),
                batch_id=active_builder.batch_id,
                status=status,
                content=_content_blocks(message.content),
                provenance=ClosureProvenance(
                    source=str(
                        metadata.get("qitos_provenance_source")
                        or "HistoryMessage"
                    ),
                    synthetic=synthetic,
                    reason=(
                        str(metadata["qitos_provenance_reason"])
                        if metadata.get("qitos_provenance_reason") is not None
                        else None
                    ),
                ),
                metadata=metadata,
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
    for index, item in enumerate(log.items):
        metadata = copy.deepcopy(item.metadata)
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
                if isinstance(part, ReasoningReference):
                    raise UnsupportedReasoningReplayError(
                        "HistoryMessage cannot safely represent reasoning references",
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
        metadata.update(
            {
                "qitos_result_status": item.status.value,
                "qitos_synthetic_closure": item.provenance.synthetic,
                "qitos_provenance_source": item.provenance.source,
                "qitos_provenance_reason": item.provenance.reason,
            }
        )
        messages.append(
            HistoryMessage(
                role="tool",
                step_id=step_id,
                content=_content_payload(item.content),
                tool_call_id=item.identity.call_id,
                metadata=metadata,
            )
        )
    return messages


__all__ = [
    "EXCHANGE_LOG_SCHEMA_VERSION",
    "ArgumentParseStatus",
    "ToolResultStatus",
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
    "ToolCall",
    "ClosureProvenance",
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
