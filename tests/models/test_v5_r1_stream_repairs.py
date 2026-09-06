"""R1-M1/M2: real Chat adapters, synthetic SDK I/O only."""

import asyncio
import json
from types import SimpleNamespace as NS

import pytest

from qitos.models.codec import ProviderFailure
from qitos.models.openai import OpenAICompatibleModel, AsyncOpenAICompatibleModel


PRIVATE = "SYNTHETIC_PRIVATE_MARKER https://private.invalid Authorization token /private/host"


def chunk(text="", reasoning=None, finish=None, calls=None, usage=None):
    return NS(
        choices=[
            NS(delta=NS(content=text, reasoning_content=reasoning, tool_calls=calls), finish_reason=finish)
        ],
        usage=usage,
    )


class SDKStream:
    def __init__(self, items, close_error=False):
        self.items = iter(items)
        self.closed = 0
        self.close_error = close_error

    def __iter__(self):
        return self

    def __next__(self):
        item = next(self.items)
        if isinstance(item, BaseException):
            raise item
        return item

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self)
        except StopIteration:
            raise StopAsyncIteration from None

    def close(self):
        self.closed += 1
        if self.close_error:
            raise RuntimeError(PRIVATE)

    async def aclose(self):
        self.close()


def adapter(monkeypatch, items, *, asynchronous=False, response_error=False, client_error=False):
    import openai

    stream = SDKStream(items, response_error)
    client = SDKStream([], client_error)

    async def create_async(**kwargs):
        return stream

    client.chat = NS(completions=NS(create=create_async if asynchronous else lambda **kw: stream))
    monkeypatch.setattr(openai, "AsyncOpenAI" if asynchronous else "OpenAI", lambda **kw: client)
    cls = AsyncOpenAICompatibleModel if asynchronous else OpenAICompatibleModel
    return (
        cls(model="offline", api_key="offline", base_url="https://offline.invalid/v1", max_tokens=10240),
        stream,
        client,
    )


@pytest.mark.parametrize("answer", ["", "answer"])
@pytest.mark.parametrize("asynchronous", [False, True])
def test_reasoning_fragments_separate_once(monkeypatch, answer, asynchronous):
    model, stream, client = adapter(
        monkeypatch,
        [chunk(reasoning="first "), chunk(reasoning="second"), chunk(answer), chunk(finish="stop")],
        asynchronous=asynchronous,
    )
    if asynchronous:

        async def consume():
            return [item async for item in model.astream([])]

        chunks = asyncio.run(consume())
        assert "".join(c.text for c in chunks) == answer
        assert chunks[-1].reasoning_fields == {"reasoning_content": "first second"}
        assert not any(c.reasoning_fields for c in chunks[:-1])
    else:
        response = model.qitos_stream_transport({"messages": []})
        assert response.text == answer
        assert response.reasoning_fields == {"reasoning_content": "first second"}
        assert response.reasoning_content == "first second"
    assert stream.closed == client.closed == 1


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("mode", ["normal", "eof", "transport", "contradiction"])
@pytest.mark.parametrize("response_error,client_error", [(True, False), (False, True), (True, True)])
def test_cleanup_priority(monkeypatch, asynchronous, mode, response_error, client_error):
    usage = NS(prompt_tokens=2, completion_tokens=3, total_tokens=5)
    events = [chunk("partial", usage=usage)]
    events += {
        "normal": [chunk(finish="stop")],
        "eof": [],
        "transport": [ConnectionError(PRIVATE)],
        "contradiction": [chunk(finish="stop"), chunk("late")],
    }[mode]
    model, stream, client = adapter(
        monkeypatch,
        events,
        asynchronous=asynchronous,
        response_error=response_error,
        client_error=client_error,
    )
    with pytest.raises(ProviderFailure) as caught:
        if asynchronous:

            async def consume():
                return [item async for item in model.astream([])]

            asyncio.run(consume())
        else:
            model.qitos_stream_transport({"messages": []})
    error = caught.value
    assert error.category == (
        "provider_exception" if mode == "normal" else "connection" if mode == "transport" else "stream"
    )
    assert error.provider_request_sent
    assert error.redacted_details["cleanup_failures"] == int(response_error) + int(client_error)
    assert error.redacted_details["partial_text_characters"] == 7
    assert error.redacted_details["usage"]["total_tokens"] == 5
    assert stream.closed == client.closed == 1
    public = str(error) + json.dumps(error.to_dict())
    for marker in ["SYNTHETIC_PRIVATE_MARKER", "private.invalid", "Authorization", "/private/host"]:
        assert marker not in public


def test_consumer_exception_identity_survives_cleanup(monkeypatch):
    model, stream, client = adapter(monkeypatch, [chunk("partial")], response_error=True, client_error=True)
    original = ValueError("consumer failed")

    def callback(text):
        raise original

    with pytest.raises(ValueError) as caught:
        model.qitos_stream_transport({"messages": []}, on_delta=callback)
    assert caught.value is original
    assert stream.closed == client.closed == 1
    assert "cleanup" in str(original.__notes__)


