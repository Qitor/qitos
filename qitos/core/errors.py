"""Unified error taxonomy for QitOS runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class ErrorCategory(str, Enum):
    MODEL = "model_error"
    PARSE = "parse_error"
    TOOL = "tool_error"
    STATE = "state_error"
    SYSTEM = "system_error"


class StopReason(str, Enum):
    SUCCESS = "success"
    FINAL = "final"
    MAX_STEPS = "max_steps"
    BUDGET_STEPS = "budget_steps"
    BUDGET_TIME = "budget_time"
    AGENT_CONDITION = "agent_condition"
    ENV_TERMINAL = "env_terminal"
    UNRECOVERABLE_ERROR = "unrecoverable_error"


@dataclass
class RuntimeErrorInfo:
    category: ErrorCategory
    message: str
    phase: str
    step_id: int
    recoverable: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


class QitosRuntimeError(Exception):
    def __init__(self, info: RuntimeErrorInfo):
        super().__init__(f"[{info.category.value}] {info.message}")
        self.info = info


class ModelExecutionError(QitosRuntimeError):
    pass


class ParseExecutionError(QitosRuntimeError):
    pass


class ToolExecutionError(QitosRuntimeError):
    pass


class StateExecutionError(QitosRuntimeError):
    pass


class SystemExecutionError(QitosRuntimeError):
    pass


def classify_exception(exc: Exception, phase: str, step_id: int) -> RuntimeErrorInfo:
    if isinstance(exc, ModelExecutionError):
        return exc.info
    if isinstance(exc, ParseExecutionError):
        return exc.info
    if isinstance(exc, ToolExecutionError):
        return exc.info
    if isinstance(exc, StateExecutionError):
        return exc.info
    if isinstance(exc, SystemExecutionError):
        return exc.info

    msg = str(exc).lower()

    if isinstance(exc, (TimeoutError, ConnectionError)) and phase.lower() in {"observe", "propose"}:
        return RuntimeErrorInfo(
            category=ErrorCategory.MODEL,
            message=str(exc),
            phase=phase,
            step_id=step_id,
            recoverable=True,
        )

    if isinstance(exc, ValueError) and ("decision mode" in msg or "parser" in msg or "json" in msg or "xml" in msg):
        return RuntimeErrorInfo(
            category=ErrorCategory.PARSE,
            message=str(exc),
            phase=phase,
            step_id=step_id,
            recoverable=True,
        )

    if isinstance(exc, (TypeError, AttributeError, AssertionError)) and "state" in msg:
        return RuntimeErrorInfo(
            category=ErrorCategory.STATE,
            message=str(exc),
            phase=phase,
            step_id=step_id,
            recoverable=False,
        )

    if phase.upper() == "ACT":
        return RuntimeErrorInfo(
            category=ErrorCategory.TOOL,
            message=str(exc),
            phase=phase,
            step_id=step_id,
            recoverable=True,
        )

    return RuntimeErrorInfo(
        category=ErrorCategory.SYSTEM,
        message=str(exc),
        phase=phase,
        step_id=step_id,
        recoverable=False,
    )
