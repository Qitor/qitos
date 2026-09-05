"""Installed, offline public API: Agent record -> page -> iterate -> export -> qita."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from qitos import AgentModule, Decision, StateSchema
from qitos.qita.reader import candidate_file_reader
from qitos.tracing.exporter import CanonicalTrajectoryExporter, ExportArtifact
from qitos.tracing.paging import iter_records
from qitos.tracing.trajectory import LossReport, PrivacyView, TrajectoryQuery


class RecordingAgent(AgentModule):
    def init_state(self, task, **kwargs):
        return StateSchema(task=task, max_steps=2)

    def reduce(self, state, observation, decision):
        return state

    def decide(self, state, observation):
        return Decision.final("deterministic trajectory recorded")


def main(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    result = RecordingAgent().run("Record one deterministic result", render=False,
                                  trace_logdir=str(root), return_state=True)
    path = root / "trajectory.journal"
    reader = candidate_file_reader(path)
    try:
        query = TrajectoryQuery(run_id=result.run_id, limit=128)
        page = reader.read_page(query, view=PrivacyView.RAW_PRIVATE)
        assert page.records and reader.capabilities.bounded_read
        records = tuple(iter_records(reader, query, view=PrivacyView.RAW_PRIVATE))
        exporter = CanonicalTrajectoryExporter()
        target = root / "canonical.json"
        receipt = exporter.export_file(reader, query, target, view=PrivacyView.RAW_PRIVATE)
        value = json.loads(target.read_bytes())
        artifact = ExportArtifact(exporter.capabilities.exporter_id, exporter.capabilities.format_version,
                                  "application/json", target.read_bytes(), receipt.digest,
                                  PrivacyView.RAW_PRIVATE, True, value["provenance"],
                                  LossReport.from_dict(value["loss"]))
        imported = exporter.reimport(artifact)
        assert tuple(r.to_dict() for r in imported.records) == tuple(r.to_dict() for r in records)
        assert receipt.digest == hashlib.sha256(target.read_bytes()).hexdigest()
        assert receipt.completed
        subprocess.run([sys.executable, "-m", "qitos.qita", "inspect", "timeline", result.run_id,
                        "--kind", "run", "--candidate-store", str(path)], check=True, capture_output=True)
        subprocess.run(["qita", "export", "--run", result.run_id, "--journal", str(path),
                        "--canonical", str(root / "public.json")], check=True)
        print(json.dumps({"installed_consumer": "passed", "records": len(records),
                          "page_watermark": page.watermark, "canonical_reimport": "record_equal"}))
    finally:
        reader.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("trajectory-example"))
    main(parser.parse_args().root.resolve())
