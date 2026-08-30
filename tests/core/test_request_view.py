from __future__ import annotations

import copy
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from qitos.core.conversation import (
    ArgumentParseStatus,
    AssistantContent,
    AssistantItem,
    CallIdentity,
    ExchangeLog,
    ReasoningReference,
    ToolCall,
    ToolBatchBuilder,
    ToolResultItem,
    UserItem,
)
from qitos.core.multimodal import ContentBlock
from qitos.core.request_view import (
    ArtifactRef,
    CompactionReceipt,
    ContextBudget,
    ContextContribution,
    ContinuationRef,
    ConversationCompatibilityReader,
    ConversationSnapshotComponent,
    IncompatibleContinuationError,
    MissingArtifactError,
    RequestContractError,
    RequestTarget,
    RequestView,
    UnsafeRequestBoundaryError,
    UnsafeSnapshotComponentError,
    UnsupportedRequestVersionError,
    reconcile_steering_receipts,
    submit_steering,
)
from qitos.core.tool_result import ToolResult


TARGET = RequestTarget(
    provider="openai",
    model="fixture-model",
    transport="openai",
    api_mode="responses",
)
FIXTURE_PATH = (
    Path(__file__).parents[1]
    / "fixtures"
    / "conversation"
    / "request_contracts.json"
)


def _call(call_id: str, *, batch_id: str, name: str) -> ToolCall:
    return ToolCall(
        identity=CallIdentity("openai:responses", call_id),
        batch_id=batch_id,
        name=name,
        raw_arguments="{}",
        parsed_arguments={},
        parse_status=ArgumentParseStatus.PARSED,
    )


def _result(call: ToolCall, *, item_id: str, exchange_id: str) -> ToolResultItem:
    return ToolResultItem(
        item_id=item_id,
        exchange_id=exchange_id,
        identity=call.identity,
        batch_id=call.batch_id,
        result=ToolResult(
            status="success",
            output={"call": call.identity.call_id},
            tool_name=call.name,
            action_id=call.identity.call_id,
            provenance={"source": "fixture.worker"},
        ),
    )


def _completed_parallel_log() -> ExchangeLog:
    log = ExchangeLog(log_id="request_source")
    log.append(
        UserItem(
            item_id="user_visual",
            exchange_id="exchange_visual",
            content=[
                ContentBlock(type="text", text="inspect"),
                ContentBlock(type="image_url", url="https://example.invalid/a.png"),
            ],
        )
    )
    first = _call("call_first", batch_id="batch_parallel", name="first")
    second = _call("call_second", batch_id="batch_parallel", name="second")
    builder = log.append(
        AssistantItem(
            item_id="assistant_parallel",
            exchange_id="exchange_tools",
            parts=[
                AssistantContent(ContentBlock(type="text", text="working")),
                ReasoningReference("openai:responses", "reasoning_ref"),
                first,
                second,
            ],
        )
    )
    assert builder is not None
    builder.record_result(
        _result(second, item_id="result_second", exchange_id="exchange_tools")
    )
    builder.record_result(
        _result(first, item_id="result_first", exchange_id="exchange_tools")
    )
    log.append(
        AssistantItem(
            item_id="assistant_final",
            exchange_id="exchange_final",
            parts=[AssistantContent(ContentBlock(type="text", text="done"))],
        )
    )
    return log


def _artifact() -> ArtifactRef:
    return ArtifactRef(
        artifact_id="artifact_fixture",
        resolver_key="artifact:fixture",
        sha256="a" * 64,
        media_type="application/json",
        byte_length=42,
        model_summary="Structured output is available through the artifact resolver.",
    )


def test_request_view_is_deterministic_immutable_and_ownership_isolated() -> None:
    log = _completed_parallel_log()
    instructions = [{"role": "system", "content": "Be precise."}]
    schemas = [{"type": "function", "function": {"name": "first"}}]

    first = log.request(
        target=TARGET,
        instructions=instructions,
        tool_schemas=schemas,
    )
    second = RequestView.from_exchange_log(
        log,
        target=TARGET,
        instructions=instructions,
        tool_schemas=schemas,
    )
    instructions[0]["content"] = "mutated"
    schemas[0]["function"]["name"] = "mutated"

    assert first == second
    assert first.request_id == second.request_id
    assert first.to_dict() == second.to_dict()
    assert first.instructions[0]["content"] == "Be precise."
    assert first.tool_schemas[0]["function"]["name"] == "first"
    returned = first.selected_items[0]
    returned["item_id"] = "mutated"
    assert first.selected_items[0]["item_id"] == "user_visual"
    with pytest.raises(FrozenInstanceError):
        first.request_id = "changed"  # type: ignore[misc]
    assert json.loads(json.dumps(first.to_dict(), allow_nan=False))


