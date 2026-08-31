from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Optional, Sequence

import pytest

from qitos.checkpoint.memory_store import InMemoryCheckpointStore
from qitos.checkpoint.pending_writes import PendingWriteManager, PendingWriteState
from qitos.checkpoint.store import Checkpoint, CheckpointConfig, CheckpointId
from qitos.core.action import Action, ActionExecutionPolicy
from qitos.core.artifact import ArtifactRef
from qitos.core.tool import BaseTool, FunctionTool, RetryPolicy, ToolSpec, tool
from qitos.core.tool_registry import ToolRegistry
from qitos.core.tool_result import ToolResult
from qitos.core.tool_runtime import (
    TOOL_LIFECYCLE_MATRIX,
    TerminalDisposition,
    ToolBatchExecution,
    ToolEffectDeclaration,
    ToolEffectReceipt,
    ToolExecutorProtocol,
    ToolLifecycleReceipt,
    ToolLifecycleState,
    ToolResourceKind,
)
from qitos.engine.action_executor import ActionExecutor
from qitos.engine.tool_runtime import ToolBatchLedger
from qitos.mcp.bridge import mcp_server_to_function_tools
from qitos.mcp.server import MCPServer, MCPToolInfo


def test_handoff_fixture_preserves_batch_correlation_and_loss_facts() -> None:
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "s2"
        / "lane_c"
        / "runtime_handoff.v1.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    batch = fixture["batch"]
    assert batch["schema_version"] == "qitos.tool_batch_snapshot/v1"
    assert batch["completion_order"] == ["call:second", "call:first"]
    assert batch["declaration_order"] == ["call:first", "call:second"]
    assert batch["closed"] is True
    assert [item["slot_id"] for item in fixture["terminal_receipts"]] == [
        "call:second",
        "call:first",
    ]
    assert all(
        item["advances_state"] is False
        for item in fixture["suppressed_terminals"]
    )


class _ClassTool(BaseTool):
    def __init__(self) -> None:
        super().__init__(
            ToolSpec(
                name="class_add",
                description="add",
                parameters={"value": {"type": "integer"}},
                required=["value"],
            )
        )

    def execute(self, args: dict[str, Any], runtime_context=None) -> Any:
        return {
            "value": args["value"] + 1,
            "has_attempt": (runtime_context or {}).get("attempt_id") is not None,
        }


@tool(name="function_add")
def _function_add(value: int, runtime_context=None) -> int:
    assert runtime_context["slot_id"]
    return value + 1


class _AsyncTool(BaseTool):
    def __init__(self) -> None:
        super().__init__(ToolSpec(name="async_value", description="async"))

    async def execute(self, args: dict[str, Any], runtime_context=None) -> Any:
        return "async-ok"


@pytest.mark.parametrize(
    ("tool_value", "action", "expected"),
    [
        (_ClassTool(), Action("class_add", {"value": 2}), {"value": 3, "has_attempt": True}),
        (FunctionTool(_function_add), Action("function_add", {"value": 2}), 3),
        (_AsyncTool(), Action("async_value"), "async-ok"),
    ],
)
def test_tool_implementation_conformance(
    tool_value: BaseTool, action: Action, expected: Any
) -> None:
    executor = ActionExecutor(ToolRegistry().register(tool_value))
    result = executor.execute_one(action, batch_id="batch:implementation")

    assert result.status == "success"
    assert result.output == expected
    assert result.attempt_id is not None
    assert result.batch_closure["batch_id"] == "batch:implementation"


def test_run_remains_only_a_compatibility_route_to_execute() -> None:
    assert _ClassTool().run(value=4) == {"value": 5, "has_attempt": False}


