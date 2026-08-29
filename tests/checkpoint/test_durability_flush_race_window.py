from __future__ import annotations

import logging
import queue
import threading

from qitos.checkpoint.durability import DurabilityManager, DurabilityMode
from qitos.checkpoint.store import Checkpoint, CheckpointConfig, CheckpointId


class _BlockingStore:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def put(self, *args: object) -> CheckpointConfig:
        self.started.set()
        assert self.release.wait(timeout=2.0)
        config = args[0]
        assert isinstance(config, CheckpointConfig)
        return config


def test_worker_can_drain_full_queue_before_flush_sentinel(caplog) -> None:
    """Deterministically prove the race in the historical warning assertion."""
    store = _BlockingStore()
    manager = DurabilityManager.__new__(DurabilityManager)
    manager._store = store
    manager._mode = DurabilityMode.ASYNC
    manager._buffer = []
    manager._queue = queue.Queue(maxsize=1)
    manager._shutdown = threading.Event()
    manager._worker = threading.Thread(target=manager._async_worker, daemon=True)

    checkpoint = Checkpoint(
        id=CheckpointId("cp-race"),
        thread_id="thread-race",
        step=0,
        state_data={},
    )
    manager._queue.put_nowait(
        (CheckpointConfig(thread_id="thread-race"), checkpoint, {}, {}, None, None)
    )
    assert manager._queue.full()
    manager._worker.start()
    assert store.started.wait(timeout=2.0)
    assert manager._queue.empty()

    flush_done = threading.Event()

    def _flush() -> None:
        manager.flush()
        flush_done.set()

    with caplog.at_level(logging.WARNING, logger="qitos.checkpoint.durability"):
        flushing = threading.Thread(target=_flush)
        flushing.start()
        # The worker is blocked in store.put, so a successful enqueue means the
        # sentinel occupied the slot that was full before the worker's get().
        for _ in range(1000):
            if manager._queue.full():
                break
            threading.Event().wait(0.001)
        assert manager._queue.full()
        store.release.set()
        flushing.join(timeout=2.0)

    assert flush_done.is_set()
    assert not any("queue full during flush" in record.message for record in caplog.records)