def test_request_view_preserves_multimodal_reasoning_parallel_and_both_orders() -> None:
    request = RequestView.from_exchange_log(_completed_parallel_log(), target=TARGET)

    assert "multimodal" in request.capability_requirements
    assert "reasoning" in request.capability_requirements
    assert "parallel_tool_calls" in request.capability_requirements
    correlation = request.to_dict()["correlation_facts"][0]
    assert correlation["declaration_order"] == ["call_first", "call_second"]
    assert correlation["completion_order"] == ["call_second", "call_first"]
    kinds = [item["kind"] for item in request.selected_items]
    assert kinds == ["user", "assistant", "tool_result", "tool_result", "assistant"]
    assistant = request.selected_items[1]
    assert [part["kind"] for part in assistant["parts"]] == [
        "content",
        "reasoning_reference",
        "tool_call",
        "tool_call",
    ]


def test_exchange_safe_budget_omits_whole_old_exchange_and_reports_context() -> None:
    log = _completed_parallel_log()
    context = [
        ContextContribution(
            contribution_id="critical",
            source="runtime:declared",
            content={"text": "required"},
            priority=10,
            required=True,
        ),
        ContextContribution(
            contribution_id="optional-large",
            source="memory:summary",
            content={"text": "x" * 600},
            priority=0,
        ),
    ]
    request = RequestView.from_exchange_log(
        log,
        target=TARGET,
        context_budget=ContextBudget(
            max_input_units=700,
            reserved_output_units=100,
            protected_recent_exchanges=1,
        ),
        context_contributions=context,
    )

    assert request.selection.selected_exchange_ids[-1] == "exchange_final"
    assert request.selection.omitted_exchange_ids == ("exchange_tools",)
    assert request.selection.selected_context_ids == ("critical",)
    assert request.selection.omitted_context_ids == ("optional-large",)
    assert request.selection.omitted_item_ids


def test_required_context_and_artifact_fail_typed_when_unavailable() -> None:
    log = _completed_parallel_log()
    with pytest.raises(UnsafeRequestBoundaryError):
        RequestView.from_exchange_log(
            log,
            target=TARGET,
            context_budget=ContextBudget(
                max_input_units=200,
                reserved_output_units=100,
                protected_recent_exchanges=0,
            ),
            context_contributions=[
                ContextContribution(
                    contribution_id="too-large",
                    source="declared",
                    content={"text": "x" * 500},
                    required=True,
                )
            ],
        )
    with pytest.raises(MissingArtifactError):
        RequestView.from_exchange_log(log, target=TARGET, artifact_refs=[_artifact()])


def test_compaction_artifact_and_context_facts_round_trip_without_blob_copy() -> None:
    receipt = CompactionReceipt(
        receipt_id="compact_fixture",
        input_exchange_ids=("exchange_visual",),
        output_digest="b" * 64,
        policy_id="summary-policy",
        declared_losses=("verbatim_wording",),
    )
    artifact = _artifact()
    request = RequestView.from_exchange_log(
        _completed_parallel_log(),
        target=TARGET,
        compaction_receipts=[receipt],
        artifact_refs=[artifact],
        available_artifact_ids=[artifact.artifact_id],
    )
    restored = RequestView.from_dict(request.to_dict())

    assert restored == request
    assert restored.compaction_receipts[0].declared_losses == ("verbatim_wording",)
    assert restored.artifact_refs[0].resolver_key == "artifact:fixture"
    assert "artifact body" not in json.dumps(restored.to_dict())


