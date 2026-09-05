"""Page an existing notes journal, stream a public export and verify re-import."""
import argparse
import json
from pathlib import Path

from qitos.qita.reader import default_reader
from qitos.tracing.exporter import CanonicalTrajectoryExporter, ExportArtifact
from qitos.tracing.paging import iter_records
from qitos.tracing.trajectory import LossReport, PrivacyView, TrajectoryQuery


def inspect(root):
    control = json.loads((root / "control.json").read_text())
    reader = default_reader(root)
    try:
        query = TrajectoryQuery(session_id=control["session_id"], limit=128)
        page = reader.read_page(query)
        assert page.records
        exporter = CanonicalTrajectoryExporter()
        target = root / "public-trajectory.json"
        receipt = exporter.export_file(reader, query, target)
        # Re-import remains a materializing API; this small lesson checks every record.
        data = target.read_bytes()
        value = json.loads(data)
        artifact = ExportArtifact(exporter.capabilities.exporter_id, exporter.capabilities.format_version,
                                  "application/json", data, receipt.digest, PrivacyView.REDACTED_PUBLIC,
                                  True, value["provenance"], LossReport.from_dict(value["loss"]))
        imported = exporter.reimport(artifact)
        expected = iter_records(reader, query)
        for actual in imported.records:
            assert actual.to_dict() == next(expected).to_dict()
        assert next(expected, None) is None
        # Legacy replay/HTML CLI still accepts an existing directory selector.
        (root / control["run_id"]).mkdir(exist_ok=True)
        print(json.dumps({"records": receipt.record_count, "lossless": imported.loss.is_lossless,
                          "run_selector": str(root / control["run_id"]), "bounded_export": True}))
    finally:
        reader.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    inspect(parser.parse_args().root.resolve())
