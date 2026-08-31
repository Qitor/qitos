"""Framework-implementer conformance for S2 Lane A runtime seams."""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Iterator, Optional, Sequence

import pytest

import qitos
from qitos.checkpoint import (
    ATOMIC_SESSION_COMMIT,
    Checkpoint,
    CheckpointCapabilityError,
    CheckpointConfig,
    CheckpointConflictError,
    CheckpointMetadata,
    CheckpointSessionErrorCode,
    CheckpointStore,
    CheckpointTuple,
    InMemoryCheckpointStore,
    PendingWrite,
    SESSION_PERSISTENCE_CAPABILITIES,
    SessionCommitReceipt,
    SessionHeadRecord,
    SessionSnapshotCommit,
    SessionSnapshotRecord,
    SqliteCheckpointStore,
    StateVersions,
)
from qitos.core.action import Action, ActionExecutionPolicy
from qitos.core.agent_module import AgentModule
from qitos.core.decision import Decision
from qitos.core.session import (
    ResolvedResource,
    ResolverNamespace,
    ResolverRegistry,
    SessionContractError,
    SessionErrorCode,
    SnapshotComponentCodec,
)
from qitos.core.state import StateSchema
from qitos.core.tool import tool
from qitos.core.tool_registry import ToolRegistry
from qitos.engine import Engine
from qitos.engine.runtime import (
    AGENT_CAPABILITY,
    CHECKPOINT_STORE_CAPABILITY,
    DEFAULT_CHECKPOINT_REFERENCE,
    LifecyclePolicy,
    RuntimeComposition,
    RuntimeSnapshotContext,
    TOOL_REGISTRY_CAPABILITY,
    RuntimeCompositionConfig,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "s2" / "lane_a"


class ThirdPartyCheckpointStore(CheckpointStore):
    """Public-protocol-only implementation with no SQLite/private dependency."""

    def __init__(self) -> None:
        self.heads: dict[str, SessionHeadRecord] = {}
        self.snapshots: dict[str, SessionSnapshotRecord] = {}
        self.lineage: dict[str, list[str]] = {}

    # Legacy checkpoint surface is deliberately independent and unused here.
    def put(
        self,
        config: CheckpointConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: StateVersions,
    ) -> CheckpointConfig:
        raise NotImplementedError

    def get_tuple(self, config: CheckpointConfig) -> Optional[CheckpointTuple]:
        return None

    def list(
        self,
        config: CheckpointConfig,
        *,
        limit: Optional[int] = None,
        before: Optional[CheckpointConfig] = None,
    ) -> Iterator[CheckpointTuple]:
        return iter(())

    def put_writes(
        self,
        config: CheckpointConfig,
        writes: Sequence[PendingWrite],
        task_id: str,
    ) -> None:
        return None

    def delete(self, config: CheckpointConfig) -> None:
        return None

    def session_capabilities(self) -> frozenset[str]:
        return SESSION_PERSISTENCE_CAPABILITIES

    def commit_session_snapshot(
        self, request: SessionSnapshotCommit
    ) -> SessionCommitReceipt:
        current = self.heads.get(request.session_id)
        if request.expected_generation is None:
            if current is not None:
                self._conflict(CheckpointSessionErrorCode.GENERATION_CONFLICT)
        else:
            if current is None or current.generation != request.expected_generation:
                self._conflict(CheckpointSessionErrorCode.GENERATION_CONFLICT)
            assert current is not None
            if current.checkpoint_id != request.expected_checkpoint_id:
                self._conflict(CheckpointSessionErrorCode.CHECKPOINT_CONFLICT)
            if current.owner_run_id != request.expected_owner_run_id:
                self._conflict(CheckpointSessionErrorCode.OWNER_CONFLICT)
        if request.snapshot_id in self.snapshots:
            self._conflict(CheckpointSessionErrorCode.CHECKPOINT_CONFLICT)
        parent = current.checkpoint_id if current is not None else None
        record = SessionSnapshotRecord(
            session_id=request.session_id,
            snapshot_id=request.snapshot_id,
            checkpoint_id=request.checkpoint_id,
            generation=request.target_generation,
            owner_run_id=request.owner_run_id,
            lifecycle=request.lifecycle,
            payload=copy.deepcopy(request.payload),
            parent_checkpoint_id=parent,
        )
        self.snapshots[request.snapshot_id] = record
        self.lineage.setdefault(request.session_id, []).append(request.snapshot_id)
        head = SessionHeadRecord(
            session_id=request.session_id,
            snapshot_id=request.snapshot_id,
            checkpoint_id=request.checkpoint_id,
            generation=request.target_generation,
            owner_run_id=request.owner_run_id,
            lifecycle=request.lifecycle,
        )
        self.heads[request.session_id] = head
        return SessionCommitReceipt(
            session_id=head.session_id,
            snapshot_id=head.snapshot_id,
            checkpoint_id=head.checkpoint_id,
            generation=head.generation,
            owner_run_id=head.owner_run_id,
            lifecycle=head.lifecycle,
            durable=True,
            store_kind="third_party",
        )

    def get_session_head(self, session_id: str) -> Optional[SessionHeadRecord]:
        return copy.deepcopy(self.heads.get(session_id))

    def get_session_snapshot(
        self, snapshot_id: str
    ) -> Optional[SessionSnapshotRecord]:
        record = self.snapshots.get(snapshot_id)
        return record.isolated_copy() if record is not None else None

    def list_session_lineage(
        self, session_id: str, *, limit: Optional[int] = None
    ) -> Iterator[SessionSnapshotRecord]:
        ids = list(reversed(self.lineage.get(session_id, [])))
        if limit is not None:
            ids = ids[:limit]
        return iter(self.snapshots[item].isolated_copy() for item in ids)

    @staticmethod
    def _conflict(code: CheckpointSessionErrorCode) -> None:
        raise CheckpointConflictError(
            code,
            "Third-party CAS rejected the stale request.",
            recoverable=code is not CheckpointSessionErrorCode.OWNER_CONFLICT,
            capability=ATOMIC_SESSION_COMMIT,
        )


class OldStyleCheckpointStore(ThirdPartyCheckpointStore):
    def session_capabilities(self) -> frozenset[str]:
        return frozenset()

    def commit_session_snapshot(self, request):
        return CheckpointStore.commit_session_snapshot(self, request)


@dataclass
class ConformanceState(StateSchema):
    committed_effects: int = 0


class ConformanceAgent(AgentModule[ConformanceState, dict[str, Any], Action]):
    name = "conformance"

    def __init__(self) -> None:
        registry = ToolRegistry()
        self.calls = 0

        @tool(name="effect")
        def effect() -> int:
            self.calls += 1
            return self.calls

        registry.register(effect)
        super().__init__(tool_registry=registry)

    def init_state(self, task: str, **kwargs: Any) -> ConformanceState:
        return ConformanceState(task=task, max_steps=3)

    def decide(self, state, observation):
        if state.current_step == 0:
            return Decision.act([Action(name="effect", args={})])
        return Decision.final("complete")

    def reduce(self, state, observation, decision):
        if decision.mode == "act":
            state.committed_effects += 1
        elif decision.mode == "final":
            state.final_result = decision.final_answer
        return state


class PauseAfterEffect(LifecyclePolicy):
    policy_id = "tests.pause_after_effect"

    def should_pause(self, context: RuntimeSnapshotContext) -> bool:
        return context.step_id == 0


class CustomSnapshotComponent:
    def __init__(self) -> None:
        self.restored: list[int] = []
        self.codec = SnapshotComponentCodec(
            slot="extension_probe",
            owner="tests.extension",
            schema_version="tests.extension.probe/v1",
            required=True,
            encode=self._encode,
            decode=self._decode,
        )

    @staticmethod
    def _encode(value: Any) -> dict[str, Any]:
        return {"committed_effects": int(value["committed_effects"])}

    @staticmethod
    def _decode(value: Any) -> dict[str, Any]:
        return {"committed_effects": int(value["committed_effects"])}

    def capture(self, context: RuntimeSnapshotContext) -> dict[str, int]:
        return {"committed_effects": context.state.committed_effects}

    def restore(self, value: Any, context: RuntimeSnapshotContext) -> None:
        self.restored.append(int(value["committed_effects"]))


@pytest.fixture(params=["memory", "sqlite", "third_party"])
def conforming_store(request: pytest.FixtureRequest, tmp_path):
    if request.param == "memory":
        return InMemoryCheckpointStore()
    if request.param == "sqlite":
        return SqliteCheckpointStore(str(tmp_path / "conformance.db"))
    return ThirdPartyCheckpointStore()


def test_reference_and_third_party_stores_share_public_semantics(
    conforming_store,
) -> None:
    request = SessionSnapshotCommit(
        session_id="session_1111111111111111",
        snapshot_id="snapshot_1111111111111111",
        checkpoint_id="checkpoint_1111111111111111",
        owner_run_id="run_1111111111111111",
        lifecycle="created",
        payload={"head_generation": 0, "lifecycle": "created", "value": [1]},
    )
    receipt = conforming_store.commit_session_snapshot(request)
    head = conforming_store.get_session_head(request.session_id)
    snapshot = conforming_store.get_session_snapshot(request.snapshot_id)
    assert receipt.durable is True
    assert head is not None and head.generation == 0
    assert snapshot is not None and snapshot.payload["value"] == [1]
    snapshot.payload["value"].append(2)
    assert conforming_store.get_session_snapshot(request.snapshot_id).payload[
        "value"
    ] == [1]
    if isinstance(conforming_store, SqliteCheckpointStore):
        conforming_store.close()


def test_custom_resolver_and_snapshot_component_restore_without_duplicate_effect() -> None:
    store = ThirdPartyCheckpointStore()
    component = CustomSnapshotComponent()
    parent_runtime = RuntimeComposition(
        checkpoint_store=store,
        lifecycle_policy=PauseAfterEffect(),
        snapshot_components=(component,),
    )
    parent_agent = ConformanceAgent()
    session = Engine(parent_agent, runtime=parent_runtime).session("effect once")
    session.run()
    assert parent_agent.calls == 1

    child_agent = ConformanceAgent()
    resolver_calls: list[ResolverNamespace] = []

    def checkpoint_resolver(reference):
        resolver_calls.append(reference.namespace)
        return ResolvedResource(
            ResolverNamespace.CHECKPOINT_STORE,
            frozenset({CHECKPOINT_STORE_CAPABILITY}),
            store,
        )

    def agent_resolver(reference):
        resolver_calls.append(reference.namespace)
        return ResolvedResource(
            ResolverNamespace.AGENT,
            frozenset({AGENT_CAPABILITY}),
            child_agent,
        )

    def tools_resolver(reference):
        resolver_calls.append(reference.namespace)
        return ResolvedResource(
            ResolverNamespace.TOOL_REGISTRY,
            frozenset({TOOL_REGISTRY_CAPABILITY}),
            child_agent.tool_registry,
        )

    resolvers = ResolverRegistry(
        {
            ResolverNamespace.CHECKPOINT_STORE: checkpoint_resolver,
            ResolverNamespace.AGENT: agent_resolver,
            ResolverNamespace.TOOL_REGISTRY: tools_resolver,
        }
    )
    child_runtime = RuntimeComposition.from_resolvers(
        resolvers,
        lifecycle_policy=PauseAfterEffect(),
        snapshot_components=(component,),
    )
    restored = Engine.restore(session.session_id, runtime=child_runtime)
    result = restored.run()

    assert set(resolver_calls) == {
        ResolverNamespace.CHECKPOINT_STORE,
        ResolverNamespace.AGENT,
        ResolverNamespace.TOOL_REGISTRY,
    }
    assert component.restored[-1] == 1
    assert result.state.committed_effects == 1
    assert child_agent.calls == 0


def test_old_store_reports_typed_unsupported_capability() -> None:
    runtime = RuntimeComposition(checkpoint_store=OldStyleCheckpointStore())
    with pytest.raises(CheckpointCapabilityError) as unsupported:
        Engine(ConformanceAgent(), runtime=runtime).session("cannot persist")
    assert unsupported.value.error_code is CheckpointSessionErrorCode.UNSUPPORTED_CAPABILITY


class CorruptingViewStore(ThirdPartyCheckpointStore):
    def __init__(self, delegate: ThirdPartyCheckpointStore) -> None:
        self.delegate = delegate

    def session_capabilities(self):
        return self.delegate.session_capabilities()

    def get_session_head(self, session_id):
        return self.delegate.get_session_head(session_id)

    def get_session_snapshot(self, snapshot_id):
        record = self.delegate.get_session_snapshot(snapshot_id)
        if record is None:
            return None
        payload = copy.deepcopy(record.payload)
        payload["head_generation"] += 1
        return SessionSnapshotRecord(
            session_id=record.session_id,
            snapshot_id=record.snapshot_id,
            checkpoint_id=record.checkpoint_id,
            generation=record.generation,
            owner_run_id=record.owner_run_id,
            lifecycle=record.lifecycle,
            payload=payload,
            parent_checkpoint_id=record.parent_checkpoint_id,
        )


def test_corrupt_snapshot_is_rejected_through_public_store_protocol() -> None:
    store = ThirdPartyCheckpointStore()
    runtime = RuntimeComposition(
        checkpoint_store=store,
        lifecycle_policy=PauseAfterEffect(),
    )
    session = Engine(ConformanceAgent(), runtime=runtime).session("corrupt")
    session.run()
    corrupt = CorruptingViewStore(store)
    child = ConformanceAgent()
    registry = ResolverRegistry()
    registry.register_resource(DEFAULT_CHECKPOINT_REFERENCE, corrupt)
    head = store.get_session_head(session.session_id.value)
    assert head is not None
    snapshot = store.get_session_snapshot(head.snapshot_id)
    assert snapshot is not None
    for raw in snapshot.payload["resolver_references"]:
        namespace = ResolverNamespace(raw["namespace"])
        if namespace is ResolverNamespace.AGENT:
            from qitos.core.session import ResolverReference

            registry.register_resource(
                ResolverReference.from_dict(raw), child
            )
        elif namespace is ResolverNamespace.TOOL_REGISTRY:
            from qitos.core.session import ResolverReference

            registry.register_resource(
                ResolverReference.from_dict(raw), child.tool_registry
            )
    child_runtime = RuntimeComposition(
        checkpoint_store=corrupt,
        resolvers=registry,
        lifecycle_policy=PauseAfterEffect(),
    )
    with pytest.raises(SessionContractError) as rejected:
        Engine.restore(session.session_id, runtime=child_runtime)
    assert rejected.value.error_code in {
        SessionErrorCode.CORRUPT_SNAPSHOT,
        SessionErrorCode.COMPONENT_DIGEST_MISMATCH,
    }


def test_interface_budget_keeps_advanced_types_off_beginner_root() -> None:
    budget = json.loads(
        (FIXTURE_ROOT / "interface-budget.json").read_text(encoding="utf-8")
    )
    signature = inspect.signature(Engine.__init__)
    assert "runtime" in signature.parameters
    assert "session_store" not in signature.parameters
    assert "Session" not in qitos.__all__
    assert "RuntimeComposition" not in qitos.__all__
    assert len(signature.parameters) == budget["engine_constructor"][
        "current_parameter_count"
    ]
    assert len(qitos.__all__) == budget["root_export_count"]["current"]
    assert not any(
        forbidden in name
        for name in (
            *qitos.__all__,
            "Session",
            "RuntimeComposition",
            "SessionSnapshotCommit",
        )
        for forbidden in ("SessionV1", "SessionV2", "LegacySession", "NextSession")
    )


def test_lane_a_fixtures_decode_through_public_protocols() -> None:
    commit_payload = json.loads(
        (FIXTURE_ROOT / "checkpoint-session-commit.json").read_text(
            encoding="utf-8"
        )
    )
    commit = SessionSnapshotCommit(**commit_payload)
    assert commit.target_generation == 5

    config_payload = json.loads(
        (FIXTURE_ROOT / "runtime-composition-config.json").read_text(
            encoding="utf-8"
        )
    )
    config = RuntimeCompositionConfig.from_dict(config_payload)
    assert config.to_dict() == config_payload

    unsupported = json.loads(
        (FIXTURE_ROOT / "unsupported-capability-matrix.json").read_text(
            encoding="utf-8"
        )
    )
    assert unsupported["schema_version"] == 1
    assert {item["error_code"] for item in unsupported["unsupported"]} == {
        "incompatible_checkpoint",
        "invalid_lifecycle_operation",
        "unsupported_capability",
    }

    manifest = json.loads(
        (FIXTURE_ROOT / "fixture-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["producer_commit"] == (
        "bc725e8b77576a7a0b5c165a5066c83c4d9965c8"
    )
    for item in manifest["files"]:
        fixture = (FIXTURE_ROOT / item["path"]).read_bytes()
        assert hashlib.sha256(fixture).hexdigest() == item["sha256"]


def test_composition_binds_context_model_and_existing_tool_policy() -> None:
    class ContextBinding:
        capability_id = "tests.context_model"

        def __init__(self) -> None:
            self.bound_engine = None

        def bind(self, engine) -> None:
            self.bound_engine = engine

    binding = ContextBinding()
    policy = ActionExecutionPolicy(
        mode="parallel",
        max_concurrency=2,
        parallel_tool_names=frozenset({"effect"}),
    )
    runtime = RuntimeComposition(
        context_model_runtime=binding,
        tool_execution_policy=policy,
    )
    engine = Engine(ConformanceAgent(), runtime=runtime)

    assert binding.bound_engine is engine
    assert engine.executor is not None and engine.executor.policy is policy
    config = runtime.export_config().to_dict()
    assert config["context_model_runtime"] == "tests.context_model"
    assert config["tool_execution_policy"]["parallel_tool_names"] == ["effect"]
