# QitOS

<img src="assets/logo.png" alt="QitOS Logo" width="75%">

[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-qitor.mintlify.app-0A66C2)](https://qitor.mintlify.app/)
[![PyPI](https://img.shields.io/pypi/v/qitos.svg)](https://pypi.org/project/qitos/)
[![Repo](https://img.shields.io/badge/github-WhitzardAgent%2FWhitzardOS-black)](https://github.com/WhitzardAgent/WhitzardOS)

QitOS 是面向 agent 研究者的 torch-flavor 框架。

你可以在同一个 `AgentModule + Engine` 内核上原型化方法、运行 benchmark，并用内建 `qita` 检查长时轨迹。

QitOS 主仓库是小而清晰的核心框架。产品级 / 展示级应用会进入独立的 `qitos-zoo`，包括计划中的 `qitos-coder` 与 `qitos-cyber-agent`。

[快速开始](https://qitor.mintlify.app/zh/quickstart) · [教程课程](https://qitor.mintlify.app/zh/tutorials) · [基准测试](https://qitor.mintlify.app/zh/benchmarks/overview) · [CLI 参考](https://qitor.mintlify.app/zh/reference/cli) · [更新日志](CHANGELOG.md) · [English README](README.md)

## 当前能力

在一个 `AgentModule + Engine` 内核上构建多轮工具 Agent，用 Session 暂停、恢复、
fork 和 handoff。通过 YAML 配置预算，选择持久记忆与显式压缩策略，使用 qita
检查和导出 canonical Trajectory。工具、provider、context、store、sink 与 sandbox
均可扩展。框架负责执行正确性；任务策略和模型表现仍由应用与 provider 决定。

## What's New

- Python 3.10 模型清理兼容修复：所有自有资源都会尝试关闭，清理失败保留安全数字诊断和原异常优先级。
- R1 本地融合与五项审查修复已完成：保留 reasoning、准确请求/清理事实、handoff 归属与纯 YAML budget/loss 接线；恢复继续保留原始会话事实。
- Memdir 召回与 closed-exchange 压缩、Read/Edit 的 canonical ToolResult、统一 Observation，以及严格快照分页与原子导出已接入用户路径。
- 中英文教程包含完整可运行文件，API Reference 绑定准确实现源码。[迁移说明](docs/zh/reference/g5-migration.mdx)列出兼容变化。

[当前 R1 状态与远端同步](docs/internal/plans/v5_r1_remote_sync.md)是唯一状态入口；
[V5 路线](docs/v5/README.md)保留后续范围。R1 完成不等于 V5 全完成，
离线框架验收不代表 live 模型资格，也不代表 package release 或文档部署。

## 开始开发

`pip install qitos` 得到 PyPI 已发布版本，不代表未发布的 R1。
先按[安装说明](docs/zh/installation.mdx)安装准确来源，再运行
[无凭据 Quickstart](docs/zh/quickstart.mdx)。
真实模型使用 [agent.yaml、CredentialRef 与显式 resolver](docs/zh/reference/configuration.mdx)。
Docker 文件工具不可用时 fail closed，不降级成 host 执行。

## 学习与贡献

- [八个学习单元](docs/zh/tutorials/index.mdx)：自定义 Agent、工具并行、Session、context/memory、sandbox/artifact、多 Agent、qita、第三方扩展。
- [完整教学文件](examples/tutorials)、[示例目录](examples/README.md)。
- [迁移、限制与排障](docs/zh/reference/g5-migration.mdx)。
- [贡献指南](docs/zh/contributing/development.mdx)、[架构](ARCHITECTURE.md)。
- [CHANGELOG](CHANGELOG.md)、[历史工程进度](docs/progress.md)、[G5 证据](docs/internal/plans/s4_g5_convergence_execution.md)。

高级 `AgentModule.run()` 和 historical trace 兼容仍保留。
