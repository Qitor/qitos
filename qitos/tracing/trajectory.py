"""Unfrozen candidate contracts for one future QitOS Trajectory architecture.

The serialized schema has a version because stored bytes need a migration
identity.  The Python concepts deliberately do not carry generation suffixes.
This module is not exported from :mod:`qitos` and is not an Engine persistence
truth.
"""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from qitos.core.artifact import ArtifactRef


TRAJECTORY_SCHEMA_VERSION = "qitos.trajectory/candidate-1"
EXPORT_SCHEMA_VERSION = "qitos.trajectory-export/candidate-1"
STORE_SCHEMA_VERSION = "qitos.trajectory-store/candidate-1"


def utc_now() -> str:
    """Return an RFC 3339-compatible UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def canonical_json_bytes(value: Any) -> bytes:
    """Encode JSON data deterministically for integrity checks."""
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def integrity_digest(value: Any) -> str:
    """Return the sha256 digest of a canonical JSON representation."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


class RecordKind(str, Enum):
    """Low-cardinality vocabulary for runtime facts and declared views."""

    SESSION = "session"
    RUN = "run"
    MODEL_REQUEST = "model_request"
    MODEL_RESPONSE = "model_response"
    REASONING = "reasoning"
    CONTINUATION = "continuation"
    TOOL_BATCH = "tool_batch"
    TOOL_SLOT = "tool_slot"
    LIFECYCLE = "lifecycle"
    EFFECT = "effect"
    CONTEXT = "context"
    COMPACTION = "compaction"
    STEERING = "steering"
    SNAPSHOT = "snapshot"
    PAUSE = "pause"
    RESTORE = "restore"
    BUDGET = "budget"
    STOP = "stop"
    ERROR = "error"
    LOSS = "loss"
    ARTIFACT = "artifact"
    WORK_GRAPH = "work_graph"
    STEP = "step"


class RecordRole(str, Enum):
    """Authority role of a record; role is never inferred from its kind."""

    CANONICAL_RUNTIME_FACT = "canonical_runtime_fact"
    DERIVED_VIEW = "derived_view"
    COMPATIBILITY_ARTIFACT = "compatibility_artifact"


class PrivacyView(str, Enum):
    """Named projections over canonical raw data."""

    RAW_PRIVATE = "raw_private"
    REDACTED_PUBLIC = "redacted_public"
    SAFE_DIAGNOSTIC = "safe_diagnostic"


@dataclass(frozen=True)
class LossEntry:
    """One machine-readable omission, redaction, or uncertainty."""

    code: str
    scope: str = "record"
    count: int = 1
    consequence: str = "information_unavailable"

    def __post_init__(self) -> None:
        if self.count < 0:
            raise ValueError("loss count must be non-negative")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "scope": self.scope,
            "count": self.count,
            "consequence": self.consequence,
        }