@pytest.mark.parametrize("asynchronous", [False, True])
def test_explicit_close_failure_is_typed(monkeypatch, asynchronous):
    model, stream, client = adapter(
        monkeypatch, [chunk("partial")], asynchronous=asynchronous, response_error=True, client_error=True
    )
    with pytest.raises(ProviderFailure):
        if asynchronous:

            async def consume():
                iterator = model.astream([])
                await anext(iterator)
                await iterator.aclose()

            asyncio.run(consume())
        else:
            iterator = model.stream([])
            next(iterator)
            iterator.close()
    assert stream.closed == client.closed == 1


def test_reasoning_tools_canonical_reread_and_capability_loss(monkeypatch):
    from dataclasses import replace
    from qitos.core.conversation import ExchangeLog, UserItem, ToolResultItem
    from qitos.core.multimodal import ContentBlock
    from qitos.core.request_view import RequestView, RequestTarget
    from qitos.core.tool_result import ToolResult
    from qitos.models.provider import execute_provider_request
    from qitos.models.codec import ProviderCapabilities, CodecError

    call = NS(index=0, id="first", function=NS(name="lookup", arguments="{}"))
    model, _, _ = adapter(
        monkeypatch,
        [chunk(reasoning="plan "), chunk(reasoning="one", calls=[call]), chunk(finish="tool_calls")],
    )
    target = RequestTarget.from_model(model)
    log = ExchangeLog("reasoning-log")
    log.append(UserItem("u1", "e1", [ContentBlock(type="text", text="start")]))
    request = RequestView.from_exchange_log(log, target=target)
    tx = execute_provider_request(model, request, stream_callback=lambda text: None)
    assert tx.model_response.text == ""
    batch = log.append(tx.assistant_item)
    assert batch is not None
    call = tx.assistant_item.tool_calls()[0]
    batch.record_result(
        ToolResultItem(
            "result1",
            tx.assistant_item.exchange_id,
            call.identity,
            call.batch_id,
            ToolResult(status="success", output="ok"),
        )
    )
    log = ExchangeLog.from_dict(log.to_persistence_dict())
    next_view = RequestView.from_exchange_log(log, target=target)
    reason = [
        part
        for item in next_view.selected_items
        if item["kind"] == "assistant"
        for part in item["parts"]
        if part["kind"] == "reasoning_block"
    ]
    assert len(reason) == 1 and reason[0]["summary"] == "plan one"
    codec = model.qitos_provider_codec()
    capabilities = ProviderCapabilities.from_model(model)
    with pytest.raises(CodecError):
        codec.encode(next_view, capabilities=capabilities)
    payload, report = codec.encode(next_view, capabilities=capabilities, allow_loss=True)
    assert "assistant.reasoning" in report.lossy_fields
    assert "plan one" not in json.dumps(payload)
    supported = replace(
        capabilities,
        supports_reasoning_input=True,
        supports_reasoning_output=True,
        supported_features=(*capabilities.supported_features, "reasoning"),
        reasoning_modes=("preserve_if_supported", "drop"),
    )
    payload, report = codec.encode(next_view, capabilities=supported)
    assert report.reasoning == "preserved"
    assert payload["messages"][1]["reasoning_content"] == "plan one"
    assert not payload["messages"][1]["content"]


def test_async_cancellation_retains_identity_and_cleans_both(monkeypatch):
    async def scenario():
        entered = asyncio.Event()
        release = asyncio.Event()
        model, stream, client = adapter(
            monkeypatch, [], asynchronous=True, response_error=True, client_error=True
        )

        async def wait_for_response(**kwargs):
            entered.set()
            await release.wait()
            return stream

        # Cancel while reading an already-owned response, not before creation.
        async def wait_next(self):
            entered.set()
            await release.wait()
            raise StopAsyncIteration

        monkeypatch.setattr(SDKStream, "__anext__", wait_next)

        async def consume():
            return [item async for item in model.astream([])]

        task = asyncio.create_task(consume())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError) as caught:
            await task
        assert stream.closed == client.closed == 1
        assert caught.value.__notes__ == ["provider_cleanup_failures=2"]

    asyncio.run(scenario())


def test_responses_helper_borrows_client_and_preserves_primary(monkeypatch):
    from qitos.models._openai_responses import _responses_stream

    model, stream, client = adapter(monkeypatch, [], response_error=True, client_error=True)
    client.responses = NS(create=lambda **kwargs: stream)
    with pytest.raises(ProviderFailure) as caught:
        list(_responses_stream(model, client, [], provider="openai-compatible"))
    assert caught.value.category == "stream"
    assert caught.value.redacted_details["cleanup_failures"] == 1
    assert stream.closed == 1 and client.closed == 0


def test_no_reasoning_is_invented(monkeypatch):
    model, _, _ = adapter(monkeypatch, [chunk("answer"), chunk(finish="stop")])
    response = model.qitos_stream_transport({"messages": []})
    assert response.reasoning_fields == {}
    assert response.reasoning_content is None


def test_cancellation_during_cleanup_attempts_remaining_resource(monkeypatch):
    from qitos.models._stream import aclose_owned

    class Resource:
        closed = 0

        async def aclose(self):
            self.closed += 1
            raise asyncio.CancelledError()

    resource = Resource()
    other = SDKStream([], True)

    async def consume():
        with pytest.raises(asyncio.CancelledError) as caught:
            await aclose_owned(resource, other)
        assert caught.value.__notes__ == ["provider_cleanup_failures=2"]

    asyncio.run(consume())
    assert resource.closed == other.closed == 1
