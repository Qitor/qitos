# QitOS v5 — 从可运行内核到好用的 Agent 开发框架

**当前实施增量：Agent Design Lab。** 基于 `f1545414913d2e0668d0eccdcd82fe91c3b28d01`，以六个可独立安装的专业课程消费者同步完善 composition、工具、记忆、技能、Session 和观测机制。见[实施与缺口账本](../internal/plans/agent_design_lab_execution.md)。安装、组合与真实 Docker 消费者已通过；真实模型矩阵单独记录，不替代下方历史 R1 证据。用户已授权收口后推送，未授权 package release 或部署。

**当前 R1 状态：** 本地融合、27 笔重放、五项修复、Python 3.10 兼容资格和正式远端同步已完成。原本地融合接受源码为
`d17a6ab4f6b09b0dd8a9c8896f859d26de17f3ec`。新增 Python 3.10 cleanup 兼容修复、
本轮验证和正式远端同步统一见[当前 R1 记录](../internal/plans/v5_r1_remote_sync.md)。

V5 状态：`in_progress`。R1 已关闭本地框架融合范围；live 未运行，R1 不等于 V5 全完成。
本目录是仓库内工程规划，不是软件版本号或站点教程。正文以中文维护；公共教程/API 同步 EN/zh。

## 1. 北极星与起点

让研究者通过少量、明确、可替换的机制，开发长期运行、可恢复、能使用工具和多 Agent 协作的应用。QitOS 提供机制，不内置某个 coding/cyber/research Agent 的产品策略。

- 审计/规划源码：`f9e45f372ba4b8a5c89982add56a667908893b30`，当时分支为 `master`。
- G5 历史 runtime 资格：`717b4cf1b23f2ed252cd03234ffd8605038d9567`；2663 passed / 50 live-opt-in skipped 只属于该来源。
- 2026-09-05 复核：publication/Python 3.10、journal 重复解析与完整双语教学页已由后继提交修复；不是待重做任务。
- R1 源码基线冻结为 `4dfb570fb7eef504c1e6d247c21a1984251b80e4`；该 HEAD 的 CI、docs、Code Quality 已通过。具体任务见 [R1 dispatch](../internal/plans/v5_dispatch.md)，审计见 [R1 review](../internal/plans/v5_r1_review.md)。
- R1 四线实现已交付；[独立实现审查](../internal/plans/v5_r1_integration_review.md)记录准确 HEAD、198 项定向复跑和五项补充反例。四线各自合格报告不等于合并树通过。
- [原融合计划](../internal/plans/v5_r1_integration_plan.md)已执行；保留历史审查和失败身份，不再作为当前待办或本轮授权边界。

已经完成并必须保留：一个 `AgentModule + Engine` 内核、ExchangeLog/RequestView/codec、原生工具批次、同步 durable Session/checkpoint/pause/restore/fork、本地持久 WorkGraph、Env-only 工具与受限 Docker 沙箱、默认 Trajectory/qita reader、配置文件/CredentialRef、composition 和安装后教学路径。

**v5 不重做上述架构。** 它关闭真实使用、旧表面一致性、长任务效率和研究数据消费的剩余目标。保留历史 wire reader；不引入公开的 `AgentV5`、`SessionNext`、第二 Engine 或第二 SessionStore。

## 2. 五组任务与可见结果

