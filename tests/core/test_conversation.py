from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from qitos.core.conversation import (
    ArgumentParseStatus,
    AssistantContent,
    AssistantItem,
    CallIdentity,
    ClosureProvenance,
    ConversationValidationError,
    DuplicateCallIdError,
    DuplicateItemIdError,
    DuplicateToolResultError,
    ExchangeLog,
    IncompleteToolBatchError,
    OpaqueContinuationAttachment,
    ReasoningReference,
    SteeringItem,
    ToolCall,
    ToolBatchBuilder,
    ToolResultItem,
    ToolResultStatus,
    UnsupportedReasoningReplayError,
    UnsafeHistoryConversionError,
    UserItem,
    exchange_log_to_history_messages,
    history_messages_to_exchange_log,
)
from qitos.core.history import HistoryMessage
from qitos.core.multimodal import ContentBlock


FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "conversation"
    / "v1"
    / "semantic_fixtures.json"
)


def _call(
    call_id: str,
    *,
    batch_id: str = "batch_1",
    provider_scope: str = "provider:mode",
) -> ToolCall:
    return ToolCall(
        identity=CallIdentity(provider_scope, call_id),
        batch_id=batch_id,
        name=f"tool_{call_id}",
        raw_arguments="{}",
        parsed_arguments={},
        parse_status=ArgumentParseStatus.PARSED,
    )


def _assistant_with_calls(
    *calls: ToolCall,
    item_id: str = "assistant_1",
    exchange_id: str = "exchange_1",
) -> AssistantItem:
    return AssistantItem(
        item_id=item_id,
        exchange_id=exchange_id,
        parts=list(calls),
    )


def _result(
    call: ToolCall,
    *,
    item_id: str,
    status: ToolResultStatus = ToolResultStatus.SUCCEEDED,
    synthetic: bool = False,
    exchange_id: str = "exchange_1",
) -> ToolResultItem:
    return ToolResultItem(
        item_id=item_id,
        exchange_id=exchange_id,
        identity=call.identity,
        batch_id=call.batch_id,
        status=status,
        content=[ContentBlock(type="text", text=f"result for {call.name}")],
        provenance=ClosureProvenance(
            source="tests.worker",
            synthetic=synthetic,
            reason="test closure" if synthetic else None,
        ),
    )


def _fixture_manifest() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_multimodal_content_and_assistant_part_order_round_trip() -> None:
    log = ExchangeLog(log_id="log_order")
    log.append(
        UserItem(
            item_id="user_1",
            exchange_id="exchange_1",
            content=[
                ContentBlock(type="text", text="look"),
                ContentBlock(type="image_url", url="https://example.invalid/a.png"),
            ],
        )
    )
    log.append(
        AssistantItem(
            item_id="assistant_1",
            exchange_id="exchange_1",
            parts=[
                AssistantContent(ContentBlock(type="text", text="before")),
                ReasoningReference("provider:mode", "reasoning_1"),
                AssistantContent(ContentBlock(type="text", text="after")),
            ],
        )
    )

    restored = ExchangeLog.from_dict(log.to_persistence_dict())

    user = restored.items[0]
    assistant = restored.items[1]
    assert isinstance(user, UserItem)
    assert [block.type for block in user.content] == ["text", "image_url"]
    assert isinstance(assistant, AssistantItem)
    assert [part.kind for part in assistant.parts] == [
        "content",
        "reasoning_reference",
        "content",
    ]


def test_exchange_log_exposes_immutable_sequence_views() -> None:
    log = ExchangeLog(log_id="log_append_only")
    initial_view = log.items
    assert isinstance(initial_view, tuple)
    with pytest.raises(AttributeError):
        initial_view.append("not an item")  # type: ignore[attr-defined]

    log.append(
        UserItem(
            item_id="user_append_only",
            exchange_id="exchange_append_only",
            content=[ContentBlock(type="text", text="fact")],
        )
    )
    assert initial_view == ()
    assert len(log.items) == 1


def test_out_of_order_completion_commits_in_declaration_order() -> None:
    first = _call("first")
    second = _call("second")
    log = ExchangeLog(log_id="log_parallel")
    builder = log.append(_assistant_with_calls(first, second))
    assert builder is not None

    assert builder.record_result(_result(second, item_id="result_second")) is False
    assert log.results_for_batch("batch_1") == []
    assert builder.record_result(_result(first, item_id="result_first")) is True

    assert [result.identity.call_id for result in log.results_for_batch("batch_1")] == [
        "first",
        "second",
    ]
    log.assert_ready_for_model_transaction()


