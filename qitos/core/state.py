"""Typed state schema and migration utilities for QitOS kernel."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, ClassVar, Dict, List, Optional, Tuple, Type, TypeVar

from .errors import StopReason


MigrationFn = Callable[[Dict[str, Any]], Dict[str, Any]]
StateT = TypeVar("StateT", bound="StateSchema")


class StateValidationError(ValueError):
    """Raised when state validation fails."""


class StateMigrationError(ValueError):
    """Raised when state migration fails."""


class StateMigrationRegistry:
    """Simple in-process migration graph for state schema versions."""

    def __init__(self):
        self._migrations: Dict[Tuple[int, int], MigrationFn] = {}

    def register(self, from_version: int, to_version: int, fn: MigrationFn) -> None:
        if to_version <= from_version:
            raise StateMigrationError("to_version must be greater than from_version")
        self._migrations[(from_version, to_version)] = fn

    def migrate(self, payload: Dict[str, Any], from_version: int, to_version: int) -> Dict[str, Any]:
        if from_version == to_version:
            return payload

        current = from_version
        output = dict(payload)

        while current < to_version:
            step = (current, current + 1)
            if step not in self._migrations:
                raise StateMigrationError(
                    f"Missing migration path from v{current} to v{current + 1}"
                )
            output = self._migrations[step](output)
            current += 1

        return output


@dataclass
class PlanState:
    """Structured plan state for planner-executor style agents."""

    steps: List[str] = field(default_factory=list)
    cursor: int = 0
    status: str = "idle"  # idle | executing | completed


@dataclass
class StateSchema:
    """Canonical typed state base for AgentModule."""

    schema_version: int = 1
    task: str = ""
    current_step: int = 0
    max_steps: int = 10
    final_result: Optional[str] = None
    stop_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    memory: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    plan: PlanState = field(default_factory=PlanState)

    # Subclasses can override this and set their own registry.
    migration_registry: ClassVar[StateMigrationRegistry] = StateMigrationRegistry()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls: Type[StateT], payload: Dict[str, Any], strict: bool = True) -> StateT:
        from dataclasses import fields

        known_fields = {f.name for f in fields(cls)}
        unknown_fields = [k for k in payload.keys() if k not in known_fields]

        if strict and unknown_fields:
            raise StateValidationError(f"Unknown state fields: {unknown_fields}")

        filtered = {k: v for k, v in payload.items() if k in known_fields}

        # Handle nested plan dict input.
        if "plan" in filtered and isinstance(filtered["plan"], dict):
            filtered["plan"] = PlanState(**filtered["plan"])

        obj = cls(**filtered)
        obj.validate()
        return obj

    @classmethod
    def migrate_payload(cls, payload: Dict[str, Any], target_version: int) -> Dict[str, Any]:
        from_version = int(payload.get("schema_version", 1))
        migrated = cls.migration_registry.migrate(payload, from_version, target_version)
        migrated["schema_version"] = target_version
        return migrated

    def validate(self) -> None:
        if not isinstance(self.task, str):
            raise StateValidationError("task must be a string")
        if self.current_step < 0:
            raise StateValidationError("current_step must be >= 0")
        if self.max_steps <= 0:
            raise StateValidationError("max_steps must be > 0")
        if self.current_step > self.max_steps:
            raise StateValidationError("current_step cannot exceed max_steps")
        if self.final_result is not None and not isinstance(self.final_result, str):
            raise StateValidationError("final_result must be a string when provided")
        if self.stop_reason is not None:
            try:
                StopReason(str(self.stop_reason))
            except ValueError as exc:
                raise StateValidationError(f"invalid stop_reason: {self.stop_reason}") from exc
        if self.plan.cursor < 0:
            raise StateValidationError("plan.cursor must be >= 0")
        if self.plan.status not in {"idle", "executing", "completed"}:
            raise StateValidationError("plan.status must be one of: idle/executing/completed")
        if self.plan.cursor > len(self.plan.steps):
            raise StateValidationError("plan.cursor cannot exceed number of plan steps")

    def set_stop(self, reason: StopReason | str, final_result: Optional[str] = None) -> None:
        if isinstance(reason, StopReason):
            self.stop_reason = reason.value
        else:
            self.stop_reason = StopReason(str(reason)).value
        if final_result is not None:
            self.final_result = final_result

    def advance_step(self) -> None:
        self.current_step += 1
        self.validate()

    def mark_plan_executing(self, steps: List[str]) -> None:
        self.plan.steps = steps
        self.plan.cursor = 0
        self.plan.status = "executing" if steps else "idle"
        self.validate()

    def mark_plan_step_done(self) -> None:
        if self.plan.cursor < len(self.plan.steps):
            self.plan.cursor += 1
        if self.plan.cursor >= len(self.plan.steps) and self.plan.steps:
            self.plan.status = "completed"
        self.validate()
