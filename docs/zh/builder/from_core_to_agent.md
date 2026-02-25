# 从 Core 到 Agent 实战

## 目标

把“理解接口”转成“可交付 Agent”：从零实现、接入模型、绑定工具、上线前加固。

## Milestone 1：先打通最小闭环

1. 定义 `StateSchema` 子类
2. 实现 `init_state/prepare/reduce`
3. 先返回 `Decision.final` 验证循环可跑

## Milestone 2：接入工具与动作

1. 注册一个简单工具
2. 让 `decide` 返回 `Decision.act`
3. 在 `reduce` 里消费 `observation['action_results']`

## Milestone 3：切到模型决策

1. 实现 `build_system_prompt`
2. 实现 `prepare`
3. 让 `decide` 返回 `None`
4. 用 parser 把输出转 `Decision`

## Milestone 4：接入 Env 与 Memory/History

1. 优先用 `HostEnv`
2. 通过 `Engine(history_policy=...)` 控制 history 窗口
3. 在 `prepare(state)` 中显式读取 memory
3. 检查 trace 里 memory/env payload 是否完整

## Milestone 5：上线前加固

1. 设置预算（steps/runtime/tokens）
2. 补 hooks 观测关键节点
3. 构建最小回归任务集

## 实战命令（可直接复制）

```bash
python examples/real/coding_agent.py \
  --model-base-url "https://api.siliconflow.cn/v1/" \
  --api-key "<your_api_key>" \
  --model-name "Qwen/Qwen3-8B" \
  --workspace ./playground
```

## Source Index

- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/core/state.py](https://github.com/Qitor/qitos/blob/main/qitos/core/state.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [examples/quickstart/minimal_agent.py](https://github.com/Qitor/qitos/blob/main/examples/quickstart/minimal_agent.py)
- [examples/real/coding_agent.py](https://github.com/Qitor/qitos/blob/main/examples/real/coding_agent.py)
