# `qitos.engine.engine`

- 模块分组: `qitos.engine`
- 源码: [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)

## 快速跳转

- [类](#classes)
- [函数](#functions)
- [Class: `Engine`](#class-engine)
- [Class: `EngineResult`](#class-engineresult)

## Classes

<a id="class-engine"></a>
???+ note "Class: `Engine(self, agent: 'AgentModule[StateT, ObservationT, ActionT]', budget: 'Optional[RuntimeBudget]' = None, validation_gate: 'Optional[StateValidationGate]' = None, recovery_handler: 'Optional[RecoveryHandler]' = None, recovery_policy: 'Optional[RecoveryPolicy]' = None, trace_writer: 'Optional[TraceWriter]' = None, parser: 'Optional[Parser[ActionT]]' = None, stop_criteria: 'Optional[List[StopCriteria]]' = None, branch_selector: 'Optional[BranchSelector[StateT, ObservationT, ActionT]]' = None, search: 'Optional[Search[StateT, ObservationT, ActionT]]' = None, critics: 'Optional[List[Critic]]' = None, env: 'Optional[Env]' = None, history_policy: 'Optional[HistoryPolicy]' = None, hooks: 'Optional[List[EngineHook]]' = None, render_hooks: 'Optional[List[Any]]' = None)`"
    Single execution kernel for all AgentModule workflows.

<a id="class-engineresult"></a>
???+ note "Class: `EngineResult(self, state: 'StateT', records: 'List[StepRecord]', events: 'List[RuntimeEvent]', step_count: 'int', task_result: 'Optional[TaskResult]' = None) -> None`"
    EngineResult(state: 'StateT', records: 'List[StepRecord]', events: 'List[RuntimeEvent]', step_count: 'int', task_result: 'Optional[TaskResult]' = None)

## Functions

- _无_

## Source Index

- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)