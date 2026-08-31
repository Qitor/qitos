"""Stable event-sink seam for candidate trajectory records."""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Dict, Iterable, List, Optional, Protocol, Tuple, runtime_checkable

from .privacy import project_data
from .trajectory import LossReport, PrivacyView, TrajectoryRecord, records_to_tuple


class FailurePolicy(str, Enum):
    """How a dispatcher treats a sink operation failure."""

    REQUIRED = "required"
    OPTIONAL = "optional"


class BackpressurePolicy(str, Enum):
    """Policy declared by a sink when it cannot accept more records."""

    BLOCK = "block"
    DROP_NEWEST = "drop_newest"
    FAIL = "fail"


class DurabilityStatus(str, Enum):
    """Outcome of a sink/store operation."""

    ACCEPTED = "accepted"
    PERSISTED = "persisted"
    DROPPED = "dropped"
    FAILED = "failed"
    CONFLICTED = "conflicted"


@dataclass(frozen=True)
class DurabilityReceipt:
    """Optional receipt returned by sinks and stores."""

    status: DurabilityStatus
    accepted_count: int = 0
    persisted_count: int = 0
    dropped_count: int = 0
    operation_id: Optional[str] = None
    detail_code: Optional[str] = None

    @property
    def successful(self) -> bool:
        return self.status in {
            DurabilityStatus.ACCEPTED,
            DurabilityStatus.PERSISTED,
        }

    def to_dict(self) -> Dict[str, object]:
        return {
            "status": self.status.value,
            "accepted_count": self.accepted_count,
            "persisted_count": self.persisted_count,
            "dropped_count": self.dropped_count,
            "operation_id": self.operation_id,
            "detail_code": self.detail_code,
        }


@dataclass(frozen=True)
class SinkCapabilities:
    """Machine-readable behavior declaration for an event sink."""

    sink_id: str
    supported_views: Tuple[PrivacyView, ...] = (
        PrivacyView.RAW_PRIVATE,
        PrivacyView.REDACTED_PUBLIC,
        PrivacyView.SAFE_DIAGNOSTIC,
    )
    durability_receipts: bool = False
    atomic_batch: bool = False
    backpressure: BackpressurePolicy = BackpressurePolicy.FAIL
    max_record_bytes: Optional[int] = None


@runtime_checkable
class EventSink(Protocol):
    """Minimal third-party sink protocol; no Engine private state is exposed."""

    @property
    def capabilities(self) -> SinkCapabilities:
        ...

    def receive(
        self, record: TrajectoryRecord
    ) -> Optional[DurabilityReceipt]:
        ...

    def flush(self) -> Optional[DurabilityReceipt]:
        ...

    def close(self) -> Optional[DurabilityReceipt]:
        ...


class EventSinkError(RuntimeError):
    """Base class for explicit sink failures."""


class SinkBackpressureError(EventSinkError):
    """A sink could not accept a record under its declared policy."""


@dataclass(frozen=True)
class SinkFailure:
    sink_id: str
    operation: str
    code: str
    required: bool

    def to_dict(self) -> Dict[str, object]:
        return {
            "sink_id": self.sink_id,
            "operation": self.operation,
            "code": self.code,
            "required": self.required,
        }


@dataclass(frozen=True)
class SinkDispatchReport:
    """Explicit report; optional failure never disappears into logging."""

    receipts: Tuple[DurabilityReceipt, ...] = ()
    failures: Tuple[SinkFailure, ...] = ()
    loss: LossReport = field(default_factory=LossReport)

    @property
    def successful(self) -> bool:
        return not self.failures and all(
            receipt.successful for receipt in self.receipts
        )

    def assert_success(self) -> None:
        if self.failures:
            raise EventSinkError(
                "event sink dispatch contains explicit failures: "
                + ",".join(failure.code for failure in self.failures)
            )


@dataclass(frozen=True)
class SinkRegistration:
    sink: EventSink
    failure_policy: FailurePolicy = FailurePolicy.REQUIRED
    view: PrivacyView = PrivacyView.REDACTED_PUBLIC

    def __post_init__(self) -> None:
        if self.view not in self.sink.capabilities.supported_views:
            raise ValueError(
                f"sink {self.sink.capabilities.sink_id!r} does not support "
                f"view {self.view.value!r}"
            )


