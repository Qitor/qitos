# `qitos.engine.validation`

- Module Group: `qitos.engine`
- Source: [qitos/engine/validation.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/validation.py)

## Quick Jump

- [Classes](#classes)
- [Functions](#functions)
- [Class: `StateValidationGate`](#class-statevalidationgate)
- [Class: `StateValidatorChain`](#class-statevalidatorchain)
- [Function: `validate_final_consistency`](#function-validate-final-consistency)
- [Function: `validate_plan_cursor`](#function-validate-plan-cursor)
- [Function: `validate_step_bounds`](#function-validate-step-bounds)

## Classes

<a id="class-statevalidationgate"></a>
???+ note "Class: `StateValidationGate(self, validators: 'Iterable[Validator]' = [<function validate_step_bounds at 0x104d6ff60>, <function validate_plan_cursor at 0x104d905e0>, <function validate_final_consistency at 0x104d90680>])`"
    Run validation checks before and after each engine phase.

<a id="class-statevalidatorchain"></a>
???+ note "Class: `StateValidatorChain(self, validators: 'List[Validator]') -> None`"
    StateValidatorChain(validators: 'List[Validator]')

## Functions

<a id="function-validate-final-consistency"></a>
???+ note "Function: `validate_final_consistency(state: 'StateSchema') -> 'None'`"
    _No summary available._

<a id="function-validate-plan-cursor"></a>
???+ note "Function: `validate_plan_cursor(state: 'StateSchema') -> 'None'`"
    _No summary available._

<a id="function-validate-step-bounds"></a>
???+ note "Function: `validate_step_bounds(state: 'StateSchema') -> 'None'`"
    _No summary available._

## Source Index

- [qitos/engine/validation.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/validation.py)