| 组 | 任务文档 | 用户得到什么 | 首批重点 |
|---|---|---|---|
| V5-01 | [开发闭环与模型 I/O](01-developer-loop-and-model-io.md) | 按教程构建真实 Agent，多轮 tools/stream 不误报成功，并证明胶水减少 | 流式错误语义、真实两轮工具交互、脚手架缺口 |
| V5-02 | [长任务上下文与记忆](02-context-memory-compaction.md) | 可直接选用的 memory/compaction，长会话恢复不丢必要上下文 | 旧 Memory 适配、exchange-safe compaction |
| V5-03 | [工具与架构收敛](03-tools-and-architecture-consolidation.md) | 一套清楚的工具入口与可靠公共接口 | Read/Edit、Observation、func、活跃 correctness |
| V5-04 | [轨迹效率与研究数据](04-trajectory-and-research-data.md) | 长轨迹低开销读写、可直接送入训练/eval 的数据 | 增量 journal、流式导出、外部格式 |
| V5-05 | [交互式 Session 与沙箱](05-interactive-session-and-sandbox.md) | 审批恢复、安全控制入口、更大真实工程工作区 | 持久审批、控制边界、大工作区/嵌套发布 |

五组是能力归属，不是五个必须同时启动的 Agent。测试、类型、文档、安全是每组自带的交付要求，不另开长期“工程门禁产线”。

### R1 已完成范围（2026-09-06）

| 组 | 已融合增量 | 已完成的融合修复/验收 | 不因 R1 完成而关闭 |
|---|---|---|---|
| 01 / A | 内置 adapter stream 终态、usage、dispatch/cleanup；安装后多轮工具消费者 | reasoning 保留、cleanup 失败优先级；最终组合消费 | live 自主任务成功、原 Agent 迁移对照 |
| 02 / B | Memdir 稳定身份和跨进程召回；显式 closed-window compactor | 纯 YAML budget/loss 接线；保留 A/B 两种请求组装修复 | Markdown replay、摘要模型、完整 history 退休和跨 Agent 策略 |
| 03 / C | handoff source CAS 竞态修复、Read/Edit、单一 Observation 状态 | 终态精确 work/transfer 归属、已知未调度的恢复事实 | func/SharedMemory、旧 preset、MCP/hooks、benchmark/packaging |
| 04 / D | 增量 derived index、有界 page/iterator、原子 canonical export | 同一 wheel/qita 消费与准确性能说明 | suffix-only I/O、Artifact GC、外部训练格式、campaign 出版 |
| 05 | 本轮没有新增实现 | R1 稳定后派发具名子包 | 审批、实时控制、额外 sandbox/异步 Session 能力 |

R1 本地框架融合已完成；本轮远端同步后的唯一下一轮 dispatch baseline 以[当前记录](../internal/plans/v5_r1_remote_sync.md)及最终报告的实际完整 SHA 为准。模型质量、摘要策略和应用流程仍由 Agent 作者决定。

## 3. v4 目标移交账本

下表替代通过旧文档勾选框判断当前状态的做法；历史内容和原始验收条件保留，不回写历史结果。

| 原目标 | 审计时状态 | v5 去向 |
|---|---|---|
| 01 baseline absorption；06/07 原始派发 | 已完成/历史指令 | 仅回归，不重新派发 |
| 00 Gate A 同一 Agent 胶水减少和非劣对照 | 未找到完整验收 | 01D |
| 00 Gate B/G 无关消费者；12/13 本地恢复与 WorkGraph | 主干已完成，不能代替真实应用对照 | 01C/D、05 回归 |
| 02/09B typed provider、reasoning、stream | 新主线已有；流式及旧入口仍有错误文本化 | 01A/B |
| 03A/B/C 原生工具与 outcome | 新 Env 工具已交付；旧别名仍有缺陷 | 03A |
| 03D 工具 preset/alias 合并 | 未完成 | 03A/C |
| 03E todo/binary 等可选工具 | 非核心阻断项 | 需求准入后归 03，不要求本轮补齐 |
| 04A/B context/artifact 扩展 | 已接线；内置 adapter 与使用闭环不完整 | 02A/B、04B、05C |
| 04C/D exchange compaction、跨 run memory | 部分完成 | 02A–D |
| 05 canonical schema/default/qita | G5 已冻结且默认启用 | 回归；不再作为待建合同 |
| 05 存储效率、真实长轨迹、训练 exporters | 部分测量；核心优化/外部格式未闭合 | 04A–D、01D |
| 08A ratchet / 08C extras 安装 | 已建立并有 20-profile 历史验收 | 各组持续门禁 |
| 08B correctness retirement / 08C 功能依赖、PEP 621 / 08D/E | 部分完成；当前 CI 修复另有 owner | 03C–E；不并行改当前 CI 修复 |
| 09C/D timeout/durability | 主线已落地；异步消费/外围资源还有差异 | 01B、03B/D、05A/B |
| 09E 普通 hook 失败 / 09F MCP parity | 未完整闭合 | 03D；04 消费 hook loss |
| 10A census | 已有历史账本 | 03 只补增量，不重复全量普查 |
| 10B/C/D/F benchmark、func、Observation、SharedMemory、helpers | 仍有真实旧实现 | 03B/C/E，helper 随语义 owner 收敛 |
| 10E qita 分层 | reader 已分离；其余按消费者路径继续 | 04D，禁止无行为收益的大拆文件 |
| 12 交互控制/approval；14 更广 sandbox 能力 | 同步基础可用，扩展未完 | 05A–D |
| 15/16 public authoring、教程与安装 | G5/文档任务已交付；真实应用闭环待执行 | 01C/D；发行验收另列 |

