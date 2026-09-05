"""Offline installed-wheel mechanism proof; no model capability claim."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace as NS
from unittest.mock import patch

from qitos.config import FakeCredentialResolver, load_agent_config, build_agent_composition
from qitos.core.conversation import ExchangeLog
from qitos.core.function_tool_decorator import function_tool
from qitos.tracing.journal_store import JournalTrajectoryStore


def run(interrupted=False):
    second_finished = Event()
    completions = []
    executions = []
    requests = []
    resources = []

    @function_tool(read_only=True, concurrency_safe=True)
    def add(a: int, b: int) -> int:
        """Add two integers."""
        executions.append(('add', a, b))
        if (a, b) == (2, 3):
            assert second_finished.wait(5)
        return a + b

    @function_tool(read_only=True, concurrency_safe=True)
    def multiply(a: int, b: int) -> int:
        """Multiply two integers."""
        executions.append(('multiply', a, b))
        return a * b

    class CompletionHook:
        def on_event(self, event, state, record, engine):
            if event.payload.get('stage') == 'tool_slot_terminal':
                name = event.payload['tool_result']['tool_name']
                completions.append(name)
                if name == 'multiply':
                    second_finished.set()

    def chunk(text='', calls=None, finish=None):
        return NS(choices=[NS(delta=NS(content=text, tool_calls=calls),
                              finish_reason=finish)], usage=None)

    def call(index, identifier, name, arguments):
        return NS(index=index, id=identifier, type='function',
                  function=NS(name=name, arguments=arguments))

    class Stream:
        def __init__(self, values):
            self.values = iter(values)
            self.closed = 0
            resources.append(self)

        def __iter__(self):
            return self

        def __next__(self):
            return next(self.values)

        def close(self):
            self.closed += 1

    class Client:
        def __init__(self, **kwargs):
            assert kwargs['max_retries'] == 0
            self.closed = 0
            self.chat = NS(completions=self)
            resources.append(self)

        def create(self, **kwargs):
            assert kwargs['stream'] is True
            assert kwargs['max_tokens'] == 10240
            requests.append(kwargs)
            results = {m['tool_call_id']: json.loads(m['content'])
                       for m in kwargs['messages'] if m['role'] == 'tool'}
            if len(requests) == 1:
                return Stream([chunk(calls=[call(0, 'one', 'add', '{"a":2,"b":3}'),
                                             call(1, 'two', 'multiply', '{"a":2,"b":3}')]),
                               chunk(finish='tool_calls')])
            if len(requests) == 2:
                assert results == {'one': 5, 'two': 6}, results
                values = [chunk(calls=[call(0, 'three', 'add', '{"a":5,"b":6}' if not interrupted else '{"a":5')])]
                if not interrupted:
                    values.append(chunk(finish='tool_calls'))
                return Stream(values)
            assert len(requests) == 3
            assert results['three'] == 11
            return Stream([chunk('{"final_answer":"11"}'), chunk(finish='stop')])

        def close(self):
            self.closed += 1

    with TemporaryDirectory(prefix='qitos-r1-consumer-') as directory:
        root = Path(directory)
        path = root / 'agent.yaml'
        journal = root / 'trajectory.journal'
        path.write_text(f'''schema: qitos.agent
agent:
  name: offline-multi-round
  protocol: json_decision_multi_v1
  parser: auto
model:
  provider: openai_compatible
  model: offline
  base_url: https://offline.invalid/v1
  credential:
    ref: offline
  request:
    max_tokens: 10240
    retries: 0
tools:
  preset: none
  policy: auto
runtime:
  environment:
    type: unsafe_host
    workspace: {root}
  session:
    enabled: true
    store: memory
  trajectory:
    enabled: true
    output: {journal}
    privacy: private
budgets:
  max_steps: 5
  max_requests: 3
''')
        with patch.dict(sys.modules, {'openai': NS(OpenAI=Client, APIConnectionError=ConnectionError, APITimeoutError=TimeoutError)}):
            with build_agent_composition(load_agent_config(path),
                                         credential_resolver=FakeCredentialResolver()) as composition:
                composition.tool_registry.register(add)
                composition.tool_registry.register(multiply)
                composition.engine.hooks.append(CompletionHook())
                composition.engine.stream_callback = lambda text: None
                session = composition.session('Compute add(2,3) and multiply(2,3), then add their results.')
                result = session.run()
                inspection = session.inspect()
                assert inspection.budget['model_requests_consumed'] == len(requests)
                snapshot = composition.runtime.checkpoint_store.get_session_snapshot(
                    session.current_head.snapshot_id.value)
                conversation = next(c for c in snapshot.payload['components'] if c['slot'] == 'conversation')
                log = ExchangeLog.from_dict(conversation['payload']['exchange_log'])
                assert log.open_batch_id() is None
                batches = [item.batch_id for item in log.items if getattr(item, 'batch_id', None)
                           and getattr(item, 'tool_calls', None)]
                assert len(batches) == (1 if interrupted else 2)
                for batch in batches:
                    calls = log.declared_calls(batch)
                    terminals = log.results_for_batch(batch)
                    assert len(calls) == len(terminals)
                    assert len({item.identity.key() for item in terminals}) == len(calls)
                    ordered = log.results_for_batch_in_declaration_order(batch)
                    assert [item.identity for item in ordered] == [item.identity for item in calls]
                assert [item.identity.call_id for item in log.results_for_batch(batches[0])] == ['two', 'one']
                assert completions[:2] == ['multiply', 'add']
                assert len(completions) == len(executions)
                assert len(executions) == (2 if interrupted else 3)
                assert len(requests) == (2 if interrupted else 3)
                if interrupted:
                    assert ('add', 5, 6) not in executions
                    assert result.error_code == 'provider_stream_protocol_error'
                    assert result.state.final_result is None
                else:
                    assert str(result.state.final_result) == '11', result
                session_id = session.session_id.value
                run_id = session.run_id.value
        store = JournalTrajectoryStore(journal, read_only=True)
        trajectory = store.read_session(session_id)
        assert trajectory.records
        assert all(record.session_id == session_id for record in trajectory.records)
        assert all(record.run_id == run_id for record in trajectory.records)
        assert all(resource.closed == 1 for resource in resources)
        return {'interrupted': interrupted, 'requests': len(requests),
                'executions': len(executions), 'completion_order': completions,
                'final': result.state.final_result}


if __name__ == '__main__':
    print(json.dumps([run(), run(interrupted=True)], ensure_ascii=False))
