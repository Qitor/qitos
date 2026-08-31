from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from qitos.core.tool_result import ToolResult
from qitos.core.session import (
    AgentIdentity,
    AttemptIdentity,
    SessionIdentity,
    WorkItemIdentity,
)
from qitos.core.work_graph import (
    WORK_GRAPH_SCHEMA_VERSION,
    BudgetAllocation,
    CapabilityAllocation,
    WorkAttempt,
    WorkGraph,
    WorkGraphContractError,
    WorkGraphSnapshotComponent,
    WorkItem,
    WorkOwner,
)


FIXTURE = Path(__file__).parents[1] / "fixtures" / "work_graph" / "contracts.json"


def _typed(identity_type, label: str):
    return identity_type(f"{identity_type.PREFIX}_{hashlib.sha256(label.encode()).hexdigest()[:32]}")


def _work(label: str) -> WorkItemIdentity:
    return _typed(WorkItemIdentity, label)


def _agent(label: str) -> AgentIdentity:
    return _typed(AgentIdentity, label)


def _session(label: str) -> SessionIdentity:
    return _typed(SessionIdentity, label)


def _attempt(label: str) -> AttemptIdentity:
    return _typed(AttemptIdentity, label)


def _item(
    identity: str,
    agent: str,
    *,
    parent: str | None = None,
    lifecycle: str = "created",
    generation: int = 0,
    detached: bool = False,
) -> WorkItem:
    return WorkItem(
        work_item_id=_work(identity),
        session_ref=_session(identity),
        task_ref=f"task:{identity}",
        lifecycle=lifecycle,
        owner=WorkOwner(_agent(agent), generation),
        parent_work_item_id=_work(parent) if parent is not None else None,
        detached=detached,
    )


def test_owner_transfer_is_compare_and_set_and_restore_advances_generation() -> None:
    graph = WorkGraph("graph:owner")
    graph.add_work_item(_item("work:root", "agent:a"))

    first = graph.transfer_owner(
        _work("work:root"),
        expected_generation=0,
        to_agent_id=_agent("agent:b"),
        transfer_id="transfer:1",
        context_transfer_ref="context:opaque:1",
    )
    restored = graph.restore_owner(
        _work("work:root"),
        expected_generation=1,
        agent_id=_agent("agent:b"),
        transfer_id="restore:1",
    )

    assert first.committed_generation == 1
    assert restored.committed_generation == 2
    assert graph.work_items[_work("work:root")].owner == WorkOwner(_agent("agent:b"), 2)
    with pytest.raises(WorkGraphContractError) as caught:
        graph.transfer_owner(
            _work("work:root"),
            expected_generation=1,
            to_agent_id=_agent("agent:c"),
            transfer_id="transfer:stale",
        )
    assert caught.value.code == "owner_generation_conflict"


def test_stale_late_and_duplicate_completion_never_replace_authoritative_result() -> None:
    graph = WorkGraph("graph:completion")
    graph.add_work_item(_item("work:root", "agent:a", generation=2))

    stale = graph.record_completion(
        completion_id="completion:stale",
        work_item_id=_work("work:root"),
        owner_generation=1,
        outcome=ToolResult(output="stale", stale_owner=True, owner_generation=1),
    )
    accepted_result = ToolResult(
        output="accepted",
        effect_ref="effect:1",
        effect_state="committed",
        owner_generation=2,
    )
    accepted = graph.record_completion(
        completion_id="completion:accepted",
        work_item_id=_work("work:root"),
        owner_generation=2,
        outcome=accepted_result,
    )
    duplicate = graph.record_completion(
        completion_id="completion:duplicate",
        work_item_id=_work("work:root"),
        owner_generation=2,
        outcome=accepted_result,
    )
    late = graph.record_completion(
        completion_id="completion:late",
        work_item_id=_work("work:root"),
        owner_generation=2,
        outcome=ToolResult(output="different", late_result=True, owner_generation=2),
    )

    assert stale == "stale_owner_rejected"
    assert accepted == "committed"
    assert duplicate == "duplicate_ignored"
    assert late == "late_terminal_rejected"
    assert len(graph.completions) == 1
    assert len(graph.late_results) == 2
    assert graph.completions[0].outcome["output"] == "accepted"


