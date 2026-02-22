# `qitos.engine.recovery`

- 模块分组: `qitos.engine`
- 源码: [qitos/engine/recovery.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/recovery.py)

## 快速跳转

- [类](#classes)
- [函数](#functions)
- [Class: `FailureDiagnostic`](#class-failurediagnostic)
- [Class: `RecoveryDecision`](#class-recoverydecision)
- [Class: `RecoveryPolicy`](#class-recoverypolicy)
- [Class: `RecoveryTracker`](#class-recoverytracker)
- [Function: `build_failure_report`](#function-build-failure-report)

## Classes

<a id="class-failurediagnostic"></a>
???+ note "Class: `FailureDiagnostic(self, step_id: 'int', phase: 'str', category: 'str', message: 'str', recoverable: 'bool', decision: 'str', recommendation: 'str') -> None`"
    FailureDiagnostic(step_id: 'int', phase: 'str', category: 'str', message: 'str', recoverable: 'bool', decision: 'str', recommendation: 'str')

<a id="class-recoverydecision"></a>
???+ note "Class: `RecoveryDecision(self, handled: 'bool', continue_run: 'bool', stop_reason: 'Optional[StopReason]' = None, note: 'Optional[str]' = None) -> None`"
    RecoveryDecision(handled: 'bool', continue_run: 'bool', stop_reason: 'Optional[StopReason]' = None, note: 'Optional[str]' = None)

<a id="class-recoverypolicy"></a>
???+ note "Class: `RecoveryPolicy(self, max_recoveries_per_run: 'int' = 3)`"
    Default runtime recovery policy.

<a id="class-recoverytracker"></a>
???+ note "Class: `RecoveryTracker(self, diagnostics: 'List[FailureDiagnostic]' = <factory>) -> None`"
    RecoveryTracker(diagnostics: 'List[FailureDiagnostic]' = <factory>)

## Functions

<a id="function-build-failure-report"></a>
???+ note "Function: `build_failure_report(policy: 'RecoveryPolicy', stop_reason: 'Optional[str]') -> 'Dict[str, Any]'`"
    _No summary available._

## Source Index

- [qitos/engine/recovery.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/recovery.py)