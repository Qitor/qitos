# `qitos.engine.engine`

- Module Group: `qitos.engine`
- Source: [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)

## Quick Jump

- [Classes](#classes)
- [Functions](#functions)
- [Class: `Engine`](#class-engine)
- [Class: `EngineResult`](#class-engineresult)

## Classes

<a id="class-engine"></a>
???+ note "Class: `Engine(self, agent: 'AgentModule[StateT, ObservationT, ActionT]', budget: 'Optional[RuntimeBudget]' = None, validation_gate: 'Optional[StateValidationGate]' = None, recovery_handler: 'Optional[RecoveryHandler]' = None, recovery_policy: 'Optional[RecoveryPolicy]' = None, trace_writer: 'Optional[TraceWriter]' = None, memory: 'Optional[Memory]' = None, parser: 'Optional[Parser[ActionT]]' = None, stop_criteria: 'Optional[List[StopCriteria]]' = None, branch_selector: 'Optional[BranchSelector[StateT, ObservationT, ActionT]]' = None, search: 'Optional[Search[StateT, ObservationT, ActionT]]' = None, critics: 'Optional[List[Critic]]' = None, env: 'Optional[Env]' = None, hooks: 'Optional[List[EngineHook]]' = None, render_hooks: 'Optional[List[Any]]' = None)`"
    Single execution kernel for all AgentModule workflows.

<a id="class-engineresult"></a>
???+ note "Class: `EngineResult(self, state: 'StateT', records: 'List[StepRecord]', events: 'List[RuntimeEvent]', step_count: 'int', task_result: 'Optional[TaskResult]' = None) -> None`"
    EngineResult(state: 'StateT', records: 'List[StepRecord]', events: 'List[RuntimeEvent]', step_count: 'int', task_result: 'Optional[TaskResult]' = None)

## Functions

- _None_

## Source Index

- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)