"""Canonical wire equivalence and failure-atomic file output."""
import hashlib
import json

import pytest

from qitos.tracing.exporter import CanonicalTrajectoryExporter, ExportArtifact, TrajectoryExportError
from qitos.tracing.paging import CursorRejected
from qitos.tracing.readers import StoreTrajectoryReader
from qitos.tracing.trajectory import LossReport, PrivacyView, TrajectoryQuery
from test_v5_bounded_reader import journal  # fixture shared by these conformance gates


@pytest.mark.parametrize("view", list(PrivacyView))
def test_streamed_export_exactly_matches_existing_projection(journal, view):
    reader = StoreTrajectoryReader.from_journal(journal)
    exporter = CanonicalTrajectoryExporter()
    expected = exporter.export(reader.read_run("run", view=PrivacyView.RAW_PRIVATE), view=view)
    target = journal.parent / "export.json"
    receipt = exporter.export_file(reader, TrajectoryQuery(run_id="run", limit=128), target, view=view)
    assert receipt.completed and receipt.record_count == 259
    assert target.read_bytes() == expected.data
    assert receipt.digest == hashlib.sha256(target.read_bytes()).hexdigest()
    value = json.loads(target.read_bytes())
    restored = exporter.reimport(ExportArtifact(
        exporter.capabilities.exporter_id, exporter.capabilities.format_version,
        "application/json", target.read_bytes(), receipt.digest, view, True,
        value["provenance"], LossReport.from_dict(value["loss"])))
    assert restored.to_dict() == exporter.reimport(expected).to_dict()
    assert reader._materialized is None
    reader.close()


@pytest.mark.parametrize("failure", ["late_corruption", "cancel", "write", "fsync"])
def test_export_failure_keeps_target_and_cleans_only_owned_staging(journal, monkeypatch, failure):
    import os
    import qitos.tracing.streaming as streaming

    target = journal.parent / "export.json"
    target.write_bytes(b"original")
    sentinel = journal.parent / ".qitos-export-unrelated"
    sentinel.mkdir()
    reader = StoreTrajectoryReader.from_journal(journal)
    original_validate = reader.validate_snapshot

    def late(snapshot):
        journal.write_bytes(journal.read_bytes().replace(b'"i":0', b'"i":9', 1))
        return original_validate(snapshot)

    if failure == "late_corruption":
        monkeypatch.setattr(reader, "validate_snapshot", late)
    elif failure == "write":
        monkeypatch.setattr(streaming, "_copy", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    elif failure == "fsync":
        monkeypatch.setattr(os, "fsync", lambda *a: (_ for _ in ()).throw(OSError()))
    calls = 0

    def cancelled():
        nonlocal calls
        calls += 1
        return failure == "cancel" and calls > 1

    with pytest.raises((TrajectoryExportError, CursorRejected)):
        CanonicalTrajectoryExporter().export_file(reader, TrajectoryQuery(limit=128), target,
                                                   cancelled=cancelled)
    assert target.read_bytes() == b"original"
    assert list(journal.parent.glob(".qitos-export-*")) == [sentinel]
    reader.close()


def test_public_sensitive_payload_and_nonempty_losses_match_old_export(tmp_path):
    from qitos.tracing.journal_store import JournalTrajectoryStore
    from qitos.tracing.trajectory import LossEntry, RecordKind, TrajectoryRecord

    path = tmp_path / "trajectory.journal"
    writer = JournalTrajectoryStore(path)
    for i in range(3):
        writer.append(TrajectoryRecord.create(
            RecordKind.RUN, run_id="run", payload={"api_key": "private-value", "ordinal": i},
            loss=LossReport(policy_id=f"policy-{i}", entries=(LossEntry("source_loss"),))))
    writer.close()
    reader = StoreTrajectoryReader.from_journal(path)
    exporter = CanonicalTrajectoryExporter()
    expected = exporter.export(reader.read_run("run", view=PrivacyView.RAW_PRIVATE))
    target = tmp_path / "public.json"
    exporter.export_file(reader, TrajectoryQuery(run_id="run", limit=1), target)
    assert target.read_bytes() == expected.data
    assert b"private-value" not in target.read_bytes()
    reader.close()


@pytest.mark.parametrize("suffix", ["", ".lock", ".index.json"])
def test_export_cannot_replace_readonly_source_or_sidecar(journal, suffix):
    reader = StoreTrajectoryReader.from_journal(journal)
    target = journal.with_name(journal.name + suffix)
    before = target.read_bytes()
    with pytest.raises(TrajectoryExportError, match="export_target_is_source"):
        CanonicalTrajectoryExporter().export_file(reader, TrajectoryQuery(limit=128), target)
    assert target.read_bytes() == before
    reader.close()
