from dataclasses import dataclass
from typing import Any, Dict, Optional

import pytest

from qitos import (
    Action,
    Decision,
    JsonDecisionParser,
    MemoryRecord,
    Policy,
    ReActTextParser,
    Runtime,
    RuntimeBudget,
    ToolRegistry,
    WindowMemory,
    SummaryMemory,
    VectorMemory,
    XmlDecisionParser,
    tool,
)


@dataclass
class State:
    task: str
    current_step: int = 0
    final_result: Optional[str] = None
    stop_reason: Optional[str] = None


class StablePolicy(Policy[State, Dict[str, Any], Action]):
    def propose(self, state: State, obs: Dict[str, Any]) -> Decision[Action]:
        if state.current_step == 0:
            return Decision.act([Action(name="add", args={"a": 40, "b": 2})])
        return Decision.final(str(state.final_result or ""))

    def update(self, state: State, obs: Dict[str, Any], decision: Decision[Action], results: list[Any]) -> State:
        if results:
            state.final_result = str(results[0])
        return state


class ParseThenRecoverPolicy(Policy[State, Dict[str, Any], str]):
    def propose(self, state: State, obs: Dict[str, Any]) -> str:
        if state.current_step == 0:
            return "gibberish"
        return "Final Answer: 42"

    def update(self, state: State, obs: Dict[str, Any], decision: Decision[str], results: list[Any]) -> State:
        return state


class FatalPolicy(Policy[State, Dict[str, Any], Action]):
    def propose(self, state: State, obs: Dict[str, Any]) -> Decision[Action]:
        raise RuntimeError("fatal-propose-error")

    def update(self, state: State, obs: Dict[str, Any], decision: Decision[Action], results: list[Any]) -> State:
        return state


class TestRuntimeSemantics:
    def test_runtime_success_path(self):
        registry = ToolRegistry()

        @tool(name="add")
        def add(a: int, b: int) -> int:
            return a + b

        registry.register(add)
        runtime = Runtime(policy=StablePolicy(), toolkit=registry, budget=RuntimeBudget(max_steps=4))
        result = runtime.run(State(task="sum"))

        assert result.state.final_result == "42"

    def test_runtime_recoverable_propose_parse_error(self):
        runtime = Runtime(
            policy=ParseThenRecoverPolicy(),
            toolkit=ToolRegistry(),
            parser=ReActTextParser(),
            budget=RuntimeBudget(max_steps=3),
        )
        result = runtime.run(State(task="recover"))

        # Step 0 parse fails and is recoverable; step 1 succeeds.
        assert result.state.final_result == "42"
        assert result.state.stop_reason == "final_result"

    def test_runtime_unrecoverable_propose_error(self):
        runtime = Runtime(policy=FatalPolicy(), toolkit=ToolRegistry(), budget=RuntimeBudget(max_steps=2))
        result = runtime.run(State(task="boom"))

        assert result.state.stop_reason == "unrecoverable_error"


class TestToolRegistryContracts:
    def test_function_and_toolset_registration_and_provenance(self):
        registry = ToolRegistry()

        @tool(name="double")
        def double(x: int) -> int:
            return x * 2

        class MathPack:
            name = "math"
            version = "1.0"

            @tool(name="add")
            def add(self, a: int, b: int) -> int:
                return a + b

            def tools(self):
                return [self.add]

        registry.register(double)
        registry.register_toolset(MathPack())

        assert registry.call("double", x=21) == 42
        assert registry.call("math.add", a=40, b=2) == 42

        desc = registry.describe_tool("math.add")
        assert desc["origin"]["source"] == "toolset"
        assert desc["origin"]["toolset_name"] == "math"

    def test_tool_name_collision_rejected(self):
        registry = ToolRegistry()

        @tool(name="add")
        def add1(a: int, b: int) -> int:
            return a + b

        @tool(name="add")
        def add2(a: int, b: int) -> int:
            return a + b + 1

        registry.register(add1)
        with pytest.raises(ValueError):
            registry.register(add2)


class TestParsers:
    def test_json_decision_parser(self):
        parser = JsonDecisionParser()
        decision = parser.parse('{"mode":"final","final_answer":"42"}')
        decision.validate()
        assert decision.mode == "final"
        assert decision.final_answer == "42"

    def test_xml_decision_parser(self):
        parser = XmlDecisionParser()
        decision = parser.parse('<decision mode="act"><action name="add"><arg name="a">20</arg><arg name="b">22</arg></action></decision>')
        decision.validate()
        assert decision.mode == "act"
        assert decision.actions[0]["name"] == "add"

    def test_react_parser_malformed(self):
        parser = ReActTextParser()
        with pytest.raises(ValueError):
            parser.parse("Thought: I should do something")


class TestMemoryAdapters:
    def _run_with_memory(self, memory):
        memory.append(MemoryRecord(role="user", content="compute 40+2", step_id=0))
        memory.append(MemoryRecord(role="assistant", content="Action add", step_id=1))
        memory.append(MemoryRecord(role="tool", content="42", step_id=2))

        hits = memory.retrieve({"text": "42", "top_k": 1}) if isinstance(memory, VectorMemory) else memory.retrieve({})
        assert len(hits) >= 1
        assert isinstance(memory.summarize(max_items=2), str)
        assert isinstance(memory.evict(), int)

    def test_window_memory(self):
        self._run_with_memory(WindowMemory(window_size=10))

    def test_summary_memory(self):
        self._run_with_memory(SummaryMemory(keep_last=5))

    def test_vector_memory(self):
        self._run_with_memory(VectorMemory(top_k=2))
