"""Strict snapshot paging with an owned, disposable disk index.

Every operation verifies all snapshot bytes. Only decoding is avoided on warm
pages. SQLite contains derived addressing/identity data, never canonical payload.
Its cache and the frame decoder are bounded independently of journal length.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import tempfile
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator

from .journal_store import JournalTrajectoryStore, _MAX_FRAME_BYTES, fcntl
from .sinks import project_record
from .store import StoreIntegrityError, StoreIOError, TrajectoryStoreError
from .trajectory import PrivacyView, TrajectoryQuery, TrajectoryRecord, canonical_json_bytes
from .work import TrajectoryWork


class BoundedReadUnsupported(TrajectoryStoreError):
    """The selected source has no bounded snapshot capability."""


class CursorRejected(StoreIntegrityError):
    """A cursor or its source no longer describes the captured snapshot."""


@dataclass(frozen=True)
class TrajectoryCursor:
    """Reader-local opaque token. No host path or credential is serialized."""

    token: str


@dataclass(frozen=True)
class TrajectoryPage:
    records: tuple[TrajectoryRecord, ...]
    next_cursor: TrajectoryCursor | None
    snapshot: TrajectoryCursor
    watermark: int


def read_page(reader: Any, query: TrajectoryQuery, cursor: TrajectoryCursor | None = None,
              *, view: PrivacyView = PrivacyView.REDACTED_PUBLIC) -> TrajectoryPage:
    """Require bounded capability; never materialize a third-party fallback."""
    if not getattr(reader.capabilities, "bounded_read", False):
        raise BoundedReadUnsupported("bounded_read_unsupported")
    return reader.read_page(query, cursor, view=view)


def iter_records(reader: Any, query: TrajectoryQuery, *,
                 view: PrivacyView = PrivacyView.REDACTED_PUBLIC) -> Iterator[TrajectoryRecord]:
    """Iterate one snapshot, releasing source locks before each user yield."""
    cursor = None
    while True:
        page = read_page(reader, query, cursor, view=view)
        yield from page.records
        cursor = page.next_cursor
        if cursor is None:
            return
        del page


class JournalPages:
    """Internal bounded file path behind StoreTrajectoryReader.from_journal.

    Close removes only the temporary index owned by this reader. The journal and
    its sidecars are read-only, including incomplete tails. Cursors expire at close.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.work = TrajectoryWork()
        self._key = secrets.token_bytes(32)
        self._lock = threading.RLock()
        self._temporary = tempfile.TemporaryDirectory(prefix="qitos-pages-")
        self._db = sqlite3.connect(str(Path(self._temporary.name) / "index.db"),
                                   check_same_thread=False)
        self._db.execute("PRAGMA cache_size=-1024")
        self._db.execute("PRAGMA temp_store=FILE")
        self._db.execute("PRAGMA journal_mode=OFF")
        self._db.execute("PRAGMA synchronous=OFF")
        self._db.execute("CREATE TABLE records (seq INTEGER PRIMARY KEY, id TEXT UNIQUE, "
                         "run TEXT, session TEXT, work TEXT, kind TEXT, offset INTEGER, "
                         "start INTEGER, previous TEXT, digest TEXT)")
        for column in ("run", "session", "work", "kind"):
            self._db.execute(f"CREATE INDEX by_{column} ON records ({column}, seq)")
        self._head: dict[str, Any] | None = None
        self._closed = False
        try:
            with self._source() as handle:
                self._capture(handle)
        except BaseException:
            self.close()
            raise

    @contextmanager
    def _source(self) -> Iterator[Any]:
        with self._lock:
            if self._closed:
                raise CursorRejected("reader_closed")
            try:
                with self.path.with_name(self.path.name + ".lock").open("rb") as lock:
                    if fcntl is not None:
                        fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
                    try:
                        with self.path.open("rb") as handle:
                            self._identity(handle)
                            yield handle
                            self._identity(handle)
                    finally:
                        if fcntl is not None:
                            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            except OSError:
                raise StoreIOError("bounded_source_read_failed") from None

    def _identity(self, handle: Any) -> str:
        actual, named = os.fstat(handle.fileno()), self.path.stat()
        if (actual.st_dev, actual.st_ino) != (named.st_dev, named.st_ino):
            raise CursorRejected("source_replaced")
        return hmac.new(self._key, f"{actual.st_dev}:{actual.st_ino}".encode(),
                        hashlib.sha256).hexdigest()

    def _hash(self, handle: Any, boundary: int) -> str:
        handle.seek(0)
        digest = hashlib.sha256()
        remaining = boundary
        while remaining:
            chunk = handle.read(min(256 * 1024, remaining))
            if not chunk:
                raise CursorRejected("source_truncated")
            self.work.read_bytes += len(chunk)
            self.work.hash_bytes += len(chunk)
            digest.update(chunk)
            remaining -= len(chunk)
        return digest.hexdigest()

    def _verify(self, handle: Any, head: dict[str, Any]) -> None:
        if self._identity(handle) != head["source"]:
            raise CursorRejected("source_replaced")
        if self._hash(handle, head["boundary"]) != head["bytes_digest"]:
            raise CursorRejected("snapshot_bytes_changed")
        self._identity(handle)

    def _capture(self, handle: Any) -> dict[str, Any]:
        source = self._identity(handle)
        size = os.fstat(handle.fileno()).st_size
        if self._head and self._head["source"] == source and self._head["boundary"] == size:
            self._verify(handle, self._head)
            return dict(self._head)
        handle.seek(0)
        digest = hashlib.sha256()
        sequence, offset, previous = 0, 0, None
        self._head = None
        self._db.execute("DELETE FROM records")
        try:
            while offset < size:
                line = handle.readline(_MAX_FRAME_BYTES + 1)
                self.work.read_bytes += len(line)
                if len(line) > _MAX_FRAME_BYTES:
                    raise StoreIntegrityError("journal_frame_limit_exceeded")
                if not line.endswith(b"\n") or offset + len(line) > size:
                    raise StoreIntegrityError("incomplete_journal_frame")
                try:
                    value = json.loads(line)
                except (ValueError, UnicodeError):
                    raise StoreIntegrityError("invalid_journal_frame") from None
                records, frame_digest = JournalTrajectoryStore._decode_frame(
                    value, expected_sequence=sequence, previous_digest=previous)
                self.work.decoded_records += len(records)
                self.work.retain(len(records))
                for record in records:
                    self._db.execute("INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?)",
                                     (record.sequence, record.record_id, record.run_id,
                                      record.session_id, record.work_item_id, record.kind.value,
                                      offset, sequence, previous, frame_digest))
                    self.work.written_index_entries += 6
                sequence += len(records)
                previous = frame_digest
                offset += len(line)
                digest.update(line)
                self.work.hash_bytes += len(line)
                del records, value, line
            self._db.commit()
        except sqlite3.IntegrityError:
            raise StoreIntegrityError("duplicate_record_id") from None
        finally:
            self.work.retain(0)
        head = {"source": source, "boundary": offset, "head_sequence": sequence - 1,
                "head_digest": previous, "bytes_digest": digest.hexdigest()}
        self._verify(handle, head)
        self._head = head
        return dict(head)

    def _seal(self, value: dict[str, Any]) -> TrajectoryCursor:
        body = canonical_json_bytes(value).hex()
        signature = hmac.new(self._key, body.encode(), hashlib.sha256).hexdigest()
        return TrajectoryCursor(body + "." + signature)

    def _unseal(self, cursor: TrajectoryCursor) -> dict[str, Any]:
        try:
            body, signature = cursor.token.split(".")
            expected = hmac.new(self._key, body.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError()
            return json.loads(bytes.fromhex(body))
        except (ValueError, TypeError, AttributeError):
            raise CursorRejected("cursor_binding_invalid") from None

    def validate_snapshot(self, snapshot: TrajectoryCursor) -> None:
        value = self._unseal(snapshot)
        with self._source() as handle:
            self._verify(handle, value["head"])

    def read_page(self, query: TrajectoryQuery, cursor: TrajectoryCursor | None = None,
                  *, view: PrivacyView = PrivacyView.REDACTED_PUBLIC) -> TrajectoryPage:
        limit = query.limit if query.limit is not None else 128
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10_000:
            raise TrajectoryStoreError("page_limit_invalid")
        binding = hashlib.sha256(canonical_json_bytes(
            {"query": asdict(query), "view": view.value})).hexdigest()
        with self._source() as handle:
            if cursor is None:
                head = self._capture(handle)
                position = query.after_sequence if query.after_sequence is not None else -1
            else:
                token = self._unseal(cursor)
                if token["filter"] != binding:
                    raise CursorRejected("cursor_filter_mismatch")
                head, position = token["head"], token["position"]
                if self._head is None:
                    raise CursorRejected("index_rebuild_required")
                self._verify(handle, head)
            snapshot = self._seal({"head": head, "filter": binding, "position": position})
            clauses = ["seq > ?", "seq <= ?"]
            params: list[Any] = [position, head["head_sequence"]]
            for column, value in (("run", query.run_id), ("session", query.session_id),
                                  ("work", query.work_item_id)):
                if value is not None:
                    clauses.append(f"{column} = ?")
                    params.append(value)
            if query.kinds:
                clauses.append("kind IN (" + ",".join("?" for _ in query.kinds) + ")")
                params.extend(kind.value for kind in query.kinds)
            rows = self._db.execute(
                "SELECT seq, offset, start, previous, digest FROM records WHERE "
                + " AND ".join(clauses) + " ORDER BY seq LIMIT ?", (*params, limit + 1))
            selected: list[TrajectoryRecord] = []
            frame_offset = -1
            frame: tuple[TrajectoryRecord, ...] = ()
            more = False
            for seq, offset, start, previous, expected in rows:
                self.work.visited_index_entries += 1
                if len(selected) == limit:
                    more = True
                    break
                if frame_offset != offset:
                    handle.seek(offset)
                    line = handle.readline(_MAX_FRAME_BYTES + 1)
                    self.work.read_bytes += len(line)
                    if len(line) > _MAX_FRAME_BYTES or not line.endswith(b"\n"):
                        raise CursorRejected("snapshot_frame_changed")
                    try:
                        frame, actual = JournalTrajectoryStore._decode_frame(
                            json.loads(line), expected_sequence=start, previous_digest=previous)
                    except (ValueError, UnicodeError):
                        raise CursorRejected("snapshot_frame_changed") from None
                    if actual != expected:
                        raise CursorRejected("snapshot_frame_changed")
                    self.work.decoded_records += len(frame)
                    frame_offset = offset
                selected.append(project_record(frame[seq - start], view))
                self.work.copied_records += 1
                self.work.retain(len(selected) + len(frame))
            rows.close()
            self._verify(handle, head)
            next_cursor = (self._seal({"head": head, "filter": binding,
                                       "position": selected[-1].sequence}) if more else None)
            self.work.retain(len(selected))
            return TrajectoryPage(tuple(selected), next_cursor, snapshot, head["head_sequence"])

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._db.close()
                self._temporary.cleanup()
                self._closed = True
                self.work.retain(0)
