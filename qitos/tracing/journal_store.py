"""Crash-safe append journal for the unfrozen Trajectory candidate.

The journal is canonical. Its JSON index is derived, disposable, and rebuilt
from verified transaction frames on every reopen. A batch is one checksummed
line, so an interrupted final write is recoverable without accepting a partial
batch. Complete malformed or checksum-invalid frames are corruption.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import uuid
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Tuple

from qitos.core.artifact import ArtifactRef

try:  # POSIX is the reference implementation; other platforms stay in-process.
    import fcntl
except ImportError:  # pragma: no cover - exercised on non-POSIX builders
    fcntl = None  # type: ignore[assignment]

from .sinks import DurabilityReceipt, DurabilityStatus
from .store import (
    IndexRebuildReport,
    MemoryTrajectoryStore,
    StorageMeasurement,
    StoreCapabilities,
    StoreConflictError,
    StoreIOError,
    StoreIntegrityError,
    StoreIntegrityReport,
    TrajectoryStoreError,
)
from .trajectory import (
    STORE_SCHEMA_VERSION,
    LossReport,
    PrivacyView,
    Trajectory,
    TrajectoryQuery,
    TrajectoryRecord,
    canonical_json_bytes,
    integrity_digest,
)


JOURNAL_SCHEMA_VERSION = "qitos.trajectory-journal/candidate-1"
INDEX_SCHEMA_VERSION = "qitos.trajectory-index/candidate-1"
_MAX_FRAME_BYTES = 64 * 1024 * 1024


class JournalTrajectoryStore:
    """Durable local store with framed append, recovery, and a derived index."""

    def __init__(
        self,
        path: str | Path,
        *,
        recover_partial_tail: bool = True,
        max_query_records: int = 10_000,
        read_only: bool = False,
    ) -> None:
        if max_query_records <= 0:
            raise ValueError("max_query_records must be positive")
        self._path = Path(path)
        self._index_path = self._path.with_name(self._path.name + ".index.json")
        self._lock_path = self._path.with_name(self._path.name + ".lock")
        self._read_only = read_only
        if not read_only:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._thread_lock = threading.RLock()
        self._memory = MemoryTrajectoryStore(
            store_id="qitos.journal_trajectory_store.memory"
        )
        self._closed = False
        self._recover_partial_tail = recover_partial_tail and not read_only
        self._max_query_records = max_query_records
        self._last_frame_digest: Optional[str] = None
        self._verified_hasher: Any = None
        self._recovered_tail_bytes = 0
        try:
            if not read_only:
                self._path.touch(exist_ok=True)
                self._lock_path.touch(exist_ok=True)
        except OSError as exc:
            raise StoreIOError("store_open_failed") from exc
        with self._exclusive_lock():
            self._load(recover=self._recover_partial_tail)
            if not read_only:
                self._write_index(best_effort=True)

    @property
    def capabilities(self) -> StoreCapabilities:
        return StoreCapabilities(
            store_id="qitos.journal_trajectory_store",
            atomic_batch=True,
            durable=True,
            concurrent_writer_policy=(
                "serialized_advisory_file_lock"
                if fcntl is not None
                else "single_process_serialized"
            ),
            max_query_records=self._max_query_records,
            partial_tail_recovery=not self._read_only,
            index_rebuild=not self._read_only,
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise TrajectoryStoreError("trajectory store is closed")

    def _ensure_writable(self) -> None:
        self._ensure_open()
        if self._read_only:
            raise TrajectoryStoreError("read_only_store")

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        with self._thread_lock:
            try:
                handle = self._lock_path.open("rb" if self._read_only else "a+b")
            except OSError as exc:
                raise StoreIOError("store_lock_failed") from exc
            try:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_SH if self._read_only else fcntl.LOCK_EX)
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()

    @staticmethod
    def _frame_document(
        records: Iterable[TrajectoryRecord],
        *,
        start_sequence: int,
        previous_digest: Optional[str],
        transaction_id: str,
    ) -> Dict[str, Any]:
        document: Dict[str, Any] = {
            "journal_schema": JOURNAL_SCHEMA_VERSION,
            "store_schema": STORE_SCHEMA_VERSION,
            "transaction_id": transaction_id,
            "start_sequence": start_sequence,
            "previous_digest": previous_digest,
            "records": [record.to_dict() for record in records],
        }
        document["frame_digest"] = integrity_digest(document)
        return document

    @staticmethod
    def _decode_frame(
        value: Any,
        *,
        expected_sequence: int,
        previous_digest: Optional[str],
    ) -> Tuple[Tuple[TrajectoryRecord, ...], str]:
        if not isinstance(value, Mapping):
            raise StoreIntegrityError("invalid_journal_frame")
        if value.get("journal_schema") != JOURNAL_SCHEMA_VERSION:
            raise StoreIntegrityError("unsupported_journal_schema")
        if value.get("store_schema") != STORE_SCHEMA_VERSION:
            raise StoreIntegrityError("unsupported_store_schema")
        if value.get("previous_digest") != previous_digest:
            raise StoreIntegrityError("journal_chain_mismatch")
        if value.get("start_sequence") != expected_sequence:
            raise StoreIntegrityError("journal_sequence_mismatch")
        supplied_digest = str(value.get("frame_digest", ""))
        digest_input = dict(value)
        digest_input.pop("frame_digest", None)
        if supplied_digest != integrity_digest(digest_input):
            raise StoreIntegrityError("journal_frame_digest_mismatch")
        raw_records = value.get("records")
        if not isinstance(raw_records, list) or any(
            not isinstance(item, Mapping) for item in raw_records
        ):
            raise StoreIntegrityError("invalid_journal_records")
        try:
            records = tuple(TrajectoryRecord.from_dict(item) for item in raw_records)
        except (KeyError, TypeError, ValueError) as exc:
            raise StoreIntegrityError("invalid_journal_record") from exc
        expected = tuple(range(expected_sequence, expected_sequence + len(records)))
        if tuple(record.sequence for record in records) != expected:
            raise StoreIntegrityError("journal_record_sequence_mismatch")
        return records, supplied_digest

    def _load(self, *, recover: bool) -> None:
        # Check every byte, including in-place edits with unchanged timestamps.
        # Only parsing/materialization is cached; file metadata is not authority.
        if self._verified_hasher is not None:
            try:
                current = hashlib.sha256()
                with self._path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(256 * 1024), b""):
                        current.update(chunk)
            except OSError:
                raise StoreIOError("store_read_failed") from None
            if current.digest() == self._verified_hasher.digest():
                return
        self._verified_hasher = None
        verified = hashlib.sha256()
        records: List[TrajectoryRecord] = []
        previous_digest: Optional[str] = None
        valid_end = 0
        try:
            with self._path.open("rb") as handle:
                while line := handle.readline(_MAX_FRAME_BYTES + 1):
                    if len(line) > _MAX_FRAME_BYTES:
                        raise StoreIntegrityError("journal_frame_limit_exceeded")
                    # The delimiter is part of the commit frame, even when the
                    # unterminated JSON happens to be syntactically complete.
                    if not line.endswith(b"\n"):
                        if not recover:
                            raise StoreIntegrityError("incomplete_journal_frame")
                        self._recovered_tail_bytes += len(line)
                        self._truncate(valid_end)
                        break
                    try:
                        value = json.loads(line)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        raise StoreIntegrityError("invalid_journal_frame") from None
                    frame_records, previous_digest = self._decode_frame(
                        value, expected_sequence=len(records),
                        previous_digest=previous_digest,
                    )
                    records.extend(frame_records)
                    valid_end += len(line)
                    verified.update(line)
        except OSError:
            raise StoreIOError("store_read_failed") from None
        self._memory._restore(records)
        report = self._memory.validate_integrity()
        if not report.valid:
            raise StoreIntegrityError("journal_record_integrity_mismatch")
        self._last_frame_digest = previous_digest
        self._verified_hasher = verified

    def _truncate(self, size: int) -> None:
        try:
            with self._path.open("r+b") as handle:
                handle.truncate(size)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise StoreIOError("partial_tail_recovery_failed") from exc

    def _append_frame(self, document: Mapping[str, Any]) -> bytes:
        data = canonical_json_bytes(document) + b"\n"
        if len(data) > _MAX_FRAME_BYTES:
            raise TrajectoryStoreError("journal_frame_limit_exceeded")
        written = 0
        attempted = False
        try:
            with self._path.open("ab", buffering=0) as handle:
                while written < len(data):
                    attempted = True
                    count = handle.write(memoryview(data)[written:])
                    if count is None or count <= 0 or count > len(data) - written:
                        raise OSError("journal write made no valid progress")
                    written += count
                os.fsync(handle.fileno())
        except OSError:
            raise StoreIOError(
                "store_append_uncertain" if attempted else "store_append_failed",
                bytes_written=written,
                durability_unknown=attempted,
            ) from None
        return data

    def _index_document(self) -> Dict[str, Any]:
        records = self._memory._snapshot_records()

        def positions(name: str) -> Dict[str, List[int]]:
            result: Dict[str, List[int]] = {}
            for record in records:
                value = getattr(record, name)
                if value:
                    result.setdefault(str(value), []).append(int(record.sequence or 0))
            return result

        document: Dict[str, Any] = {
            "index_schema": INDEX_SCHEMA_VERSION,
            "journal_schema": JOURNAL_SCHEMA_VERSION,
            "record_count": len(records),
            "journal_head_digest": self._last_frame_digest,
            "runs": positions("run_id"),
            "sessions": positions("session_id"),
            "work_items": positions("work_item_id"),
        }
        document["index_digest"] = integrity_digest(document)
        return document

    def _write_index(self, *, best_effort: bool) -> bool:
        data = canonical_json_bytes(self._index_document())
        descriptor = -1
        temp_name = ""
        try:
            descriptor, temp_name = tempfile.mkstemp(
                prefix=f".{self._index_path.name}.",
                suffix=".tmp",
                dir=str(self._index_path.parent),
            )
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = -1
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self._index_path)
            temp_name = ""
            return True
        except OSError as exc:
            if best_effort:
                return False
            raise StoreIOError("index_write_failed") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temp_name:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass

    def append(self, record: TrajectoryRecord) -> DurabilityReceipt:
        return self.append_batch((record,))

    def append_batch(
        self, records: Iterable[TrajectoryRecord]
    ) -> DurabilityReceipt:
        self._ensure_writable()
        batch = tuple(records)
        with self._exclusive_lock():
            self._ensure_open()
            self._load(recover=self._recover_partial_tail)
            if not batch:
                return DurabilityReceipt(
                    status=DurabilityStatus.PERSISTED,
                    operation_id=str(uuid.uuid4()),
                )
            before = self._memory._snapshot_records()
            existing = {record.record_id: record for record in before}
            repeated = [record for record in batch if record.record_id in existing]
            if repeated:
                if len(repeated) != len(batch) or len({r.record_id for r in batch}) != len(batch):
                    raise StoreConflictError("partial_duplicate_batch")
                for record in repeated:
                    stored = existing[record.record_id]
                    if not record.validate_integrity():
                        raise StoreIntegrityError("record_integrity_mismatch")
                    supplied, persisted = record.to_dict(), stored.to_dict()
                    for assigned_field in ("sequence", "recorded_at", "digest"):
                        supplied.pop(assigned_field, None)
                        persisted.pop(assigned_field, None)
                    if supplied != persisted:
                        raise StoreConflictError("record_id_already_exists")
                # A previous append may have written a full frame before fsync
                # failed. Confirm durability now without duplicating its effects.
                self._flush_unlocked()
                return DurabilityReceipt(
                    status=DurabilityStatus.PERSISTED,
                    accepted_count=len(batch), persisted_count=len(batch),
                    detail_code="already_persisted",
                )
            verified = self._verified_hasher.copy()
            self._verified_hasher = None
            receipt = self._memory.append_batch(batch)
            after = self._memory._snapshot_records()
            assigned = after[len(before) :]
            transaction_id = receipt.operation_id or str(uuid.uuid4())
            document = self._frame_document(
                assigned,
                start_sequence=len(before),
                previous_digest=self._last_frame_digest,
                transaction_id=transaction_id,
            )
            try:
                frame = self._append_frame(document)
            except Exception:
                self._memory._restore(before)
                raise
            self._last_frame_digest = str(document["frame_digest"])
            verified.update(frame)
            self._verified_hasher = verified
            index_persisted = self._write_index(best_effort=True)
            return DurabilityReceipt(
                status=DurabilityStatus.PERSISTED,
                accepted_count=len(assigned),
                persisted_count=len(assigned),
                operation_id=transaction_id,
                detail_code=None if index_persisted else "index_rebuild_required",
            )

    def _query_unlocked(
        self, query: TrajectoryQuery
    ) -> Tuple[TrajectoryRecord, ...]:
        if query.limit is not None and query.limit > self._max_query_records:
            raise TrajectoryStoreError("query_limit_exceeded")
        if query.limit is not None and query.limit <= 0:
            raise TrajectoryStoreError("query_limit_invalid")
        effective = query
        if effective.limit is None:
            effective = replace(effective, limit=self._max_query_records + 1)
        records = self._memory.query(effective)
        if query.limit is None and len(records) > self._max_query_records:
            raise TrajectoryStoreError("query_requires_pagination")
        return records

    def query(self, query: TrajectoryQuery) -> Tuple[TrajectoryRecord, ...]:
        with self._exclusive_lock():
            self._ensure_open()
            self._load(recover=self._recover_partial_tail)
            return self._query_unlocked(query)

    def _trajectory(self, query: TrajectoryQuery) -> Trajectory:
        # A whole-trajectory API returns a complete materialized snapshot. Page
        # limits still apply to individual queries; the read holds one lock so
        # a concurrent append cannot shift page boundaries.
        with self._exclusive_lock():
            self._ensure_open()
            self._load(recover=self._recover_partial_tail)
            records: List[TrajectoryRecord] = []
            page_query = replace(query, limit=self._max_query_records)
            while True:
                page = self._query_unlocked(page_query)
                records.extend(page)
                if len(page) < self._max_query_records:
                    break
                page_query = replace(page_query, after_sequence=page[-1].sequence)
        return Trajectory(
            records=tuple(records),
            metadata={"store_id": self.capabilities.store_id, "complete": True},
            provenance={"source": "trajectory_journal"},
            privacy_view=PrivacyView.RAW_PRIVATE,
            loss=LossReport(policy_id="qitos.loss/none"),
        )

    def read_run(self, run_id: str) -> Trajectory:
        return self._trajectory(TrajectoryQuery(run_id=run_id))

    def read_session(self, session_id: str) -> Trajectory:
        return self._trajectory(TrajectoryQuery(session_id=session_id))

    def replay(self, query: TrajectoryQuery) -> Tuple[TrajectoryRecord, ...]:
        return self.query(query) if query.limit is not None else self._trajectory(query).records

    def artifact_refs(self, query: TrajectoryQuery) -> Tuple[ArtifactRef, ...]:
        refs: Dict[str, ArtifactRef] = {}
        for record in self.query(query):
            for ref in record.artifact_refs:
                refs[ref.sha256] = ref
        return tuple(refs.values())

    def validate_integrity(self) -> StoreIntegrityReport:
        with self._exclusive_lock():
            self._ensure_open()
            try:
                self._load(recover=False)
            except (StoreIntegrityError, StoreIOError):
                return StoreIntegrityReport(
                    valid=False,
                    record_count=len(self._memory._snapshot_records()),
                    store_digest_valid=False,
                    recovered_tail_bytes=self._recovered_tail_bytes,
                )
            report = self._memory.validate_integrity()
            return replace(
                report,
                store_digest_valid=True,
                recovered_tail_bytes=self._recovered_tail_bytes,
            )

    def rebuild_index(self) -> IndexRebuildReport:
        self._ensure_writable()
        with self._exclusive_lock():
            self._ensure_open()
            self._load(recover=self._recover_partial_tail)
            base = self._memory.rebuild_index()
            self._write_index(best_effort=False)
            return replace(base, persisted=True)

    def measure_storage(self) -> StorageMeasurement:
        with self._exclusive_lock():
            self._ensure_open()
            self._load(recover=self._recover_partial_tail)
            return StorageMeasurement(
                storage_schema=STORE_SCHEMA_VERSION,
                record_count=len(self._memory._snapshot_records()),
                size_bytes=self._path.stat().st_size,
                measurement_kind="observed_journal_bytes",
            )

    def _flush_unlocked(self) -> DurabilityReceipt:
        try:
            with self._path.open("rb") as handle:
                os.fsync(handle.fileno())
        except OSError as exc:
            raise StoreIOError("store_flush_failed") from exc
        count = len(self._memory._snapshot_records())
        return DurabilityReceipt(
            status=DurabilityStatus.PERSISTED,
            accepted_count=count,
            persisted_count=count,
        )

    def flush(self) -> DurabilityReceipt:
        self._ensure_writable()
        with self._exclusive_lock():
            self._ensure_open()
            return self._flush_unlocked()

    def close(self) -> DurabilityReceipt:
        with self._exclusive_lock():
            if self._closed:
                return DurabilityReceipt(status=DurabilityStatus.PERSISTED)
            receipt = (DurabilityReceipt(status=DurabilityStatus.ACCEPTED)
                       if self._read_only else self._flush_unlocked())
            self._memory.close()
            self._closed = True
            return receipt


__all__ = [
    "INDEX_SCHEMA_VERSION",
    "JOURNAL_SCHEMA_VERSION",
    "JournalTrajectoryStore",
]
