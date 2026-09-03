from types import SimpleNamespace

import pytest

from qitos import Action, AgentModule, Decision, Engine, ToolRegistry, tool
from qitos.core.history import History, HistoryMessage
from qitos.core.model_response import ModelResponse
from qitos.core.state import StateSchema
from qitos.engine import RuntimeBudget
from qitos.engine.recovery import RecoveryPolicy, build_failure_report
from qitos.engine.states import StepRecord
from qitos.kit.parser import (
    JsonDecisionParser,
    MiniMaxToolCallParser,
    ReActTextParser,
    ToolUseXmlParser,
    XmlDecisionParser,
)


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


def test_native_tool_chain_removes_tool_results_without_retained_assistant_call():
    engine = Engine(agent=_ToolCallAgent(llm=None), budget=RuntimeBudget(max_steps=1))
    messages = [
        {"role": "system", "content": "System prompt"},
        {
            "role": "tool",
            "content": "stale result",
            "tool_call_id": "call_evicted",
        },
        {"role": "user", "content": "continue"},
    ]
    original_messages = [dict(message) for message in messages]

    repaired = engine._model_runtime._ensure_chain_consistency(messages)

    assert messages == original_messages
    assert repaired == [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "continue"},
    ]


def test_native_tool_chain_preserves_complete_call_and_result_pair():
    engine = Engine(agent=_ToolCallAgent(llm=None), budget=RuntimeBudget(max_steps=1))
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_complete",
                    "type": "function",
                    "function": {"name": "add", "arguments": '{"a": 20, "b": 22}'},
                }
            ],
        },
        {
            "role": "tool",
            "content": "42",
            "tool_call_id": "call_complete",
        },
    ]

    repaired = engine._model_runtime._ensure_chain_consistency(messages)

    assert repaired == messages


def test_native_tool_chain_keeps_existing_missing_result_placeholder_recovery():
    engine = Engine(agent=_ToolCallAgent(llm=None), budget=RuntimeBudget(max_steps=1))
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_interrupted",
                    "type": "function",
                    "function": {"name": "add", "arguments": '{"a": 20, "b": 22}'},
                }
            ],
        }
    ]

    repaired = engine._model_runtime._ensure_chain_consistency(messages)

    assert repaired == [
        messages[0],
        {
            "role": "tool",
            "tool_call_id": "call_interrupted",
            "content": "[Tool execution was interrupted. No result available.]",
        },
    ]


def _native_text_engine(*, parser=None, protocol="react_text_v1"):
    llm = SimpleNamespace(
        qitos_harness_metadata={
            "tool_policy": {"native_tool_call_preferred": True},
            "protocol": protocol,
        }
    )
    agent = _ToolCallAgent(llm=llm)
    if parser is not None:
        agent.model_parser = parser
    return Engine(agent=agent, budget=RuntimeBudget(max_steps=2))


@pytest.mark.parametrize(
    "response_text",
    [
        (
            "thought: inspect the workspace\n"
            "action:\n"
            "name: add\n"
            "args:\n"
            "command: pwd"
        ),
        '{"thought":"inspect","action":{"name":"add","args":{"a":1',
        "{thought: inspect, action: {name: add, args: {a: 1",
        '{"tool":"add"',
        '{"call":"add"',
        '{"command":"pwd"',
    ],
)
def test_native_text_structured_action_parse_error_stays_in_recovery(response_text):
    engine = _native_text_engine()
    record = StepRecord(step_id=0)

    decision = engine._model_runtime.normalize_decision(
        ModelResponse(text=response_text, finish_reason="stop", tool_calls=None),
        step=0,
        record=record,
    )

    assert decision.mode == "wait"
    assert decision.final_answer is None
    assert decision.meta["parser_error"] is True
    assert record.decision_source == "parser"
    assert record.parser_diagnostics["severity"] == "error"
    assert any(
        event.payload.get("stage") == "native_text_final_rejected"
        and event.payload.get("reason") == "structured_action_parse_error"
        for event in engine.events
    )


def test_native_text_plain_natural_language_still_becomes_final():
    engine = _native_text_engine()
    record = StepRecord(step_id=0)
    response_text = (
        "The requested action is complete; the tool named add returned 42."
    )

    decision = engine._model_runtime.normalize_decision(
        ModelResponse(
            text=response_text,
            finish_reason="stop",
            tool_calls=None,
        ),
        step=0,
        record=record,
    )

    assert decision.mode == "final"
    assert decision.final_answer == response_text
    assert decision.meta["decision_source"] == "native_text_final"
    assert record.decision_source == "native_text_final"


