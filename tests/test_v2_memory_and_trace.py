import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from qitos.core.action import Action
from qitos import AgentModule, Decision
from qitos.core.state import StateSchema
from qitos.core.tool import tool
from qitos import ToolRegistry
from qitos.engine.fsm_engine import FSMEngine
from qitos.memory.v2 import MemoryRecord, SummaryMemoryV2, VectorMemoryV2, WindowMemoryV2
from qitos.trace import TraceWriter


class TestMemoryV2:
    def test_window_memory_retrieve_and_evict(self):
        mem = WindowMemoryV2(window_size=2)
        mem.append(MemoryRecord(role="user", content="a", step_id=0))
        mem.append(MemoryRecord(role="assistant", content="b", step_id=1))
        mem.append(MemoryRecord(role="user", content="c", step_id=2))

        recs = mem.retrieve()
        assert len(recs) == 2
        assert recs[0].content == "b"
        assert mem.evict() == 1

    def test_summary_memory(self):
        mem = SummaryMemoryV2(keep_last=2)
        mem.append(MemoryRecord(role="user", content="alpha", step_id=0))
        mem.append(MemoryRecord(role="assistant", content="beta", step_id=1))
        mem.append(MemoryRecord(role="assistant", content="gamma", step_id=2))

        removed = mem.evict()
        assert removed == 1
        assert len(mem.retrieve()) == 2

    def test_vector_memory_retrieve(self):
        mem = VectorMemoryV2(top_k=1)
        mem.append(MemoryRecord(role="user", content="read python docs", step_id=0))
        mem.append(MemoryRecord(role="user", content="book flight", step_id=1))

        hit = mem.retrieve({"text": "python", "top_k": 1})
        assert len(hit) == 1


@dataclass
class TraceState(StateSchema):
    notes: List[str] = field(default_factory=list)


class TraceAgent(AgentModule[TraceState, Dict[str, Any], Action]):
    def __init__(self):
        registry = ToolRegistry()

        @tool(name="add")
        def add(a: int, b: int) -> int:
            return a + b

        registry.register(add)
        super().__init__(toolkit=registry)

    def init_state(self, task: str, **kwargs: Any) -> TraceState:
        return TraceState(task=task, max_steps=2)

    def observe(self, state: TraceState, env_view: Dict[str, Any]) -> Dict[str, Any]:
        return {"step": state.current_step}

    def decide(self, state: TraceState, observation: Dict[str, Any]) -> Decision[Action]:
        if state.current_step == 0:
            return Decision.act(actions=[Action(name="add", args={"a": 10, "b": 32})])
        return Decision.final("42")

    def reduce(
        self,
        state: TraceState,
        observation: Dict[str, Any],
        decision: Decision[Action],
        action_results: List[Any],
    ) -> TraceState:
        if action_results:
            state.notes.append(str(action_results[0]))
        return state


class TestTraceWriterIntegration:
    def test_fsm_trace_files(self, tmp_path: Path):
        writer = TraceWriter(output_dir=str(tmp_path), run_id="run-1")
        memory = WindowMemoryV2(window_size=20)
        engine = FSMEngine(agent=TraceAgent(), trace_writer=writer, memory=memory)

        result = engine.run("trace task")

        run_dir = tmp_path / "run-1"
        assert (run_dir / "events.jsonl").exists()
        assert (run_dir / "steps.jsonl").exists()
        assert (run_dir / "manifest.json").exists()

        manifest = json.loads((run_dir / "manifest.json").read_text())
        assert manifest["status"] == "completed"
        assert manifest["summary"]["final_result"] == "42"

        steps_lines = (run_dir / "steps.jsonl").read_text().strip().splitlines()
        assert len(steps_lines) == len(result.records)
        step0 = json.loads(steps_lines[0])
        assert step0["actions"][0]["name"] == "add"
        mem_roles = [r.role for r in memory.records]
        assert "observation" in mem_roles
        assert "decision" in mem_roles
        assert "action_result" in mem_roles
