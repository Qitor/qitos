from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from qitos.core.conversation import (
    CONTINUATION_REDACTED_DIAGNOSTIC_VERSION,
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
    UnsupportedSchemaVersionError,
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
    / "v2"
    / "semantic_fixtures.json"
)

FIXTURE_SCHEMA_VERSION = "qitos.conversation.fixture.v2"


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


def _validate_fixture_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("fixture_version") != FIXTURE_SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            f"unsupported conversation fixture schema: "
            f"{manifest.get('fixture_version')!r}"
        )
    return manifest


def _fixture_manifest() -> dict[str, Any]:
    manifest = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return _validate_fixture_manifest(manifest)


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


def test_exchange_log_exposes_isolated_sequence_snapshots() -> None:
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


def test_append_and_read_boundaries_isolate_all_nested_mutable_values() -> None:
    block_metadata = {"nested": {"value": "block-original"}}
    parsed_arguments = {"nested": {"value": "args-original"}}
    call_metadata = {"nested": {"value": "call-original"}}
    reasoning_metadata = {"nested": {"value": "reasoning-original"}}
    opaque_payload = {"nested": ["opaque-original"]}
    attachment_metadata = {"nested": {"value": "attachment-original"}}
    assistant_metadata = {"nested": {"value": "assistant-original"}}
    call = ToolCall(
        identity=CallIdentity("provider:mode", "nested_call"),
        batch_id="nested_batch",
        name="nested_tool",
        raw_arguments="{}",
        parsed_arguments=parsed_arguments,
        parse_status=ArgumentParseStatus.PARSED,
        metadata=call_metadata,
    )
    parts = [
        AssistantContent(
            ContentBlock(type="text", text="fact", metadata=block_metadata)
        ),
        ReasoningReference(
            "provider:mode", "reasoning", metadata=reasoning_metadata
        ),
        call,
    ]
    attachments = [
        OpaqueContinuationAttachment(
            attachment_id="nested_attachment",
            provider_scope="provider:mode",
            api_mode="mode",
            opaque_payload=opaque_payload,
            metadata=attachment_metadata,
        )
    ]
    log = ExchangeLog(log_id="log_nested_isolation")
    builder = log.append(
        AssistantItem(
            item_id="assistant_nested",
            exchange_id="exchange_nested",
            parts=parts,
            continuation_attachments=attachments,
            metadata=assistant_metadata,
        )
    )
    assert builder is not None

    parts.clear()
    attachments.clear()
    block_metadata["nested"]["value"] = "block-mutated"
    parsed_arguments["nested"]["value"] = "args-mutated"
    call_metadata["nested"]["value"] = "call-mutated"
    reasoning_metadata["nested"]["value"] = "reasoning-mutated"
    opaque_payload["nested"].append("opaque-mutated")
    attachment_metadata["nested"]["value"] = "attachment-mutated"
    assistant_metadata["nested"]["value"] = "assistant-mutated"

    result_content_metadata = {"nested": {"value": "result-content-original"}}
    provenance_details = {"nested": {"value": "provenance-original"}}
    result_metadata = {"nested": {"value": "result-original"}}
    result = ToolResultItem(
        item_id="result_nested",
        exchange_id="exchange_nested",
        identity=call.identity,
        batch_id=call.batch_id,
        status=ToolResultStatus.SUCCEEDED,
        content=[
            ContentBlock(
                type="text", text="done", metadata=result_content_metadata
            )
        ],
        provenance=ClosureProvenance(
            source="tests.worker", details=provenance_details
        ),
        metadata=result_metadata,
    )
    builder.record_result(result)
    result_content_metadata["nested"]["value"] = "result-content-mutated"
    provenance_details["nested"]["value"] = "provenance-mutated"
    result_metadata["nested"]["value"] = "result-mutated"
    result.content.append(ContentBlock(type="text", text="late mutation"))

    snapshot = log.items
    assistant = snapshot[0]
    recorded_result = snapshot[1]
    assert isinstance(assistant, AssistantItem)
    assert isinstance(recorded_result, ToolResultItem)
    assistant.parts.clear()
    assistant.continuation_attachments[0].opaque_payload["nested"].append(
        "snapshot-mutated"
    )
    assistant.metadata["nested"]["value"] = "snapshot-mutated"
    recorded_result.content.clear()
    recorded_result.provenance.details["nested"]["value"] = "snapshot-mutated"
    recorded_result.metadata["nested"]["value"] = "snapshot-mutated"

    persisted = log.to_persistence_dict()
    assert len(persisted["items"][0]["parts"]) == 3
    assert persisted["items"][0]["parts"][0]["block"]["metadata"]["nested"][
        "value"
    ] == "block-original"
    assert persisted["items"][0]["parts"][2]["parsed_arguments"]["nested"][
        "value"
    ] == "args-original"
    assert persisted["items"][0]["parts"][1]["metadata"]["nested"][
        "value"
    ] == "reasoning-original"
    assert persisted["items"][0]["parts"][2]["metadata"]["nested"][
        "value"
    ] == "call-original"
    assert persisted["items"][0]["continuation_attachments"][0][
        "opaque_payload"
    ] == {"nested": ["opaque-original"]}
    assert persisted["items"][0]["continuation_attachments"][0]["metadata"][
        "nested"
    ]["value"] == "attachment-original"
    assert persisted["items"][0]["metadata"]["nested"]["value"] == (
        "assistant-original"
    )
    assert persisted["items"][1]["provenance"]["details"]["nested"][
        "value"
    ] == "provenance-original"
    assert persisted["items"][1]["content"][0]["metadata"]["nested"][
        "value"
    ] == "result-content-original"
    assert len(persisted["items"][1]["content"]) == 1

    persisted["items"][0]["parts"].clear()
    persisted["items"][1]["metadata"]["nested"]["value"] = "serialized-mutated"
    fresh = log.to_persistence_dict()
    assert len(fresh["items"][0]["parts"]) == 3
    assert fresh["items"][1]["metadata"]["nested"]["value"] == "result-original"


