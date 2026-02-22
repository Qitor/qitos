from __future__ import annotations

from qitos.kit.env import TextWebEnv
from qitos.kit.tool import FindInPage, FindNext, PageDown, PageUp


def test_text_web_env_exposes_web_browser_ops():
    env = TextWebEnv(workspace_root=".")
    env.reset()
    ops = env.get_ops("web_browser")
    assert ops is not None
    summary = ops.summary()
    assert "active_url" in summary


def test_text_web_atomic_tools_use_ops_context():
    env = TextWebEnv(workspace_root=".")
    env.reset()
    ops = env.get_ops("web_browser")
    ops.state.lines = [f"line {i}" for i in range(120)]  # type: ignore[attr-defined]
    ops.state.url = "https://example.com"  # type: ignore[attr-defined]
    ops.state.title = "Example"  # type: ignore[attr-defined]

    ctx = {"ops": {"web_browser": ops}, "env": env}
    down = PageDown().run(lines=20, runtime_context=ctx)
    assert down["status"] == "success"
    assert down["line_start"] == 20

    up = PageUp().run(lines=10, runtime_context=ctx)
    assert up["status"] == "success"
    assert up["line_start"] == 10

    find = FindInPage().run(keyword="line 42", runtime_context=ctx)
    assert find["status"] == "success"
    assert find["matched_line"] == 42

    next_match = FindNext().run(runtime_context=ctx)
    assert next_match["status"] == "error"

