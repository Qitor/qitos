# `qitos.engine.hooks`

- 模块分组: `qitos.engine`
- 源码: [qitos/engine/hooks.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/hooks.py)

## 快速跳转

- [类](#classes)
- [函数](#functions)
- [Class: `EngineHook`](#class-enginehook)
- [Class: `HookContext`](#class-hookcontext)

## Classes

<a id="class-enginehook"></a>
???+ note "Class: `EngineHook(self, /, *args, **kwargs)`"
    Base engine hook with full lifecycle callbacks.

<a id="class-hookcontext"></a>
???+ note "Class: `HookContext(self, task: 'str', step_id: 'int', phase: 'RuntimePhase', state: 'StateSchema', env_view: 'Optional[Dict[str, Any]]' = None, observation: 'Any' = None, decision: 'Any' = None, action_results: 'List[Any]' = <factory>, record: 'Optional[StepRecord]' = None, payload: 'Dict[str, Any]' = <factory>, error: 'Optional[Exception]' = None, stop_reason: 'Optional[str]' = None, run_id: 'str' = '', ts: 'str' = '') -> None`"
    HookContext(task: 'str', step_id: 'int', phase: 'RuntimePhase', state: 'StateSchema', env_view: 'Optional[Dict[str, Any]]' = None, observation: 'Any' = None, decision: 'Any' = None, action_results: 'List[Any]' = <factory>, record: 'Optional[StepRecord]' = None, payload: 'Dict[str, Any]' = <factory>, error: 'Optional[Exception]' = None, stop_reason: 'Optional[str]' = None, run_id: 'str' = '', ts: 'str' = '')

## Functions

- _无_

## Source Index

- [qitos/engine/hooks.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/hooks.py)