"""Permanent application-policy counterexamples; installed tests are separate."""

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from qitos.core.action import Action
from qitos.core.decision import Decision
from qitos.core.observation import Observation
from qitos.core.tool_result import ToolResult

ROOT = Path(__file__).resolve().parents[1]


def load(monkeypatch, directory, package, filename):
    name = f"lab_policy_{package}_{filename}"
    path = ROOT / "examples/projects" / directory / "src" / package / (filename + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "dynamic,version,plan", [(False, 1, ["first"]), (True, 2, ["second"])]
)
def test_static_plan_accepts_one_proposal_even_in_same_batch(
    monkeypatch, dynamic, version, plan
):
    module = load(monkeypatch, "planact_research", "qitos_lab_planact", "agent")
    agent = module.ResearchAgent(dynamic=dynamic)
    state = agent.init_state("compare plans")
    observation = Observation(
        step_id=0,
        action_results=[
            ToolResult(tool_name="revise_plan", output={"remaining_plan": [name]})
            for name in ["first", "second"]
        ],
    )
    agent.reduce(state, observation, Decision.act([Action("revise_plan")]))
    assert state.plan_version == version
    assert state.plan == plan
    assert len(state.evidence) == 2  # Rejected proposals are not erased.


@pytest.mark.parametrize("citations", [None, {}, [None], [{"source": "protocol.md"}]])
def test_research_checker_rejects_malformed_citations_without_crashing(
    monkeypatch, citations
):
    module = load(monkeypatch, "react_research", "qitos_lab_react", "evaluate")
    report = {
        "conclusion": "claimed",
        "limitations": ["limited"],
        "citations": citations,
    }
    result = SimpleNamespace(
        records=[
            SimpleNamespace(
                action_results=[
                    ToolResult(
                        tool_name="submit_report",
                        output={"submitted_report": report},
                    )
                ]
            )
        ],
        state=SimpleNamespace(stop_reason="final"),
        tool_calls_by_name={"read_file": 99},
    )
    verdict = module.evaluate(
        result, {"required_sources": ["protocol.md"], "expected_metrics": {}}
    )
    assert not verdict["passed"]
    assert not verdict["checks"]["actual_reads"]
    json.dumps(verdict)
