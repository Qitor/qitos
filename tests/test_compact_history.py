from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from qitos import (
    Action,
    AgentModule,
    Decision,
    Engine,
    HistoryPolicy,
    StateSchema,
    ToolRegistry,
    tool,
)
from qitos.engine import RuntimeBudget
from qitos.kit.history import CompactHistory, MessageGrouper
from qitos.kit.parser import ReActTextParser


def test_message_grouper_prefers_step_rounds() -> None:
    from qitos.core.history import HistoryMessage

    grouper = MessageGrouper()
    groups = grouper.group(
        [
            HistoryMessage(role="system", content="s0", step_id=0),
            HistoryMessage(role="user", content="u0", step_id=0),
            HistoryMessage(role="assistant", content="a0", step_id=0),
            HistoryMessage(role="user", content="u1", step_id=1),
            HistoryMessage(role="assistant", content="a1", step_id=1),
        ]
    )

    assert len(groups) == 2
    assert [len(group) for group in groups] == [3, 2]
    assert [msg.step_id for msg in groups[-1]] == [1, 1]


def test_compact_history_keeps_active_native_tool_round_atomic() -> None:
    from qitos.core.history import HistoryMessage

    history = CompactHistory(
        max_tokens=1,
        keep_last_messages=1,
        auto_compact=True,
    )
    history.append(HistoryMessage(role="user", content="old", step_id=0))
    history.append(
        HistoryMessage(
            role="assistant",
            content=None,
            step_id=1,
            native_items=[
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "lookup",
                    "arguments": "{}",
                }
            ],
        )
    )
    history.append(
        HistoryMessage(
            role="tool",
            content="result",
            step_id=1,
            tool_call_id="call_1",
        )
    )

    retrieved = history.retrieve({"max_tokens": 1, "auto_compact": True})

    assert [message.role for message in retrieved[-2:]] == ["assistant", "tool"]
    assert retrieved[-2].native_items[0]["call_id"] == "call_1"


def test_compact_history_emits_microcompact_and_summary_events() -> None:
    from qitos.core.history import HistoryMessage

    history = CompactHistory(
        max_tokens=90, keep_last_rounds=1, keep_last_messages=4, hard_window=20
    )
    for idx in range(6):
        role = "user" if idx % 2 == 0 else "assistant"
        history.append(
            HistoryMessage(
                role=role,
                content=(f"message {idx} " + "with verbose context " * 80).strip(),
                step_id=idx,
                metadata={"source": "engine"},
            )
        )

    retrieved = history.retrieve(
        query={
            "roles": ["user", "assistant"],
            "max_items": 12,
            "max_tokens": 90,
            "pending_content": "next prompt with another long continuation",
        }
    )
    events = history.consume_runtime_events()
    metadata = history.get_last_message_metadata()

    assert retrieved
    assert retrieved[0].metadata.get("summary") is True
    assert any(
        event.get("stage") == "context_history"
        and (event.get("context") or {}).get("stage") == "warning"
        for event in events
    )
    assert any(
        event.get("stage") == "context_history"
        and (event.get("context") or {}).get("stage") == "microcompact_applied"
        for event in events
    )
    assert any(
        event.get("stage") == "context_history"
        and (event.get("context") or {}).get("stage") == "summary_compact_applied"
        for event in events
    )
    assert metadata[0].get("summary") is True
    assert metadata[0].get("source") == "compact_history"


