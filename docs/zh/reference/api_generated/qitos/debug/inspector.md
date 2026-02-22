# `qitos.debug.inspector`

- 模块分组: `qitos.debug`
- 源码: [qitos/debug/inspector.py](https://github.com/Qitor/qitos/blob/main/qitos/debug/inspector.py)

## 快速跳转

- [类](#classes)
- [函数](#functions)
- [Class: `InspectorPayload`](#class-inspectorpayload)
- [Function: `build_inspector_payload`](#function-build-inspector-payload)
- [Function: `compare_steps`](#function-compare-steps)

## Classes

<a id="class-inspectorpayload"></a>
???+ note "Class: `InspectorPayload(self, step_id: 'int', rationale: 'Optional[str]', decision_mode: 'Optional[str]', actions: 'list[Any]', tool_invocations: 'list[Any]', action_results: 'list[Any]', critic_outputs: 'list[Any]', state_diff: 'Dict[str, Any]', stop_reason: 'Optional[str]', remediation_hint: 'Optional[str]') -> None`"
    InspectorPayload(step_id: 'int', rationale: 'Optional[str]', decision_mode: 'Optional[str]', actions: 'list[Any]', tool_invocations: 'list[Any]', action_results: 'list[Any]', critic_outputs: 'list[Any]', state_diff: 'Dict[str, Any]', stop_reason: 'Optional[str]', remediation_hint: 'Optional[str]')

## Functions

<a id="function-build-inspector-payload"></a>
???+ note "Function: `build_inspector_payload(step: 'Dict[str, Any]', manifest: 'Optional[Dict[str, Any]]' = None) -> 'InspectorPayload'`"
    _No summary available._

<a id="function-compare-steps"></a>
???+ note "Function: `compare_steps(base_step: 'Dict[str, Any]', other_step: 'Dict[str, Any]') -> 'Dict[str, Any]'`"
    Return a compact comparison payload for two step snapshots.

## Source Index

- [qitos/debug/inspector.py](https://github.com/Qitor/qitos/blob/main/qitos/debug/inspector.py)