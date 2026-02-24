"""
@Copyright (c) 2026, Qitor Research. All rights reserved.
QitOS public API surface.

"""

__version__ = "0.1.0a1"

from .core.agent_module import AgentModule
from .core.action import Action, ActionExecutionPolicy, ActionKind, ActionResult, ActionStatus
from .core.decision import Decision
from .core.env import CommandCapability, Env, EnvObservation, EnvSpec, EnvStepResult, FileSystemCapability
from .core.errors import ErrorCategory, QitosRuntimeError, RuntimeErrorInfo, StopReason
from .core.memory import Memory, MemoryRecord
from .core.state import PlanState, StateSchema
from .core.task import (
    Task,
    TaskBudget,
    TaskCriterionResult,
    TaskResource,
    TaskResourceBinding,
    TaskResult,
    TaskValidationIssue,
)
from .core.tool import BaseTool, FunctionTool, ToolPermission, ToolSpec, tool
from .core.tool_registry import ToolRegistry
from .benchmark import (
    BenchmarkAdapter,
    BenchmarkSource,
    CyBenchAdapter,
    CyBenchRuntime,
    GaiaAdapter,
    TauBenchAdapter,
    load_cybench_tasks,
    load_gaia_tasks,
    load_tau_bench_tasks,
    score_cybench_submission,
)
from .evaluate import EvaluationContext, EvaluationResult, EvaluationSuite, SuiteEvaluationResult, TrajectoryEvaluator
from .engine.engine import Engine, EngineResult
from .metric import Metric, MetricInput, MetricRegistry, MetricReport
from .engine.states import RuntimeBudget

__all__ = [
    "AgentModule",
    "Engine",
    "EngineResult",
    "Task",
    "TaskResource",
    "TaskBudget",
    "TaskValidationIssue",
    "TaskResourceBinding",
    "TaskCriterionResult",
    "TaskResult",
    "StateSchema",
    "PlanState",
    "Decision",
    "Action",
    "ActionResult",
    "ActionKind",
    "ActionStatus",
    "ActionExecutionPolicy",
    "Memory",
    "MemoryRecord",
    "Env",
    "EnvSpec",
    "EnvObservation",
    "EnvStepResult",
    "FileSystemCapability",
    "CommandCapability",
    "BaseTool",
    "FunctionTool",
    "ToolPermission",
    "ToolSpec",
    "tool",
    "ToolRegistry",
    "BenchmarkAdapter",
    "BenchmarkSource",
    "CyBenchAdapter",
    "CyBenchRuntime",
    "score_cybench_submission",
    "load_cybench_tasks",
    "GaiaAdapter",
    "TauBenchAdapter",
    "load_gaia_tasks",
    "load_tau_bench_tasks",
    "TrajectoryEvaluator",
    "EvaluationContext",
    "EvaluationResult",
    "EvaluationSuite",
    "SuiteEvaluationResult",
    "Metric",
    "MetricInput",
    "MetricRegistry",
    "MetricReport",
    "RuntimeBudget",
    "ErrorCategory",
    "StopReason",
    "RuntimeErrorInfo",
    "QitosRuntimeError",
]
