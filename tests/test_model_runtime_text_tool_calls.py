from types import SimpleNamespace

from qitos import Action, AgentModule, Decision, Engine, ToolRegistry, tool
from qitos.core.history import History, HistoryMessage
from qitos.core.state import StateSchema
from qitos.engine import RuntimeBudget
from qitos.engine.recovery import RecoveryPolicy, build_failure_report
from qitos.kit.parser import JsonDecisionParser, ReActTextParser


class _HistoryCapture(History):
    def __init__(self):
        self.messages: list[HistoryMessage] = []

    def append(self, message: HistoryMessage) -> None:
        self.messages.append(message)

    def retrieve(self, query=None, state=None, observation=None):
        _ = query, state, observation
        return list(self.messages)

    def summarize(self, max_items: int = 5) -> str:
        _ = max_items
        return ""

    def evict(self) -> int:
        return 0

    def reset(self, run_id=None) -> None:
        _ = run_id
        self.messages = []


class _State(StateSchema):
    pass


class _ToolCallAgent(AgentModule[_State, dict, Action]):
    def __init__(self, llm):
        registry = ToolRegistry()

        @tool(name="add")
        def add(a: int, b: int) -> int:
            return a + b

        registry.register(add)
        super().__init__(tool_registry=registry, llm=llm)
        self.model_parser = ReActTextParser()
        self.history = _HistoryCapture()

    def init_state(self, task: str, **kwargs):
        _ = kwargs
        return _State(task=task, max_steps=2)

    def build_system_prompt(self, state: _State):
        _ = state
        return "System prompt"

    def prepare(self, state: _State) -> str:
        _ = state
        return "solve"

    def decide(self, state: _State, observation: dict):
        _ = observation
        if state.current_step > 0:
            return Decision.final("done")
        return None

    def reduce(self, state: _State, observation: dict, decision: Decision[Action]):
        _ = observation, decision
        return state


def test_extract_response_text_preserves_object_message_content_when_tool_calls_exist():
    engine = Engine(agent=_ToolCallAgent(llm=None), budget=RuntimeBudget(max_steps=1))
    runtime = engine._model_runtime
    raw = SimpleNamespace(
        message=SimpleNamespace(
            content="Conclusion: likely 1-byte trigger. Next: write and submit.",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "add", "arguments": '{"a": 20, "b": 22}'},
                }
            ],
        )
    )

    text = runtime._extract_response_text(raw)

    assert text == "Conclusion: likely 1-byte trigger. Next: write and submit."


def test_extract_response_text_uses_reasoning_content_when_content_is_empty():
    engine = Engine(agent=_ToolCallAgent(llm=None), budget=RuntimeBudget(max_steps=1))
    runtime = engine._model_runtime
    raw = SimpleNamespace(
        message=SimpleNamespace(
            content=None,
            reasoning_content="Conclusion: the checksum logic is the trigger. Next: write a candidate.",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "add", "arguments": '{"a": 20, "b": 22}'},
                }
            ],
        )
    )

    text = runtime._extract_response_text(raw)

    assert text == "Conclusion: the checksum logic is the trigger. Next: write a candidate."


def test_extract_response_text_returns_empty_for_null_message_without_tool_calls():
    engine = Engine(agent=_ToolCallAgent(llm=None), budget=RuntimeBudget(max_steps=1))
    runtime = engine._model_runtime
    object_raw = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=None, tool_calls=None),
                finish_reason="stop",
            )
        ]
    )
    dict_raw = {
        "choices": [
            {
                "message": {"content": None, "tool_calls": None},
                "finish_reason": "stop",
            }
        ]
    }

    assert runtime._extract_response_text(object_raw) == ""
    assert runtime._extract_response_text(dict_raw) == ""


