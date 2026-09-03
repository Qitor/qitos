from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

from qitos.core.artifact import ArtifactRef
from qitos.core.context_transfer import (
    ContextTransferError,
    ContextTransferPlan,
    ContextTransferReceipt,
    execute_context_transfer,
)
from qitos.core.conversation import (
    ArgumentParseStatus,
    AssistantContent,
    AssistantItem,
    CallIdentity,
    ExchangeLog,
    SteeringItem,
    ToolCall,
    ToolResultItem,
    UserItem,
)
from qitos.core.multimodal import ContentBlock
from qitos.core.request_view import (
    CompactionReceipt,
    ContextBudget,
    ContinuationRef,
    ConversationSnapshotComponent,
    RequestTarget,
    RequestView,
    SteeringReceipt,
)
from qitos.core.session import (
    AgentIdentity,
    ContinuationIdentity,
    ResolverNamespace,
    ResolverReference,
    RunIdentity,
    SessionIdentity,
    SnapshotIdentity,
    WorkItemIdentity,
)
from qitos.core.tool_result import ToolResult
from qitos.core.work_graph import BudgetAllocation, CapabilityAllocation


DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64
AUTHORITY_NAMES = {
    "parent_grant",
    "destination_policy",
    "tool_environment",
    "artifact_access",
    "caller_transfer_policy",
}
FIXTURE = Path(__file__).parents[1] / "fixtures" / "context_transfer" / "v1" / "semantic_fixtures.json"
REPOSITORY_ROOT = Path(__file__).parents[2]
PRODUCER_MANIFEST = (
    REPOSITORY_ROOT
    / "tests"
    / "fixtures"
    / "context_transfer"
    / "v1"
    / "producer-manifest.json"
)


def _ids() -> dict[str, Any]:
    parent = WorkItemIdentity.generate()
    child = WorkItemIdentity.generate()
    return {
        "session": SessionIdentity.generate(),
        "run": RunIdentity.generate(),
        "parent": parent,
        "child": child,
        "snapshot": SnapshotIdentity.generate(),
        "agent": AgentIdentity.generate(),
    }


def _plan(
    *,
    policy: str = "full",
    recent: int = 0,
    custom: Sequence[str] = (),
    continuation: ContinuationRef | None = None,
    continuation_required: bool = False,
    losses: Sequence[str] = (),
    capabilities: Sequence[str] = ("tool.read",),
    limits: Mapping[str, int] = {"steps": 2, "tokens": 20},
    artifacts: Sequence[ArtifactRef] = (),
    required: Sequence[str] = ("conversation", "state", "authority"),
    constraints: Mapping[str, Any] = {},
    identities: dict[str, Any] | None = None,
) -> ContextTransferPlan:
    ids = identities or _ids()
    return ContextTransferPlan.create(
        operation_id="transfer.case",
        operation_kind="delegate",
        source_session_id=ids["session"],
        source_run_id=ids["run"],
        source_work_item_id=ids["parent"],
        source_snapshot_id=ids["snapshot"],
        source_head_generation=7,
        source_head_digest=DIGEST_A,
        destination_agent_id=ids["agent"],
        destination_agent_ref=ResolverReference(
            ResolverNamespace.AGENT, "child.agent", "agent.resolve"
        ),
        destination_provider="openai",
        destination_model="gpt.test",
        destination_api_mode="responses",
        context_policy=policy,
        context_policy_ref=f"policy.{policy}",
        context_policy_digest=DIGEST_B,
        recent_exchange_count=recent,
        custom_exchange_ids=custom,
        source_schema_id="state.source",
        destination_schema_id="state.destination",
        state_projector_ref="projector.test",
        state_projector_digest=DIGEST_C,
        state_projector_capability="state.project",
        state_fields=("task", "count"),
        continuation_required=continuation_required,
        continuation=continuation,
        budget_request=BudgetAllocation(
            "budget.case", ids["parent"], ids["child"], dict(limits)
        ),
        capability_request=CapabilityAllocation(
            "capability.case", ids["parent"], ids["child"], list(capabilities)
        ),
        artifact_refs=artifacts,
        required_components=required,
        approved_losses=losses,
        destination_constraints=constraints,
    )


