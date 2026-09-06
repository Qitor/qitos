# V5 R1 — 有界修复、融合与用户路径验收

**Executed R1 closure (2026-09-06):** preservation and all 27 replays complete; five repairs, same-wheel original/combined consumers, 20 handoff rounds and complete qualification pass on `55c356f9d0f6b0df431ac1427f2373dfd5e540fa`. The current user instruction authorizes qualified local master fast-forward and non-forced retirement; it replaces earlier waiting-for-authorization text. Remote sync/push is still unauthorized. Final local acceptance SHA and actual retirement receipts are reported by the executing task after these gates, avoiding a self-referential SHA commit. This plan has no deferred documentation-only closing round. See [execution evidence](v5_r1_integration_execution.md).

日期：2026-09-05。状态：`planned`；本文件不是融合已执行或 push 授权。
依据：[独立实现审查](v5_r1_integration_review.md)。

## 1. 本轮结果与停止边界

由一个 integration owner 完成，不重新开四条互相等待的 producer 线。
交付：一个吸收四线成果、修复五项已证实缺口、通过安装后组合消费者的新候选。
目标是用户可以配置、运行、恢复、检查自己的 Agent；不新建 Engine、Session、
canonical outcome 或 Trajectory，不把本轮扩展为全仓库旧债清理。

本计划只规划动作。执行者须得到用户的融合任务授权后才创建工作树、重放和提交。
推送、主工作树提升、发布和清理分别遵循该次任务的明确授权；本次审查没有执行它们。

## 2. 固定来源与预检

唯一源码起点：`4dfb570fb7eef504c1e6d247c21a1984251b80e4`。
拟用分支 `codex/v5-r1-integration`；拟用主仓库旁的
`WhitzardOS-v5-r1-integration` 工作树。不存在时从该 SHA 创建；已经存在则先核验归属、
HEAD、merge-base、dirty 状态，不覆盖、不强制复用。未来 moving master 不替换固定来源。

逐项核验以下四个 source HEAD，提取 baseline 到 HEAD 的完整有序 commit 清单：

| 顺序 | Source branch | 固定 HEAD | 提交数 |
|---|---|---|---:|
| 1 | codex/v5-r1-c-runtime-correctness | `5b8a4363e59fd01286009741b26597f197de706b` | 6 |
| 2 | codex/v5-r1-b-memory-context | `4b62f46712f1683338c0b7590ae1290c492cb542` | 4 |
| 3 | codex/v5-r1-d-trajectory-efficiency | `522ce90abf5a39fd5510fd254652a256ad283f4f` | 11 |
| 4 | codex/v5-r1-a-model-io | `5c6c2c370c0465e5471024a6e4870a9feb8c2b2a` | 6 |

共 27 个提交，按每线原有顺序重放；产生 source/replay 映射，不 squash 丢失来源。
没有必要为了融合另建逐字段 producer manifest 层。

必读：根及实际编辑目录 AGENTS、docs/AGENTS、ARCHITECTURE、framework-responsibility-boundary、
本审查、四份实施报告、[V5 总纲](../../v5/README.md)。后续修复先读相关源码/测试，
不能仅根据本文件行文猜实现。

当前 main 是带 V5 草稿的旧文档 HEAD。明确保存/导入这批规划输入，保留远端已完成的
教程更新；不得 pull、stash、reset 或用旧 README 覆盖新教程。主工作树仍有未提交内容时
不能直接 fast-forward：先逐项证明它们已保留在候选提交中，并按照用户授权处理；
无法证明时保留候选和主工作树，报告准确差异，不能以清空工作区换“clean”。

## 3. 融合租约与冲突处理

本轮 integration owner 统一拥有四线交叉接线和下列五项修复，不让各线同时改共享文件。

- `_model_runtime.py`：同时保留 step/exchange identity、预选择 compaction、真实工具
  completion order、声明顺序 request view、dispatch admission/计费与失败退款事实。
- config loader/builder/extensions：仅接通现有 budget policy 与显式 codec loss 选项；
  不增加全新配置体系、不将 secret/resolver/live object 放入持久化配置。
- Session/WorkRuntime：仅修 handoff 归属与已知调度失败；CAS、未知效果不重放、source
  失权后不得写 head 的原则不变。
- docs bindings/generated pages/sync script：保留四线条目，融合 B/D 脚本改动，再针对
  真实合并源码重生成 EN/zh 页面。不得整文件 ours/theirs。
