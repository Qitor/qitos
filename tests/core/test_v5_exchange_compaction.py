"""Explicit deterministic selection preserves canonical exchange facts."""
import hashlib
import json
from dataclasses import replace

import pytest

from qitos.core.context import ContextCompactionRequiredError
from qitos.core.conversation import (
    AssistantContent, AssistantItem, CallIdentity, ExchangeLog,
    IncompleteToolBatchError, OpaqueContinuationAttachment, SteeringItem,
    ToolCall, ToolResultItem, UserItem,
)
from qitos.core.multimodal import ContentBlock
from qitos.core.request_view import (
    ArtifactRef, ContextBudget, ContextBudgetExceededError, ContextContribution,
    ContinuationRef, ConversationSnapshotComponent, MissingArtifactError,
    RequestTarget, RequestView, UnsafeRequestBoundaryError,
    reconcile_steering_receipts, submit_steering,
)
from qitos.core.session import ContinuationIdentity
from qitos.core.tool_result import ToolResult
from qitos.kit.context.compaction import ClosedExchangeWindowCompactor
from qitos.kit.memory.adapter import MemorySourceAdapter
from qitos.kit.memory.markdown_file_memory import MarkdownFileMemory
from qitos.core.memory import MemoryRecord

TARGET = RequestTarget("fixture", "fixture", "fixture", "fixture")


def closed(index, size=60):
    return AssistantItem(f"a{index}", f"e{index}", [
        AssistantContent(ContentBlock(type="text", text=str(index) + "x" * size))
    ])


def log_bytes(log):
    return json.dumps(log.to_persistence_dict(), sort_keys=True).encode()


def build(log, maximum=3000, **options):
    options.setdefault("compaction_policy", ClosedExchangeWindowCompactor())
    return RequestView.from_exchange_log(log, target=TARGET, context_budget=ContextBudget(
        max_input_units=maximum, reserved_output_units=0,
        protected_recent_exchanges=2,
    ), **options)