def _log() -> ExchangeLog:
    log = ExchangeLog(log_id="log_transfer")
    log.append(
        UserItem(
            item_id="user_one",
            exchange_id="exchange_one",
            content=[
                ContentBlock(type="text", text="inspect"),
                ContentBlock(type="image_url", url="https://example.com/a.png"),
            ],
            metadata={"private_parent_note": "not child input"},
        )
    )
    builder = log.append(
        AssistantItem(
            item_id="assistant_two",
            exchange_id="exchange_two",
            parts=[
                AssistantContent(ContentBlock(type="text", text="working")),
                ToolCall(
                    CallIdentity("openai:responses", "call_a"),
                    "batch_two",
                    "read_a",
                    "{}",
                    {},
                    ArgumentParseStatus.PARSED,
                ),
                ToolCall(
                    CallIdentity("openai:responses", "call_b"),
                    "batch_two",
                    "read_b",
                    "{}",
                    {},
                    ArgumentParseStatus.PARSED,
                ),
            ],
        )
    )
    assert builder is not None
    builder.record_result(
        ToolResultItem(
            item_id="result_b",
            exchange_id="exchange_two",
            identity=CallIdentity("openai:responses", "call_b"),
            batch_id="batch_two",
            result=ToolResult(
                status="success", output="B", action_id="call_b", tool_name="read_b"
            ),
        )
    )
    builder.record_result(
        ToolResultItem(
            item_id="result_a",
            exchange_id="exchange_two",
            identity=CallIdentity("openai:responses", "call_a"),
            batch_id="batch_two",
            result=ToolResult(
                status="success", output="A", action_id="call_a", tool_name="read_a"
            ),
        )
    )
    log.append(
        UserItem(
            item_id="user_three",
            exchange_id="exchange_three",
            content=[ContentBlock(type="text", text="continue")],
        )
    )
    return log


def _component(log: ExchangeLog | None = None, *, compacted: bool = False) -> ConversationSnapshotComponent:
    source = log or _log()
    if not compacted:
        return ConversationSnapshotComponent.from_exchange_log(source)
    request = RequestView.from_exchange_log(
        source,
        target=RequestTarget("openai", "gpt.test", "https", "responses"),
        context_budget=ContextBudget(
            max_input_units=1400,
            reserved_output_units=100,
            protected_recent_exchanges=1,
        ),
    )
    receipt = CompactionReceipt(
        "compact.case",
        tuple(request.selection.omitted_exchange_ids),
        DIGEST_A,
        "compact.policy",
        ("early_exchange_summary",),
    )
    return ConversationSnapshotComponent.from_exchange_log(
        source, last_request_view=request, compaction_receipts=(receipt,)
    )


@dataclass
class Projector:
    projector_ref: str = "projector.test"
    projector_digest: str = DIGEST_C
    source_schema_id: str = "state.source"
    destination_schema_id: str = "state.destination"
    capabilities: frozenset[str] = frozenset({"state.project"})
    fail: bool = False

    def project(
        self, source_state: Mapping[str, Any], *, selected_fields: Sequence[str]
    ) -> Mapping[str, Any]:
        if self.fail:
            raise RuntimeError("third party projector failed")
        return {
            "state": {"task": source_state["task"], "counter": source_state["count"]},
            "selected_fields": list(selected_fields),
            "transformed_fields": ["state.count_to_counter"],
            "omitted_fields": ["parent_only"],
            "defaulted_fields": ["status"],
            "validation": "valid",
        }


def _authorities(
    *, capabilities: Sequence[str] = ("tool.read",), steps: int = 5, tokens: int = 100
) -> tuple[dict[str, set[str]], dict[str, dict[str, int]]]:
    return (
        {name: set(capabilities) for name in AUTHORITY_NAMES},
        {name: {"steps": steps, "tokens": tokens} for name in AUTHORITY_NAMES},
    )