def test_continuation_is_provider_model_api_scoped_and_contains_only_reference() -> None:
    continuation = ContinuationRef(
        reference_id="continuation_fixture",
        resolver_key="continuation:fixture",
        provider="openai",
        model="fixture-model",
        api_mode="responses",
        attachment_id="attachment_fixture",
        payload_digest="c" * 64,
    )
    request = RequestView.from_exchange_log(
        _completed_parallel_log(), target=TARGET, continuation=continuation
    )

    rendered = json.dumps(request.to_dict())
    assert "continuation:fixture" in rendered
    assert "opaque_payload" not in rendered
    assert "continuation" in request.capability_requirements
    with pytest.raises(IncompatibleContinuationError):
        RequestView.from_exchange_log(
            _completed_parallel_log(),
            target=RequestTarget("anthropic", "fixture-model", "messages", "messages"),
            continuation=continuation,
        )


def test_steering_queue_order_reconcile_and_restore_are_exactly_once() -> None:
    log = ExchangeLog(log_id="steering_log")
    call = _call("call_open", batch_id="batch_open", name="read")
    builder = log.append(
        AssistantItem(
            item_id="assistant_open",
            exchange_id="exchange_open",
            parts=[call],
        )
    )
    assert builder is not None
    receipts = [
        submit_steering(
            log,
            "Focus on the parser",
            sequence=0,
            boundary_id="during_batch",
            exchange_id="exchange_next",
        ),
        submit_steering(
            log,
            "Then minimize the patch",
            sequence=1,
            boundary_id="during_batch",
            exchange_id="exchange_next",
        ),
    ]
    assert [item.disposition for item in receipts] == ["queued", "queued"]
    restored = ExchangeLog.from_dict(log.to_persistence_dict())
    restored_builder = restored.append  # prove ordinary append remains blocked
    assert callable(restored_builder)
    builder = ToolBatchBuilder(restored, "batch_open")
    builder.record_result(
        _result(call, item_id="result_open", exchange_id="exchange_open")
    )
    applied = reconcile_steering_receipts(
        restored, receipts, boundary_id="after_batch"
    )
    applied_again = reconcile_steering_receipts(
        restored, applied, boundary_id="after_restore"
    )

    assert [item.disposition for item in applied] == ["applied", "applied"]
    assert applied_again == applied
    steering_items = [item for item in restored.items if item.kind == "steering"]
    assert [item.metadata["sequence"] for item in steering_items] == [0, 1]
    assert len({item.item_id for item in steering_items}) == 2


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
def test_terminal_session_steering_is_typed_reject_without_log_mutation(status: str) -> None:
    log = ExchangeLog(log_id="terminal_steering")
    receipt = submit_steering(
        log,
        "too late",
        sequence=0,
        boundary_id="terminal",
        exchange_id="unused",
        session_status=status,
    )
    assert receipt.disposition == "rejected"
    assert receipt.reason_code == f"session_{status}"
    assert log.items == ()


def test_snapshot_component_round_trip_digest_and_pending_steering() -> None:
    log = ExchangeLog(log_id="component_log")
    call = _call("component_call", batch_id="component_batch", name="read")
    builder = log.append(
        AssistantItem(
            item_id="component_assistant",
            exchange_id="component_exchange",
            parts=[call],
        )
    )
    assert builder is not None
    receipt = submit_steering(
        log,
        "queued",
        sequence=0,
        boundary_id="unsafe",
        exchange_id="component_next",
    )
    component = ConversationSnapshotComponent.from_exchange_log(
        log, steering_receipts=[receipt]
    )
    payload = component.to_dict()
    restored = ConversationSnapshotComponent.from_dict(payload)

    assert restored.to_dict() == payload
    assert restored.exchange_log.to_persistence_dict() == log.to_persistence_dict()
    payload["exchange_log"]["log_id"] = "mutated"
    assert restored.exchange_log.log_id == "component_log"
    corrupt = component.to_dict()
    corrupt["digest"] = "0" * 64
    with pytest.raises(UnsafeSnapshotComponentError):
        ConversationSnapshotComponent.from_dict(corrupt)


