"""Engine modules for QitOS Framework."""

from .engine import Engine, EngineResult
from .critic import Critic
from .parser import Parser, BaseParser
from .search import Search
from .branching import BranchSelector, FirstCandidateSelector
from .action_executor import ActionExecutor
from .hooks import EngineHook, HookContext
from .recovery import RecoveryPolicy, RecoveryDecision, RecoveryTracker, FailureDiagnostic, build_failure_report
from .states import RuntimePhase, RuntimeEvent, RuntimeBudget, StepRecord
from .stop_criteria import StopCriteria, MaxStepsCriteria, MaxRuntimeCriteria, StagnationCriteria, FinalResultCriteria
from .validation import StateValidationGate

__all__ = [
    "Engine",
    "EngineResult",
    "Critic",
    "Parser",
    "BaseParser",
    "Search",
    "BranchSelector",
    "FirstCandidateSelector",
    "ActionExecutor",
    "EngineHook",
    "HookContext",
    "RecoveryPolicy",
    "RecoveryDecision",
    "RecoveryTracker",
    "FailureDiagnostic",
    "build_failure_report",
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
]