def _execute(plan: ContextTransferPlan, **overrides: Any) -> ContextTransferReceipt:
    caps, budgets = _authorities()
    values = {
        "conversation": _component(),
        "observed_source_head_digest": plan.source_head_digest,
        "source_state": {"task": "demo", "count": 3, "parent_only": True},
        "projector": Projector(),
        "capability_authorities": caps,
        "budget_authorities": budgets,
        "destination_codec_capabilities": {
            "continuation",
            "multimodal_input",
            "native_tool_calls",
            "reasoning_input",
            "stateless_replay",
        },
        "available_continuation_refs": (
            {plan.continuation.reference_id.value} if plan.continuation else set()
        ),
        "available_artifact_ids": set(),
        "authorized_artifact_ids": set(),
        "evaluated_at": "2026-08-31T12:00:00+00:00",
    }
    values.update(overrides)
    return execute_context_transfer(plan, **values)


@pytest.mark.parametrize(
    ("policy", "recent", "custom", "expected"),
    [
        ("full", 0, (), ("exchange_one", "exchange_two", "exchange_three")),
        ("recent_window", 1, (), ("exchange_three",)),
        ("none", 0, (), ()),
        ("custom", 0, ("exchange_two",), ("exchange_two",)),
    ],
)
def test_context_selection_is_ordered_exchange_safe(policy, recent, custom, expected):
    required = ("state", "authority") if policy == "none" else ("conversation", "state", "authority")
    receipt = _execute(_plan(policy=policy, recent=recent, custom=custom, required=required))
    assert receipt.terminal_disposition == "accepted"
    assert receipt.selected_exchange_ids == expected
    if "exchange_two" in expected:
        assert [item["item_id"] for item in receipt.selected_items if item["exchange_id"] == "exchange_two"] == [
            "assistant_two", "result_b", "result_a"
        ]
    assert "conversation.metadata" in receipt.omitted_fields or policy != "full"


def test_compacted_context_carries_declared_loss():
    receipt = _execute(_plan(policy="compacted"), conversation=_component(compacted=True))
    assert receipt.terminal_disposition == "accepted"
    assert "compaction_receipts" in receipt.selected_components
    assert "early_exchange_summary" in receipt.loss_facts


def test_multimodal_parallel_batch_and_nested_input_are_immutable():
    component = _component()
    before = component.exchange_log.to_persistence_dict()
    receipt = _execute(_plan(), conversation=component)
    child = receipt.selected_items[0]
    child["content"][0]["text"] = "mutated"
    budget = receipt.plan.budget_request
    budget.limits["steps"] = 999
    assert receipt.selected_items[0]["content"][0]["text"] == "inspect"
    assert receipt.plan.budget_request.limits["steps"] == 2
    assert component.exchange_log.to_persistence_dict() == before
    assert receipt.selected_items[0]["content"][1]["type"] == "image_url"


def test_context_transfer_intersects_selected_semantics_with_provider_capability():
    receipt = _execute(
        _plan(),
        destination_codec_capabilities={"continuation", "stateless_replay"},
    )

    assert receipt.terminal_disposition == "rejected"
    assert receipt.failure_code == "provider_context_capability_mismatch"
    assert receipt.rejected_capabilities == (
        "multimodal_input",
        "native_tool_calls",
    )


def test_queued_steering_stays_a_durable_queue_and_is_not_model_input():
    log = ExchangeLog(log_id="queued_log")
    builder = log.append(
        AssistantItem(
            "assistant_open",
            "exchange_open",
            [ToolCall(CallIdentity("scope", "call_open"), "batch_open", "tool", "{}")],
        )
    )
    assert builder is not None
    log.queue_steering(
        SteeringItem(
            "steering_waiting",
            "exchange_open",
            [ContentBlock(type="text", text="change direction")],
        )
    )
    component = ConversationSnapshotComponent.from_exchange_log(
        log,
        steering_receipts=(
            SteeringReceipt("steering.receipt", 1, "steering_waiting", "queued", "boundary.open"),
        ),
    )
    plan = _plan()
    receipt = _execute(plan, conversation=component)
    assert receipt.terminal_disposition == "accepted"
    assert receipt.queued_steering[0]["item_id"] == "steering_waiting"
    assert "queued_steering" in receipt.selected_components
    assert all(item["item_id"] != "steering_waiting" for item in receipt.to_model_dict()["selected_items"])
    assert component.exchange_log.queued_steering[0].item_id == "steering_waiting"


