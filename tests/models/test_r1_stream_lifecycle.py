"""Real adapter regressions with only the SDK transport replaced."""
from types import SimpleNamespace as NS

import pytest

from qitos.models.codec import ProviderFailure
from qitos.models.openai import OpenAIModel, OpenAICompatibleModel


def chunk(text='', finish=None, usage=None):
    return NS(choices=[NS(delta=NS(content=text, tool_calls=None),
                          finish_reason=finish)], usage=usage)


class Stream:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.closed = 0

    def __iter__(self):
        return self

    def __next__(self):
        return next(self.chunks)

    def close(self):
        self.closed += 1


@pytest.fixture(params=[OpenAIModel, OpenAICompatibleModel])
def adapter(request):
    return request.param(model='offline', api_key='offline', base_url='https://offline.invalid/v1', max_tokens=10240)


def sdk(monkeypatch, chunks):
    import openai
    stream = Stream(chunks)
    calls = []
    client = NS(closed=0)

    def close():
        client.closed += 1

    def create(**kwargs):
        calls.append(kwargs)
        return stream

    client.close = close
    client.chat = NS(completions=NS(create=create))
    monkeypatch.setattr(openai, 'OpenAI', lambda **kw: client)
    return stream, client, calls


def test_construction_failure_is_not_answer(monkeypatch, adapter):
    import openai

    def fail(**kwargs):
        raise ConnectionError('private endpoint credential')

    monkeypatch.setattr(openai, 'OpenAI', fail)
    deltas = []
    with pytest.raises(ProviderFailure) as caught:
        adapter.qitos_stream_transport({'messages': []}, on_delta=deltas.append)
    assert caught.value.category == 'connection'
    assert caught.value.provider_request_sent is False
    assert deltas == []
    assert 'private' not in str(caught.value)


def test_eof_is_failure(monkeypatch, adapter):
    stream, client, _ = sdk(monkeypatch, [chunk('partial')])
    deltas = []
    with pytest.raises(ProviderFailure) as caught:
        adapter.qitos_stream_transport({'messages': []}, on_delta=deltas.append)
    assert caught.value.redacted_details['partial_text_characters'] == len('partial')
    assert caught.value.redacted_details['transport_attempts'] == 1
    assert deltas == ['partial']
    assert stream.closed == client.closed == 1


def test_late_usage_and_finish(monkeypatch, adapter):
    usage = NS(prompt_tokens=2, completion_tokens=3, total_tokens=5)
    stream, client, calls = sdk(monkeypatch, [
        chunk('Error: ordinary model text'), chunk(finish='length'),
        NS(choices=[], usage=usage), NS(choices=[], usage=usage),
    ])
    response = adapter.qitos_stream_transport({
        'messages': [], 'options': {'chat_template_kwargs': {'x': True}},
    })
    assert response.text == 'Error: ordinary model text'
    assert response.finish_reason == 'length'
    assert response.usage['total_tokens'] == 5
    assert calls[0]['max_tokens'] == 10240
    assert 'chat_template_kwargs' not in calls[0]
    assert calls[0]['extra_body']['chat_template_kwargs'] == {'x': True}
    assert stream.closed == client.closed == 1


def test_close_cleans_owned_resources(monkeypatch, adapter):
    stream, client, _ = sdk(monkeypatch, [chunk('partial'), chunk(finish='stop')])
    iterator = adapter.stream([])
    assert next(iterator).text == 'partial'
    iterator.close()
    assert stream.closed == client.closed == 1


@pytest.mark.parametrize('tail', [chunk('late'), chunk(finish='length')])
def test_conflicting_terminal(monkeypatch, adapter, tail):
    sdk(monkeypatch, [chunk(finish='stop'), tail])
    with pytest.raises(ProviderFailure):
        adapter.qitos_stream_transport({'messages': []})


@pytest.mark.parametrize('events', [[], [NS(type='response.failed', error='private')]])
def test_responses_missing_success(monkeypatch, events):
    import openai
    model = OpenAIModel(model='offline', api_key='offline', api_mode='responses')
    stream = Stream(events)
    client = NS(responses=NS(create=lambda **kw: stream), close=lambda: None)
    monkeypatch.setattr(openai, 'OpenAI', lambda **kw: client)
    with pytest.raises(ProviderFailure):
        model.qitos_stream_transport({'messages': []})
    assert stream.closed == 1


