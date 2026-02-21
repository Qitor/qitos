"""
QitOS Framework
A state-driven Agent framework for research and development

Core Features:
- Explicit over implicit: All state changes must be traceable and debuggable
- State is everything: typed runtime state is the single source of truth
- Debugging is development: Provides IDE-like single-step execution and time-travel capabilities
- Interactive CLI: Supports Rich rendering and Typer command line
"""

__version__ = "0.1-alpha"

from .core.agent_module import AgentModule
from .core.decision import Decision
from .core.action import Action, ActionResult, ActionKind, ActionStatus, ActionExecutionPolicy
from .core.errors import ErrorCategory, StopReason, RuntimeErrorInfo, QitosRuntimeError
from .core.state import StateSchema, PlanState
from .core.memory import Memory, MemoryRecord
from .core.env import Env, EnvSpec, EnvObservation, EnvStepResult, FileSystemCapability, CommandCapability
from .core.task import Task, TaskResource, TaskBudget
from .core.tool import BaseTool, FunctionTool, ToolPermission, ToolSpec, tool
from .core.tool_registry import ToolRegistry
from .engine.engine import Engine, EngineResult
from .engine.critic import Critic
from .engine.parser import Parser, BaseParser
from .engine.search import Search
from .engine.branching import BranchSelector, FirstCandidateSelector
from .engine.action_executor import ActionExecutor
from .engine.hooks import EngineHook, HookContext
from .engine.recovery import RecoveryPolicy, RecoveryDecision, RecoveryTracker, FailureDiagnostic
from .engine.states import RuntimePhase, RuntimeEvent, RuntimeBudget, StepRecord
from .engine.stop_criteria import StopCriteria, MaxStepsCriteria, MaxRuntimeCriteria, StagnationCriteria, FinalResultCriteria
from .engine.validation import StateValidationGate
from .kit.tool.toolset import ToolSet
from .kit.memory import WindowMemory, SummaryMemory, VectorMemory, MarkdownFileMemory
from .kit.env import DockerEnv, HostEnv, RepoEnv
from .kit.critic import PassThroughCritic, SelfReflectionCritic, ReActSelfReflectionCritic
from .kit.parser import JsonDecisionParser, ReActTextParser, XmlDecisionParser
from .kit.planning import GreedySearch, DynamicTreeSearch
from .trace import TraceEvent, TraceStep, TraceWriter, TraceSchemaValidator
from .debug import Breakpoint, InspectorPayload, ReplaySession, ReplaySnapshot, build_inspector_payload, compare_steps
from .render import ClaudeStyleHook, RenderStreamHook, RenderEvent
from . import kit

__all__ = [
    "AgentModule",
    "Decision",
    "Critic",
    "PassThroughCritic",
    "Parser",
    "BaseParser",
    "JsonDecisionParser",
    "ReActTextParser",
    "XmlDecisionParser",
    "Search",
    "GreedySearch",
    "DynamicTreeSearch",
    "BranchSelector",
    "FirstCandidateSelector",
    "Action",
    "ActionResult",
    "ActionKind",
    "ActionStatus",
    "ActionExecutionPolicy",
    "ErrorCategory",
    "StopReason",
    "RuntimeErrorInfo",
    "QitosRuntimeError",
    "StateSchema",
    "PlanState",
    "BaseTool",
    "FunctionTool",
    "ToolPermission",
    "ToolSpec",
    "tool",
    "ToolRegistry",
    "ToolSet",
    "Engine",
    "EngineResult",
    "ActionExecutor",
    "EngineHook",
    "HookContext",
    "RecoveryPolicy",
    "RecoveryDecision",
    "RecoveryTracker",
    "FailureDiagnostic",
    "RuntimePhase",
    "RuntimeEvent",
    "RuntimeBudget",
    "StepRecord",
    "StopCriteria",
    "MaxStepsCriteria",
    "MaxRuntimeCriteria",
    "StagnationCriteria",
    "FinalResultCriteria",
    "StateValidationGate",
    "Memory",
    "MemoryRecord",
    "Env",
    "EnvSpec",
    "EnvObservation",
    "EnvStepResult",
    "FileSystemCapability",
    "CommandCapability",
    "Task",
    "TaskResource",
    "TaskBudget",
    "WindowMemory",
    "SummaryMemory",
    "VectorMemory",
    "MarkdownFileMemory",
    "HostEnv",
    "DockerEnv",
    "RepoEnv",
    "SelfReflectionCritic",
    "ReActSelfReflectionCritic",
    "TraceEvent",
    "TraceStep",
    "TraceWriter",
    "TraceSchemaValidator",
    "Breakpoint",
    "InspectorPayload",
    "build_inspector_payload",
    "compare_steps",
    "ReplaySession",
    "ReplaySnapshot",
    "ClaudeStyleHook",
    "RenderStreamHook",
    "RenderEvent",
    "kit",
]
