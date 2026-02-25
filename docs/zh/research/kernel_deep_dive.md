# 内核深度拆解

## 一次运行的精确流程

`Engine.run(task)`：

1. 初始化状态（`agent.init_state`）
2. 预检（task/env）
3. 循环：`DECIDE -> ACT -> REDUCE -> CHECK_STOP`
4. 收尾（trace/task_result）

## 各阶段语义

### INIT

- 重置运行时组件
- 准备 env/toolset
- 发送 run_start 事件

### DECIDE

输入：
- `state`
- 上一轮 `observation`

两条路径：
1. `agent.decide(...)` 返回 `Decision`
2. 返回 `None` 走默认模型路径：
- `prepare(state)`
- 组装 messages（system + history + user）
- `llm(messages)`
- parser -> `Decision`

### ACT

- 通过 `ActionExecutor` 执行工具动作
- 更新 `record.action_results`
- env step 输出并入动作结果

### REDUCE

- 调用 `agent.reduce(state, observation, decision)`
- `observation` 承载步骤输出（`action_results`、env 数据、状态快照）
- 计算 `state_diff`

### CHECK_STOP

停止来源包括：
- `decision.mode == final`
- `agent.should_stop(state)`
- env terminal
- budget / criteria

## Memory 与 History 语义

- Memory 归属 agent（`agent.memory`），用于存储运行工件（`task/decision/action/observation/...`）。
- History 仅用于模型消息（`agent.history` 或 engine 运行时 history）。
- Engine 使用 `history_policy` 组装模型输入消息。
- `observation` 默认不包含 memory/history。

## Hook 体系

主要回调族：
- run：`on_run_start`、`on_run_end`
- step：`on_before_step`、`on_after_step`
- phase：`on_before_decide/act/reduce/check_stop` 与 `on_after_*`
- recovery/event：`on_recover`、`on_event`