def test_user_and_queued_steering_inputs_and_snapshots_are_isolated() -> None:
    user_content = [
        ContentBlock(type="text", text="user", metadata={"nested": ["original"]})
    ]
    user_metadata = {"nested": ["original"]}
    log = ExchangeLog(log_id="log_user_steering_isolation")
    log.append(
        UserItem(
            item_id="user_isolated",
            exchange_id="exchange_user",
            content=user_content,
            metadata=user_metadata,
        )
    )
    user_content.clear()
    user_metadata["nested"].append("mutated")

    call = _call("steering_isolation", batch_id="batch_steering_isolation")
    builder = log.append(
        _assistant_with_calls(
            call,
            item_id="assistant_steering_isolation",
            exchange_id="exchange_steering_isolation",
        )
    )
    assert builder is not None
    steering_content = [ContentBlock(type="text", text="queued")]
    steering_metadata = {"nested": ["queued-original"]}
    steering = SteeringItem(
        item_id="steering_isolated",
        exchange_id="exchange_next",
        content=steering_content,
        metadata=steering_metadata,
    )
    log.queue_steering(steering)
    steering_content.clear()
    steering_metadata["nested"].append("mutated")
    queued_snapshot = log.queued_steering[0]
    queued_snapshot.content.clear()
    queued_snapshot.metadata["nested"].append("snapshot-mutated")

    partial = log.to_persistence_dict()
    assert partial["items"][0]["content"][0]["text"] == "user"
    assert partial["items"][0]["metadata"] == {"nested": ["original"]}
    assert partial["queued_steering"][0]["content"][0]["text"] == "queued"
    assert partial["queued_steering"][0]["metadata"] == {
        "nested": ["queued-original"]
    }


