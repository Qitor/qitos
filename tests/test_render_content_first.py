from __future__ import annotations

from rich.console import Console

from qitos.render.content_renderer import ContentFirstRenderer
from qitos.render.events import RenderEvent
from qitos.render.hooks import ClaudeStyleHook


def test_content_first_renderer_core_blocks() -> None:
    renderer = ContentFirstRenderer(max_preview_chars=200)

    thought_evt = RenderEvent(
        channel="thinking",
        node="decision",
        step_id=0,
        payload={"rationale": "First inspect the target page and extract key points."},
    )
    thought = renderer.thought_text(thought_evt)
    assert isinstance(thought, str)
    assert "inspect the target page" in thought

    action_evt = RenderEvent(
        channel="action",
        node="planned_actions",
        step_id=0,
        payload={"actions": [{"name": "web_search", "args": {"query": "finding nemo fish species"}}]},
    )
    action = renderer.action_summary(action_evt)
    assert isinstance(action, dict)
    assert action.get("label") == "WEB SEARCH"
    assert "finding nemo fish species" in str(action.get("detail"))

    obs_evt = RenderEvent(
        channel="observation",
        node="action_results",
        step_id=0,
        payload={
            "action_results": [
                {
                    "results": [
                        {"title": "All fishes in Finding Nemo", "url": "https://example.com/nemo/fishes"},
                    ]
                }
            ]
        },
    )
    obs = renderer.observation_summary(obs_evt)
    assert isinstance(obs, dict)
    assert obs.get("title") == "Search Results"


def test_claude_style_hook_ignores_model_input_payload() -> None:
    hook = ClaudeStyleHook(max_preview_chars=200)
    hook.console = Console(record=True, width=120)

    hook.on_render_event(
        RenderEvent(channel="lifecycle", node="run_start", step_id=0, payload={"task": "demo task", "max_steps": 3})
    )
    hook.on_render_event(RenderEvent(channel="lifecycle", node="step_start", step_id=0, payload={}))
    hook.on_render_event(
        RenderEvent(
            channel="observation",
            node="observation",
            step_id=0,
            payload={"observation": {"scratchpad": ["a", "b"], "memory": {"records": [1, 2, 3]}}},
        )
    )
    hook.on_render_event(
        RenderEvent(
            channel="thinking",
            node="model_input",
            step_id=0,
            payload={"messages": [{"role": "user", "content": "very long history"}]},
        )
    )
    hook.on_render_event(
        RenderEvent(
            channel="thinking",
            node="decision",
            step_id=0,
            payload={"rationale": "I should use web_search first."},
        )
    )

    text = hook.console.export_text()
    assert "State" in text
    assert "sp_toks" in text
    assert "⦿" in text
    assert "web_search first" in text
    assert "very long history" not in text


def test_claude_style_hook_prints_agent_composition() -> None:
    class _Budget:
        max_steps = 5

    class _LLM:
        model_name = "Qwen/Qwen3-8B"

    class _Agent:
        llm = _LLM()

    class _Memory:
        pass

    class _Search:
        pass

    class _Registry:
        @staticmethod
        def list_tools():
            return ["web_search", "visit_url"]

    class _Engine:
        budget = _Budget()
        agent = _Agent()
        memory = _Memory()
        search = _Search()
        tool_registry = _Registry()

    hook = ClaudeStyleHook(max_preview_chars=200)
    hook.console = Console(record=True, width=120)
    hook.on_run_start(task="demo", state={}, engine=_Engine())
    hook._stop_status()
    text = hook.console.export_text()
    assert "AGENT COMPOSITION" in text
    assert "Qwen/Qwen3-8B" in text
    assert "web_search" in text