来源：[v4 总目标](../v4/00-goal-metric.md)、[质量](../v4/08-quality-gates-and-packaging.md)、[生命周期](../v4/09-runtime-lifecycle-and-error-semantics.md)、[收敛](../v4/10-consolidation-and-surface-reduction.md)、[框架责任边界](../architecture/framework-responsibility-boundary.md)。

## 4. 责任边界与完成判定

| 类别 | 谁负责 | 如何处理 |
|---|---|---|
| 丢工具结果、重复 committed effect、错误当文本、越权、计费事实错误、假持久化 | 框架 | 必修；即使 live 暴露也转换为确定性回归 |
| prompt、策略、选工具、分解任务、记忆内容、摘要质量、预算大小 | Agent 作者 | 提供扩展/示例与诊断，不把策略写入 core |
| 上游不可用、真实模型能力、限流、远端未知效果 | provider/backend | typed 结果、能力矩阵；不能伪装成功，也不自动阻断无关功能 |
| 更强隔离、多租户、额外平台/厂商 | 按需扩展 owner | 未验证则不广告支持；不拖住已经验证的基础路径 |

每项分别记录 `implementation`、`deterministic_validation`、`live_observation`、`platform_qualification`、`migration`，不能用一个 `passed` 混合表示。状态限于 `planned / in_progress / implemented / qualified / blocked / deferred`；blocked/deferred 必须写剩余动作及 owner。

可合并机制修复与“真实应用证明完成”是两回事：外部模型不可用不应阻止前者；但没有真实成功闭环就不得宣布后者完成。不得无限重跑模型直到得到好结果。没有证据支持的收益不填百分比。

## 5. 迭代顺序与并行租约

### R1 — 历史派发合同（已执行 / superseded）

- A：01A/B 的内置 streaming failure/termination/usage/cleanup，以及安装后离线多轮工具消费者；live 另记资格。
- B：02A 与 02B 的可用 memory adapter、无需模型的 closed-exchange compactor；不要求本轮完成摘要模型或全部长会话迁移。
- C：优先修复新教程暴露的 same-Session handoff terminal/CAS 竞态，再修 Read/Edit 与 Observation。func、SharedMemory、MCP、benchmark 清理留 R2，不用兼容清理延迟活跃 runtime 修复。
- D：04A 的严格完整性下索引开销与 bounded reader，加最小流式 canonical export；04B GC、外部训练格式与大规模数据出版不在 R1。
- 05 的审批/控制/大工作区不启动。C 仅获得现有 handoff bugfix 的 Session/WorkGraph 文件租约，不获得新控制系统设计权。