def project_record(
    record: TrajectoryRecord, view: PrivacyView
) -> TrajectoryRecord:
    """Create a derived safe projection without mutating canonical raw data."""
    if view == PrivacyView.RAW_PRIVATE:
        return TrajectoryRecord.from_dict(record.to_dict())
    projection = project_data(record.payload, view=view)
    updated = replace(
        record,
        payload=copy.deepcopy(dict(projection.data or {})),
        privacy_view=view,
        loss=record.loss.merged(projection.loss),
        digest="",
    )
    return replace(updated, digest=updated.compute_digest())


class EventSinkDispatcher:
    """Synchronous fan-out with explicit required/optional failure behavior."""

    def __init__(
        self, registrations: Optional[Iterable[SinkRegistration]] = None
    ) -> None:
        self._registrations = list(registrations or [])
        self._closed = False

    def add_sink(
        self,
        sink: EventSink,
        *,
        failure_policy: FailurePolicy = FailurePolicy.REQUIRED,
        view: PrivacyView = PrivacyView.REDACTED_PUBLIC,
    ) -> None:
        if self._closed:
            raise EventSinkError("event sink dispatcher is closed")
        self._registrations.append(
            SinkRegistration(
                sink=sink,
                failure_policy=failure_policy,
                view=view,
            )
        )

    @property
    def registrations(self) -> Tuple[SinkRegistration, ...]:
        return tuple(self._registrations)

    def receive(self, record: TrajectoryRecord) -> SinkDispatchReport:
        if self._closed:
            raise EventSinkError("event sink dispatcher is closed")
        return self._dispatch("receive", record)

    def flush(self) -> SinkDispatchReport:
        if self._closed:
            raise EventSinkError("event sink dispatcher is closed")
        return self._dispatch("flush")

    def close(self) -> SinkDispatchReport:
        if self._closed:
            return SinkDispatchReport()
        report = self._dispatch("close")
        self._closed = True
        return report

    def _dispatch(
        self,
        operation: str,
        record: Optional[TrajectoryRecord] = None,
    ) -> SinkDispatchReport:
        receipts: List[DurabilityReceipt] = []
        failures: List[SinkFailure] = []
        losses: List[LossReport] = []
        for registration in self._registrations:
            sink = registration.sink
            try:
                if operation == "receive":
                    if record is None:
                        raise EventSinkError("receive requires a record")
                    projected = project_record(record, registration.view)
                    losses.append(projected.loss)
                    receipt = sink.receive(projected)
                elif operation == "flush":
                    receipt = sink.flush()
                elif operation == "close":
                    receipt = sink.close()
                else:
                    raise EventSinkError(f"unsupported sink operation: {operation}")
                if receipt is not None:
                    receipts.append(receipt)
                    if not receipt.successful:
                        raise EventSinkError(
                            receipt.detail_code or f"sink_{receipt.status.value}"
                        )
            except Exception as exc:
                failure = SinkFailure(
                    sink_id=sink.capabilities.sink_id,
                    operation=operation,
                    code=type(exc).__name__,
                    required=(registration.failure_policy == FailurePolicy.REQUIRED),
                )
                failures.append(failure)
                if registration.failure_policy == FailurePolicy.REQUIRED:
                    raise EventSinkError(
                        f"required sink {failure.sink_id!r} failed during "
                        f"{operation}: {failure.code}"
                    ) from exc
        merged_loss = LossReport(policy_id="qitos.loss/none")
        if losses:
            merged_loss = losses[0].merged(*losses[1:])
        return SinkDispatchReport(
            receipts=tuple(receipts),
            failures=tuple(failures),
            loss=merged_loss,
        )