@pytest.mark.parametrize(
    "status",
    [
        ToolResultStatus.FAILED,
        ToolResultStatus.PERMISSION_BLOCKED,
        ToolResultStatus.TIMED_OUT,
        ToolResultStatus.CANCELLED,
        ToolResultStatus.MISSING_WORKER,
    ],
)
def test_every_non_success_terminal_state_can_close_a_slot(
    status: ToolResultStatus,
) -> None:
    call = _call("terminal")
    log = ExchangeLog(log_id=f"log_{status.value}")
    builder = log.append(_assistant_with_calls(call))
    assert builder is not None

    builder.close_missing(status=status, reason=status.value)

    result = log.results_for_batch("batch_1")[0]
    assert result.status is status
    assert result.provenance.synthetic is True
    assert result.provenance.reason == status.value
    log.assert_ready_for_model_transaction()


def test_duplicate_call_id_is_scoped_and_typed() -> None:
    log = ExchangeLog(log_id="log_duplicate")
    with pytest.raises(DuplicateCallIdError) as exc_info:
        log.append(_assistant_with_calls(_call("same"), _call("same")))
    assert exc_info.value.code == "duplicate_call_id"

    cross_scope = ExchangeLog(log_id="log_cross_scope")
    builder = cross_scope.append(
        _assistant_with_calls(
            _call("same", provider_scope="provider:chat"),
            _call("same", provider_scope="provider:responses"),
        )
    )
    assert builder is not None
    builder.close_missing(status=ToolResultStatus.CANCELLED, reason="test")
    cross_scope.assert_ready_for_model_transaction()

    across_batches = ExchangeLog(log_id="log_across_batches")
    first = _call("reused", batch_id="batch_first")
    first_builder = across_batches.append(_assistant_with_calls(first))
    assert first_builder is not None
    first_builder.record_result(
        _result(first, item_id="result_first_batch", exchange_id="exchange_1")
    )
    with pytest.raises(DuplicateCallIdError):
        across_batches.append(
            _assistant_with_calls(
                _call("reused", batch_id="batch_second"),
                item_id="assistant_second_batch",
                exchange_id="exchange_2",
            )
        )


def test_duplicate_result_is_typed_before_batch_commit() -> None:
    first = _call("first")
    second = _call("second")
    log = ExchangeLog(log_id="log_duplicate_result")
    builder = log.append(_assistant_with_calls(first, second))
    assert builder is not None
    builder.record_result(_result(first, item_id="result_first"))

    with pytest.raises(DuplicateToolResultError) as exc_info:
        builder.record_result(_result(first, item_id="result_first_again"))
    assert exc_info.value.code == "duplicate_tool_result"

    with pytest.raises(DuplicateItemIdError):
        builder.record_result(_result(second, item_id="result_first"))


def test_incomplete_batch_blocks_normal_items_and_queues_steering() -> None:
    call = _call("open")
    log = ExchangeLog(log_id="log_steering")
    builder = log.append(_assistant_with_calls(call))
    assert builder is not None

    with pytest.raises(IncompleteToolBatchError):
        log.append(
            UserItem(
                item_id="user_blocked",
                exchange_id="exchange_2",
                content=[ContentBlock(type="text", text="next turn")],
            )
        )
    steering = SteeringItem(
        item_id="steering_1",
        exchange_id="exchange_2",
        content=[ContentBlock(type="text", text="change course")],
    )
    log.queue_steering(steering)
    assert log.queued_steering == (steering,)
    with pytest.raises(IncompleteToolBatchError):
        log.assert_ready_for_model_transaction()

    builder.record_result(_result(call, item_id="result_open"))

    assert log.queued_steering == ()
    assert log.items[-1] is steering
    assert sum(isinstance(item, SteeringItem) for item in log.items) == 1
    log.assert_ready_for_model_transaction()


