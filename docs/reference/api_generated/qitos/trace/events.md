# `qitos.trace.events`

- Module Group: `qitos.trace`
- Source: [qitos/trace/events.py](https://github.com/Qitor/qitos/blob/main/qitos/trace/events.py)

## Quick Jump

- [Classes](#classes)
- [Functions](#functions)
- [Class: `TraceEvent`](#class-traceevent)
- [Class: `TraceStep`](#class-tracestep)

## Classes

<a id="class-traceevent"></a>
???+ note "Class: `TraceEvent(self, run_id: 'str', step_id: 'int', phase: 'str', ok: 'bool' = True, payload: 'Dict[str, Any]' = <factory>, error: 'Optional[str]' = None, ts: 'str' = <factory>) -> None`"
    TraceEvent(run_id: 'str', step_id: 'int', phase: 'str', ok: 'bool' = True, payload: 'Dict[str, Any]' = <factory>, error: 'Optional[str]' = None, ts: 'str' = <factory>)

<a id="class-tracestep"></a>
???+ note "Class: `TraceStep(self, step_id: 'int', observation: 'Any' = None, decision: 'Any' = None, actions: 'List[Any]' = <factory>, action_results: 'List[Any]' = <factory>, tool_invocations: 'List[Any]' = <factory>, critic_outputs: 'List[Any]' = <factory>, state_diff: 'Dict[str, Any]' = <factory>) -> None`"
    TraceStep(step_id: 'int', observation: 'Any' = None, decision: 'Any' = None, actions: 'List[Any]' = <factory>, action_results: 'List[Any]' = <factory>, tool_invocations: 'List[Any]' = <factory>, critic_outputs: 'List[Any]' = <factory>, state_diff: 'Dict[str, Any]' = <factory>)

## Functions

- _None_

## Source Index

- [qitos/trace/events.py](https://github.com/Qitor/qitos/blob/main/qitos/trace/events.py)