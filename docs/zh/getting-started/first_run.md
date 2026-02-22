# 第一次运行（最小 + 大模型）

## 目标

跑通两次完整闭环：

1. 不调用模型的最小示例：先把内核链路验证清楚
2. 调用大模型的 ReAct 示例：验证 model + parser + tool + trace 全链路

## 0）一次性配置模型（用于 LLM 示例）

QitOS 的 examples 默认读取：

- `OPENAI_BASE_URL`（服务端 endpoint）
- `OPENAI_API_KEY`（或 `QITOS_API_KEY`）

最快配置：

```bash
export OPENAI_BASE_URL="https://api.siliconflow.cn/v1/"
export OPENAI_API_KEY="<your_api_key>"
```

如果你不想写环境变量（纯命令行配置），见：[配置与 API Key](../builder/configuration.md)。

## 1）跑最小 Agent（不调用模型）

```bash
python examples/quickstart/minimal_agent.py
```

你需要确认：

1. 程序能结束并输出结果。
2. stop reason 明确。
3. trace 开启时，`runs/` 下有 run 目录。

## 2）跑一个 LLM 驱动的 Agent（ReAct）

这一步会真正走到默认的模型路径：

- `AgentModule.decide(...) -> None`
- Engine 组装 messages（system + memory + prepare 文本）
- Engine 调用 `llm(messages)`
- parser 把文本解析成 `Decision(Action(...))`
- Engine 执行工具调用，并把结果 reduce 回 state

```bash
python examples/patterns/react.py --workspace ./playground
```

你需要确认：

1. 终端 render 里能看到模型输出（除非你加了 `--disable-render`）。
2. 工具确实被调用（scratchpad/trace 里能看到 action 结果）。
3. `runs/` 下有 run 目录，并包含 `manifest.json`、`events.jsonl`、`steps.jsonl`。

## 下一步

- 如果模型调用失败：见 [配置与 API Key](../builder/configuration.md)
- 用 qita 复盘：见 [qita 使用指南](../builder/qita.md)

## Source Index

- [examples/quickstart/minimal_agent.py](https://github.com/Qitor/qitos/blob/main/examples/quickstart/minimal_agent.py)
- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
