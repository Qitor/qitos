# 30 分钟实验课（从零搭建版）

这套实验课假设你已经读过 QitOS 的核心文档（内核架构、AgentModule、Engine、Task、Env、Memory）。

目标不是“看懂示例代码”，而是：

1. 从研究问题出发，自己搭建 Agent 架构。
2. 在同一内核下逐步走到更强范式（ReAct -> PlanAct -> Reflexion）。
3. 用统一 trace 证据做可复现比较。

## 你会获得什么

1. 一套可复用的实验流程模板（问题定义 -> 状态设计 -> 策略实现 -> 验证评测）。
2. 一套可发表/可复现实验的最小规范（预算、指标、失败分类）。
3. 与 QitOS 强绑定的工程实践（不会落回“只会改 prompt”的伪研究）。

## 环境准备

```bash
pip install -e .
export OPENAI_BASE_URL="https://api.siliconflow.cn/v1/"
export OPENAI_API_KEY="<your_key>"
```

如果还没配好，请先看：

- [配置与 API Key](../../builder/configuration.md)

## 学习顺序

1. [Lab 1 - 从零构建 ReAct 研究基线](lab1_react.md)
2. [Lab 2 - 从 ReAct 升级到 PlanAct](lab2_planact.md)
3. [Lab 3 - 从 PlanAct 升级到 Reflexion](lab3_reflexion.md)

## 建议执行方式

每个 Lab 按下面四段走，不跳步：

1. 研究问题定义（你想优化什么）
2. 设计决策（状态、策略、停止条件）
3. 最小实现（只改一个变量）
4. 统一评估（trace + 指标 + 失败报告）

## Source Index

- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
- [examples/patterns/planact.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/planact.py)
- [examples/patterns/reflexion.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/reflexion.py)
- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
