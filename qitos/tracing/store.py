"""Replaceable candidate trajectory stores and a lightweight reference store."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol, Tuple, runtime_checkable

from qitos.core.artifact import ArtifactRef

from .sinks import DurabilityReceipt, DurabilityStatus
from .trajectory import (
    STORE_SCHEMA_VERSION,
    LossReport,
    PrivacyView,
    Trajectory,
    TrajectoryQuery,
    TrajectoryRecord,
    canonical_json_bytes,
    filter_records,
    integrity_digest,
    records_to_tuple,
)


class TrajectoryStoreError(RuntimeError):
    """Base class for typed store failures."""


class StoreConflictError(TrajectoryStoreError):
    """A record identity or sequence conflicts with stored data."""


class StoreIntegrityError(TrajectoryStoreError):
    """Stored data failed integrity validation."""


class StoreIOError(TrajectoryStoreError):
    """A durable store operation failed without echoing host details."""

    def __init__(self, code: str, *, bytes_written: int = 0,
                 durability_unknown: bool = False) -> None:
        super().__init__(code)
        self.bytes_written = bytes_written
        self.durability_unknown = durability_unknown


@dataclass(frozen=True)
class StoreCapabilities:
    store_id: str
    atomic_batch: bool
    durable: bool
    query: bool = True
    replay: bool = True
    integrity_validation: bool = True
    artifact_references: bool = True
    concurrent_writer_policy: str = "single_process_serialized"
    max_query_records: int = 10_000
    partial_tail_recovery: bool = False
    index_rebuild: bool = False


@dataclass(frozen=True)
class StoreIntegrityReport:
    valid: bool
    record_count: int
    invalid_record_ids: Tuple[str, ...] = ()
    duplicate_record_ids: Tuple[str, ...] = ()
    sequence_gaps: Tuple[int, ...] = ()
    store_digest_valid: Optional[bool] = None
    recovered_tail_bytes: int = 0


@dataclass(frozen=True)
class IndexRebuildReport:
    """Result for rebuilding a derived, disposable query index."""

    record_count: int
    run_count: int
    session_count: int
    work_item_count: int
    persisted: bool = False


@dataclass(frozen=True)
class StorageMeasurement:
    """Observed bytes only; this type makes no performance claim."""

    storage_schema: str
    record_count: int
    size_bytes: int
    measurement_kind: str


@runtime_checkable
class TrajectoryStore(Protocol):
    """Store protocol implemented without Engine or qita dependencies."""

    @property
    def capabilities(self) -> StoreCapabilities:
        ...

    def append(self, record: TrajectoryRecord) -> DurabilityReceipt:
        ...

    def append_batch(
        self, records: Iterable[TrajectoryRecord]
    ) -> DurabilityReceipt:
        ...

    def query(self, query: TrajectoryQuery) -> Tuple[TrajectoryRecord, ...]:
        ...

    def read_run(self, run_id: str) -> Trajectory:
        ...

    def read_session(self, session_id: str) -> Trajectory:
        ...

    def replay(self, query: TrajectoryQuery) -> Tuple[TrajectoryRecord, ...]:
        ...

    def artifact_refs(self, query: TrajectoryQuery) -> Tuple[ArtifactRef, ...]:
        ...

    def validate_integrity(self) -> StoreIntegrityReport:
        ...

    def rebuild_index(self) -> IndexRebuildReport:
        ...

    def measure_storage(self) -> StorageMeasurement:
        ...

    def flush(self) -> DurabilityReceipt:
        ...

    def close(self) -> DurabilityReceipt:
        ...


class MemoryTrajectoryStore:
    """Thread-safe reference store with atomic batches and deep isolation."""

    def __init__(self, *, store_id: str = "qitos.memory_trajectory_store") -> None:
        self._capabilities = StoreCapabilities(
            store_id=store_id,
            atomic_batch=True,
            durable=False,
        )
        self._records: List[TrajectoryRecord] = []
        self._record_ids: set[str] = set()
        self._closed = False
        self._lock = threading.RLock()

    @classmethod
    def from_records(
        cls,
        records: Iterable[TrajectoryRecord],
        *,
        store_id: str = "qitos.memory_trajectory_snapshot",
    ) -> "MemoryTrajectoryStore":
        """Build an exact in-memory snapshot without resequencing records."""
        store = cls(store_id=store_id)
        store._restore(records)
        report = store.validate_integrity()
        if not report.valid:
            raise StoreIntegrityError("snapshot_integrity_mismatch")
        return store

    @property
    def capabilities(self) -> StoreCapabilities:
        return self._capabilities

    def _restore(self, records: Iterable[TrajectoryRecord]) -> None:
        restored = records_to_tuple(tuple(records))
        with self._lock:
            self._records = list(restored)
            self._record_ids = {record.record_id for record in restored}

    def _ensure_open(self) -> None:
        if self._closed:
            raise TrajectoryStoreError("trajectory store is closed")

    def append(self, record: TrajectoryRecord) -> DurabilityReceipt:
        return self.append_batch((record,))

    def append_batch(
        self, records: Iterable[TrajectoryRecord]
    ) -> DurabilityReceipt:
        batch = tuple(records)
        with self._lock:
            self._ensure_open()
            if not batch:
                return DurabilityReceipt(
                    status=DurabilityStatus.ACCEPTED,
                    operation_id=str(uuid.uuid4()),
                )
            invalid = [
                record.record_id
                for record in batch
                if not record.validate_integrity()
            ]
            if invalid:
                raise StoreIntegrityError("record_integrity_mismatch")
            batch_ids = [record.record_id for record in batch]
            if len(set(batch_ids)) != len(batch_ids):
                raise StoreConflictError("duplicate_record_id_in_batch")
            if self._record_ids.intersection(batch_ids):
                raise StoreConflictError("record_id_already_exists")

            start = len(self._records)
            assigned = tuple(
                record.with_sequence(start + index)
                for index, record in enumerate(batch)
            )
            self._records.extend(assigned)
            self._record_ids.update(batch_ids)
            return DurabilityReceipt(
                status=DurabilityStatus.ACCEPTED,
                accepted_count=len(assigned),
                operation_id=str(uuid.uuid4()),
            )

    def query(self, query: TrajectoryQuery) -> Tuple[TrajectoryRecord, ...]:
        with self._lock:
            self._ensure_open()
            selected = filter_records(self._records, query)
            return records_to_tuple(selected)

    def _trajectory(self, query: TrajectoryQuery) -> Trajectory:
        records = self.query(query)
        return Trajectory(
            records=records,
            metadata={"store_id": self.capabilities.store_id},
            provenance={"source": "trajectory_store"},
            privacy_view=PrivacyView.RAW_PRIVATE,
            loss=LossReport(policy_id="qitos.loss/none"),
        )

    def read_run(self, run_id: str) -> Trajectory:
        return self._trajectory(TrajectoryQuery(run_id=run_id))

    def read_session(self, session_id: str) -> Trajectory:
        return self._trajectory(TrajectoryQuery(session_id=session_id))

    def replay(self, query: TrajectoryQuery) -> Tuple[TrajectoryRecord, ...]:
        return self.query(query)

    def artifact_refs(self, query: TrajectoryQuery) -> Tuple[ArtifactRef, ...]:
        refs: Dict[str, ArtifactRef] = {}
        for record in self.query(query):
            for ref in record.artifact_refs:
                refs[ref.sha256] = ref
        return tuple(refs.values())

    def validate_integrity(self) -> StoreIntegrityReport:
        with self._lock:
            invalid = tuple(
                record.record_id
                for record in self._records
                if not record.validate_integrity()
            )
            seen: set[str] = set()
            duplicates: List[str] = []
            for record in self._records:
                if record.record_id in seen:
                    duplicates.append(record.record_id)
                seen.add(record.record_id)
            sequences = [record.sequence for record in self._records]
            expected = list(range(len(self._records)))
            gaps = tuple(
                expected[index]
                for index, value in enumerate(sequences)
                if value != expected[index]
            )
            return StoreIntegrityReport(
                valid=not invalid and not duplicates and not gaps,
                record_count=len(self._records),
                invalid_record_ids=invalid,
                duplicate_record_ids=tuple(duplicates),
                sequence_gaps=gaps,
            )

    def rebuild_index(self) -> IndexRebuildReport:
        with self._lock:
            self._ensure_open()
            return IndexRebuildReport(
                record_count=len(self._records),
                run_count=len({record.run_id for record in self._records if record.run_id}),
                session_count=len(
                    {record.session_id for record in self._records if record.session_id}
                ),
                work_item_count=len(
                    {
                        record.work_item_id
                        for record in self._records
                        if record.work_item_id
                    }
                ),
            )

    def measure_storage(self) -> StorageMeasurement:
        with self._lock:
            payload = {
                "storage_schema": STORE_SCHEMA_VERSION,
                "records": [record.to_dict() for record in self._records],
            }
            return StorageMeasurement(
                storage_schema=STORE_SCHEMA_VERSION,
                record_count=len(self._records),
                size_bytes=len(canonical_json_bytes(payload)),
                measurement_kind="canonical_json_bytes_in_memory",
            )

    def flush(self) -> DurabilityReceipt:
        with self._lock:
            self._ensure_open()
            return DurabilityReceipt(
                status=DurabilityStatus.ACCEPTED,
                accepted_count=len(self._records),
            )

    def close(self) -> DurabilityReceipt:
        with self._lock:
            if self._closed:
                return DurabilityReceipt(status=DurabilityStatus.ACCEPTED)
            count = len(self._records)
            self._closed = True
            return DurabilityReceipt(
                status=DurabilityStatus.ACCEPTED,
                accepted_count=count,
            )

    def snapshot(self) -> Tuple[TrajectoryRecord, ...]:
        with self._lock:
            return records_to_tuple(self._records)

    def _snapshot_records(self) -> Tuple[TrajectoryRecord, ...]:
        """Internal read-only view for owned store adapters; never expose to callers."""
        with self._lock:
            return tuple(self._records)


class JsonTrajectoryStore:
    """Atomic single-file JSON reference store with a versioned disk schema."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._memory = MemoryTrajectoryStore(
            store_id="qitos.json_trajectory_store.memory"
        )
        self._closed = False
        self._stored_digest: Optional[str] = None
        if self._path.exists():
            self._load()
        else:
            self._persist(())

    @property
    def capabilities(self) -> StoreCapabilities:
        return StoreCapabilities(
            store_id="qitos.json_trajectory_store",
            atomic_batch=True,
            durable=True,
            partial_tail_recovery=False,
            index_rebuild=True,
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise TrajectoryStoreError("trajectory store is closed")

    @staticmethod
    def _document(records: Iterable[TrajectoryRecord]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "storage_schema": STORE_SCHEMA_VERSION,
            "records": [record.to_dict() for record in records],
        }
        payload["store_digest"] = integrity_digest(payload)
        return payload

    def _load(self) -> None:
        try:
            document = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StoreIntegrityError("invalid_store_document") from exc
        if not isinstance(document, Mapping):
            raise StoreIntegrityError("invalid_store_document")
        if document.get("storage_schema") != STORE_SCHEMA_VERSION:
            raise StoreIntegrityError("unsupported_store_schema")
        supplied_digest = str(document.get("store_digest", ""))
        digest_input = dict(document)
        digest_input.pop("store_digest", None)
        if supplied_digest != integrity_digest(digest_input):
            raise StoreIntegrityError("store_digest_mismatch")
        raw_records = document.get("records")
        if not isinstance(raw_records, list) or any(
            not isinstance(item, Mapping) for item in raw_records
        ):
            raise StoreIntegrityError("invalid_store_records")
        try:
            records = tuple(
                TrajectoryRecord.from_dict(item)
                for item in raw_records
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise StoreIntegrityError("invalid_store_record") from exc
        self._memory._restore(records)
        report = self._memory.validate_integrity()
        if not report.valid:
            raise StoreIntegrityError("store_record_integrity_mismatch")
        self._stored_digest = supplied_digest

    def _persist(self, records: Iterable[TrajectoryRecord]) -> None:
        document = self._document(records)
        data = canonical_json_bytes(document)
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{self._path.name}.",
            suffix=".tmp",
            dir=str(self._path.parent),
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self._path)
            directory_fd = os.open(self._path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise
        self._stored_digest = str(document["store_digest"])

    def append(self, record: TrajectoryRecord) -> DurabilityReceipt:
        return self.append_batch((record,))

    def append_batch(
        self, records: Iterable[TrajectoryRecord]
    ) -> DurabilityReceipt:
        batch = tuple(records)
        with self._lock:
            self._ensure_open()
            before = self._memory.snapshot()
            accepted = self._memory.append_batch(batch)
            try:
                after = self._memory.snapshot()
                self._persist(after)
            except Exception:
                self._memory._restore(before)
                raise
            return DurabilityReceipt(
                status=DurabilityStatus.PERSISTED,
                accepted_count=accepted.accepted_count,
                persisted_count=accepted.accepted_count,
                operation_id=accepted.operation_id,
            )

    def query(self, query: TrajectoryQuery) -> Tuple[TrajectoryRecord, ...]:
        with self._lock:
            self._ensure_open()
            return self._memory.query(query)

    def read_run(self, run_id: str) -> Trajectory:
        with self._lock:
            self._ensure_open()
            trajectory = self._memory.read_run(run_id)
            return Trajectory(
                records=trajectory.records,
                metadata={"store_id": self.capabilities.store_id},
                provenance={"source": "trajectory_store"},
                privacy_view=trajectory.privacy_view,
                loss=trajectory.loss,
            )

    def read_session(self, session_id: str) -> Trajectory:
        with self._lock:
            self._ensure_open()
            trajectory = self._memory.read_session(session_id)
            return Trajectory(
                records=trajectory.records,
                metadata={"store_id": self.capabilities.store_id},
                provenance={"source": "trajectory_store"},
                privacy_view=trajectory.privacy_view,
                loss=trajectory.loss,
            )

    def replay(self, query: TrajectoryQuery) -> Tuple[TrajectoryRecord, ...]:
        return self.query(query)

    def artifact_refs(self, query: TrajectoryQuery) -> Tuple[ArtifactRef, ...]:
        return self._memory.artifact_refs(query)

    def validate_integrity(self) -> StoreIntegrityReport:
        with self._lock:
            report = self._memory.validate_integrity()
            digest_valid: Optional[bool] = None
            if self._path.exists():
                try:
                    document = json.loads(self._path.read_text(encoding="utf-8"))
                    supplied = str(document.pop("store_digest", ""))
                    digest_valid = supplied == integrity_digest(document)
                except (
                    OSError,
                    json.JSONDecodeError,
                    AttributeError,
                    TypeError,
                ):
                    digest_valid = False
            return StoreIntegrityReport(
                valid=report.valid and digest_valid is True,
                record_count=report.record_count,
                invalid_record_ids=report.invalid_record_ids,
                duplicate_record_ids=report.duplicate_record_ids,
                sequence_gaps=report.sequence_gaps,
                store_digest_valid=digest_valid,
            )

    def rebuild_index(self) -> IndexRebuildReport:
        return self._memory.rebuild_index()

    def measure_storage(self) -> StorageMeasurement:
        with self._lock:
            return StorageMeasurement(
                storage_schema=STORE_SCHEMA_VERSION,
                record_count=len(self._memory.snapshot()),
                size_bytes=self._path.stat().st_size,
                measurement_kind="observed_file_bytes",
            )

    def flush(self) -> DurabilityReceipt:
        with self._lock:
            self._ensure_open()
            records = self._memory.snapshot()
            self._persist(records)
            return DurabilityReceipt(
                status=DurabilityStatus.PERSISTED,
                accepted_count=len(records),
                persisted_count=len(records),
            )

    def close(self) -> DurabilityReceipt:
        with self._lock:
            if self._closed:
                return DurabilityReceipt(status=DurabilityStatus.PERSISTED)
            receipt = self.flush()
            self._memory.close()
            self._closed = True
            return receipt


__all__ = [
    "JsonTrajectoryStore",
    "IndexRebuildReport",
    "MemoryTrajectoryStore",
    "StorageMeasurement",
    "StoreCapabilities",
    "StoreConflictError",
    "StoreIntegrityError",
    "StoreIntegrityReport",
    "StoreIOError",
    "TrajectoryStore",
    "TrajectoryStoreError",
]