- quality baseline：按当前融合源码校验；只 shrink 已修 finding，不扩大 allowance、
  放宽工具链、忽略冲突或把其他线的 JSON 整体覆盖回来。

## 4. 五项有界修复与验收 oracle

### 4.1 R1-M1：reasoning 的真实保留

用实际 OpenAI-compatible sync/async adapter，只替换 SDK I/O。输入分段 reasoning、
普通内容、并行工具及后续工具轮。支持的 reasoning 出现在既有 canonical representation，
不混入 answer、不重复；历史重读和下一 RequestView 仍保留。无法表达则按现有
capability/loss 合同拒绝或报告，不能 silent drop。没有 reasoning 的 provider 不补造内容。

### 4.2 R1-M2：清理异常与主失败

覆盖正常终止、EOF/协议失败、transport failure、consumer callback failure、主动 close、
async cancellation；分别注入 response close、client close 和两者同时失败。
所有 owned resource 均被尝试清理；借用资源不关闭。主失败的类别、sent、usage、partial
事实保留；附加 cleanup failure 有界脱敏；没有主失败时清理失败也不能假成功。
禁止 raw endpoint/header/token/host path 或 synthetic private marker 出现在公开 diagnostics。

### 4.3 R1-C1：终态必须属于准确 work/transfer

先把审查中的合法双 work graph 反例变成 failing regression，再增加公开 Session/SQLite
消费者：两个 work/session 使用同一个 Agent，只有一个完成时另一个不变；增加 parent/child、
重复 handoff、同 Agent 再次接管、过期 generation、late callback 场景。
以显式 work/session/run/transfer/generation 绑定事实，不解析名字或路径推断归属。
保持 C 已通过的源 callback / destination restore 交错矩阵，并在最终源码执行 20 轮
Event/barrier 驱动的有界验证；不使用 sleep 排序或 rerun-only。

### 4.4 R1-C2：区分未调度与结果未知

覆盖队列拒绝、scheduler unavailable、resolver 在 worker 创建前失败，以及真实 dispatch 后
失联。前者需要落盘的准确 admission/failure 与可执行恢复路径；后者仍为 unknown，不自动重放。
显式同 operation ID retry 的返回、调度次数和 ownership 必须可解释。证明没有重复 effect、
没有把 callback ack 当任务完成，也没有为记录调度失败而让旧 owner 绕过 fencing。
这里只支持本地已声明的 scheduler 合同，不要求实现分布式调度或远程硬取消。

### 4.5 R1-DX1：纯 YAML 的预算与有损选择

公开 `load_agent_config` 接受 `context.budget_policy`、`context.allow_codec_loss` 的严格
合法形状；named policy 从现有 extensions factory 解析。未知名字、错误布尔值、缺失 loss
opt-in 在首个请求前 typed fail。B 示例不再依赖 `dataclasses.replace` 才能启用机制。
配置开关不引入策略魔法：摘要内容、预算大小和 memory 选择仍由 Agent 作者决定。

## 5. 一个组合消费者，另加一个失败变体

复用四线已安装消费者的组件；从同一个最终 wheel 安装到独立 venv，在仓库外运行，
不使用 source PYTHONPATH、tests helper、Engine 私有字段或第二执行循环。

正常路径必须全部真实发生：

1. 公开 YAML + 显式 resolver/extensions 创建 AgentComposition 和 durable Session。
2. 第一进程创建 Memdir 记录；后一进程恢复后召回，另一 namespace 不得到该记录。
3. 使用内置 adapter 的离线 SDK transport，至少三次请求、两轮工具，强制产生可验证的
   乱序完成。ExchangeLog 存真实完成顺序，provider request 符合声明关联。
4. 在一条足够长的确定性对话中至少两次触发真实预算选择和 closed-window omission；
   记录 loss，保留 required context/artifact、开放 batch 和最近窗口，原日志不被覆盖。
   continuation 与可压缩/不可压缩边界分别验证，不为了触发压缩删掉保护条件。
5. 暂停后同 Session handoff/clean-process restore，正确 owner 继续；另一个同 Agent 的
   work item 不被误关闭。检查 operation、head generation、state 与终态。
6. canonical journal 有对应事实；reader page/iterator 与 canonical export/reimport 逐项等价，
   qita 只消费 reader。资源 close 后无消费者自建的后台线程/进程/临时索引残留。

失败变体：第二轮 stream 在完整工具 batch 之前截断并注入清理失败；未完成 batch 的工具
不执行，不出现成功 final，不丢失已完成工具结果，sent/usage/partial/cleanup facts 正确。
最终不因增加消费者而改变核心默认参数或 root exports。

