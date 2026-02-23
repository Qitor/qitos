"""
QitOS Render Module

Rich rendering components and Engine render hooks.

主要组件：
- RichRender: 统一的 Rich 渲染工具类
- RichConsoleHook: Rich 控制台渲染钩子
- 便捷函数: print_step_header, print_thought 等

Usage:
    from qitos.render import RichConsoleHook
    result = agent.run(task="...", return_state=True, render_hooks=[RichConsoleHook()])
"""

from .cli_render import (
    RichRender,
    RichRender as render,
    print_step_header,
    print_thought,
    print_action,
    print_observation,
    print_final_answer,
    print_error,
)
from .hooks import (
    RenderHook,
    RenderStreamHook,
    RichConsoleHook,
    SimpleRichConsoleHook,
    VerboseRichConsoleHook,
    ClaudeStyleHook,
)
from .events import RenderEvent
from .content_renderer import ContentFirstRenderer

__all__ = [
    # Rendering
    "RichRender",
    "render",
    "print_step_header",
    "print_thought",
    "print_action",
    "print_observation",
    "print_final_answer",
    "print_error",
    
    # Render hooks
    "RenderHook",
    "RenderStreamHook",
    "RichConsoleHook",
    "SimpleRichConsoleHook",
    "VerboseRichConsoleHook",
    "ClaudeStyleHook",
    "RenderEvent",
    "ContentFirstRenderer",
]
