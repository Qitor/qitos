"""Async Engine for non-blocking AgentModule execution."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, AsyncIterator, Generic, List, Optional, TypeVar

from ..core.agent_module import AgentModule
from ..core.state import StateSchema
from .engine import Engine, EngineResult
from .events import EngineEvent, EngineEventType, EventStream
from .hooks import HookContext
from .states import RuntimeEvent, RuntimePhase, StepRecord
from .stream.transformer import StreamTransformer, TransformerChain, TransformerOutput

StateT = TypeVar("StateT", bound=StateSchema)
ObservationT = TypeVar("ObservationT")
ActionT = TypeVar("ActionT")


class AsyncEngine(Generic[StateT, ObservationT, ActionT]):
    """Async execution kernel for AgentModule workflows.

    Provides the same interface as Engine but with async execution:
    - ``await async_engine.arun(task)`` returns EngineResult
    - ``async for event in async_engine.arun_stream(task)`` yields EngineEvents

    Internally delegates to a sync Engine but runs blocking calls in a
    thread pool, and optionally uses Model.acall() when available.
    """

    def __init__(
        self,
        agent: AgentModule[StateT, ObservationT, ActionT],
        **engine_kwargs: Any,
    ):
        self._engine = Engine(agent=agent, **engine_kwargs)
        self.agent = self._engine.agent
        self.event_stream: Optional[EventStream] = None
        self._workers: set[asyncio.Task[Any]] = set()
        self._active_hook: Optional[_StreamBridgeHook] = None

    def _track_worker(self, task: asyncio.Task[Any]) -> None:
        # A cancelled consumer cannot stop Python code already in the thread.
        # Retain ownership until the worker has actually finished.
        self._workers.add(task)

        def finished(done: asyncio.Task[Any]) -> None:
            self._workers.discard(done)
            if not done.cancelled():
                done.exception()

        task.add_done_callback(finished)

    @property
    def engine(self) -> Engine[StateT, ObservationT, ActionT]:
        return self._engine

    async def arun(self, task: str, **kwargs: Any) -> EngineResult[StateT]:
        """Run the agent loop asynchronously, returning the final result.

        This executes the sync Engine.run() in a thread pool to avoid
        blocking the event loop.

        If the awaiting task is cancelled, the same cancellation signal is
        propagated to the underlying Engine. Note that a sync tool already
        executing inside the worker thread cannot be forcibly killed by
        Python; it is asked to stop and drains on its own.
        """
        run_task = asyncio.ensure_future(
            asyncio.to_thread(self._engine.run, task, **kwargs)
        )
        self._track_worker(run_task)
        try:
            return await asyncio.shield(run_task)
        except asyncio.CancelledError:
            self.cancel("immediate")
            raise

    def cancel(self, mode: str = "immediate") -> None:
        """Request cancellation of the in-flight run.

        Thread-safe, idempotent, and usable after the run has started.
        Delegates to the underlying Engine's cancellation token.
        """
        self._engine.cancel(mode)

    async def arun_stream(
        self,
        task: str,
        *,
        transformers: Optional[List[StreamTransformer]] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[EngineEvent | TransformerOutput, None]:
        """Run the agent loop and yield structured events as they occur.

        A sync Engine runs in a thread pool. Engine hooks bridge events
        into the EventStream for async consumption.

        Parameters
        ----------
        task : str
            The task to execute.
        transformers : list of StreamTransformer, optional
            If provided, each event is passed through the transformer chain
            and TransformerOutput values are yielded instead of raw events.
            Events that produce no TransformerOutput are suppressed.
        """
        stream = EventStream()
        self.event_stream = stream
        chain = TransformerChain(transformers) if transformers else None

        hook = _StreamBridgeHook(stream)
        self._active_hook = hook
        self._engine.hooks.append(hook)

        if chain:
            chain.on_run_start()

        def _run() -> EngineResult[StateT]:
            try:
                return self._engine.run(task, **kwargs)
            finally:
                stream.close()

        run_task = asyncio.ensure_future(asyncio.to_thread(_run))
        self._track_worker(run_task)

        try:
            async for event in stream:
                if chain:
                    outputs = await chain.aprocess(event)
                    for output in outputs:
                        yield output
                else:
                    yield event
            await asyncio.shield(run_task)
        finally:
            try:
                if chain:
                    chain.on_run_end()
            finally:
                self._engine.hooks = [
                    h for h in self._engine.hooks if h is not hook
                ]
                self._active_hook = None
                self.event_stream = None
                if not run_task.done():
                    self.cancel("immediate")
                    stream.close()

    def run(self, task: str, **kwargs: Any) -> EngineResult[StateT]:
        """Synchronous run (delegates to underlying Engine)."""
        return self._engine.run(task, **kwargs)

    async def arun_stream_tokens(
        self, task: str, **kwargs: Any
    ) -> AsyncIterator[EngineEvent]:
        """Run the agent loop with token-level streaming.

        Yields EngineEvents including STEP_STREAM events that carry
        ModelStreamChunk payloads for real-time token display.

        Falls back to arun_stream() if the model does not support streaming.
        """
        capabilities = getattr(getattr(self.agent, "llm", None), "qitos_provider_capabilities", None)
        native_stream = not callable(capabilities) or capabilities().get("supports_streaming", False)
        previous_callback = self._engine.stream_callback

        def on_delta(text: str) -> None:
            stream = self.event_stream
            if stream is not None:
                stream.emit_sync(EngineEvent(
                    event_type=EngineEventType.STEP_STREAM,
                    step_id=self._active_hook.step_id if self._active_hook else 0,
                    phase=RuntimePhase.DECIDE, payload={"text": text},
                ))

        if native_stream:
            self._engine.stream_callback = on_delta
        iterator = self.arun_stream(task, **kwargs)
        try:
            async for item in iterator:
                if isinstance(item, EngineEvent):
                    yield item
        finally:
            await iterator.aclose()
            self._engine.stream_callback = previous_callback


class _StreamBridgeHook:
    """Engine hook that bridges RuntimeEvents into an EventStream."""

    def __init__(self, stream: EventStream) -> None:
        self._stream = stream
        self.step_id = 0

    def on_run_start(self, task: str, state: Any, engine: Engine) -> None:
        self._stream.emit_sync(
            EngineEvent(
                event_type=EngineEventType.RUN_START,
                payload={"task": task},
            )
        )

    def on_run_end(self, result: EngineResult, engine: Engine) -> None:
        self._stream.emit_sync(
            EngineEvent(
                event_type=EngineEventType.RUN_END,
                step_id=result.step_count,
                payload={
                    "step_count": result.step_count,
                    "runtime_seconds": result.runtime_seconds,
                    "total_tokens": result.total_tokens,
                    "stop_reason": result.state.stop_reason
                    if result.state
                    else None,
                },
            )
        )

    def on_before_step(self, ctx: HookContext, engine: Engine) -> None:
        agent_id = getattr(ctx.record, "agent_id", None) if ctx.record else None
        self._stream.emit_sync(
            EngineEvent(
                event_type=EngineEventType.STEP_START,
                step_id=ctx.step_id,
                agent_id=agent_id,
                phase=ctx.phase,
                payload={"phase": ctx.phase.value if ctx.phase else None},
            )
        )

    def on_after_step(self, ctx: HookContext, engine: Engine) -> None:
        agent_id = getattr(ctx.record, "agent_id", None) if ctx.record else None
        self._stream.emit_sync(
            EngineEvent(
                event_type=EngineEventType.STEP_END,
                step_id=ctx.step_id,
                agent_id=agent_id,
                phase=ctx.phase,
                payload={
                    "phase": ctx.phase.value if ctx.phase else None,
                    "stop_reason": ctx.stop_reason,
                },
            )
        )

    def on_before_decide(self, ctx: HookContext, engine: Engine) -> None:
        self.step_id = ctx.step_id
        self._stream.emit_sync(
            EngineEvent(
                event_type=EngineEventType.DECIDE,
                step_id=ctx.step_id,
                phase=RuntimePhase.DECIDE,
                payload={"stage": "start"},
            )
        )

    def on_after_decide(self, ctx: HookContext, engine: Engine) -> None:
        mode = None
        if ctx.decision is not None:
            mode = getattr(ctx.decision, "mode", None)
        self._stream.emit_sync(
            EngineEvent(
                event_type=EngineEventType.DECIDE,
                step_id=ctx.step_id,
                phase=RuntimePhase.DECIDE,
                payload={"stage": "end", "mode": mode},
            )
        )

    def on_before_act(self, ctx: HookContext, engine: Engine) -> None:
        self._stream.emit_sync(
            EngineEvent(
                event_type=EngineEventType.ACT,
                step_id=ctx.step_id,
                phase=RuntimePhase.ACT,
                payload={"stage": "start"},
            )
        )

    def on_after_act(self, ctx: HookContext, engine: Engine) -> None:
        self._stream.emit_sync(
            EngineEvent(
                event_type=EngineEventType.ACT,
                step_id=ctx.step_id,
                phase=RuntimePhase.ACT,
                payload={"stage": "end"},
            )
        )

    def on_event(
        self, event: RuntimeEvent, state: Any, record: Optional[StepRecord], engine: Engine
    ) -> None:
        phase_val = getattr(event, "phase", None)
        phase_str = phase_val.value if phase_val else ""
        event_type = EngineEventType.PHASE_END

        if "HANDOFF" in phase_str:
            event_type = EngineEventType.HANDOFF
        elif "DELEGATE" in phase_str:
            event_type = EngineEventType.DELEGATE
        elif "FANOUT" in phase_str:
            event_type = EngineEventType.FANOUT

        agent_id = getattr(record, "agent_id", None) if record else None
        self._stream.emit_sync(
            EngineEvent(
                event_type=event_type,
                step_id=getattr(event, "step_id", 0),
                agent_id=agent_id,
                phase=phase_val,
                ok=getattr(event, "ok", True),
                payload=getattr(event, "payload", {}) or {},
                error=getattr(event, "error", None),
            )
        )


__all__ = ["AsyncEngine"]