def test_hundred_exchanges_two_budget_compactions_are_deterministic_and_immutable():
    log = ExchangeLog("hundred", items=[closed(index) for index in range(100)])
    before = log_bytes(log)
    first = build(log)
    assert first.selection.total_units > first.context_budget.available_input_units
    assert first.selection.selected_units <= 3000
    assert first.selection.selected_exchange_ids[-2:] == ("e98", "e99")
    assert first.selection.omitted_exchange_ids == tuple(
        f"e{index}" for index in range(len(first.selection.omitted_exchange_ids))
    )
    assert first.to_dict() == build(log).to_dict()
    assert log_bytes(log) == before
    for index in range(100, 110):
        log.append(closed(index))
    before_second = log_bytes(log)
    second = build(log)
    assert second.selection.total_units > 3000
    assert len(second.selection.omitted_exchange_ids) > len(first.selection.omitted_exchange_ids)
    assert second.selection.selected_exchange_ids[-2:] == ("e108", "e109")
    assert second.compaction_receipts[0].receipt_id != first.compaction_receipts[0].receipt_id
    assert log_bytes(log) == before_second
    receipt = second.compaction_receipts[0]
    payload = json.dumps(list(second.selected_items), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert receipt.output_digest == hashlib.sha256(payload.encode()).hexdigest()
    assert receipt.input_exchange_ids == second.selection.omitted_exchange_ids
    assert receipt.declared_losses == ("closed_exchange_omitted_without_summary",)
    assert receipt.model_reference is None


def test_default_is_not_implicit_compaction_and_previous_receipt_is_not_authorization():
    log = ExchangeLog("default", items=[closed(index) for index in range(20)])
    with pytest.raises(ContextCompactionRequiredError):
        build(log, compaction_policy=None)
    receipt = build(log).compaction_receipts
    with pytest.raises(ContextCompactionRequiredError):
        build(log, compaction_policy=None, compaction_receipts=receipt)


def parallel_log(required_artifact=False, leave_open=False):
    log = ExchangeLog("parallel")
    calls = [ToolCall(CallIdentity("fixture", str(i)), "batch", "tool", "{}") for i in range(2)]
    builder = log.append(AssistantItem("calls", "e0", calls))
    reference = ArtifactRef("artifact-one", "artifact:fixture", "a" * 64, "text/plain", 1,
                            model_summary="fixture", required=True)
    for i in (1, 0):
        if leave_open and i == 0:
            break
        builder.record_result(ToolResultItem(
            f"r{i}", "e0", calls[i].identity, "batch",
            ToolResult(status="success", output="x" * 2500,
                       artifact_refs=(reference,) if required_artifact else ()),
        ))
    return log


def test_parallel_reverse_completion_retained_or_omitted_as_one_exchange():
    log = parallel_log()
    for i in (1, 2):
        log.append(closed(i))
    before = log_bytes(log)
    full = build(log, 15000)
    assert full.to_dict()["correlation_facts"][0]["completion_order"] == ["1", "0"]
    compact = build(log)
    assert compact.selection.omitted_item_ids == ("calls", "r1", "r0")
    assert compact.to_dict()["correlation_facts"] == []
    assert log_bytes(log) == before


def test_open_batch_cannot_be_selected_or_compacted():
    log = parallel_log(leave_open=True)
    before = log_bytes(log)
    with pytest.raises(IncompleteToolBatchError):
        build(log)
    assert log_bytes(log) == before


@pytest.mark.parametrize("kind", ["recent", "required", "instruction", "context"])
def test_protected_or_required_over_budget_fails_without_mutation(kind):
    items = [closed(i) for i in range(3)]
    options = {}
    if kind == "recent":
        items[-1] = closed(2, 5000)
    elif kind == "required":
        items[0] = replace(closed(0, 5000), metadata={"required": True})
    elif kind == "instruction":
        options["instructions"] = [{"role": "system", "content": "x" * 5000}]
    else:
        options["context_contributions"] = [ContextContribution("required", "test", "x" * 5000, required=True)]
    log = ExchangeLog("required", items=items)
    before = log_bytes(log)
    with pytest.raises(UnsafeRequestBoundaryError):
        build(log, **options)
    assert log_bytes(log) == before


def test_required_artifact_missing_or_over_budget_is_not_silently_omitted():
    log = parallel_log(required_artifact=True)
    for i in (1, 2):
        log.append(closed(i))
    with pytest.raises(MissingArtifactError):
        build(log)
    with pytest.raises(ContextBudgetExceededError):
        build(log, available_artifact_ids=["artifact-one"])
    assert "e0" in build(log, 15000, available_artifact_ids=["artifact-one"]).selection.selected_exchange_ids


def test_steering_safe_boundary_consumes_once_and_pending_input_is_protected():
    log = parallel_log()
    receipt = submit_steering(log, "steer", sequence=1, boundary_id="safe", exchange_id="e1")
    first = build(log, 15000)
    assert receipt.item_id in first.selection.selected_item_ids
    reconciled = reconcile_steering_receipts(log, [receipt], boundary_id="next")
    assert len(reconciled) == 1 and reconciled[0].applied_once
    assert sum(isinstance(item, SteeringItem) for item in log.items) == 1
    log.append(closed(2))
    log.append(closed(3))
    # A steering-only exchange remains protected conservatively, even when old.
    assert receipt.item_id in build(log).selection.selected_item_ids
    pending = UserItem("pending", "e4", [ContentBlock(type="text", text="x" * 4000)])
    log.append(pending)
    with pytest.raises(ContextBudgetExceededError):
        build(log)


def test_continuation_and_opaque_attachment_protection():
    log = ExchangeLog("continuation", items=[closed(i) for i in range(20)])
    continuation = ContinuationRef(
        reference_id=ContinuationIdentity("continuation_20000000000000000000000000000001"),
        resolver_key="continuation:fixture", provider="fixture", model="fixture", api_mode="fixture",
    )
    with pytest.raises(ContextBudgetExceededError):
        build(log, continuation=continuation)
    assert not build(log, 15000, continuation=continuation).selection.omitted_exchange_ids
    attached = replace(closed(0, 4000), continuation_attachments=[
        OpaqueContinuationAttachment("opaque", "fixture", "fixture", {"token": "private"})
    ])
    log = ExchangeLog("attached", items=[attached, closed(1), closed(2)])
    with pytest.raises(ContextBudgetExceededError):
        build(log)


def test_request_snapshot_isolation_and_same_revision_reinjection_after_restore(tmp_path):
    memory = MarkdownFileMemory(str(tmp_path / "run.md"))
    memory.append(MemoryRecord("user", {"remembered-value": 17}, 0))
    adapter = MemorySourceAdapter(memory, namespace="run")
    recalled = adapter.contribute(None)
    log = ExchangeLog("restore", items=[closed(i) for i in range(20)])
    first = build(log, context_contributions=recalled)
    hidden = build(log, context_contributions=[replace(recalled[0], content=recalled[0].content_value, model_visible=False)])
    assert hidden.selection.omitted_context_ids == first.selection.selected_context_ids
    snapshot = ConversationSnapshotComponent.from_exchange_log(log, last_request_view=hidden)
    restored = ConversationSnapshotComponent.from_dict(snapshot.to_dict())
    third = build(restored.exchange_log, context_contributions=adapter.contribute(None))
    assert third.context_contributions[0]["revision"] == first.context_contributions[0]["revision"]
    third.context_contributions[0]["content"]["remembered-value"] = 99
    third.selected_items[0]["item_id"] = "changed"
    assert third.to_dict() == first.to_dict()
    assert log_bytes(restored.exchange_log) == log_bytes(log)


def test_optional_priority_cannot_displace_required_context():
    log = ExchangeLog("priority", items=[closed(0), closed(1)])
    values = [ContextContribution("optional", "test", "x" * 2500, priority=100),
              ContextContribution("required", "test", "x" * 500, required=True)]
    assert build(log, context_contributions=values).selection.selected_context_ids == ("required",)


def test_engine_context_probes_required_artifacts_before_any_provider_request():
    from types import SimpleNamespace
    from qitos.core.artifact import ArtifactContractError
    from qitos.engine._context_runtime import _ContextRuntime

    class Provider:
        model = "fixture"

        def call_raw(self, messages, **options):
            raise AssertionError("missing artifact must stop before provider dispatch")

    reference = ArtifactRef("missing", "artifact:fixture", "a" * 64, "text/plain", 1,
                            model_summary="fixture", required=True)
    runtime = _ContextRuntime(SimpleNamespace(agent=SimpleNamespace(config={})))
    with pytest.raises(ArtifactContractError) as failure:
        runtime.build_request_context(llm=Provider(), request_key="one", target=TARGET,
                                      artifact_refs=[reference])
    assert failure.value.code == "missing_required_artifact"


def test_nonmatching_or_absent_receipt_cannot_authorize_loss():
    class InvalidCompactor:
        policy_id = "invalid"

        def compact(self, **values):
            return None

    log = ExchangeLog("invalid", items=[closed(i) for i in range(20)])
    with pytest.raises(UnsafeRequestBoundaryError, match="matching explicit loss receipt"):
        build(log, compaction_policy=InvalidCompactor())
    with pytest.raises(UnsafeRequestBoundaryError):
        build(log, compaction_policy=type("BadDigest", (), {
            "policy_id": "invalid",
            "compact": lambda self, **values: replace(
                ClosedExchangeWindowCompactor().compact(**values),
                policy_id="invalid", output_digest="a" * 64,
            ),
        })())


def test_unanswered_input_in_reused_exchange_cannot_be_omitted_with_zero_window():
    log = ExchangeLog("reused", items=[closed(0), UserItem(
        "unanswered", "e0", [ContentBlock(type="text", text="x" * 4000)]
    )])
    with pytest.raises(ContextBudgetExceededError):
        RequestView.from_exchange_log(log, target=TARGET,
            compaction_policy=ClosedExchangeWindowCompactor(),
            context_budget=ContextBudget(max_input_units=3000, reserved_output_units=0,
                                         protected_recent_exchanges=0))
