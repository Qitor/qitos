from dataclasses import dataclass, field
from typing import Any

from qitos import Action, AgentModule, Decision, Engine, RuntimeBudget, StateSchema, ToolRegistry, tool
from qitos.kit.memory import WindowMemory
from qitos.kit.parser import ReActTextParser
from qitos.core.memory import Memory, MemoryRecord


@dataclass
class DemoState(StateSchema):
    logs: list[str] = field(default_factory=list)


class DemoAgent(AgentModule[DemoState, dict[str, Any], Action]):
    def __init__(self):
        registry = ToolRegistry()

        @tool(name="add")
        def add(a: int, b: int) -> int:
            return a + b

        registry.register(add)
        super().__init__(tool_registry=registry)

    def init_state(self, task: str, **kwargs: Any) -> DemoState:
        return DemoState(task=task, max_steps=3)

    def build_memory_query(self, state: DemoState, runtime_view: dict[str, Any]) -> dict[str, Any] | None:
        return {"max_items": 4}

    def decide(self, state: DemoState, observation: dict[str, Any]) -> Decision[Action]:
        if state.current_step == 0:
            return Decision.act(actions=[Action(name="add", args={"a": 19, "b": 23})], rationale="use tool")
        return Decision.final("42")

    def reduce(
        self,
        state: DemoState,
        observation: dict[str, Any],
        decision: Decision[Action],
    ) -> DemoState:
        action_results = observation.get("action_results", []) if isinstance(observation, dict) else []
        if action_results:
            state.logs.append(str(action_results[0]))
        return state


def test_engine_happy_path():
    result = Engine(agent=DemoAgent(), budget=RuntimeBudget(max_steps=3)).run("compute")
    assert result.state.final_result == "42"
    assert result.state.stop_reason == "final"
    assert result.records[0].action_results == [42]


def test_agent_run_shortcut():
    agent = DemoAgent()
    assert agent.run("compute") == "42"


def test_engine_injects_memory_context_into_env_view():
    agent = DemoAgent()
    result = Engine(agent=agent, budget=RuntimeBudget(max_steps=3), memory=WindowMemory(window_size=20)).run("compute")
    assert result.state.final_result == "42"
    assert hasattr(agent, "memory")
    assert agent.memory is not None


def test_engine_default_model_decide_with_prepare():
    seen_messages: list[dict[str, str]] = []

    class _DummyModel:
        def __call__(self, messages):
            seen_messages.extend(messages)
            return "Action: add(a=20, b=22)"

    class LLMDrivenDemo(DemoAgent):
        def __init__(self):
            super().__init__()
            self.llm = _DummyModel()
            self.model_parser = ReActTextParser()

        def build_system_prompt(self, state: DemoState) -> str | None:
            return "System prompt"

        def prepare(self, state: DemoState) -> str:
            return f"Task={state.task} Step={state.current_step}"

        def decide(self, state: DemoState, observation: dict[str, Any]):
            if state.current_step == 0:
                return None
            return Decision.final("42")

    result = Engine(agent=LLMDrivenDemo(), budget=RuntimeBudget(max_steps=3)).run("compute")
    assert result.state.final_result == "42"
    assert len(seen_messages) == 2
    assert seen_messages[0]["role"] == "system"
    assert seen_messages[1]["role"] == "user"


def test_engine_uses_memory_retrieved_messages_for_next_llm_call():
    calls: list[list[dict[str, str]]] = []

    class _DummyModel:
        def __call__(self, messages):
            calls.append(list(messages))
            return "Action: add(a=1, b=1)"

    class MultiTurnLLMDemo(DemoAgent):
        def __init__(self):
            super().__init__()
            self.llm = _DummyModel()
            self.model_parser = ReActTextParser()

        def build_system_prompt(self, state: DemoState) -> str | None:
            return "System prompt"

        def prepare(self, state: DemoState) -> str:
            return f"Task={state.task} Step={state.current_step}"

        def decide(self, state: DemoState, observation: dict[str, Any]):
            if state.current_step < 2:
                return None
            return Decision.final("42")

    result = Engine(
        agent=MultiTurnLLMDemo(),
        budget=RuntimeBudget(max_steps=4),
        memory=WindowMemory(window_size=50),
    ).run("compute")
    assert result.state.final_result == "42"
    assert len(calls) == 2
    assert calls[0][0]["role"] == "system"
    assert calls[0][-1]["role"] == "user"
    # second call should include history from memory (previous user+assistant)
    assert len(calls[1]) >= 4
    assert calls[1][1]["role"] == "user"
    assert calls[1][2]["role"] == "assistant"


def test_engine_uses_memory_retrieve_messages_contract():
    class ContractMemory(Memory):
        def __init__(self):
            self._records: list[MemoryRecord] = []
            self.retrieve_messages_called = 0

        def append(self, record: MemoryRecord) -> None:
            self._records.append(record)

        def retrieve(self, query=None, state=None, observation=None):
            return []

        def retrieve_messages(self, state=None, observation=None, query=None):
            self.retrieve_messages_called += 1
            return [{"role": "assistant", "content": "history_hint"}]

        def summarize(self, max_items: int = 5) -> str:
            return ""

        def evict(self) -> int:
            return 0

        def reset(self, run_id=None) -> None:
            self._records = []

    seen_messages: list[dict[str, str]] = []

    class _DummyModel:
        def __call__(self, messages):
            seen_messages.extend(messages)
            return "Final Answer: 42"

    class LLMOnceAgent(DemoAgent):
        def __init__(self):
            super().__init__()
            self.llm = _DummyModel()
            self.model_parser = ReActTextParser()

        def build_system_prompt(self, state: DemoState) -> str | None:
            return "System prompt"

        def prepare(self, state: DemoState) -> str:
            return "solve"

        def decide(self, state: DemoState, observation: dict[str, Any]):
            return None

    mem = ContractMemory()
    result = Engine(agent=LLMOnceAgent(), budget=RuntimeBudget(max_steps=2), memory=mem).run("compute")
    assert result.state.final_result == "42"
    assert mem.retrieve_messages_called >= 1
    assert any(m.get("content") == "history_hint" for m in seen_messages)
