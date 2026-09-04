"""Tests for bounded queue capacity in EventStream and DurabilityManager."""
from __future__ import annotations

import logging
import threading


from qitos.engine.events import EventStream, EngineEvent, EngineEventType
from qitos.checkpoint.durability import DurabilityManager, DurabilityMode
from qitos.checkpoint.memory_store import InMemoryCheckpointStore
from qitos.checkpoint.store import Checkpoint, CheckpointConfig, CheckpointId


def test_eventstream_main_queue_has_maxsize():
    """EventStream._queue has maxsize=4096."""
    es = EventStream()
    assert es._queue.maxsize == 4096


def test_eventstream_subscriber_queue_has_maxsize():
    """Subscriber queues have maxsize=1024."""
    es = EventStream()
    sub = es.subscribe()
    assert sub.maxsize == 1024


def test_eventstream_emit_does_not_raise_when_queue_full():
    """Emitting to a full queue drops gracefully without raising."""
    es = EventStream()
    # Fill the queue to capacity
    event = EngineEvent(event_type=EngineEventType.RUN_START, payload={})
    for _ in range(4096):
        es._queue.put_nowait(event)
    # This should not raise
    es.emit(event)


def test_eventstream_close_does_not_raise_when_queue_full():
    """Closing with a full queue drops the sentinel gracefully."""
    es = EventStream()
    event = EngineEvent(event_type=EngineEventType.RUN_START, payload={})
    for _ in range(4096):
        es._queue.put_nowait(event)
    # This should not raise
    es.close()


def test_durability_manager_async_queue_is_bounded():
    """DurabilityManager._queue has maxsize=4096 in ASYNC mode."""
    store = InMemoryCheckpointStore()
    dm = DurabilityManager(store, mode=DurabilityMode.ASYNC)
    try:
        assert dm._queue is not None
        assert dm._queue.maxsize == 4096
    finally:
        dm.shutdown()


def test_durability_manager_sync_has_no_queue():
    """DurabilityManager in SYNC mode has no queue (it is None)."""
    store = InMemoryCheckpointStore()
    dm = DurabilityManager(store, mode=DurabilityMode.SYNC)
    assert dm._queue is None


def test_durability_manager_full_queue_logs_warning(caplog):
    """A held real store write makes queue saturation deterministic."""
    entered = threading.Event()
    release = threading.Event()

    class HeldStore(InMemoryCheckpointStore):
        def put(self, *args, **kwargs):
            entered.set()
            assert release.wait(10), "test did not release the owned store worker"
            return super().put(*args, **kwargs)

    dm = DurabilityManager(HeldStore(), mode=DurabilityMode.ASYNC)
    cp = Checkpoint(
        id=CheckpointId("cp1"), thread_id="t1", step=0, state_data={"x": 1}
    )
    config = CheckpointConfig(thread_id="t1")
    try:
        dm.put(config, cp, {}, {})
        assert entered.wait(5), "owned store worker did not start"
        for _ in range(4096):
            dm.put(config, cp, {}, {})
        with caplog.at_level(logging.WARNING, logger="qitos.checkpoint.durability"):
            _, receipt = dm.put_with_receipt(config, cp, {}, {})
        assert receipt.state.value == "rejected"
        assert any("queue full" in rec.message.lower() for rec in caplog.records)
    finally:
        release.set()
        dm.shutdown()


def test_durability_manager_flush_uses_ack_barrier_not_queue_sentinel():
    """An empty accepted prefix is immediately and honestly durable."""
    store = InMemoryCheckpointStore()
    dm = DurabilityManager(store, mode=DurabilityMode.ASYNC)
    try:
        assert dm._queue is not None
        receipt = dm.flush(timeout=0.0)
        assert receipt.target_sequence == 0
        assert receipt.complete is True
        assert receipt.durable is True
    finally:
        dm.shutdown()
