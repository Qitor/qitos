# Decision 与 Action

## 目标

理解 QitOS 里“标准化意图层”是如何工作的。

## Decision

`Decision` 描述下一步策略意图：

- `act`：执行动作（工具调用）
- `wait`：本步不执行动作但继续
- `final`：终止并给出最终结果

## Action

`Action` 是标准化的工具调用：

- `name`：工具名
- `args`：参数
- `max_retries/timeout_s`：执行策略

## 实用规则

如果希望 Engine 自动调用模型，请让 `AgentModule.decide` 返回 `None`。

## Source Index

- [qitos/core/decision.py](https://github.com/Qitor/qitos/blob/main/qitos/core/decision.py)
- [qitos/core/action.py](https://github.com/Qitor/qitos/blob/main/qitos/core/action.py)
- [qitos/engine/action_executor.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/action_executor.py)