def test_delegate_spawn_fan_out_and_join_remain_distinct() -> None:
    graph = WorkGraph("graph:operations")
    graph.add_work_item(_item("work:root", "agent:parent"))
    graph.add_delegation(
        delegation_id="delegate:1",
        edge_id="edge:delegate",
        parent_work_item_id=_work("work:root"),
        child=_item("work:delegated", "agent:reviewer", parent="work:root"),
    )
    graph.add_spawn(
        spawn_id="spawn:1",
        edge_id="edge:spawn",
        parent_work_item_id=_work("work:root"),
        child=_item("work:spawned", "agent:watcher", parent="work:root"),
        supervision_policy="parent_until_detached",
    )
    graph.add_fan_out(
        group_id="fanout:1",
        parent_work_item_id=_work("work:root"),
        children=[
            _item("work:fan:1", "agent:worker", parent="work:root"),
            _item("work:fan:2", "agent:worker", parent="work:root"),
        ],
    )
    graph.declare_join(
        join_id="join:partial",
        parent_work_item_id=_work("work:root"),
        child_work_item_ids=[_work("work:fan:1"), _work("work:fan:2")],
        policy="all",
    )
    graph.record_completion(
        completion_id="completion:fan:1",
        work_item_id=_work("work:fan:1"),
        owner_generation=0,
        outcome=ToolResult(output="one"),
    )
    graph.accept_join_result("join:partial", _work("work:fan:1"))

    assert [edge.operation for edge in graph.edges] == [
        "delegate", "spawn", "fan_out", "fan_out"
    ]
    assert graph.joins[0].accepted_child_ids == [_work("work:fan:1")]
    with pytest.raises(WorkGraphContractError) as caught:
        graph.accept_join_result("join:partial", _work("work:delegated"))
    assert caught.value.code == "undeclared_join_child"


def test_cancellation_detachment_budget_and_capability_are_explicit() -> None:
    graph = WorkGraph("graph:authority")
    graph.add_work_item(_item("work:root", "agent:parent"))
    graph.add_spawn(
        spawn_id="spawn:1",
        edge_id="edge:spawn",
        parent_work_item_id=_work("work:root"),
        child=_item("work:child", "agent:worker", parent="work:root"),
        supervision_policy="parent_until_detached",
    )
    graph.request_cancel(
        cancellation_id="cancel:1",
        work_item_id=_work("work:child"),
        expected_generation=0,
        propagation="request_and_wait",
    )
    graph.add_budget_allocation(
        BudgetAllocation(
            "budget:1", _work("work:root"), _work("work:child"), {"model_tokens": 1000}
        )
    )
    graph.add_capability_allocation(
        CapabilityAllocation(
            "capability:1", _work("work:root"), _work("work:child"), ["repo.read"]
        )
    )
    graph.detach_child(
        detachment_id="detach:1",
        parent_work_item_id=_work("work:root"),
        child_work_item_id=_work("work:child"),
        supervisor_ref="supervisor:caller",
    )

    assert graph.work_items[_work("work:child")].detached is True
    assert graph.cancellations[0].propagation == "request_and_wait"
    assert graph.budget_allocations[0].limits == {"model_tokens": 1000}
    assert graph.capability_allocations[0].capabilities == ["repo.read"]


def test_snapshot_component_lists_only_unresolved_work() -> None:
    graph = WorkGraph("graph:snapshot")
    graph.add_work_item(_item("work:open", "agent:a", lifecycle="running"))
    graph.add_work_item(_item("work:done", "agent:b", lifecycle="completed"))

    payload = graph.snapshot_component().to_dict()
    restored = WorkGraphSnapshotComponent.from_dict(payload)

    assert restored.unresolved_work_item_ids == [_work("work:open")]


def test_cancelled_child_late_result_is_recorded_without_reopening() -> None:
    graph = WorkGraph("graph:cancelled")
    graph.add_work_item(
        _item("work:cancelled", "agent:child", lifecycle="cancelled", generation=3)
    )

    disposition = graph.record_completion(
        completion_id="completion:after-cancel",
        work_item_id=_work("work:cancelled"),
        owner_generation=3,
        outcome=ToolResult(
            output="finished after cancellation",
            late_result=True,
            owner_generation=3,
        ),
    )

    assert disposition == "late_terminal_rejected"
    assert graph.work_items[_work("work:cancelled")].lifecycle == "cancelled"
    assert graph.completions == []
    assert graph.late_results[0].reason == "cancelled"


def test_strict_round_trip_owns_input_and_rejects_unknown_schema_or_non_json() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    graph = _graph_from_fixture(fixture)
    payload = graph.to_persistence_dict()
    restored = WorkGraph.from_canonical_dict(payload)
    payload["work_items"][0]["task_ref"] = "mutated"

    assert restored.to_persistence_dict() == graph.to_persistence_dict()
    assert restored.schema_version == WORK_GRAPH_SCHEMA_VERSION

    unknown = graph.to_persistence_dict()
    unknown["schema_version"] = "qitos.work_graph/v999"
    with pytest.raises(WorkGraphContractError) as caught:
        WorkGraph.from_canonical_dict(unknown)
    assert caught.value.code == "unknown_schema_version"

    extra = graph.to_persistence_dict()
    extra["scheduler"] = {"live": True}
    with pytest.raises(WorkGraphContractError) as caught:
        WorkGraph.from_canonical_dict(extra)
    assert caught.value.code == "unknown_field"

    with pytest.raises(WorkGraphContractError) as caught:
        graph.add_budget_allocation(
            BudgetAllocation("budget:bad", _work("work:root"), _work("work:child"), {"future": object()})
        )
    assert caught.value.code == "non_json_value"


