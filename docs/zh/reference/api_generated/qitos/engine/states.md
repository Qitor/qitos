# `qitos.engine.states`

- 模块分组: `qitos.engine`
- 源码: [qitos/engine/states.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/states.py)

## 快速跳转

- [类](#classes)
- [函数](#functions)
- [Class: `RuntimeBudget`](#class-runtimebudget)
- [Class: `RuntimeEvent`](#class-runtimeevent)
- [Class: `RuntimePhase`](#class-runtimephase)
- [Class: `StepRecord`](#class-steprecord)

## Classes

<a id="class-runtimebudget"></a>
???+ note "Class: `RuntimeBudget(self, max_steps: 'int' = 20, max_runtime_seconds: 'Optional[float]' = None, max_tokens: 'Optional[int]' = None) -> None`"
    RuntimeBudget(max_steps: 'int' = 20, max_runtime_seconds: 'Optional[float]' = None, max_tokens: 'Optional[int]' = None)

<a id="class-runtimeevent"></a>
???+ note "Class: `RuntimeEvent(self, step_id: 'int', phase: 'RuntimePhase', ok: 'bool' = True, payload: 'Dict[str, Any]' = <factory>, error: 'Optional[str]' = None, ts: 'str' = <factory>) -> None`"
    RuntimeEvent(step_id: 'int', phase: 'RuntimePhase', ok: 'bool' = True, payload: 'Dict[str, Any]' = <factory>, error: 'Optional[str]' = None, ts: 'str' = <factory>)

<a id="class-runtimephase"></a>
???+ note "Class: `RuntimePhase(self, *args, **kwds)`"
    str(object='') -> str

<a id="class-steprecord"></a>
???+ note "Class: `StepRecord(self, step_id: 'int', phase_events: 'List[RuntimeEvent]' = <factory>, observation: 'Any' = None, decision: 'Any' = None, actions: 'List[Any]' = <factory>, action_results: 'List[Any]' = <factory>, tool_invocations: 'List[Any]' = <factory>, critic_outputs: 'List[Any]' = <factory>, state_diff: 'Dict[str, Any]' = <factory>) -> None`"
    StepRecord(step_id: 'int', phase_events: 'List[RuntimeEvent]' = <factory>, observation: 'Any' = None, decision: 'Any' = None, actions: 'List[Any]' = <factory>, action_results: 'List[Any]' = <factory>, tool_invocations: 'List[Any]' = <factory>, critic_outputs: 'List[Any]' = <factory>, state_diff: 'Dict[str, Any]' = <factory>)

## Functions

- _无_

## Source Index

- [qitos/engine/states.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/states.py)