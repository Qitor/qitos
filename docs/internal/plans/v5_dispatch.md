# V5 R1 — 四线执行合同

日期：2026-09-05。状态：历史 R1 派发合同；四线候选已交付，尚未整体融合验收。
当前来源、补充反例与下一任务见 [独立实现审查](v5_r1_integration_review.md)及[融合计划](v5_r1_integration_plan.md)。下文保留原执行边界，不应再次派发为新任务。
适用：用户将某条指令交给 coding agent 后，仅授权该线的实现、测试、本地提交；不自动启动其他 Agent。

## 1. 唯一源码基线与任务输入

```text
Repository: WhitzardAgent/WhitzardOS
Branch at review: master
R1_BASELINE: 4dfb570fb7eef504c1e6d247c21a1984251b80e4
Subject: Merge pull request #37 from WhitzardAgent/codex/docs-self-contained-learning
```

该 HEAD 的远端 CI、docs、Code Quality 已完成且成功，详见 [审计](v5_r1_review.md)。所有实现 worktree **直接从这一个 commit 创建**，不是从本地主工作树 HEAD、旧 G5、origin 的未来移动 HEAD 或其他 lane 创建。

本地主工作树当前是 `60809b3be388d22ea40ea41b4aaa1f5540c76fda`，落后远端，且保留未提交 v5 文档。这不是阻断：Git 对象已存在，独立 worktree 可以直接使用指定 commit。**不要 pull、stash、reset、清理或替用户提交主工作树。**

本文件、四线指令和 `docs/v5/` 是主工作树中的本地任务输入，尚未进入指定 baseline。2026-09-05 加强后的四条对话指令各自包含完整执行合同，可独立发送；它们是当轮任务依据，文件是同步副本与背景资料。能够读取本地文件时记录路径与 SHA-256；新 worktree/异机没有本地草稿不构成阻断，不猜另一 SHA、不要求先完成文档收口。仓库规则从固定 baseline 读取。不得声称远端已经包含本地草稿。

共同必读：根 `AGENTS.md`、`ARCHITECTURE.md`、`qitos/AGENTS.md`、实际编辑目录的嵌套 AGENTS、baseline 的 `docs/AGENTS.md`、`docs/architecture/framework-responsibility-boundary.md`、`docs/v5/README.md`、本文件和自己的 lane 指令。

## 2. 预检与工作树

先在主仓库只读记录 status、HEAD、worktree list；可执行 `git fetch origin master`，只更新远端追踪信息。必须确认指定 commit 是 commit 对象且可从 origin/master 到达。远端在此后前进不改变本轮基线；如果已不包含此 commit，停止报告，不自行选新起点。

```bash
git status --short --branch
git worktree list --porcelain
git fetch origin master
git cat-file -t 4dfb570fb7eef504c1e6d247c21a1984251b80e4
git merge-base --is-ancestor 4dfb570fb7eef504c1e6d247c21a1984251b80e4 origin/master
```

| Agent | Branch | 从主仓库创建的 worktree | 完整执行指令 |
|---|---|---|---|
| A | `codex/v5-r1-a-model-io` | `../WhitzardOS-v5-r1-a` | [A](v5_r1_a_model_io.md) |
| B | `codex/v5-r1-b-memory-context` | `../WhitzardOS-v5-r1-b` | [B](v5_r1_b_memory_context.md) |
| C | `codex/v5-r1-c-runtime-correctness` | `../WhitzardOS-v5-r1-c` | [C](v5_r1_c_runtime_correctness.md) |
| D | `codex/v5-r1-d-trajectory-efficiency` | `../WhitzardOS-v5-r1-d` | [D](v5_r1_d_trajectory_efficiency.md) |

各自的创建命令见 lane 文件。若 branch/path 已存在，核验其归属、HEAD、merge-base、dirty 状态；同一任务可恢复，但不是同一任务时停止，不复用/覆盖。新工作树初始 HEAD 和 `git merge-base HEAD 4dfb570fb7eef504c1e6d247c21a1984251b80e4` 必须均为固定基线。本轮不自行 rebase、cherry-pick 其他线或改其他工作树。

