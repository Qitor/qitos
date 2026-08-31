from __future__ import annotations

import copy
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
    UnsupportedSchemaVersionError,
    UnsupportedReasoningReplayError,
    UnsafeHistoryConversionError,
    UserItem,
    exchange_log_to_history_messages,
    history_messages_to_exchange_log,
)
from qitos.core.history import HistoryMessage
from qitos.core.multimodal import ContentBlock
from qitos.core.tool_result import ToolResult
from qitos.core.tool_result import (
    HISTORICAL_TOOL_RESULT_SCHEMA_VERSION,
    TOOL_RESULT_MODEL_VIEW_VERSION,
    TOOL_RESULT_SCHEMA_VERSION,
    TOOL_RESULT_TRACE_SAFE_VERSION,
)


FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "conversation"
    / "v3"
    / "semantic_fixtures.json"
)

FIXTURE_SCHEMA_VERSION = "qitos.conversation.fixture.v3"
QUALIFICATION_EVIDENCE_PATH = FIXTURE_PATH.with_name("qualification-evidence.json")

C_FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "tool_results"
    / "v1"
    / "contract_hardening.json"
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
    status: str = "success",
    synthetic: bool = False,
    exchange_id: str = "exchange_1",
) -> ToolResultItem:
    canonical = (
        ToolResult(
            status="success",
            output=f"result for {call.name}",
            tool_name=call.name,
            action_id=call.identity.call_id,
            provenance={"source": "tests.worker"},
        )
        if status == "success"
        else ToolResult(
            status=status,  # type: ignore[arg-type]
            tool_name=call.name,
            action_id=call.identity.call_id,
            error=f"result for {call.name}",
            error_kind="policy" if status == "skipped" else "execution",
            error_code=status,
            provenance={"source": "tests.worker"},
        )
    )
    return ToolResultItem(
        item_id=item_id,
        exchange_id=exchange_id,
        identity=call.identity,
        batch_id=call.batch_id,
        result=canonical,
        synthetic=synthetic,
        closure_reason="test closure" if synthetic else None,
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


def _scalar_leaves(value: object) -> list[object]:
    if isinstance(value, dict):
        return [
            leaf
            for item in value.values()
            for leaf in _scalar_leaves(item)
        ]
    if isinstance(value, list):
        return [leaf for item in value for leaf in _scalar_leaves(item)]
    return [value]


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

    result_output = {"nested": {"value": "result-output-original"}}
    provenance_details = {"nested": {"value": "provenance-original"}}
    result_metadata = {"nested": {"value": "result-original"}}
    result = ToolResultItem(
        item_id="result_nested",
        exchange_id="exchange_nested",
        identity=call.identity,
        batch_id=call.batch_id,
        result=ToolResult(
            output=result_output,
            metadata=result_metadata,
            provenance={
                "source": "tests.worker",
                "details": provenance_details,
            },
        ),
    )
    builder.record_result(result)
    result_output["nested"]["value"] = "result-output-mutated"
    provenance_details["nested"]["value"] = "provenance-mutated"
    result_metadata["nested"]["value"] = "result-mutated"
    result.result.output["nested"]["value"] = "late mutation"

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
    recorded_result.result.output["nested"]["value"] = "snapshot-mutated"
    recorded_result.result.provenance["details"]["nested"][
        "value"
    ] = "snapshot-mutated"
    recorded_result.result.metadata["nested"]["value"] = "snapshot-mutated"

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
    assert persisted["items"][1]["result"]["provenance"]["details"]["nested"][
        "value"
    ] == "provenance-original"
    assert persisted["items"][1]["result"]["output"]["nested"][
        "value"
    ] == "result-output-original"

    persisted["items"][0]["parts"].clear()
    persisted["items"][1]["result"]["metadata"]["nested"][
        "value"
    ] = "serialized-mutated"
    fresh = log.to_persistence_dict()
    assert len(fresh["items"][0]["parts"]) == 3
    assert fresh["items"][1]["result"]["metadata"]["nested"][
        "value"
    ] == "result-original"


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
        "schema_version": "qitos.exchange_log.v2",
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


def test_strict_v2_reader_normalizes_all_malformed_payloads_to_typed_errors() -> None:
    base = ExchangeLog(log_id="strict_v2")
    base.append(
        UserItem(
            item_id="strict_user",
            exchange_id="strict_exchange",
            content=[ContentBlock(type="text", text="hello")],
        )
    )
    valid = base.to_persistence_dict()
    malformed: list[Any] = [None, [], "not-an-object"]

    def changed(*path_and_value: Any) -> dict[str, Any]:
        payload = copy.deepcopy(valid)
        *path, value = path_and_value
        target: Any = payload
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        return payload

    malformed.extend(
        [
            {**valid, "unknown": True},
            {key: value for key, value in valid.items() if key != "items"},
            changed("schema_version", "qitos.exchange_log.v999"),
            changed("log_id", 7),
            changed("items", {}),
            changed("queued_steering", {}),
            changed("items", 0, "unknown", True),
            changed("items", 0, "kind", "unknown"),
            changed("items", 0, "content", {}),
            changed("items", 0, "content", 0, "unknown", True),
            changed("items", 0, "content", 0, "text", object()),
            changed("items", 0, "metadata", {"value": float("nan")}),
            changed("items", 0, "metadata", {1: "non-string-key"}),
        ]
    )

    call = _call("strict_call", batch_id="strict_batch")
    result_log = ExchangeLog(log_id="strict_result")
    builder = result_log.append(
        _assistant_with_calls(
            call,
            item_id="strict_assistant",
            exchange_id="strict_result_exchange",
        )
    )
    assert builder is not None
    builder.record_result(
        _result(
            call,
            item_id="strict_result_item",
            exchange_id="strict_result_exchange",
        )
    )
    result_payload = result_log.to_persistence_dict()
    old_envelope = copy.deepcopy(result_payload)
    old_item = old_envelope["items"][1]
    old_item["status"] = old_item.pop("result")["status"]
    malformed.append(old_envelope)
    unknown_canonical = copy.deepcopy(result_payload)
    unknown_canonical["items"][1]["result"]["unknown"] = True
    malformed.append(unknown_canonical)
    wrong_result_shape = copy.deepcopy(result_payload)
    wrong_result_shape["items"][1]["result"] = []
    malformed.append(wrong_result_shape)

    for payload in malformed:
        with pytest.raises(ConversationValidationError):
            ExchangeLog.from_dict(payload)


def test_exchange_log_consumes_exact_c_fixture_without_outcome_duplication() -> None:
    fixture = json.loads(C_FIXTURE_PATH.read_text(encoding="utf-8"))
    canonical_payload = fixture["model_safe_source"]
    canonical = ToolResult.from_value(canonical_payload)
    call = ToolCall(
        identity=CallIdentity("fixture:c", canonical.action_id or "call-safe"),
        batch_id="fixture_c_batch",
        name=canonical.tool_name or "inspect",
        raw_arguments="{}",
        parsed_arguments={},
        parse_status=ArgumentParseStatus.PARSED,
    )
    log = ExchangeLog(log_id="c_fixture_consumer")
    builder = log.append(
        _assistant_with_calls(
            call,
            item_id="c_fixture_assistant",
            exchange_id="c_fixture_exchange",
        )
    )
    assert builder is not None
    builder.record_result(
        ToolResultItem(
            item_id="c_fixture_result",
            exchange_id="c_fixture_exchange",
            identity=call.identity,
            batch_id=call.batch_id,
            result=canonical,
        )
    )

    persisted = log.to_persistence_dict()
    result_payload = persisted["items"][1]["result"]
    assert result_payload == canonical.to_persistence_dict()
    assert "status" not in persisted["items"][1]
    assert "content" not in persisted["items"][1]
    assert "provenance" not in persisted["items"][1]
    assert ExchangeLog.from_dict(persisted).to_persistence_dict() == persisted


def test_exchange_log_restores_nested_historical_tool_result() -> None:
    call = _call("historical_nested", batch_id="historical_nested_batch")
    log = ExchangeLog(log_id="historical_nested_log")
    builder = log.append(
        _assistant_with_calls(
            call,
            item_id="historical_nested_assistant",
            exchange_id="historical_nested_exchange",
        )
    )
    assert builder is not None
    builder.record_result(
        _result(
            call,
            item_id="historical_nested_result",
            exchange_id="historical_nested_exchange",
        )
    )
    payload = log.to_persistence_dict()
    current_result = payload["items"][1]["result"]
    current_only = {
        "attempt_id",
        "effect_ref",
        "effect_state",
        "idempotency_ref",
        "retry_disposition",
        "reconciliation_required",
        "outcome_unknown",
        "late_result",
        "owner_generation",
        "stale_owner",
        "batch_closure",
    }
    historical_result = {
        key: value for key, value in current_result.items() if key not in current_only
    }
    historical_result["schema_version"] = HISTORICAL_TOOL_RESULT_SCHEMA_VERSION
    payload["items"][1]["result"] = historical_result

    restored = ExchangeLog.from_dict(payload)

    assert restored.items[1].result.schema_version == TOOL_RESULT_SCHEMA_VERSION
    assert restored.items[1].result.output == "result for tool_historical_nested"


def test_exchange_log_delegates_result_persistence_model_and_trace_views() -> None:
    call = _call("projection", batch_id="projection_batch")
    canonical = ToolResult.execution_error(
        tool_name=call.name,
        action_id=call.identity.call_id,
        code="tool_failed",
        error="token=result-secret /Users/example/private/error.log",
        output="token=output-secret /Users/example/private/output.log",
        recovery_hint="password=hint-secret /Users/example/private/hint.txt",
    )
    log = ExchangeLog(log_id="projection_log")
    builder = log.append(
        _assistant_with_calls(
            call,
            item_id="projection_assistant",
            exchange_id="projection_exchange",
        )
    )
    assert builder is not None
    builder.record_result(
        ToolResultItem(
            item_id="projection_result",
            exchange_id="projection_exchange",
            identity=call.identity,
            batch_id=call.batch_id,
            result=canonical,
        )
    )

    persistence = log.to_persistence_dict()["items"][1]["result"]
    model = log.to_model_dict()["items"][1]["result"]
    trace = log.to_trace_safe_dict()["items"][1]["result"]

    assert persistence["schema_version"] == TOOL_RESULT_SCHEMA_VERSION
    assert model["schema_version"] == TOOL_RESULT_MODEL_VIEW_VERSION
    assert trace["schema_version"] == TOOL_RESULT_TRACE_SAFE_VERSION
    assert persistence == canonical.to_persistence_dict()
    assert model == canonical.to_model_dict()
    assert trace == canonical.to_trace_safe_dict()
    assert "result-secret" not in json.dumps(model)
    assert "result-secret" not in json.dumps(trace)


def test_exchange_log_inherits_collision_safe_canonical_key_projections() -> None:
    call = _call("key_projection", batch_id="key_projection_batch")
    canonical = ToolResult(
        tool_name=call.name,
        action_id=call.identity.call_id,
        output={
            "/Users/alice/private/result": "path-key-value",
            "token=result-secret": "token-key-value",
            "[REDACTED_KEY_1]": "preexisting-placeholder",
            "benign": "unchanged",
        },
        next_action={
            "name": "read",
            "args": {"nested": [{"authorization": "token=next-secret"}]},
        },
        omitted={"/Users/alice/private/omitted": 1, "benign": 2},
    )
    log = ExchangeLog(log_id="key_projection_log")
    builder = log.append(
        _assistant_with_calls(
            call,
            item_id="key_projection_assistant",
            exchange_id="key_projection_exchange",
        )
    )
    assert builder is not None
    builder.record_result(
        ToolResultItem(
            item_id="key_projection_result",
            exchange_id="key_projection_exchange",
            identity=call.identity,
            batch_id=call.batch_id,
            result=canonical,
        )
    )

    persistence = log.to_persistence_dict()["items"][1]["result"]
    model = log.to_model_dict()["items"][1]["result"]
    trace = log.to_trace_safe_dict()["items"][1]["result"]
    rendered_model = json.dumps(model, sort_keys=True)
    rendered_trace = json.dumps(trace, sort_keys=True)

    assert persistence == canonical.to_persistence_dict()
    assert model == canonical.to_model_dict()
    assert trace == canonical.to_trace_safe_dict()
    assert persistence["output"]["/Users/alice/private/result"] == "path-key-value"
    for forbidden in (
        "/Users/alice/private/result",
        "token=result-secret",
        "authorization",
        "next-secret",
        "/Users/alice/private/omitted",
    ):
        assert forbidden not in rendered_model
        assert forbidden not in rendered_trace
    assert trace["loss"]["fields"]["model_output"]["redacted_keys"] == 2
    assert trace["loss"]["fields"]["next_action"]["redacted_keys"] == 1
    assert trace["loss"]["fields"]["omitted"]["redacted_keys"] == 1


def test_exchange_log_inherits_forced_secret_scalar_projection_without_runtime_changes() -> None:
    call = _call("scalar_projection", batch_id="scalar_projection_batch")
    unique_integer = 918273641
    canonical = ToolResult(
        tool_name=call.name,
        action_id=call.identity.call_id,
        output={
            "token": {
                "integer": unique_integer,
                "float": 765432.125,
                "boolean": True,
                "null": None,
            },
            "benign": {"integer": 4, "boolean": False, "null": None},
        },
        next_action={"name": "read", "args": {"api_key": 1123581321}},
        omitted={"token=hidden-field": 7},
    )
    log = ExchangeLog(log_id="scalar_projection_log")
    builder = log.append(
        _assistant_with_calls(
            call,
            item_id="scalar_projection_assistant",
            exchange_id="scalar_projection_exchange",
        )
    )
    assert builder is not None
    builder.record_result(
        ToolResultItem(
            item_id="scalar_projection_result",
            exchange_id="scalar_projection_exchange",
            identity=call.identity,
            batch_id=call.batch_id,
            result=canonical,
        )
    )

    persistence = log.to_persistence_dict()["items"][1]["result"]
    model = log.to_model_dict()["items"][1]["result"]
    trace = log.to_trace_safe_dict()["items"][1]["result"]
    projected = json.loads(model["model_output"])
    secret_subtree = next(
        value
        for key, value in projected.items()
        if key.startswith("[REDACTED_KEY_")
    )
    omitted_key = next(
        key for key in trace["omitted"] if key.startswith("[REDACTED_KEY_")
    )

    assert persistence == canonical.to_persistence_dict()
    assert model == canonical.to_model_dict()
    assert trace == canonical.to_trace_safe_dict()
    assert set(_scalar_leaves(secret_subtree)) == {"[REDACTED]"}
    assert projected["benign"] == {"integer": 4, "boolean": False, "null": None}
    assert trace["omitted"][omitted_key] == 7
    assert str(unique_integer) not in json.dumps(model, sort_keys=True)
    assert str(unique_integer) not in json.dumps(trace, sort_keys=True)


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
        status="error",
        reason="missing_worker",
    )

    results = recovered.results_for_batch("batch_synthetic_recovery")
    assert [result.identity.call_id for result in results] == ["second", "first"]
    assert results[0].item_id == "result_completed"
    assert results[0].synthetic is False
    assert results[1].synthetic is True
    assert results[1].result.status == "error"
    assert results[1].result.error_code == "missing_worker"


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("error", "failed"),
        ("skipped", "permission_blocked"),
        ("timed_out", "timed_out"),
        ("cancelled", "cancelled"),
        ("error", "missing_worker"),
    ],
)
def test_every_non_success_terminal_state_can_close_a_slot(
    status: str,
    reason: str,
) -> None:
    call = _call("terminal")
    log = ExchangeLog(log_id=f"log_{reason}")
    builder = log.append(_assistant_with_calls(call))
    assert builder is not None

    builder.close_missing(status=status, reason=reason)  # type: ignore[arg-type]

    result = log.results_for_batch("batch_1")[0]
    assert result.result.status == status
    assert result.result.error_code == reason
    assert result.synthetic is True
    assert result.closure_reason == reason
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
    builder.close_missing(status="cancelled", reason="test")
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
    builder.close_missing(status="cancelled", reason="test")
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
        assert case["schema_version"] == "qitos.exchange_log.v2"
        assert case["expected_invariant"]
        assert "expected_error" in case
        assert case["consumer_simulations"]
        assert isinstance(case["lossless"], bool)

    evidence = json.loads(
        QUALIFICATION_EVIDENCE_PATH.read_text(encoding="utf-8")
    )
    assert evidence["contract_id"] == "qitos.exchange_log"
    assert evidence["contract_version"] == "qitos.exchange_log.v2"
    assert evidence["fixture_path"].endswith("v3/semantic_fixtures.json")
    assert evidence["qualification_authority"] == "qitos.g1.integration_owner/v1"
    assert evidence["qualified"] is True


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
