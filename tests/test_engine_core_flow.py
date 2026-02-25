from dataclasses import dataclass, field
from typing import Any

from qitos import Action, AgentModule, Decision, Engine, HistoryPolicy, RuntimeBudget, StateSchema, ToolRegistry, tool
from qitos.core.history import History, HistoryMessage
from qitos.kit.memory import WindowMemory
from qitos.kit.history import WindowHistory
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
    agent.memory = WindowMemory(window_size=20)
    result = Engine(agent=agent, budget=RuntimeBudget(max_steps=3)).run("compute")
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


def test_engine_uses_history_messages_for_next_llm_call():
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

    agent = MultiTurnLLMDemo()
    agent.history = WindowHistory(window_size=50)
    result = Engine(
        agent=agent,
        budget=RuntimeBudget(max_steps=4),
        history_policy=HistoryPolicy(max_messages=4),
    ).run("compute")
    assert result.state.final_result == "42"
    assert len(calls) == 2
    assert calls[0][0]["role"] == "system"
    assert calls[0][-1]["role"] == "user"
    # second call should include history (previous user+assistant)
    assert len(calls[1]) >= 4
    assert calls[1][1]["role"] == "user"
    assert calls[1][2]["role"] == "assistant"


def test_engine_uses_history_retrieve_contract():
    class ContractHistory(History):
        def __init__(self):
            self._messages: list[HistoryMessage] = []
            self.retrieve_called = 0

        def append(self, message: HistoryMessage) -> None:
            self._messages.append(message)

        def retrieve(self, query=None, state=None, observation=None):
            self.retrieve_called += 1
            return [{"role": "assistant", "content": "history_hint"}]

        def summarize(self, max_items: int = 5) -> str:
            return ""

        def evict(self) -> int:
            return 0

        def reset(self, run_id=None) -> None:
            self._messages = []

    class ContractMemory(Memory):
        def __init__(self):
            self._records: list[MemoryRecord] = []
            self.retrieve_called = 0

        def append(self, record: MemoryRecord) -> None:
            self._records.append(record)

        def retrieve(self, query=None, state=None, observation=None):
            self.retrieve_called += 1
            return []

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
    hist = ContractHistory()
    agent = LLMOnceAgent()
    agent.memory = mem
    agent.history = hist
    result = Engine(agent=agent, budget=RuntimeBudget(max_steps=2)).run("compute")
    assert result.state.final_result == "42"
    assert hist.retrieve_called >= 1
    assert mem.retrieve_called == 0
    assert any(m.get("content") == "history_hint" for m in seen_messages)


def test_memory_and_history_streams_are_strictly_separated():
    class CaptureMemory(Memory):
        def __init__(self):
            self.records: list[MemoryRecord] = []

        def append(self, record: MemoryRecord) -> None:
            self.records.append(record)

        def retrieve(self, query=None, state=None, observation=None):
            return list(self.records)

        def summarize(self, max_items: int = 5) -> str:
            return ""

        def evict(self) -> int:
            return 0

        def reset(self, run_id=None) -> None:
            self.records = []

    class CaptureHistory(History):
        def __init__(self):
            self.messages: list[HistoryMessage] = []

        def append(self, message: HistoryMessage) -> None:
            self.messages.append(message)

        def retrieve(self, query=None, state=None, observation=None):
            return list(self.messages)

        def summarize(self, max_items: int = 5) -> str:
            return ""

        def evict(self) -> int:
            return 0

        def reset(self, run_id=None) -> None:
            self.messages = []

    class _DummyModel:
        def __call__(self, messages):
            return "Final Answer: ok"

    class OneShotLLMAgent(DemoAgent):
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

    mem = CaptureMemory()
    hist = CaptureHistory()
    agent = OneShotLLMAgent()
    agent.memory = mem
    agent.history = hist
    result = Engine(agent=agent, budget=RuntimeBudget(max_steps=2)).run("compute")
    assert result.state.stop_reason == "final"

    mem_roles = {r.role for r in mem.records}
    assert {"task", "state", "decision", "next_state", "observation"}.issubset(mem_roles)
    assert "message" not in mem_roles

    hist_roles = [m.role for m in hist.messages]
    assert "user" in hist_roles
    assert "assistant" in hist_roles
