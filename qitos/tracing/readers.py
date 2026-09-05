"""Trajectory reader protocol and compatibility/store reader adapters."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Protocol, Tuple, runtime_checkable

from .paging import BoundedReadUnsupported, JournalPages, TrajectoryCursor, TrajectoryPage
from .adapters import classify_event
from .privacy import project_data
from .sinks import project_record
from .store import StoreIntegrityReport, TrajectoryStore
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


@dataclass(frozen=True)
class ReaderCapabilities:
    reader_id: str
    source_kind: str
    supported_views: Tuple[PrivacyView, ...]
    session_query: bool
    live_tail: bool = False
    default_qualified: bool = False
    bounded_read: bool = False


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    status: Optional[str]
    updated_at: Optional[str]
    step_count: int
    event_count: int
    stop_reason: Optional[str]
    final_result: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.run_id,
            "run_id": self.run_id,
            "status": self.status,
            "updated_at": self.updated_at,
            "step_count": self.step_count,
            "event_count": self.event_count,
            "stop_reason": self.stop_reason,
            "final_result": copy.deepcopy(self.final_result),
            **copy.deepcopy(self.metadata),
        }


@dataclass(frozen=True)
class ReaderIntegrityReport:
    valid: bool
    source_kind: str
    record_count: int
    findings: Tuple[str, ...] = ()


@runtime_checkable
class TrajectoryReader(Protocol):
    """Read-only protocol used by qita, exporters and evaluators."""

    @property
    def capabilities(self) -> ReaderCapabilities:
        ...

    def discover_runs(self) -> Tuple[RunSummary, ...]:
        ...

    def read_run(
        self,
        run_id: str,
        *,
        view: PrivacyView = PrivacyView.REDACTED_PUBLIC,
    ) -> Trajectory:
        ...

    def read_session(
        self,
        session_id: str,
        *,
        view: PrivacyView = PrivacyView.REDACTED_PUBLIC,
    ) -> Trajectory:
        ...

    def replay(
        self,
        query: TrajectoryQuery,
        *,
        view: PrivacyView = PrivacyView.REDACTED_PUBLIC,
    ) -> Tuple[TrajectoryRecord, ...]:
        ...

    def validate_integrity(self) -> ReaderIntegrityReport:
        ...


def _json_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


def _jsonl_file(path: Path) -> Tuple[List[Dict[str, Any]], int]:
    if not path.exists():
        return [], 0
    records: List[Dict[str, Any]] = []
    invalid = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            invalid += 1
            continue
        if isinstance(value, dict):
            records.append(value)
        else:
            invalid += 1
    return records, invalid


def _manifest_summary(manifest: Mapping[str, Any]) -> RunSummary:
    summary = manifest.get("summary")
    if not isinstance(summary, Mapping):
        summary = {}
    topology = manifest.get("agent_topology")
    agent_names: List[Any] = []
    if isinstance(topology, Mapping):
        maybe_agents = topology.get("agents")
        if isinstance(maybe_agents, list):
            agent_names = maybe_agents
    elif manifest.get("agent_name"):
        agent_names = [manifest.get("agent_name")]
    run_meta = summary.get("run_meta")
    if not isinstance(run_meta, Mapping):
        run_meta = {}
    harness = run_meta.get("harness")
    prompt = run_meta.get("prompt")
    return RunSummary(
        run_id=str(manifest.get("run_id", "")),
        status=(str(manifest["status"]) if manifest.get("status") is not None else None),
        updated_at=(
            str(manifest["updated_at"])
            if manifest.get("updated_at") is not None
            else None
        ),
        step_count=int(manifest.get("step_count", 0) or 0),
        event_count=int(manifest.get("event_count", 0) or 0),
        stop_reason=(
            str(summary["stop_reason"])
            if summary.get("stop_reason") is not None
            else None
        ),
        final_result=summary.get("final_result"),
        metadata={
            "agent_name": manifest.get("agent_name"),
            "agent_topology": topology,
            "handoff_count": manifest.get("handoff_count"),
            "agent_count": len(agent_names),
            "manifest_meta": {
                "schema_version": manifest.get("schema_version"),
                "model_id": manifest.get("model_id"),
                "model_family": manifest.get("model_family"),
                "family_preset": (
                    harness.get("family_preset")
                    if isinstance(harness, Mapping)
                    else None
                ),
                "prompt_hash": manifest.get("prompt_hash"),
                "benchmark_name": manifest.get("benchmark_name"),
                "benchmark_split": manifest.get("benchmark_split"),
                "prompt_builder": (
                    prompt.get("prompt_builder")
                    if isinstance(prompt, Mapping)
                    else None
                ),
                "protocol": run_meta.get("protocol"),
                "protocol_resolution_source": run_meta.get(
                    "protocol_resolution_source"
                ),
                "prompt_protocol": manifest.get("prompt_protocol"),
                "parser_name": manifest.get("parser_name"),
                "run_config_hash": manifest.get("run_config_hash"),
                "seed": manifest.get("seed"),
                "git_sha": manifest.get("git_sha"),
                "package_version": manifest.get("package_version"),
                "official_run": manifest.get("official_run"),
                "replay_mode": manifest.get("replay_mode"),
                "replay_note": manifest.get("replay_note"),
                "summary_steps": summary.get("steps"),
                "token_usage": summary.get(
                    "token_usage", manifest.get("token_usage")
                ),
                "latency_seconds": manifest.get("latency_seconds"),
                "cost": manifest.get("cost"),
                "context": summary.get("context"),
                "parser": summary.get("parser"),
                "run_spec": manifest.get("run_spec"),
                "experiment_spec": manifest.get("experiment_spec"),
            },
            "source_kind": "frozen_trace_compatibility",
        },
    )


class TraceCompatibilityReader:
    """Additive reader for the frozen manifest/events/steps trace contract."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).resolve()

    @property
    def capabilities(self) -> ReaderCapabilities:
        return ReaderCapabilities(
            reader_id="qitos.trace_compatibility_reader",
            source_kind="frozen_trace_compatibility",
            supported_views=(
                PrivacyView.RAW_PRIVATE,
                PrivacyView.REDACTED_PUBLIC,
                PrivacyView.SAFE_DIAGNOSTIC,
            ),
            session_query=False,
            live_tail=True,
            default_qualified=True,
        )

    def _run_dir(self, run_id: str) -> Path:
        if not run_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for char in run_id):
            raise ValueError("invalid run id")
        path = (self._root / run_id).resolve()
        if path.parent != self._root or not path.is_dir():
            raise FileNotFoundError(f"run not found: {run_id}")
        return path

    def discover_runs(self) -> Tuple[RunSummary, ...]:
        summaries: List[RunSummary] = []
        if not self._root.exists():
            return ()
        for path in sorted(self._root.iterdir()):
            if not path.is_dir() or not (path / "manifest.json").is_file():
                continue
            try:
                manifest = _json_file(path / "manifest.json")
                if not manifest.get("run_id"):
                    manifest["run_id"] = path.name
                summaries.append(_manifest_summary(manifest))
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                continue
        return tuple(summaries)

    def _read_private(self, run_id: str) -> Trajectory:
        run_dir = self._run_dir(run_id)
        manifest = _json_file(run_dir / "manifest.json")
        events, invalid_events = _jsonl_file(run_dir / "events.jsonl")
        steps, invalid_steps = _jsonl_file(run_dir / "steps.jsonl")
        manifest_run_id = str(manifest.get("run_id") or run_id)
        losses = [
            LossEntry("compatibility_trace_input", consequence="known_v1_gaps"),
            LossEntry("missing_session_id", consequence="session_query_unavailable"),
            LossEntry("missing_work_item_id", consequence="work_graph_unavailable"),
            LossEntry("missing_snapshot_lineage", consequence="restore_lineage_unavailable"),
        ]
        if manifest.get("parent_run_id"):
            losses.append(
                LossEntry(
                    "unverified_parent_run_metadata",
                    consequence="not_promoted_to_lineage",
                )
            )
        if invalid_events:
            losses.append(
                LossEntry(
                    "invalid_compatibility_event",
                    count=invalid_events,
                    consequence="event_omitted",
                )
            )
        if invalid_steps:
            losses.append(
                LossEntry(
                    "invalid_compatibility_step",
                    count=invalid_steps,
                    consequence="step_omitted",
                )
            )
        loss = LossReport(
            policy_id="qitos.compatibility/frozen-trace-v1",
            entries=tuple(losses),
        )
        records: List[TrajectoryRecord] = []
        for index, event in enumerate(events):
            step_id = event.get("step_id")
            records.append(
                TrajectoryRecord.create(
                    classify_event(
                        str(event.get("phase", "")),
                        (
                            event.get("payload")
                            if isinstance(event.get("payload"), Mapping)
                            else {}
                        ),
                        ok=bool(event.get("ok", True)),
                        error=event.get("error"),
                    ),
                    role=RecordRole.COMPATIBILITY_ARTIFACT,
                    record_id=f"compat-event-{manifest_run_id}-{index}",
                    run_id=manifest_run_id,
                    step_id=(int(step_id) if step_id is not None else None),
                    phase=(str(event["phase"]) if event.get("phase") else None),
                    agent_id=(
                        str(event["agent_id"])
                        if event.get("agent_id") is not None
                        else None
                    ),
                    occurred_at=str(event.get("ts") or "unknown"),
                    payload=event,
                    loss=loss,
                ).with_sequence(len(records))
            )
        for index, step in enumerate(steps):
            step_id = step.get("step_id")
            records.append(
                TrajectoryRecord.create(
                    RecordKind.STEP,
                    role=RecordRole.COMPATIBILITY_ARTIFACT,
                    record_id=f"compat-step-{manifest_run_id}-{index}",
                    run_id=manifest_run_id,
                    step_id=(int(step_id) if step_id is not None else None),
                    agent_id=(
                        str(step["agent_id"])
                        if step.get("agent_id") is not None
                        else None
                    ),
                    payload=step,
                    loss=loss,
                ).with_sequence(len(records))
            )
        return Trajectory(
            records=tuple(records),
            metadata={
                "manifest": manifest,
                "events": events,
                "steps": steps,
                "source_run_id": run_id,
            },
            provenance={
                "reader_id": self.capabilities.reader_id,
                "source_kind": self.capabilities.source_kind,
                "source_schema": manifest.get("schema_version", "v1"),
            },
            privacy_view=PrivacyView.RAW_PRIVATE,
            loss=loss,
        )

    @staticmethod
    def _project(trajectory: Trajectory, view: PrivacyView) -> Trajectory:
        if view == PrivacyView.RAW_PRIVATE:
            return Trajectory.from_dict(trajectory.to_dict())
        records = tuple(project_record(record, view) for record in trajectory.records)
        metadata_projection = project_data(trajectory.metadata, view=view)
        provenance_projection = project_data(trajectory.provenance, view=view)
        return Trajectory(
            records=records,
            metadata=copy.deepcopy(dict(metadata_projection.data or {})),
            provenance=copy.deepcopy(dict(provenance_projection.data or {})),
            privacy_view=view,
            loss=trajectory.loss.merged(
                *(record.loss for record in records),
                metadata_projection.loss,
                provenance_projection.loss,
            ),
        )

    def read_run(
        self,
        run_id: str,
        *,
        view: PrivacyView = PrivacyView.REDACTED_PUBLIC,
    ) -> Trajectory:
        return self._project(self._read_private(run_id), view)

    def read_session(
        self,
        session_id: str,
        *,
        view: PrivacyView = PrivacyView.REDACTED_PUBLIC,
    ) -> Trajectory:
        raise LookupError(
            "session_query_unavailable: frozen trace does not contain session identity"
        )

    def replay(
        self,
        query: TrajectoryQuery,
        *,
        view: PrivacyView = PrivacyView.REDACTED_PUBLIC,
    ) -> Tuple[TrajectoryRecord, ...]:
        if query.run_id is None:
            raise ValueError("frozen trace replay requires run_id")
        trajectory = self.read_run(query.run_id, view=view)
        records = trajectory.records
        if query.after_sequence is not None:
            records = tuple(
                record
                for record in records
                if record.sequence is not None
                and record.sequence > query.after_sequence
            )
        if query.kinds:
            records = tuple(record for record in records if record.kind in query.kinds)
        if query.limit is not None:
            records = records[: query.limit]
        return records

    def validate_integrity(self) -> ReaderIntegrityReport:
        findings: List[str] = []
        count = 0
        for summary in self.discover_runs():
            try:
                trajectory = self._read_private(summary.run_id)
            except (OSError, ValueError, json.JSONDecodeError):
                findings.append("compatibility_read_failed")
                continue
            count += len(trajectory.records)
            if trajectory.validate_integrity():
                findings.append("record_integrity_mismatch")
        return ReaderIntegrityReport(
            valid=not findings,
            source_kind=self.capabilities.source_kind,
            record_count=count,
            findings=tuple(findings),
        )