class _RecordingSummaryLLM:
    """Capture every summary request and hand back a numbered summary."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def __call__(self, messages: list[dict[str, Any]]) -> str:
        self.prompts.append(str(messages[-1]["content"]))
        return f"SUMMARY_{len(self.prompts)}"


def _numbered_history(
    count: int, *, llm: Any = None, chars: int = 200
) -> tuple[Any, Any]:
    from qitos.core.history import HistoryMessage
    from qitos.kit.history.compact_history import CompactConfig

    config = CompactConfig(
        max_tokens=200,
        keep_last_rounds=2,
        keep_last_messages=8,
        compact_long_messages_over_chars=10,
        auto_compact=True,
    )
    history = CompactHistory(llm=llm, config=config)
    for idx in range(count):
        history.append(
            HistoryMessage(
                role="user" if idx % 2 == 0 else "assistant",
                content=f"ITEM_{idx:02d} " + "x" * chars,
                step_id=idx,
            )
        )
    return history, config


def test_summary_input_covers_full_prefix_including_earliest() -> None:
    """Regression for #36: the replaced prefix head must reach the summary model."""

    llm = _RecordingSummaryLLM()
    history, config = _numbered_history(35, llm=llm)

    retrieved = history.retrieve(query={"max_tokens": 200})

    assert retrieved[0].metadata.get("summary") is True
    prompt = llm.prompts[-1]
    covered = {int(token.split("_")[1]) for token in re.findall(r"ITEM_\d\d", prompt)}
    # 33 messages are replaced by the summary; every one of them must be covered,
    # including the ones beyond `summary_input_message_limit`.
    assert covered == set(range(33))
    assert len(covered) > config.summary_input_message_limit


def test_summary_input_elides_long_older_messages_without_dropping_them() -> None:
    llm = _RecordingSummaryLLM()
    history, _ = _numbered_history(35, llm=llm, chars=4000)

    history.retrieve(query={"max_tokens": 200})

    prompt = llm.prompts[-1]
    covered = {int(token.split("_")[1]) for token in re.findall(r"ITEM_\d\d", prompt)}
    assert covered == set(range(33))
    # Older turns are shortened rather than removed, so the request stays bounded.
    assert "elided" in prompt
    assert len(prompt) < 35 * 4000


def test_summary_trace_reports_real_input_counts_and_ranges() -> None:
    llm = _RecordingSummaryLLM()
    history, _ = _numbered_history(35, llm=llm)

    retrieved = history.retrieve(query={"max_tokens": 200})
    events = history.consume_runtime_events()

    summary_events = [
        event["context"]
        for event in events
        if (event.get("context") or {}).get("stage") == "summary_compact_applied"
    ]
    assert summary_events
    context = summary_events[-1]
    meta = retrieved[0].metadata
    for payload in (context, meta):
        assert payload["summarized_message_count"] == 33
        assert payload["summary_input_message_count"] == 33
        assert payload["summary_dropped_message_count"] == 0
        assert payload["summarized_step_range"] == [0, 32]
        assert payload["summary_input_step_range"] == [0, 32]
        assert payload["summary_input_mode"] in {"full", "microcompacted"}


def test_second_compaction_consumes_prior_summary() -> None:
    llm = _RecordingSummaryLLM()
    history, _ = _numbered_history(35, llm=llm)

    first = history.retrieve(query={"max_tokens": 200})
    assert first[0].metadata.get("built_on_prior_summary") is False
    assert history.last_summary == "SUMMARY_1"

    second = history.retrieve(query={"max_tokens": 200})
    assert second[0].metadata.get("built_on_prior_summary") is True
    assert "SUMMARY_1" in llm.prompts[-1]
    assert history.last_summary == "SUMMARY_2"


def test_retrieve_does_not_mutate_stored_history() -> None:
    llm = _RecordingSummaryLLM()
    history, _ = _numbered_history(35, llm=llm)

    before = [msg.content for msg in history.messages]
    history.retrieve(query={"max_tokens": 200})
    history.retrieve(query={"roles": ["user"], "max_items": 10, "max_tokens": 200})

    assert [msg.content for msg in history.messages] == before