def test_fixture_manifest_has_executable_budget_capability_and_restore_outcomes() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    expected = {
        "handoff", "delegate", "spawn", "fan_out", "partial_join",
        "cancel_requested", "cancelled_but_worker_unknown", "detached_child",
        "ownership_transfer", "stale_owner_result", "late_result",
        "budget_exhaustion", "missing_capability", "restore_with_unresolved_child",
    }

    assert fixture["schema_version"] == "qitos.work_graph.fixture_manifest/v2"
    assert set(fixture["scenario_manifest"]) == expected
    WorkItemIdentity.from_dict(fixture["work_items"][0]["work_item_id"])
    AgentIdentity.from_dict(fixture["work_items"][0]["owner"]["agent_id"])
    assert fixture["safe_boundary_matrix"]["all_workers_quiescent"] == "safe"
    assert all(
        state == "unsafe"
        for boundary, state in fixture["safe_boundary_matrix"].items()
        if boundary != "all_workers_quiescent"
    )
    outcomes = {
        name: ToolResult(**payload)
        for name, payload in fixture["terminal_outcomes"].items()
    }
    assert outcomes["budget_exhaustion"].error_code == "budget_exhausted"
    assert outcomes["missing_capability"].error_kind == "policy"
    assert outcomes["unresolved_child"].worker_still_running is True
    assert outcomes["unresolved_child"].outcome_unknown is True


def _graph_from_fixture(fixture: dict) -> WorkGraph:
    graph = WorkGraph(fixture["graph_id"])
    for raw in fixture["work_items"]:
        parent = raw.get("parent_work_item_id")
        graph.add_work_item(
            WorkItem(
                work_item_id=WorkItemIdentity.from_dict(raw["work_item_id"]),
                session_ref=SessionIdentity.from_dict(raw["session_ref"]),
                task_ref=raw["task_ref"],
                lifecycle=raw["lifecycle"],
                owner=WorkOwner(
                    AgentIdentity.from_dict(raw["owner"]["agent_id"]),
                    raw["owner"]["generation"],
                ),
                parent_work_item_id=(
                    WorkItemIdentity.from_dict(parent) if parent is not None else None
                ),
                detached=raw["detached"],
            )
        )
    root_id = next(iter(graph.work_items))
    graph.record_attempt(
        WorkAttempt(_attempt("attempt:root:1"), root_id, 0, "running", "worker:local")
    )
    child = WorkItem(
        work_item_id=_work("work:child"),
        session_ref=_session("work:child"),
        task_ref="task:work:child",
        lifecycle="created",
        owner=WorkOwner(_agent("agent:child"), 0),
        parent_work_item_id=root_id,
    )
    graph.add_spawn(
        spawn_id="spawn:fixture",
        edge_id="edge:fixture",
        parent_work_item_id=root_id,
        child=child,
        supervision_policy="parent_until_detached",
    )
    return graph


