from __future__ import annotations

from types import SimpleNamespace

from qitos.engine.action_executor import ActionExecutor


class _Hook:
    def __init__(self) -> None:
        self.context = None

    def on_after_tool_use(self, ctx, _engine) -> None:
        self.context = ctx


def test_native_tool_hook_uses_active_engine_step() -> None:
    """Tool provenance must identify the decision round that produced it."""
    hook = _Hook()
    engine = SimpleNamespace(hooks=[hook], _active_state=SimpleNamespace(current_step=17))
    executor = ActionExecutor.__new__(ActionExecutor)
    executor._engine = engine

    executor._dispatch_tool_hook("on_after_tool_use", "READ", {"path": "repo-vul/a.c"}, {"ok": True})

    assert hook.context is not None
    assert hook.context.step_id == 17
    assert hook.context.state is engine._active_state

def test_relocate_chat_template_kwargs_moves_unknown_sdk_kwargs() -> None:
    from qitos.models.openai import _relocate_chat_template_kwargs

    relocated = _relocate_chat_template_kwargs(
        {
            "temperature": 0.2,
            "do_sample": True,
            "chat_template_kwargs": {"enable_thinking": False},
            "extra_body": {"custom": 1},
        }
    )

    assert relocated["temperature"] == 0.2
    assert "do_sample" not in relocated
    assert "chat_template_kwargs" not in relocated
    assert relocated["extra_body"] == {
        "custom": 1,
        "chat_template_kwargs": {"enable_thinking": False},
        "do_sample": True,
    }


def test_relocate_chat_template_kwargs_no_extras_untouched() -> None:
    from qitos.models.openai import _relocate_chat_template_kwargs

    assert _relocate_chat_template_kwargs({"temperature": 0.1}) == {"temperature": 0.1}
