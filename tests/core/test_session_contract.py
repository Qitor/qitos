"""Strict tests for lifecycle, resolver, head, receipt, and snapshot contracts."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from qitos.core.session import (
    AgentIdentity,
    CheckpointIdentity,
    ComponentSlot,
    CORE_SNAPSHOT_COMPONENT_CODECS,
    HeadGeneration,
    PauseReceipt,
    PauseSafety,
    PersistenceReceiptStatus,
    ResolvedResource,
    ResolverNamespace,
    ResolverReference,
    ResolverRegistry,
    RunIdentity,
    SafeBoundaryKind,
    SessionContractError,
    SessionErrorCode,
    SessionHead,
    SessionIdentity,
    SessionLifecycle,
    SessionOperation,
    SessionSnapshot,
    SnapshotComponent,
    SnapshotIdentity,
    SnapshotTiming,
    lifecycle_allows,
    lifecycle_can_transition,
)


FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "session"
STAMP = "2026-08-30T00:00:00Z"
SESSION = SessionIdentity("session_20000000000000000000000000000001")
RUN = RunIdentity("run_20000000000000000000000000000002")
SNAPSHOT = SnapshotIdentity("snapshot_20000000000000000000000000000003")
CHECKPOINT = CheckpointIdentity("checkpoint_20000000000000000000000000000004")
AGENT = AgentIdentity("agent_20000000000000000000000000000005")


def _component(
    slot: ComponentSlot,
    payload: dict | None = None,
    *,
    required: bool | None = None,
) -> SnapshotComponent:
    codec = next(item for item in CORE_SNAPSHOT_COMPONENT_CODECS if item.slot == slot.value)
    return SnapshotComponent(
        slot=slot,
        schema_version=codec.schema_version,
        required=codec.required if required is None else required,
        owner=codec.owner,
        payload=payload or {"present": True},
    )


def _components() -> tuple[SnapshotComponent, ...]:
    return (
        _component(
            ComponentSlot.AGENT_STATE,
            {
                "agent_id": AGENT.to_dict(),
                "state_schema": "research_state",
                "state": {"task": "inspect parser", "step": 2},
            },
        ),
        _component(
            ComponentSlot.ENGINE_PROGRESS,
            {"phase": "check_stop", "safe_boundary": True},
        ),
        _component(
            ComponentSlot.BUDGET_CAPABILITY,
            {"steps_remaining": 8, "capability_digest": "0" * 64},
        ),
        _component(
            ComponentSlot.TRACE_LINEAGE,
            {
                "run_id": RUN.to_dict(),
                "trace_complete": True,
                "parent_run_id": None,
            },
        ),
    )


def _references() -> tuple[ResolverReference, ...]:
    return tuple(
        ResolverReference(namespace, f"default:{namespace.value}", capability)
        for namespace, capability in (
            (ResolverNamespace.MODEL, "model.call"),
            (ResolverNamespace.TOOL_REGISTRY, "tools.execute"),
            (ResolverNamespace.ENVIRONMENT, "environment.observe"),
            (ResolverNamespace.ARTIFACT_STORE, "artifacts.read"),
            (ResolverNamespace.SECRET, "secret.read"),
            (ResolverNamespace.CHECKPOINT_STORE, "checkpoint.read_write"),
            (
                ResolverNamespace.PROVIDER_CONTINUATION,
                "provider_continuation.resolve",
            ),
            (ResolverNamespace.AGENT, "agent.module"),
            (ResolverNamespace.RUNTIME_EVENT_SINK, "runtime.events"),
        )
    )


def _snapshot(
    *,
    lifecycle: SessionLifecycle = SessionLifecycle.PAUSED,
    generation: int = 6,
    components: tuple[SnapshotComponent, ...] | None = None,
    session_id: SessionIdentity = SESSION,
    snapshot_id: SnapshotIdentity = SNAPSHOT,
) -> SessionSnapshot:
    return SessionSnapshot.create(
        snapshot_id=snapshot_id,
        session_id=session_id,
        head_generation=HeadGeneration(generation),
        lifecycle=lifecycle,
        created_at=STAMP,
        timing=SnapshotTiming(
            captured_at=STAMP,
            pause_requested_at=STAMP,
            safe_boundary_at=STAMP,
        ),
        components=components or _components(),
        resolver_references=_references(),
    )


def _semantic_fixture() -> dict:
    path = FIXTURE_ROOT / "semantic-fixtures.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_lifecycle_vocabulary_and_terminal_states_are_closed() -> None:
    required = {
        "created",
        "running",
        "pause_requested",
        "pausing",
        "paused",
        "restoring",
        "completed",
        "failed",
        "cancelled",
        "superseded",
    }
    assert required.issubset({state.value for state in SessionLifecycle})
    assert {state.value for state in SessionLifecycle if state.terminal} == {
        "completed",
        "failed",
        "cancelled",
        "superseded",
    }


def test_pause_request_is_not_a_safe_pause() -> None:
    assert lifecycle_can_transition(
        SessionLifecycle.RUNNING, SessionLifecycle.PAUSE_REQUESTED
    )
    assert not lifecycle_can_transition(
        SessionLifecycle.PAUSE_REQUESTED, SessionLifecycle.PAUSED
    )
    assert lifecycle_can_transition(
        SessionLifecycle.PAUSE_REQUESTED, SessionLifecycle.PAUSING
    )
    assert lifecycle_can_transition(SessionLifecycle.PAUSING, SessionLifecycle.PAUSED)


def test_operation_matrix_exposes_run_pause_restore_and_fork_permissions() -> None:
    assert lifecycle_allows(SessionLifecycle.CREATED, SessionOperation.RUN)
    assert lifecycle_allows(SessionLifecycle.RUNNING, SessionOperation.PAUSE)
    assert lifecycle_allows(SessionLifecycle.PAUSED, SessionOperation.RESTORE)
    assert lifecycle_allows(SessionLifecycle.COMPLETED, SessionOperation.FORK)
    assert not lifecycle_allows(SessionLifecycle.RUNNING, SessionOperation.RESTORE)
    assert not lifecycle_allows(SessionLifecycle.CREATED, SessionOperation.FORK)


def test_safe_pause_requires_recorded_slots_quiescence_and_resolved_effects() -> None:
    PauseSafety(SafeBoundaryKind.PARTIAL_PARALLEL_RECORDED).require_migratable()
    with pytest.raises(SessionContractError) as unsafe:
        PauseSafety(
            SafeBoundaryKind.PARTIAL_PARALLEL_RECORDED,
            open_slots_recorded=False,
        ).require_migratable()
    assert unsafe.value.error_code is SessionErrorCode.UNSAFE_PAUSE_BOUNDARY
    with pytest.raises(SessionContractError) as unresolved:
        PauseSafety(
            SafeBoundaryKind.AFTER_TOOL_RESULT,
            unresolved_effect_count=1,
        ).require_migratable()
    assert unresolved.value.error_code is SessionErrorCode.UNRESOLVED_EFFECT


def test_head_compare_and_set_advances_once_and_rejects_stale_generation() -> None:
    head = SessionHead(SESSION, SNAPSHOT, CHECKPOINT, HeadGeneration(4), RUN)
    advanced = head.advance(
        expected_generation=HeadGeneration(4),
        owner_run_id=RUN,
        snapshot_id=SnapshotIdentity(
            "snapshot_20000000000000000000000000000006"
        ),
        checkpoint_id=CheckpointIdentity(
            "checkpoint_20000000000000000000000000000007"
        ),
    )
    assert advanced.generation == HeadGeneration(5)
    assert head.generation == HeadGeneration(4)
    with pytest.raises(SessionContractError) as conflict:
        head.advance(
            expected_generation=HeadGeneration(3),
            owner_run_id=RUN,
            snapshot_id=SNAPSHOT,
            checkpoint_id=CHECKPOINT,
        )
    assert conflict.value.error_code is SessionErrorCode.GENERATION_CONFLICT


def test_head_rejects_superseded_owner() -> None:
    head = SessionHead(SESSION, SNAPSHOT, CHECKPOINT, HeadGeneration(4), RUN)
    stale = RunIdentity("run_20000000000000000000000000000008")
    with pytest.raises(SessionContractError) as exc_info:
        head.advance(
            expected_generation=HeadGeneration(4),
            owner_run_id=stale,
            snapshot_id=SNAPSHOT,
            checkpoint_id=CHECKPOINT,
        )
    assert exc_info.value.error_code is SessionErrorCode.SUPERSEDED_OWNER


def test_resolver_reference_round_trip_covers_every_namespace() -> None:
    for reference in _references():
        assert ResolverReference.from_dict(reference.to_dict()) == reference
    assert {ref.namespace for ref in _references()} == set(ResolverNamespace)


def test_missing_wrong_and_unavailable_resolvers_are_typed_and_safe() -> None:
    model_ref = _references()[0]
    with pytest.raises(SessionContractError) as missing:
        ResolverRegistry().resolve(model_ref)
    assert missing.value.error_code is SessionErrorCode.MISSING_RESOLVER

    wrong_registry = ResolverRegistry(
        {
            ResolverNamespace.MODEL: lambda ref: ResolvedResource(
                ResolverNamespace.ENVIRONMENT,
                frozenset({"environment.observe"}),
                object(),
            )
        }
    )
    with pytest.raises(SessionContractError) as mismatch:
        wrong_registry.resolve(model_ref)
    assert mismatch.value.error_code is SessionErrorCode.RESOLVER_TYPE_MISMATCH

    secret_ref = next(
        ref for ref in _references() if ref.namespace is ResolverNamespace.SECRET
    )
    secret_registry = ResolverRegistry({ResolverNamespace.SECRET: lambda ref: None})
    with pytest.raises(SessionContractError) as unavailable:
        secret_registry.resolve(secret_ref)
    assert unavailable.value.error_code is SessionErrorCode.UNAVAILABLE_SECRET
    assert secret_ref.reference_id not in json.dumps(unavailable.value.to_dict())


def test_resolver_returns_process_local_resource_without_serializing_it() -> None:
    resource = object()
    ref = _references()[0]
    registry = ResolverRegistry(
        {
            ResolverNamespace.MODEL: lambda item: ResolvedResource(
                ResolverNamespace.MODEL, frozenset({"model.call"}), resource
            )
        }
    )
    assert registry.resolve(ref).resource is resource
    assert "resource" not in ref.to_dict()


def test_snapshot_round_trip_is_deterministic_and_integrity_checked() -> None:
    snapshot = _snapshot()
    raw = snapshot.canonical_json()
    restored = SessionSnapshot.from_json(raw)
    assert restored.to_dict() == snapshot.to_dict()
    assert restored.canonical_json() == raw
    assert restored.integrity.digest == snapshot.integrity.digest


@pytest.mark.parametrize("fixture_name", ["restore-candidate.json", "forked-session.json"])
def test_committed_snapshot_fixtures_use_current_strict_reader(fixture_name: str) -> None:
    raw = (FIXTURE_ROOT / fixture_name).read_text(encoding="utf-8")
    snapshot = SessionSnapshot.from_json(raw)
    assert snapshot.schema_version == 2
    assert snapshot.canonical_json() == raw.strip()


def test_snapshot_owns_nested_values_and_serialized_output_is_isolated() -> None:
    source = {"nested": {"items": [1, 2]}}
    components = list(_components())
    components[1] = _component(ComponentSlot.ENGINE_PROGRESS, source)
    snapshot = _snapshot(components=tuple(components))
    source["nested"]["items"].append(3)
    output = snapshot.to_dict()
    output["components"][1]["payload"]["nested"]["items"].append(4)
    assert snapshot.to_dict()["components"][1]["payload"] == {
        "nested": {"items": [1, 2]}
    }


@pytest.mark.parametrize("bad_value", [object(), (1, 2), float("nan"), float("inf")])
def test_snapshot_rejects_non_json_and_non_finite_component_values(bad_value: object) -> None:
    with pytest.raises(SessionContractError) as exc_info:
        _component(ComponentSlot.AGENT_STATE, {"bad": bad_value})
    assert exc_info.value.error_code is SessionErrorCode.CORRUPT_SNAPSHOT


@pytest.mark.parametrize(
    "bad_value",
    [
        "/Users/private/worktree/file.txt",
        "/home/researcher/private.txt",
        "Authorization: Bearer private-value",
        "password=private-value",
    ],
)
def test_snapshot_rejects_host_paths_and_credentials(bad_value: str) -> None:
    with pytest.raises(SessionContractError) as exc_info:
        _component(ComponentSlot.AGENT_STATE, {"bad": bad_value})
    failure = json.dumps(exc_info.value.to_dict())
    assert exc_info.value.error_code is SessionErrorCode.CORRUPT_SNAPSHOT
    assert bad_value not in failure


def test_snapshot_reader_rejects_unknown_field_and_wrong_type() -> None:
    payload = _snapshot().to_dict()
    payload["unknown"] = True
    with pytest.raises(SessionContractError) as unknown:
        SessionSnapshot.from_dict(payload)
    assert unknown.value.error_code is SessionErrorCode.CORRUPT_SNAPSHOT

    payload = _snapshot().to_dict()
    payload["head_generation"] = "6"
    with pytest.raises(SessionContractError) as wrong:
        SessionSnapshot.from_dict(payload)
    assert wrong.value.error_code is SessionErrorCode.CORRUPT_SNAPSHOT


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_snapshot_json_reader_rejects_non_finite_constants(constant: str) -> None:
    raw = _snapshot().canonical_json().replace('"head_generation":6', f'"head_generation":{constant}')
    with pytest.raises(SessionContractError) as exc_info:
        SessionSnapshot.from_json(raw)
    assert exc_info.value.error_code is SessionErrorCode.CORRUPT_SNAPSHOT


def test_snapshot_reader_rejects_corrupt_digest() -> None:
    payload = _snapshot().to_dict()
    payload["components"][0]["payload"]["state"]["step"] = 999
    with pytest.raises(SessionContractError) as exc_info:
        SessionSnapshot.from_dict(payload)
    assert exc_info.value.error_code is SessionErrorCode.COMPONENT_DIGEST_MISMATCH


def test_snapshot_rejects_unsupported_envelope_and_component_schemas() -> None:
    payload = _snapshot().to_dict()
    payload["schema_version"] = 999
    with pytest.raises(SessionContractError) as envelope:
        SessionSnapshot.from_dict(payload)
    assert envelope.value.error_code is SessionErrorCode.UNSUPPORTED_SNAPSHOT_SCHEMA

    payload = _snapshot().to_dict()
    payload["components"][0]["schema_version"] = 999
    with pytest.raises(SessionContractError) as component:
        SessionSnapshot.from_dict(payload)
    assert component.value.error_code is SessionErrorCode.UNSUPPORTED_COMPONENT_SCHEMA


def test_snapshot_rejects_missing_required_component() -> None:
    components = tuple(
        component
        for component in _components()
        if component.slot != ComponentSlot.AGENT_STATE.value
    )
    with pytest.raises(SessionContractError) as exc_info:
        _snapshot(components=components)
    assert exc_info.value.error_code is SessionErrorCode.MISSING_REQUIRED_COMPONENT


def test_pause_receipts_do_not_confuse_accepted_failed_or_conflict_with_paused() -> None:
    persisted = PauseReceipt(
        session_id=SESSION,
        run_id=RUN,
        status=PersistenceReceiptStatus.PERSISTED,
        lifecycle=SessionLifecycle.PAUSED,
        expected_generation=HeadGeneration(4),
        actual_generation=HeadGeneration(5),
        snapshot_id=SNAPSHOT,
        checkpoint_id=CHECKPOINT,
    )
    persisted.require_persisted()

    for status, code in (
        (PersistenceReceiptStatus.ACCEPTED, SessionErrorCode.PERSISTENCE_REJECTED),
        (PersistenceReceiptStatus.REJECTED, SessionErrorCode.PERSISTENCE_REJECTED),
        (PersistenceReceiptStatus.FAILED, SessionErrorCode.PERSISTENCE_FAILED),
        (PersistenceReceiptStatus.CONFLICT, SessionErrorCode.GENERATION_CONFLICT),
    ):
        receipt = PauseReceipt(
            session_id=SESSION,
            run_id=RUN,
            status=status,
            lifecycle=SessionLifecycle.PAUSING,
            expected_generation=HeadGeneration(4),
            actual_generation=HeadGeneration(4),
            error_code=code,
        )
        with pytest.raises(SessionContractError) as exc_info:
            receipt.require_persisted()
        assert exc_info.value.error_code is code


def test_semantic_fixture_covers_every_required_scenario() -> None:
    fixture = _semantic_fixture()
    assert fixture["schema_version"] == 1
    cases = {item["case_id"] for item in fixture["cases"]}
    assert cases == {
        "created_session",
        "running_session",
        "pause_requested",
        "safely_paused",
        "partial_parallel_batch",
        "pending_steering",
        "persistence_failure",
        "generation_conflict",
        "superseded_owner",
        "missing_resolver",
        "unavailable_secret",
        "corrupt_snapshot",
        "unsupported_component",
        "restore_candidate",
        "forked_session",
    }
    for item in fixture["cases"]:
        SessionLifecycle(item["lifecycle"])
        HeadGeneration(item["generation"])
        if item["component_slot"] is not None:
            ComponentSlot(item["component_slot"])
        if item["error_code"] is not None:
            SessionErrorCode(item["error_code"])


def test_fixture_manifest_binds_exact_producer_bytes() -> None:
    manifest = json.loads(
        (FIXTURE_ROOT / "fixture-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == 1
    assert manifest["producers"] == {
        "identity": "g2-contract-convergence",
        "snapshot": "g2-contract-convergence",
    }
    for item in manifest["files"]:
        fixture_bytes = (FIXTURE_ROOT / item["path"]).read_bytes()
        assert hashlib.sha256(fixture_bytes).hexdigest() == item["sha256"]


def test_qualification_evidence_binds_manifest_and_unsupported_claims() -> None:
    evidence = json.loads(
        (FIXTURE_ROOT / "qualification-evidence.json").read_text(encoding="utf-8")
    )
    manifest_bytes = (FIXTURE_ROOT / "fixture-manifest.json").read_bytes()
    assert evidence["contract_id"] == "qitos.session_contract_bundle"
    assert evidence["contract_version"] == "qitos.session_contract_bundle/v2"
    assert evidence["fixture_path"] == "tests/fixtures/session/fixture-manifest.json"
    assert evidence["qualification_authority"] == "qitos.s1.integration_owner/v1"
    assert evidence["qualified"] is True
    assert evidence["lineage_evidence"] == {
        "status": "explicit",
        "edge_source": "producer_fact",
        "inferred": False,
    }
    assert len(set(evidence["identity_bindings"].values())) == len(
        evidence["identity_bindings"]
    )
    assert hashlib.sha256(manifest_bytes).hexdigest() == (
        "952dc20f3c412830ef1f18fe73805cc6d8e04ecc28d89e4991883c983a983466"
    )
    assert "engine_pause_runtime" in evidence["unsupported_claims"]
    assert "fresh_process_restore_runtime" in evidence["unsupported_claims"]
    assert "trajectory_schema_freeze" in evidence["unsupported_claims"]


def test_fork_fixture_has_new_session_and_snapshot_identities() -> None:
    lineage = _semantic_fixture()["fork_lineage"]
    source_session = SessionIdentity.from_dict(lineage["source_session_id"])
    source_snapshot = SnapshotIdentity.from_dict(lineage["source_snapshot_id"])
    fork_session = SessionIdentity.from_dict(lineage["fork_session_id"])
    fork_snapshot = SnapshotIdentity.from_dict(lineage["fork_snapshot_id"])
    assert fork_session != source_session
    assert fork_snapshot != source_snapshot


def test_every_stable_failure_has_safe_machine_readable_shape() -> None:
    for error_code in SessionErrorCode:
        error = SessionContractError(
            error_code,
            "Safe diagnostic.",
            recoverable=True,
            remediation="Use a safe remediation.",
            metadata={
                "field": "session_id",
                "secret_token": "do-not-persist",
                "source": "/Users/private/worktree",
            },
        )
        payload = error.to_dict()
        serialized = json.dumps(payload)
        assert payload["error_code"] == error_code.value
        assert payload["message"] == "Safe diagnostic."
        assert payload["recoverable"] is True
        assert payload["remediation"]
        assert "do-not-persist" not in serialized
        assert "/Users/private/worktree" not in serialized


def test_snapshot_output_mutation_does_not_change_digest() -> None:
    snapshot = _snapshot()
    before = snapshot.integrity.digest
    output = copy.deepcopy(snapshot.to_dict())
    output["components"].clear()
    assert snapshot.integrity.digest == before
    assert len(snapshot.components) == len(CORE_SNAPSHOT_COMPONENT_CODECS)
    CORE_SNAPSHOT_COMPONENT_CODECS,
