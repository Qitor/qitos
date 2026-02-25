# History

## 目标

明确 QitOS 中消息历史（History）的归属和用法。

## 归属

History 归属于 `AgentModule`（`self.history`），未设置时使用 Engine 运行时 history。

## 契约

`History` 提供：

- `append(message)`
- `retrieve(query, state, observation)`
- `summarize(max_items)`
- `reset(run_id)`

## Engine 使用方式

默认模型路径（`decide -> None`）下，Engine 按如下顺序组装消息：

1. `system`（可选）
2. 按 `history_policy` 选择的 history 消息
3. 当前 `prepare(state)` 生成的 `user` 消息

Engine 会把当前轮 user/assistant 消息写入 history。

典型 history 序列：

- `system`
- `user`
- `assistant`
- `user`
- `assistant`
- ...

## HistoryPolicy

通过 Engine 配置：

- `roles`
- `max_messages`
- `step_window`

## Source Index

- [qitos/core/history.py](https://github.com/Qitor/qitos/blob/main/qitos/core/history.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [qitos/kit/history/window_history.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/history/window_history.py)
