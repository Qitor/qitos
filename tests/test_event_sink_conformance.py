from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Callable

import pytest

from qitos.tracing.sinks import (
    EventSink,
    EventSinkDispatcher,
    FailurePolicy,
    InMemoryEventSink,
    TrajectoryStoreEventSink,
)
from qitos.tracing.sinks import (
    BackpressurePolicy,
    DurabilityStatus,
    EventSinkError,
    SinkCapabilities,
)
from qitos.tracing.store import JsonTrajectoryStore
from qitos.tracing.trajectory import PrivacyView, RecordKind, TrajectoryRecord


ROOT = Path(__file__).resolve().parents[1]


def _third_party_module() -> Any:
    path = ROOT / "tests" / "fixtures" / "s2" / "lane_d" / "third_party.py"
    spec = importlib.util.spec_from_file_location("lane_d_third_party_sink", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "factory",
    [
        InMemoryEventSink,
        lambda: _third_party_module().ThirdPartySink(),
    ],
    ids=["reference", "third-party-style"],
)
def test_event_sink_conformance(factory: Callable[[], Any]) -> None:
    sink = factory()
    assert isinstance(sink, EventSink)
    assert sink.capabilities.sink_id
    record = TrajectoryRecord.create(
        RecordKind.MODEL_REQUEST,
        run_id="run-1",
        session_id="session-1",
        payload={
            "messages": ["hello"],
            "authorization": "Bearer value-that-must-not-pass",
            "artifact_path": "/Users/example/private.txt",
        },
    )
    dispatcher = EventSinkDispatcher()
    dispatcher.add_sink(sink, view=PrivacyView.REDACTED_PUBLIC)

    report = dispatcher.receive(record)
    assert report.successful
    assert report.receipts[0].status == DurabilityStatus.ACCEPTED
    assert record.payload["authorization"].startswith("Bearer")

    stored = sink.records if isinstance(sink, InMemoryEventSink) else tuple(sink.items)
    assert len(stored) == 1
    rendered = str(stored[0].payload)
    assert "value-that-must-not-pass" not in rendered
    assert "/Users/" not in rendered
    assert stored[0].privacy_view == PrivacyView.REDACTED_PUBLIC
    assert not stored[0].loss.is_lossless

    flush = dispatcher.flush()
    assert flush.successful
    closed = dispatcher.close()
    assert closed.successful


class _FailingSink:
    @property
    def capabilities(self) -> SinkCapabilities:
        return SinkCapabilities(sink_id="third_party.failing")

    def receive(self, record: TrajectoryRecord) -> None:
        raise RuntimeError("backend unavailable")

    def flush(self) -> None:
        raise RuntimeError("backend unavailable")

    def close(self) -> None:
        raise RuntimeError("backend unavailable")


def test_required_sink_failure_is_not_silent() -> None:
    dispatcher = EventSinkDispatcher()
    dispatcher.add_sink(_FailingSink(), failure_policy=FailurePolicy.REQUIRED)
    with pytest.raises(EventSinkError, match="required sink"):
        dispatcher.receive(TrajectoryRecord.create(RecordKind.RUN, run_id="r"))


def test_optional_sink_failure_is_explicit_and_not_success() -> None:
    dispatcher = EventSinkDispatcher()
    dispatcher.add_sink(_FailingSink(), failure_policy=FailurePolicy.OPTIONAL)
    report = dispatcher.receive(
        TrajectoryRecord.create(RecordKind.RUN, run_id="r")
    )
    assert not report.successful
    assert report.failures[0].required is False
    assert report.failures[0].code == "RuntimeError"
    with pytest.raises(EventSinkError):
        report.assert_success()


def test_backpressure_drop_is_a_failed_receipt_not_success() -> None:
    sink = InMemoryEventSink(
        max_records=0,
        backpressure=BackpressurePolicy.DROP_NEWEST,
    )
    receipt = sink.receive(TrajectoryRecord.create(RecordKind.RUN, run_id="r"))
    assert receipt.status == DurabilityStatus.DROPPED
    assert receipt.successful is False
    assert receipt.dropped_count == 1


def test_store_backed_reference_sink_returns_durability_receipts(
    tmp_path: Path,
) -> None:
    store = JsonTrajectoryStore(tmp_path / "trajectory-store.json")
    dispatcher = EventSinkDispatcher()
    dispatcher.add_sink(
        TrajectoryStoreEventSink(store),
        view=PrivacyView.RAW_PRIVATE,
    )

    received = dispatcher.receive(
        TrajectoryRecord.create(RecordKind.RUN, run_id="run-1")
    )
    flushed = dispatcher.flush()
    closed = dispatcher.close()

    assert received.receipts[0].status == DurabilityStatus.PERSISTED
    assert flushed.receipts[0].status == DurabilityStatus.PERSISTED
    assert closed.receipts[0].status == DurabilityStatus.PERSISTED
    assert store.validate_integrity().valid
    store.close()
