"""FSM state and event model for QitOS v2 engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RuntimePhase(str, Enum):
    INIT = "INIT"
    OBSERVE = "OBSERVE"
    DECIDE = "DECIDE"
    ACT = "ACT"
    REDUCE = "REDUCE"
    CHECK_STOP = "CHECK_STOP"
    END = "END"
    DECIDE_ERROR = "DECIDE_ERROR"
    ACT_ERROR = "ACT_ERROR"
    RECOVER = "RECOVER"


@dataclass
class RuntimeBudget:
    max_steps: int = 20
    max_runtime_seconds: Optional[float] = None
    max_tokens: Optional[int] = None


@dataclass
class RuntimeEvent:
    step_id: int
    phase: RuntimePhase
    ok: bool = True
    payload: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class StepRecord:
    step_id: int
    phase_events: List[RuntimeEvent] = field(default_factory=list)
    observation: Any = None
    decision: Any = None
    actions: List[Any] = field(default_factory=list)
    action_results: List[Any] = field(default_factory=list)
    state_diff: Dict[str, Any] = field(default_factory=dict)
