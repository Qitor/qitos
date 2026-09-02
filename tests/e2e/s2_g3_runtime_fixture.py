"""Offline two-process fixture for the S2 G3 vertical convergence proof."""

from __future__ import annotations

import json
import sys
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Optional

from qitos.checkpoint import SqliteCheckpointStore
from qitos.checkpoint.session import (
    CheckpointConflictError,
    SessionSnapshotCommit,
)
from qitos.core.action import Action, ActionExecutionPolicy
from qitos.core.agent_module import AgentModule
from qitos.core.artifact import ArtifactRef
from qitos.core.conversation import (
    ArgumentParseStatus,
    AssistantContent,
    CallIdentity,
    ReasoningBlock,
    ToolCall,
)
from qitos.core.decision import Decision
from qitos.core.multimodal import ContentBlock
from qitos.core.request_view import ContinuationRef, RequestTarget
from qitos.core.session import (
    ContinuationIdentity,
    ResolverNamespace,
    ResolverReference,
    ResolverRegistry,
)
from qitos.core.state import StateSchema
from qitos.core.tool import tool
from qitos.core.tool_registry import ToolRegistry
from qitos.core.tool_result import ToolResult
from qitos.core.tool_runtime import ToolEffectDeclaration
from qitos.engine import Engine
from qitos.engine.runtime import DEFAULT_CHECKPOINT_REFERENCE, RuntimeComposition
from qitos.kit import ReActTextParser
from qitos.models.codec import (
    CodecReport,
    ProviderCapabilities,
    ProviderFailure,
    report_for_request,
)
from qitos.models.provider import (
    ContinuationResolution,
    ProviderDecodedResponse,
    normalize_provider_failure,
)
from qitos.qita.reader import default_reader
from qitos.tracing.readers import StoreTrajectoryReader
from qitos.tracing.sinks import (
    DurabilityReceipt,
    DurabilityStatus,
    SinkCapabilities,
)
from qitos.tracing.store import JsonTrajectoryStore
from qitos.tracing.trajectory import RecordKind


@dataclass
class VerticalState(StateSchema):
    reduced_batches: int = 0