def _continuation(*, model: str = "gpt.test", expiry: str = "2026-09-01T00:00:00+00:00") -> ContinuationRef:
    return ContinuationRef(
        ContinuationIdentity.generate(),
        "continuation.alias",
        "openai",
        model,
        "responses",
        payload_digest=DIGEST_A,
        expires_at=expiry,
    )


def test_continuation_preserved_only_on_exact_compatible_unexpired_codec():
    receipt = _execute(_plan(continuation=_continuation(), continuation_required=True))
    assert receipt.continuation_disposition == "preserved"
    assert "continuation_resolver" in receipt.reconstruction_requirements


@pytest.mark.parametrize(
    ("continuation", "codec", "code"),
    [
        (
            _continuation(model="other.model"),
            {
                "continuation",
                "multimodal_input",
                "native_tool_calls",
                "reasoning_input",
                "stateless_replay",
            },
            "continuation_incompatible",
        ),
        (
            _continuation(expiry="2026-08-30T00:00:00+00:00"),
            {
                "continuation",
                "multimodal_input",
                "native_tool_calls",
                "reasoning_input",
                "stateless_replay",
            },
            "continuation_expired",
        ),
        (
            _continuation(),
            {
                "multimodal_input",
                "native_tool_calls",
                "reasoning_input",
                "stateless_replay",
            },
            "continuation_incompatible",
        ),
    ],
)
def test_continuation_rejects_incompatible_expired_or_unsupported(continuation, codec, code):
    receipt = _execute(
        _plan(continuation=continuation, continuation_required=True),
        destination_codec_capabilities=codec,
    )
    assert receipt.terminal_disposition == "rejected"
    assert receipt.failure_code == code
    assert receipt.continuation_disposition == "rejected"


def test_explicit_stateless_reconstruction_is_loss_not_preservation():
    receipt = _execute(
        _plan(
            continuation=_continuation(model="other.model"),
            continuation_required=True,
            losses=("continuation_stateless_reconstruction",),
        )
    )
    assert receipt.terminal_disposition == "accepted"
    assert receipt.continuation_disposition == "stateless_reconstruction"
    assert "continuation_stateless_reconstruction" in receipt.loss_facts


def test_missing_continuation_resolver_fails_closed():
    receipt = _execute(
        _plan(continuation=_continuation(), continuation_required=True),
        available_continuation_refs=set(),
    )
    assert receipt.failure_code == "missing_continuation_resolver"


def test_state_projection_success_failure_unknown_and_missing_resolver():
    accepted = _execute(_plan())
    assert accepted.projected_state == {"counter": 3, "task": "demo"}
    assert "state.count_to_counter" in accepted.transformed_fields
    assert _execute(_plan(), projector=Projector(fail=True)).failure_code == "state_projection_failed"
    assert _execute(_plan(), projector=None).failure_code == "missing_state_projector"
    assert _execute(_plan(), source_state={"task": "demo"}).failure_code == "unknown_state_field"


def test_artifact_transfer_requires_resolution_and_explicit_sensitive_access():
    artifact = ArtifactRef("artifact.case", "store.main", DIGEST_A, "text/plain", 4, sensitivity="restricted")
    plan = _plan(artifacts=(artifact,), required=("conversation", "state", "authority", "artifacts"))
    denied = _execute(
        plan,
        available_artifact_ids={"artifact.case"},
        authorized_artifact_ids={"artifact.case"},
    )
    assert denied.failure_code == "artifact_access_denied"
    accepted = _execute(
        plan,
        available_artifact_ids={"artifact.case"},
        authorized_artifact_ids={"artifact.case"},
        authorized_sensitive_artifact_ids={"artifact.case"},
    )
    assert accepted.artifact_refs == (artifact,)
    assert "resolver_key" not in accepted.to_model_dict()["artifact_refs"][0]


