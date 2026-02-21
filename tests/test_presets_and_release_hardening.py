from pathlib import Path

from qitos import MemoryRecord
from qitos import Runtime, RuntimeBudget
from qitos.presets import build_registry
from qitos.presets.policies import ArithmeticState
from qitos.release import run_release_checks, write_release_readiness_report


def test_preset_registry_and_composition():
    reg = build_registry()

    policy = reg.get("policy", "react_arithmetic").factory()
    toolkit = reg.get("toolkit", "math").factory()
    search = reg.get("search", "greedy").factory(top_k=1)
    critic = reg.get("critic", "pass_through").factory()

    runtime = Runtime(
        policy=policy,
        toolkit=toolkit,
        search_adapter=search,
        critics=[critic],
        budget=RuntimeBudget(max_steps=4),
    )
    result = runtime.run(ArithmeticState(task="compute"))
    assert result.state.final_result == "42"


def test_preset_composition_variants():
    reg = build_registry()
    parser_names = ["json", "react_text", "xml"]
    memory_names = ["window", "summary", "vector"]

    for parser_name, memory_name in zip(parser_names, memory_names):
        parser = reg.get("parser", parser_name).factory()
        memory = reg.get("memory", memory_name).factory()
        assert parser is not None
        if parser_name == "json":
            decision = parser.parse('{"mode":"wait"}')
            assert decision.mode == "wait"
        elif parser_name == "react_text":
            decision = parser.parse("Final Answer: done")
            assert decision.mode == "final"
        elif parser_name == "xml":
            decision = parser.parse('<decision mode="wait"></decision>')
            assert decision.mode == "wait"
        memory.append(MemoryRecord(role="user", content="alpha", step_id=0))
        memory.append(MemoryRecord(role="assistant", content="beta", step_id=1))
        assert len(memory.retrieve({})) >= 1
        assert isinstance(memory.summarize(max_items=1), str)


def test_release_checks_and_report(tmp_path: Path):
    report = run_release_checks()
    assert report["ok"] is True

    out = tmp_path / "release_readiness.md"
    persisted = write_release_readiness_report(str(out))
    assert persisted["ok"] is True
    assert out.exists()
    assert "Release Readiness Report" in out.read_text(encoding="utf-8")