class FileContinuationResolver:
    resolver_key = "continuation:s2-g3-file"

    def __init__(self, path: Path) -> None:
        self.path = path

    def capture(
        self,
        *,
        target: RequestTarget,
        payload: Any,
        attachment_id: str,
        expires_at: Optional[str] = None,
    ) -> ContinuationRef:
        resolution = ContinuationResolution(payload=payload, status="resolved")
        identity = ContinuationIdentity.generate()
        self.path.write_text(
            json.dumps(
                {
                    "identity": identity.to_dict(),
                    "payload": payload,
                    "payload_digest": resolution.payload_digest,
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return ContinuationRef(
            reference_id=identity,
            resolver_key=self.resolver_key,
            provider=target.provider,
            model=target.model,
            api_mode=target.api_mode,
            attachment_id=attachment_id,
            payload_digest=resolution.payload_digest,
            expires_at=expires_at,
        )

    def resolve(self, reference: ContinuationRef) -> ContinuationResolution:
        if reference.resolver_key != self.resolver_key or not self.path.exists():
            return ContinuationResolution(
                status="missing",
                reason_code="continuation_not_found",
            )
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if value["identity"] != reference.reference_id.to_dict():
            return ContinuationResolution(
                status="missing",
                reason_code="continuation_identity_mismatch",
            )
        return ContinuationResolution(
            status="resolved",
            payload=value["payload"],
            payload_digest=value["payload_digest"],
        )


class FixtureCodec:
    codec_id = "qitos.fixture.s2-g3"
    codec_version = "1"

    def encode(
        self,
        request,
        *,
        capabilities=None,
        transport=None,
        allow_loss=False,
    ):
        declared = capabilities or ProviderCapabilities.from_model(transport)
        report = report_for_request(
            request,
            declared,
            codec_id=self.codec_id,
            codec_version=self.codec_version,
            reasoning="preserved",
            continuation=("requested" if request.continuation else "none"),
            supported=request.capability_requirements,
        )
        return {"request_id": request.request_id}, report

    def apply_continuation(
        self,
        payload: dict[str, Any],
        resolution: ContinuationResolution,
        *,
        request,
        report: CodecReport,
    ):
        updated = dict(payload)
        updated["continuation"] = resolution.payload
        return updated, replace(report, continuation="resolved")

    def decode(self, response: Mapping[str, Any], *, request):
        if response["kind"] == "final":
            return ProviderDecodedResponse(
                parts=(
                    AssistantContent(
                        ContentBlock(type="text", text="Final Answer: complete")
                    ),
                ),
                finish_reason="stop",
                model_name=request.target.model,
            )
        batch_id = f"batch_{request.request_id}"
        provider_scope = "fixture:responses"
        calls = tuple(
            ToolCall(
                identity=CallIdentity(provider_scope, call_id),
                batch_id=batch_id,
                name=name,
                raw_arguments="{}",
                parsed_arguments={},
                parse_status=ArgumentParseStatus.PARSED,
            )
            for call_id, name in (
                ("call_effect", "committed_effect"),
                ("call_barrier", "barrier"),
                ("call_missing", "eligible_missing"),
            )
        )
        return ProviderDecodedResponse(
            parts=(
                ReasoningBlock(
                    provider_scope=provider_scope,
                    reference_id="reasoning_s2_g3",
                    block_type="summary",
                    summary="deterministic reasoning receipt",
                ),
                *calls,
            ),
            finish_reason="tool_calls",
            model_name=request.target.model,
            continuation_payload={"cursor": "after-tool-batch"},
            continuation_attachment_id="continuation_s2_g3",
        )


class FixtureProvider:
    model = "fixture-s2-g3"
    context_window = 8192
    max_tokens = 256
    qitos_harness_metadata = {
        "tool_policy": {"native_tool_call_preferred": True},
        "parser": "ReActTextParser",
        "protocol": "react_text_v1",
    }

    def __init__(self, resolver: FileContinuationResolver) -> None:
        self.qitos_continuation_resolver = resolver
        self._codec = FixtureCodec()

    def qitos_request_target(self):
        return RequestTarget(
            provider="fixture",
            model=self.model,
            transport="memory",
            api_mode="responses",
        )

    def qitos_provider_capabilities(self):
        return {
            "supported_features": (
                "text",
                "tool_calls",
                "tool_results",
                "tool_schemas",
                "parallel_tool_calls",
                "reasoning",
                "continuation",
                "ordered_interleaving",
            ),
            "reasoning_modes": ("preserve_if_supported",),
            "multimodal_types": ("text",),
            "supports_parallel_tool_calls": True,
            "supports_tool_schemas": True,
            "supports_continuation": True,
            "max_input_units": 8192,
        }

    def qitos_provider_codec(self):
        return self._codec

    def qitos_transport(self, payload):
        return {"kind": "final" if payload.get("continuation") else "tools"}

    def qitos_stream_transport(self, payload, *, on_delta=None):
        return self.qitos_transport(payload)

    def qitos_normalize_failure(self, error, *, report=None):
        return normalize_provider_failure(
            error,
            target=self.qitos_request_target(),
            report=report,
        )


class VerticalAgent(AgentModule[VerticalState, Any, Action]):
    name = "s2_g3_vertical"

    def __init__(
        self,
        *,
        counter_path: Path,
        resolver: FileContinuationResolver,
        barrier_entered: threading.Event,
        barrier_release: threading.Event,
    ) -> None:
        lock = threading.Lock()
        registry = ToolRegistry()

        def increment(name: str) -> None:
            with lock:
                value = json.loads(counter_path.read_text(encoding="utf-8"))
                value[name] += 1
                counter_path.write_text(
                    json.dumps(value, sort_keys=True),
                    encoding="utf-8",
                )

        @tool(
            name="committed_effect",
            concurrency_safe=True,
            effect=ToolEffectDeclaration("effect:s2-g3-counter"),
        )
        def committed_effect() -> ToolResult:
            increment("committed_effect")
            return ToolResult(
                output="committed",
                artifact_refs=(
                    ArtifactRef(
                        artifact_id="artifact:s2-g3-effect",
                        resolver_key="artifact-resolver:s2-g3",
                        sha256="a" * 64,
                        media_type="application/json",
                        byte_length=2,
                        model_summary="Committed effect receipt",
                    ),
                ),
            )

        @tool(name="barrier", concurrency_safe=True)
        def barrier() -> str:
            barrier_entered.set()
            if not barrier_release.wait(timeout=10):
                raise RuntimeError("deterministic barrier was not released")
            increment("barrier")
            return "released"

        @tool(name="eligible_missing", concurrency_safe=True)
        def eligible_missing() -> str:
            increment("eligible_missing")
            return "recovered"

        registry.register(committed_effect)
        registry.register(barrier)
        registry.register(eligible_missing)
        super().__init__(
            tool_registry=registry,
            llm=FixtureProvider(resolver),
            model_parser=ReActTextParser(),
            continuation_resolver=resolver,
        )

    def init_state(self, task: str, **kwargs: Any) -> VerticalState:
        return VerticalState(task=task, max_steps=3)

    def decide(self, state, observation):
        return None

    def reduce(self, state, observation, decision: Decision[Action]):
        if decision.mode == "act":
            state.reduced_batches += 1
        elif decision.mode == "final":
            state.final_result = decision.final_answer
        return state


class ControlTrajectorySink:
    def __init__(
        self,
        store: JsonTrajectoryStore,
        *,
        barrier_release: Optional[threading.Event] = None,
    ) -> None:
        self.capabilities = SinkCapabilities(
            sink_id="qitos.s2-g3-trajectory",
            durability_receipts=True,
        )
        self.store = store
        self.session = None
        self.barrier_release = barrier_release
        self.triggered = False
        self.worker_running_proof = False

    def receive(self, record):
        receipt = self.store.append(record)
        payload = record.payload.get("payload", {})
        if (
            self.barrier_release is not None
            and not self.triggered
            and payload.get("stage") == "tool_slot_terminal"
            and payload.get("slot_id") == "call_effect"
        ):
            self.triggered = True
            steering = self.session.steer("new constraint")
            if steering.disposition != "queued":
                raise AssertionError("steering was not queued in the open batch")
            accepted = self.session.pause()
            if accepted.status.value != "accepted":
                raise AssertionError("pause was not accepted")
            self.worker_running_proof = bool(
                not self.session._quiescence_receipt.migratable
                and self.session.lifecycle.value == "running"
            )
            self.barrier_release.set()
        return receipt

    def flush(self):
        return DurabilityReceipt(DurabilityStatus.PERSISTED)

    def close(self):
        return DurabilityReceipt(DurabilityStatus.PERSISTED)


def build_agent(root: Path, *, release_barrier: bool) -> tuple[VerticalAgent, Any, Any]:
    entered = threading.Event()
    release = threading.Event()
    if release_barrier:
        release.set()
    resolver = FileContinuationResolver(root / "continuation.json")
    agent = VerticalAgent(
        counter_path=root / "counters.json",
        resolver=resolver,
        barrier_entered=entered,
        barrier_release=release,
    )
    return agent, resolver, (entered, release)


def parent(root: Path) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    (root / "counters.json").write_text(
        json.dumps(
            {"committed_effect": 0, "barrier": 0, "eligible_missing": 0}
        ),
        encoding="utf-8",
    )
    checkpoint = SqliteCheckpointStore(str(root / "session.db"))
    trajectory = JsonTrajectoryStore(root / "trajectory.json")
    agent, _, events = build_agent(root, release_barrier=False)
    sink = ControlTrajectorySink(trajectory, barrier_release=events[1])
    runtime = RuntimeComposition(
        checkpoint_store=checkpoint,
        event_sink=sink,
        tool_execution_policy=ActionExecutionPolicy(
            mode="parallel",
            max_concurrency=2,
        ),
    )
    session = Engine(agent, runtime=runtime).session("vertical convergence")
    sink.session = session
    result = session.run()
    batch = session.inspect().tool_batch
    assert batch is not None
    payload = {
        "session_id": session.session_id.value,
        "run_id": session.run_id.value,
        "lifecycle": session.lifecycle.value,
        "generation": session.current_head.generation.value,
        "checkpoint_id": session.current_head.checkpoint_id.value,
        "snapshot_id": session.current_head.snapshot_id.value,
        "missing_slots": [slot.slot_id for slot in batch.missing_slots],
        "completion_order": list(batch.completion_order),
        "worker_running_proof": sink.worker_running_proof,
        "runtime_budget_max_steps": session.inspect().budget["max_steps"],
        "reduced_batches": result.state.reduced_batches,
        "counters": json.loads((root / "counters.json").read_text(encoding="utf-8")),
    }
    checkpoint.close()
    trajectory.close()
    return payload


def bind_snapshot_resources(
    *,
    checkpoint: SqliteCheckpointStore,
    snapshot: Any,
    agent: VerticalAgent,
    resolver: FileContinuationResolver,
    sink: ControlTrajectorySink,
) -> ResolverRegistry:
    registry = ResolverRegistry()
    registry.register_resource(DEFAULT_CHECKPOINT_REFERENCE, checkpoint)
    for raw in snapshot.payload["resolver_references"]:
        reference = ResolverReference.from_dict(raw)
        resources = {
            ResolverNamespace.AGENT: agent,
            ResolverNamespace.MODEL: agent.llm,
            ResolverNamespace.TOOL_REGISTRY: agent.tool_registry,
            ResolverNamespace.PROVIDER_CONTINUATION: resolver,
            ResolverNamespace.RUNTIME_EVENT_SINK: sink,
        }
        resource = resources.get(reference.namespace)
        if resource is not None:
            registry.register_resource(reference, resource)
    return registry


def child(root: Path, parent_receipt: Mapping[str, Any]) -> dict[str, Any]:
    checkpoint = SqliteCheckpointStore(str(root / "session.db"))
    trajectory = JsonTrajectoryStore(root / "trajectory.json")
    agent, resolver, _ = build_agent(root, release_barrier=True)
    sink = ControlTrajectorySink(trajectory)
    session_id = str(parent_receipt["session_id"])
    old_head = checkpoint.get_session_head(session_id)
    snapshot = checkpoint.get_session_snapshot(old_head.snapshot_id)
    registry = bind_snapshot_resources(
        checkpoint=checkpoint,
        snapshot=snapshot,
        agent=agent,
        resolver=resolver,
        sink=sink,
    )
    runtime = RuntimeComposition(
        checkpoint_store=checkpoint,
        resolvers=registry,
        event_sink=sink,
        tool_execution_policy=ActionExecutionPolicy(
            mode="parallel",
            max_concurrency=2,
        ),
    )
    session = Engine.restore(session_id, runtime=runtime)
    budget_continuity = (
        session._engine.budget.max_steps
        == int(parent_receipt["runtime_budget_max_steps"])
    )
    stale_rejected = False
    stale_payload = dict(snapshot.payload)
    stale_payload["head_generation"] = int(parent_receipt["generation"]) + 1
    try:
        checkpoint.commit_session_snapshot(
            SessionSnapshotCommit(
                session_id=session_id,
                snapshot_id="snapshot_ffffffffffffffffffffffffffffffff",
                checkpoint_id="checkpoint_ffffffffffffffffffffffffffffffff",
                owner_run_id=str(parent_receipt["run_id"]),
                lifecycle="paused",
                payload=stale_payload,
                expected_generation=int(parent_receipt["generation"]),
                expected_checkpoint_id=str(parent_receipt["checkpoint_id"]),
                expected_owner_run_id=str(parent_receipt["run_id"]),
            )
        )
    except CheckpointConflictError:
        stale_rejected = True

    result = session.run()
    runtime.flush_events()
    records = trajectory.read_session(session_id).records
    kinds = {record.kind for record in records}
    reader = StoreTrajectoryReader(trajectory)
    qita_view = reader.read_session(session_id)
    frozen_default = default_reader(root / "frozen-trace")
    head = checkpoint.get_session_head(session_id)
    final_snapshot = checkpoint.get_session_snapshot(head.snapshot_id)
    conversation = next(
        item
        for item in final_snapshot.payload["components"]
        if item["slot"] == "conversation"
    )["payload"]
    steering = conversation["steering_receipts"]
    payload = {
        "session_id": session_id,
        "run_id": session.run_id.value,
        "lifecycle": session.lifecycle.value,
        "final_result": result.state.final_result,
        "reduced_batches": result.state.reduced_batches,
        "counters": json.loads((root / "counters.json").read_text(encoding="utf-8")),
        "stale_rejected": stale_rejected,
        "steering_applied_once": (
            len(steering) == 1
            and steering[0]["disposition"] == "applied"
            and steering[0]["applied_once"] is True
        ),
        "continuation_count": len(conversation["continuation_refs"]),
        "artifact_count": len(conversation["artifact_refs"]),
        "budget_continuity": budget_continuity,
        "trajectory_record_count": len(records),
        "trajectory_kinds": sorted(kind.value for kind in kinds),
        "trajectory_session_match": all(
            record.session_id == session_id for record in records
        ),
        "trajectory_cursor_monotonic": [
            record.sequence for record in records
        ] == list(range(len(records))),
        "qita_read_only": (
            len(qita_view.records) == len(records)
            and not hasattr(reader, "append")
            and reader.capabilities.default_qualified is False
            and frozen_default.capabilities.default_qualified is True
        ),
        "runtime_sink_reports": len(runtime.event_sink_reports),
        "required_kinds_present": {
            kind.value: kind in kinds
            for kind in (
                RecordKind.SESSION,
                RecordKind.PAUSE,
                RecordKind.RESTORE,
                RecordKind.MODEL_REQUEST,
                RecordKind.MODEL_RESPONSE,
                RecordKind.REASONING,
                RecordKind.CONTINUATION,
                RecordKind.TOOL_BATCH,
                RecordKind.TOOL_SLOT,
                RecordKind.EFFECT,
                RecordKind.ARTIFACT,
            )
        },
    }
    checkpoint.close()
    trajectory.close()
    return payload


def main() -> None:
    phase = sys.argv[1]
    root = Path(sys.argv[2])
    if phase == "parent":
        value = parent(root)
    elif phase == "child":
        value = child(root, json.loads(sys.argv[3]))
    else:
        raise ValueError("phase must be parent or child")
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