@pytest.mark.parametrize('compatible', [False, True])
def test_async_stream_close_and_usage(monkeypatch, compatible):
    import asyncio
    import openai
    from qitos.models.openai import AsyncOpenAIModel, AsyncOpenAICompatibleModel
    model = (AsyncOpenAICompatibleModel if compatible else AsyncOpenAIModel)(
        model='offline', api_key='offline', base_url='https://offline.invalid/v1', max_tokens=16384,
    )
    resources = []

    class AsyncStream(Stream):
        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self.chunks)
            except StopIteration:
                raise StopAsyncIteration

        async def close(self):
            self.closed += 1

    class Client:
        def __init__(self, **kw):
            self.closed = 0
            self.chat = NS(completions=self)
            resources.append(self)

        async def create(self, **kw):
            stream = AsyncStream([chunk('text'), chunk(finish='stop')])
            resources.append(stream)
            return stream

        async def close(self):
            self.closed += 1

    monkeypatch.setattr(openai, 'AsyncOpenAI', Client)

    async def run():
        iterator = model.astream([])
        assert (await anext(iterator)).text == 'text'
        await iterator.aclose()
        chunks = [item async for item in model.astream([])]
        assert sum(item.done for item in chunks) == 1
        assert chunks[-1].usage is None

    asyncio.run(run())
    assert all(resource.closed == 1 for resource in resources)


@pytest.mark.parametrize('status,category', [(429, 'rate_limit'), (401, 'authentication'),
                                          (403, 'authentication'), (503, 'provider_server')])
def test_stream_status_failure_once(monkeypatch, adapter, status, category):
    import openai
    attempts = []
    closed = []

    def create(**kwargs):
        attempts.append(kwargs)
        error = RuntimeError('private')
        error.status_code = status
        raise error

    client = NS(chat=NS(completions=NS(create=create)), close=lambda: closed.append(True))
    monkeypatch.setattr(openai, 'OpenAI', lambda **kw: client)
    with pytest.raises(ProviderFailure) as caught:
        list(adapter.stream([]))
    assert caught.value.category == category
    assert caught.value.provider_request_sent is True
    assert len(attempts) == len(closed) == 1


def test_callback_failure_closes_stream(monkeypatch, adapter):
    stream, client, _ = sdk(monkeypatch, [chunk('partial'), chunk(finish='stop')])

    def fail(text):
        raise RuntimeError('consumer')

    with pytest.raises(RuntimeError, match='consumer'):
        adapter.qitos_stream_transport({'messages': []}, on_delta=fail)
    assert stream.closed == client.closed == 1


@pytest.mark.parametrize('finished', [False, True])
def test_partial_tool_input_never_executes(monkeypatch, adapter, finished):
    tool = NS(index=0, id='call', function=NS(name='add', arguments='{"a":2'))
    values = [NS(choices=[NS(delta=NS(content=None, tool_calls=[tool]), finish_reason=None)], usage=None)]
    if finished:
        values.append(chunk(finish='tool_calls'))
    stream, client, _ = sdk(monkeypatch, values)
    with pytest.raises(ProviderFailure):
        adapter.qitos_stream_transport({'messages': []})
    assert stream.closed == client.closed == 1


@pytest.mark.parametrize('compatible', [False, True])
def test_async_consumer_cancellation(monkeypatch, compatible):
    import asyncio
    import openai
    from qitos.models.openai import AsyncOpenAIModel, AsyncOpenAICompatibleModel

    async def run():
        entered = asyncio.Event()
        closed = []

        class Response:
            def __aiter__(self):
                return self

            async def __anext__(self):
                entered.set()
                await asyncio.Event().wait()

            async def close(self):
                closed.append('response')

        class Client:
            def __init__(self, **kw):
                self.chat = NS(completions=self)

            async def create(self, **kw):
                return Response()

            async def close(self):
                closed.append('client')

        monkeypatch.setattr(openai, 'AsyncOpenAI', Client)
        model = (AsyncOpenAICompatibleModel if compatible else AsyncOpenAIModel)(
            model='offline', api_key='offline', base_url='https://offline.invalid')

        async def consume():
            return [item async for item in model.astream([])]

        task = asyncio.create_task(consume())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert closed == ['response', 'client']

    asyncio.run(run())


@pytest.mark.parametrize('refusal', [False, True])
def test_responses_completion_and_refusal(monkeypatch, refusal):
    import openai
    model = OpenAIModel(model='offline', api_key='offline', api_mode='responses')
    item = {'type': 'function_call', 'id': 'item', 'call_id': 'one', 'name': 'add',
            'arguments': '{"a":2}', 'status': 'completed'}
    response = {'status': 'completed', 'output': [item],
                'usage': {'input_tokens': 2, 'output_tokens': 3, 'total_tokens': 5}}
    values = ([NS(type='response.refusal.delta', delta='private')]
              if refusal else [NS(type='response.output_item.done', item=item),
                               NS(type='response.completed', response=response),
                               NS(type='response.completed', response=response)])
    stream = Stream(values)
    closed = []
    monkeypatch.setattr(openai, 'OpenAI', lambda **kw: NS(
        responses=NS(create=lambda **kw: stream), close=lambda: closed.append(True)))
    if refusal:
        with pytest.raises(ProviderFailure) as caught:
            model.qitos_stream_transport({'messages': []})
        assert caught.value.category == 'provider_refusal'
    else:
        result = model.qitos_stream_transport({'messages': []})
        assert result.finish_reason == 'completed'
        assert len(result.native_items) == len(result.tool_calls) == 1
        assert result.usage['total_tokens'] == 5
    assert stream.closed == 1 and closed == [True]
