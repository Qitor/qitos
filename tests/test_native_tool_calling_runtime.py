from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qitos import (
    Action,
    AgentModule,
    Decision,
    Engine,
    Observation,
    StateSchema,
    ToolRegistry,
    tool,
)
from qitos.core.model_response import ModelResponse
from qitos.engine import RuntimeBudget
from qitos.kit import ReActTextParser


def test_loop_block_closes_native_tool_batch_before_next_request():

    class RepeatingModel:
        qitos_harness_metadata = {"protocol": "json_decision_multi_v1"}

        def __init__(self):
            self.calls = 0

        def call_raw(self, messages, **options):
            self.calls += 1
            if self.calls > 4:
                self.final_messages = messages
                return {"choices": [{"message": {"content": "Final Answer: done"}}]}
            return {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": f"repeat_{self.calls}",
                                    "type": "function",
                                    "function": {
                                        "name": "weird_tool",
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        }
                    }
                ]
            }

    class RepeatingAgent(_NativeToolAgent):
        def __init__(self, model):
            registry = ToolRegistry()

            @tool(name="weird_tool")
            def repeated():
                return {"value": "unchanged"}

            registry.register(repeated)
            AgentModule.__init__(
                self,
                llm=model,
                tool_registry=registry,
                model_protocol="json_decision_multi_v1",
            )

        def init_state(self, task, **kwargs):
            return _State(task=task, max_steps=6)

    model = RepeatingModel()
    result = (
        Engine(RepeatingAgent(model), budget=RuntimeBudget(max_steps=6))
        .session("repeat safely")
        .run()
    )
    assert result.state.final_result == "done"
    assert model.calls == 5
    assert result.records[3].action_results[0].error_code == "tool_call_loop_detected"
    assert any(item.get("tool_call_id") == "repeat_4" for item in model.final_messages)


