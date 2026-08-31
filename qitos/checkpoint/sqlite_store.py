"""SQLite-backed checkpoint store with WAL mode.

Provides durable, file-based checkpoint persistence suitable for
production use.  Uses WAL mode for concurrent read/write support.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any, Iterator, List, Optional, Sequence

from .store import (
    Checkpoint,
    CheckpointConfig,
    CheckpointId,
    CheckpointMetadata,
    CheckpointStore,
    CheckpointTuple,
    PendingWrite,
    StateVersions,
)
from .session import (
    SESSION_PERSISTENCE_CAPABILITIES,
    CheckpointPersistenceError,
    CheckpointSessionError,
    CheckpointSessionErrorCode,
    SessionCommitReceipt,
    SessionHeadRecord,
    SessionSnapshotCommit,
    SessionSnapshotRecord,
    checkpoint_conflict,
    generation_conflict,
    owner_conflict,
)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id  TEXT PRIMARY KEY,
    thread_id      TEXT NOT NULL,
    step           INTEGER NOT NULL,
    state_data     TEXT NOT NULL,          -- JSON
    state_versions TEXT NOT NULL DEFAULT '{}',  -- JSON
    versions_seen  TEXT NOT NULL DEFAULT '{}',  -- JSON
    parent_id      TEXT,
    created_at     TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT 'v2'
);

CREATE TABLE IF NOT EXISTS checkpoint_writes (
    write_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    checkpoint_id TEXT NOT NULL REFERENCES checkpoints(checkpoint_id),
    task_id       TEXT NOT NULL,
    channel       TEXT NOT NULL,
    value         TEXT,                     -- JSON (nullable)
    UNIQUE(checkpoint_id, task_id, channel)
);

CREATE TABLE IF NOT EXISTS checkpoint_metadata (
    checkpoint_id TEXT PRIMARY KEY REFERENCES checkpoints(checkpoint_id),
    source        TEXT,
    step_int      INTEGER,
    parents       TEXT DEFAULT '{}',        -- JSON
    run_id        TEXT
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_thread
    ON checkpoints(thread_id, step);

CREATE INDEX IF NOT EXISTS idx_writes_checkpoint
    ON checkpoint_writes(checkpoint_id);

CREATE TABLE IF NOT EXISTS session_heads (
    session_id     TEXT PRIMARY KEY,
    snapshot_id    TEXT NOT NULL,
    checkpoint_id  TEXT NOT NULL REFERENCES checkpoints(checkpoint_id),
    generation     INTEGER NOT NULL,
    owner_run_id   TEXT NOT NULL,
    lifecycle      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_snapshot_index (
    snapshot_id    TEXT PRIMARY KEY,
    session_id     TEXT NOT NULL,
    checkpoint_id  TEXT NOT NULL UNIQUE REFERENCES checkpoints(checkpoint_id)
);

CREATE INDEX IF NOT EXISTS idx_session_snapshots_session
    ON session_snapshot_index(session_id);
"""


