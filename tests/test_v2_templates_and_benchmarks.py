from benchmarks.plan_act_eval import run_eval as run_plan_act_eval
from benchmarks.react_eval import run_eval as run_react_eval
from templates.plan_act.editor_agent import PlanActEditorAgent
from templates.react.editor_agent import ReActEditorAgent


def test_react_template_eval_baseline():
    metrics = run_react_eval()
    assert metrics["total"] >= 3
    assert metrics["success"] == metrics["total"]
    assert metrics["success_rate"] == 1.0


def test_plan_act_template_eval_baseline():
    metrics = run_plan_act_eval()
    assert metrics["total"] >= 3
    assert metrics["success"] == metrics["total"]
    assert metrics["success_rate"] == 1.0
    assert metrics["avg_steps"] >= 3


def test_react_editor_tool_integration(tmp_path):
    agent = ReActEditorAgent(workspace_root=str(tmp_path))
    result = agent.run(
        "Create a file and verify content",
        path="notes/react_test.txt",
        content="react integration content",
    )

    target = tmp_path / "notes" / "react_test.txt"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "react integration content"
    assert result == "verified:notes/react_test.txt"


def test_plan_act_editor_tool_integration(tmp_path):
    agent = PlanActEditorAgent(workspace_root=str(tmp_path))
    result = agent.run(
        "Plan file creation and verification",
        path="notes/plan_act_test.txt",
        content="plan act integration content",
    )

    target = tmp_path / "notes" / "plan_act_test.txt"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "plan act integration content"
    assert result == "verified:notes/plan_act_test.txt"