def test_from_dict_copies_nested_input_values() -> None:
    payload = {
        "schema_version": "qitos.exchange_log.v1",
        "log_id": "log_from_dict_isolation",
        "queued_steering": [],
        "items": [
            {
                "kind": "user",
                "item_id": "user_from_dict",
                "exchange_id": "exchange_from_dict",
                "content": [
                    {
                        "type": "text",
                        "text": "original",
                        "metadata": {"nested": ["original"]},
                    }
                ],
                "metadata": {"nested": ["original"]},
            }
        ],
    }
    log = ExchangeLog.from_dict(payload)
    payload["items"][0]["content"][0]["text"] = "mutated"
    payload["items"][0]["content"][0]["metadata"]["nested"].append("mutated")
    payload["items"][0]["metadata"]["nested"].append("mutated")

    assert log.to_persistence_dict()["items"][0] == {
        "kind": "user",
        "item_id": "user_from_dict",
        "exchange_id": "exchange_from_dict",
        "content": [
            {
                "type": "text",
                "text": "original",
                "metadata": {"nested": ["original"]},
            }
        ],
        "metadata": {"nested": ["original"]},
    }


def test_out_of_order_completion_persists_immediately_in_completion_order() -> None:
    first = _call("first")
    second = _call("second")
    log = ExchangeLog(log_id="log_parallel")
    builder = log.append(_assistant_with_calls(first, second))
    assert builder is not None

    assert builder.record_result(_result(second, item_id="result_second")) is False
    assert [result.identity.call_id for result in log.results_for_batch("batch_1")] == [
        "second"
    ]
    assert builder.record_result(_result(first, item_id="result_first")) is True

    assert [result.identity.call_id for result in log.results_for_batch("batch_1")] == [
        "second",
        "first",
    ]
    assert [
        result.identity.call_id
        for result in log.results_for_batch_in_declaration_order("batch_1")
    ] == [
        "first",
        "second",
    ]
    log.assert_ready_for_model_transaction()


def test_partial_batch_round_trip_resumes_only_missing_calls_and_steering_once() -> None:
    first = _call("first", batch_id="batch_recovery")
    second = _call("second", batch_id="batch_recovery")
    log = ExchangeLog(log_id="log_recovery")
    builder = log.append(
        _assistant_with_calls(
            first,
            second,
            item_id="assistant_recovery",
            exchange_id="exchange_recovery",
        )
    )
    assert builder is not None
    builder.record_result(
        _result(
            second,
            item_id="result_second_before_reload",
            exchange_id="exchange_recovery",
        )
    )
    log.queue_steering(
        SteeringItem(
            item_id="steering_after_recovery",
            exchange_id="exchange_next",
            content=[ContentBlock(type="text", text="continue once")],
        )
    )

    persisted = json.loads(json.dumps(log.to_persistence_dict()))
    recovered = ExchangeLog.from_dict(persisted)
    assert recovered.open_batch_id() == "batch_recovery"
    with pytest.raises(IncompleteToolBatchError):
        recovered.assert_ready_for_model_transaction()

    recovered_builder = ToolBatchBuilder(recovered, "batch_recovery")
    with pytest.raises(DuplicateToolResultError):
        recovered_builder.record_result(
            _result(
                second,
                item_id="duplicate_second_after_reload",
                exchange_id="exchange_recovery",
            )
        )
    with pytest.raises(IncompleteToolBatchError):
        recovered.append(
            UserItem(
                item_id="blocked_after_reload",
                exchange_id="exchange_blocked",
                content=[ContentBlock(type="text", text="too early")],
            )
        )
    executed: list[str] = []
    for missing in recovered_builder.missing_calls:
        executed.append(missing.identity.call_id)
        recovered_builder.record_result(
            _result(
                missing,
                item_id=f"result_{missing.identity.call_id}_after_reload",
                exchange_id="exchange_recovery",
            )
        )

    assert executed == ["first"]
    assert [
        result.identity.call_id
        for result in recovered.results_for_batch("batch_recovery")
    ] == ["second", "first"]
    assert [
        result.identity.call_id
        for result in recovered.results_for_batch_in_declaration_order(
            "batch_recovery"
        )
    ] == ["first", "second"]
    assert sum(
        item.item_id == "steering_after_recovery" for item in recovered.items
    ) == 1
    assert recovered.items[-1].item_id == "steering_after_recovery"
    assert recovered.queued_steering == ()
    recovered.assert_ready_for_model_transaction()


