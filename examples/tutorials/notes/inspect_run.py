"""Read an existing notes run, verify the index, and export a public view."""
import argparse
import json
from pathlib import Path

from qitos.qita.reader import default_reader
from qitos.tracing.exporter import CanonicalTrajectoryExporter
from qitos.tracing.trajectory import PrivacyView


def inspect(root):
    control = json.loads((root / "control.json").read_text())
    trajectory = default_reader(root).read_session(control["session_id"], view=PrivacyView.RAW_PRIVATE)
    assert trajectory.records
    exporter = CanonicalTrajectoryExporter()
    exported = exporter.export(trajectory, view=PrivacyView.REDACTED_PUBLIC)
    imported = exporter.reimport(exported)
    assert len(imported.records) == len(trajectory.records)
    (root / "public-trajectory.json").write_bytes(exported.data)
    # qita's --run selector currently requires an existing run directory.
    # This directory is only a selector; the journal remains authoritative.
    (root / control["run_id"]).mkdir(exist_ok=True)
    print(json.dumps({"records": len(trajectory.records), "lossless": exported.loss.is_lossless,
                      "run_selector": str(root / control["run_id"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    inspect(parser.parse_args().root.resolve())
