"""Two unrelated, deterministic consumers of the same WorkGraph contracts.

These are contract/read-model examples, not a scheduler or runtime receipt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qitos.core.session import AgentIdentity, AttemptIdentity, SessionIdentity, WorkItemIdentity
from qitos.core.tool_result import ToolResult
from qitos.core.work_graph import WorkAttempt, WorkGraph, WorkItem, WorkOwner
from qitos.tracing.readers import StoreTrajectoryReader
from qitos.tracing.store import MemoryTrajectoryStore
from qitos.tracing.work_graph_reader import GraphSelector, WorkGraphReader, work_graph_event_record


@dataclass(frozen=True)
class ConsumerResult:
    graph: WorkGraph
    inspection: dict


def _inspect(records: list) -> dict:
    store = MemoryTrajectoryStore()
    store.append_batch(records)
    session_id = records[0].session_id
    return WorkGraphReader(StoreTrajectoryReader(store)).read(
        GraphSelector("session", session_id)
    ).to_dict()


def bounded_research_fan_out() -> ConsumerResult:
    """User-owned research tasks with an all-successful deterministic join."""
    session_id, parent_id = SessionIdentity.generate(), WorkItemIdentity.generate()
    owner = AgentIdentity.generate()
    graph = WorkGraph("research-graph")
    parent = WorkItem(parent_id, session_id, "synthesize", "running", WorkOwner(owner, 0))
    graph.add_work_item(parent)
    records = [work_graph_event_record(
        "work_declared", session_id=session_id.value, run_id="run_research00000001",
        work_item_id=parent_id.value, operation_id="declare-parent",
        producer_authority="example.user_code", record_provenance={"offline": True},
        payload={"lifecycle": "running", "owner_id": owner.value},
    )]
    children = []
    for index, topic in enumerate(("source-a", "source-b")):
        child_id, attempt_id = WorkItemIdentity.generate(), AttemptIdentity.generate()
        child_owner = AgentIdentity.generate()
        child = WorkItem(
            child_id, session_id, topic, "running", WorkOwner(child_owner, 0),
            parent_work_item_id=parent_id,
        )
        children.append(child)
        graph.add_fan_out(
            group_id=f"fan-out-{index}", parent_work_item_id=parent_id, children=[child]
        )
        graph.record_attempt(WorkAttempt(attempt_id, child_id, 0, "running"))
        graph.record_completion(
            completion_id=f"complete-{index}", work_item_id=child_id,
            owner_generation=0, outcome=ToolResult(output={"topic": topic}),
        )
        records.extend([
            work_graph_event_record(
                "work_declared", session_id=session_id.value, run_id="run_research00000001",
                work_item_id=child_id.value, parent_work_item_id=parent_id.value,
                source_work_item_id=parent_id.value, operation_id=f"fan-out-{index}",
                producer_authority="example.user_code", record_provenance={"offline": True},
                payload={"operation": "fan_out", "lifecycle": "running", "owner_id": child_owner.value},
            ),
            work_graph_event_record(
                "child_terminal", session_id=session_id.value, run_id="run_research00000001",
                work_item_id=child_id.value, attempt_id=attempt_id.value,
                parent_work_item_id=parent_id.value, owner_generation=0,
                operation_id=f"complete-{index}", producer_authority="example.user_code",
                record_provenance={"offline": True}, payload={"lifecycle": "completed"},
            ),
        ])
    join = graph.declare_join(
        join_id="research-join", parent_work_item_id=parent_id,
        child_work_item_ids=[item.work_item_id for item in children], policy="all_successful",
    )
    for child in children:
        graph.accept_join_result(join.join_id, child.work_item_id)
    records.append(work_graph_event_record(
        "join_closed", session_id=session_id.value, run_id="run_research00000001",
        work_item_id=parent_id.value, operation_id=join.join_id,
        producer_authority="example.user_code", record_provenance={"offline": True},
        payload={"policy": join.policy, "accepted_child_ids": [item.value for item in join.accepted_child_ids]},
    ))
    return ConsumerResult(graph, _inspect(records))


def proposal_critique_transfer() -> ConsumerResult:
    """User-owned proposal/reviewer roles with generation-checked handoff."""
    session_id, work_id = SessionIdentity.generate(), WorkItemIdentity.generate()
    proposer, reviewer = AgentIdentity.generate(), AgentIdentity.generate()
    graph = WorkGraph("review-graph")
    graph.add_work_item(
        WorkItem(work_id, session_id, "review proposal", "running", WorkOwner(proposer, 0))
    )
    transfer = graph.transfer_owner(
        work_id, expected_generation=0, to_agent_id=reviewer,
        transfer_id="proposal-to-reviewer", reason="user_defined_review",
    )
    attempt_id = AttemptIdentity.generate()
    graph.record_attempt(WorkAttempt(attempt_id, work_id, 1, "completed"))
    graph.record_completion(
        completion_id="review-complete", work_item_id=work_id, owner_generation=1,
        outcome=ToolResult(output={"decision": "accepted"}),
    )
    common: dict[str, Any] = {
        "session_id": session_id.value, "run_id": "run_review0000000001",
        "work_item_id": work_id.value, "producer_authority": "example.user_code",
        "record_provenance": {"offline": True},
    }
    records = [
        work_graph_event_record(
            "work_declared", operation_id="declare-proposal",
            payload={"lifecycle": "running", "owner_id": proposer.value}, **common,
        ),
        work_graph_event_record(
            "ownership_transfer_committed", operation_id=transfer.transfer_id,
            attempt_id=attempt_id.value, owner_generation=1,
            payload={"from_owner_id": proposer.value, "to_owner_id": reviewer.value}, **common,
        ),
        work_graph_event_record(
            "outcome_accepted", operation_id="review-complete", attempt_id=attempt_id.value,
            owner_generation=1, payload={"disposition": "accepted"}, **common,
        ),
    ]
    return ConsumerResult(graph, _inspect(records))


if __name__ == "__main__":
    for result in (bounded_research_fan_out(), proposal_critique_transfer()):
        print(result.inspection["session_summary"])
