# QitOS

![QitOS Logo](assets/logo.png)

面向研究与工程落地的智能体框架，采用唯一内核主线：
`AgentModule + Engine`。

- English README: [README.md](README.md)
- 文档站点: [https://qitor.github.io/QitOS/](https://qitor.github.io/QitOS/)
- 仓库地址: [https://github.com/Qitor/qitos](https://github.com/Qitor/qitos)

## 为什么是 QitOS

- 所有 Agent 统一执行主线：`observe -> decide -> act -> reduce -> check_stop`。
- 可快速复现研究范式：ReAct、PlanAct、ToT、Reflexion、SWE-style。
- 可观测性强：hooks + 标准化 trace + `qita`（board/view/replay/export）。
- 组合式扩展：tool、env、memory、parser、critic、search 均可替换。

## 安装

```bash
pip install -e .
```

## 快速开始

先跑最小内核链路：

```bash
python examples/quickstart/minimal_agent.py
```

再跑一个大模型驱动示例：

```bash
export OPENAI_BASE_URL="https://api.siliconflow.cn/v1/"
export OPENAI_API_KEY="<your_api_key>"

python examples/patterns/react.py --workspace ./playground
```

查看运行轨迹：

```bash
qita board --logdir runs
```

## 内核设计入口

- 策略契约：`qitos/core/agent_module.py`
- 运行时内核：`qitos/engine/engine.py`
- 类型化状态：`qitos/core/state.py`
- Task / Env / Memory 契约：
  - `qitos/core/task.py`
  - `qitos/core/env.py`
  - `qitos/core/memory.py`
- Tool 调度：
  - `qitos/core/tool.py`
  - `qitos/core/tool_registry.py`
  - `qitos/engine/action_executor.py`

## 文档导航

- 文档首页: [https://qitor.github.io/QitOS/](https://qitor.github.io/QitOS/)
- 内核架构：
  - [English](https://qitor.github.io/QitOS/research/kernel/)
  - [中文](https://qitor.github.io/QitOS/zh/research/kernel/)
- 30 分钟实验课：
  - [English](https://qitor.github.io/QitOS/research/labs/)
  - [中文](https://qitor.github.io/QitOS/zh/research/labs/)
- 自动生成 API 参考（构建时从 `qitos/*` 同步）：
  - [English](https://qitor.github.io/QitOS/reference/api_generated/)
  - [中文](https://qitor.github.io/QitOS/zh/reference/api_generated/)

## 本地文档开发

```bash
pip install -r docs/requirements.txt
mkdocs serve
```

说明：

- 文档构建会执行 `docs/hooks.py`，自动生成 API 参考到：
  - `docs/reference/api_generated/`
  - `docs/zh/reference/api_generated/`

## GitHub Pages 部署

工作流文件：

- `.github/workflows/docs.yml`

该工作流会在 `main` 分支更新时自动构建并发布到 GitHub Pages，目标地址：

- [https://qitor.github.io/QitOS/](https://qitor.github.io/QitOS/)
