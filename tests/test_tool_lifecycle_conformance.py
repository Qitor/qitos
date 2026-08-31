from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from qitos.core.action import Action
from qitos.core.session import AttemptIdentity
from qitos.core.tool import BaseTool, ToolSpec
from qitos.core.tool_registry import ToolRegistry
from qitos.core.tool_runtime import (
    TOOL_LIFECYCLE_MATRIX,
    CancellationCapability,
    MigrationDisposition,
    ToolLifecycleReceipt,
    ToolLifecycleSpec,
    ToolLifecycleState,
    ToolResourceKind,
)
from qitos.engine.action_executor import ActionExecutor
from qitos.engine.cancellation import (
    QuiescenceBarrier,
    QuiescenceState,
)


def test_lifecycle_matrix_covers_every_required_resource_family() -> None:
    assert set(TOOL_LIFECYCLE_MATRIX) == set(ToolResourceKind)
    for kind, spec in TOOL_LIFECYCLE_MATRIX.items():
        assert spec.resource_kind is kind
        assert spec.owner
        assert spec.completion_signal
        assert spec.timeout_behavior
        assert spec.cleanup_responsibility
        assert spec.process_loss_behavior
        assert spec.late_result_handling
        assert spec.migration in set(MigrationDisposition)

    assert (
        TOOL_LIFECYCLE_MATRIX[ToolResourceKind.THREAD].cancellation_capability
        is CancellationCapability.NONE
    )


def test_lifecycle_fixture_exactly_matches_executable_matrix() -> None:
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "s2"
        / "lane_c"
        / "lifecycle_matrix.v1.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert fixture == {
        "schema_version": "qitos.s2_lane_c.lifecycle_matrix/v1",
        "rows": [spec.to_dict() for spec in TOOL_LIFECYCLE_MATRIX.values()],
    }
    assert (
        TOOL_LIFECYCLE_MATRIX[ToolResourceKind.SUBPROCESS].cancellation_capability
        is CancellationCapability.TERMINATE_OWNED_PROCESS
    )


class _FakeLifecycleAdapter:
    def __init__(
        self,
        kind: ToolResourceKind,
        capability: CancellationCapability,
    ) -> None:
        base = TOOL_LIFECYCLE_MATRIX[kind]
        self._spec = ToolLifecycleSpec(
            resource_kind=kind,
            owner="fake adapter",
            completion_signal="fake completion event",
            cancellation_capability=capability,
            timeout_behavior=base.timeout_behavior,
            cleanup_responsibility="fake adapter cleanup",
            process_loss_behavior=base.process_loss_behavior,
            migration=base.migration,
            late_result_handling=base.late_result_handling,
        )
        self.completed = threading.Event()
        self.cancel_requests = 0

    @property
    def spec(self) -> ToolLifecycleSpec:
        return self._spec

    def request_cancel(self, attempt_id: AttemptIdentity) -> bool:
        self.cancel_requests += 1
        if self.spec.cancellation_capability is CancellationCapability.NONE:
            return False
        self.completed.set()
        return True

    def wait_completed(self, attempt_id: AttemptIdentity, timeout: float) -> bool:
        return self.completed.wait(timeout=timeout)


@pytest.mark.parametrize(
    ("kind", "capability"),
    [
        (ToolResourceKind.SYNC_FUNCTION, CancellationCapability.NONE),
        (ToolResourceKind.ASYNC_COROUTINE, CancellationCapability.COOPERATIVE),
        (ToolResourceKind.THREAD, CancellationCapability.NONE),
        (
            ToolResourceKind.SUBPROCESS,
            CancellationCapability.TERMINATE_OWNED_PROCESS,
        ),
    ],
)
def test_lifecycle_adapter_protocol_conformance(
    kind: ToolResourceKind, capability: CancellationCapability
) -> None:
    adapter = _FakeLifecycleAdapter(kind, capability)
    attempt = AttemptIdentity.generate()
    accepted = adapter.request_cancel(attempt)
    assert accepted is (capability is not CancellationCapability.NONE)
    assert adapter.wait_completed(attempt, timeout=0.0) is accepted


class _KindTool(BaseTool):
    def __init__(self, name: str, kind: ToolResourceKind) -> None:
        super().__init__(ToolSpec(name=name, description=name, lifecycle=kind))

    def execute(self, args: dict[str, Any], runtime_context=None) -> Any:
        return self.name


class _AsyncKindTool(_KindTool):
    async def execute(self, args: dict[str, Any], runtime_context=None) -> Any:
        return self.name