class SqliteCheckpointStore(CheckpointStore):
    """SQLite-backed checkpoint store with WAL mode.

    Args:
        db_path: Path to the SQLite database file.
            Use ``":memory:"`` for an in-memory database (testing only).
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None  # type: ignore[assignment]

    def __enter__(self) -> SqliteCheckpointStore:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ---- internal helpers ----

    def _row_to_checkpoint(self, row: tuple) -> Checkpoint:
        (
            cp_id, thread_id, step,
            state_data_json, state_versions_json, versions_seen_json,
            parent_id, created_at, schema_version,
        ) = row
        return Checkpoint(
            id=CheckpointId(cp_id),
            thread_id=thread_id,
            step=step,
            state_data=json.loads(state_data_json),
            state_versions=json.loads(state_versions_json),
            versions_seen=json.loads(versions_seen_json),
            parent_id=parent_id,
            created_at=created_at,
            schema_version=schema_version,
        )

    def _load_pending_writes(self, checkpoint_id: str) -> List[PendingWrite]:
        cur = self._conn.execute(
            "SELECT task_id, channel, value FROM checkpoint_writes "
            "WHERE checkpoint_id = ?",
            (checkpoint_id,),
        )
        writes = []
        for task_id, channel, value_json in cur.fetchall():
            value = json.loads(value_json) if value_json is not None else None
            writes.append(PendingWrite(task_id=task_id, channel=channel, value=value))
        return writes

    def _load_metadata(self, checkpoint_id: str) -> CheckpointMetadata:
        cur = self._conn.execute(
            "SELECT source, step_int, parents, run_id FROM checkpoint_metadata "
            "WHERE checkpoint_id = ?",
            (checkpoint_id,),
        )
        row = cur.fetchone()
        if row is None:
            return CheckpointMetadata()
        source, step_int, parents_json, run_id = row
        meta: CheckpointMetadata = {}
        if source is not None:
            meta["source"] = source
        if step_int is not None:
            meta["step"] = step_int
        if parents_json is not None:
            meta["parents"] = json.loads(parents_json)
        if run_id is not None:
            meta["run_id"] = run_id
        return meta

    def _resolve_config(self, config: CheckpointConfig) -> Optional[CheckpointId]:
        if config.checkpoint_id is not None:
            return config.checkpoint_id
        # find latest for thread
        cur = self._conn.execute(
            "SELECT checkpoint_id FROM checkpoints "
            "WHERE thread_id = ? ORDER BY step DESC, rowid DESC LIMIT 1",
            (config.thread_id,),
        )
        row = cur.fetchone()
        return CheckpointId(row[0]) if row else None

    def _find_parent_config(self, thread_id: str, parent_id: Optional[str]) -> Optional[CheckpointConfig]:
        if parent_id is None:
            return None
        return CheckpointConfig(thread_id=thread_id, checkpoint_id=CheckpointId(parent_id))

    # ---- sync interface ----

    def put(
        self,
        config: CheckpointConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: StateVersions,
    ) -> CheckpointConfig:
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO checkpoints "
                "(checkpoint_id, thread_id, step, state_data, state_versions, "
                "versions_seen, parent_id, created_at, schema_version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    checkpoint.id,
                    checkpoint.thread_id,
                    checkpoint.step,
                    json.dumps(checkpoint.state_data, ensure_ascii=False),
                    json.dumps(checkpoint.state_versions, ensure_ascii=False),
                    json.dumps(checkpoint.versions_seen, ensure_ascii=False),
                    checkpoint.parent_id,
                    checkpoint.created_at,
                    checkpoint.schema_version,
                ),
            )
            # metadata
            self._conn.execute(
                "INSERT OR REPLACE INTO checkpoint_metadata "
                "(checkpoint_id, source, step_int, parents, run_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    checkpoint.id,
                    metadata.get("source"),
                    metadata.get("step"),
                    json.dumps(metadata.get("parents", {}), ensure_ascii=False),
                    metadata.get("run_id"),
                ),
            )

        return CheckpointConfig(
            thread_id=config.thread_id, checkpoint_id=checkpoint.id
        )

    def get_tuple(self, config: CheckpointConfig) -> Optional[CheckpointTuple]:
        cp_id = self._resolve_config(config)
        if cp_id is None:
            return None
        cur = self._conn.execute(
            "SELECT checkpoint_id, thread_id, step, state_data, state_versions, "
            "versions_seen, parent_id, created_at, schema_version "
            "FROM checkpoints WHERE checkpoint_id = ?",
            (cp_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        checkpoint = self._row_to_checkpoint(row)
        pending_writes = self._load_pending_writes(cp_id)
        meta = self._load_metadata(cp_id)
        parent_config = self._find_parent_config(checkpoint.thread_id, checkpoint.parent_id)

        return CheckpointTuple(
            config=CheckpointConfig(
                thread_id=checkpoint.thread_id, checkpoint_id=checkpoint.id
            ),
            checkpoint=checkpoint,
            metadata=meta,
            parent_config=parent_config,
            pending_writes=pending_writes if pending_writes else None,
        )

    def list(
        self,
        config: CheckpointConfig,
        *,
        limit: Optional[int] = None,
        before: Optional[CheckpointConfig] = None,
    ) -> Iterator[CheckpointTuple]:
        params: list = [config.thread_id]
        sql = (
            "SELECT checkpoint_id, thread_id, step, state_data, state_versions, "
            "versions_seen, parent_id, created_at, schema_version "
            "FROM checkpoints WHERE thread_id = ?"
        )
        if before is not None and before.checkpoint_id is not None:
            sql += " AND step < (SELECT step FROM checkpoints WHERE checkpoint_id = ?)"
            params.append(before.checkpoint_id)
        sql += " ORDER BY step DESC, rowid DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        cur = self._conn.execute(sql, params)
        for row in cur.fetchall():
            checkpoint = self._row_to_checkpoint(row)
            pending_writes = self._load_pending_writes(checkpoint.id)
            meta = self._load_metadata(checkpoint.id)
            parent_config = self._find_parent_config(
                checkpoint.thread_id, checkpoint.parent_id
            )
            yield CheckpointTuple(
                config=CheckpointConfig(
                    thread_id=checkpoint.thread_id,
                    checkpoint_id=checkpoint.id,
                ),
                checkpoint=checkpoint,
                metadata=meta,
                parent_config=parent_config,
                pending_writes=pending_writes if pending_writes else None,
            )

    def put_writes(
        self,
        config: CheckpointConfig,
        writes: Sequence[PendingWrite],
        task_id: str,
    ) -> None:
        cp_id = self._resolve_config(config)
        if cp_id is None:
            return
        with self._conn:
            for w in writes:
                self._conn.execute(
                    "INSERT OR REPLACE INTO checkpoint_writes "
                    "(checkpoint_id, task_id, channel, value) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        cp_id,
                        w.task_id,
                        w.channel,
                        json.dumps(w.value, ensure_ascii=False) if w.value is not None else None,
                    ),
                )

    def delete(self, config: CheckpointConfig) -> None:
        cp_id = self._resolve_config(config)
        if cp_id is None:
            return
        with self._conn:
            self._conn.execute(
                "DELETE FROM checkpoint_writes WHERE checkpoint_id = ?", (cp_id,)
            )
            self._conn.execute(
                "DELETE FROM checkpoint_metadata WHERE checkpoint_id = ?", (cp_id,)
            )
            self._conn.execute(
                "DELETE FROM checkpoints WHERE checkpoint_id = ?", (cp_id,)
            )

    # ---- durable Session protocol ----

    def session_capabilities(self) -> frozenset[str]:
        return SESSION_PERSISTENCE_CAPABILITIES

    def commit_session_snapshot(
        self, request: SessionSnapshotCommit
    ) -> SessionCommitReceipt:
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                current = self._load_session_head_row(request.session_id)
                self._validate_session_cas(request, current)
                parent_id = current.checkpoint_id if current is not None else None
                self._conn.execute(
                    "INSERT INTO checkpoints "
                    "(checkpoint_id, thread_id, step, state_data, state_versions, "
                    "versions_seen, parent_id, created_at, schema_version) "
                    "VALUES (?, ?, ?, ?, '{}', '{}', ?, ?, ?)",
                    (
                        request.checkpoint_id,
                        request.session_id,
                        request.target_generation,
                        json.dumps(
                            {"session_snapshot": request.payload},
                            ensure_ascii=False,
                            allow_nan=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        parent_id,
                        str(request.payload.get("created_at", "")),
                        "qitos.session.snapshot/v2",
                    ),
                )
                self._conn.execute(
                    "INSERT INTO checkpoint_metadata "
                    "(checkpoint_id, source, step_int, parents, run_id) "
                    "VALUES (?, 'session', ?, '{}', ?)",
                    (
                        request.checkpoint_id,
                        request.target_generation,
                        request.owner_run_id,
                    ),
                )
                self._conn.execute(
                    "INSERT INTO session_snapshot_index "
                    "(snapshot_id, session_id, checkpoint_id) VALUES (?, ?, ?)",
                    (
                        request.snapshot_id,
                        request.session_id,
                        request.checkpoint_id,
                    ),
                )
                if current is None:
                    self._conn.execute(
                        "INSERT INTO session_heads "
                        "(session_id, snapshot_id, checkpoint_id, generation, "
                        "owner_run_id, lifecycle) VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            request.session_id,
                            request.snapshot_id,
                            request.checkpoint_id,
                            request.target_generation,
                            request.owner_run_id,
                            request.lifecycle,
                        ),
                    )
                else:
                    self._conn.execute(
                        "UPDATE session_heads SET snapshot_id = ?, checkpoint_id = ?, "
                        "generation = ?, owner_run_id = ?, lifecycle = ? "
                        "WHERE session_id = ?",
                        (
                            request.snapshot_id,
                            request.checkpoint_id,
                            request.target_generation,
                            request.owner_run_id,
                            request.lifecycle,
                            request.session_id,
                        ),
                    )
                self._conn.commit()
            except CheckpointSessionError:
                self._conn.rollback()
                raise
            except sqlite3.IntegrityError as exc:
                self._conn.rollback()
                raise checkpoint_conflict() from exc
            except (sqlite3.Error, TypeError, ValueError) as exc:
                self._conn.rollback()
                raise CheckpointPersistenceError() from exc

        return SessionCommitReceipt(
            session_id=request.session_id,
            snapshot_id=request.snapshot_id,
            checkpoint_id=request.checkpoint_id,
            generation=request.target_generation,
            owner_run_id=request.owner_run_id,
            lifecycle=request.lifecycle,
            durable=True,
            store_kind="sqlite",
        )

    def get_session_head(self, session_id: str) -> Optional[SessionHeadRecord]:
        with self._lock:
            return self._load_session_head_row(session_id)

    def get_session_snapshot(
        self, snapshot_id: str
    ) -> Optional[SessionSnapshotRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT i.session_id, i.snapshot_id, c.checkpoint_id, c.step, "
                "m.run_id, h.lifecycle, c.state_data, c.parent_id "
                "FROM session_snapshot_index i "
                "JOIN checkpoints c ON c.checkpoint_id = i.checkpoint_id "
                "LEFT JOIN checkpoint_metadata m ON m.checkpoint_id = c.checkpoint_id "
                "LEFT JOIN session_heads h ON h.session_id = i.session_id "
                "AND h.snapshot_id = i.snapshot_id WHERE i.snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
        return self._session_record_from_row(row) if row is not None else None

    def list_session_lineage(
        self, session_id: str, *, limit: Optional[int] = None
    ) -> Iterator[SessionSnapshotRecord]:
        sql = (
            "SELECT i.session_id, i.snapshot_id, c.checkpoint_id, c.step, "
            "m.run_id, h.lifecycle, c.state_data, c.parent_id "
            "FROM session_snapshot_index i "
            "JOIN checkpoints c ON c.checkpoint_id = i.checkpoint_id "
            "LEFT JOIN checkpoint_metadata m ON m.checkpoint_id = c.checkpoint_id "
            "LEFT JOIN session_heads h ON h.session_id = i.session_id "
            "AND h.snapshot_id = i.snapshot_id WHERE i.session_id = ? "
            "ORDER BY c.step DESC, c.rowid DESC"
        )
        params: List[Any] = [session_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        for row in rows:
            yield self._session_record_from_row(row)

    def _load_session_head_row(self, session_id: str) -> Optional[SessionHeadRecord]:
        row = self._conn.execute(
            "SELECT session_id, snapshot_id, checkpoint_id, generation, "
            "owner_run_id, lifecycle FROM session_heads WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return SessionHeadRecord(*row) if row is not None else None

    @staticmethod
    def _validate_session_cas(
        request: SessionSnapshotCommit, current: Optional[SessionHeadRecord]
    ) -> None:
        if request.expected_generation is None:
            if current is not None:
                raise generation_conflict(None, current.generation)
            return
        if current is None:
            raise generation_conflict(request.expected_generation, None)
        if current.generation != request.expected_generation:
            raise generation_conflict(request.expected_generation, current.generation)
        if current.checkpoint_id != request.expected_checkpoint_id:
            raise checkpoint_conflict()
        if current.owner_run_id != request.expected_owner_run_id:
            raise owner_conflict()

    @staticmethod
    def _session_record_from_row(row: tuple) -> SessionSnapshotRecord:
        (
            session_id,
            snapshot_id,
            checkpoint_id,
            generation,
            owner_run_id,
            current_lifecycle,
            state_data_json,
            parent_checkpoint_id,
        ) = row
        try:
            state_data = json.loads(state_data_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise CheckpointSessionError(
                CheckpointSessionErrorCode.CORRUPT_SNAPSHOT,
                "Stored checkpoint JSON is corrupt.",
                recoverable=False,
            ) from exc
        payload = state_data.get("session_snapshot") if isinstance(state_data, dict) else None
        if not isinstance(payload, dict):
            raise CheckpointSessionError(
                CheckpointSessionErrorCode.INCOMPATIBLE_CHECKPOINT,
                "Checkpoint does not contain a canonical Session snapshot.",
                recoverable=False,
            )
        lifecycle = current_lifecycle or str(payload.get("lifecycle", ""))
        return SessionSnapshotRecord(
            session_id=session_id,
            snapshot_id=snapshot_id,
            checkpoint_id=checkpoint_id,
            generation=generation,
            owner_run_id=owner_run_id or "unknown",
            lifecycle=lifecycle,
            payload=payload,
            parent_checkpoint_id=parent_checkpoint_id,
        )


__all__ = ["SqliteCheckpointStore"]
