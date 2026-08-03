"""Regression tests for issue #35 — safe multi-action concurrent execution contract.

Covers:
1. Exclusive actions act as barriers (no reordering across them).
2. max_concurrency is respected; results stay in model call order.
3. Async handlers are awaited; timeouts change the terminal state.
4. fail_fast does not mislabel already-completed actions and blocks unstarted ones.
5. Public ``action_execution_policy`` entry point survives handoff.
6. Public ``Engine.cancel()`` / ``AsyncEngine.cancel()``.
7. Traces record policy, concurrency peak, ordering, terminal states.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Dict, List

import pytest

from qitos.core.action import Action, ActionExecutionPolicy, ActionStatus
from qitos.core.tool import BaseTool, ToolSpec
from qitos.engine.action_executor import ActionExecutor


class _Recorder:
    """Thread-safe timeline + concurrency peak tracker."""

    def __init__(self) -> None:
        self.timeline: List[str] = []
        self._lock = threading.Lock()
        self._active = 0
        self.peak = 0

    def start(self, name: str) -> None:
        with self._lock:
            self.timeline.append(f"{name}:start")
            self._active += 1
            self.peak = max(self.peak, self._active)

    def end(self, name: str) -> None:
        with self._lock:
            self._active -= 1
            self.timeline.append(f"{name}:end")


class TimelineTool(BaseTool):
    def __init__(
        self,
        name: str,
        recorder: _Recorder,
        *,
        concurrency_safe: bool = False,
        delay: float = 0.05,
        boom: bool = False,
        timeout_s: float | None = None,
    ) -> None:
        super().__init__(
            ToolSpec(
                name=name,
                description=name,
                concurrency_safe=concurrency_safe,
                timeout_s=timeout_s,
            )
        )
        self._recorder = recorder
        self._delay = delay
        self._boom = boom

    def execute(self, args: Dict[str, Any], runtime_context: Any = None) -> Any:
        self._recorder.start(self.spec.name)
        try:
            time.sleep(self._delay)
            if self._boom:
                raise RuntimeError("boom")
            return f"{self.spec.name}:ok"
        finally:
            self._recorder.end(self.spec.name)


class FakeRegistry:
    def __init__(self, tools: Dict[str, BaseTool]) -> None:
        self._tools = tools

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)


def _executor(tools: Dict[str, BaseTool], **policy_kwargs: Any) -> ActionExecutor:
    policy = ActionExecutionPolicy(**policy_kwargs) if policy_kwargs else None
    return ActionExecutor(tool_registry=FakeRegistry(tools), policy=policy)


# ---------------------------------------------------------------------------
# 1. Exclusive barrier
# ---------------------------------------------------------------------------


def test_safe_action_does_not_jump_exclusive_barrier():
    rec = _Recorder()
    tools = {
        "safe_a": TimelineTool("safe_a", rec, concurrency_safe=True),
        "exclusive_b": TimelineTool("exclusive_b", rec),
        "safe_c": TimelineTool("safe_c", rec, concurrency_safe=True),
    }
    results = _executor(tools, mode="parallel", max_concurrency=2).execute(
        [
            Action(name="safe_a"),
            Action(name="exclusive_b"),
            Action(name="safe_c"),
        ]
    )

    assert [r.name for r in results] == ["safe_a", "exclusive_b", "safe_c"]
    assert all(r.status == ActionStatus.SUCCESS for r in results)

    # safe_c must not start before exclusive_b has finished.
    assert rec.timeline.index("safe_c:start") > rec.timeline.index("exclusive_b:end")
    # safe_a must finish before exclusive_b starts.
    assert rec.timeline.index("safe_a:end") < rec.timeline.index("exclusive_b:start")


def test_contiguous_safe_actions_still_run_concurrently():
    rec = _Recorder()
    tools = {
        "safe_a": TimelineTool("safe_a", rec, concurrency_safe=True),
        "safe_b": TimelineTool("safe_b", rec, concurrency_safe=True),
        "exclusive": TimelineTool("exclusive", rec),
    }
    results = _executor(tools, mode="parallel", max_concurrency=4).execute(
        [Action(name="safe_a"), Action(name="safe_b"), Action(name="exclusive")]
    )

    assert [r.status for r in results] == [ActionStatus.SUCCESS] * 3
    assert rec.peak == 2
    # Both safe actions start before either ends.
    assert rec.timeline[:2] == ["safe_a:start", "safe_b:start"] or rec.timeline[:2] == [
        "safe_b:start",
        "safe_a:start",
    ]


# ---------------------------------------------------------------------------
# 2. max_concurrency + ordering
# ---------------------------------------------------------------------------


def test_max_concurrency_peaks_at_limit_with_order_preserved():
    rec = _Recorder()
    tools = {
        f"safe_{i}": TimelineTool(f"safe_{i}", rec, concurrency_safe=True, delay=0.05)
        for i in range(4)
    }
    actions = [Action(name=f"safe_{i}", args={"n": i}) for i in range(4)]
    results = _executor(tools, mode="parallel", max_concurrency=2).execute(actions)

    assert rec.peak == 2
    assert [r.name for r in results] == ["safe_0", "safe_1", "safe_2", "safe_3"]
    assert [r.output for r in results] == [f"safe_{i}:ok" for i in range(4)]


# ---------------------------------------------------------------------------
# 3. Async handlers and timeouts
# ---------------------------------------------------------------------------


class AsyncTool(BaseTool):
    def __init__(self, name: str = "async_tool", delay: float = 0.0) -> None:
        super().__init__(ToolSpec(name=name, description=name))
        self._delay = delay

    async def execute(self, args: Dict[str, Any], runtime_context: Any = None) -> Any:
        await asyncio.sleep(self._delay)
        return "awaited"


def test_async_handler_is_awaited(recwarn):
    executor = _executor({"async_tool": AsyncTool()})
    result = executor.execute([Action(name="async_tool")])[0]

    assert result.status == ActionStatus.SUCCESS
    assert result.output == "awaited"
    assert not any(
        "never awaited" in str(w.message) for w in recwarn.list
    ), "coroutine leaked without being awaited"


def test_action_timeout_yields_timed_out_status():
    rec = _Recorder()
    tools = {"slow": TimelineTool("slow", rec, delay=0.5)}
    result = _executor(tools).execute([Action(name="slow", timeout_s=0.01)])[0]

    assert result.status == ActionStatus.TIMED_OUT
    assert result.metadata.get("timeout_source") == "action"
    assert result.metadata.get("timeout_s") == pytest.approx(0.01)


def test_tool_spec_timeout_is_enforced():
    rec = _Recorder()
    tools = {"slow": TimelineTool("slow", rec, delay=0.5, timeout_s=0.01)}
    result = _executor(tools).execute([Action(name="slow")])[0]

    assert result.status == ActionStatus.TIMED_OUT
    assert result.metadata.get("timeout_source") == "tool_spec"


def test_action_timeout_overrides_tool_spec_timeout():
    rec = _Recorder()
    tools = {"quick": TimelineTool("quick", rec, delay=0.02, timeout_s=0.001)}
    # Action-level timeout is generous and must win over the tight spec default.
    result = _executor(tools).execute([Action(name="quick", timeout_s=5.0)])[0]

    assert result.status == ActionStatus.SUCCESS


def test_async_tool_timeout_is_enforced():
    executor = _executor({"async_tool": AsyncTool(delay=0.5)})
    result = executor.execute([Action(name="async_tool", timeout_s=0.01)])[0]

    assert result.status == ActionStatus.TIMED_OUT


def test_timeout_does_not_claim_thread_was_killed():
    rec = _Recorder()
    tools = {"slow": TimelineTool("slow", rec, delay=0.3)}
    result = _executor(tools).execute([Action(name="slow", timeout_s=0.01)])[0]

    assert result.metadata.get("worker_still_running") is True


# ---------------------------------------------------------------------------
# 4. fail_fast terminal states
# ---------------------------------------------------------------------------


def test_fail_fast_does_not_mislabel_completed_action():
    rec = _Recorder()
    tools = {
        "running_safe": TimelineTool("running_safe", rec, concurrency_safe=True, delay=0.15),
        "failing_safe": TimelineTool(
            "failing_safe", rec, concurrency_safe=True, delay=0.01, boom=True
        ),
        "exclusive": TimelineTool("exclusive", rec, delay=0.01),
    }
    results = _executor(tools, mode="parallel", fail_fast=True).execute(
        [
            Action(name="running_safe"),
            Action(name="failing_safe"),
            Action(name="exclusive"),
        ]
    )

    # The action that actually ran to completion must not be recorded as an error.
    assert results[0].status == ActionStatus.SUCCESS
    assert results[1].status == ActionStatus.ERROR
    # fail_fast must prevent the not-yet-started exclusive action.
    assert results[2].status == ActionStatus.CANCELLED
    assert "exclusive:start" not in rec.timeline


def test_fail_fast_disabled_runs_everything():
    rec = _Recorder()
    tools = {
        "safe_a": TimelineTool("safe_a", rec, concurrency_safe=True, delay=0.01),
        "failing": TimelineTool("failing", rec, concurrency_safe=True, delay=0.01, boom=True),
        "exclusive": TimelineTool("exclusive", rec, delay=0.01),
    }
    results = _executor(tools, mode="parallel", fail_fast=False).execute(
        [Action(name="safe_a"), Action(name="failing"), Action(name="exclusive")]
    )

    assert [r.status for r in results] == [
        ActionStatus.SUCCESS,
        ActionStatus.ERROR,
        ActionStatus.SUCCESS,
    ]
    assert "exclusive:start" in rec.timeline


# ---------------------------------------------------------------------------
# 5. Cancellation reaches the executor
# ---------------------------------------------------------------------------


def test_cancel_token_prevents_unstarted_actions():
    from qitos.engine.cancellation import CancelToken

    rec = _Recorder()
    token = CancelToken()
    tools = {
        "safe_a": TimelineTool("safe_a", rec, concurrency_safe=True, delay=0.01),
        "exclusive": TimelineTool("exclusive", rec, delay=0.01),
    }
    executor = ActionExecutor(
        tool_registry=FakeRegistry(tools),
        policy=ActionExecutionPolicy(mode="parallel"),
        cancel_token=token,
    )
    token.request_cancel("immediate")
    results = executor.execute([Action(name="safe_a"), Action(name="exclusive")])

    assert all(r.status == ActionStatus.CANCELLED for r in results)
    assert results[0].metadata.get("cancel_source") == "cancel_token"
    assert rec.timeline == []


# ---------------------------------------------------------------------------
# 6. Trace metadata
# ---------------------------------------------------------------------------


def test_execution_records_policy_and_concurrency_peak():
    rec = _Recorder()
    tools = {
        "safe_a": TimelineTool("safe_a", rec, concurrency_safe=True, delay=0.02),
        "safe_b": TimelineTool("safe_b", rec, concurrency_safe=True, delay=0.02),
    }
    executor = _executor(tools, mode="parallel", max_concurrency=2)
    results = executor.execute([Action(name="safe_a"), Action(name="safe_b")])

    stats = executor.last_execution_stats
    assert stats["policy"]["mode"] == "parallel"
    assert stats["policy"]["max_concurrency"] == 2
    assert stats["concurrency_peak"] == 2
    for r in results:
        assert r.metadata.get("segment_index") == 0
        assert isinstance(r.metadata.get("started_at"), float)
        assert isinstance(r.metadata.get("ended_at"), float)


# ---------------------------------------------------------------------------
# 7. Engine / AsyncEngine public API
# ---------------------------------------------------------------------------


def test_engine_accepts_action_execution_policy():
    from qitos.core.agent_module import AgentModule
    from qitos.core.state import StateSchema
    from qitos.engine.engine import Engine

    class _Agent(AgentModule):
        name = "policy_agent"

        def init_state(self, task: str, **kwargs: Any) -> StateSchema:
            return StateSchema(task=task)

        def reduce(self, state, observation, decision):
            return state

    policy = ActionExecutionPolicy(mode="parallel", max_concurrency=3)
    engine = Engine(agent=_Agent(), action_execution_policy=policy)

    assert engine.executor is not None
    assert engine.executor.policy is policy


def test_policy_survives_handoff_executor_rebuild():
    from qitos.core.agent_module import AgentModule
    from qitos.core.state import StateSchema
    from qitos.core.tool_registry import ToolRegistry
    from qitos.engine.engine import Engine

    class _Agent(AgentModule):
        name = "policy_agent"

        def init_state(self, task: str, **kwargs: Any) -> StateSchema:
            return StateSchema(task=task)

        def reduce(self, state, observation, decision):
            return state

    policy = ActionExecutionPolicy(mode="parallel", max_concurrency=3)
    engine = Engine(agent=_Agent(), action_execution_policy=policy)

    # Simulate the handoff rebuild path.
    engine.tool_registry = ToolRegistry()
    rebuilt = engine._build_action_executor(engine.tool_registry)

    assert rebuilt is not None
    assert rebuilt.policy is policy
    assert rebuilt._engine is engine


def test_engine_exposes_public_cancel():
    from qitos.core.agent_module import AgentModule
    from qitos.core.state import StateSchema
    from qitos.engine.engine import Engine

    class _Agent(AgentModule):
        name = "cancel_agent"

        def init_state(self, task: str, **kwargs: Any) -> StateSchema:
            return StateSchema(task=task)

        def reduce(self, state, observation, decision):
            return state

    engine = Engine(agent=_Agent())
    engine.cancel()
    assert engine._cancel_token.is_cancel_requested

    # Idempotent
    engine.cancel()
    assert engine._cancel_token.is_cancel_requested


def test_async_engine_exposes_public_cancel():
    from qitos.core.agent_module import AgentModule
    from qitos.core.state import StateSchema
    from qitos.engine.async_engine import AsyncEngine

    class _Agent(AgentModule):
        name = "cancel_agent"

        def init_state(self, task: str, **kwargs: Any) -> StateSchema:
            return StateSchema(task=task)

        def reduce(self, state, observation, decision):
            return state

    async_engine = AsyncEngine(
        agent=_Agent(),
        action_execution_policy=ActionExecutionPolicy(mode="parallel"),
    )
    assert async_engine.engine.executor.policy.mode == "parallel"

    async_engine.cancel()
    assert async_engine.engine._cancel_token.is_cancel_requested
