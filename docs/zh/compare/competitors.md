# QitOS 与 LangChain、Langflow、Dify 对比

## 对比范围说明

这里比较的是“智能体研发与落地”视角下的架构取舍，不是对项目好坏做简单结论。

## 总览表

| 维度 | QitOS | LangChain | Langflow | Dify |
|---|---|---|---|---|
| 主定位 | Agent 内核框架 | 通用 LLM 框架 | 可视化流程编排 | LLM 应用平台 |
| 主线清晰度 | 高（`AgentModule + Engine`） | 中（抽象层较多） | 中（以流程图为中心） | 中（以应用管线为中心） |
| 运行阶段可见性 | 高 | 中 | 中低 | 中低 |
| 研究复现友好度 | 高 | 中 | 中低 | 中（偏产品日志） |
| 低代码友好度 | 低 | 中 | 高 | 高 |
| 最适用场景 | 研究复现、方法创新、可控运行 | 广泛集成与应用开发 | 快速可视化原型 | 团队级应用部署 |

## 实战层面的差异

### QitOS 的优势

1. 内核主线单一，认知负担更低。
2. 对 Agent 行为做 phase 级调试更直接。
3. 更适合在同一契约下做策略横向比较。

### 其他框架常见优势

1. 集成生态更广。
2. 非研究场景的上手速度可能更快。
3. 对非代码团队更友好（尤其 Langflow/Dify）。

## Source Index

- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [qitos/core/env.py](https://github.com/Qitor/qitos/blob/main/qitos/core/env.py)
- [qitos/trace/schema.py](https://github.com/Qitor/qitos/blob/main/qitos/trace/schema.py)
- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