def _canonical_run_payload(records: Tuple[TrajectoryRecord, ...]) -> Dict[str, Any]:
    """Project explicit runtime start/stop facts into qita's existing summary."""
    initial = next((record for record in records if record.kind == RecordKind.RUN), None)
    if initial is None:
        return {}
    payload = copy.deepcopy(initial.payload)
    if not isinstance(payload.get("payload"), Mapping) or "ok" not in payload:
        return payload
    payload = dict(payload["payload"])
    summary: Dict[str, Any] = {}
    lifecycle = None
    for record in records:
        if record.kind == RecordKind.SESSION and record.lifecycle_state:
            lifecycle = record.lifecycle_state
        detail = record.payload.get("payload", {})
        if isinstance(detail, Mapping) and detail.get("stop_reason"):
            summary["stop_reason"] = detail["stop_reason"]
            if "final_result" in detail:
                summary["final_result"] = detail["final_result"]
    reason = summary.get("stop_reason")
    status = lifecycle or ({"final": "completed", "unrecoverable_error": "failed"}.get(reason)
                           if reason else None)
    return {"run_id": initial.run_id, "status": status, "summary": summary,
            "run_meta": payload.get("run_meta", {})}


class StoreTrajectoryReader:
    """Reader adapter for any conforming trajectory store."""

    def __init__(self, store: TrajectoryStore) -> None:
        self._materialized: TrajectoryStore | None = store
        self._pages: JournalPages | None = None

    @classmethod
    def from_journal(cls, path: str | Path) -> "StoreTrajectoryReader":
        """Open a validated read-only journal without materializing its history."""
        reader = cls.__new__(cls)
        reader._materialized = None
        reader._pages = JournalPages(path)
        return reader

    @property
    def _store(self) -> TrajectoryStore:
        # Old complete-read/discovery APIs keep their documented memory cost.
        if self._materialized is None:
            from .journal_store import JournalTrajectoryStore
            if self._pages is None:
                raise BoundedReadUnsupported("journal_source_unavailable")
            return JournalTrajectoryStore(self._pages.path, read_only=True)
        return self._materialized

    @property
    def work(self) -> Any:
        return self._pages.work if self._pages is not None else None

    def read_page(self, query: TrajectoryQuery, cursor: TrajectoryCursor | None = None,
                  *, view: PrivacyView = PrivacyView.REDACTED_PUBLIC) -> TrajectoryPage:
        if self._pages is None:
            raise BoundedReadUnsupported("bounded_read_unsupported")
        return self._pages.read_page(query, cursor, view=view)

    def validate_export_target(self, target: str | Path) -> None:
        """Keep the read-only source and its sidecars outside export replacement."""
        from .exporter import TrajectoryExportError
        if self._pages is not None:
            source = self._pages.path
            protected = (source, source.with_name(source.name + ".lock"),
                         source.with_name(source.name + ".index.json"))
            if Path(target).resolve() in {path.resolve() for path in protected}:
                raise TrajectoryExportError("export_target_is_source")

    def validate_snapshot(self, snapshot: TrajectoryCursor) -> None:
        if self._pages is None:
            raise BoundedReadUnsupported("bounded_read_unsupported")
        self._pages.validate_snapshot(snapshot)

    def close(self) -> None:
        if self._pages is not None:
            self._pages.close()
        if self._materialized is not None:
            self._materialized.close()

    @property
    def capabilities(self) -> ReaderCapabilities:
        return ReaderCapabilities(
            reader_id="qitos.store_trajectory_reader",
            source_kind="candidate_trajectory_store",
            supported_views=(
                PrivacyView.RAW_PRIVATE,
                PrivacyView.REDACTED_PUBLIC,
                PrivacyView.SAFE_DIAGNOSTIC,
            ),
            session_query=True,
            default_qualified=False,
            bounded_read=self._pages is not None,
        )

    @staticmethod
    def _project(trajectory: Trajectory, view: PrivacyView) -> Trajectory:
        return TraceCompatibilityReader._project(trajectory, view)

    def discover_runs(self) -> Tuple[RunSummary, ...]:
        records_list: List[TrajectoryRecord] = []
        store = self._store
        limit = store.capabilities.max_query_records
        query = TrajectoryQuery(limit=limit)
        while True:
            page = store.query(query)
            records_list.extend(page)
            if len(page) < limit:
                break
            query = TrajectoryQuery(limit=limit, after_sequence=page[-1].sequence)
        records = tuple(records_list)
        run_ids = tuple(
            dict.fromkeys(record.run_id for record in records if record.run_id)
        )
        summaries: List[RunSummary] = []
        for run_id in run_ids:
            run_records = tuple(record for record in records if record.run_id == run_id)
            run_payload: Mapping[str, Any] = _canonical_run_payload(run_records)
            summary_payload = run_payload.get("summary")
            if not isinstance(summary_payload, Mapping):
                summary_payload = {}
            summaries.append(
                RunSummary(
                    run_id=str(run_id),
                    status=(
                        str(run_payload["status"])
                        if run_payload.get("status") is not None
                        else None
                    ),
                    updated_at=(
                        run_records[-1].recorded_at if run_records else None
                    ),
                    step_count=len(
                        [record for record in run_records if record.kind == RecordKind.STEP]
                    ),
                    event_count=len(run_records),
                    stop_reason=(
                        str(summary_payload["stop_reason"])
                        if summary_payload.get("stop_reason") is not None
                        else None
                    ),
                    final_result=summary_payload.get("final_result"),
                    metadata={
                        "source_kind": self.capabilities.source_kind,
                        "manifest_meta": {
                            "schema_version": "candidate-unfrozen"
                        },
                    },
                )
            )
        return tuple(summaries)

    def read_run(
        self,
        run_id: str,
        *,
        view: PrivacyView = PrivacyView.REDACTED_PUBLIC,
    ) -> Trajectory:
        return self._project(self._store.read_run(run_id), view)

    def read_session(
        self,
        session_id: str,
        *,
        view: PrivacyView = PrivacyView.REDACTED_PUBLIC,
    ) -> Trajectory:
        return self._project(self._store.read_session(session_id), view)

    def replay(
        self,
        query: TrajectoryQuery,
        *,
        view: PrivacyView = PrivacyView.REDACTED_PUBLIC,
    ) -> Tuple[TrajectoryRecord, ...]:
        records = self._store.replay(query)
        return tuple(project_record(record, view) for record in records)

    def validate_integrity(self) -> ReaderIntegrityReport:
        report: StoreIntegrityReport = self._store.validate_integrity()
        findings: List[str] = []
        if report.invalid_record_ids:
            findings.append("record_integrity_mismatch")
        if report.duplicate_record_ids:
            findings.append("duplicate_record_id")
        if report.sequence_gaps:
            findings.append("sequence_gap")
        if report.store_digest_valid is False:
            findings.append("store_digest_mismatch")
        return ReaderIntegrityReport(
            valid=report.valid,
            source_kind=self.capabilities.source_kind,
            record_count=report.record_count,
            findings=tuple(findings),
        )