## 3. 实现范围与共享文件

本轮交付 **四个可使用的增量**，不是五大 v5 任务全完成：

- A：真实内置 adapter 的 stream 正确性和安装后多轮工具路径。
- B：现成 memory adapter 与确定性 compaction，可从现有配置扩展使用。
- C：现有 handoff 竞态、Read/Edit 和 Observation 的 correctness。
- D：严格完整性下的索引改进、bounded reader 和流式 canonical export。

| 写租约 | Owner |
|---|---|
| models、`engine/_model_runtime.py`、model request/stream bridges | A |
| core context/memory/request_view/conversation、kit memory/history/context、`engine/_context_runtime.py` | B |
| existing Session/WorkRuntime 的 handoff fix、Observation、旧 coding aliases、对应 executor/permission adapter | C |
| tracing store/reader/export、qita reader/poll/export、artifact 仅现有读引用消费 | D |
| `config/builder.py`、loader、`_extensions.py`、scaffold、`qitos/cli.py` | A，仅确有本轮消费者缺口时；B/C/D 用实际存在的 `build_agent_composition(..., extensions={...})` mapping/factory 槽位 |
| checkpoint CAS、sandbox、permission authority 语义 | 冻结；C 只可增加 handoff 回归，不放宽 CAS 或审批 |
| `_trace_runtime.py` hooks、MCP、func、SharedMemory、recipes/benchmark、packaging/CI | 本轮冻结，不顺手扩展 |

共享文件有三个明确例外：

1. 每线可在自己的分支给 README/README.zh 的 What's New 和 CHANGELOG 对应分类追加**仅本线**的简短事实；不能覆盖其他条目或宣称整体完成。符合根 AGENTS 的文档同步要求。
2. 每线可运行 `static_quality.py update` **仅移除确实修复的 finding**，不得新增 exception、改变工具链、重建 bootstrap 或整体忽略。这笔 delta 单独提交。最终 integration 从融合代码重新生成 shrink，不逐个用 ours/theirs 覆盖 JSON。
3. `docs/api-contracts.json`、`tutorial-contracts.json` 只添加/更新自己教学单元的绑定；禁止全量重排。同步脚本仅生成本线拥有的页面，其他生成变化报告给 integration。公共 root/aggregate exports 和 Engine 参数数量默认零增长；需要新模块级 API 可增加明确 `__all__`，但不能自动扩大 root。

`docs/progress.md`、v4 状态、v5 总体状态由 integration owner 写，四线不改。每线自己的详细实施/证据记录路径在其任务中固定。不要创建逐字段 manifest 套娃；已有 committed contract 直接 import/消费。

## 4. 共同工程验收

使用 task-local Python 3.12.7 环境，核对 `quality/toolchain.json`、`requirements/quality.txt`；flake8 7.0.0、mypy 1.19.1、pyflakes 3.2.0、pycodestyle 2.11.1、mccabe 0.7.0。mypy source target 3.11；不能把 shell 默认 Python 3.13 的 metadata 缺失冒充源码失败。不要改共享全局环境。

缺陷必须先有 failing regression，再实现。自己的定向 tests 在每个行为提交后执行；最终 HEAD 完整执行以下门禁一次：

```bash
python scripts/static_quality.py update
QUALITY_BASELINE_REF=4dfb570fb7eef504c1e6d247c21a1984251b80e4 python scripts/static_quality.py check
python -m flake8 qitos/core qitos/engine qitos/models qitos/trace
python -m mypy qitos/core qitos/engine qitos/models qitos/trace
python -m pytest -q tests/test_architecture_boundaries.py tests/test_public_surface.py tests/test_no_local_paths.py
python -m pytest -q
python scripts/validate_docs.py
python scripts/sync_api_reference.py --check
python scripts/sync_tutorial_docs.py --check
git diff --check
```