def test_recovery_synthetic_closure_never_overwrites_completed_slots() -> None:
    first = _call("first", batch_id="batch_synthetic_recovery")
    second = _call("second", batch_id="batch_synthetic_recovery")
    log = ExchangeLog(log_id="log_synthetic_recovery")
    builder = log.append(
        _assistant_with_calls(
            first,
            second,
            item_id="assistant_synthetic_recovery",
            exchange_id="exchange_synthetic_recovery",
        )
    )
    assert builder is not None
    builder.record_result(
        _result(
            second,
            item_id="result_completed",
            exchange_id="exchange_synthetic_recovery",
        )
    )

    recovered = ExchangeLog.from_dict(log.to_persistence_dict())
    recovered_builder = ToolBatchBuilder(recovered, "batch_synthetic_recovery")
    recovered_builder.close_missing(
        status=ToolResultStatus.MISSING_WORKER,
        reason="worker_missing_after_reload",
    )

    results = recovered.results_for_batch("batch_synthetic_recovery")
    assert [result.identity.call_id for result in results] == ["second", "first"]
    assert results[0].item_id == "result_completed"
    assert results[0].provenance.synthetic is False
    assert results[1].provenance.synthetic is True
    assert results[1].status is ToolResultStatus.MISSING_WORKER


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
    assert log.items[-1] == steering
    assert sum(isinstance(item, SteeringItem) for item in log.items) == 1
    log.assert_ready_for_model_transaction()


def test_opaque_continuation_is_lossless_only_in_persistence_projection() -> None:
    attachment = OpaqueContinuationAttachment(
        attachment_id="opaque_1",
        provider_scope="provider:responses",
        api_mode="responses",
        opaque_payload={"encrypted_content": "ciphertext"},
        metadata={"token": "diagnostic-secret"},
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
    diagnostic = log.to_continuation_redacted_diagnostic_dict()

    assert "ciphertext" in json.dumps(persisted)
    assert "ciphertext" not in json.dumps(diagnostic)
    assert "diagnostic-secret" in json.dumps(diagnostic)
    assert diagnostic["projection_version"] == (
        CONTINUATION_REDACTED_DIAGNOSTIC_VERSION
    )
    assert diagnostic["items"][0]["continuation_attachments"][0][
        "opaque_payload"
    ] == {"redacted": True}
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
    assert [result.identity.call_id for result in results] == ["call_b", "call_a"]
    assert [
        result.identity.call_id
        for result in log.results_for_batch_in_declaration_order("legacy_batch_0")
    ] == ["call_a", "call_b"]
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
    assert "ciphertext" not in json.dumps(
        log.to_continuation_redacted_diagnostic_dict()
    )
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
    assert manifest["fixture_version"] == FIXTURE_SCHEMA_VERSION
    assert set(fixtures) == required
    for case in fixtures.values():
        assert case["schema_version"] == "qitos.exchange_log.v1"
        assert case["expected_invariant"]
        assert "expected_error" in case
        assert case["consumer_simulations"]
        assert isinstance(case["lossless"], bool)


def test_old_fixture_envelope_is_rejected_with_typed_version_error() -> None:
    with pytest.raises(UnsupportedSchemaVersionError) as exc_info:
        _validate_fixture_manifest(
            {"fixture_version": "qitos.conversation.fixture.v1"}
        )
    assert exc_info.value.code == "unsupported_schema_version"


def test_execution_fixture_consumer_simulation_closes_batches() -> None:
    """In-repository simulation of an execution-side fixture consumer."""

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
        ] == case["completion_order"]
        assert [
            result.identity.call_id
            for result in log.results_for_batch_in_declaration_order(batch_id)
        ] == [call.identity.call_id for call in builder.calls]
        if case["name"] == "mid_batch_steering":
            assert isinstance(log.items[-1], SteeringItem)


def test_persistence_fixture_consumer_simulation_validates_semantics() -> None:
    """In-repository simulation of a persistence-side fixture consumer."""

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
        elif operation == "continuation_redacted_diagnostic_projection":
            assert "opaque-ciphertext" in json.dumps(log.to_persistence_dict())
            diagnostic = log.to_continuation_redacted_diagnostic_dict()
            assert "opaque-ciphertext" not in json.dumps(diagnostic)
            assert "diagnostic-secret" in json.dumps(diagnostic)
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