def test_compact_ratio_moves_the_compaction_trigger() -> None:
    from qitos.engine._context_runtime import _ContextRuntime
    from qitos.engine.states import ContextConfig, ContextTelemetry

    class _LLM:
        context_window = 100_000
        max_tokens = 1_000

    class _Engine:
        class agent:
            llm = _LLM()

        def _estimate_tokens(self, payload: Any) -> int:
            return 0

    runtime = _ContextRuntime(_Engine())

    def probe(compact_ratio: float, target_utilization: float) -> tuple[int, int]:
        runtime.config = ContextConfig(
            safety_reserve_tokens=0,
            compact_ratio=compact_ratio,
            target_utilization=target_utilization,
        )
        ceiling = runtime.resolve_request_budget(_LLM())["available_input_budget"]
        telemetry = ContextTelemetry(
            available_input_budget=ceiling,
            system_prompt_tokens=0,
            prepared_tokens=0,
        )
        return ceiling, runtime.compact_trigger_budget(telemetry)

    eager_ceiling, eager_trigger = probe(0.20, 0.85)
    lazy_ceiling, lazy_trigger = probe(0.95, 0.85)

    # The documented compact threshold now controls when reduction starts...
    assert eager_trigger < lazy_trigger
    # ...while the hard per-request ceiling stays governed by target_utilization.
    assert eager_ceiling == lazy_ceiling == 84_000
    assert probe(0.85, 0.50)[0] == 49_000
    # warning_ratio < compact_ratio < overflow(1.0) must hold at the defaults.
    default_ceiling, default_trigger = probe(
        ContextConfig().compact_ratio, ContextConfig().target_utilization
    )
    assert (
        default_ceiling * ContextConfig().warning_ratio
        < default_trigger
        < default_ceiling
    )


@dataclass
class CompactDemoState(StateSchema):
    logs: list[str] = field(default_factory=list)


class CompactDemoAgent(AgentModule[CompactDemoState, dict[str, Any], Action]):
    def __init__(self):
        registry = ToolRegistry()

        @tool(name="add")
        def add(a: int, b: int) -> int:
            return a + b

        registry.register(add)
        super().__init__(tool_registry=registry)

    def init_state(self, task: str, **kwargs: Any) -> CompactDemoState:
        return CompactDemoState(task=task, max_steps=3)

    def reduce(
        self,
        state: CompactDemoState,
        observation: dict[str, Any],
        decision: Decision[Action],
    ) -> CompactDemoState:
        action_results = (
            observation.get("action_results", [])
            if isinstance(observation, dict)
            else []
        )
        if action_results:
            state.logs.append(str(action_results[0]))
        return state


def test_engine_surfaces_compact_events_and_history_metadata() -> None:
    calls: list[list[dict[str, str]]] = []

    class _DummyModel:
        model = "dummy-compact"

        def __call__(self, messages):
            calls.append(list(messages))
            if len(calls) == 1:
                return "Action: add(a=20, b=22)"
            return "Final Answer: 42"

    class LLMCompactAgent(CompactDemoAgent):
        def __init__(self):
            super().__init__()
            self.llm = _DummyModel()
            self.model_parser = ReActTextParser()
            self.history = CompactHistory(
                max_tokens=110, keep_last_rounds=1, keep_last_messages=4, hard_window=24
            )

        def build_system_prompt(self, state: CompactDemoState) -> str | None:
            return "Compact system prompt"

        def prepare(self, state: CompactDemoState) -> str:
            return (
                f"Task={state.task}\n"
                f"Step={state.current_step}\n"
                + ("Observation context and scratchpad detail. " * 50)
            ).strip()

        def decide(self, state: CompactDemoState, observation: dict[str, Any]):
            return None

    result = Engine(
        agent=LLMCompactAgent(),
        budget=RuntimeBudget(max_steps=3),
        history_policy=HistoryPolicy(max_messages=10, max_tokens=110),
    ).run("compute")

    assert result.state.final_result == "42"
    assert len(calls) == 2
    compact_stages = [
        (event.payload.get("context") or {}).get("stage")
        for event in result.events
        if getattr(event.phase, "value", event.phase) == "DECIDE"
        and event.payload.get("stage") == "context_history"
    ]
    assert "warning" in compact_stages
    assert any(
        stage in {"microcompact_applied", "summary_compact_applied"}
        for stage in compact_stages
    )

    model_input_events = [
        event for event in result.events if event.payload.get("stage") == "model_input"
    ]
    assert model_input_events
    history_meta = model_input_events[-1].payload.get("history_messages_meta", [])
    assert isinstance(history_meta, list)
    assert history_meta
    assert any(item.get("summary") or item.get("compacted") for item in history_meta)
    context = model_input_events[-1].payload.get("context", {})
    assert context.get("input_tokens_total", 0) > 0
