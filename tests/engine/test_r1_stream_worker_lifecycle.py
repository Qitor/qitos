"""A consumer cancellation cannot claim that a running Python worker stopped."""
import asyncio
from threading import Event

import pytest

from qitos.core.agent_module import AgentModule
from qitos.core.decision import Decision
from qitos.core.state import StateSchema
from qitos.engine.async_engine import AsyncEngine


def test_cancelled_async_consumer_retains_worker_owner():
    entered, release = Event(), Event()

    class Agent(AgentModule):
        def init_state(self, task, **kwargs):
            return StateSchema(task=task)

        def decide(self, state, observation):
            entered.set()
            assert release.wait(5)
            return Decision.final('done')

        def reduce(self, state, observation, decision):
            return state

    async def run():
        engine = AsyncEngine(Agent())
        consumer = asyncio.create_task(engine.arun('controlled worker'))
        assert await asyncio.to_thread(entered.wait, 5)
        consumer.cancel()
        try:
            with pytest.raises(asyncio.CancelledError):
                await consumer
            assert len(engine._workers) == 1
            assert not next(iter(engine._workers)).done()
        finally:
            release.set()
        await asyncio.gather(*engine._workers)
        await asyncio.sleep(0)
        assert not engine._workers

    asyncio.run(run())