def test_snapshot_continuation_requires_resolver_pointer_not_opaque_token() -> None:
    continuation = ContinuationRef(
        reference_id="ref_snapshot",
        resolver_key="continuation:snapshot",
        provider="openai",
        model="fixture-model",
        api_mode="responses",
        attachment_id="attachment_snapshot",
    )
    from qitos.core.conversation import OpaqueContinuationAttachment

    unsafe = ExchangeLog(log_id="unsafe_component")
    unsafe.append(
        AssistantItem(
            item_id="assistant_unsafe",
            exchange_id="exchange_unsafe",
            parts=[
                ReasoningReference(
                    "openai:responses",
                    "reasoning",
                    attachment_id="attachment_snapshot",
                )
            ],
            continuation_attachments=[
                OpaqueContinuationAttachment(
                    attachment_id="attachment_snapshot",
                    provider_scope="openai:responses",
                    api_mode="responses",
                    opaque_payload={"token": "opaque-secret"},
                )
            ],
        )
    )
    with pytest.raises(UnsafeSnapshotComponentError):
        ConversationSnapshotComponent.from_exchange_log(
            unsafe, continuation_refs=[continuation]
        )

    safe_payload = unsafe.to_persistence_dict()
    safe_payload["items"][0]["continuation_attachments"][0]["opaque_payload"] = {
        "resolver_ref": "ref_snapshot"
    }
    safe = ExchangeLog.from_dict(safe_payload)
    component = ConversationSnapshotComponent.from_exchange_log(
        safe, continuation_refs=[continuation]
    )
    rendered = json.dumps(component.to_dict())
    assert "opaque-secret" not in rendered
    assert '"resolver_ref": "ref_snapshot"' in rendered


def test_strict_request_component_and_compatibility_readers() -> None:
    request = RequestView.from_exchange_log(_completed_parallel_log(), target=TARGET)
    valid = request.to_dict()
    malformed = [None, [], "bad", {**valid, "unknown": True}]
    wrong_version = copy.deepcopy(valid)
    wrong_version["schema_version"] = "qitos.request_view/v999"
    malformed.append(wrong_version)
    non_finite = copy.deepcopy(valid)
    non_finite["provenance"]["bad"] = float("nan")
    malformed.append(non_finite)
    non_json = copy.deepcopy(valid)
    non_json["provenance"]["bad"] = object()
    malformed.append(non_json)
    for payload in malformed:
        with pytest.raises((RequestContractError, UnsupportedRequestVersionError)):
            RequestView.from_dict(payload)

    current = ConversationCompatibilityReader.read(
        _completed_parallel_log().to_persistence_dict()
    )
    assert current.log_id == "request_source"
    compat = ConversationCompatibilityReader.read(
        {
            "schema_version": "qitos.history_message_envelope/v1",
            "provider_scope": "legacy:test",
            "messages": [
                {
                    "role": "user",
                    "step_id": 1,
                    "content": "hello",
                    "tool_calls": [],
                    "tool_call_id": None,
                    "name": None,
                    "metadata": {},
                    "native_items": [],
                }
            ],
        }
    )
    assert compat.items[0].kind == "user"
    with pytest.raises(UnsupportedRequestVersionError):
        ConversationCompatibilityReader.read(
            {"schema_version": "unknown", "provider_scope": "x", "messages": []}
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"resolver_key": "/Users/example/private/blob"},
        {"resolver_key": "C:\\private\\blob"},
    ],
)
def test_reference_contract_rejects_raw_host_paths(kwargs: dict[str, str]) -> None:
    with pytest.raises(RequestContractError):
        ArtifactRef(
            artifact_id="bad",
            sha256="d" * 64,
            media_type="text/plain",
            byte_length=1,
            **kwargs,
        )


def test_stable_path_fixture_manifest_and_samples_cover_required_contracts() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    required = {
        "ordinary_text",
        "multimodal",
        "one_tool_call",
        "native_parallel_tool_calls",
        "completion_order_differs_from_declaration",
        "multiple_assistant_tool_rounds",
        "preserved_reasoning",
        "opaque_continuation",
        "incompatible_continuation",
        "queued_steering",
        "multiple_steering_messages",
        "restore_with_pending_steering",
        "context_omission",
        "compaction",
        "artifact_reference",
        "provider_capability_mismatch",
        "provider_refusal",
        "provider_exception",
        "malformed_response",
        "lossy_codec",
        "lossless_codec",
    }
    assert fixture["fixture_version"] == "qitos.request_contract_fixture/v1"
    assert {case["name"] for case in fixture["cases"]} == required
    request = RequestView.from_dict(fixture["samples"]["request_view"])
    component = ConversationSnapshotComponent.from_dict(
        fixture["samples"]["conversation_component"]
    )
    assert request.request_id == "request_d88c0c3df61a2909c2379816"
    assert component.exchange_log.log_id == "fixture_request_log"
