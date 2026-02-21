import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from qitos import Action, Decision, Policy, Runtime, RuntimeBudget, ToolRegistry, TraceWriter, tool
from qitos.debug import ReplaySession


@dataclass
class State:
    task: str
    current_step: int = 0
    final_result: Optional[str] = None
    stop_reason: Optional[str] = None


class ToolPolicy(Policy[State, Dict[str, Any], Action]):
    def __init__(self, tool_name: str):
        self.tool_name = tool_name

    def propose(self, state: State, obs: Dict[str, Any]) -> Decision[Action]:
        if state.current_step == 0:
            return Decision.act([Action(name=self.tool_name, args={"a": 40, "b": 2})])
        return Decision.final(str(state.final_result or ""))

    def update(self, state: State, obs: Dict[str, Any], decision: Decision[Action], results: list[Any]) -> State:
        if results:
            first = results[0]
            if isinstance(first, dict) and "error" in first:
                state.final_result = "error"
            else:
                state.final_result = str(first)
        return state


def test_tool_invocation_provenance_in_trace(tmp_path: Path):
    registry = ToolRegistry()

    class MathSet:
        name = "math"
        version = "1.2"

        @tool(name="add")
        def add(self, a: int, b: int) -> int:
            return a + b

        def setup(self, context: Dict[str, Any]) -> None:
            return None

        def teardown(self, context: Dict[str, Any]) -> None:
            return None

        def tools(self):
            return [self.add]

    registry.register_toolset(MathSet())

    writer = TraceWriter(output_dir=str(tmp_path), run_id="tool-provenance")
    runtime = Runtime(policy=ToolPolicy("math.add"), toolkit=registry, budget=RuntimeBudget(max_steps=3), trace_writer=writer)
    result = runtime.run(State(task="sum"))

    assert result.state.final_result == "42"
    steps = [json.loads(line) for line in (tmp_path / "tool-provenance" / "steps.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    inv = steps[0]["tool_invocations"][0]
    assert inv["tool_name"] == "math.add"
    assert inv["toolset_name"] == "math"
    assert inv["source"] == "toolset"


def test_teardown_error_event_and_inspector_hint(tmp_path: Path):
    registry = ToolRegistry()

    class BrokenSet:
        name = "broken"
        version = "0.1"

        @tool(name="add")
        def add(self, a: int, b: int) -> int:
            return a + b

        def setup(self, context: Dict[str, Any]) -> None:
            return None

        def teardown(self, context: Dict[str, Any]) -> None:
            raise RuntimeError("teardown exploded")

        def tools(self):
            return [self.add]

    registry.register_toolset(BrokenSet())

    writer = TraceWriter(output_dir=str(tmp_path), run_id="teardown-error")
    runtime = Runtime(policy=ToolPolicy("broken.add"), toolkit=registry, budget=RuntimeBudget(max_steps=3), trace_writer=writer)
    runtime.run(State(task="sum"))

    events = [json.loads(line) for line in (tmp_path / "teardown-error" / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(e["phase"] == "toolset_teardown_error" and e["ok"] is False for e in events)

    session = ReplaySession(str(tmp_path / "teardown-error"))
    payload = session.inspect_step(0)
    assert payload is not None
    assert "tool_invocations" in payload
