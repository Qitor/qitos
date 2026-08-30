from __future__ import annotations

import json
from pathlib import Path

import pytest

from qitos.core.tool_result import ToolResult
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
        work_item_id=identity,
        session_ref=f"session:{identity}",
        task_ref=f"task:{identity}",
        lifecycle=lifecycle,
        owner=WorkOwner(agent, generation),
        parent_work_item_id=parent,
        detached=detached,
    )


def test_owner_transfer_is_compare_and_set_and_restore_advances_generation() -> None:
    graph = WorkGraph("graph:owner")
    graph.add_work_item(_item("work:root", "agent:a"))

    first = graph.transfer_owner(
        "work:root",
        expected_generation=0,
        to_agent_id="agent:b",
        transfer_id="transfer:1",
        context_transfer_ref="context:opaque:1",
    )
    restored = graph.restore_owner(
        "work:root",
        expected_generation=1,
        agent_id="agent:b",
        transfer_id="restore:1",
    )

    assert first.committed_generation == 1
    assert restored.committed_generation == 2
    assert graph.work_items["work:root"].owner == WorkOwner("agent:b", 2)
    with pytest.raises(WorkGraphContractError) as caught:
        graph.transfer_owner(
            "work:root",
            expected_generation=1,
            to_agent_id="agent:c",
            transfer_id="transfer:stale",
        )
    assert caught.value.code == "owner_generation_conflict"


def test_stale_late_and_duplicate_completion_never_replace_authoritative_result() -> None:
    graph = WorkGraph("graph:completion")
    graph.add_work_item(_item("work:root", "agent:a", generation=2))

    stale = graph.record_completion(
        completion_id="completion:stale",
        work_item_id="work:root",
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
        work_item_id="work:root",
        owner_generation=2,
        outcome=accepted_result,
    )
    duplicate = graph.record_completion(
        completion_id="completion:duplicate",
        work_item_id="work:root",
        owner_generation=2,
        outcome=accepted_result,
    )
    late = graph.record_completion(
        completion_id="completion:late",
        work_item_id="work:root",
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
        parent_work_item_id="work:root",
        child=_item("work:delegated", "agent:reviewer", parent="work:root"),
    )
    graph.add_spawn(
        spawn_id="spawn:1",
        edge_id="edge:spawn",
        parent_work_item_id="work:root",
        child=_item("work:spawned", "agent:watcher", parent="work:root"),
        supervision_policy="parent_until_detached",
    )
    graph.add_fan_out(
        group_id="fanout:1",
        parent_work_item_id="work:root",
        children=[
            _item("work:fan:1", "agent:worker", parent="work:root"),
            _item("work:fan:2", "agent:worker", parent="work:root"),
        ],
    )
    graph.declare_join(
        join_id="join:partial",
        parent_work_item_id="work:root",
        child_work_item_ids=["work:fan:1", "work:fan:2"],
        policy="all",
    )
    graph.record_completion(
        completion_id="completion:fan:1",
        work_item_id="work:fan:1",
        owner_generation=0,
        outcome=ToolResult(output="one"),
    )
    graph.accept_join_result("join:partial", "work:fan:1")

    assert [edge.operation for edge in graph.edges] == [
        "delegate", "spawn", "fan_out", "fan_out"
    ]
    assert graph.joins[0].accepted_child_ids == ["work:fan:1"]
    with pytest.raises(WorkGraphContractError) as caught:
        graph.accept_join_result("join:partial", "work:delegated")
    assert caught.value.code == "undeclared_join_child"


def test_cancellation_detachment_budget_and_capability_are_explicit() -> None:
    graph = WorkGraph("graph:authority")
    graph.add_work_item(_item("work:root", "agent:parent"))
    graph.add_spawn(
        spawn_id="spawn:1",
        edge_id="edge:spawn",
        parent_work_item_id="work:root",
        child=_item("work:child", "agent:worker", parent="work:root"),
        supervision_policy="parent_until_detached",
    )
    graph.request_cancel(
        cancellation_id="cancel:1",
        work_item_id="work:child",
        expected_generation=0,
        propagation="request_and_wait",
    )
    graph.add_budget_allocation(
        BudgetAllocation(
            "budget:1", "work:root", "work:child", {"model_tokens": 1000}
        )
    )
    graph.add_capability_allocation(
        CapabilityAllocation(
            "capability:1", "work:root", "work:child", ["repo.read"]
        )
    )
    graph.detach_child(
        detachment_id="detach:1",
        parent_work_item_id="work:root",
        child_work_item_id="work:child",
        supervisor_ref="supervisor:caller",
    )

    assert graph.work_items["work:child"].detached is True
    assert graph.cancellations[0].propagation == "request_and_wait"
    assert graph.budget_allocations[0].limits == {"model_tokens": 1000}
    assert graph.capability_allocations[0].capabilities == ["repo.read"]


def test_snapshot_component_lists_only_unresolved_work() -> None:
    graph = WorkGraph("graph:snapshot")
    graph.add_work_item(_item("work:open", "agent:a", lifecycle="running"))
    graph.add_work_item(_item("work:done", "agent:b", lifecycle="completed"))

    payload = graph.snapshot_component().to_dict()
    restored = WorkGraphSnapshotComponent.from_dict(payload)

    assert restored.unresolved_work_item_ids == ["work:open"]


def test_cancelled_child_late_result_is_recorded_without_reopening() -> None:
    graph = WorkGraph("graph:cancelled")
    graph.add_work_item(
        _item("work:cancelled", "agent:child", lifecycle="cancelled", generation=3)
    )

    disposition = graph.record_completion(
        completion_id="completion:after-cancel",
        work_item_id="work:cancelled",
        owner_generation=3,
        outcome=ToolResult(
            output="finished after cancellation",
            late_result=True,
            owner_generation=3,
        ),
    )

    assert disposition == "late_terminal_rejected"
    assert graph.work_items["work:cancelled"].lifecycle == "cancelled"
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
            BudgetAllocation("budget:bad", "work:root", "work:child", {"future": object()})
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

    assert set(fixture["scenario_manifest"]) == expected
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
        graph.add_work_item(
            _item(
                raw["work_item_id"],
                raw["agent_id"],
                parent=raw.get("parent_work_item_id"),
                lifecycle=raw["lifecycle"],
                generation=raw["generation"],
            )
        )
    graph.record_attempt(
        WorkAttempt("attempt:root:1", "work:root", 0, "running", "worker:local")
    )
    graph.add_spawn(
        spawn_id="spawn:fixture",
        edge_id="edge:fixture",
        parent_work_item_id="work:root",
        child=_item("work:child", "agent:child", parent="work:root"),
        supervision_policy="parent_until_detached",
    )
    return graph
