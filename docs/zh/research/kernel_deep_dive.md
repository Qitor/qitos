# 内核深度拆解

## 目标

建立一套“可推演”的内核心智模型：一次 `Engine.run(...)` 到底如何流转，数据在哪一层被构造与修改，扩展点应该放在哪里。

## 1）标准执行链路

一次运行大致分为：

1. 初始化状态（`agent.init_state`）
2. 预检（Task 校验 + Env 能力校验）
3. 逐步循环：
- `observe`
- `decide`
- `act`
- `reduce`
- `critic`（可选）
- `check_stop`
4. 收尾（trace 与 task result）

这条链路是 QitOS 可调试与可复现的基础。

## 2）生命周期 phase 语义（核心契约）

这一节强调的是 **语义契约**，不是“代码顺序复述”。
你在实现新的 agent/parser/critic/env 时，应该尽量贴合这些含义，否则可比较性与可复盘性会变差。

### Phase：`INIT`

目的：

- 启动一次新的 run，并生成稳定的 `run_id`
- 重置运行时组件（`Memory.reset`、recovery policy reset）
- 补齐 trace 元信息并写入 run 级身份
- 做预检：Task 合法性 + Env 能力匹配

输入：

- `task`（字符串或 `Task`）
- agent 配置（`AgentModule.__init__` + state kwargs）

输出：

- `agent.init_state(...)` 返回的初始 `StateSchema`

不变量：

- `state.task` 必须被设置
- 第一次 `OBSERVE` 之前，tool registry 与 env 都应该 ready

可观测性：

- 发送 `RuntimePhase.INIT` event
- 触发 hook：`on_run_start(...)`

### Phase：`OBSERVE`

目的：

- 构造“当前步”可决策的 observation（agent 定义的结构）

输入：

- `state`（唯一事实来源）
- `env_view`（预算/元信息/env 信息/以及 *memory context view*）

输出：

- `observation`

建议：

- observation 必须 **有界**（截断历史）
- 不要把整个 state 原封不动塞给模型

副作用：

- 如果启用 memory，Engine 会把 observation 追加到 memory 记录里（用于复盘）

可观测性：

- 发送 `RuntimePhase.OBSERVE` events（`start`、`observation_ready`）
- 触发 hook：`on_before_observe`、`on_after_observe`

### Phase：`DECIDE`

目的：

- 将 observation 转成标准化 `Decision`（act/final/wait/branch）

输入：

- `state`
- `observation`

输出：

- `Decision[Action]`（写入 `StepRecord.decision`）

两条决策路径：

1. Agent 自己决定：
   - `AgentModule.decide(...) -> Decision`
   - 适合确定性策略、规则逻辑、无需模型时
2. Engine 驱动模型：
   - `AgentModule.decide(...) -> None`
   - Engine 自动执行：
     - `prepared = agent.prepare(state, observation)`（字符串）
     - `system = agent.build_system_prompt(state)`（可选）
     - `history = memory.retrieve_messages(state, observation, query={})`（若提供 memory）
     - `raw_output = agent.llm(messages)`
     - `Decision = parser.parse(raw_output, context={...})`

重要细节：

- `AgentModule.build_memory_query(...)` 目前主要影响 **`env_view["memory"]` 的展示上下文**，
  但 Engine 在模型路径里取 history 时使用的是 `retrieve_messages(..., query={})`。
  因此 `env_view["memory"]` 更像“可调试的 memory 视图”，并不等同于“模型真实上下文”。

分支选择：

- 如果 `Decision.mode == "branch"`，Engine 会选择一个候选：
  - 优先走 `Search`（若提供），否则用 `BranchSelector`

可观测性：

- 发送 `RuntimePhase.DECIDE` events（`start`、`model_input`、`model_output`、`decision_ready`）
- 失败时会发送 `DECIDE_ERROR`，随后发送 `RECOVER`
- 触发 hook：`on_before_decide`、`on_after_decide`

### Phase：`ACT`

目的：

- 在 `Decision.mode == "act"` 时执行工具动作

输入：

- `Decision.actions`（标准化 `Action(name, args)`）
- `Env`（可选，但若工具需要 ops groups 则必须提供）

输出：

- `action_results: list[Any]`（写入 `StepRecord.action_results`）

执行路径：

- `ActionExecutor.execute(...)`
- `ToolRegistry.call(tool_name, args, runtime_context={env, ops, state, ...})`
- Engine 从 Env 解析 ops groups，并在必要时注入（高级用法）

可观测性：

- 发送 `RuntimePhase.ACT` events（`start`、`skipped`、`action_results`）
- 失败时会发送 `ACT_ERROR`，随后发送 `RECOVER`
- 触发 hook：`on_before_act`、`on_after_act`