def test_required_before_final_rejects_early_text_and_then_allows_final(
    tmp_path: Path,
) -> None:
    from qitos.config import (
        AgentConfig,
        BudgetConfig,
        EnvironmentConfig,
        RuntimeConfig,
        build_agent_composition,
    )
    from qitos.kit.env import HostEnv

    (tmp_path / "fact.txt").write_text("verified\n", encoding="utf-8")

    class PolicyModel:
        model = "policy-model"
        qitos_harness_metadata = {"protocol": "json_decision_v1"}

        def __init__(self) -> None:
            self.options: list[dict[str, Any]] = []

        def call_raw(
            self, messages: list[dict[str, Any]], **options: Any
        ) -> dict[str, Any]:
            _ = messages
            self.options.append(dict(options))
            if len(self.options) == 1:
                return {"choices": [{"message": {"content": "too early"}}]}
            if len(self.options) == 2:
                return {
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "read-policy",
                                        "type": "function",
                                        "function": {
                                            "name": "read_file",
                                            "arguments": '{"path":"fact.txt"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            return {"choices": [{"message": {"content": "verified final"}}]}

    model = PolicyModel()
    config = AgentConfig(
        name="policy-agent",
        protocol="json_decision_v1",
        parser="auto",
        tool_preset="env_coding",
        tool_use_policy="required_before_final",
        runtime=RuntimeConfig(
            environment=EnvironmentConfig(
                type="unsafe_host",
                image="",
                workspace=str(tmp_path),
                container_workspace="",
                network="host",
                read_only_root=False,
                cap_drop=False,
                no_new_privileges=False,
                pids_limit=None,
                memory_mb=None,
                cpus=None,
                cleanup_required=False,
            )
        ),
        budgets=BudgetConfig(max_steps=5),
    )
    composition = build_agent_composition(
        config,
        model_override=model,
        env_override=HostEnv(workspace_root=str(tmp_path)),
    )
    try:
        result = composition.engine.run("read the fact and finish")
    finally:
        composition.close()

    assert result.state.final_result == "verified final"
    assert result.tool_calls_by_name == {"read_file": 1}
    assert model.options[0]["tool_choice"] == "required"
    assert model.options[1]["tool_choice"] == "required"
    assert "tool_choice" not in model.options[2]
    assert any(
        event.payload.get("stage") == "tool_use_policy_rejected"
        and event.payload.get("code") == "tool_use_policy_violation"
        for event in result.events
    )


def test_malformed_native_tool_call_is_typed_and_not_text_fallback() -> None:
    class MalformedModel:
        model = "malformed-model"
        qitos_harness_metadata = {"protocol": "json_decision_v1"}

        def call_raw(self, messages: object, **options: object) -> dict[str, Any]:
            _ = messages, options
            return {
                "choices": [
                    {
                        "message": {
                            "content": "I called it successfully",
                            "tool_calls": [
                                {
                                    "id": "bad",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": "[not-an-object]",
                                    },
                                }
                            ],
                        }
                    }
                ]
            }

    engine = Engine(
        agent=_NativeToolAgent(llm=MalformedModel()),
        budget=RuntimeBudget(max_steps=1),
        protocol="json_decision_v1",
    )
    result = engine.run("malformed")

    assert result.state.final_result in {None, ""}
    assert any(
        event.payload.get("stage") == "native_tool_call_rejected"
        and event.payload.get("reason") == "malformed_structured_response"
        for event in result.events
    )


def test_required_native_tool_call_reports_provider_capability_loss() -> None:
    class TextOnlyModel:
        model = "text-only"
        qitos_harness_metadata = {
            "tool_policy": {"native_tool_call_preferred": True},
            "protocol": "react_text_v1",
        }

        def call_raw(self, messages: object, **options: object) -> dict[str, Any]:
            _ = messages, options
            return {"choices": [{"message": {"content": "Final Answer: guessed"}}]}

    agent = _NativeToolAgent(llm=TextOnlyModel())
    agent.config.update(
        {
            "native_tool_calls_required": True,
            "tool_use_policy": "required_for_next_decision",
        }
    )
    result = Engine(
        agent=agent,
        budget=RuntimeBudget(max_steps=1),
        protocol="react_text_v1",
    ).run("native required")

    assert result.state.final_result in {None, ""}
    assert any(
        event.payload.get("stage") == "native_tool_call_required"
        and event.payload.get("code") == "provider_capability_loss"
        for event in result.events
    )


from qitos.models._openai_responses import _to_responses_input


@dataclass
class _State(StateSchema):
    pass


class _NativeToolModel:
    model = "test-native"
    max_tokens = 256
    context_window = 8192

    def __init__(self):
        self.calls = 0
        self.seen_messages: list[list[dict[str, Any]]] = []
        self.qitos_harness_metadata = {
            "tool_policy": {"native_tool_call_preferred": True},
            "parser": "ReActTextParser",
            "protocol": "react_text_v1",
        }

    def call_raw(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        self.seen_messages.append(list(messages))
        if self.calls == 0:
            self.calls += 1
            return {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_native_1",
                                    "type": "function",
                                    "function": {
                                        "name": "weird_tool",
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        self.calls += 1
        return {"choices": [{"message": {"content": "Final Answer: done"}}]}


class _NativeToolAgent(AgentModule[_State, Observation, Action]):
    def __init__(self, llm: Any):
        registry = ToolRegistry()

        @tool(name="weird_tool")
        def weird_tool() -> dict[str, Any]:
            return {"payload": {1, 2}}

        registry.register(weird_tool)
        super().__init__(
            tool_registry=registry, llm=llm, model_parser=ReActTextParser()
        )

    def init_state(self, task: str, **kwargs: Any) -> _State:
        return _State(task=task, max_steps=3)

    def decide(
        self, state: _State, observation: Observation
    ) -> Decision[Action] | None:
        _ = state
        _ = observation
        return None

    def reduce(
        self, state: _State, observation: Observation, decision: Decision[Action]
    ) -> _State:
        _ = observation
        _ = decision
        return state


class _HarnessAwareModel:
    def __init__(self):
        self.qitos_harness_metadata = {
            "parser": "ReActTextParser",
            "protocol": "react_text_v1",
        }

    def __call__(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        _ = messages
        _ = kwargs
        return "Final Answer: auto harness parser worked"


class _HarnessAgent(AgentModule[_State, Observation, Action]):
    def __init__(self):
        super().__init__(llm=_HarnessAwareModel())

    def init_state(self, task: str, **kwargs: Any) -> _State:
        _ = kwargs
        return _State(task=task, max_steps=2)

    def decide(
        self, state: _State, observation: Observation
    ) -> Decision[Action] | None:
        _ = state
        _ = observation
        return None

    def reduce(
        self, state: _State, observation: Observation, decision: Decision[Action]
    ) -> _State:
        _ = observation
        _ = decision
        return state


def test_native_tool_chain_reports_non_json_result_as_typed_contract_failure() -> None:
    llm = _NativeToolModel()
    agent = _NativeToolAgent(llm=llm)
    result = Engine(agent=agent, budget=RuntimeBudget(max_steps=3)).run("native")
    assert result.state.final_result == "done"
    assert len(llm.seen_messages) >= 2
    second_call = llm.seen_messages[1]
    assistant_msgs = [msg for msg in second_call if msg.get("role") == "assistant"]
    tool_msgs = [msg for msg in second_call if msg.get("role") == "tool"]
    assert assistant_msgs
    assert tool_msgs
    assert assistant_msgs[-1].get("tool_calls")
    assert tool_msgs[-1].get("tool_call_id") == "call_native_1"
    tool_content = str(tool_msgs[-1].get("content", ""))
    assert "non_serializable_value" in tool_content
    assert "{1, 2, 3}" not in tool_content


def test_default_history_window_never_sends_orphan_parallel_tool_results() -> None:
    class _VariableNativeToolModel:
        model = "test-variable-native"
        max_tokens = 256
        context_window = 8192
        qitos_harness_metadata = {
            "tool_policy": {"native_tool_call_preferred": True},
            "parser": "ReActTextParser",
            "protocol": "react_text_v1",
        }

        def __init__(self) -> None:
            self.calls = 0
            self.orphan_ids_by_call: list[list[str]] = []

        def call_raw(
            self, messages: list[dict[str, Any]], **kwargs: Any
        ) -> dict[str, Any]:
            _ = kwargs
            assistant_ids = {
                str(tool_call["id"])
                for message in messages
                if message.get("role") == "assistant"
                for tool_call in message.get("tool_calls", [])
                if isinstance(tool_call, dict) and tool_call.get("id")
            }
            tool_result_ids = {
                str(message["tool_call_id"])
                for message in messages
                if message.get("role") == "tool" and message.get("tool_call_id")
            }
            self.orphan_ids_by_call.append(sorted(tool_result_ids - assistant_ids))

            call_index = self.calls
            self.calls += 1
            if call_index >= 8:
                return {"choices": [{"message": {"content": "Final Answer: done"}}]}

            tool_call_count = 3 if call_index == 0 else 1
            return {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": f"call_{call_index}_{offset}",
                                    "type": "function",
                                    "function": {
                                        "name": "probe",
                                        "arguments": (
                                            '{"value": %d}' % (call_index * 10 + offset)
                                        ),
                                    },
                                }
                                for offset in range(tool_call_count)
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }

    class _VariableNativeToolAgent(AgentModule[_State, Observation, Action]):
        def __init__(self, llm: Any):
            registry = ToolRegistry()

            @tool(name="probe")
            def probe(value: int) -> dict[str, int]:
                return {"value": value}

            registry.register(probe)
            super().__init__(
                tool_registry=registry,
                llm=llm,
                model_parser=ReActTextParser(),
            )

        def init_state(self, task: str, **kwargs: Any) -> _State:
            _ = kwargs
            return _State(task=task, max_steps=12)

        def prepare(self, state: _State) -> str:
            return f"continue step {state.current_step}"

        def decide(
            self, state: _State, observation: Observation
        ) -> Decision[Action] | None:
            _ = state, observation
            return None

        def reduce(
            self,
            state: _State,
            observation: Observation,
            decision: Decision[Action],
        ) -> _State:
            _ = observation, decision
            return state

    llm = _VariableNativeToolModel()
    result = Engine(
        agent=_VariableNativeToolAgent(llm),
        budget=RuntimeBudget(max_steps=12),
    ).run("exercise variable native tool rounds")

    assert result.state.final_result == "done"
    assert llm.calls == 9
    assert llm.orphan_ids_by_call == [[] for _ in range(9)]
    model_input_messages = [
        event.payload["messages"]
        for event in result.events
        if event.payload.get("stage") == "model_input"
    ]
    assert len(model_input_messages) == 9
    for messages in model_input_messages:
        assistant_ids = {
            str(tool_call["id"])
            for message in messages
            if message.get("role") == "assistant"
            for tool_call in message.get("tool_calls", [])
            if isinstance(tool_call, dict) and tool_call.get("id")
        }
        tool_result_ids = {
            str(message["tool_call_id"])
            for message in messages
            if message.get("role") == "tool" and message.get("tool_call_id")
        }
        assert tool_result_ids <= assistant_ids


def test_responses_native_items_survive_engine_tool_round() -> None:
    class _ResponsesNativeModel(_NativeToolModel):
        def call_raw(
            self, messages: list[dict[str, Any]], **kwargs: Any
        ) -> ModelResponse:
            _ = kwargs
            self.seen_messages.append(list(messages))
            if self.calls == 0:
                self.calls += 1
                return ModelResponse(
                    text="",
                    tool_calls=[
                        {
                            "id": "call_native_1",
                            "type": "function",
                            "function": {
                                "name": "weird_tool",
                                "arguments": "{}",
                            },
                        }
                    ],
                    native_items=[
                        {
                            "type": "reasoning",
                            "id": "reasoning_1",
                            "summary": [],
                        },
                        {
                            "type": "function_call",
                            "id": "function_1",
                            "call_id": "call_native_1",
                            "name": "weird_tool",
                            "arguments": "{}",
                        },
                    ],
                )
            self.calls += 1
            return ModelResponse(text="Final Answer: done")

    llm = _ResponsesNativeModel()
    result = Engine(
        agent=_NativeToolAgent(llm=llm),
        budget=RuntimeBudget(max_steps=3),
    ).run("native responses")

    assert result.state.final_result == "done"
    replay_items = _to_responses_input(llm.seen_messages[1])
    replay_types = [item.get("type") for item in replay_items]
    reasoning_index = replay_types.index("reasoning")
    assert replay_types[reasoning_index : reasoning_index + 3] == [
        "reasoning",
        "function_call",
        "function_call_output",
    ]
    assert replay_items[reasoning_index + 2]["call_id"] == "call_native_1"


def test_agent_run_auto_applies_harness_parser_defaults() -> None:
    agent = _HarnessAgent()
    output = agent.run("auto-parser", trace=False, render=False)
    assert output == "auto harness parser worked"
