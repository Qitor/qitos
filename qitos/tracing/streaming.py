"""Bounded canonical JSON file export, compatible with the existing importer."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Callable

from .exporter import TrajectoryExportError
from .paging import read_page
from .privacy import project_data
from .trajectory import (
    EXPORT_SCHEMA_VERSION, TRAJECTORY_SCHEMA_VERSION, LossReport, PrivacyView,
    TrajectoryQuery, canonical_json_bytes,
)


@dataclass(frozen=True)
class FileExportReceipt:
    """Returned only after full validation, fsync and atomic replacement."""

    record_count: int
    size_bytes: int
    digest: str
    privacy_view: PrivacyView
    completed: bool = True


def _copy(source: BinaryIO, target: BinaryIO, digest: Any = None) -> None:
    while chunk := source.read(256 * 1024):
        target.write(chunk)
        if digest is not None:
            digest.update(chunk)


def export_file(reader: Any, query: TrajectoryQuery, target: str | Path, *,
                view: PrivacyView = PrivacyView.REDACTED_PUBLIC,
                cancelled: Callable[[], bool] | None = None) -> FileExportReceipt:
    """Stream a bounded journal snapshot to an atomically replaced canonical file.

    Disk spools keep arbitrary loss entries/policy IDs out of resident memory.
    The old artifact/reimport API remains materializing. Source authority and
    privacy semantics are unchanged. No receipt is emitted for partial output.
    """
    if not callable(getattr(reader, "validate_snapshot", None)):
        raise TrajectoryExportError("snapshot_validation_unsupported")

    def check_cancel() -> None:
        if cancelled is not None and cancelled():
            raise TrajectoryExportError("export_cancelled")

    target = Path(target)
    validate_target = getattr(reader, "validate_export_target", None)
    if validate_target is not None:
        validate_target(target)
    count = 0
    try:
        with tempfile.TemporaryDirectory(prefix=".qitos-export-", dir=target.parent) as staging:
            root = Path(staging)
            with sqlite3.connect(root / "policies.db") as policies:
                policies.execute("PRAGMA cache_size=-256")
                policies.execute("PRAGMA temp_store=FILE")
                policies.execute("CREATE TABLE policies (id INTEGER PRIMARY KEY, value TEXT UNIQUE)")
                policies.execute("INSERT INTO policies(value) VALUES (?)", ("qitos.loss/none",))
                loss_count = 0
                with (root / "records").open("w+b") as records, (root / "entries").open("w+b") as entries:
                    def add_loss(loss: LossReport) -> None:
                        nonlocal loss_count
                        policies.execute("INSERT OR IGNORE INTO policies(value) VALUES (?)", (loss.policy_id,))
                        for entry in loss.entries:
                            if loss_count:
                                entries.write(b",")
                            entries.write(canonical_json_bytes(entry.to_dict()))
                            loss_count += 1

                    def fallback_pages() -> Any:
                        cursor = None
                        while True:
                            page = read_page(reader, query, cursor, view=view)
                            yield page
                            cursor = page.next_cursor
                            if cursor is None:
                                return

                    stream = getattr(reader, "_export_pages", None)
                    pages = stream(query, view=view) if stream is not None else fallback_pages()
                    for page in pages:
                        check_cancel()
                        for record in page.records:
                            if count:
                                records.write(b",")
                            records.write(canonical_json_bytes(record.to_dict()))
                            count += 1
                            if view != PrivacyView.RAW_PRIVATE:
                                add_loss(record.loss)
                        snapshot = page.snapshot
                        del page
                    metadata = {"store_id": "qitos.journal_trajectory_store", "complete": True}
                    provenance = {"source": "trajectory_journal"}
                    if view != PrivacyView.RAW_PRIVATE:
                        projected_meta = project_data(metadata, view=view)
                        projected_provenance = project_data(provenance, view=view)
                        metadata, provenance = projected_meta.data, projected_provenance.data
                        add_loss(projected_meta.loss)
                        add_loss(projected_provenance.loss)

                    def write_loss(handle: BinaryIO) -> None:
                        handle.write(b'{"entries":[')
                        entries.seek(0)
                        _copy(entries, handle)
                        handle.write(b'],"is_lossless":' + (b"true" if not loss_count else b"false"))
                        handle.write(b',"policy_id":"')
                        for index, (policy,) in enumerate(policies.execute("SELECT value FROM policies ORDER BY id")):
                            if index:
                                handle.write(b"+")
                            handle.write(canonical_json_bytes(policy)[1:-1])
                        handle.write(b'"}')

                    with (root / "body").open("w+b") as body:
                        body.write(b'{"exact_reimport":true,"exporter_id":"qitos.canonical_trajectory",')
                        body.write(b'"format_version":' + canonical_json_bytes(EXPORT_SCHEMA_VERSION) + b',"loss":')
                        write_loss(body)
                        body.write(b',"privacy_view":' + canonical_json_bytes(view.value))
                        body.write(b',"provenance":' + canonical_json_bytes(provenance))
                        body.write(b',"trajectory":{"loss":')
                        write_loss(body)
                        body.write(b',"metadata":' + canonical_json_bytes(metadata))
                        body.write(b',"privacy_view":' + canonical_json_bytes(view.value))
                        body.write(b',"provenance":' + canonical_json_bytes(provenance))
                        body.write(b',"records":[')
                        records.seek(0)
                        _copy(records, body)
                        body.write(b'],"schema_version":' + canonical_json_bytes(TRAJECTORY_SCHEMA_VERSION) + b'}}')
                        body.seek(0)
                        content_hash = hashlib.sha256()
                        while chunk := body.read(256 * 1024):
                            check_cancel()
                            content_hash.update(chunk)
                        final_hash = hashlib.sha256()
                        with (root / "complete").open("wb") as output:
                            prefix = b'{"content_digest":' + canonical_json_bytes(content_hash.hexdigest()) + b","
                            output.write(prefix)
                            final_hash.update(prefix)
                            body.seek(1)
                            _copy(body, output, final_hash)
                            output.flush()
                            os.fsync(output.fileno())
                            size = output.tell()
                        reader.validate_snapshot(snapshot)
                        check_cancel()
                        os.replace(root / "complete", target)
                        return FileExportReceipt(count, size, final_hash.hexdigest(), view)
    except OSError:
        raise TrajectoryExportError("export_write_failed") from None
