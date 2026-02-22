# StopReason

## 目标

stop reason 是调试与评测的稳定契约。

## 它是什么

`StopReason` 是标准化的枚举（以字符串形式存放在 `StateSchema.stop_reason`）。

它让 QitOS 的运行结果可以被严格比较：

- 不同 prompt/parser/tool
- 不同 Env 后端
- 不同 recovery 策略

## 常见 stop reason（含语义）

- `success`：成功结束（可能由 task/env 包装层设置）
- `final`：产出了最终答案
- `max_steps` / `budget_steps`：步数预算用尽
- `budget_time`：运行时长预算用尽
- `budget_tokens`：token 预算用尽（模型侧）
- `agent_condition`：`AgentModule.should_stop(...)` 请求停止
- `critic_stop`：critic 请求停止（如果启用 critic）
- `stagnation`：停滞检测触发停止（如果启用）
- `env_terminal`：环境终止（例如容器退出）
- `task_validation_failed`：Task/env_spec/budget 不合法
- `env_capability_mismatch`：工具声明的 ops groups 无法由 Env 提供
- `unrecoverable_error`：不可恢复错误导致停止（recovery 策略判定）

## 如何正确设置 stop_reason

建议通过 state 的方法来设置：

```python
from qitos.core.errors import StopReason

state.set_stop(StopReason.FINAL, final_result="done")
```

避免随意字符串：`StateSchema.validate()` 会强制 stop_reason 必须属于 `StopReason`。

## Source Index

- [qitos/core/errors.py](https://github.com/Qitor/qitos/blob/main/qitos/core/errors.py)
- [qitos/engine/recovery.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/recovery.py)
