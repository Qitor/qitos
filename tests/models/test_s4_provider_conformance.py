from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any, Mapping

import pytest

from qitos.core.conversation import (
    ArgumentParseStatus,
    AssistantItem,
    CallIdentity,
    ExchangeLog,
    ToolCall,
    ToolResultItem,
    UserItem,
)
from qitos.core.multimodal import ContentBlock
from qitos.core.model_response import ModelResponse
from qitos.core.request_view import (
    ContextContribution,
    RequestContractError,
    RequestTarget,
    RequestView,
)
from qitos.core.tool_result import ToolResult
from qitos.models.anthropic import AnthropicModel
from qitos.models.codec import CodecCapabilityError, CodecError, ProviderCapabilities
from qitos.models.conformance import (
    ProviderConformanceCase,
    run_provider_conformance,
    run_provider_failure_conformance,
)
from qitos.models.provider import ProviderFailure, execute_provider_request
from qitos.models.gemini import GeminiModel
from qitos.models.litellm import LiteLLMModel
from qitos.models.local import LMStudioModel, OllamaGenerateModel, OllamaModel, VLLMModel
from qitos.models.openai import OpenAIModel


FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "s4"
    / "lane_b"
    / "third_party_adapter.py"
)


def _fixture() -> dict[str, Any]:
    return runpy.run_path(str(FIXTURE))