## 6. 兼容性与文档

- 明确 Memdir 默认恢复现有目录、创建需 `create=True`；修正实际新手示例。
- Read/Edit 直接调用返回 ToolResult，给出旧字符串消费者迁移例；维持 canonical result
  的唯一性，不声明所有历史调用无变化。
- 保留 Observation dict/dataclass/旧 checkpoint 覆盖。
- D 只声明已测得的内存/索引收益，同时报告 full-byte hash、writer RSS、冷启动、遍历
  和 I/O 成本。不开 suffix-only/GC/训练格式的新任务以拖住 R1。
- README/README.zh、CHANGELOG、相关 API/tutorial、V5 状态和 progress 同步；历史测量
  与资格保留原 source，新的执行结果必须绑定最终 code HEAD/wheel digest。

## 7. 最终验证与交付

在固定 Python 3.12.7 和 quality/toolchain.json 下：先各修复定向回归，再全套 pytest、
stable flake8/mypy、相对精确基线的 ratchet、architecture/public/no-local-path、build/twine、
四线原 installed consumers 和新增组合消费者。按 docs/AGENTS 完成 source bindings、
EN/zh 同步、MDX/链接及改动教程的桌面/移动端检查，不重复无关全站装修。

完整 pytest 中 50 个 live opt-in 和显式 Docker skip 单列，不充当本轮 required success。
安全/Env 语义未变化时不扩大 Docker 压力矩阵；若修复实质触及其路径，则串行执行对应
真实 Docker gate，不清理无关容器。Linux/Python 3.10–3.12 支持声明需要相应环境证据，
本机没有的环境诚实注明，不把本地 3.12 通过写成整矩阵通过。

Live 默认 `not_run`。只有另获启动配置、CredentialRef 和本轮累计预算授权才追加有限测试；
不从聊天重抄密钥、不扫描凭据、不把单次输出写死 4096。上游不可用不阻断离线框架融合，
但不能据此声称真实任务成功。

交付报告只需：准确来源/27 项映射、五项修复及 before/after、组合消费者、完整验证、
兼容变化、剩余范围、最终 HEAD/clean、promotion/push/cleanup 各自真实状态。
不制造另一轮只有文档身份更新、没有行为收益的资格任务。

## 8. 新 baseline 与后续四线

只有修复、组合消费者和最终门禁通过，才冻结新的 R1 integrated code HEAD。若获得提升
授权，在保存 main 草稿后 fast-forward 并复验；若获得 push 授权，再非强制同步并回读。
未实际产生 SHA 时不发布占位符 dispatch；R2 四线一律从最终被接受的同一完整 SHA 创建。

推送/验证后，按用户此前的空间回收要求，用非强制 `git worktree remove` 退役本轮已合入、
idle、clean 的四个来源工作树及临时 integration 工作树，保留 branch refs。cherry-pick 后
须证明 patch/行为已吸收，不能只用祖先判断；不删除 main、无关 docs-learning 或有未保留
文件的工作树。报告实际删除对象和可由 refs 重建，不预先宣称已释放空间。

之后再冻结 R2 的四条实际能力线，建议分工如下，不属于本轮新增实现范围：

| 线 | 下一用户结果 | 主要归属与边界 |
|---|---|---|
| A | 原有仓库外 Agent 的真实迁移与有界端到端对照，量化框架胶水减少 | V5-01C/D；prompt/策略不写进 core，真实模型与框架正确性分开报告 |
| B | 长会话/跨 run memory 的稳定使用路径，必要时增加可替换摘要策略 | V5-02C/D；摘要模型走 canonical provider/预算，不复制请求循环 |
| C | 可恢复的审批与明确 Session 控制边界 | V5-05A/B；唯一拥有 Session/permission 接线，不能把没有 daemon 的 CLI 伪装成实时控制 |
| D | 一种明确的研究训练/eval 导出及 Artifact 引用消费 | V5-04B/C；限定格式、loss 与授权数据，不以 campaign 出版为默认前提 |

func/SharedMemory/MCP/hooks/旧 presets/packaging 的 V5-03 剩余包仍在账本中，按具名消费者
拆入后续波次；不因改派 C 做交互能力而假称这些清理完成。R2 正式指令需在新 baseline
上再核对最小文件租约，避免 A 的迁移接线与 B/C 重复编辑 runtime/config。
