# `qitos.core.errors`

- 模块分组: `qitos.core`
- 源码: [qitos/core/errors.py](https://github.com/Qitor/qitos/blob/main/qitos/core/errors.py)

## 快速跳转

- [类](#classes)
- [函数](#functions)
- [Class: `ErrorCategory`](#class-errorcategory)
- [Class: `ModelExecutionError`](#class-modelexecutionerror)
- [Class: `ParseExecutionError`](#class-parseexecutionerror)
- [Class: `QitosRuntimeError`](#class-qitosruntimeerror)
- [Class: `RuntimeErrorInfo`](#class-runtimeerrorinfo)
- [Class: `StateExecutionError`](#class-stateexecutionerror)
- [Class: `StopReason`](#class-stopreason)
- [Class: `SystemExecutionError`](#class-systemexecutionerror)
- [Class: `ToolExecutionError`](#class-toolexecutionerror)
- [Function: `classify_exception`](#function-classify-exception)

## Classes

<a id="class-errorcategory"></a>
???+ note "Class: `ErrorCategory(self, *args, **kwds)`"
    str(object='') -> str

<a id="class-modelexecutionerror"></a>
???+ note "Class: `ModelExecutionError(self, info: 'RuntimeErrorInfo')`"
    Common base class for all non-exit exceptions.

<a id="class-parseexecutionerror"></a>
???+ note "Class: `ParseExecutionError(self, info: 'RuntimeErrorInfo')`"
    Common base class for all non-exit exceptions.

<a id="class-qitosruntimeerror"></a>
???+ note "Class: `QitosRuntimeError(self, info: 'RuntimeErrorInfo')`"
    Common base class for all non-exit exceptions.

<a id="class-runtimeerrorinfo"></a>
???+ note "Class: `RuntimeErrorInfo(self, category: 'ErrorCategory', message: 'str', phase: 'str', step_id: 'int', recoverable: 'bool' = False, details: 'Dict[str, Any]' = <factory>) -> None`"
    RuntimeErrorInfo(category: 'ErrorCategory', message: 'str', phase: 'str', step_id: 'int', recoverable: 'bool' = False, details: 'Dict[str, Any]' = <factory>)

<a id="class-stateexecutionerror"></a>
???+ note "Class: `StateExecutionError(self, info: 'RuntimeErrorInfo')`"
    Common base class for all non-exit exceptions.

<a id="class-stopreason"></a>
???+ note "Class: `StopReason(self, *args, **kwds)`"
    str(object='') -> str

<a id="class-systemexecutionerror"></a>
???+ note "Class: `SystemExecutionError(self, info: 'RuntimeErrorInfo')`"
    Common base class for all non-exit exceptions.

<a id="class-toolexecutionerror"></a>
???+ note "Class: `ToolExecutionError(self, info: 'RuntimeErrorInfo')`"
    Common base class for all non-exit exceptions.

## Functions

<a id="function-classify-exception"></a>
???+ note "Function: `classify_exception(exc: 'Exception', phase: 'str', step_id: 'int') -> 'RuntimeErrorInfo'`"
    _No summary available._

## Source Index

- [qitos/core/errors.py](https://github.com/Qitor/qitos/blob/main/qitos/core/errors.py)