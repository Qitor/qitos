# V5-02 — 可直接使用的长任务上下文、记忆与压缩

状态：`in_progress`；R1-B 的 Memdir adapter、确定性 compactor、纯 YAML 接线与组合验收已完成。优先级：高。后续范围遵循 [共同合同](README.md)；当前状态统一见[本轮记录](../internal/plans/v5_r1_remote_sync.md)。
承接 v4 04A–D、02B/D、10F 中 request-budget/token/history 归属。

## 1. 用户结果

用户通过 composition/config 选择少量成熟基础实现，就能使用项目指令、会话上下文、跨 run memory、长对话压缩和 artifact 引用。高级用户仍能替换 contributor/selector/compactor；普通用户不必自己生成 CompactionReceipt 或拼接 messages。

Memory 内容、检索策略和语义摘要质量属于 Agent 作者；框架负责生命周期、可见性、预算、权限、损失和恢复的一致性。本组不提供“所有任务最优”的记忆算法，不把 benchmark 策略或源码路径排序特例写入核心。

## 2. 起点与必读

- [原 context/memory 任务](../v4/04-context-injection-and-memory.md)、[会话合同](../v4/02-conversation-kernel.md)。
- `qitos/core/context.py`、`memory.py`、`request_view.py`、`conversation.py`、`artifact.py`。
- `qitos/kit/memory/`、`qitos/kit/history/compact_history.py`、`qitos/kit/context/`。
- `qitos/engine/_context_runtime.py`、`_model_runtime.py`、`qitos/config/_extensions.py`。
- `tests/core/test_s4_context_extensions.py`、`tests/test_context_contributor_conformance.py`、`examples/tutorials/context_memory.py`。

历史审计起点（MemorySourceAdapter 已由 R1 接入）：Memdir/Markdown 原为旧 Memory.retrieve 接口；教程 memory 为 static contributor，compactor 为明确有损删除。CompactHistory 仍拥有 HistoryMessage 列表和旧 summary 调用。不能把“接口存在”直接当成内置长任务体验完成。

## 3. Ownership 与依赖

本组 owns core 的 context/memory/request-view 语义、kit 的具体实现、`_context_runtime.py`。新增公开类型先复用现有协议，默认零 root exports 增长。

01 串行集成 `_model_runtime.py` 的模型调用/accounting；config 注册按共同租约交付，不能另建 registry/composition root。04 owns ArtifactRef store/retrieval；05 owns Session snapshot/control；03 owns Observation 迁移。可先完成 adapter 和独立 conformance，不需要等待全部集成。

## 4. 子任务

### 02A — 既有 memory 的正式适配

1. 在 kit 提供一个通用、显式的 Memory→MemorySource adapter；复用 MemdirMemory/MarkdownFileMemory，不为每个策略复制一套协议。
2. 明确 write/append、retrieve、reset、evict、close 和 namespace 的 owner；新 run 不得无意清除 cross-run memory。调用方的 borrowed memory 不被 composition 关闭或删除。
3. 将检索记录映射为稳定 contribution identity/revision/source/provenance，保留实际 selection、omission 和 retention 事实。跨 Agent transfer 按现有授权交集，不把所有记忆继承给 child。
4. config 中使用 logical reference/factory 注册，不持久化 callable、live object、宿主路径或秘密。缺少 resolver/不兼容 namespace 要 typed fail，不静默创建空 memory。
5. 提供 run-scoped 和 cross-run 两个完整 installed 示例；后者必须进程 A 写入、进程 B 重建并检索，不能只在一个 Python 对象里读两次。

验收：默认 adapter 直接可用、第三方 MemorySource conformance 通过、隔离/删除/恢复语义明确。Vector/远端数据库能力只在已声明支持范围验证，不借适配任务扩充全部存储后端。

### 02B — exchange-safe 内置 compaction

1. 把旧 CompactHistory 中仍有价值的窗口、microcompact、摘要机制迁到唯一 exchange/request selection 路径；历史 API 在边界委托，不再建立第二会话真相。
2. 提供一个无需模型的确定性窗口/引用化基础策略，以及显式选择的摘要策略。摘要内容策略可替换；summary model 调用必须走 01 的 canonical provider/预算/error 路径。
3. 只处理允许压缩的完整 closed exchanges；保护开放 batch、必要 tool anchors、最近窗口、未消费 steering、required context/artifact 和 continuation 约束。
4. 记录 input IDs/digest、policy/config、原单位、实际 output/summary digest、budget、loss；失败不能留下半替换会话。原始 ExchangeLog 事实不被摘要覆盖。
5. 不再从 SummaryCompactor 直接偷偷调用旧 `llm(...)` 后吞错。默认拒绝或采用用户明确选择的 fallback，并记录失败、实际请求和损失。
6. 旧 `History.retrieve/CompactHistory` 的兼容路径有 before/after tests；只删除已替代机制，不批量改变用户摘要 prompt。

