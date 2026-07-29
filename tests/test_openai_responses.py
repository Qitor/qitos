from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from qitos.core.model_response import ModelResponse
from qitos.models import _openai_responses as responses_module
from qitos.models.openai import (
    AsyncOpenAICompatibleModel,
    OpenAICompatibleModel,
    OpenAIModel,
)


def _response_with_function_calls() -> SimpleNamespace:
    return SimpleNamespace(
        id="resp_29",
        model="gpt-5",
        status="completed",
        previous_response_id=None,
        output_text="",
        output=[
            SimpleNamespace(
                type="reasoning",
                id="rs_1",
                status="completed",
                summary=[{"type": "summary_text", "text": "Need a tool."}],
                encrypted_content="opaque-private-state",
            ),
            SimpleNamespace(
                type="function_call",
                id="fc_1",
                call_id="call_1",
                name="add",
                arguments='{"a":1,"b":2}',
                status="completed",
            ),
            SimpleNamespace(
                type="function_call",
                id="fc_2",
                call_id="call_2",
                name="lookup",
                arguments='{"key":"x"}',
                status="completed",
            ),
        ],
        usage=SimpleNamespace(
            input_tokens=11,
            output_tokens=7,
            total_tokens=18,
            input_tokens_details=SimpleNamespace(cached_tokens=2),
            output_tokens_details=SimpleNamespace(reasoning_tokens=3),
        ),
    )


def test_model_response_summary_redacts_opaque_native_reasoning_state() -> None:
    response = ModelResponse(
        text="",
        native_items=[
            {
                "type": "reasoning",
                "id": "rs_1",
                "status": "completed",
                "summary": [{"type": "summary_text", "text": "Need a tool."}],
                "encrypted_content": "opaque-private-state",
            }
        ],
    )

    summary = response.to_summary_dict()

    assert summary["native_items"] == [
        {
            "type": "reasoning",
            "id": "rs_1",
            "status": "completed",
            "summary": [{"type": "summary_text", "text": "Need a tool."}],
        }
    ]


def test_responses_input_replays_native_items_and_tool_outputs() -> None:
    messages = [
        {"role": "user", "content": "calculate"},
        {
            "role": "assistant",
            "content": None,
            "native_items": [
                {"type": "reasoning", "id": "rs_1", "status": "completed"},
                {
                    "type": "function_call",
                    "id": "fc_1",
                    "call_id": "call_1",
                    "name": "add",
                    "arguments": '{"a":1,"b":2}',
                    "status": "completed",
                },
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "name": "add",
            "content": "3",
        },
    ]

    payload = responses_module._to_responses_input(messages)

    assert payload == [
        {"role": "user", "content": "calculate"},
        {"type": "reasoning", "id": "rs_1", "status": "completed"},
        {
            "type": "function_call",
            "id": "fc_1",
            "call_id": "call_1",
            "name": "add",
            "arguments": '{"a":1,"b":2}',
            "status": "completed",
        },
        {"type": "function_call_output", "call_id": "call_1", "output": "3"},
    ]


def test_responses_tools_flatten_chat_function_schema() -> None:
    tools = [
        {
            "type": "function",
            "function": {
                "name": "add",
                "description": "Add numbers",
                "parameters": {
                    "type": "object",
                    "properties": {"a": {"type": "integer"}},
                },
                "strict": True,
            },
        },
        {"type": "web_search_preview"},
    ]

    assert responses_module._to_responses_tools(tools) == [
        {
            "type": "function",
            "name": "add",
            "description": "Add numbers",
            "parameters": {
                "type": "object",
                "properties": {"a": {"type": "integer"}},
            },
            "strict": True,
        },
        {"type": "web_search_preview"},
    ]


def test_responses_tool_choice_flattens_forced_function() -> None:
    assert responses_module._to_responses_tool_choice(
        {"type": "function", "function": {"name": "add"}}
    ) == {"type": "function", "name": "add"}
    assert responses_module._to_responses_tool_choice("required") == "required"


def test_responses_normalization_preserves_order_and_uses_call_id() -> None:
    normalized = responses_module._model_response_from_responses(
        _response_with_function_calls(),
        provider="openai",
    )

    assert normalized.tool_calls == [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "add", "arguments": '{"a":1,"b":2}'},
            "metadata": {"response_item_id": "fc_1", "status": "completed"},
        },
        {
            "id": "call_2",
            "type": "function",
            "function": {"name": "lookup", "arguments": '{"key":"x"}'},
            "metadata": {"response_item_id": "fc_2", "status": "completed"},
        },
    ]
    assert normalized.usage == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
        "input_tokens_details": {"cached_tokens": 2},
        "output_tokens_details": {"reasoning_tokens": 3},
    }
    assert [item["type"] for item in normalized.native_items or []] == [
        "reasoning",
        "function_call",
        "function_call",
    ]