@dataclass(frozen=True)
class LossReport:
    """Explicit fidelity report carried by readers, exporters and evaluators."""

    policy_id: str = "qitos.loss/none"
    entries: Tuple[LossEntry, ...] = ()

    @property
    def is_lossless(self) -> bool:
        return not self.entries

    def merged(self, *others: "LossReport") -> "LossReport":
        entries = list(self.entries)
        policy_ids = [self.policy_id]
        for other in others:
            entries.extend(other.entries)
            policy_ids.append(other.policy_id)
        policy_id = "+".join(dict.fromkeys(policy_ids))
        return LossReport(policy_id=policy_id, entries=tuple(entries))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "is_lossless": self.is_lossless,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LossReport":
        raw_entries = value.get("entries") or []
        if not isinstance(raw_entries, (list, tuple)) or any(
            not isinstance(item, Mapping) for item in raw_entries
        ):
            raise ValueError("loss entries must be a list of objects")
        entries = tuple(
            LossEntry(
                code=str(item.get("code", "unknown_loss")),
                scope=str(item.get("scope", "record")),
                count=int(item.get("count", 1)),
                consequence=str(
                    item.get("consequence", "information_unavailable")
                ),
            )
            for item in raw_entries
        )
        return cls(
            policy_id=str(value.get("policy_id", "qitos.loss/unknown")),
            entries=entries,
        )


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class TrajectoryRecord:
    """One immutable event-shaped record in the candidate trajectory stream."""

    record_id: str
    kind: RecordKind
    role: RecordRole
    payload: Dict[str, Any] = field(default_factory=dict)
    sequence: Optional[int] = None
    occurred_at: str = field(default_factory=utc_now)
    recorded_at: str = field(default_factory=utc_now)
    session_id: Optional[str] = None
    run_id: Optional[str] = None
    work_item_id: Optional[str] = None
    step_id: Optional[int] = None
    phase: Optional[str] = None
    agent_id: Optional[str] = None
    snapshot_id: Optional[str] = None
    checkpoint_ref: Optional[str] = None
    exchange_id: Optional[str] = None
    tool_call_id: Optional[str] = None
    attempt_id: Optional[str] = None
    owner_generation: Optional[int] = None
    operation_id: Optional[str] = None
    source_session_id: Optional[str] = None
    source_work_item_id: Optional[str] = None
    producer_authority: Optional[str] = None
    record_provenance: Dict[str, Any] = field(default_factory=dict)
    causation_id: Optional[str] = None
    correlation_id: Optional[str] = None
    parent_run_id: Optional[str] = None
    parent_work_item_id: Optional[str] = None
    artifact_refs: Tuple[ArtifactRef, ...] = ()
    privacy_view: PrivacyView = PrivacyView.RAW_PRIVATE
    loss: LossReport = field(default_factory=LossReport)
    digest: str = ""

    def __post_init__(self) -> None:
        if not self.record_id.strip():
            raise ValueError("record_id must not be empty")
        if self.sequence is not None and self.sequence < 0:
            raise ValueError("sequence must be non-negative")
        if self.step_id is not None and self.step_id < 0:
            raise ValueError("step_id must be non-negative")
        if self.owner_generation is not None and self.owner_generation < 0:
            raise ValueError("owner_generation must be non-negative")

    @classmethod
    def create(
        cls,
        kind: RecordKind,
        *,
        role: RecordRole = RecordRole.CANONICAL_RUNTIME_FACT,
        payload: Optional[Mapping[str, Any]] = None,
        record_id: Optional[str] = None,
        **identities: Any,
    ) -> "TrajectoryRecord":
        record = cls(
            record_id=record_id or str(uuid.uuid4()),
            kind=kind,
            role=role,
            payload=copy.deepcopy(dict(payload or {})),
            **identities,
        )
        return replace(record, digest=record.compute_digest())

    def _digest_payload(self) -> Dict[str, Any]:
        value = self.to_dict()
        value.pop("digest", None)
        return value

    def compute_digest(self) -> str:
        return integrity_digest(self._digest_payload())

    def validate_integrity(self) -> bool:
        return bool(self.digest) and self.digest == self.compute_digest()

    def with_sequence(self, sequence: int) -> "TrajectoryRecord":
        updated = replace(self, sequence=sequence, recorded_at=utc_now(), digest="")
        return replace(updated, digest=updated.compute_digest())

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "schema_version": TRAJECTORY_SCHEMA_VERSION,
            "record_id": self.record_id,
            "sequence": self.sequence,
            "kind": self.kind.value,
            "role": self.role.value,
            "occurred_at": self.occurred_at,
            "recorded_at": self.recorded_at,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "work_item_id": self.work_item_id,
            "step_id": self.step_id,
            "phase": self.phase,
            "agent_id": self.agent_id,
            "snapshot_id": self.snapshot_id,
            "checkpoint_ref": self.checkpoint_ref,
            "exchange_id": self.exchange_id,
            "tool_call_id": self.tool_call_id,
            "attempt_id": self.attempt_id,
            "owner_generation": self.owner_generation,
            "operation_id": self.operation_id,
            "source_session_id": self.source_session_id,
            "source_work_item_id": self.source_work_item_id,
            "producer_authority": self.producer_authority,
            "record_provenance": copy.deepcopy(self.record_provenance),
            "causation_id": self.causation_id,
            "correlation_id": self.correlation_id,
            "parent_run_id": self.parent_run_id,
            "parent_work_item_id": self.parent_work_item_id,
            "artifact_refs": [ref.to_dict() for ref in self.artifact_refs],
            "privacy_view": self.privacy_view.value,
            "payload": copy.deepcopy(self.payload),
            "loss": self.loss.to_dict(),
            "digest": self.digest,
        }
        return data

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TrajectoryRecord":
        schema = value.get("schema_version")
        if schema != TRAJECTORY_SCHEMA_VERSION:
            raise ValueError(f"unsupported trajectory schema: {schema!r}")
        raw_artifact_refs = value.get("artifact_refs") or []
        if not isinstance(raw_artifact_refs, (list, tuple)) or any(
            not isinstance(item, Mapping) for item in raw_artifact_refs
        ):
            raise ValueError("artifact_refs must be a list of objects")
        raw_payload = value.get("payload") or {}
        if not isinstance(raw_payload, Mapping):
            raise ValueError("record payload must be an object")
        raw_loss = value.get("loss") or {}
        if not isinstance(raw_loss, Mapping):
            raise ValueError("record loss must be an object")
        raw_provenance = value.get("record_provenance") or {}
        if not isinstance(raw_provenance, Mapping):
            raise ValueError("record provenance must be an object")
        record = cls(
            record_id=str(value["record_id"]),
            sequence=(
                int(value["sequence"])
                if value.get("sequence") is not None
                else None
            ),
            kind=RecordKind(str(value["kind"])),
            role=RecordRole(str(value["role"])),
            occurred_at=str(value["occurred_at"]),
            recorded_at=str(value["recorded_at"]),
            session_id=_optional_text(value.get("session_id")),
            run_id=_optional_text(value.get("run_id")),
            work_item_id=_optional_text(value.get("work_item_id")),
            step_id=(
                int(value["step_id"])
                if value.get("step_id") is not None
                else None
            ),
            phase=_optional_text(value.get("phase")),
            agent_id=_optional_text(value.get("agent_id")),
            snapshot_id=_optional_text(value.get("snapshot_id")),
            checkpoint_ref=_optional_text(value.get("checkpoint_ref")),
            exchange_id=_optional_text(value.get("exchange_id")),
            tool_call_id=_optional_text(value.get("tool_call_id")),
            attempt_id=_optional_text(value.get("attempt_id")),
            owner_generation=(
                int(value["owner_generation"])
                if value.get("owner_generation") is not None
                else None
            ),
            operation_id=_optional_text(value.get("operation_id")),
            source_session_id=_optional_text(value.get("source_session_id")),
            source_work_item_id=_optional_text(
                value.get("source_work_item_id")
            ),
            producer_authority=_optional_text(value.get("producer_authority")),
            record_provenance=copy.deepcopy(dict(raw_provenance)),
            causation_id=_optional_text(value.get("causation_id")),
            correlation_id=_optional_text(value.get("correlation_id")),
            parent_run_id=_optional_text(value.get("parent_run_id")),
            parent_work_item_id=_optional_text(
                value.get("parent_work_item_id")
            ),
            artifact_refs=tuple(
                ArtifactRef.from_dict(item)
                for item in raw_artifact_refs
            ),
            privacy_view=PrivacyView(
                str(value.get("privacy_view", PrivacyView.RAW_PRIVATE.value))
            ),
            payload=copy.deepcopy(dict(raw_payload)),
            loss=LossReport.from_dict(raw_loss),
            digest=str(value.get("digest", "")),
        )
        if not record.validate_integrity():
            raise ValueError("trajectory record integrity mismatch")
        return record


