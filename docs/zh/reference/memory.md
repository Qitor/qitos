# Memory

## 目标

明确 QitOS 中 memory 的归属和用法。

## 归属

Memory 归属于 `AgentModule`（`self.memory`）。

- 推荐在 agent 构造时传入。

## 契约

`Memory` 提供：

- `append(record)`
- `retrieve(query, state, observation)`
- `summarize(max_items)`
- `reset(run_id)`

## 使用方式

1. 运行中，Engine 会把记录写入 `agent.memory`。
2. 自定义 agent 时，可在 `prepare(state)` 里直接读取 `self.memory`。

典型 memory 序列：

- `task`
- `state`
- `decision`
- `action`
- `observation`
- `next_state`
- ...

## 关键边界

`observation` 默认不应包含 memory。

- `observation` 用于承载步骤输出（`action_results`、env 数据、状态快照）。
- memory 由 `self.memory` 显式读取。
