# 开发者文档总览

## 目标

帮助你快速把 Agent 跑起来，并稳定接入自己的业务系统。

## 推荐阅读顺序

1. [快速开始](quickstart.md)
2. [配置与 API Key](configuration.md)
3. [qita 使用指南](qita.md)
4. [模型接入](model.md)
5. [从 Core 到 Agent 实战](from_core_to_agent.md)
6. [工具与环境](tools_env.md)
7. [GAIA Benchmark 适配](benchmark_gaia.md)
8. [Tau-Bench 适配](benchmark_tau.md)
9. [生产落地指南](production.md)

## 1 小时上手路径

1. 跑 `examples/quickstart/minimal_agent.py`
2. 跑 `examples/patterns/react.py`
3. 用 `qita board` 查看 trace
4. 在自己的任务上做一次小改造

## Source Index

- [examples/quickstart/minimal_agent.py](https://github.com/Qitor/qitos/blob/main/examples/quickstart/minimal_agent.py)
- [examples/real/coding_agent.py](https://github.com/Qitor/qitos/blob/main/examples/real/coding_agent.py)
- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