def test_responses_text_output_normalizes_without_tool_calls() -> None:
    response = SimpleNamespace(
        id="resp_text",
        model="gpt-5",
        status="completed",
        previous_response_id=None,
        output_text="hello from responses",
        output=[
            SimpleNamespace(
                type="message",
                id="msg_1",
                role="assistant",
                status="completed",
                content=[
                    SimpleNamespace(
                        type="output_text",
                        text="hello from responses",
                        annotations=[],
                    )
                ],
            )
        ],
        usage=None,
    )

    normalized = responses_module._model_response_from_responses(
        response, provider="openai"
    )

    assert normalized.text == "hello from responses"
    assert normalized.tool_calls is None
    assert normalized.native_items and normalized.native_items[0]["type"] == "message"


def test_responses_normalization_accepts_mapping_contract() -> None:
    normalized = responses_module._model_response_from_responses(
        {
            "id": "resp_mapping",
            "model": "compatible-model",
            "status": "completed",
            "output_text": "",
            "output": [
                {
                    "type": "function_call",
                    "id": "fc_mapping",
                    "call_id": "call_mapping",
                    "name": "lookup",
                    "arguments": '{"key":"value"}',
                    "status": "completed",
                }
            ],
            "usage": {
                "input_tokens": 4,
                "output_tokens": 2,
                "total_tokens": 6,
            },
        },
        provider="openai-compatible",
    )

    assert normalized.model_name == "compatible-model"
    assert normalized.tool_calls and normalized.tool_calls[0]["id"] == "call_mapping"
    assert normalized.usage == {
        "prompt_tokens": 4,
        "completion_tokens": 2,
        "total_tokens": 6,
    }


def test_responses_missing_call_id_is_preserved_but_not_executed() -> None:
    response = SimpleNamespace(
        id="resp_invalid",
        model="gpt-5",
        status="completed",
        previous_response_id=None,
        output_text="",
        output=[
            SimpleNamespace(
                type="function_call",
                id="fc_invalid",
                call_id=None,
                name="add",
                arguments="{}",
                status="completed",
            )
        ],
        usage=None,
    )

    normalized = responses_module._model_response_from_responses(
        response, provider="openai"
    )

    assert normalized.tool_calls is None
    assert normalized.native_items and normalized.native_items[0]["id"] == "fc_invalid"


def test_api_mode_defaults_to_chat_and_rejects_unknown_values() -> None:
    model = OpenAIModel(model="gpt-4o-mini", api_key="test-key")
    assert model.api_mode == "chat_completions"

    with pytest.raises(ValueError, match="api_mode"):
        OpenAIModel(model="gpt-4o-mini", api_key="test-key", api_mode="auto")


def test_sync_responses_transport_uses_responses_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _response_with_function_calls()
    calls: List[Dict[str, Any]] = []

    class _Responses:
        def create(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            return response

    fake_client = SimpleNamespace(
        responses=_Responses(),
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: pytest.fail("Chat endpoint must not be called")
            )
        ),
    )
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: fake_client)
    model = OpenAICompatibleModel(
        model="gpt-5",
        api_key="test-key",
        base_url="https://example.test/v1",
        api_mode="responses",
        max_tokens=321,
    )

    result = model.call_raw(
        [{"role": "user", "content": "calculate"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "add",
                    "description": "Add",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )

    assert isinstance(result, ModelResponse)
    assert calls == [
        {
            "model": "gpt-5",
            "input": [{"role": "user", "content": "calculate"}],
            "temperature": 0.7,
            "max_output_tokens": 321,
            "tools": [
                {
                    "type": "function",
                    "name": "add",
                    "description": "Add",
                    "parameters": {"type": "object", "properties": {}},
                }
            ],
        }
    ]


def test_official_openai_model_uses_responses_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: List[Dict[str, Any]] = []

    class _Responses:
        def create(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            return _response_with_function_calls()

    fake_client = SimpleNamespace(responses=_Responses())
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: fake_client)
    model = OpenAIModel(
        model="gpt-5",
        api_key="test-key",
        api_mode="responses",
    )

    result = model.call_raw([{"role": "user", "content": "calculate"}])

    assert isinstance(result, ModelResponse)
    assert result.provider == "openai"
    assert calls[0]["input"] == [{"role": "user", "content": "calculate"}]


def test_responses_mode_never_falls_back_to_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: pytest.fail("Chat endpoint must not be called")
            )
        )
    )
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: fake_client)
    model = OpenAICompatibleModel(
        model="gpt-5",
        api_key="test-key",
        base_url="https://example.test/v1",
        api_mode="responses",
    )

    with pytest.raises(RuntimeError, match="openai>=1.66.0"):
        model.call_raw([{"role": "user", "content": "go"}])


