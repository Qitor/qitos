"""
QitOS Framework v3.1
A state-driven Agent framework born for developer happiness

Core Features:
- Explicit over implicit: All state changes must be traceable and debuggable
- State is everything: AgentContext is the single source of truth
- Debugging is development: Provides IDE-like single-step execution and time-travel capabilities
- Interactive CLI: Supports Rich rendering and Typer command line
"""

__version__ = "0.1-alpha"

from .core.context import AgentContext
from .core.agent import AgentModule
from .core.skill import skill, ToolRegistry
from .engine.execution_engine import ExecutionEngine, run_agent
from .core.hooks import Hook, CompositeHook

__all__ = [
    "AgentContext",
    "AgentModule", 
    "skill",
    "ToolRegistry",
    "ExecutionEngine",
    "run_agent",
    "Hook",
    "CompositeHook",
]