`update` 遇到增长必须停下修源码，禁止借更新掩盖新 finding；没有 finding 变化时不制造 baseline 提交。修改 stable 目录外代码也要运行其定向 flake8/mypy 并记录已有债务，不扩大 ignore。

每线新增至少一个**安装后 public-path consumer**：构建 wheel，独立临时 venv 安装，从仓库外执行，不用 source PYTHONPATH、tests helper 或 Engine 私有字段。完整 API 输入/输出和断言必须保留；stub SDK 只能证明框架机制，不能写成真实模型成功。复用已有 wheel/page fixture 与构建命令，避免再造安装 harness。

本轮不改 package metadata；仍须 build wheel/sdist 与 twine check，因为每条线交付安装消费者。保留当前 Linux Python 3.10–3.12 兼容；无本地 3.10 可用时注明，不能使用仅 3.11+ 的无 guard 特性。

涉及公共教程，完整示例文件与 EN/zh named region 同步；API imports/signatures 有 contract binding。使用 `docs/AGENTS.md` 的页面检查要求；没有改页面布局的实现，不需重做全站装修。每条线的文档页 ownership 见自己的指令。

不使用 masked exit、rerun-only、缩样本、删除原测试或扩大 skip 制造绿色。既有 opt-in skip 单列，不计为本线 required success。真实 Docker 仅运行自己有标签的资源，四线不同时压测共享 daemon；失败时保留 typed platform 结果，不清理其他容器。跨进程排序用 Event/barrier 与有界 deadline。

## 5. Live 与责任边界

R1 必需门禁全部可离线，不依赖 private profile。默认不读取 credentials、不扫描环境、不请求模型。若用户另外提供**启动配置路径、显式 CredentialRef resolver 与本轮 aggregate 预算授权**，A 可追加一次有界功能观察，否则交付离线代码且记录 `live_not_run`，不是整个任务 blocked。

配置中的单次输出建议 10240，不是框架上限；不写死 2048/4096，不从历史聊天取密钥，不把 endpoint/key 写入代码、docs、fixtures 或报告。模型失败与 Agent 策略失败独立于框架 gate；框架丢结果、假终态、权限/持久化错误仍必须修。不得无限重试凑成功。

## 6. 独立完成、融合与停止边界

每线不等待其他线的 receipt。B 用现有 `extensions` mapping 完成配置消费（仓库没有独立 ExtensionRegistry 类型），D 用已冻结 Trajectory，C 用已有 producer，A 用现有 context。真正跨线接线另列一张短清单，由融合 owner 完成，不能据此虚报本地消费者通过。

建议融合顺序 **C → B → D → A**：先稳定 runtime，再加入上下文与 reader，最后 A 运行组合消费者。此文件不启动融合工作树，不授予 push/default-branch/release 权限。融合 owner 应先纳入本次 v5 草稿并保留最新 master 文档，再按来源顺序合入各线、手工合并共享文档与重生成 shrink baseline，完整复验一次。

融合的额外验收只有一条实际组合路径：installed config → memory/compaction → native multi-round tools → paused Session handoff/restore → journal page/export。它不需要实现新的审批或实时 daemon。每阶段对应独立可观察结果，live 另列。

实现代理结束时本地提交并保持 clean，**不 push、不部署、不发布、不修改 default branch、不删除 worktree**。合并并获准推送、验证成功后，协调者才能非强制退役已合入且 idle/clean 的工作树；保留 refs。

最终报告固定 12 项：Outcome（本线范围）；baseline/source；branch/worktree；行为修复与新增用户能力；before/after regression；installed consumer；完整验证与未运行项；API/quality/doc delta；明确限制及跨线交接；commits；最终 clean/HEAD；未执行的 remote/live/cleanup 操作。不重复粘贴整个历史阶段报告。
