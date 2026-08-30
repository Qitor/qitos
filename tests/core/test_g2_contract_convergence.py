"""Cross-line proofs for the G2 stable-contract convergence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from qitos.core.artifact import ArtifactRef
from qitos.core.conversation import ExchangeLog, UserItem
from qitos.core.multimodal import ContentBlock
from qitos.core.request_view import (
    CONVERSATION_SNAPSHOT_COMPONENT_CODEC,
    ContinuationRef,
    ConversationSnapshotComponent,
    RequestTarget,
    RequestView,
)
from qitos.core.session import (
    AgentIdentity,
    AgentStateSnapshotComponent,
    AttemptIdentity,
    ContinuationIdentity,
    CORE_SNAPSHOT_COMPONENT_CODECS,
    HeadGeneration,
    RunIdentity,
    SessionContractError,
    SessionErrorCode,
    SessionIdentity,
    SessionLifecycle,
    SessionSnapshot,
    SnapshotComponent,
    SnapshotIdentity,
    SnapshotTiming,
    TraceLineageSnapshotComponent,
    WorkItemIdentity,
)
from qitos.core.snapshot_composition import STABLE_SNAPSHOT_COMPONENT_REGISTRY
from qitos.core.tool_result import (
    HISTORICAL_TOOL_RESULT_SCHEMA_VERSION,
    TOOL_EFFECTS_SNAPSHOT_COMPONENT_CODEC,
    TOOL_RESULT_SCHEMA_VERSION,
    ToolEffectsSnapshotComponent,
    ToolResult,
    ToolResultCompatibilityReader,
)
from qitos.core.work_graph import (
    WORK_GRAPH_SNAPSHOT_COMPONENT_CODEC,
    WorkGraph,
    WorkGraphContractError,
    WorkGraphSnapshotComponent,
    WorkItem,
    WorkOwner,
)
from qitos.models.codec import ProviderCapabilities, ProviderFailure


ROOT = Path(__file__).parents[2]
STAMP = "2026-08-30T00:00:00Z"
SESSION = SessionIdentity("session_40000000000000000000000000000001")
RUN = RunIdentity("run_40000000000000000000000000000002")
SNAPSHOT = SnapshotIdentity("snapshot_40000000000000000000000000000003")
AGENT = AgentIdentity("agent_40000000000000000000000000000004")
WORK = WorkItemIdentity("work_item_40000000000000000000000000000005")
ATTEMPT = AttemptIdentity("attempt_40000000000000000000000000000006")
CONTINUATION = ContinuationIdentity(
    "continuation_40000000000000000000000000000007"
)


def _artifact() -> ArtifactRef:
    return ArtifactRef(
        artifact_id="artifact:g2-proof",
        resolver_key="artifact-resolver:g2-proof",
        sha256="b" * 64,
        media_type="application/json",
        byte_length=42,
        sensitivity="internal",
        provenance_digest="c" * 64,
        model_summary="The structured result is available through the artifact resolver.",
    )


def _core_components() -> list[SnapshotComponent]:
    by_slot = {item.slot: item for item in CORE_SNAPSHOT_COMPONENT_CODECS}
    return [
        SnapshotComponent.from_value(
            by_slot["agent_state"],
            AgentStateSnapshotComponent(AGENT, "g2_state", {"step": 2}),
        ),
        SnapshotComponent.from_value(
            by_slot["engine_progress"],
            {"phase": "check_stop", "safe_boundary": True},
        ),
        SnapshotComponent.from_value(
            by_slot["budget_capability"],
            {"steps_remaining": 4, "capability_digest": "d" * 64},
        ),
        SnapshotComponent.from_value(
            by_slot["trace_lineage"],
            TraceLineageSnapshotComponent(RUN, True),
        ),
    ]


def _conversation_component(artifact: ArtifactRef) -> ConversationSnapshotComponent:
    log = ExchangeLog(log_id="g2_conversation")
    log.append(
        UserItem(
            item_id="g2_user",
            exchange_id="g2_exchange",
            content=[ContentBlock(type="text", text="continue")],
        )
    )
    continuation = ContinuationRef(
        reference_id=CONTINUATION,
        resolver_key="continuation-resolver:g2",
        provider="declared",
        model="fixture",
        api_mode="responses",
    )
    return ConversationSnapshotComponent.from_exchange_log(
        log,
        continuation_refs=(continuation,),
        artifact_refs=(artifact,),
    )


def test_lane_c_directly_consumes_lane_a_identity_types_and_rejects_strings() -> None:
    item = WorkItem(
        work_item_id=WORK,
        session_ref=SESSION,
        task_ref="task:g2",
        lifecycle="running",
        owner=WorkOwner(AGENT, 0),
    )
    graph = WorkGraph("graph:g2")
    graph.add_work_item(item)

    payload = graph.to_persistence_dict()
    restored = WorkGraph.from_canonical_dict(payload)
    assert next(iter(restored.work_items)) == WORK
    assert payload["work_items"][0]["session_ref"] == SESSION.to_dict()
    assert payload["work_items"][0]["owner"]["agent_id"] == AGENT.to_dict()

    with pytest.raises(WorkGraphContractError) as caught:
        WorkOwner("agent:raw", 0)  # type: ignore[arg-type]
    assert caught.value.code == "invalid_identity_kind"


def test_lane_a_reader_decodes_real_lane_b_and_lane_c_components() -> None:
    artifact = _artifact()
    conversation = _conversation_component(artifact)
    effects = ToolEffectsSnapshotComponent(
        (ToolResult(output={"ok": True}, artifact_refs=(artifact,), attempt_id=ATTEMPT),)
    )
    work = WorkGraphSnapshotComponent("graph:g2", [WORK])
    components = [
        *_core_components(),
        SnapshotComponent.from_value(
            CONVERSATION_SNAPSHOT_COMPONENT_CODEC, conversation
        ),
        SnapshotComponent.from_value(TOOL_EFFECTS_SNAPSHOT_COMPONENT_CODEC, effects),
        SnapshotComponent.from_value(WORK_GRAPH_SNAPSHOT_COMPONENT_CODEC, work),
    ]
    snapshot = SessionSnapshot.create(
        snapshot_id=SNAPSHOT,
        session_id=SESSION,
        head_generation=HeadGeneration(2),
        lifecycle=SessionLifecycle.PAUSED,
        created_at=STAMP,
        timing=SnapshotTiming(STAMP, STAMP, STAMP),
        components=components,
        artifact_refs=(artifact,),
        component_registry=STABLE_SNAPSHOT_COMPONENT_REGISTRY,
    )

    restored = SessionSnapshot.from_dict(
        snapshot.to_dict(),
        component_registry=STABLE_SNAPSHOT_COMPONENT_REGISTRY,
    )
    decoded = {
        item.slot: item.decode(STABLE_SNAPSHOT_COMPONENT_REGISTRY)
        for item in restored.components
    }
    assert isinstance(decoded["conversation"], ConversationSnapshotComponent)
    assert isinstance(decoded["tool_effects"], ToolEffectsSnapshotComponent)
    assert decoded["work_graph"].unresolved_work_item_ids == [WORK]
    assert decoded["trace_lineage"].run_id == RUN
    assert restored.artifact_refs == (artifact,)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("owner", SessionErrorCode.UNKNOWN_COMPONENT_OWNER),
        ("schema", SessionErrorCode.UNSUPPORTED_COMPONENT_SCHEMA),
        ("digest", SessionErrorCode.COMPONENT_DIGEST_MISMATCH),
        ("missing", SessionErrorCode.MISSING_REQUIRED_COMPONENT),
    ],
)
def test_composed_snapshot_failures_are_typed(mutation: str, code: SessionErrorCode) -> None:
    artifact = _artifact()
    components = [
        *_core_components(),
        SnapshotComponent.from_value(
            CONVERSATION_SNAPSHOT_COMPONENT_CODEC,
            _conversation_component(artifact),
        ),
        SnapshotComponent.from_value(
            TOOL_EFFECTS_SNAPSHOT_COMPONENT_CODEC,
            ToolEffectsSnapshotComponent((ToolResult(),)),
        ),
        SnapshotComponent.from_value(
            WORK_GRAPH_SNAPSHOT_COMPONENT_CODEC,
            WorkGraphSnapshotComponent("graph:g2", [WORK]),
        ),
    ]
    if mutation == "missing":
        components.pop()
        with pytest.raises(SessionContractError) as caught:
            SessionSnapshot.create(
                snapshot_id=SNAPSHOT,
                session_id=SESSION,
                head_generation=HeadGeneration(1),
                lifecycle=SessionLifecycle.PAUSED,
                created_at=STAMP,
                timing=SnapshotTiming(STAMP),
                components=components,
                component_registry=STABLE_SNAPSHOT_COMPONENT_REGISTRY,
            )
    else:
        payload = components[-1].to_dict()
        if mutation == "owner":
            payload["owner"] = "unknown.owner"
        elif mutation == "schema":
            payload["schema_version"] = "qitos.work_graph.snapshot_component/v999"
        else:
            payload["digest"] = "0" * 64
        with pytest.raises(SessionContractError) as caught:
            component = SnapshotComponent.from_dict(payload)
            STABLE_SNAPSHOT_COMPONENT_REGISTRY.validate(
                [*components[:-1], component]
            )
    assert caught.value.error_code is code


def test_one_artifact_ref_round_trips_through_all_current_consumers() -> None:
    artifact = _artifact()
    log = _conversation_component(artifact).exchange_log
    target = RequestTarget("declared", "fixture", "fixture", "responses")
    request = RequestView.from_exchange_log(
        log,
        target=target,
        artifact_refs=(artifact,),
        available_artifact_ids=(artifact.artifact_id,),
    )
    result = ToolResult(output="stored", artifact_refs=(artifact,))

    assert RequestView.from_dict(request.to_dict()).artifact_refs == (artifact,)
    assert ToolResult.from_canonical_dict(result.to_dict()).artifact_refs == (artifact,)
    projection = artifact.to_model_projection()
    assert "resolver_key" not in projection
    assert "body" not in json.dumps(artifact.to_dict())


def test_historical_and_current_tool_result_readers_are_isolated() -> None:
    historical_path = (
        ROOT / "tests" / "fixtures" / "tool_results" / "v1" / "canonical_outcomes.json"
    )
    historical = json.loads(historical_path.read_text(encoding="utf-8"))
    old_payload = historical["cases"][0]["result"]
    assert old_payload["schema_version"] == HISTORICAL_TOOL_RESULT_SCHEMA_VERSION
    migrated = ToolResultCompatibilityReader.read(old_payload)
    assert migrated.schema_version == TOOL_RESULT_SCHEMA_VERSION

    current = ToolResult(output={"current": True}, attempt_id=ATTEMPT)
    current_payload = current.to_persistence_dict()
    assert current_payload["schema_version"] == TOOL_RESULT_SCHEMA_VERSION
    assert ToolResult.from_canonical_dict(current_payload) == current
    with pytest.raises(Exception):
        ToolResult.from_canonical_dict(old_payload)


class _DeclaredAdapter:
    def __init__(self, *, continuation: bool, label: str) -> None:
        self.model = label
        self.continuation = continuation

    def qitos_request_target(self) -> RequestTarget:
        return RequestTarget("same-provider", self.model, "same-transport", "same-api")

    def qitos_provider_capabilities(self) -> dict[str, Any]:
        features = ["text"]
        if self.continuation:
            features.extend(["continuation", "reasoning"])
        return {
            "supported_features": tuple(features),
            "reasoning_modes": (
                ("preserve_if_supported", "drop")
                if self.continuation
                else ("drop",)
            ),
            "multimodal_types": ("text",),
            "supports_parallel_tool_calls": False,
            "supports_tool_schemas": False,
            "supports_continuation": self.continuation,
            "max_input_units": 4096,
        }


def test_capabilities_depend_on_declarations_not_provider_or_class_names() -> None:
    first_type = type("OpenAIResponsesLookingName", (_DeclaredAdapter,), {})
    second_type = type("CompletelyDifferentName", (_DeclaredAdapter,), {})
    first = ProviderCapabilities.from_model(
        first_type(continuation=False, label="shared-model")
    )
    second = ProviderCapabilities.from_model(
        second_type(continuation=False, label="shared-model")
    )
    varied = ProviderCapabilities.from_model(
        second_type(continuation=True, label="shared-model")
    )

    assert first == second
    assert first.target.provider == varied.target.provider == "same-provider"
    assert first.supports_continuation is False
    assert varied.supports_continuation is True
    assert "reasoning" not in first.supported_features
    assert "reasoning" in varied.supported_features


def test_provider_and_work_graph_diagnostics_remove_adversarial_values() -> None:
    forbidden = (
        "Bearer top-secret",
        "/Users/private/repository",
        r"C:\\Users\\private\\repository",
        "file:///home/private/result",
        "http://127.0.0.1:9010/private",
        "cookie-secret",
    )
    failure = ProviderFailure(
        category="provider_exception",
        message=f"failed at {forbidden[0]}",
        provider=forbidden[4],
        api_mode="responses",
        redacted_details={
            "authorization": forbidden[0],
            "nested": [
                forbidden[1],
                {"headers": {"cookie": forbidden[5]}},
                forbidden[2],
                forbidden[3],
            ],
            "provider_payload": {"raw": "must-not-survive"},
        },
    )
    rendered = json.dumps(failure.to_dict(), sort_keys=True)
    assert all(value not in rendered for value in forbidden)
    assert "must-not-survive" not in rendered
    assert "authorization" not in rendered

    with pytest.raises(WorkGraphContractError) as caught:
        WorkOwner(forbidden[1], 0)  # type: ignore[arg-type]
    assert forbidden[1] not in str(caught.value)
