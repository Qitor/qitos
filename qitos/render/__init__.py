"""
QitOS Render Module

提供 Rich 控制台渲染组件和 CLI 钩子。

主要组件：
- RichRender: 统一的 Rich 渲染工具类
- RichConsoleHook: Rich 控制台渲染钩子
- 便捷函数: print_step_header, print_thought 等

Usage:
    from qitos.render import RichRender, RichConsoleHook
    
    # 直接渲染
    RichRender.print_step_header(0)
    RichRender.print_action("search", {"query": "python"})
    RichRender.print_final_answer("结果是 42")
    
    # 在 Agent 中使用
    from qitos import AgentModule
    from qitos.render import RichConsoleHook
    
    class MyAgent(AgentModule):
        def gather(self, context):
            return f"任务：{context.task}"
    
    agent = MyAgent()
    agent.run(task="xxx", hooks=[RichConsoleHook()])
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
    RichConsoleHook,
    SimpleRichConsoleHook,
    VerboseRichConsoleHook,
)

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
    
    # Hooks
    "RichConsoleHook",
    "SimpleRichConsoleHook",
    "VerboseRichConsoleHook",
]
