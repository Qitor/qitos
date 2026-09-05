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

- R1 融合：严格 YAML 通过现有 composition extensions 接通具名上下文预算与显式 codec loss。

- Observation 的属性与映射写入保持一致，提供原子校验和独立序列化快照。

- 旧 Read/Edit 现在正确保留分页窗口、拒绝非唯一编辑，并返回 canonical 失败结果。

- 同一 Session 的 handoff 在 dispatch 前持久化 admission；目标 restore 与完成不再依赖迟到的源 callback。
- 显式 memory adapter 与确定性 closed-exchange 压缩：已验证安装后两进程 Memdir 召回、namespace 隔离和实际 request selection；[用法与边界](examples/v5/r1_b_memory_context/README.md)。
- V5 R1 Lane D 新增严格快照分页与原子流式 canonical export，warm append 增量维护 ID/位置索引；仍校验全部历史字节。见[实施证据](docs/internal/plans/v5_r1_d_execution.md)。
- Model I/O stream 回归覆盖净化错误、终态校验、usage 与自有资源清理；离线多轮 composition 消费者验证最终结果 11 和工具输入中断。

- 网页自足教程：资料整理 Agent 的完整代码、中英文学习路径、可核对源码签名的核心 API Reference；测试直接执行网页文件。

- [v5 迭代路线](docs/v5/README.md)现已记录四条 R1 候选交付：模型 I/O、memory/compaction、runtime 正确性和有界轨迹消费。[独立审查](docs/internal/plans/v5_r1_integration_review.md)复跑 198 项测试，并列出组合验收前的五项有界修复；这些候选尚未融合进 master。

- master 修复 Python 3.10 publication、journal 重复解析和历史证据可移植核验；这些后继修复独立验证，不改写 G5 历史资格。
- G5 框架资格通过，S4 本地集成完成，runtime 身份固定为 `717b4cf1b23f2ed252cd03234ffd8605038d9567`。
- 双语文档统一到安装 → 项目 → 配置 → Session → 检查 → 恢复/扩展。
- 默认开发分支为 `master`，push 和 PR 执行 CI/docs 门禁；发布仍须显式触发。
- 本轮文档与运行教程的验收结果单独记录；远端同步已核验，docs CI 已通过。
  后继提交的 CI 修复与准确验证结果见[CI 计划](docs/internal/plans/master_ci_stabilization.md)；未发布 package 或部署文档。

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

V5 R1 Lane D：轨迹工作量计数区分历史字节校验、解析和索引维护。
