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

QitOS 是研究优先的 Agent 框架：一个 `AgentModule + Engine` 内核，
通过 Session 管理运行、暂停、持久化恢复和 fork。工具、provider、context、
store、sink 和 sandbox 可扩展；qita 只读检查 Trajectory。
框架保证执行机制的正确性，不保证任意模型完成任意任务。

## What's New

- master 修复 Python 3.10 publication 的哈希兼容性；这是独立验证的 G5 后继修复，不改写历史资格。
- G5 框架资格通过，S4 本地集成完成，runtime 身份固定为 `717b4cf1b23f2ed252cd03234ffd8605038d9567`。
- 双语文档统一到安装 → 项目 → 配置 → Session → 检查 → 恢复/扩展。
- 默认开发分支为 `master`，push 和 PR 执行 CI/docs 门禁；发布仍须显式触发。
- 本轮文档与运行教程的验收结果单独记录；远端同步已核验，docs CI 已通过。
  完整 CI 的兼容性与历史证据阻塞见[提升报告](docs/internal/plans/g5_docs_tutorials_report.md)；未发布 package 或部署文档。

## 开始开发

`pip install qitos` 得到 PyPI 已发布版本，不代表未发布的 G5。
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

G5 历史结果 2663 passed / 50 skipped 仅属于上述 runtime SHA（Python 3.12.7）。
高级 `AgentModule.run()` 和兼容 historical trace 仍保留；它们不是第二条初学者路径。
