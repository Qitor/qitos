from dataclasses import dataclass, field

from qitos.kit.planning import LLMDecisionBlock, PlanCursor, ToolAwareMessageBuilder, append_log, parse_numbered_plan, set_final
from qitos.kit.parser import ReActTextParser
from qitos.kit.prompts import PLAN_ACT_SYSTEM_PROMPT, REACT_SYSTEM_PROMPT, render_prompt
from qitos.kit.state import append_str, set_str


class _DummyRegistry:
    def get_tool_descriptions(self) -> str:
        return "## add\nDescription: add two ints"


class _DummyLLM:
    def __call__(self, messages):
        assert messages
        return "Action: add(a=20, b=22)"


@dataclass
class _S:
    notes: list[str] = field(default_factory=list)
    final_result: str | None = None
    plan: list[str] = field(default_factory=list)
    plan_cursor: int = 0
    title: str = ""


def test_planning_blocks_and_state_helpers():
    builder = ToolAwareMessageBuilder(system_template="Tools:\n{tool_schema}")
    msgs = builder.build(task="compute", tool_registry=_DummyRegistry(), scratchpad=["Thought: start"])
    assert len(msgs) == 2
    obs_msgs = builder.build_from_observation(
        observation={
            "task": "compute",
            "scratchpad": ["Thought: start"],
            "phase": "act",
            "memory": {"summary": "recent memory", "records": [{"role": "observation", "content": "x"}]},
        },
        tool_registry=_DummyRegistry(),
    )
    assert "recent memory" in obs_msgs[1]["content"]

    decider = LLMDecisionBlock(llm=_DummyLLM(), parser=ReActTextParser())
    d = decider.decide(msgs)
    assert d.mode == "act"

    steps = parse_numbered_plan("1. gather\n2. act")
    s = _S()
    cursor = PlanCursor(plan_field="plan", cursor_field="plan_cursor")
    cursor.init(s, steps)
    assert cursor.current(s) == "gather"
    cursor.advance(s)
    assert cursor.current(s) == "act"

    append_log(s, "notes", "ok", max_items=3)
    set_final(s, "done")
    set_str(s, "title", "x")
    append_str(s, "notes", "y", max_items=5)
    assert s.final_result == "done"
    assert s.title == "x"
    assert s.notes[-1] == "y"


def test_prompts_exist():
    assert "ReAct" in REACT_SYSTEM_PROMPT
    assert "planning" in PLAN_ACT_SYSTEM_PROMPT.lower()


def test_render_prompt_is_safe_for_literal_braces_and_unknown_keys():
    template = "Tool schema: {tool_schema}\nBad example: {'name': 'http_get', 'args': {...}}\nUnknown: {missing}"
    rendered = render_prompt(template, {"tool_schema": "## get\nDescription: x"})
    assert "## get" in rendered
    assert "{'name': 'http_get'" in rendered
    assert "{missing}" in rendered