@pytest.mark.parametrize(
    "response_text",
    [
        "Command: pytest -q",
        "Call: +1 (555) 010-2000 for support.",
        "Tools: Python and pytest were used to verify the result.",
    ],
)
def test_native_text_ambiguous_labels_still_become_final(response_text):
    engine = _native_text_engine()
    record = StepRecord(step_id=0)

    decision = engine._model_runtime.normalize_decision(
        ModelResponse(text=response_text, finish_reason="stop", tool_calls=None),
        step=0,
        record=record,
    )

    assert decision.mode == "final"
    assert decision.final_answer == response_text
    assert record.decision_source == "native_text_final"


def test_native_text_tool_use_parser_heuristic_wait_keeps_legacy_final_fallback():
    engine = _native_text_engine(
        parser=ToolUseXmlParser(), protocol="tool_use_xml_v1"
    )
    record = StepRecord(step_id=0)
    response_text = "All requested checks passed successfully."

    decision = engine._model_runtime.normalize_decision(
        ModelResponse(text=response_text, finish_reason="stop", tool_calls=None),
        step=0,
        record=record,
    )

    assert decision.mode == "final"
    assert decision.final_answer == response_text
    assert record.decision_source == "native_text_final"


def test_native_text_valid_react_action_still_uses_parser():
    engine = _native_text_engine()
    record = StepRecord(step_id=0)

    decision = engine._model_runtime.normalize_decision(
        ModelResponse(
            text="Thought: calculate\nAction: add(a=20, b=22)",
            finish_reason="stop",
            tool_calls=None,
        ),
        step=0,
        record=record,
    )

    assert decision.mode == "act"
    assert decision.actions == [{"name": "add", "args": {"a": 20, "b": 22}}]
    assert record.decision_source == "parser"


def test_native_text_valid_react_final_still_uses_parser():
    engine = _native_text_engine()
    record = StepRecord(step_id=0)

    decision = engine._model_runtime.normalize_decision(
        ModelResponse(
            text="Thought: finished\nFinal Answer: 42",
            finish_reason="stop",
            tool_calls=None,
        ),
        step=0,
        record=record,
    )

    assert decision.mode == "final"
    assert decision.final_answer == "42"
    assert record.decision_source == "parser"


@pytest.mark.parametrize(
    ("parser", "protocol", "response_text"),
    [
        (
            JsonDecisionParser(),
            "json_decision_v1",
            '{"mode":"wait","thought":"Need another observation."}',
        ),
        (
            XmlDecisionParser(),
            "xml_decision_v1",
            '<decision mode="wait"><thought>Need another observation.</thought></decision>',
        ),
    ],
)
def test_native_text_explicit_parser_wait_stays_wait(
    parser, protocol, response_text
):
    engine = _native_text_engine(parser=parser, protocol=protocol)
    record = StepRecord(step_id=0)

    decision = engine._model_runtime.normalize_decision(
        ModelResponse(
            text=response_text,
            finish_reason="stop",
            tool_calls=None,
        ),
        step=0,
        record=record,
    )

    assert decision.mode == "wait"
    assert decision.meta.get("parser_error") is not True
    assert record.decision_source == "parser"


@pytest.mark.parametrize(
    ("parser", "protocol", "response_text"),
    [
        (
            MiniMaxToolCallParser(),
            "minimax_tool_call_v1",
            '<minimax:tool_call><invoke name="add"><parameter name="a">1',
        ),
        (
            ToolUseXmlParser(),
            "tool_use_xml_v1",
            "<tool_use><tool_name>add</tool_name><arguments>{\"a\": 1}",
        ),
    ],
)
def test_native_text_malformed_protocol_action_stays_in_recovery(
    parser, protocol, response_text
):
    engine = _native_text_engine(parser=parser, protocol=protocol)
    record = StepRecord(step_id=0)

    decision = engine._model_runtime.normalize_decision(
        ModelResponse(text=response_text, finish_reason="stop", tool_calls=None),
        step=0,
        record=record,
    )

    assert decision.mode == "wait"
    assert decision.meta["parser_error"] is True
    assert record.decision_source == "parser"


