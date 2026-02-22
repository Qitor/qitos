# `qitos.core.action`

- Module Group: `qitos.core`
- Source: [qitos/core/action.py](https://github.com/Qitor/qitos/blob/main/qitos/core/action.py)

## Quick Jump

- [Classes](#classes)
- [Functions](#functions)
- [Class: `Action`](#class-action)
- [Class: `ActionExecutionPolicy`](#class-actionexecutionpolicy)
- [Class: `ActionKind`](#class-actionkind)
- [Class: `ActionResult`](#class-actionresult)
- [Class: `ActionStatus`](#class-actionstatus)

## Classes

<a id="class-action"></a>
???+ note "Class: `Action(self, name: 'str', args: 'Dict[str, Any]' = <factory>, kind: 'ActionKind' = <ActionKind.TOOL: 'tool'>, action_id: 'Optional[str]' = None, timeout_s: 'Optional[float]' = None, max_retries: 'int' = 0, idempotent: 'bool' = True, classification: 'str' = 'default', metadata: 'Dict[str, Any]' = <factory>) -> None`"
    Normalized action contract emitted by policy and consumed by executor.

<a id="class-actionexecutionpolicy"></a>
???+ note "Class: `ActionExecutionPolicy(self, mode: 'str' = 'serial', fail_fast: 'bool' = False, max_concurrency: 'int' = 4) -> None`"
    Executor policy for action batches.

<a id="class-actionkind"></a>
???+ note "Class: `ActionKind(self, *args, **kwds)`"
    str(object='') -> str

<a id="class-actionresult"></a>
???+ note "Class: `ActionResult(self, name: 'str', status: 'ActionStatus', output: 'Any' = None, error: 'Optional[str]' = None, action_id: 'Optional[str]' = None, attempts: 'int' = 1, latency_ms: 'float' = 0.0, metadata: 'Dict[str, Any]' = <factory>) -> None`"
    Standardized action execution result.

<a id="class-actionstatus"></a>
???+ note "Class: `ActionStatus(self, *args, **kwds)`"
    str(object='') -> str

## Functions

- _None_

## Source Index

- [qitos/core/action.py](https://github.com/Qitor/qitos/blob/main/qitos/core/action.py)