@dataclass(frozen=True)
class TrajectoryQuery:
    """Store-independent declarative trajectory query."""

    session_id: Optional[str] = None
    run_id: Optional[str] = None
    work_item_id: Optional[str] = None
    kinds: Tuple[RecordKind, ...] = ()
    after_sequence: Optional[int] = None
    limit: Optional[int] = None


@dataclass(frozen=True)
class Trajectory:
    """Ordered records plus provenance and explicit loss."""

    records: Tuple[TrajectoryRecord, ...]
    schema_version: str = TRAJECTORY_SCHEMA_VERSION
    metadata: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
    privacy_view: PrivacyView = PrivacyView.RAW_PRIVATE
    loss: LossReport = field(default_factory=LossReport)

    def __post_init__(self) -> None:
        if self.schema_version != TRAJECTORY_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported trajectory schema: {self.schema_version!r}"
            )
        sequences = [
            record.sequence
            for record in self.records
            if record.sequence is not None
        ]
        if sequences != sorted(sequences):
            raise ValueError("trajectory records must be sequence ordered")
        if len(sequences) != len(set(sequences)):
            raise ValueError("trajectory record sequences must be unique")

    @property
    def run_ids(self) -> Tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                record.run_id for record in self.records if record.run_id
            )
        )

    @property
    def session_ids(self) -> Tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                record.session_id
                for record in self.records
                if record.session_id
            )
        )

    def validate_integrity(self) -> Tuple[str, ...]:
        return tuple(
            record.record_id
            for record in self.records
            if not record.validate_integrity()
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "privacy_view": self.privacy_view.value,
            "metadata": copy.deepcopy(self.metadata),
            "provenance": copy.deepcopy(self.provenance),
            "loss": self.loss.to_dict(),
            "records": [record.to_dict() for record in self.records],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Trajectory":
        raw_metadata = value.get("metadata") or {}
        raw_provenance = value.get("provenance") or {}
        raw_loss = value.get("loss") or {}
        raw_records = value.get("records") or []
        if not isinstance(raw_metadata, Mapping):
            raise ValueError("trajectory metadata must be an object")
        if not isinstance(raw_provenance, Mapping):
            raise ValueError("trajectory provenance must be an object")
        if not isinstance(raw_loss, Mapping):
            raise ValueError("trajectory loss must be an object")
        if not isinstance(raw_records, (list, tuple)) or any(
            not isinstance(item, Mapping) for item in raw_records
        ):
            raise ValueError("trajectory records must be a list of objects")
        return cls(
            schema_version=str(value.get("schema_version", "")),
            privacy_view=PrivacyView(
                str(value.get("privacy_view", PrivacyView.RAW_PRIVATE.value))
            ),
            metadata=copy.deepcopy(dict(raw_metadata)),
            provenance=copy.deepcopy(dict(raw_provenance)),
            loss=LossReport.from_dict(raw_loss),
            records=tuple(
                TrajectoryRecord.from_dict(item)
                for item in raw_records
            ),
        )


def filter_records(
    records: Iterable[TrajectoryRecord], query: TrajectoryQuery
) -> Tuple[TrajectoryRecord, ...]:
    """Apply a declarative query without depending on a concrete store."""
    selected = []
    for record in records:
        if query.session_id is not None and record.session_id != query.session_id:
            continue
        if query.run_id is not None and record.run_id != query.run_id:
            continue
        if (
            query.work_item_id is not None
            and record.work_item_id != query.work_item_id
        ):
            continue
        if query.kinds and record.kind not in query.kinds:
            continue
        if (
            query.after_sequence is not None
            and (record.sequence is None or record.sequence <= query.after_sequence)
        ):
            continue
        selected.append(record)
        if query.limit is not None and len(selected) >= query.limit:
            break
    return tuple(selected)


def records_to_tuple(
    records: Sequence[TrajectoryRecord],
) -> Tuple[TrajectoryRecord, ...]:
    """Return isolated records through their integrity-checked representation."""
    return tuple(TrajectoryRecord.from_dict(record.to_dict()) for record in records)


__all__ = [
    "TRAJECTORY_SCHEMA_VERSION",
    "EXPORT_SCHEMA_VERSION",
    "STORE_SCHEMA_VERSION",
    "LossEntry",
    "LossReport",
    "PrivacyView",
    "RecordKind",
    "RecordRole",
    "Trajectory",
    "TrajectoryQuery",
    "TrajectoryRecord",
    "canonical_json_bytes",
    "filter_records",
    "integrity_digest",
    "records_to_tuple",
]
