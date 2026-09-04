"""Two processes, a durable checkpoint, steering and independent fork."""
import argparse
import json
from pathlib import Path

from notes import compose
from qitos.qita.reader import default_reader
from qitos.tracing.trajectory import PrivacyView


# docs:start create
def create(root):
    root.mkdir(parents=True, exist_ok=False)
    with compose(root, pause=True) as composition:
        session = composition.session("Index the two notes")
        result = session.run()
        assert session.lifecycle.value == "paused"
        assert result.records[0].action_results[0].output["title"] == "Session"
        document = composition.config.to_dict()
        document["runtime"]["environment"] = {"type": "unsafe_host", "workspace": str(root)}
        (root / "agent.json").write_text(json.dumps(document), encoding="utf-8")
        (root / "control.json").write_text(json.dumps({"session_id": session.session_id.value}), encoding="utf-8")
        print("paused after first note; exit this process before restore")
# docs:end create


# docs:start restore
def restore(root):
    identity = json.loads((root / "control.json").read_text())["session_id"]
    # This fixture always pauses after its first response. Only the fake cursor
    # is supplied here; QitOS restores the real Session state from SQLite.
    with compose(root, start=1, pause=True) as composition:
        before = composition.runtime.checkpoint_store.get_session_head(identity)
        child = composition.fork(identity)
        child.run(steering="Finish an independent index.")
        assert child.session_id.value != identity
        assert composition.runtime.checkpoint_store.get_session_head(identity) == before
    with compose(root, start=1, pause=True) as composition:
        session = composition.restore(identity)
        result = session.run(steering="Finish the index concisely.")
        assert any(a.tool_name == "summarize_note" and a.output["title"] == "Artifact"
                   for record in result.records for a in record.action_results)
        assert result.state.final_result == "Indexed 2 notes: Session, Artifact."
        trajectory = default_reader(root).read_session(identity, view=PrivacyView.RAW_PRIVATE)
        assert any(record.kind.value == "steering" for record in trajectory.records)
        (root / "control.json").write_text(json.dumps({"session_id": identity, "run_id": result.run_id}), encoding="utf-8")
        print("restored; steering recorded; fork left parent head unchanged")
# docs:end restore


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("create", "restore"))
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    {"create": create, "restore": restore}[args.phase](args.root.resolve())
