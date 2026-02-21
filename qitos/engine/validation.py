"""Runtime state validation gates for Engine execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, List

from ..core.state import StateSchema, StateValidationError


Validator = Callable[[StateSchema], None]


def validate_step_bounds(state: StateSchema) -> None:
    if state.current_step > state.max_steps:
        raise StateValidationError(
            f"current_step={state.current_step} exceeds max_steps={state.max_steps}"
        )


def validate_plan_cursor(state: StateSchema) -> None:
    if state.plan.cursor > len(state.plan.steps):
        raise StateValidationError("plan cursor exceeds available plan steps")


def validate_final_consistency(state: StateSchema) -> None:
    if state.stop_reason and not isinstance(state.stop_reason, str):
        raise StateValidationError("stop_reason must be a string")
    if state.stop_reason == "final" and not state.final_result:
        raise StateValidationError("stop_reason=final requires final_result")


DEFAULT_STATE_VALIDATORS: List[Validator] = [
    validate_step_bounds,
    validate_plan_cursor,
    validate_final_consistency,
]


@dataclass
class StateValidatorChain:
    validators: List[Validator]

    def validate(self, state: StateSchema) -> None:
        state.validate()
        for validator in self.validators:
            validator(state)


class StateValidationGate:
    """Run validation checks before and after each engine phase."""

    def __init__(self, validators: Iterable[Validator] = DEFAULT_STATE_VALIDATORS):
        self.chain = StateValidatorChain(list(validators))

    def before_phase(self, state: StateSchema, phase: str) -> None:
        self.chain.validate(state)

    def after_phase(self, state: StateSchema, phase: str) -> None:
        self.chain.validate(state)


__all__ = [
    "Validator",
    "DEFAULT_STATE_VALIDATORS",
    "StateValidatorChain",
    "StateValidationGate",
    "validate_step_bounds",
    "validate_plan_cursor",
    "validate_final_consistency",
]