class _SubprocessKindTool(_KindTool):
    def execute(self, args: dict[str, Any], runtime_context=None) -> Any:
        completed = subprocess.run(
            [sys.executable, "-c", "print('subprocess-ok')"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        return completed.stdout.strip()


@pytest.mark.parametrize(
    "tool_value",
    [
        _KindTool("sync", ToolResourceKind.SYNC_FUNCTION),
        _AsyncKindTool("async", ToolResourceKind.ASYNC_COROUTINE),
        _KindTool("thread", ToolResourceKind.THREAD),
        _SubprocessKindTool("subprocess", ToolResourceKind.SUBPROCESS),
    ],
)
def test_reference_executor_emits_lifecycle_receipt_for_adapter_family(
    tool_value: BaseTool,
) -> None:
    receipts = []
    result = ActionExecutor(ToolRegistry().register(tool_value)).execute_one(
        Action(tool_value.name), terminal_callback=receipts.append
    )
    assert result.status == "success"
    assert receipts[0].lifecycle.spec.resource_kind is tool_value.spec.lifecycle
    assert receipts[0].lifecycle.state is ToolLifecycleState.TERMINAL
    assert receipts[0].lifecycle.migratable is True


def test_non_cancellable_running_thread_is_non_migratable_until_ack() -> None:
    entered = threading.Event()
    release = threading.Event()

    class _ThreadTool(BaseTool):
        def __init__(self) -> None:
            super().__init__(
                ToolSpec(
                    name="thread_work",
                    description="thread",
                    lifecycle=ToolResourceKind.THREAD,
                )
            )

        def execute(self, args, runtime_context=None):
            entered.set()
            assert release.wait(timeout=2.0)
            return "done"

    executor = ActionExecutor(ToolRegistry().register(_ThreadTool()))
    worker = threading.Thread(
        target=lambda: executor.execute_one(Action("thread_work"))
    )
    worker.start()
    assert entered.wait(timeout=2.0)

    blocked = executor.request_pause(timeout=0.0)
    assert blocked.state is QuiescenceState.NON_MIGRATABLE
    assert blocked.migratable is False
    assert blocked.attempts[0].state is QuiescenceState.WORKER_STILL_RUNNING
    assert blocked.attempts[0].worker_still_running is True

    release.set()
    worker.join(timeout=2.0)
    quiesced = executor.request_pause(timeout=0.0)
    assert quiesced.state is QuiescenceState.QUIESCED
    assert quiesced.migratable is True


def test_cooperative_cancellation_requires_completion_ack() -> None:
    barrier = QuiescenceBarrier()
    attempt = AttemptIdentity.generate()
    spec = TOOL_LIFECYCLE_MATRIX[ToolResourceKind.ASYNC_COROUTINE]
    callback_called = threading.Event()

    def _cancel() -> bool:
        callback_called.set()
        barrier.mark_terminal(
            ToolLifecycleReceipt(
                attempt,
                spec,
                ToolLifecycleState.CANCELLED,
                owner_generation=0,
                started_at=1.0,
                completed_at=2.0,
            )
        )
        return True

    barrier.register(attempt, spec, owner_generation=0, cancel_callback=_cancel)
    receipt = barrier.request_pause(timeout=1.0)
    assert callback_called.is_set()
    assert receipt.state is QuiescenceState.QUIESCED
    assert receipt.attempts[0].state is QuiescenceState.CANCELLED


def test_sync_timeout_does_not_claim_hard_thread_cancellation() -> None:
    entered = threading.Event()
    release = threading.Event()
    finished = threading.Event()

    class _TimedThread(BaseTool):
        def __init__(self) -> None:
            super().__init__(
                ToolSpec(
                    name="timed_thread",
                    description="thread",
                    lifecycle=ToolResourceKind.THREAD,
                    timeout_s=0.01,
                )
            )

        def execute(self, args, runtime_context=None):
            entered.set()
            try:
                assert release.wait(timeout=2.0)
                return "late"
            finally:
                finished.set()

    executor = ActionExecutor(ToolRegistry().register(_TimedThread()))
    result = executor.execute_one(Action("timed_thread"))
    assert entered.is_set()
    assert result.status == "timed_out"
    assert result.worker_still_running is True
    assert result.retry_disposition == "blocked_worker_running"
    assert executor.request_pause(timeout=0.0).migratable is False

    release.set()
    assert finished.wait(timeout=2.0)
    assert executor.request_pause(timeout=1.0).migratable is True


def test_outcome_unknown_remains_non_migratable_after_worker_completion() -> None:
    barrier = QuiescenceBarrier()
    attempt = AttemptIdentity.generate()
    spec = TOOL_LIFECYCLE_MATRIX[ToolResourceKind.HTTP_CLIENT]
    barrier.register(attempt, spec, owner_generation=4)
    barrier.mark_terminal(
        ToolLifecycleReceipt(
            attempt,
            spec,
            ToolLifecycleState.OUTCOME_UNKNOWN,
            owner_generation=4,
            started_at=time.time(),
            completed_at=time.time(),
            outcome_unknown=True,
        )
    )
    receipt = barrier.request_pause(timeout=0.0)
    assert receipt.state is QuiescenceState.NON_MIGRATABLE
    assert receipt.attempts[0].state is QuiescenceState.OUTCOME_UNKNOWN
    assert receipt.attempts[0].outcome_unknown is True
