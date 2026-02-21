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

from .core.agent_module import AgentModule, LegacyPerceiveAdapter
from .core.decision import Decision
from .core.critic import Critic, PassThroughCritic
from .core.parser import Parser, BaseParser, JsonDecisionParser, ReActTextParser, XmlDecisionParser
from .core.policy import Policy, BranchSelector, FirstCandidateSelector
from .core.search import SearchAdapter, GreedySearchAdapter
from .core.action import Action, ActionResult, ActionKind, ActionStatus, ActionExecutionPolicy
from .core.errors import ErrorCategory, StopReason, RuntimeErrorInfo, QitosRuntimeError
from .core.state import StateSchema, PlanState
from .core.state_validators import StateValidationGate
from .core.tool import BaseTool, FunctionTool, ToolPermission, ToolSpec, tool
from .core.tool_registry import ToolRegistry
from .core.toolset import ToolSet
from .core.skill import skill, ToolRegistry as LegacyToolRegistry
from .engine.fsm_engine import FSMEngine, EngineResult
from .engine.action_executor import ActionExecutor
from .engine.recovery import RecoveryPolicy, RecoveryDecision, RecoveryTracker, FailureDiagnostic
from .engine.states import RuntimePhase, RuntimeEvent, RuntimeBudget, StepRecord
from .runtime import Runtime, RuntimeResult, StopCriteria, MaxStepsCriteria, MaxRuntimeCriteria, StagnationCriteria, FinalResultCriteria
from .memory import MemoryAdapter, MemoryRecord, WindowMemory, SummaryMemory, VectorMemory
from .trace import TraceEvent, TraceStep, TraceWriter, TraceSchemaValidator
from .debug import Breakpoint, InspectorPayload, ReplaySession, ReplaySnapshot, build_inspector_payload, compare_steps
from .presets import build_registry as build_preset_registry
from .release import run_release_checks, write_release_readiness_report
from .core.hooks import Hook, CompositeHook

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
    "LegacyPerceiveAdapter",
    "Policy",
    "SearchAdapter",
    "GreedySearchAdapter",
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
    "StateValidationGate",
    "BaseTool",
    "FunctionTool",
    "ToolPermission",
    "ToolSpec",
    "tool",
    "ToolRegistry",
    "ToolSet",
    "skill",
    "LegacyToolRegistry",
    "FSMEngine",
    "EngineResult",
    "ActionExecutor",
    "RecoveryPolicy",
    "RecoveryDecision",
    "RecoveryTracker",
    "FailureDiagnostic",
    "RuntimePhase",
    "RuntimeEvent",
    "RuntimeBudget",
    "StepRecord",
    "Runtime",
    "RuntimeResult",
    "StopCriteria",
    "MaxStepsCriteria",
    "MaxRuntimeCriteria",
    "StagnationCriteria",
    "FinalResultCriteria",
    "MemoryAdapter",
    "MemoryRecord",
    "WindowMemory",
    "SummaryMemory",
    "VectorMemory",
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
    "build_preset_registry",
    "run_release_checks",
    "write_release_readiness_report",
    "Hook",
    "CompositeHook",
]
