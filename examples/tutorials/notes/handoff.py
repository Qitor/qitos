"""Transfer one work item's owner; demonstrate the superseded source fence."""
import argparse
from pathlib import Path
import subprocess
import sys

from notes import compose
from multi_agent import wait
from qitos.engine.work_runtime import DurableWorkRuntime, LocalWorkScheduler, WorkRuntimeError


def run(root):
    root.mkdir(parents=True, exist_ok=False)

    class Resolver:
        resolver_id = "notes.handoff.worker"

        def resolve(self, descriptor):
            def execute():
                # Acknowledge transfer before the destination claims this same
                # Session head. This receipt is not destination task completion.
                return {"destination": descriptor.parent_session_id, "admitted": True}
            return execute

    with compose(root, pause=True) as composition:
        composition.runtime.work_runtime = DurableWorkRuntime(LocalWorkScheduler(Resolver()))
        source = composition.session("Index notes, then transfer ownership")
        source.run()
        identity = source.work_item_id
        operation = source.handoff("notes_agent", rationale="Finish with the destination worker")
        graph = wait(source, operation)
        transfer = graph.transfers[-1]
        assert transfer.from_agent_id != transfer.to_agent_id
        assert graph.work_items[identity].owner.agent_id == transfer.to_agent_id
        try:
            source.spawn("notes_agent", task="A stale owner must not dispatch")
        except WorkRuntimeError as error:
            assert error.code == "superseded_owner"
        else:
            raise AssertionError("Superseded source unexpectedly dispatched")
        identity = source.session_id.value
    # Serialized handoff: source callbacks and resource cleanup finish first.
    result = subprocess.run([
        sys.executable, __file__, "--root", str(root), "--destination", identity,
    ], capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError(result.stderr)
    print("handoff destination ran; owner changed; source fenced")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--destination")
    args = parser.parse_args()
    if args.destination:
        with compose(args.root.resolve(), start=1, pause=True) as composition:
            result = composition.restore(args.destination).run()
            assert result.state.final_result == "Indexed 2 notes: Session, Artifact."
    else:
        run(args.root.resolve())