def test_missing_required_artifact_rejects():
    artifact = ArtifactRef("artifact.case", "store.main", DIGEST_A, "text/plain", 4)
    receipt = _execute(
        _plan(artifacts=(artifact,)),
        authorized_artifact_ids={"artifact.case"},
    )
    assert receipt.failure_code == "missing_required_artifact"


def test_capability_and_budget_narrowing_and_escalation():
    accepted = _execute(_plan(capabilities=("tool.read",), limits={"steps": 2, "tokens": 20}))
    assert accepted.granted_capabilities == ("tool.read",)
    assert accepted.granted_budget is not None
    caps, budgets = _authorities()
    caps["destination_policy"] = set()
    rejected_cap = _execute(_plan(), capability_authorities=caps, budget_authorities=budgets)
    assert rejected_cap.failure_code == "capability_escalation"
    assert rejected_cap.rejected_capabilities == ("tool.read",)
    rejected_budget = _execute(_plan(limits={"steps": 6, "tokens": 20}))
    assert rejected_budget.failure_code == "budget_escalation"
    assert rejected_budget.rejected_budget_fields == ("steps",)


@pytest.mark.parametrize(
    "unsafe",
    [
        "/Users/alice/private.txt",
        "/home/alice/private.txt",
        r"C:\\Users\\alice\\private.txt",
        r"\\server\\share\\private.txt",
        "file:///tmp/private.txt",
        "~/private.txt",
        "http://127.0.0.1:8080/private",
        "http://192.168.1.2/internal",
        "Authorization: Bearer abcdefghijk",
        "sk-abcdefghijklmnop",
    ],
)
def test_plan_rejects_secret_paths_and_private_endpoints_without_echo(unsafe):
    with pytest.raises(ContextTransferError) as caught:
        _plan(constraints={"safe": unsafe})
    assert caught.value.code == "unsafe_persisted_value"
    assert unsafe not in str(caught.value)


@pytest.mark.parametrize("key", ["token", "headers", "cookie", "api_key", "secret"])
def test_plan_filters_sensitive_keys_before_hashing(key):
    with pytest.raises(ContextTransferError) as caught:
        _plan(constraints={key: "not-even-hashed"})
    assert caught.value.code == "unsafe_persisted_value"
    assert "not-even-hashed" not in str(caught.value)


def test_context_secret_filter_requires_explicit_loss_and_never_echoes():
    log = ExchangeLog(log_id="secret_log")
    log.append(UserItem("user_secret", "exchange_secret", [ContentBlock(type="text", text="token=abcdef")]))
    rejected = _execute(_plan(), conversation=_component(log))
    assert rejected.failure_code == "unapproved_context_loss"
    accepted = _execute(
        _plan(losses=("sensitive_context_filtering",)), conversation=_component(log)
    )
    rendered = accepted.canonical_json() + json.dumps(accepted.to_model_dict()) + json.dumps(accepted.to_diagnostic_dict())
    assert "abcdef" not in rendered
    assert "[filtered]" in rendered


def test_strict_round_trip_integrity_unknown_schema_and_projection_bounds():
    plan = _plan()
    assert ContextTransferPlan.from_json(plan.canonical_json()).to_dict() == plan.to_dict()
    receipt = _execute(plan)
    restored = ContextTransferReceipt.from_json(receipt.canonical_json())
    assert restored.to_dict() == receipt.to_dict()
    malformed = plan.to_dict()
    malformed["unknown"] = True
    with pytest.raises(ContextTransferError, match="unknown_field"):
        ContextTransferPlan.from_dict(malformed)
    tampered = receipt.to_dict()
    tampered["selected_item_ids"].append("item_tampered")
    with pytest.raises(ContextTransferError, match="integrity_mismatch"):
        ContextTransferReceipt.from_dict(tampered)
    model = receipt.to_model_dict()
    diagnostic = receipt.to_diagnostic_dict()
    assert "projected_state" not in model
    assert "plan" not in model
    assert "selected_items" not in diagnostic
    assert "projected_state" not in diagnostic