class _FakeMCPServer(MCPServer):
    @property
    def name(self) -> str:
        return "fake-runtime-server"

    async def connect(self) -> None:
        return None

    async def cleanup(self) -> None:
        return None

    async def list_tools(self) -> list[MCPToolInfo]:
        return [
            MCPToolInfo(
                name="remote_echo",
                input_schema={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
            )
        ]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        return {"tool": tool_name, "value": arguments["value"]}


@pytest.mark.asyncio
async def test_mcp_bridge_uses_the_canonical_executor_boundary() -> None:
    bridged = await mcp_server_to_function_tools(_FakeMCPServer())
    receipts = []
    result = ActionExecutor(ToolRegistry().register(bridged[0])).execute_one(
        Action("remote_echo", {"value": "mcp-ok"}),
        terminal_callback=receipts.append,
    )
    assert result.output == {"tool": "remote_echo", "value": "mcp-ok"}
    assert (
        receipts[0].lifecycle.spec.resource_kind
        is ToolResourceKind.MCP_REQUEST
    )


def test_environment_operation_uses_runtime_context_and_canonical_receipt() -> None:
    env = object()

    class _EnvironmentTool(BaseTool):
        def __init__(self) -> None:
            super().__init__(
                ToolSpec(
                    name="env_operation",
                    description="env operation",
                    lifecycle=ToolResourceKind.ENVIRONMENT_OPERATION,
                )
            )

        def execute(self, args, runtime_context=None):
            return runtime_context["env"] is env

    receipts = []
    result = ActionExecutor(
        ToolRegistry().register(_EnvironmentTool())
    ).execute_one(
        Action("env_operation"), env=env, terminal_callback=receipts.append
    )
    assert result.output is True
    assert (
        receipts[0].lifecycle.spec.resource_kind
        is ToolResourceKind.ENVIRONMENT_OPERATION
    )


def test_canonical_artifact_output_crosses_the_same_runtime_boundary() -> None:
    artifact = ArtifactRef(
        artifact_id="artifact:runtime-fixture",
        resolver_key="artifact-resolver:runtime-fixture",
        sha256="a" * 64,
        media_type="application/json",
        byte_length=2,
    )

    class _ArtifactTool(BaseTool):
        def __init__(self) -> None:
            super().__init__(
                ToolSpec(
                    name="artifact_output",
                    description="artifact output",
                    produces_artifact=True,
                )
            )

        def execute(self, args, runtime_context=None):
            return ToolResult(output={"ok": True}, artifact_refs=(artifact,))

    result = ActionExecutor(
        ToolRegistry().register(_ArtifactTool())
    ).execute_one(Action("artifact_output"))
    assert result.output == {"ok": True}
    assert result.artifact_refs == (artifact,)


class _GatedTool(BaseTool):
    def __init__(
        self,
        name: str,
        entered: threading.Event,
        release: threading.Event,
    ) -> None:
        super().__init__(
            ToolSpec(name=name, description=name, concurrency_safe=True)
        )
        self._entered = entered
        self._release = release

    def execute(self, args: dict[str, Any], runtime_context=None) -> Any:
        self._entered.set()
        assert self._release.wait(timeout=2.0)
        return self.name


def test_parallel_batch_publishes_terminal_slots_before_batch_closure() -> None:
    first_entered = threading.Event()
    second_entered = threading.Event()
    first_release = threading.Event()
    second_release = threading.Event()
    terminal_events = {"first": threading.Event(), "second": threading.Event()}
    terminal_order: list[str] = []
    snapshots = []
    tools = ToolRegistry().register(
        _GatedTool("first", first_entered, first_release)
    ).register(_GatedTool("second", second_entered, second_release))
    executor = ActionExecutor(
        tools,
        policy=ActionExecutionPolicy(mode="parallel", max_concurrency=2),
    )
    holder: list[ToolBatchExecution] = []

    def _terminal(receipt) -> None:
        terminal_order.append(receipt.slot.slot_id)
        terminal_events[receipt.slot.slot_id].set()

    worker = threading.Thread(
        target=lambda: holder.append(
            executor.execute_batch(
                [
                    Action("first", action_id="first"),
                    Action("second", action_id="second"),
                ],
                batch_id="batch:parallel",
                terminal_callback=_terminal,
                partial_batch_callback=snapshots.append,
            )
        )
    )
    worker.start()
    assert first_entered.wait(timeout=2.0)
    assert second_entered.wait(timeout=2.0)

    second_release.set()
    assert terminal_events["second"].wait(timeout=2.0)
    assert worker.is_alive()
    assert snapshots[-1].completion_order == ("second",)
    assert snapshots[-1].closed is False

    first_release.set()
    assert terminal_events["first"].wait(timeout=2.0)
    worker.join(timeout=2.0)

    execution = holder[0]
    assert terminal_order == ["second", "first"]
    assert execution.snapshot.completion_order == ("second", "first")
    assert execution.snapshot.declaration_order == ("first", "second")
    assert [
        result.output for result in execution.results_in_declaration_order
    ] == ["first", "second"]
    assert execution.snapshot.closed is True


def test_partial_batch_terminal_callback_is_immediately_persistable() -> None:
    store = InMemoryCheckpointStore()
    checkpoint = Checkpoint(
        id=CheckpointId("cp-partial"),
        thread_id="thread-partial",
        step=0,
        state_data={},
    )
    store.put(CheckpointConfig(thread_id="thread-partial"), checkpoint, {}, {})
    config = CheckpointConfig(
        thread_id="thread-partial", checkpoint_id=checkpoint.id
    )
    pending = PendingWriteManager(store)
    first_entered = threading.Event()
    second_entered = threading.Event()
    first_release = threading.Event()
    second_release = threading.Event()
    second_persisted = threading.Event()
    tools = ToolRegistry().register(
        _GatedTool("first", first_entered, first_release)
    ).register(_GatedTool("second", second_entered, second_release))
    executor = ActionExecutor(
        tools,
        policy=ActionExecutionPolicy(mode="parallel", max_concurrency=2),
    )

    def _partial(snapshot) -> None:
        for slot in snapshot.slots:
            pending.begin_task(
                slot.slot_id,
                "tool_terminal",
                owner_generation=slot.owner_generation,
            )

    def _terminal(receipt) -> None:
        persisted = pending.complete_task(
            receipt.slot.slot_id,
            receipt.to_dict(),
            config,
            owner_generation=receipt.slot.owner_generation,
        )
        if receipt.slot.slot_id == "second":
            assert persisted.state is PendingWriteState.PERSISTED
            second_persisted.set()

    worker = threading.Thread(
        target=lambda: executor.execute_batch(
            [
                Action("first", action_id="first"),
                Action("second", action_id="second"),
            ],
            batch_id="batch:persistence",
            terminal_callback=_terminal,
            partial_batch_callback=_partial,
        )
    )
    worker.start()
    assert first_entered.wait(timeout=2.0)
    assert second_entered.wait(timeout=2.0)
    second_release.set()
    assert second_persisted.wait(timeout=2.0)

    recovered = store.get_tuple(config)
    assert recovered is not None
    assert [write.task_id for write in recovered.pending_writes or []] == ["second"]
    assert pending.get_receipt("first").state is PendingWriteState.ACCEPTED

    first_release.set()
    worker.join(timeout=2.0)
    assert pending.wait_for_tasks(["first", "second"], timeout=0.0).durable


class _ThirdPartyPolicy:
    mode = "parallel"
    fail_fast = False
    max_concurrency = 1
    parallel_tool_names = frozenset({"echo"})


class _ThirdPartyExecutor:
    """A package-style adapter implementing the public protocol by composition."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._delegate = ActionExecutor(registry, policy=_ThirdPartyPolicy())

    def execute_one(self, action: Action, **kwargs: Any) -> ToolResult:
        return self._delegate.execute_one(action, **kwargs)

    def execute_batch(
        self, actions: Sequence[Action], **kwargs: Any
    ) -> ToolBatchExecution:
        return self._delegate.execute_batch(actions, **kwargs)


class _Echo(BaseTool):
    def __init__(self) -> None:
        super().__init__(
            ToolSpec(name="echo", description="echo", concurrency_safe=True)
        )

    def execute(self, args: dict[str, Any], runtime_context=None) -> Any:
        return args["value"]


@pytest.mark.parametrize("factory", [ActionExecutor, _ThirdPartyExecutor])
def test_executor_protocol_conformance(factory) -> None:
    executor: ToolExecutorProtocol = factory(ToolRegistry().register(_Echo()))
    execution = executor.execute_batch(
        [Action("echo", {"value": 1}), Action("echo", {"value": 2})],
        batch_id="batch:executor-conformance",
    )
    assert [result.output for result in execution.results_in_declaration_order] == [
        1,
        2,
    ]
    assert execution.snapshot.closed


class _EffectBackend:
    def __init__(self) -> None:
        self.keys: set[str] = set()
        self.duplicate_effects = 0

    def commit(self, key: str) -> None:
        if key in self.keys:
            self.duplicate_effects += 1
        self.keys.add(key)


class _CommitThenFail(BaseTool):
    def __init__(self, backend: _EffectBackend) -> None:
        super().__init__(
            ToolSpec(
                name="effectful",
                description="effectful",
                effect=ToolEffectDeclaration("effect:fake-write"),
                retry_policy=RetryPolicy(
                    max_attempts=3, backoff_factor=0, jitter=False
                ),
            )
        )
        self._backend = backend

    def execute(self, args: dict[str, Any], runtime_context=None) -> Any:
        self._backend.commit(runtime_context["idempotency_key"])
        raise RuntimeError("transport failed after the external commit")


class _CommitSuccessfully(BaseTool):
    def __init__(self, backend: _EffectBackend) -> None:
        super().__init__(
            ToolSpec(
                name="effect_success",
                description="effect success",
                effect=ToolEffectDeclaration("effect:fake-success"),
            )
        )
        self._backend = backend

    def execute(self, args: dict[str, Any], runtime_context=None) -> Any:
        self._backend.commit(runtime_context["idempotency_key"])
        return "committed"


def test_declared_effect_failure_is_not_retried_or_guessed() -> None:
    backend = _EffectBackend()
    result = ActionExecutor(
        ToolRegistry().register(_CommitThenFail(backend))
    ).execute_one(Action("effectful"), batch_id="batch:effect")

    assert result.attempts == 1
    assert result.effect_state == "reconciliation_required"
    assert result.outcome_unknown is True
    assert result.retry_disposition == "requires_reconciliation"
    assert len(backend.keys) == 1
    assert backend.duplicate_effects == 0


def test_committed_effect_is_terminal_and_non_retryable() -> None:
    backend = _EffectBackend()
    result = ActionExecutor(
        ToolRegistry().register(_CommitSuccessfully(backend))
    ).execute_one(Action("effect_success"), batch_id="batch:committed")

    assert result.status == "success"
    assert result.effect_state == "committed"
    assert result.retry_disposition == "non_retryable"
    assert result.idempotency_ref is not None
    assert len(backend.keys) == 1
    assert backend.duplicate_effects == 0


class _CountingEffectPolicy:
    def __init__(self) -> None:
        self.declarations = 0
        self.finalizations = 0

    def declare(self, action, tool, runtime_context):
        self.declarations += 1
        return None

    def finalize(self, declaration, result, *, dispatched):
        self.finalizations += 1
        return ToolEffectReceipt(
            declaration=None,
            state="no_effect_declared",
            retry_disposition="non_retryable",
        )


def test_third_party_effect_policy_is_replaceable() -> None:
    policy = _CountingEffectPolicy()
    result = ActionExecutor(
        ToolRegistry().register(_Echo()), effect_policy=policy
    ).execute_one(Action("echo", {"value": "ok"}))
    assert result.output == "ok"
    assert policy.declarations == 1
    assert policy.finalizations == 1


def test_duplicate_and_stale_terminal_submissions_are_suppressed() -> None:
    action = Action("echo", action_id="call:one")
    ledger = ToolBatchLedger([action], batch_id="batch:ledger", owner_generation=3)
    slot = ledger.slot_for_index(0)
    spec = TOOL_LIFECYCLE_MATRIX[ToolResourceKind.SYNC_FUNCTION]
    lifecycle = ToolLifecycleReceipt(
        slot.attempt_id,
        spec,
        ToolLifecycleState.TERMINAL,
        owner_generation=3,
        started_at=1.0,
        completed_at=2.0,
    )
    effect = ToolEffectReceipt(
        None, "no_effect_declared", "non_retryable"
    )
    first = ledger.commit_terminal(
        slot_id=slot.slot_id,
        result=ToolResult(output="one"),
        lifecycle=lifecycle,
        effect=effect,
        owner_generation=3,
    )
    duplicate = ledger.commit_terminal(
        slot_id=slot.slot_id,
        result=ToolResult(output="one"),
        lifecycle=lifecycle,
        effect=effect,
        owner_generation=3,
    )
    stale = ledger.commit_terminal(
        slot_id=slot.slot_id,
        result=ToolResult(output="stale"),
        lifecycle=lifecycle,
        effect=effect,
        owner_generation=2,
    )

    assert first.disposition is TerminalDisposition.COMMITTED
    assert duplicate.disposition is TerminalDisposition.DUPLICATE_IGNORED
    assert stale.disposition is TerminalDisposition.STALE_OWNER_REJECTED
    assert ledger.snapshot().results_in_declaration_order[0].output == "one"


def test_permission_diagnostics_do_not_copy_secret_arguments() -> None:
    class _Denied(_Echo):
        def check_permissions(self, args, runtime_context=None):
            from qitos.core.tool import ToolPermissionDecision

            return ToolPermissionDecision.deny("blocked")

    secret = "sk-secret-value-that-must-not-appear"
    result = ActionExecutor(ToolRegistry().register(_Denied())).execute_one(
        Action("echo", {"value": secret})
    )
    assert result.status == "skipped"
    assert secret not in json.dumps(result.to_persistence_dict(), sort_keys=True)


def test_permission_rewrite_runs_full_validation_before_dispatch() -> None:
    executed = threading.Event()

    class _Rewritten(_Echo):
        def check_permissions(self, args, runtime_context=None):
            from qitos.core.tool import ToolPermissionDecision

            return ToolPermissionDecision.allow(updated_args={"value": "blocked"})

        def validate_input(self, args, runtime_context=None):
            from qitos.core.tool import ToolValidationResult

            if args["value"] == "blocked":
                return ToolValidationResult.fail(
                    "rewritten value is forbidden", code="rewritten_forbidden"
                )
            return ToolValidationResult.ok()

        def execute(self, args, runtime_context=None):
            executed.set()
            return args["value"]

    result = ActionExecutor(ToolRegistry().register(_Rewritten())).execute_one(
        Action("echo", {"value": "allowed"})
    )
    assert result.status == "error"
    assert result.error_code == "rewritten_forbidden"
    assert result.metadata["validation"]["boundary"] == "post_permission"
    assert not executed.is_set()
