# Engine（API 参考）

## 职责

`Engine` 是唯一运行时内核，负责：

- 循环编排
- task/env 预检
- action 执行
- budget 与 stop 判定
- hooks/events/trace

## 运行链路

每一步：

1. DECIDE
2. ACT
3. REDUCE
4. CHECK_STOP

当 `agent.decide(...)` 返回 `None` 时，DECIDE 阶段会调用 `prepare(state)`。

## 默认模型路径

当 `decide` 返回 `None`，Engine 会：

1. `prepared = agent.prepare(state)`
2. 组装 messages（system + memory history + 当前 user 输入）
3. `raw = agent.llm(messages)`
4. parser 解析成 `Decision`

## 常用参数

- `env`
- `hooks`
- `trace_writer`
- `memory`（便捷注入到 `agent.memory`）

## 返回结果

`Engine.run(...)` 返回：

- `state`
- `records`
- `events`
- `step_count`
- `task_result`（可选）