四个 Agent 槽位时，先派 01/02/03/04 的上述子包。01 与 02 不得同时改 `_model_runtime.py`；共同接线由 01 owner 串行集成，02 先在 core/kit 和独立测试交付。有明确消费者的修复可短周期合并，无需等五组全完。

上述段落保留原派发合同，不再作为“尚未开工”状态。B 的实施报告记录了获准的最小请求
接线调整；融合 owner 要保留该调整与 A 的 completion-order/dispatch 修复，不能整文件覆盖。
这些五项修复、27 提交吸收和安装后组合消费者均已完成，不再重新派发。

### R2 — 同一基线上的长任务、真实迁移与交互恢复

R1 接线通过后：01D 迁移旧 Agent；02C/D 长会话与跨 run；03C/D 旧依赖与 MCP/hooks；04C/D 数据导出/测量；05A/B/C 交互 Session 和工程工作区。按实际槽位错峰，最多一个 owner 编辑一个共享文件。

首次 R2 四槽建议优先分给真实 Agent 迁移、长会话 memory、可恢复审批/控制、研究数据导出。
03 的剩余清理包继续具名保留，不能因槽位分配而算完成；细化任务与文件租约以已验收的
新 baseline 为准，当前不发送含占位 SHA 的 R2 指令。

### R3 — 明确可选扩展与发行维护

03E PEP 621/剩余低风险清理，以及 05D 强隔离 adapter，单独授权和验收。基础 v5 不要求支持所有 sandbox 厂商；但所选范围不得用 fake 当真实隔离证明。

| 共享文件/表面 | 唯一集成 owner | 其他组交付方式 |
|---|---|---|
| `engine/_model_runtime.py`、provider request/stream dispatch | 01 | 02 提供 context API/test；05 提交控制需求 |
| `core/conversation.py`、`core/request_view.py`、context/memory schema | 02 | 01 提供 codec consumers；不擅改冻结 wire |
| `engine/action_executor.py`、tool registry/permission、Observation | 03 | 05 提供审批/控制 contract tests |
| `config/builder.py`、`config/loader.py`、`config/_extensions.py`、`cli.py` | 01 在 R1；显式移交后 05 在 R2 | 02/03/04 提供注册清单与消费者，不自行抢写 |
| `engine/session_runtime.py`、checkpoint、WorkGraph/sandbox 接线 | R1 的 C 仅限 handoff terminal/ownership bugfix；R2 转交 05 | 其他组使用已有 snapshot slots；不新增 control/approval/sandbox 能力 |
| `tracing/*`、qita reader/export、artifact store | 04 | 其他组只生产事实/引用，不建立第二 writer |
| `engine/_trace_runtime.py` 普通 hook dispatch | 03 | 04 定义接收的 failure/loss 数据 |
| sandbox backend/retention/publication | 05 | 03 仅使用 Env seam；先吸收现有 CI 修复 |
| quality baseline、公共 docs manifest、全局说明 | R1 有界例外见 dispatch | 各线只 shrink / 添加自有教学条目；integration 逐项合并后重生成，禁止整体覆盖 |

这些租约优先于目录级泛化 ownership。重叠时拆提交或显式转交，不复制 helper 规避依赖。采用当前 committed producer API 后才能写“消费已完成”；相同基线已含 producer 时无需重新制作一层 receipt。

## 6. 通用交付和验证合同

每个子包都要交付：用户可见结果、最小改动、自动化回归、installed/public-path 消费者、兼容/撤销方式、EN/zh 文档和源码身份。接口先复用，不把 JSON receipt/CAS/schema 数组强加给初学者。

实现提交的基础门禁（在记录的固定工具链下执行）：

先核对 `quality/toolchain.json`、`requirements/quality.txt` 和当前已验证的 Python；独立 worktree 使用自己的环境。shell 默认 Python 不匹配时先修环境，不更改 baseline 或放宽工具版本。下文 `python` 指已验证环境中的解释器。