def test_responses_stream_emits_typed_text_and_completed_tool_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed_response = _response_with_function_calls()
    events = iter(
        [
            SimpleNamespace(
                type="response.output_text.delta",
                delta="answer ",
                sequence_number=1,
                output_index=0,
                item_id="msg_1",
            ),
            SimpleNamespace(
                type="response.output_text.delta",
                delta="text",
                sequence_number=2,
                output_index=0,
                item_id="msg_1",
            ),
            SimpleNamespace(
                type="response.function_call_arguments.delta",
                delta='{"a":',
                sequence_number=3,
                output_index=1,
                item_id="fc_1",
            ),
            SimpleNamespace(
                type="response.output_item.done",
                item=completed_response.output[1],
                sequence_number=4,
                output_index=1,
            ),
            SimpleNamespace(
                type="response.completed",
                response=completed_response,
                sequence_number=5,
            ),
        ]
    )

    class _Responses:
        def create(self, **kwargs: Any) -> Any:
            assert kwargs["stream"] is True
            return events

    fake_client = SimpleNamespace(responses=_Responses())
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: fake_client)
    model = OpenAICompatibleModel(
        model="gpt-5",
        api_key="test-key",
        base_url="https://example.test/v1",
        api_mode="responses",
    )

    chunks = list(model.stream([{"role": "user", "content": "go"}]))

    assert [chunk.text for chunk in chunks if chunk.text] == ["answer ", "text"]
    assert chunks[0].event_type == "response.output_text.delta"
    argument_delta = [
        chunk
        for chunk in chunks
        if chunk.event_type == "response.function_call_arguments.delta"
    ]
    assert argument_delta[0].event_metadata["delta"] == '{"a":'
    completed_item = [
        chunk for chunk in chunks if chunk.event_type == "response.output_item.done"
    ]
    assert completed_item[0].native_items[0]["call_id"] == "call_1"
    assert chunks[-1].done is True
    assert chunks[-1].tool_calls
    assert chunks[-1].tool_calls[0]["id"] == "call_1"
    assert chunks[-1].native_items
    assert chunks[-1].usage["prompt_tokens"] == 11


def test_responses_stream_can_finish_from_output_item_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    function_item = _response_with_function_calls().output[1]

    class _Responses:
        def create(self, **kwargs: Any) -> Any:
            return iter(
                [
                    SimpleNamespace(
                        type="response.output_item.done",
                        item=function_item,
                        sequence_number=1,
                        output_index=0,
                    )
                ]
            )

    monkeypatch.setattr(
        "openai.OpenAI",
        lambda **kwargs: SimpleNamespace(responses=_Responses()),
    )
    model = OpenAICompatibleModel(
        model="compatible-model",
        api_key="test-key",
        base_url="https://example.test/v1",
        api_mode="responses",
    )

    chunks = list(model.stream([{"role": "user", "content": "go"}]))

    assert chunks[-1].done is True
    assert chunks[-1].tool_calls and chunks[-1].tool_calls[0]["id"] == "call_1"
    assert chunks[-1].native_items and chunks[-1].native_items[0]["id"] == "fc_1"


def test_async_responses_transport_uses_shared_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    calls: List[Dict[str, Any]] = []

    class _Responses:
        async def create(self, **kwargs: Any) -> Any:
            calls.append(kwargs)
            return _response_with_function_calls()

    fake_client = SimpleNamespace(responses=_Responses())
    monkeypatch.setattr("openai.AsyncOpenAI", lambda **kwargs: fake_client)
    model = AsyncOpenAICompatibleModel(
        model="gpt-5",
        api_key="test-key",
        base_url="https://example.test/v1",
        api_mode="responses",
    )

    response = asyncio.run(model.acall_raw([{"role": "user", "content": "calculate"}]))

    assert isinstance(response, ModelResponse)
    assert response.tool_calls and response.tool_calls[0]["id"] == "call_1"
    assert calls[0]["input"] == [{"role": "user", "content": "calculate"}]


def test_async_responses_stream_preserves_typed_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    completed_response = _response_with_function_calls()

    class _Events:
        def __init__(self) -> None:
            self._events = iter(
                [
                    SimpleNamespace(
                        type="response.output_text.delta",
                        delta="async text",
                        sequence_number=1,
                    ),
                    SimpleNamespace(
                        type="response.completed",
                        response=completed_response,
                        sequence_number=2,
                    ),
                ]
            )

        def __aiter__(self) -> "_Events":
            return self

        async def __anext__(self) -> Any:
            try:
                return next(self._events)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    class _Responses:
        async def create(self, **kwargs: Any) -> Any:
            assert kwargs["stream"] is True
            return _Events()

    monkeypatch.setattr(
        "openai.AsyncOpenAI",
        lambda **kwargs: SimpleNamespace(responses=_Responses()),
    )
    model = AsyncOpenAICompatibleModel(
        model="gpt-5",
        api_key="test-key",
        base_url="https://example.test/v1",
        api_mode="responses",
    )

    async def _collect() -> List[Any]:
        return [
            chunk
            async for chunk in model.astream([{"role": "user", "content": "calculate"}])
        ]

    chunks = asyncio.run(_collect())

    assert chunks[0].text == "async text"
    assert chunks[0].event_type == "response.output_text.delta"
    assert chunks[-1].done is True
    assert chunks[-1].tool_calls and chunks[-1].tool_calls[0]["id"] == "call_1"