class InMemoryEventSink:
    """Lightweight reference sink with isolated reads and bounded capacity."""

    def __init__(
        self,
        *,
        sink_id: str = "qitos.in_memory_event_sink",
        max_records: Optional[int] = None,
        backpressure: BackpressurePolicy = BackpressurePolicy.FAIL,
    ) -> None:
        self._capabilities = SinkCapabilities(
            sink_id=sink_id,
            durability_receipts=True,
            atomic_batch=False,
            backpressure=backpressure,
        )
        self._max_records = max_records
        self._records: List[TrajectoryRecord] = []
        self._closed = False
        self._lock = threading.RLock()

    @property
    def capabilities(self) -> SinkCapabilities:
        return self._capabilities

    @property
    def records(self) -> Tuple[TrajectoryRecord, ...]:
        with self._lock:
            return records_to_tuple(self._records)

    def receive(self, record: TrajectoryRecord) -> DurabilityReceipt:
        with self._lock:
            if self._closed:
                raise EventSinkError("event sink is closed")
            if not record.validate_integrity():
                raise EventSinkError("record_integrity_mismatch")
            if (
                self._max_records is not None
                and len(self._records) >= self._max_records
            ):
                if self.capabilities.backpressure == BackpressurePolicy.DROP_NEWEST:
                    return DurabilityReceipt(
                        status=DurabilityStatus.DROPPED,
                        dropped_count=1,
                        detail_code="sink_capacity_exhausted",
                    )
                raise SinkBackpressureError("sink_capacity_exhausted")
            self._records.append(TrajectoryRecord.from_dict(record.to_dict()))
            return DurabilityReceipt(
                status=DurabilityStatus.ACCEPTED,
                accepted_count=1,
            )

    def flush(self) -> DurabilityReceipt:
        with self._lock:
            if self._closed:
                raise EventSinkError("event sink is closed")
            return DurabilityReceipt(
                status=DurabilityStatus.PERSISTED,
                accepted_count=len(self._records),
                persisted_count=len(self._records),
            )

    def close(self) -> DurabilityReceipt:
        with self._lock:
            if self._closed:
                return DurabilityReceipt(status=DurabilityStatus.PERSISTED)
            self._closed = True
            return DurabilityReceipt(
                status=DurabilityStatus.PERSISTED,
                accepted_count=len(self._records),
                persisted_count=len(self._records),
            )


class TrajectoryStoreEventSink:
    """Reference adapter from the event-sink seam to a trajectory store."""

    def __init__(self, store: object, *, sink_id: str = "qitos.store_sink") -> None:
        self._store = store
        self._closed = False
        self._capabilities = SinkCapabilities(
            sink_id=sink_id,
            durability_receipts=True,
            atomic_batch=True,
            backpressure=BackpressurePolicy.BLOCK,
        )

    @property
    def capabilities(self) -> SinkCapabilities:
        return self._capabilities

    def receive(self, record: TrajectoryRecord) -> DurabilityReceipt:
        if self._closed:
            raise EventSinkError("event sink is closed")
        append = getattr(self._store, "append", None)
        if not callable(append):
            raise EventSinkError("store_missing_append")
        receipt = append(record)
        if not isinstance(receipt, DurabilityReceipt):
            raise EventSinkError("store_invalid_receipt")
        return receipt

    def flush(self) -> DurabilityReceipt:
        if self._closed:
            raise EventSinkError("event sink is closed")
        flush = getattr(self._store, "flush", None)
        if callable(flush):
            receipt = flush()
            if isinstance(receipt, DurabilityReceipt):
                return receipt
        return DurabilityReceipt(status=DurabilityStatus.PERSISTED)

    def close(self) -> DurabilityReceipt:
        if self._closed:
            return DurabilityReceipt(status=DurabilityStatus.PERSISTED)
        receipt = self.flush()
        self._closed = True
        return receipt


__all__ = [
    "BackpressurePolicy",
    "DurabilityReceipt",
    "DurabilityStatus",
    "EventSink",
    "EventSinkDispatcher",
    "EventSinkError",
    "FailurePolicy",
    "InMemoryEventSink",
    "SinkBackpressureError",
    "SinkCapabilities",
    "SinkDispatchReport",
    "SinkFailure",
    "SinkRegistration",
    "TrajectoryStoreEventSink",
    "project_record",
]
