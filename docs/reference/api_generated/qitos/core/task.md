# `qitos.core.task`

- Module Group: `qitos.core`
- Source: [qitos/core/task.py](https://github.com/Qitor/qitos/blob/main/qitos/core/task.py)

## Quick Jump

- [Classes](#classes)
- [Functions](#functions)
- [Class: `Task`](#class-task)
- [Class: `TaskBudget`](#class-taskbudget)
- [Class: `TaskCriterionResult`](#class-taskcriterionresult)
- [Class: `TaskResource`](#class-taskresource)
- [Class: `TaskResourceBinding`](#class-taskresourcebinding)
- [Class: `TaskResult`](#class-taskresult)
- [Class: `TaskValidationIssue`](#class-taskvalidationissue)

## Classes

<a id="class-task"></a>
???+ note "Class: `Task(self, id: 'str', objective: 'str', inputs: 'Dict[str, Any]' = <factory>, resources: 'List[TaskResource]' = <factory>, env_spec: 'Optional[EnvSpec]' = None, constraints: 'Dict[str, Any]' = <factory>, success_criteria: 'List[str]' = <factory>, budget: 'TaskBudget' = <factory>, metadata: 'Dict[str, Any]' = <factory>) -> None`"
    Task package with objective, resources, and environment requirements.

<a id="class-taskbudget"></a>
???+ note "Class: `TaskBudget(self, max_steps: 'Optional[int]' = None, max_runtime_seconds: 'Optional[float]' = None, max_tokens: 'Optional[int]' = None) -> None`"
    Task-level budget contract.

<a id="class-taskcriterionresult"></a>
???+ note "Class: `TaskCriterionResult(self, criterion: 'str', passed: 'bool', evidence: 'str' = '') -> None`"
    TaskCriterionResult(criterion: 'str', passed: 'bool', evidence: 'str' = '')

<a id="class-taskresource"></a>
???+ note "Class: `TaskResource(self, kind: 'str', path: 'Optional[str]' = None, uri: 'Optional[str]' = None, mount_to: 'Optional[str]' = None, required: 'bool' = True, description: 'str' = '', metadata: 'Dict[str, Any]' = <factory>) -> None`"
    One resource entry required by a task.

<a id="class-taskresourcebinding"></a>
???+ note "Class: `TaskResourceBinding(self, kind: 'str', source: 'str', target: 'Optional[str]' = None, exists: 'bool' = False, required: 'bool' = True, metadata: 'Dict[str, Any]' = <factory>) -> None`"
    TaskResourceBinding(kind: 'str', source: 'str', target: 'Optional[str]' = None, exists: 'bool' = False, required: 'bool' = True, metadata: 'Dict[str, Any]' = <factory>)

<a id="class-taskresult"></a>
???+ note "Class: `TaskResult(self, task_id: 'str', success: 'bool', stop_reason: 'Optional[str]', final_result: 'Any', criteria: 'List[TaskCriterionResult]' = <factory>, artifacts: 'List[TaskResourceBinding]' = <factory>, metrics: 'Dict[str, Any]' = <factory>, metadata: 'Dict[str, Any]' = <factory>) -> None`"
    TaskResult(task_id: 'str', success: 'bool', stop_reason: 'Optional[str]', final_result: 'Any', criteria: 'List[TaskCriterionResult]' = <factory>, artifacts: 'List[TaskResourceBinding]' = <factory>, metrics: 'Dict[str, Any]' = <factory>, metadata: 'Dict[str, Any]' = <factory>)

<a id="class-taskvalidationissue"></a>
???+ note "Class: `TaskValidationIssue(self, code: 'str', message: 'str', field: 'str', details: 'Dict[str, Any]' = <factory>) -> None`"
    TaskValidationIssue(code: 'str', message: 'str', field: 'str', details: 'Dict[str, Any]' = <factory>)

## Functions

- _None_

## Source Index

- [qitos/core/task.py](https://github.com/Qitor/qitos/blob/main/qitos/core/task.py)