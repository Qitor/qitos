"""Core modules for QitOS Framework."""
from .agent_module import AgentModule, LegacyPerceiveAdapter
from .decision import Decision
from .critic import Critic, PassThroughCritic
from .parser import Parser, BaseParser, JsonDecisionParser, ReActTextParser, XmlDecisionParser
from .policy import Policy, BranchSelector, FirstCandidateSelector, ObservationBuilder
from .search import SearchAdapter, GreedySearchAdapter
from .action import Action, ActionResult, ActionKind, ActionStatus, ActionExecutionPolicy
from .errors import (
    ErrorCategory,
    StopReason,
    RuntimeErrorInfo,
    QitosRuntimeError,
    ModelExecutionError,
    ParseExecutionError,
    ToolExecutionError,
    StateExecutionError,
    SystemExecutionError,
    classify_exception,
)
from .state import StateSchema, PlanState, StateMigrationRegistry, StateValidationError, StateMigrationError
from .state_validators import StateValidationGate
from .tool import BaseTool, FunctionTool, ToolPermission, ToolSpec, tool
from .tool_registry import ToolRegistry
from .toolset import ToolSet
from .skill import skill, ToolRegistry as LegacyToolRegistry
from .hooks import Hook, CompositeHook

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
    "ObservationBuilder",
    "Action",
    "ActionResult",
    "ActionKind",
    "ActionStatus",
    "ActionExecutionPolicy",
    "ErrorCategory",
    "StopReason",
    "RuntimeErrorInfo",
    "QitosRuntimeError",
    "ModelExecutionError",
    "ParseExecutionError",
    "ToolExecutionError",
    "StateExecutionError",
    "SystemExecutionError",
    "classify_exception",
    "StateSchema",
    "PlanState",
    "StateMigrationRegistry",
    "StateValidationError",
    "StateMigrationError",
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
    "Hook",
    "CompositeHook",
]