def test_g2_contract_manifest_binds_executable_c_lane_fixtures() -> None:
    manifest_path = FIXTURE.with_name("g2-contract-manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["contract_id"] == "qitos.work_effect_contract_bundle"
    for item in manifest["files"]:
        payload = Path(__file__).parents[2] / item["path"]
        assert hashlib.sha256(payload.read_bytes()).hexdigest() == item["sha256"]

    evidence = json.loads(
        FIXTURE.with_name("qualification-evidence.json").read_text(encoding="utf-8")
    )
    assert evidence["qualified"] is True
    assert evidence["lineage_evidence"]["edge_source"] == "producer_fact"
    assert len(set(evidence["identity_bindings"].values())) == len(
        evidence["identity_bindings"]
    )


def test_multi_record_mutations_are_all_or_nothing() -> None:
    graph = WorkGraph("graph:atomic")
    graph.add_work_item(_item("root", "parent"))
    graph.add_work_item(_item("existing", "worker", parent="root"))
    before = graph.to_persistence_dict()

    with pytest.raises(WorkGraphContractError) as caught:
        graph.add_fan_out(
            group_id="fan:atomic",
            parent_work_item_id=_work("root"),
            children=[
                _item("new", "worker", parent="root"),
                _item("existing", "worker", parent="root"),
            ],
        )

    assert caught.value.code == "duplicate_identity"
    assert graph.to_persistence_dict() == before


def test_strict_reader_rejects_dangling_parent_and_parent_edge_mismatch() -> None:
    graph = WorkGraph("graph:strict-refs")
    graph.add_work_item(_item("root", "parent"))
    graph.add_delegation(
        delegation_id="delegate:strict",
        edge_id="edge:strict",
        parent_work_item_id=_work("root"),
        child=_item("child", "worker", parent="root"),
    )

    dangling = graph.to_persistence_dict()
    dangling["work_items"][1]["parent_work_item_id"] = _work("missing").to_dict()
    with pytest.raises(WorkGraphContractError) as caught:
        WorkGraph.from_canonical_dict(dangling)
    assert caught.value.code == "missing_work_item"

    mismatch = graph.to_persistence_dict()
    mismatch["edges"][0]["source_work_item_id"] = _work("child").to_dict()
    with pytest.raises(WorkGraphContractError) as caught:
        WorkGraph.from_canonical_dict(mismatch)
    assert caught.value.code in {"self_edge", "parent_edge_mismatch"}


@pytest.mark.parametrize(
    ("policy", "quorum", "close_after"),
    [("all", None, 2), ("all_successful", None, 2), ("first_success", None, 1), ("quorum", 1, 1)],
)
def test_join_policies_close_deterministically(policy, quorum, close_after) -> None:
    graph = WorkGraph(f"graph:join:{policy}")
    graph.add_work_item(_item("root", "parent"))
    graph.add_fan_out(
        group_id=f"fan:{policy}",
        parent_work_item_id=_work("root"),
        children=[
            _item("child:0", "worker", parent="root"),
            _item("child:1", "worker", parent="root"),
        ],
    )
    graph.declare_join(
        join_id=f"join:{policy}",
        parent_work_item_id=_work("root"),
        child_work_item_ids=[_work("child:0"), _work("child:1")],
        policy=policy,
        quorum=quorum,
        reducer_ref="reducers:ordered",
        reducer_digest="sha256:ordered",
    )
    for index in range(close_after):
        graph.record_completion(
            completion_id=f"completion:{policy}:{index}",
            work_item_id=_work(f"child:{index}"),
            owner_generation=0,
            outcome=ToolResult(output=f"result:{index}"),
        )
        graph.accept_join_result(f"join:{policy}", _work(f"child:{index}"))

    join = graph.joins[0]
    assert join.state == "closed"
    assert join.terminal_receipt_ref == f"join_terminal:join:{policy}:{close_after}"
    assert join.completion_order == [_work(f"child:{index}") for index in range(close_after)]
    restored = WorkGraph.from_canonical_dict(graph.to_persistence_dict())
    assert restored.joins[0] == join


def test_closed_join_records_late_child_without_reducing_twice() -> None:
    graph = WorkGraph("graph:join:late")
    graph.add_work_item(_item("root", "parent"))
    graph.add_fan_out(
        group_id="fan:late",
        parent_work_item_id=_work("root"),
        children=[
            _item("child:fast", "worker", parent="root"),
            _item("child:late", "worker", parent="root"),
        ],
    )
    graph.declare_join(
        join_id="join:first",
        parent_work_item_id=_work("root"),
        child_work_item_ids=[_work("child:fast"), _work("child:late")],
        policy="first_success",
    )
    for child in ("child:fast", "child:late"):
        graph.record_completion(
            completion_id=f"completion:{child}",
            work_item_id=_work(child),
            owner_generation=0,
            outcome=ToolResult(output=child),
        )
        graph.accept_join_result("join:first", _work(child))

    join = graph.joins[0]
    assert join.accepted_child_ids == [_work("child:fast")]
    assert join.discarded_child_ids == [_work("child:late")]
    assert join.generation == 1


def test_all_successful_join_closes_with_typed_failure_receipt() -> None:
    graph = WorkGraph("graph:join:all-successful-failure")
    graph.add_work_item(_item("root", "parent"))
    graph.add_fan_out(
        group_id="fan:all-successful-failure",
        parent_work_item_id=_work("root"),
        children=[
            _item("child:ok", "worker", parent="root"),
            _item("child:failed", "worker", parent="root"),
        ],
    )
    graph.declare_join(
        join_id="join:all-successful-failure",
        parent_work_item_id=_work("root"),
        child_work_item_ids=[_work("child:ok"), _work("child:failed")],
        policy="all_successful",
    )
    outcomes = [
        ToolResult(output="ok"),
        ToolResult(
            status="error",
            error="failed",
            error_kind="execution",
            error_code="child_failed",
        ),
    ]
    for child, outcome in zip(("child:ok", "child:failed"), outcomes):
        graph.record_completion(
            completion_id=f"completion:{child}",
            work_item_id=_work(child),
            owner_generation=0,
            outcome=outcome,
        )
        graph.accept_join_result(
            "join:all-successful-failure", _work(child)
        )

    join = graph.joins[0]
    assert join.state == "closed"
    assert join.terminal_receipt_ref == (
        "join_failed:join:all-successful-failure:2"
    )