def test_empty_model_response_uses_bounded_model_recovery():
    class _EmptyResponseModel:
        model = "empty-response-model"
        provider = "deterministic-fake"

        def __init__(self):
            self.calls = 0

        def call_raw(self, messages):
            _ = messages
            self.calls += 1
            return {
                "choices": [
                    {
                        "message": {"content": None, "tool_calls": None},
                        "finish_reason": "length",
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 8192,
                    "total_tokens": 8292,
                },
            }

    class _TrackingJsonParser(JsonDecisionParser):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def parse(self, raw_output, context=None):
            self.calls += 1
            return super().parse(raw_output, context=context)

    class _EmptyResponseAgent(_ToolCallAgent):
        def __init__(self, llm, parser):
            super().__init__(llm=llm)
            self.model_parser = parser

        def init_state(self, task: str, **kwargs):
            _ = kwargs
            return _State(task=task, max_steps=3)

        def decide(self, state: _State, observation: dict):
            _ = state, observation
            return None

    model = _EmptyResponseModel()
    parser = _TrackingJsonParser()
    policy = RecoveryPolicy()
    result = Engine(
        agent=_EmptyResponseAgent(model, parser),
        budget=RuntimeBudget(max_steps=3),
        recovery_policy=policy,
    ).run("reproduce empty response")

    assert model.calls == 2
    assert parser.calls == 0
    assert result.state.stop_reason == "unrecoverable_error"
    assert result.step_count == 2
    assert [record.model_response["finish_reason"] for record in result.records] == [
        "length",
        "length",
    ]
    assert [record.model_response["usage"] for record in result.records] == [
        {
            "prompt_tokens": 100,
            "completion_tokens": 8192,
            "total_tokens": 8292,
        },
        {
            "prompt_tokens": 100,
            "completion_tokens": 8192,
            "total_tokens": 8292,
        },
    ]
    failure_report = build_failure_report(policy, result.state.stop_reason)
    assert failure_report["failure_count"] == 2
    assert [item["category"] for item in failure_report["failures"]] == [
        "model_error",
        "model_error",
    ]
    assert [item["decision"] for item in failure_report["failures"]] == [
        "continue",
        "stop",
    ]


def test_agent_interpretation_can_handle_empty_model_response():
    class _EmptyResponseModel:
        model = "empty-response-model"

        def call_raw(self, messages):
            _ = messages
            return {
                "choices": [
                    {
                        "message": {"content": None, "tool_calls": None},
                        "finish_reason": "stop",
                    }
                ]
            }

    class _NeverParser:
        def parse(self, raw_output, context=None):
            _ = raw_output, context
            raise AssertionError("agent interpretation should bypass the parser")

    class _InterpretingAgent(_ToolCallAgent):
        def __init__(self):
            super().__init__(llm=_EmptyResponseModel())
            self.model_parser = _NeverParser()

        def decide(self, state: _State, observation: dict):
            _ = state, observation
            return None

        def interpret_model_response(self, state, observation, response):
            _ = state, observation
            assert response.text == ""
            assert response.finish_reason == "stop"
            return Decision.final("handled by agent")

        def reduce(self, state, observation, decision):
            _ = observation
            state.set_stop("final", decision.final_answer)
            return state

    result = Engine(
        agent=_InterpretingAgent(), budget=RuntimeBudget(max_steps=1)
    ).run("handle provider metadata")

    assert result.state.stop_reason == "final"
    assert result.state.final_result == "handled by agent"
    assert result.records[0].model_response["text"] == ""


def test_native_tool_call_history_keeps_assistant_text_and_tool_calls():
    class _ObjectResponseModel:
        model = "demo-model"
        qitos_harness_metadata = {
            "tool_policy": {"native_tool_call_preferred": True}
        }

        def __call__(self, messages):
            _ = messages
            return SimpleNamespace(
                message=SimpleNamespace(
                    content="Conclusion: likely 1-byte trigger. Next: use add.",
                    tool_calls=[
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "add", "arguments": '{"a": 20, "b": 22}'},
                        }
                    ],
                ),
                finish_reason="tool_calls",
            )

    agent = _ToolCallAgent(llm=_ObjectResponseModel())
    result = Engine(agent=agent, budget=RuntimeBudget(max_steps=2)).run("compute")

    assert result.state.final_result == "done"
    assistant_messages = [m for m in agent.history.messages if m.role == "assistant"]
    assert assistant_messages
    first = assistant_messages[0]
    assert first.content == "Conclusion: likely 1-byte trigger. Next: use add."
    assert first.tool_calls
    assert first.tool_calls[0]["function"]["name"] == "add"