def test_opaque_continuation_is_lossless_only_in_persistence_projection() -> None:
    attachment = OpaqueContinuationAttachment(
        attachment_id="opaque_1",
        provider_scope="provider:responses",
        api_mode="responses",
        opaque_payload={"encrypted_content": "ciphertext"},
    )
    log = ExchangeLog(log_id="log_opaque")
    log.append(
        AssistantItem(
            item_id="assistant_opaque",
            exchange_id="exchange_opaque",
            parts=[
                ReasoningReference(
                    "provider:responses", "reasoning_1", attachment_id="opaque_1"
                )
            ],
            continuation_attachments=[attachment],
        )
    )

    persisted = log.to_persistence_dict()
    safe = log.to_safe_dict()

    assert "ciphertext" in json.dumps(persisted)
    assert "ciphertext" not in json.dumps(safe)
    assert safe["items"][0]["continuation_attachments"][0]["opaque_payload"] == {
        "redacted": True
    }
    assert ExchangeLog.from_dict(persisted).to_persistence_dict() == persisted


def test_history_adapter_preserves_compatible_parallel_exchange() -> None:
    history = [
        HistoryMessage(
            role="assistant",
            step_id=7,
            content="working",
            tool_calls=[
                {
                    "id": "call_a",
                    "type": "function",
                    "function": {"name": "a", "arguments": "{\"x\":1}"},
                },
                {
                    "id": "call_b",
                    "type": "function",
                    "function": {"name": "b", "arguments": "[1,2]"},
                },
            ],
        ),
        HistoryMessage(
            role="tool", step_id=7, content="b-result", tool_call_id="call_b"
        ),
        HistoryMessage(
            role="tool", step_id=7, content="a-result", tool_call_id="call_a"
        ),
    ]

    log = history_messages_to_exchange_log(history, provider_scope="legacy:test")
    calls = log.declared_calls("legacy_batch_0")
    results = log.results_for_batch("legacy_batch_0")

    assert [call.identity.call_id for call in calls] == ["call_a", "call_b"]
    assert calls[0].parse_status is ArgumentParseStatus.PARSED
    assert calls[1].parse_status is ArgumentParseStatus.PARSED_INVALID
    assert [result.identity.call_id for result in results] == ["call_a", "call_b"]
    projected = exchange_log_to_history_messages(log)
    assert [message.role for message in projected] == ["assistant", "tool", "tool"]
    assert [message.tool_call_id for message in projected[1:]] == [
        "call_a",
        "call_b",
    ]


def test_history_adapter_never_infers_error_prefix_as_failure() -> None:
    history = [
        HistoryMessage(
            role="assistant",
            step_id=1,
            content="Error: this is authored model text.",
        )
    ]

    log = history_messages_to_exchange_log(history)
    projected = exchange_log_to_history_messages(log)

    assert projected[0].content == "Error: this is authored model text."


def test_history_adapter_preserves_native_items_as_opaque_not_text() -> None:
    native = [{"type": "reasoning", "encrypted_content": "ciphertext"}]
    history = [
        HistoryMessage(
            role="assistant",
            step_id=2,
            content=None,
            native_items=native,
            metadata={"api_mode": "responses"},
        )
    ]

    log = history_messages_to_exchange_log(
        history, provider_scope="openai:responses"
    )
    assistant = log.items[0]
    assert isinstance(assistant, AssistantItem)
    assert assistant.parts == []
    assert assistant.continuation_attachments[0].opaque_payload == native
    assert "ciphertext" not in json.dumps(log.to_safe_dict())
    projected = exchange_log_to_history_messages(log)
    assert projected[0].content is None
    assert projected[0].native_items == native


def test_history_projection_rejects_reasoning_and_interleaving_loss() -> None:
    reasoning_log = ExchangeLog(log_id="log_reasoning")
    reasoning_log.append(
        AssistantItem(
            item_id="assistant_reasoning",
            exchange_id="exchange_reasoning",
            parts=[ReasoningReference("provider:mode", "ref_1")],
        )
    )
    with pytest.raises(UnsupportedReasoningReplayError):
        exchange_log_to_history_messages(reasoning_log)

    interleaved = ExchangeLog(log_id="log_interleaved")
    call = _call("interleaved")
    builder = interleaved.append(
        AssistantItem(
            item_id="assistant_interleaved",
            exchange_id="exchange_1",
            parts=[
                call,
                AssistantContent(ContentBlock(type="text", text="after call")),
            ],
        )
    )
    assert builder is not None
    builder.close_missing(status=ToolResultStatus.CANCELLED, reason="test")
    with pytest.raises(UnsafeHistoryConversionError):
        exchange_log_to_history_messages(interleaved)