验收：不孤立 call/result，不通过删除 required 内容“让预算过关”；重复处理同一 input/policy 不重复写入摘要；完整回放仍可读取原事实。

### 02C — 上下文可见性、预算与恢复

1. 统一当前 request budget owner；不同 tokenizer/heuristic 必须标明估计来源，不把字符数当精确 token。
2. revision/digest 去重只针对实际可见上下文。compaction、stateless replay、恢复后上下文不可见时重新注入，不能因为 revision 没变永久跳过。
3. project/user/session/runtime contributions 的优先级、placement、persistence horizon 一致；runtime control context 不伪装成用户 steering，记忆不提升为 system authority。
4. artifact 原文外置后必须可经 resolver 检索；required 缺失/损坏为 typed failure，optional omission 有明确 receipt。跟随 04 的 store，不复制 body 到每条记录。
5. Session snapshot 只保存重建所需身份与选择事实；通过 05 owner 接线。restore/fork/transfer 后的 memory namespace、compaction、steering 和 continuation 均不串线。

### 02D — 长任务消费者与收益

1. 定义固定长会话：至少 100 个 closed exchanges，含不同完成顺序的 tools、多模态引用、两次 compaction、一次 fresh-process restore、一次 steering。
2. 另加 adversarial open batch、missing artifact、过期 continuation、摘要失败和 budget exhaustion；使用确定性模型即可证明机制，不必为每项调用 live。
3. 对同一输入比较旧路径、基础策略和显式摘要策略：request 大小、模型请求/summary 次数、tool-result 关联、恢复事实、耗时、实际 token/估计 token。
4. 联合 01 的真实迁移 Agent 验证长任务；不改变 prompts/tasks/model 后宣称框架压缩提高了成功率。策略没有改善也保留结果。

## 5. 必需测试矩阵

| 维度 | 必须覆盖 |
|---|---|
| memory | run/cross-run、两进程、namespace、borrowed/owned、missing resolver、eviction |
| context | required/optional、priority/placement、修改 revision、同 revision 失去可见性、权限隔离 |
| compaction | closed/open batch、reasoning/opaque、多模态、重复请求、summary failure、非 JSON 输出 |
| recovery | pause/restore/fork、queued steering 一次、旧 reader compatibility、partial failure |
| budgets | 输入/输出/summary 调用、估计单位、无 tokenizer、超预算拒绝、不隐式加预算 |

先运行已有 context/memory/history 测试及 `tests/core/test_s4_context_extensions.py`、`tests/test_context_contributor_conformance.py`。新增建议 `tests/engine/test_v5_long_context_restore.py`、`tests/test_v5_memory_adapters.py`，再跑共同门禁。测试进程使用 Event/barrier 和有界 deadline，不用 sleep 排序制造恢复正确性。

## 6. V5 整体交付与完成（R1 子集见文末）

- [ ] 02A 两种既有 memory 可通过统一 adapter/config 使用，跨 run 示例实际执行。
- [ ] 02B 内置 compaction 可直接选择，旧机制已委托，完整 exchange/预算/损失不变假。
- [ ] 02C visibility、artifact、steering、continuation 和 namespace 可恢复。
- [ ] 02D 固定长任务及真实迁移消费者分别给出机制与任务结果。
- [ ] 01/04/05 独立 consumer 通过；第三方扩展不读取 Engine 私有字段。
- [ ] 新旧路径、默认选择与限制进入 EN/zh 教程；不存在第二会话 store 或隐式 summary 模型请求。

实施/证据文件：`docs/internal/plans/v5_long_task_context.md`（实现时创建）。建议提交：memory adapter → closed-exchange compaction → owner 接线 → 长任务/恢复消费者 → 教程与迁移。输出应包含移除的重复 history/token 机制，不只列新增类名。

## R1 integration closure — 2026-09-06

DX1 已修复：纯 YAML 的 budget_policy 名称和真实布尔 allow_codec_loss 经显式 extensions 解析。Memdir 默认恢复，初始化 create=True；组合消费者真实 namespace 隔离、重复压缩且 required memory/artifact、recent window、continuation/open batch 保护通过。原始 ExchangeLog 在恢复后不再从有损 History 重建。Markdown durable reader 与模型摘要仍未实现。

完整来源、修复和验证见[融合执行](../internal/plans/v5_r1_integration_execution.md)。本轮 live_not_run，R1 不等于 V5 全完成。