@dataclass
class ThirdPartySelector:
    policy_ref: str = "policy.custom"
    policy_digest: str = DIGEST_B

    def select_exchange_ids(self, log: ExchangeLog) -> Sequence[str]:
        assert isinstance(log, ExchangeLog)
        return ("exchange_three", "exchange_one")


def test_independent_policy_and_projector_protocol_conformance():
    receipt = _execute(
        _plan(policy="custom", custom=()),
        selection_policy=ThirdPartySelector(),
        projector=Projector(),
    )
    assert receipt.terminal_disposition == "accepted"
    assert receipt.selected_exchange_ids == ("exchange_one", "exchange_three")
    assert receipt.projected_state == {"counter": 3, "task": "demo"}


def test_fail_closed_destination_resolver_and_incomplete_authority():
    assert _execute(_plan(), destination_agent_resolved=False).failure_code == "missing_destination_resolver"
    caps, budgets = _authorities()
    caps.pop("artifact_access")
    receipt = _execute(_plan(), capability_authorities=caps, budget_authorities=budgets)
    assert receipt.failure_code == "incomplete_authority_sources"
    assert "child.agent" not in json.dumps(receipt.to_diagnostic_dict())
    assert _execute(_plan(), observed_source_head_digest=DIGEST_B).failure_code == "source_head_mismatch"


def test_destination_bound_and_non_json_live_objects_fail_closed():
    receipt = _execute(_plan(constraints={"max_selected_items": 1}))
    assert receipt.failure_code == "destination_context_limit"
    with pytest.raises(ContextTransferError) as caught:
        _plan(constraints={"worker": object()})
    assert caught.value.code == "non_json_value"


def test_producer_semantic_fixture_is_exact_and_complete():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["dispatch_source"] == "851f7902f15da670e72f4c04d7453cf37201aee7"
    assert fixture["plan_schema"] == "qitos.context_transfer_plan/v1"
    assert fixture["receipt_schema"] == "qitos.context_transfer_receipt/v1"
    case_ids = {item["case_id"] for item in fixture["cases"]}
    assert {
        "full_context", "recent_window", "compacted_context", "no_context",
        "custom_deterministic", "parallel_multimodal", "queued_steering",
        "continuation_exact", "continuation_incompatible", "continuation_expired",
        "continuation_stateless", "state_projection", "state_projection_failure",
        "artifact_private", "capability_escalation", "budget_escalation",
        "portable_boundary", "strict_round_trip", "third_party_protocols",
    } == case_ids


def test_producer_manifest_binds_committed_source_paths_digests_and_test_nodes():
    manifest = json.loads(PRODUCER_MANIFEST.read_text(encoding="utf-8"))
    producer_commit = manifest["producer_commit"]
    assert re.fullmatch(r"[0-9a-f]{40}", producer_commit)
    subprocess.run(
        ["git", "cat-file", "-e", f"{producer_commit}^{{commit}}"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "cat-file", "-e", f"{producer_commit}:qitos/core/context_transfer.py"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    paths = [item["path"] for item in manifest["producer_files"]]
    assert len(paths) == len(set(paths))
    for item in manifest["producer_files"]:
        relative = Path(item["path"])
        assert not relative.is_absolute()
        assert ".." not in relative.parts
        producer_file = REPOSITORY_ROOT / relative
        assert producer_file.is_file(), item["path"]
        assert hashlib.sha256(producer_file.read_bytes()).hexdigest() == item["sha256"]

    for node_id in manifest["producer_test_node_ids"]:
        path_text, separator, function_name = node_id.partition("::")
        assert separator and function_name.startswith("test_")
        test_path = REPOSITORY_ROOT / path_text
        assert test_path.is_file(), path_text
        tree = ast.parse(test_path.read_text(encoding="utf-8"))
        functions = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert function_name in functions, node_id
