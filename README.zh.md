# QitOS

<img src="assets/logo.png" alt="QitOS Logo" width="75%">

[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-qitor.mintlify.app-0A66C2)](https://qitor.mintlify.app/)
[![PyPI](https://img.shields.io/pypi/v/qitos.svg)](https://pypi.org/project/qitos/)
[![Repo](https://img.shields.io/badge/github-Qitor%2Fqitos-black)](https://github.com/Qitor/qitos)

QitOS 是面向 agent 研究者的 torch-flavor 框架。

你可以在同一个 `AgentModule + Engine` 内核上原型化方法、运行 benchmark，并用内建 `qita` 检查长时轨迹。

QitOS 主仓库是小而清晰的核心框架。产品级 / 展示级应用会进入独立的 `qitos-zoo`，包括计划中的 `qitos-coder` 与 `qitos-cyber-agent`。

[快速开始](https://qitor.mintlify.app/zh/quickstart) · [教程课程](https://qitor.mintlify.app/zh/tutorials) · [基准测试](https://qitor.mintlify.app/zh/benchmarks/overview) · [CLI 参考](https://qitor.mintlify.app/zh/reference/cli) · [更新日志](CHANGELOG.md) · [English README](README.md)

## 最新进展

- **S2 单智能体运行时已资格化，Trajectory 发布仍阻塞**：G3 在既有 `AgentModule + Engine` 内核中收敛了 Session 持久化、canonical conversation/model I/O、并行工具批次的部分持久化、quiescent pause、fresh-process 恢复、steering/continuation 与唯一 EventSink bridge。离线 SQLite 父/子进程证明独立运行 20 轮，committed effect 从不重放。这不代表冻结候选 Trajectory schema、默认启用 writer、迁移 qita、实现 S3 多智能体 scheduler/authoring sugar，也不保证外部 effect exactly-once。
- **保留 G2 契约基线**：G2-R2 已将契约代码提升至 `c0f19cd...`，关闭五组独立审计发现的契约 blocker，并在保留全部 branch ref 的前提下安全回收 17 个过期 worktree。S2 lane 的固定 ancestry 仍为 `446a347d1ac73636476ca2515a01da601b567c68`；G3 随后把各 lane producer 重放到 `47cd4dc...` integration source，再完成上方所述的 runtime convergence。
- **持久会话与原生多智能体架构**：[Task 12](docs/v4/12-session-runtime-and-persistence.md) 规划了以当前 canonical checkpoint 为唯一持久化机制的安全暂停、跨进程恢复、fork 与 effect-aware recovery；[Task 13](docs/v4/13-durable-multi-agent-work-graph.md) 则把 handoff、delegate、fan-out、spawn、fork、steer、join 明确为一个持久 work graph 上不同的所有权语义。[四产线手册](docs/v4/11-four-lane-execution-playbook.md)也已调整：G1 后工程质量成为跨线合并门禁，四条能力线转为 Session、Conversation/Context、Tools/Multi-Agent、Trajectory/qita/DX。
- **静态 ratchet 资格验证与可执行贡献门禁**：确定性测试覆盖所有关键 baseline 转换；tool-schema workflow 与仓库测试现在共同执行同一个已提交入口，真实检查已注册 class tools，并包含受控 malformed-spec 失败证明。required-candidate、advisory、stale 与 release-only 角色继续明确记录，同时不声称掌握外部 branch-protection 配置。
- **证据化 v4 集成进度账本**：[`docs/progress.md`](docs/progress.md) 现在持续记录各产线的准确 HEAD、集成结论、可执行复核探针、跨线契约阻断、合并顺序以及 G1/G2 检查表；收敛波次分支“已完成”与集成分支“已合入并通过资格验证”被明确区分。
- **规范工具结果与运行时所有权**：`ToolResult` 是唯一无损 action/tool outcome，`ActionResult`、历史字典和 `model_summary` 通过兼容边界接入。结构化 schema 硬门禁、生命周期所有权矩阵、确定性的 durability 竞态证明及 Lane B/D schema-bearing fixtures 共同完成 Task 03A/09A 合同层；本轮未改变编码工具、checkpoint 或 MCP transport 行为。
- **ToolResult 契约加固**：canonical persistence 不再展开 output，带版本 payload 严格解析，legacy flattening 进入显式 adapter；模型与 trace-safe view 使用有界、脱敏的 allowlist。错误 schema 及 interceptor/permission 改写后的参数都会在工具执行前被共享硬门禁拒绝；C1-R fixture 固定了 Lane B/D 交接，但不宣称已经解决完整 trajectory privacy。
- **G1 ToolResult 边界已关闭**：递归 JSON-only 参数会在 interceptor、权限与工具代码之前失败，canonical 与 legacy 的嵌套值均隔离调用方所有权；model/trace 可见 mapping key 采用无碰撞脱敏，forced-secret 标量内容与类型化 trace-safe omitted count 分离，并提供 aggregate 与 per-field loss 计数。
- **仓库全包静态质量 ratchet**：固定版本的 Python/flake8/mypy 单一命令会用提交态分类 baseline 检查所有 active `qitos` package。新 finding 会阻断 CI，已修复 finding 会强制缩小 baseline，core/engine/models/trace 稳定层继续保持零债务；correctness finding 按语义交给对应产线，而不会被降级成普通清理。
- **工程质量审计与证据门禁**：[证据化审计](docs/engineering-quality-audit.md)覆盖全包质量门禁、错误与持久化语义、资源生命周期、重复抽象、可选依赖和测试可信度。首轮质量保障、对话/上下文、工具/运行时、轨迹/架构收敛四线被保留为 G1 收口历史；G1 之后，同一套 ratchet 与证据规则将作为四条能力线的强制门禁。
- **规范对话事务契约**：模块级 `qitos.core.conversation` 不再复制 outcome 字段，而是嵌入唯一 canonical `ToolResult`；persistence/model/trace view 全部委托给 C，ExchangeLog v2 严格读取并统一返回类型化错误，同时保留面向崩溃恢复的部分完成顺序与 steering，且直接用已提交的 C fixture 完成资格验证。Engine/provider 默认路径与 Task 02B 仍未启动。
- **迁移前先完成轨迹数据平面证据**：[Lane D D1/D1-R 计划](docs/internal/plans/lane_d_data_convergence.md)现已逐条映射 runtime/trace/tracing/render/qita/checkpoint 与分发链路，登记公共表面移除阻塞项，选择两类受隐私门禁保护的 fixture 来源，并提供严格 manifest/发布/可移植性校验与逐合同类型化 readiness receipt。本轮不修改 trace v1 或 qita、不发布敏感 fixture、不宣称压缩收益、不完成 05A，也不冻结 trajectory v2。
- **已验证的 producer receipt**：D readiness 仅根据受审 authority、精确 producer commit、已提交 fixture/evidence 路径与字节哈希推导 B/C 资格。伪造字段会产生类型化 blocker，单个 receipt 只解除自身合同；发布仍未合格，trajectory v2 继续保持未冻结。
- **中性的传输与容器控制**：OpenAI-compatible 模型支持由调用方管理的 `default_headers`；`DockerEnv` 支持显式 `container_env` 映射，并正确保留容器内绝对路径，不吸收实战任务专属的路由或环境策略。
- **立即取消状态保持一致**：Engine 识别立即取消后，State、任务/运行结果、END event 与 trace manifest 现在都会记录 `cancelled_immediate`；qita 会将该 manifest 视为 `stopped`，不再误判为正常完成。
- **结构化动作文本不再假完成**：当原生工具模型没有返回 `tool_calls`、却以文本输出了格式错误的动作字段时，QitOS 现在会保留 parser 恢复路径，而不会把动作文本当成最终答案；普通自然语言结论的行为保持不变。
- **窗口安全的原生工具历史**：当消息窗口裁掉 assistant 调用声明时，模型请求会移除对应的孤立工具结果，避免长时并行工具 Agent 发送非法 `tool_call_id` 链，同时保持完整轮次和原有恢复行为不变。
- **直接构造 Engine 时保留 preset 协议**：`Engine(agent=...)` 现在会采用 `build_model_for_preset(...)` 写入模型的协议，使 Kimi K3 等服务商别名继续使用 JSON/原生 API 工具交付，而不会静默回退到文本 ReAct。
- **空模型响应有界恢复**：既无有效文本也无工具调用的模型响应现在会被记录为可追踪的 `model_error`，重试一次后若仍为空则明确停止，不再伪装成 parser `wait` 并耗尽 Agent 步数预算。
- **可选 OpenAI Responses API 传输**：通过 `api_mode="responses"`（或 YAML `api_mode: responses`）保留类型化输出项、并行函数调用、`call_id` 工具结果、流式事件和可重放工具上下文。现有 Chat Completions 行为仍是默认值。

## v0.5.0 最新进展

- **12 个方法模板**：ReAct、PlanAct、SWE-Agent、Voyager、Debate、Manager-Worker、Planner-Executor、Self-Refine、Reflexion、LATS、MoA 和 Magentic-One — 每个都包含 paper.md、config.yaml 和 recipe 实现。
- **`qit new` CLI**：使用 `qit new --template <name>` 从内建模板脚手架新 agent 项目。
- **导出 API**：`EngineConfig`、`ToolPermissionSpec`、`CriticTrace` 和 `HandoffTrace` 用于程序化访问引擎配置和 trace 数据。
- **Tracing 集成**：W&B (`WandbTraceProcessor`) 和 MLflow (`MlflowTraceProcessor`) 实验追踪。
- **FamilyPreset 可扩展性**：`override()`、`recommended_*` 建议字段、`MaxTokensCriteria` 停止条件。
- **qita 成本面板**：运行概览中的 token 用量和成本指标。

详见 [CHANGELOG.md](CHANGELOG.md)。

## Live Terminal of QitOS for Code Review

<p align="center">
  <img src="demo.gif" alt="QitOS long-running agent demo" width="92%">
</p>

## QitOS 适合谁

- **方法研究者**：频繁改 prompt、parser、critic、tool 与 memory policy，但不想每次都重写 runtime。
- **benchmark 使用者**：希望 GAIA、Tau-Bench、CyBench 跑在和 agent 开发同一套内核上。
- **长时 agent 调试者**：更关心 trajectory review、replay、diff 与 context collapse，而不是先拼应用脚手架。

## 2 分钟跑通 QitOS

QitOS 里的 minimal agent 应该是一个最轻量的 **coding agent**。它会配置真实模型、进入 workspace、改代码、跑验证，并留下 qita 可检查的 trace。

```bash
pip install "qitos[models]"
export OPENAI_API_KEY="sk-..."
qit --version
qit demo minimal
qita board --logdir runs
```

OpenAI-compatible provider 常见补充配置：

```bash
export OPENAI_BASE_URL="https://api.siliconflow.cn/v1/"
export QITOS_MODEL="Qwen/Qwen3-8B"
```

`qit demo minimal` 会先种一个最小 bug workspace，再让模型驱动的 coding agent 修复它、运行验证，并把轨迹写到 `./runs`。

接下来可以继续：

- 想看 ReAct：见 [`examples/patterns/react.py`](examples/patterns/react.py)
- 想看 coding agent：见 [`examples/real/coding_agent.py`](examples/real/coding_agent.py)
- 想看 benchmark：从 [评测总览](https://qitor.mintlify.app/zh/benchmarks/overview) 开始
- 想看方法模板：见 [方法模板指南](https://qitor.mintlify.app/zh/guides/method-templates)

## 为什么是 QitOS

| 如果你想要... | QitOS 提供... |
|---|---|
| 可复现的 agent 研究 | 稳定的 `AgentModule + Engine` 内核 |
| 方法 = Agent + Critic | 12 个内建方法模板，映射经典论文 |
| 强可观测性 | `qita` board、replay、export 与 trace 工件 |
| benchmark 工作流 | GAIA、Tau-Bench、CyBench 适配器 |
| 更少框架胶水 | 一条 canonical 执行主线 |

## 方法模板

QitOS 内置 12 个方法模板 — 每个都是实现经典 agentic 推理模式的 Agent + Critic 组合：

| 模板 | 模式 | 论文 |
|------|------|------|
| ReAct | 推理 + 行动 | Yao et al. 2023 |
| PlanAct | 先规划再执行 | — |
| SWE-Agent | 软件工程 | Princeton 2024 |
| Voyager | 开放探索 | Wang et al. 2023 |
| Debate | 多 Agent 辩论 | — |
| Manager-Worker | 编排与委派 | — |
| Planner-Executor | 计划分解 | — |
| Self-Refine | 生成 → 批评 → 改进 | Madaan et al. 2023 |
| Reflexion | 行动 → 反思 → 重试 | Shinn et al. 2023 |
| LATS | 蒙特卡洛树搜索 | Zhou et al. 2023 |
| MoA | 并行提议 + 聚合 | Wang et al. 2024 |
| Magentic-One | 编排器 + 专家 | Furtado et al. 2024 |

直接使用：

```python
from qitos.recipes.reflexion import ReflexionAgent, ReflexionCritic

agent = ReflexionAgent(llm=my_llm)
result = agent.run(
    task="Debug the failing test",
    critics=[ReflexionCritic(max_reflections=3)],
    max_steps=15,
    return_state=True,
)
```

或从任意模板脚手架新 agent：

```bash
pip install qitos[cookiecutter]
qit new --agent-name my_agent --agent-description "My custom agent"
qit list-templates
```

## 工具层布局

QitOS 将工具导入分为三层：

- `qitos.kit`：最简单的常用工具集入口
- `qitos.kit.toolset`：场景导向的预设和注册表构建器
- `qitos.kit.tool.<domain>`：高级原子能力导入

默认组合是列表优先：

```python
from qitos import ToolRegistry
from qitos.kit.tool.file import ReadFile
from qitos.kit.toolset import coding_tools

registry = ToolRegistry().include_toolset(
    [
        ReadFile(workspace_root="."),
        coding_tools(workspace_root="."),
    ]
)
```

安全敏感工具为显式 opt-in 导入，不在 `qitos`、`qitos.kit`、`qit demo` 或快速开始路径中。

## 文档地图

- 第一次接触： [简介](https://qitor.mintlify.app/zh/introduction)
- 第一条成功路径： [快速开始](https://qitor.mintlify.app/zh/quickstart)
- 安装方式： [安装](https://qitor.mintlify.app/zh/installation)
- 写自己的最小 coding agent： [构建第一个 Agent](https://qitor.mintlify.app/zh/guides/build-your-first-agent)
- 方法模板： [方法模板指南](https://qitor.mintlify.app/zh/guides/method-templates)
- 理解运行时： [AgentModule](https://qitor.mintlify.app/zh/concepts/agent-module) / [Engine](https://qitor.mintlify.app/zh/concepts/engine)
- 看 trace： [可观测性](https://qitor.mintlify.app/zh/guides/observability)
- 走完整课程： [教程](https://qitor.mintlify.app/zh/tutorials)
- 看 benchmark： [评测总览](https://qitor.mintlify.app/zh/benchmarks/overview)
- 看命令： [CLI 参考](https://qitor.mintlify.app/zh/reference/cli)
- 看 API： [API 参考](https://qitor.mintlify.app/zh/reference/api)

## 界面预览

<table>
  <tr>
    <td align="center"><strong>QitOS CLI</strong></td>
    <td align="center"><strong>qita Board</strong></td>
    <td align="center"><strong>qita Trajectory View</strong></td>
  </tr>
  <tr>
    <td align="center">
      <a href="assets/qitos_cli_snapshot.png">
        <img src="assets/qitos_cli_snapshot.png" alt="QitOS CLI" width="100%" />
      </a>
    </td>
    <td align="center">
      <a href="assets/qita_board_snapshot.png">
        <img src="assets/qita_board_snapshot.png" alt="qita Board" width="100%" />
      </a>
    </td>
    <td align="center">
      <a href="assets/qita_traj_snapshot.png">
        <img src="assets/qita_traj_snapshot.png" alt="qita Trajectory View" width="100%" />
      </a>
    </td>
  </tr>
</table>

## 当前阶段

QitOS 当前处于 **Beta**。

- 相对稳定：`AgentModule + Engine`、trace/qita、canonical examples、benchmark adapters，以及官方可复现 run 契约。
- 仍会演进：更高层 convenience API、部分 `kit` 模块、实验性 toolset。
- 如果你正在评估接入，建议从 kernel 与 examples 开始，而不是假设所有高层表面都已冻结。
- 持续演进和升级说明见 [CHANGELOG.md](CHANGELOG.md)。

## 安装与版本

- 支持的 Python 版本：**3.10+**
- 普通用户安装：`pip install "qitos[models]"`
- 版本检查：`qit --version`
- 最小 coding agent：`qit demo minimal`
- 常见 provider 配置：`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`QITOS_MODEL`
- 仅核心安装：`pip install qitos`
- 仓库源码安装：`pip install -r requirements.txt`
- 完整开发安装：`pip install -r requirements-dev.txt`
- 可选扩展：`qitos[wandb]`、`qitos[mlflow]`、`qitos[cookiecutter]`、`qitos[all]`
- 安装说明： [安装](https://qitor.mintlify.app/zh/installation)

## 参与贡献

欢迎贡献方法模板、benchmark adapters、memory/history 工作流、qita UX 与核心框架能力。产品级 agent 应优先进入 `qitos-zoo`。开发环境、方法模板贡献、文档贡献流程详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## License

MIT，见 [LICENSE](LICENSE)。