def _request(adapter: Any) -> RequestView:
    target = adapter.qitos_request_target()
    scope = f"{target.provider}:{target.api_mode}"
    first = ToolCall(
        identity=CallIdentity(scope, "prior-first"),
        batch_id="prior-batch",
        name="first",
        raw_arguments="{}",
        parsed_arguments={},
        parse_status=ArgumentParseStatus.PARSED,
    )
    second = ToolCall(
        identity=CallIdentity(scope, "prior-second"),
        batch_id="prior-batch",
        name="second",
        raw_arguments="{}",
        parsed_arguments={},
        parse_status=ArgumentParseStatus.PARSED,
    )
    log = ExchangeLog(log_id="s4-conformance-log")
    log.append(
        UserItem(
            item_id="user-one",
            exchange_id="exchange-one",
            content=[
                ContentBlock(type="text", text="inspect"),
                ContentBlock(type="image_base64", data="AA==", mime_type="image/png"),
            ],
        )
    )
    batch = log.append(
        AssistantItem(
            item_id="assistant-one",
            exchange_id="exchange-one",
            parts=[first, second],
        )
    )
    assert batch is not None
    for call in (second, first):
        batch.record_result(
            ToolResultItem(
                item_id=f"result-{call.identity.call_id}",
                exchange_id="exchange-one",
                identity=call.identity,
                batch_id=call.batch_id,
                result=ToolResult(
                    status="success",
                    output={"call": call.identity.call_id},
                    tool_name=call.name,
                    action_id=call.identity.call_id,
                ),
            )
        )
    log.append(
        UserItem(
            item_id="user-two",
            exchange_id="exchange-two",
            content=[ContentBlock(type="text", text="continue")],
        )
    )
    return RequestView.from_exchange_log(
        log,
        target=target,
        instructions=[{"role": "system", "content": "Be exact."}],
        tool_schemas=[
            {
                "type": "function",
                "function": {
                    "name": "first",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        context_contributions=[
            ContextContribution(
                contribution_id="context-one",
                source="fixture",
                content={"instruction": "preserve order"},
            )
        ],
    )


def _minimal_request(adapter: Any) -> RequestView:
    log = ExchangeLog(log_id="official-conformance-log")
    log.append(
        UserItem(
            item_id="official-user",
            exchange_id="official-exchange",
            content=[ContentBlock(type="text", text="inspect")],
        )
    )
    return RequestView.from_exchange_log(log, target=RequestTarget.from_model(adapter))


def _offline_model(model_type: type, api_mode: str) -> Any:
    model = object.__new__(model_type)
    model.model = "fixture-model"
    model.api_mode = api_mode
    model.context_window = 32_768
    model.max_tokens = 10_240
    return model


def test_standalone_third_party_adapter_passes_reusable_conformance_runner() -> None:
    fixture = _fixture()
    adapter = fixture["ExampleSemanticAdapter"]()
    case = ProviderConformanceCase(
        request=_request(adapter),
        sample_response=fixture["example_response"](),
        expected_part_kinds=(
            "reasoning_block",
            "content",
            "content",
            "tool_call",
            "tool_call",
        ),
        expect_parallel_tools=True,
        expect_reasoning=True,
        expect_multimodal=True,
        expect_continuation=True,
        expect_usage=True,
        exercise_stream=True,
    )

    report = run_provider_conformance(adapter, case)

    assert report.transaction is not None
    assert report.transaction.model_response.raw is None
    assert report.transaction.model_response.usage == {
        "prompt_tokens": 7,
        "completion_tokens": 5,
        "total_tokens": 12,
    }
    serialized = json.dumps(report.to_dict(), sort_keys=True)
    assert "opaque-example" not in serialized
    assert "continuation:example" not in serialized


@pytest.mark.parametrize(
    ("model_type", "api_mode", "response", "part_kinds", "reasoning", "continuation"),
    [
        (
            OpenAIModel,
            "chat_completions",
            {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
            ("content",),
            False,
            False,
        ),
        (
            OpenAIModel,
            "responses",
            ModelResponse(
                text="ok",
                usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                metadata={"id": "response-fixture"},
                native_items=[
                    {"type": "reasoning", "id": "r1", "summary": []},
                    {"type": "message", "content": [{"type": "output_text", "text": "ok"}]},
                ],
            ),
            ("reasoning_block", "content"),
            True,
            True,
        ),
        (
            AnthropicModel,
            "messages",
            {
                "content": [
                    {"type": "thinking", "thinking": "summary", "signature": "opaque"},
                    {"type": "text", "text": "ok"},
                ],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
            ("reasoning_block", "content"),
            True,
            True,
        ),
        (
            GeminiModel,
            "generate_content",
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"thought": True, "text": "summary", "thoughtSignature": "opaque"},
                                {"text": "ok"},
                            ]
                        }
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 1,
                    "candidatesTokenCount": 1,
                    "totalTokenCount": 2,
                },
            },
            ("reasoning_block", "content"),
            True,
            True,
        ),
        (
            LiteLLMModel,
            "chat_completions",
            {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
            ("content",),
            False,
            False,
        ),
        (
            OllamaModel,
            "chat",
            {
                "model": "fixture-model",
                "done": True,
                "prompt_eval_count": 1,
                "eval_count": 1,
                "message": {"content": "ok"},
            },
            ("content",),
            False,
            False,
        ),
        (
            OllamaGenerateModel,
            "generate",
            {
                "model": "fixture-model",
                "done": True,
                "prompt_eval_count": 1,
                "eval_count": 1,
                "response": "ok",
            },
            ("content",),
            False,
            False,
        ),
        (
            LMStudioModel,
            "chat_completions",
            {"choices": [{"message": {"content": "ok"}}]},
            ("content",),
            False,
            False,
        ),
        (
            VLLMModel,
            "chat_completions",
            {"choices": [{"message": {"content": "ok"}}]},
            ("content",),
            False,
            False,
        ),
    ],
)
def test_declared_builtin_modes_use_the_same_conformance_runner(
    model_type: type,
    api_mode: str,
    response: Any,
    part_kinds: tuple[str, ...],
    reasoning: bool,
    continuation: bool,
) -> None:
    model = _offline_model(model_type, api_mode)
    report = run_provider_conformance(
        model,
        ProviderConformanceCase(
            request=_minimal_request(model),
            sample_response=response,
            expected_part_kinds=part_kinds,
            expect_reasoning=reasoning,
            expect_continuation=continuation,
        ),
    )
    assert report.codec_id == model.qitos_provider_codec().codec_id


def test_conformance_failure_normalization_never_echoes_raw_details() -> None:
    fixture = _fixture()
    adapter = fixture["ExampleSemanticAdapter"]()
    failure = run_provider_failure_conformance(
        adapter,
        TimeoutError("sk-private https://localhost:9443 /Users/private"),
    )
    rendered = json.dumps(failure.to_dict(), sort_keys=True)
    assert failure.stage == "timeout"
    assert failure.provider_request_sent is True
    assert "sk-private" not in rendered
    assert "localhost" not in rendered
    assert "/Users/" not in rendered


def test_model_response_diagnostics_redact_headers_tokens_and_reasoning() -> None:
    response = ModelResponse(
        text="safe answer",
        metadata={
            "headers": {"Authorization": "Bearer secret-token"},
            "request_id": "request-safe",
        },
        reasoning_content="private chain of thought",
        reasoning_fields={"reasoning": "private chain of thought"},
        reasoning_source="reasoning",
    )

    summary = response.to_summary_dict()
    rendered = json.dumps(summary, sort_keys=True)
    assert "secret-token" not in rendered
    assert "private chain of thought" not in rendered
    assert summary["reasoning"] == {
        "present": True,
        "source": "reasoning",
        "field_names": ["reasoning"],
    }


def test_admission_and_cancellation_fail_before_transport_with_exact_facts() -> None:
    fixture = _fixture()

    class CountingAdapter(fixture["ExampleSemanticAdapter"]):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def qitos_transport(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
            self.calls += 1
            return super().qitos_transport(payload)

    adapter = CountingAdapter()
    with pytest.raises(ProviderFailure) as admitted:
        execute_provider_request(
            adapter,
            _request(adapter),
            request_admission=lambda: (_ for _ in ()).throw(
                RuntimeError("private admission")
            ),
        )
    assert admitted.value.stage == "admission"
    assert admitted.value.provider_request_sent is False
    assert adapter.calls == 0

    with pytest.raises(ProviderFailure) as cancelled:
        execute_provider_request(
            adapter,
            _request(adapter),
            cancellation_check=lambda: True,
        )
    assert cancelled.value.stage == "cancellation"
    assert cancelled.value.provider_request_sent is False
    assert adapter.calls == 0


def test_capabilities_reject_unknown_fields_non_boolean_and_illegal_budgets() -> None:
    fixture = _fixture()
    adapter = fixture["ExampleSemanticAdapter"]()
    valid = dict(adapter.qitos_provider_capabilities())

    for update in (
        {"unknown_capability": True},
        {"supports_usage": 1},
        {"max_output_units": 0},
        {"api_style": "provider-guessed"},
    ):
        declaration = {**valid, **update}

        class InvalidAdapter(fixture["ExampleSemanticAdapter"]):
            def qitos_provider_capabilities(self) -> Mapping[str, Any]:
                return declaration

        with pytest.raises(CodecCapabilityError):
            ProviderCapabilities.from_model(InvalidAdapter())


def test_request_projection_rejects_ten_megabytes_cycles_and_depth() -> None:
    fixture = _fixture()
    adapter = fixture["ExampleSemanticAdapter"]()
    target = adapter.qitos_request_target()
    log = ExchangeLog(log_id="bounded-log")
    log.append(
        UserItem(
            item_id="bounded-user",
            exchange_id="bounded-exchange",
            content=[ContentBlock(type="text", text="bounded")],
        )
    )
    cycle: list[Any] = []
    cycle.append(cycle)
    deep: Any = "leaf"
    for _ in range(66):
        deep = [deep]

    for content in ("x" * (10 * 1024 * 1024), cycle, deep):
        with pytest.raises(RequestContractError):
            RequestView.from_exchange_log(
                log,
                target=target,
                context_contributions=[
                    ContextContribution(
                        contribution_id="oversized",
                        source="fixture",
                        content=content,
                    )
                ],
            )
