from qitos import MemoryRecord
from qitos.kit.critic import PassThroughCritic
from qitos.kit.memory import SummaryMemory, VectorMemory, WindowMemory
from qitos.kit.parser import (
    JsonDecisionParser,
    ReActTextParser,
    XmlDecisionParser,
    parse_first_action_invocation,
    split_args_robust,
)


def test_memory_adapters_basic():
    win = WindowMemory(window_size=2)
    win.append(MemoryRecord(role="user", content="a", step_id=0))
    win.append(MemoryRecord(role="assistant", content="b", step_id=1))
    win.append(MemoryRecord(role="user", content="c", step_id=2))
    assert [r.content for r in win.retrieve()] == ["b", "c"]

    summary = SummaryMemory(keep_last=2)
    summary.append(MemoryRecord(role="user", content="alpha", step_id=0))
    summary.append(MemoryRecord(role="assistant", content="beta", step_id=1))
    assert "alpha" in summary.summarize(max_items=2)

    vec = VectorMemory(top_k=1)
    vec.append(MemoryRecord(role="user", content="python docs", step_id=0))
    vec.append(MemoryRecord(role="user", content="flight booking", step_id=1))
    top = vec.retrieve({"text": "python", "top_k": 1})
    assert len(top) == 1


def test_parser_and_critic_impls():
    d1 = JsonDecisionParser().parse('{"mode":"wait"}')
    assert d1.mode == "wait"

    d2 = ReActTextParser().parse("Final Answer: done")
    assert d2.mode == "final"
    d2b = ReActTextParser().parse("Thought: x\nAction: {'name': 'add', 'args': {'a': 2, 'b': 3}}")
    assert d2b.mode == "act"
    assert d2b.actions[0]["name"] == "add"

    long_html = "<html><head><script>var x = {a:1,b:2};</script></head><body>Hello, world</body></html>"
    raw = f"Thought: parse\nAction: extract_web_text(html={long_html!r}, max_chars=6000, keep_links=False)"
    d2c = ReActTextParser().parse(raw)
    assert d2c.mode == "act"
    assert d2c.actions[0]["name"] == "extract_web_text"
    assert d2c.actions[0]["args"]["max_chars"] == 6000
    assert d2c.actions[0]["args"]["keep_links"] is False
    assert "Hello, world" in d2c.actions[0]["args"]["html"]

    d3 = XmlDecisionParser().parse('<decision mode="wait"></decision>')
    assert d3.mode == "wait"

    critic = PassThroughCritic()
    out = critic.evaluate(state={}, decision=d1, results=[])
    assert out["action"] == "continue"


def test_func_parser_handles_nested_and_truncated_calls():
    s = "a=1, payload={'x':[1,2,3], 'y':'k,v'}, html='<div>(x)</div>', flag=true"
    parts = split_args_robust(s)
    assert len(parts) == 4

    parsed = parse_first_action_invocation("Thought: x\nAction: tool(a=1, b='x,y', c={'k':[1,2]})")
    assert parsed is not None
    assert parsed["name"] == "tool"
    assert parsed["args"]["a"] == 1
    assert parsed["args"]["b"] == "x,y"
    assert parsed["args"]["c"]["k"] == [1, 2]

    # truncated tail: still recover partial kwargs
    parsed2 = parse_first_action_invocation("Action: extract_web_text(html='<html><body>abc', max_chars=5000")
    assert parsed2 is not None
    assert parsed2["name"] == "extract_web_text"
    assert parsed2["args"]["max_chars"] == 5000