def trajectory_to_qita_payload(trajectory: Trajectory) -> Dict[str, Any]:
    """Build qita's established payload shape from a reader result."""
    metadata = trajectory.metadata
    manifest = copy.deepcopy(dict(metadata.get("manifest") or {}))
    events = copy.deepcopy(list(metadata.get("events") or []))
    steps = copy.deepcopy(list(metadata.get("steps") or []))
    if not events:
        for record in trajectory.records:
            if record.kind == RecordKind.STEP:
                continue
            payload = copy.deepcopy(record.payload)
            if record.role == RecordRole.COMPATIBILITY_ARTIFACT and isinstance(payload, dict):
                events.append(payload)
                continue
            events.append(
                {
                    "record_id": record.record_id,
                    "step_id": record.step_id,
                    "phase": record.phase or record.kind.value,
                    "ok": record.kind != RecordKind.ERROR,
                    "ts": record.occurred_at,
                    "payload": payload,
                }
            )
    if not steps:
        steps = [
            copy.deepcopy(record.payload)
            for record in trajectory.records
            if record.kind == RecordKind.STEP
        ]
    if not manifest:
        manifest = _canonical_run_payload(trajectory.records)
    run_id = str(
        manifest.get("run_id")
        or next((record.run_id for record in trajectory.records if record.run_id), "")
    )
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        grouped.setdefault(str(event.get("step_id", "none")), []).append(event)
    tool_effect_timeline = [
        record.to_dict()
        for record in trajectory.records
        if record.kind in {RecordKind.TOOL_BATCH, RecordKind.TOOL_SLOT, RecordKind.EFFECT}
    ]
    snapshot_lineage = [
        record.to_dict()
        for record in trajectory.records
        if record.kind
        in {
            RecordKind.SNAPSHOT,
            RecordKind.PAUSE,
            RecordKind.RESTORE,
            RecordKind.WORK_GRAPH,
            RecordKind.STEERING,
        }
    ]
    work_graph = [
        record.to_dict()
        for record in trajectory.records
        if record.kind == RecordKind.WORK_GRAPH
    ]
    return {
        "run_id": run_id,
        "manifest": manifest,
        "events": events,
        "steps": steps,
        "events_by_step": grouped,
        "tool_effect_timeline": tool_effect_timeline,
        "snapshot_lineage": snapshot_lineage,
        "work_graph": work_graph,
        "trajectory_meta": {
            "schema_version": trajectory.schema_version,
            "privacy_view": trajectory.privacy_view.value,
            "provenance": copy.deepcopy(trajectory.provenance),
            "loss": trajectory.loss.to_dict(),
            "session_ids": list(trajectory.session_ids),
            "run_ids": list(trajectory.run_ids),
        },
    }


__all__ = [
    "ReaderCapabilities",
    "ReaderIntegrityReport",
    "RunSummary",
    "StoreTrajectoryReader",
    "TraceCompatibilityReader",
    "TrajectoryReader",
    "trajectory_to_qita_payload",
]