@pytest.mark.parametrize(
    "response_text",
    [
        '<minimax:tool_call><invoke name="add">',
        "<tool_use><tool_name>add</tool_name>",
        (
            "<|tool_calls_section_begin|><|tool_call_begin|> functions.add:0 "
            '<|tool_call_argument_begin|> {"a": 1'
        ),
        "Action add(",
    ],
)
def test_structured_action_intent_recognizes_native_protocol_markers(response_text):
    assert _native_text_engine()._model_runtime._looks_like_structured_action_intent(
        response_text
    )


def test_native_text_parse_recovery_runs_tool_then_finishes():
    malformed = (
        "thought: inspect the workspace\n"
        "action:\n"
        "name: add\n"
        "args:\n"
        "a: 20\n"
        "b: 22"
    )

    class _RecoveryModel:
        model = "native-text-recovery-model"
        qitos_harness_metadata = {
            "tool_policy": {"native_tool_call_preferred": True},
            "protocol": "react_text_v1",
        }

        def __init__(self):
            self.calls = 0

        def call_raw(self, messages):
            _ = messages
            self.calls += 1
            if self.calls == 1:
                return ModelResponse(
                    text=malformed, finish_reason="stop", tool_calls=None
                )
            if self.calls == 2:
                return ModelResponse(
                    text="",
                    finish_reason="tool_calls",
                    tool_calls=[
                        {
                            "id": "call_add",
                            "type": "function",
                            "function": {
                                "name": "add",
                                "arguments": '{"a": 20, "b": 22}',
                            },
                        }
                    ],
                )
            return ModelResponse(
                text="Final Answer: done",
                finish_reason="stop",
                tool_calls=None,
            )

    class _RecoveryAgent(_ToolCallAgent):
        def init_state(self, task: str, **kwargs):
            _ = kwargs
            return _State(task=task, max_steps=4)

        def decide(self, state: _State, observation: dict):
            _ = state, observation
            return None

    model = _RecoveryModel()
    result = Engine(
        agent=_RecoveryAgent(llm=model), budget=RuntimeBudget(max_steps=4)
    ).run("recover malformed action")

    assert model.calls == 3
    assert result.state.stop_reason == "final"
    assert result.state.final_result == "done"
    assert [record.decision.mode for record in result.records] == [
        "wait",
        "act",
        "final",
    ]
    assert [record.decision_source for record in result.records] == [
        "parser",
        "native_tool_calls",
        "parser",
    ]
    assert sum(len(record.tool_invocations) for record in result.records) == 1

def test_extract_reasoning_alias_and_fallback_when_content_is_empty():
    engine = Engine(agent=_ToolCallAgent(llm=None), budget=RuntimeBudget(max_steps=1))
    runtime = engine._model_runtime
    raw = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "reasoning": "The parser expects a byte count, so inspect the header first.",
                    "tool_calls": [],
                }
            }
        ]
    }

    response = runtime._normalize_model_response(raw)

    assert response.text == "The parser expects a byte count, so inspect the header first."
    assert response.reasoning_content == response.text
    assert response.reasoning_fields == {"reasoning": response.text}
    assert response.reasoning_source == "reasoning"


def test_reasoning_content_takes_priority_while_both_native_fields_are_preserved():
    engine = Engine(agent=_ToolCallAgent(llm=None), budget=RuntimeBudget(max_steps=1))
    runtime = engine._model_runtime
    raw = SimpleNamespace(
        message=SimpleNamespace(
            content="Use READ first.",
            reasoning_content="Canonical provider reasoning.",
            reasoning="Provider alias reasoning.",
        )
    )

    response = runtime._normalize_model_response(raw)

    assert response.text == "Use READ first."
    assert response.reasoning_content == "Canonical provider reasoning."
    assert response.reasoning_source == "reasoning_content"
    assert response.reasoning_fields == {
        "reasoning_content": "Canonical provider reasoning.",
        "reasoning": "Provider alias reasoning.",
    }
    summary = response.to_summary_dict()
    assert summary["reasoning"] == {
        "present": True,
        "source": "reasoning_content",
        "field_names": ["reasoning", "reasoning_content"],
    }
    assert "Canonical provider reasoning." not in repr(summary)
    assert "Provider alias reasoning." not in repr(summary)


def test_agent_thought_text_is_not_native_reasoning():
    engine = Engine(agent=_ToolCallAgent(llm=None), budget=RuntimeBudget(max_steps=1))
    runtime = engine._model_runtime
    response = runtime._normalize_model_response(
        {"content": '{"thought":"inspect repo-vul"}'}
    )

    assert response.reasoning_content is None
    assert response.reasoning_fields == {}
