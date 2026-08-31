from __future__ import annotations

import threading

from qitos.checkpoint.durability import (
    DurabilityManager,
    DurabilityMode,
    DurabilityWriteState,
)
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


class _ImmediateStore:
    def put(self, *args: object) -> CheckpointConfig:
        config = args[0]
        assert isinstance(config, CheckpointConfig)
        return config


def test_flush_waits_for_real_store_completion_ack() -> None:
    """The flush barrier cannot complete merely because a queue item was taken."""
    store = _BlockingStore()
    manager = DurabilityManager(store, mode=DurabilityMode.ASYNC)  # type: ignore[arg-type]
    checkpoint = Checkpoint(
        id=CheckpointId("cp-race"),
        thread_id="thread-race",
        step=0,
        state_data={},
    )
    _, queued = manager.put_with_receipt(
        CheckpointConfig(thread_id="thread-race"), checkpoint, {}, {}
    )
    assert queued.state is DurabilityWriteState.QUEUED
    assert store.started.wait(timeout=2.0)

    flush_done = threading.Event()
    holder = []

    def _flush() -> None:
        holder.append(manager.flush(timeout=2.0))
        flush_done.set()

    flushing = threading.Thread(target=_flush)
    flushing.start()
    assert not flush_done.wait(timeout=0.05)
    store.release.set()
    assert flush_done.wait(timeout=2.0)
    flushing.join(timeout=2.0)

    assert holder[0].complete is True
    assert holder[0].durable is True
    assert holder[0].completed_sequence >= queued.sequence
    manager.shutdown()


def test_fast_store_ack_cannot_regress_to_queued() -> None:
    """Producer publication cannot overwrite a worker's terminal receipt."""
    manager = DurabilityManager(
        _ImmediateStore(), mode=DurabilityMode.ASYNC  # type: ignore[arg-type]
    )
    target = 128
    for index in range(target):
        checkpoint = Checkpoint(
            id=CheckpointId(f"cp-fast-{index}"),
            thread_id="thread-fast",
            step=index,
            state_data={},
        )
        manager.put_with_receipt(
            CheckpointConfig(thread_id="thread-fast"), checkpoint, {}, {}
        )

    receipt = manager.flush(timeout=2.0)
    assert receipt.complete is True
    assert receipt.durable is True
    assert receipt.completed_sequence == target
    manager.shutdown()