```bash
python scripts/static_quality.py check
python -m flake8 qitos/core qitos/engine qitos/models qitos/trace
python -m mypy qitos/core qitos/engine qitos/models qitos/trace
python -m pytest -q tests/test_architecture_boundaries.py tests/test_public_surface.py tests/test_no_local_paths.py
python -m pytest -q
python scripts/validate_docs.py
git diff --check
```

integration 的 ratchet 另按脚本实际 CLI 绑定精确 base ref；不得只对自行更新的 baseline 检查。packaging/export/entrypoint 变化须 build、twine、fresh wheel/extra 对照；文档站点变更遵守 `docs/AGENTS.md` 的 MDX、双语及页面检查。记录 required/advisory/live/platform 的区别，不能 `|| true`、rerun-only 或扩大 skip 来制造绿色。

不要求每笔提交重新跑昂贵 live/Docker 全矩阵；先跑对应风险门禁，每轮共同集成后完整复验一次。继承未改组件的历史证据要注明 exact source，不能改头换面成当前执行证据。

每组结果保存在相应 `docs/internal/plans/v5_*.md`；`docs/progress.md` 由 integration owner 追加。报告至少包含 source、scope、behavior、tests、API/dependency delta、limitations、consumer outcome、commits、dirty status。不要反复复制整份大轨迹或为每个标量建立新 manifest。

## 7. 基线、worktree 和交接

1. R1 已读取 master CI 稳定化及教学任务结果，并核验远端精确 HEAD 的 checks；不再等待旧任务口头确认。
2. [v5_dispatch.md](../internal/plans/v5_dispatch.md) 已记录 R1 的精确基线、四条线、前置核验和租约；无占位 SHA。实现 Agent 读取本地主工作树中的任务输入，记录其 digest，再从指定源码基线建立自己的工作树。
3. 同一轮所有 worktree 必须从该 commit 创建；`git merge-base` 必须相等。R1 的四个精确 branch/worktree 名称以 dispatch 表格为准，不自行采用旧草案名称。已存在则先核验，禁止 reset/强制覆盖；后续轮次单独冻结，不复用移动基线。
4. worktree 路径由协调者登记为 repo 外独立目录，不在公共文档写本机绝对路径。保持用户/其他 Agent 的 dirty tree，不借用其他线的 venv、Docker 容器或临时凭据。
5. 按依赖短周期合并、复验。push/release/default-branch 操作必须有当轮明确授权；本计划不授予该权限。
6. 共同 baseline 提升、授权推送并核验后，只对已合入、clean、idle、无未收录产物的该轮 worktree 执行非强制 `git worktree remove` 和 prune。保留 branch/tag/commit refs；dirty/unmerged/运行中工作树不删，报告原因，不用递归删除替代 Git 检查。

## 8. v5 的完成定义

基础范围是 01A–D、02A–D、03A–D、04A–D、05A–C；不支持的非必需平台明确排除。分开记录两个完成状态：`V5_MECHANISMS_QUALIFIED` 指声明范围的代码/确定性/已支持平台通过；`V5_RESIDUAL_GOALS_CLOSED` 还要求 01C/D 的真实功能与迁移对照完成。外部条件不足时可以推进前者，后者保持 pending，不能声称“真实开发收益已验收”。非劣的统计结论按登记实验能支持的强度报告，不要求模型所有任务都成功。

工程里程碑可逐包 qualified；整体不能靠把所有未完项改成 deferred 来关闭。03E、05D 是列明的后续选项，未选择时不作能力承诺。

最终至少回答：同一 Agent 少写了什么、哪些真实流程已跑通、长任务内存/存储改善多少、研究数据送到哪些消费者、哪些旧入口已迁移、哪些能力仍受限。Rust core、分布式 scheduler、任意线程硬取消、外部 exactly-once、全部模型任务成功均不是基础收口条件。
