"""Engine hook contracts for runtime extensibility."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from ..core.state import StateSchema
from .states import RuntimeEvent, RuntimePhase, StepRecord

if TYPE_CHECKING:
    from .engine import Engine, EngineResult


@dataclass
class HookContext:
    task: str
    step_id: int
    phase: RuntimePhase
    state: StateSchema
    env_view: Optional[Dict[str, Any]] = None
    observation: Any = None
    decision: Any = None
    action_results: List[Any] = field(default_factory=list)
    record: Optional[StepRecord] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    error: Optional[Exception] = None
    stop_reason: Optional[str] = None


class EngineHook:
    """Base engine hook with full lifecycle callbacks."""

    # Run lifecycle
    def on_run_start(self, task: str, state: StateSchema, engine: "Engine") -> None:
        pass

    def on_run_end(self, result: "EngineResult", engine: "Engine") -> None:
        pass

    # Step lifecycle
    def on_before_step(self, ctx: HookContext, engine: "Engine") -> None:
        pass

    def on_after_step(self, ctx: HookContext, engine: "Engine") -> None:
        pass

    # Observe
    def on_before_observe(self, ctx: HookContext, engine: "Engine") -> None:
        pass

    def on_after_observe(self, ctx: HookContext, engine: "Engine") -> None:
        pass

    # Decide
    def on_before_decide(self, ctx: HookContext, engine: "Engine") -> None:
        pass

    def on_after_decide(self, ctx: HookContext, engine: "Engine") -> None:
        pass

    # Act
    def on_before_act(self, ctx: HookContext, engine: "Engine") -> None:
        pass

    def on_after_act(self, ctx: HookContext, engine: "Engine") -> None:
        pass

    # Reduce
    def on_before_reduce(self, ctx: HookContext, engine: "Engine") -> None:
        pass

    def on_after_reduce(self, ctx: HookContext, engine: "Engine") -> None:
        pass

    # Critic
    def on_before_critic(self, ctx: HookContext, engine: "Engine") -> None:
        pass

    def on_after_critic(self, ctx: HookContext, engine: "Engine") -> None:
        pass

    # Stop check
    def on_before_check_stop(self, ctx: HookContext, engine: "Engine") -> None:
        pass

    def on_after_check_stop(self, ctx: HookContext, engine: "Engine") -> None:
        pass

    # Recovery
    def on_recover(self, ctx: HookContext, engine: "Engine") -> None:
        pass

    # Compatibility/event stream callbacks
    def on_event(
        self,
        event: RuntimeEvent,
        state: StateSchema,
        record: Optional[StepRecord],
        engine: "Engine",
    ) -> None:
        pass

    def on_step_end(self, record: StepRecord, state: StateSchema, engine: "Engine") -> None:
        pass


__all__ = ["EngineHook", "HookContext"]
