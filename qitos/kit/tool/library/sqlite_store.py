"""Versioned procedural documents/programs; storage never executes skill code."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any, Optional

from .base import BaseToolLibrary, ToolArtifact


class ToolLibraryError(ValueError):
    """Non-echoing library failure, identified by a stable code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class SqliteToolLibrary(BaseToolLibrary):
    """Atomic revisions scoped to an explicitly selected namespace.

    A catalog exposes descriptions, never executable source. ``get`` loads the
    complete selected artifact; no implicit truncation or execution takes place.
    The caller owns the connection and must close it (or use a context manager).
    SQLite is a trusted local resource, not an authorization boundary against a
    user who can directly open the same database file.
    """

    def __init__(self, path: str | Path, *, namespace: str):
        if not isinstance(namespace, str) or not namespace.strip():
            raise ToolLibraryError("invalid_namespace")
        self.namespace = namespace
        self._lock = threading.RLock()
        self._closed = False
        self._db = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
        try:
            self._db.execute('''CREATE TABLE IF NOT EXISTS tool_revisions (
                namespace TEXT NOT NULL, name TEXT NOT NULL, version INTEGER NOT NULL,
                payload TEXT NOT NULL, PRIMARY KEY(namespace, name, version))''')
            self._db.commit()
        except BaseException:
            self._db.close()
            raise

    def __enter__(self) -> SqliteToolLibrary:
        self._require_open()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._db.close()
                self._closed = True

    def _require_open(self) -> None:
        if self._closed:
            raise ToolLibraryError("library_closed")

    @staticmethod
    def _encode(artifact: ToolArtifact) -> str:
        if (not isinstance(artifact, ToolArtifact)
                or not isinstance(artifact.name, str) or not artifact.name.strip()
                or not isinstance(artifact.description, str)
                or not isinstance(artifact.source, str)
                or not isinstance(artifact.summary, str)
                or not isinstance(artifact.tags, list)
                or any(not isinstance(tag, str) for tag in artifact.tags)
                or not isinstance(artifact.metadata, dict)
                or type(artifact.active) is not bool):
            raise ToolLibraryError("invalid_artifact")
        try:
            return json.dumps(asdict(artifact), allow_nan=False, sort_keys=True,
                              ensure_ascii=False)
        except (ValueError, TypeError, RecursionError):
            raise ToolLibraryError("invalid_artifact") from None

    @classmethod
    def _decode(cls, payload: str) -> ToolArtifact:
        try:
            artifact = ToolArtifact(**json.loads(payload))
            cls._encode(artifact)
            if type(artifact.version) is not int or artifact.version < 1:
                raise ValueError
            return artifact
        except (ValueError, TypeError, RecursionError):
            raise ToolLibraryError("corrupt_artifact") from None

    def get(self, name: str) -> Optional[ToolArtifact]:
        with self._lock:
            self._require_open()
            row = self._db.execute(
                'SELECT payload FROM tool_revisions WHERE namespace=? AND name=? '
                'ORDER BY version DESC LIMIT 1', (self.namespace, name),
            ).fetchone()
            return self._decode(row[0]) if row else None

    def get_version(self, name: str, version: int) -> Optional[ToolArtifact]:
        with self._lock:
            self._require_open()
            row = self._db.execute(
                'SELECT payload FROM tool_revisions WHERE namespace=? AND name=? AND version=?',
                (self.namespace, name, version),
            ).fetchone()
            return self._decode(row[0]) if row else None

    def add_or_update(self, artifact: ToolArtifact, *, expected_version: Optional[int] = None) -> ToolArtifact:
        # Clone before acquiring the transaction; caller mutations are isolated.
        copied = self._decode(self._encode(artifact))
        if expected_version is not None and (type(expected_version) is not int or expected_version < 0):
            raise ToolLibraryError("invalid_expected_version")
        with self._lock:
            self._require_open()
            try:
                self._db.execute('BEGIN IMMEDIATE')
                previous = self.get(copied.name)
                version = previous.version if previous else 0
                if expected_version is not None and version != expected_version:
                    raise ToolLibraryError("version_conflict")
                now = datetime.now(timezone.utc).isoformat()
                copied.version = version + 1
                copied.created_at = previous.created_at if previous else now
                copied.updated_at = now
                self._db.execute('INSERT INTO tool_revisions VALUES (?, ?, ?, ?)',
                                 (self.namespace, copied.name, copied.version, self._encode(copied)))
                self._db.commit()
            except BaseException:
                self._db.rollback()
                raise
        return copied

    def list_active(self) -> list[ToolArtifact]:
        with self._lock:
            self._require_open()
            rows = self._db.execute('''SELECT r.payload FROM tool_revisions r
                JOIN (SELECT name, MAX(version) AS v FROM tool_revisions
                      WHERE namespace=? GROUP BY name) h ON r.name=h.name AND r.version=h.v
                WHERE r.namespace=? ORDER BY r.name''', (self.namespace, self.namespace)).fetchall()
            values = [self._decode(row[0]) for row in rows]
            return [value for value in values if value.active]

    def search(self, query: str, top_k: int = 5) -> list[ToolArtifact]:
        if type(top_k) is not int or top_k < 0:
            raise ToolLibraryError("invalid_limit")
        terms = query.casefold().split()
        ranked = []
        for value in self.list_active():
            text = ' '.join([value.name, value.description, *value.tags]).casefold()
            score = sum(text.count(term) for term in terms)
            if score or not terms:
                ranked.append((score, value))
        ranked.sort(key=lambda item: (-item[0], item[1].name))
        return [value for _, value in ranked[:top_k]]

    def catalog(self, query: str = '', *, limit: int = 20) -> list[dict[str, Any]]:
        """Return selectable identities/descriptions without source or metadata.

        This is a projection, not a privacy sanitizer or bounded-I/O claim.
        """
        return [{'name': value.name, 'description': value.description,
                 'version': value.version, 'tags': list(value.tags)}
                for value in self.search(query, top_k=limit)]

    def deprecate(self, name: str) -> bool:
        with self._lock:
            artifact = self.get(name)
            if artifact is None or not artifact.active:
                return False
            artifact.active = False
            self.add_or_update(artifact, expected_version=artifact.version)
            return True