### Phase：`REDUCE`

目的：

- 用 observation + decision + action_results 更新 state

输入：

- `state`（前态）
- `observation`
- `Decision`
- `action_results`

输出：

- 更新后的 state（原地 mutate 或返回新对象）
- `state_diff` 写入 `StepRecord.state_diff`

建议：

- `reduce` 尽量保持“纯状态转移”（不要在这里做 I/O）
- 必须留下足够的 breadcrumbs（scratchpad、plan cursor 等）便于调试

可观测性：

- 发送 `RuntimePhase.REDUCE` events（`start`、`state_reduced`）
- 触发 hook：`on_before_reduce`、`on_after_reduce`

### Phase：`CRITIC`（可选）

目的：

- 对“当前步结果”做评估，必要时请求 retry/stop

输入：

- 更新后的 state
- 本步 decision + results

输出：

- `"continue" | "retry" | "stop"`

可观测性：

- 发送 `RuntimePhase.CRITIC` events（`start`、`outputs_ready`）
- 触发 hook：`on_before_critic`、`on_after_critic`

### Phase：`CHECK_STOP`

目的：

- 判定是否停止，并写入标准 stop_reason

停止来源（大致优先级）：

1. `Decision.mode == "final"` => `StopReason.FINAL` + `final_answer`
2. `AgentModule.should_stop(state)` => `StopReason.AGENT_CONDITION`（若尚未设置）
3. `Env.is_terminal(...)` => `StopReason.ENV_TERMINAL`
4. stop criteria 与预算：
   - `StopReason.BUDGET_STEPS`、`StopReason.BUDGET_TIME`、`StopReason.BUDGET_TOKENS` 等

可观测性：

- 发送 `RuntimePhase.CHECK_STOP` events（`start`、`continue`、`stop`）
- 触发 hook：`on_before_check_stop`、`on_after_check_stop`

### Phase：`END`

目的：

- finalize trace（manifest + summary），返回 `EngineResult`

可观测性：

- 发送 `RuntimePhase.END` event（包含 `stop_reason`）
- 触发 hook：`on_run_end(...)`

### 错误与恢复 phases

当逐步循环内部发生异常时，Engine 会：

1. 根据失败位置发送 `DECIDE_ERROR` 或 `ACT_ERROR`
2. 发送 `RECOVER`
3. 调用 `RecoveryPolicy.handle(...)` 决定继续还是停止

若最终停止，使用 `StopReason.UNRECOVERABLE_ERROR`。

## 2）核心模块职责边界

### `AgentModule`

负责“策略语义”：

- 观察如何组织
- 决策如何产生
- 状态如何更新

### `Engine`

负责“执行语义”：

- 循环顺序
- 预算约束
- hook 触发
- 事件与 trace 写入

### `Decision` / `Action`

负责“标准化意图表达”：

- 是否执行动作
- 执行哪些动作与参数

### `Env`

负责“能力后端”：

- 提供 ops groups
- 屏蔽 host/docker/repo 差异

### `Memory`

负责“上下文检索与写入”：

- 供模型输入使用
- 供调试与复盘使用

## 3）两条决策路径（非常关键）

### 路径 A：Agent 自己决定

`decide` 直接返回 `Decision`。

适合：

- 规则策略
- 确定性控制逻辑

### 路径 B：Engine 驱动模型决策

`decide` 返回 `None`，Engine 自动执行：

1. `prepare`
2. 消息组装
3. `llm(messages)`
4. parser -> `Decision`

适合：

- LLM 驱动策略
- 需要 parser 约束输出格式

## 4）为何这种设计对研究友好

1. 单轴替换容易（parser/memory/critic/env）
2. 多方案比较口径一致
3. 失败能定位到具体 phase
4. trace 可直接作为实验证据

## 5）典型反模式

1. 把编排逻辑塞进 Agent 内部
2. 在 parser/prompt 里混入环境后端细节
3. 关键状态放在局部变量不进入 StateSchema
4. 一次实验同时改多个变量

## Source Index

- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/core/state.py](https://github.com/Qitor/qitos/blob/main/qitos/core/state.py)
- [qitos/core/decision.py](https://github.com/Qitor/qitos/blob/main/qitos/core/decision.py)
- [qitos/core/action.py](https://github.com/Qitor/qitos/blob/main/qitos/core/action.py)
- [qitos/core/env.py](https://github.com/Qitor/qitos/blob/main/qitos/core/env.py)
- [qitos/core/memory.py](https://github.com/Qitor/qitos/blob/main/qitos/core/memory.py)
- [qitos/engine/hooks.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/hooks.py)