def test_history_adapter_rejects_unsupported_role_without_mutating_message() -> None:
    message = HistoryMessage(role="system", step_id=0, content="stable system")
    before = message.__dict__.copy()

    with pytest.raises(UnsafeHistoryConversionError):
        history_messages_to_exchange_log([message])

    assert message.__dict__ == before


def test_versioned_semantic_fixture_manifest_exercises_all_required_cases() -> None:
    manifest = _fixture_manifest()
    fixtures = {case["name"]: case for case in manifest["fixtures"]}
    required = {
        "multimodal_exchange",
        "single_tool_call",
        "native_parallel_calls",
        "out_of_order_completion",
        "malformed_raw_args",
        "raw_valid_parsed_failed",
        "duplicate_call_id",
        "incomplete_batch",
        "interrupted_batch_synthetic_closure",
        "mid_batch_steering",
        "opaque_continuation",
        "unsupported_reasoning_replay",
        "genuine_error_prefix_assistant_text",
        "serialization_round_trip",
    }
    assert manifest["fixture_version"] == "qitos.conversation.fixture.v1"
    assert set(fixtures) == required
    for case in fixtures.values():
        assert case["schema_version"] == "qitos.exchange_log.v1"
        assert case["expected_invariant"]
        assert "expected_error" in case
        assert case["consumers"]
        assert isinstance(case["lossless"], bool)


def test_lane_c_execution_consumer_closes_fixture_batches() -> None:
    """Independent consumer 1: executor-like completion and ordered commit."""

    cases = _fixture_manifest()["fixtures"]
    for case in cases:
        if case["operation"] != "complete_batch":
            continue
        log = ExchangeLog.from_dict(case["exchange_log"])
        batch_id = log.open_batch_id()
        assert batch_id is not None
        builder = ToolBatchBuilder(log, batch_id)
        with pytest.raises(IncompleteToolBatchError):
            log.assert_ready_for_model_transaction()
        calls = {call.identity.call_id: call for call in builder.calls}
        for position, call_id in enumerate(case["completion_order"]):
            builder.record_result(
                _result(
                    calls[call_id],
                    item_id=f"fixture_result_{case['name']}_{position}",
                    exchange_id=builder.exchange_id,
                )
            )
        log.assert_ready_for_model_transaction()
        assert [
            result.identity.call_id for result in log.results_for_batch(batch_id)
        ] == [call.identity.call_id for call in builder.calls]
        if case["name"] == "mid_batch_steering":
            assert isinstance(log.items[-1], SteeringItem)


def test_lane_d_persistence_consumer_validates_fixture_semantics() -> None:
    """Independent consumer 2: trajectory-like load, errors, and round-trip."""

    for case in _fixture_manifest()["fixtures"]:
        expected_error = case["expected_error"]
        if expected_error == "duplicate_call_id":
            with pytest.raises(ConversationValidationError) as exc_info:
                ExchangeLog.from_dict(case["exchange_log"])
            assert exc_info.value.code == expected_error
            continue
        log = ExchangeLog.from_dict(case["exchange_log"])
        operation = case["operation"]
        if operation == "assert_ready":
            with pytest.raises(ConversationValidationError) as exc_info:
                log.assert_ready_for_model_transaction()
            assert exc_info.value.code == expected_error
        elif operation == "history_projection":
            if expected_error:
                with pytest.raises(ConversationValidationError) as exc_info:
                    exchange_log_to_history_messages(log)
                assert exc_info.value.code == expected_error
            else:
                projected = exchange_log_to_history_messages(log)
                assert projected
        elif operation == "safe_projection":
            assert "opaque-ciphertext" in json.dumps(log.to_persistence_dict())
            assert "opaque-ciphertext" not in json.dumps(log.to_safe_dict())
        elif operation == "round_trip":
            persisted = log.to_persistence_dict()
            assert ExchangeLog.from_dict(persisted).to_persistence_dict() == persisted
        elif operation == "assert_parse_status":
            batch_id = log.open_batch_id()
            assert batch_id is not None
            call = log.declared_calls(batch_id)[0]
            expected = (
                ArgumentParseStatus.MALFORMED_RAW
                if case["name"] == "malformed_raw_args"
                else ArgumentParseStatus.PARSED_INVALID
            )
            assert call.parse_status is expected
