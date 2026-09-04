"""Synthetic notes; fake model, real tools, composition, Session and journal."""
import argparse
from dataclasses import replace
import json
from pathlib import Path

from qitos.config import build_agent_composition, load_agent_config
from qitos.core.function_tool_decorator import function_tool
from qitos.engine.runtime import LifecyclePolicy

# docs:start fixture
NOTES = (
    "Session: A durable session can resume after a process exits.",
    "Artifact: Large tool outputs can be retained outside model context.",
)


@function_tool(read_only=True, concurrency_safe=True)
def summarize_note(index: int) -> dict:
    """Extract a title and word count from a synthetic in-memory note."""
    text = NOTES[index]
    return {"title": text.split(":", 1)[0], "words": len(text.split())}
# docs:end fixture


# docs:start provider
class FakeProvider:
    """Scripted responses; this does not summarize or reason like a real model."""
    model = "notes-fake"
    qitos_protocol = "react_text_v1"

    def __init__(self, start=0):
        self.stage = start

    def call_raw(self, messages, **options):
        if self.stage < len(NOTES):
            content = f"Thought: inspect a note\nAction: summarize_note(index={self.stage})"
        else:
            content = "Final Answer: Indexed 2 notes: Session, Artifact."
        self.stage += 1
        return {"choices": [{"message": {"content": content}}]}
# docs:end provider


class PauseAfterTool(LifecyclePolicy):
    policy_id = "notes.pause_after_tool"

    def should_pause(self, context):
        return context.step_id == 0


# docs:start composition
def configuration(root):
    config = load_agent_config(Path(__file__).with_name("agent.yaml"))
    return replace(config, runtime=replace(
        config.runtime, data_root=str(root / "data"),
        environment=replace(config.runtime.environment, workspace=str(root)),
        session=replace(config.runtime.session, path=str(root / "sessions.sqlite3")),
        trajectory=replace(config.runtime.trajectory, output=str(root / "trajectory.journal")),
    ))


def compose(root, *, start=0, pause=False):
    config = configuration(root)
    if pause:
        config = replace(config, lifecycle={"policy": "pause"})
    composition = build_agent_composition(
        config, model_override=FakeProvider(start), extensions={"pause": PauseAfterTool},
    )
    composition.tool_registry.register(summarize_note)
    return composition
# docs:end composition


# docs:start run
def run(root):
    root.mkdir(parents=True, exist_ok=False)
    with compose(root) as composition:
        session = composition.session("Index both synthetic notes")
        result = session.run()
        outputs = [action.output for record in result.records for action in record.action_results
                   if action.tool_name == "summarize_note"]
        assert [output["title"] for output in outputs] == ["Session", "Artifact"]
        assert result.state.final_result == "Indexed 2 notes: Session, Artifact."
        config = composition.config.to_dict()
        config["runtime"]["environment"] = {"type": "unsafe_host", "workspace": str(root)}
        (root / "agent.json").write_text(json.dumps(config), encoding="utf-8")
        control = {"session_id": session.session_id.value, "run_id": result.run_id}
        (root / "control.json").write_text(json.dumps(control), encoding="utf-8")
        print(json.dumps({**control, "result": result.state.final_result, "outputs": outputs}))
# docs:end run


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("notes-run"))
    run(parser.parse_args().root.resolve())
