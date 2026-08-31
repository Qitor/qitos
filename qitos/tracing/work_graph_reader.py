"""Read-only work-graph views over the candidate Trajectory reader seam.

The builder consumes explicit record fields only.  It never decodes an ID,
directory, tool name, or message body to manufacture lineage.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from .trajectory import (
    LossEntry,
    LossReport,
    PrivacyView,
    RecordKind,
    RecordRole,
    Trajectory,
    TrajectoryQuery,
    TrajectoryRecord,
)


WORK_GRAPH_READ_MODEL_VERSION = "qitos.work_graph.read_model/candidate-1"
WORK_GRAPH_EVENT_CONTRACT = "qitos.work_graph.event/candidate-1"

WORK_GRAPH_EVENT_TYPES = frozenset(
    {
        "session_created",
        "session_restored",
        "session_forked",
        "run_started",
        "run_terminated",
        "work_declared",
        "work_attempt",
        "owner_assigned",
        "ownership_transfer_requested",
        "ownership_transfer_committed",
        "ownership_transfer_rejected",
        "delegate_declared",
        "spawn_declared",
        "fan_out_declared",
        "child_dispatched",
        "child_running",
        "child_paused",
        "child_waiting",
        "child_terminal",
        "cancellation_requested",
        "cancellation_acknowledged",
        "cancellation_unresolved",
        "child_detached",
        "supervision_declared",
        "join_declared",
        "join_progressed",
        "join_closed",
        "outcome_accepted",
        "outcome_discarded",
        "outcome_late",
        "outcome_stale",
        "outcome_unknown",
        "budget_allocated",
        "capability_allocated",
        "context_transferred",
        "continuation_transferred",
        "artifact_referenced",
        "process_loss_recovered",
        "generation_conflict",
        "loss_projected",
        "privacy_projected",
    }
)

_WORK_EVENTS = WORK_GRAPH_EVENT_TYPES - {
    "session_created",
    "session_restored",
    "session_forked",
    "run_started",
    "run_terminated",
    "loss_projected",
    "privacy_projected",
}
_ATTEMPT_EVENTS = frozenset(
    {
        "work_attempt",
        "child_dispatched",
        "child_running",
        "child_paused",
        "child_waiting",
        "child_terminal",
        "outcome_accepted",
        "outcome_discarded",
        "outcome_late",
        "outcome_stale",
        "outcome_unknown",
    }
)
_OWNER_EVENTS = frozenset(
    {
        "work_attempt",
        "owner_assigned",
        "ownership_transfer_requested",
        "ownership_transfer_committed",
        "ownership_transfer_rejected",
        "child_dispatched",
        "child_running",
        "child_paused",
        "child_waiting",
        "child_terminal",
        "cancellation_requested",
        "cancellation_acknowledged",
        "cancellation_unresolved",
        "outcome_accepted",
        "outcome_discarded",
        "outcome_late",
        "outcome_stale",
        "outcome_unknown",
        "generation_conflict",
    }
)


class WorkGraphReadError(RuntimeError):
    """Typed, non-echoing read or conformance failure."""

    def __init__(self, code: str, remediation: str) -> None:
        self.code = str(code)
        self.remediation = str(remediation)
        super().__init__(self.code)

    def to_dict(self) -> Dict[str, str]:
        return {
            "code": self.code,
            "remediation": self.remediation,
        }


@dataclass(frozen=True)
class GraphSelector:
    scope: str
    identity: str

    def __post_init__(self) -> None:
        if self.scope not in {"session", "run", "work", "attempt"}:
            raise WorkGraphReadError(
                "invalid_selector_scope",
                "select session, run, work, or attempt explicitly",
            )
        if not isinstance(self.identity, str) or not self.identity.strip():
            raise WorkGraphReadError(
                "invalid_selector_identity",
                "provide a non-empty opaque identity",
            )


@dataclass(frozen=True)
class TimelineEntry:
    record_id: str
    event_type: str
    occurred_at: str
    sequence: Optional[int]
    session_id: Optional[str]
    run_id: Optional[str]
    work_item_id: Optional[str]
    attempt_id: Optional[str]
    operation_id: Optional[str]
    owner_generation: Optional[int]
    parent_work_item_id: Optional[str]
    source_work_item_id: Optional[str]
    producer_authority: Optional[str]
    role: str
    payload: Dict[str, Any]
    loss: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return copy.deepcopy(self.__dict__)


@dataclass(frozen=True)
class WorkItemView:
    work_item_id: str
    session_id: Optional[str] = None
    parent_work_item_id: Optional[str] = None
    source_work_item_id: Optional[str] = None
    lifecycle: Optional[str] = None
    current_owner_id: Optional[str] = None
    owner_generation: Optional[int] = None
    detached: bool = False
    attempts: Tuple[Dict[str, Any], ...] = ()
    ownership_history: Tuple[Dict[str, Any], ...] = ()
    terminal_outcomes: Tuple[Dict[str, Any], ...] = ()
    unresolved_facts: Tuple[Dict[str, Any], ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return copy.deepcopy(self.__dict__)


@dataclass(frozen=True)
class WorkGraphReadModel:
    selector: GraphSelector
    session_summary: Dict[str, Any]
    authoritative_head: Dict[str, Any]
    work_items: Tuple[WorkItemView, ...]
    edges: Tuple[Dict[str, Any], ...]
    fan_out_groups: Tuple[Dict[str, Any], ...]
    joins: Tuple[Dict[str, Any], ...]
    cancellations: Tuple[Dict[str, Any], ...]
    detachments: Tuple[Dict[str, Any], ...]
    restore_generations: Tuple[Dict[str, Any], ...]
    timeline: Tuple[TimelineEntry, ...]
    completeness: Dict[str, Any]
    provenance: Dict[str, Any]
    schema_version: str = WORK_GRAPH_READ_MODEL_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "selector": copy.deepcopy(self.selector.__dict__),
            "session_summary": copy.deepcopy(self.session_summary),
            "authoritative_head": copy.deepcopy(self.authoritative_head),
            "work_items": [item.to_dict() for item in self.work_items],
            "edges": copy.deepcopy(list(self.edges)),
            "fan_out_groups": copy.deepcopy(list(self.fan_out_groups)),
            "joins": copy.deepcopy(list(self.joins)),
            "cancellations": copy.deepcopy(list(self.cancellations)),
            "detachments": copy.deepcopy(list(self.detachments)),
            "restore_generations": copy.deepcopy(list(self.restore_generations)),
            "timeline": [entry.to_dict() for entry in self.timeline],
            "completeness": copy.deepcopy(self.completeness),
            "provenance": copy.deepcopy(self.provenance),
        }


def work_graph_event_record(
    event_type: str,
    *,
    session_id: str,
    run_id: str,
    operation_id: str,
    producer_authority: str,
    record_provenance: Mapping[str, Any],
    payload: Optional[Mapping[str, Any]] = None,
    record_id: Optional[str] = None,
    sequence: Optional[int] = None,
    occurred_at: Optional[str] = None,
    work_item_id: Optional[str] = None,
    attempt_id: Optional[str] = None,
    owner_generation: Optional[int] = None,
    parent_run_id: Optional[str] = None,
    parent_work_item_id: Optional[str] = None,
    source_session_id: Optional[str] = None,
    source_work_item_id: Optional[str] = None,
    artifact_refs: Tuple[Any, ...] = (),
    loss: Optional[LossReport] = None,
) -> TrajectoryRecord:
    """Create one exact candidate work-graph fact with explicit authority."""
    if event_type not in WORK_GRAPH_EVENT_TYPES:
        raise WorkGraphReadError(
            "unknown_work_graph_event",
            "use the candidate work-graph event vocabulary",
        )
    required_text = {
        "session_id": session_id,
        "run_id": run_id,
        "operation_id": operation_id,
        "producer_authority": producer_authority,
    }
    if any(not isinstance(value, str) or not value.strip() for value in required_text.values()):
        raise WorkGraphReadError(
            "missing_event_identity",
            "supply explicit session, run, operation, and producer authority",
        )
    if event_type in _WORK_EVENTS and not work_item_id:
        raise WorkGraphReadError(
            "missing_work_identity",
            "supply an explicit work item identity",
        )
    if event_type in _ATTEMPT_EVENTS and not attempt_id:
        raise WorkGraphReadError(
            "missing_attempt_identity",
            "supply an explicit attempt identity",
        )
    if event_type in _OWNER_EVENTS and owner_generation is None:
        raise WorkGraphReadError(
            "missing_owner_generation",
            "supply the authoritative owner generation",
        )
    event_payload = copy.deepcopy(dict(payload or {}))
    event_payload["event_type"] = event_type
    record = TrajectoryRecord.create(
        RecordKind.WORK_GRAPH,
        role=RecordRole.CANONICAL_RUNTIME_FACT,
        payload=event_payload,
        record_id=record_id,
        session_id=session_id,
        run_id=run_id,
        work_item_id=work_item_id,
        attempt_id=attempt_id,
        owner_generation=owner_generation,
        operation_id=operation_id,
        producer_authority=producer_authority,
        record_provenance=copy.deepcopy(dict(record_provenance)),
        parent_run_id=parent_run_id,
        parent_work_item_id=parent_work_item_id,
        source_session_id=source_session_id,
        source_work_item_id=source_work_item_id,
        artifact_refs=artifact_refs,
        loss=loss or LossReport(),
        **({"occurred_at": occurred_at} if occurred_at else {}),
    )
    return record.with_sequence(sequence) if sequence is not None else record


def _event_type(record: TrajectoryRecord) -> str:
    value = record.payload.get("event_type")
    return str(value) if value is not None else record.kind.value


def _record_fact(record: TrajectoryRecord) -> Dict[str, Any]:
    return {
        "record_id": record.record_id,
        "event_type": _event_type(record),
        "operation_id": record.operation_id,
        "attempt_id": record.attempt_id,
        "owner_generation": record.owner_generation,
        "occurred_at": record.occurred_at,
        "payload": copy.deepcopy(record.payload),
    }


def _matching_records(
    records: Iterable[TrajectoryRecord], selector: GraphSelector
) -> Tuple[TrajectoryRecord, ...]:
    if selector.scope == "session":
        return tuple(record for record in records if record.session_id == selector.identity)
    if selector.scope == "run":
        return tuple(record for record in records if record.run_id == selector.identity)
    if selector.scope == "work":
        selected_ids = {selector.identity}
        changed = True
        materialized = tuple(records)
        while changed:
            changed = False
            for record in materialized:
                if record.parent_work_item_id in selected_ids and record.work_item_id:
                    if record.work_item_id not in selected_ids:
                        selected_ids.add(record.work_item_id)
                        changed = True
        return tuple(
            record
            for record in materialized
            if record.work_item_id in selected_ids
            or record.parent_work_item_id in selected_ids
            or record.source_work_item_id in selected_ids
        )
    return tuple(record for record in records if record.attempt_id == selector.identity)


def build_work_graph_read_model(
    trajectory: Trajectory, selector: GraphSelector
) -> WorkGraphReadModel:
    """Build a unified graph/timeline projection from explicit facts only."""
    records = _matching_records(trajectory.records, selector)
    work_state: Dict[str, Dict[str, Any]] = {}
    edges: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    fan_out: Dict[str, Dict[str, Any]] = {}
    joins: Dict[str, Dict[str, Any]] = {}
    cancellations: list[Dict[str, Any]] = []
    detachments: list[Dict[str, Any]] = []
    restores: list[Dict[str, Any]] = []
    heads: list[Dict[str, Any]] = []
    timeline = []
    missing_authority = 0
    unknown_event = 0

    for record in records:
        event_type = _event_type(record)
        if event_type not in WORK_GRAPH_EVENT_TYPES:
            unknown_event += 1
        if record.role == RecordRole.CANONICAL_RUNTIME_FACT and not record.producer_authority:
            missing_authority += 1
        timeline.append(
            TimelineEntry(
                record_id=record.record_id,
                event_type=event_type,
                occurred_at=record.occurred_at,
                sequence=record.sequence,
                session_id=record.session_id,
                run_id=record.run_id,
                work_item_id=record.work_item_id,
                attempt_id=record.attempt_id,
                operation_id=record.operation_id,
                owner_generation=record.owner_generation,
                parent_work_item_id=record.parent_work_item_id,
                source_work_item_id=record.source_work_item_id,
                producer_authority=record.producer_authority,
                role=record.role.value,
                payload=copy.deepcopy(record.payload),
                loss=record.loss.to_dict(),
            )
        )

        payload = record.payload
        if record.work_item_id:
            item = work_state.setdefault(
                record.work_item_id,
                {
                    "work_item_id": record.work_item_id,
                    "session_id": record.session_id,
                    "parent_work_item_id": record.parent_work_item_id,
                    "source_work_item_id": record.source_work_item_id,
                    "lifecycle": None,
                    "current_owner_id": None,
                    "owner_generation": record.owner_generation,
                    "detached": False,
                    "attempts": [],
                    "ownership_history": [],
                    "terminal_outcomes": [],
                    "unresolved_facts": [],
                },
            )
            for field_name in ("lifecycle", "owner_id"):
                if payload.get(field_name) is not None:
                    target = "current_owner_id" if field_name == "owner_id" else field_name
                    item[target] = str(payload[field_name])
            if record.owner_generation is not None:
                item["owner_generation"] = record.owner_generation
            if event_type in _ATTEMPT_EVENTS:
                item["attempts"].append(_record_fact(record))
            if event_type in {
                "owner_assigned",
                "ownership_transfer_requested",
                "ownership_transfer_committed",
                "ownership_transfer_rejected",
                "generation_conflict",
            }:
                item["ownership_history"].append(_record_fact(record))
                if event_type == "ownership_transfer_committed" and payload.get("to_owner_id"):
                    item["current_owner_id"] = str(payload["to_owner_id"])
            if event_type in {
                "child_terminal",
                "outcome_accepted",
                "outcome_discarded",
                "outcome_late",
                "outcome_stale",
            }:
                item["terminal_outcomes"].append(_record_fact(record))
            if event_type in {"outcome_unknown", "cancellation_unresolved", "generation_conflict"}:
                item["unresolved_facts"].append(_record_fact(record))
            if event_type == "child_detached":
                item["detached"] = True

        if (
            event_type
            in {"work_declared", "delegate_declared", "spawn_declared", "fan_out_declared"}
            and record.parent_work_item_id
            and record.work_item_id
        ):
            key = (
                record.parent_work_item_id,
                record.work_item_id,
                record.operation_id,
            )
            edges[key] = {
                "parent_work_item_id": record.parent_work_item_id,
                "child_work_item_id": record.work_item_id,
                "source_work_item_id": record.source_work_item_id,
                "operation_id": record.operation_id,
                "operation": payload.get("operation"),
            }
        if event_type == "fan_out_declared" and record.operation_id:
            fan_out[record.operation_id] = _record_fact(record)
        if event_type.startswith("join_") and record.operation_id:
            join = joins.setdefault(
                record.operation_id,
                {"operation_id": record.operation_id, "history": []},
            )
            join["history"].append(_record_fact(record))
            join["status"] = event_type.removeprefix("join_")
            for name in ("policy", "expected_child_ids", "accepted_child_ids", "outstanding_child_ids", "receipt"):
                if name in payload:
                    join[name] = copy.deepcopy(payload[name])
        if event_type.startswith("cancellation_"):
            cancellations.append(_record_fact(record))
        if event_type in {"child_detached", "supervision_declared"}:
            detachments.append(_record_fact(record))
        if event_type in {"session_restored", "session_forked", "process_loss_recovered"}:
            restores.append(_record_fact(record))
        if isinstance(payload.get("authoritative_head"), Mapping):
            heads.append(copy.deepcopy(dict(payload["authoritative_head"])))

    timeline.sort(
        key=lambda item: (
            item.sequence is None,
            item.sequence if item.sequence is not None else 0,
            item.occurred_at,
            item.record_id,
        )
    )
    work_items = tuple(
        WorkItemView(
            **{
                **value,
                "attempts": tuple(value["attempts"]),
                "ownership_history": tuple(value["ownership_history"]),
                "terminal_outcomes": tuple(value["terminal_outcomes"]),
                "unresolved_facts": tuple(value["unresolved_facts"]),
            }
        )
        for _, value in sorted(work_state.items())
    )
    loss_entries = list(trajectory.loss.entries)
    if missing_authority:
        loss_entries.append(
            LossEntry(
                "missing_producer_authority",
                count=missing_authority,
                consequence="record_authority_unknown",
            )
        )
    if unknown_event:
        loss_entries.append(
            LossEntry(
                "unrecognized_work_graph_event",
                count=unknown_event,
                consequence="read_model_incomplete",
            )
        )
    if not records:
        loss_entries.append(
            LossEntry(
                "selector_has_no_facts",
                consequence="requested_identity_unavailable",
            )
        )
    combined_loss = LossReport(
        policy_id=trajectory.loss.policy_id,
        entries=tuple(loss_entries),
    )
    session_ids = tuple(dict.fromkeys(record.session_id for record in records if record.session_id))
    run_ids = tuple(dict.fromkeys(record.run_id for record in records if record.run_id))
    lifecycles = [
        str(record.payload["lifecycle"])
        for record in records
        if record.payload.get("lifecycle") is not None
    ]
    return WorkGraphReadModel(
        selector=selector,
        session_summary={
            "session_ids": list(session_ids),
            "run_ids": list(run_ids),
            "latest_lifecycle": lifecycles[-1] if lifecycles else None,
            "work_item_count": len(work_items),
            "unresolved_count": sum(len(item.unresolved_facts) for item in work_items),
        },
        authoritative_head=heads[-1] if heads else {},
        work_items=work_items,
        edges=tuple(edges.values()),
        fan_out_groups=tuple(fan_out[key] for key in sorted(fan_out)),
        joins=tuple(joins[key] for key in sorted(joins)),
        cancellations=tuple(cancellations),
        detachments=tuple(detachments),
        restore_generations=tuple(restores),
        timeline=tuple(timeline),
        completeness={
            "complete": combined_loss.is_lossless,
            "loss": combined_loss.to_dict(),
            "fact_count": len(records),
        },
        provenance=copy.deepcopy(trajectory.provenance),
    )


class WorkGraphReader:
    """Read-model client over any structural ``TrajectoryReader``."""

    def __init__(self, reader: Any) -> None:
        self._reader = reader

    @property
    def source_capabilities(self) -> Any:
        return self._reader.capabilities

    def read(self, selector: GraphSelector) -> WorkGraphReadModel:
        try:
            if selector.scope == "session":
                if not self._reader.capabilities.session_query:
                    raise WorkGraphReadError(
                        "session_query_unavailable",
                        "use an explicit run selector or a session-capable reader",
                    )
                trajectory = self._reader.read_session(
                    selector.identity, view=PrivacyView.REDACTED_PUBLIC
                )
            elif selector.scope == "run":
                trajectory = self._reader.read_run(
                    selector.identity, view=PrivacyView.REDACTED_PUBLIC
                )
            elif selector.scope == "work":
                records = self._reader.replay(
                    TrajectoryQuery(),
                    view=PrivacyView.REDACTED_PUBLIC,
                )
                trajectory = Trajectory(
                    records=tuple(records),
                    privacy_view=PrivacyView.REDACTED_PUBLIC,
                    provenance={
                        "reader_id": self._reader.capabilities.reader_id,
                        "source_kind": self._reader.capabilities.source_kind,
                    },
                )
            else:
                records = self._reader.replay(
                    TrajectoryQuery(), view=PrivacyView.REDACTED_PUBLIC
                )
                selected = tuple(
                    record for record in records if record.attempt_id == selector.identity
                )
                trajectory = Trajectory(
                    records=selected,
                    privacy_view=PrivacyView.REDACTED_PUBLIC,
                    provenance={
                        "reader_id": self._reader.capabilities.reader_id,
                        "source_kind": self._reader.capabilities.source_kind,
                    },
                )
        except WorkGraphReadError:
            raise
        except (FileNotFoundError, LookupError, ValueError) as exc:
            raise WorkGraphReadError(
                "reader_fact_unavailable",
                "select an identity present in the configured read-only source",
            ) from exc
        return build_work_graph_read_model(trajectory, selector)


__all__ = [
    "WORK_GRAPH_EVENT_CONTRACT",
    "WORK_GRAPH_EVENT_TYPES",
    "WORK_GRAPH_READ_MODEL_VERSION",
    "GraphSelector",
    "TimelineEntry",
    "WorkGraphReadError",
    "WorkGraphReadModel",
    "WorkGraphReader",
    "WorkItemView",
    "build_work_graph_read_model",
    "work_graph_event_record",
]
