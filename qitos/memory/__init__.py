"""
Memory Module

记忆模块，提供多种历史消息检索策略。

内置实现：
- WindowMemory: 滑动窗口记忆（默认）
- ConversationMemory: 对话式记忆
- SummaryMemory: 摘要记忆

Usage:
    from qitos.memory import WindowMemory
    
    # 自定义记忆策略
    memory = WindowMemory(window_size=10)
"""

from .base import (
    BaseMemory,
    MemoryMixin,
    ConversationMemory,
    SummaryMemory
)
from .window import (
    WindowMemory,
    SlidingWindowMemory,
    FixedWindowMemory,
    UnlimitedMemory
)

__all__ = [
    # 基类
    "BaseMemory",
    "MemoryMixin",
    
    # 对话记忆
    "ConversationMemory",
    
    # 摘要记忆
    "SummaryMemory",
    
    # 窗口记忆
    "WindowMemory",
    "SlidingWindowMemory",
    "FixedWindowMemory",
    "UnlimitedMemory",
]
