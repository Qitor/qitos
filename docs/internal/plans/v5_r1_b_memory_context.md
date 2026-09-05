# 发给 Agent B：V5 R1 可直接使用的 Memory 与 Compaction

你负责 B 线实现。先读主工作树的 [共同合同](v5_dispatch.md)、[V5-02](../../v5/02-context-memory-compaction.md) 和本文件。目标是用户可以直接选择现成机制，不是再交一套空 protocol/fixtures。

## 1. 固定起点

```bash
git worktree add -b codex/v5-r1-b-memory-context ../WhitzardOS-v5-r1-b 4dfb570fb7eef504c1e6d247c21a1984251b80e4
```

执行前遵循共同预检；实施记录：`docs/internal/plans/v5_r1_b_execution.md`。

## 2. 源码与租约

必读 `core/context.py`、`memory.py`、`request_view.py`、`conversation.py`、`kit/memory/*`、`kit/history/compact_history.py`、`kit/context/*`、`engine/_context_runtime.py`、`config/_extensions.py` 和 baseline 的 `examples/tutorials/notes/context.py`。

可改 core/kit 的上述 context/memory/compaction 实现、`_context_runtime.py` 和自己的测试。config 文件只读；使用实际存在的 `build_agent_composition(..., extensions={...})` mapping/factory 参数，仓库没有独立 ExtensionRegistry 类。不得改 `_model_runtime.py`、provider、Session/checkpoint/WorkGraph、ArtifactRef store 或 CLI。如必须补 model-runtime 接线，提交小型 consumer test 与期望给 A/融合 owner，不复制 loop，也不能因此阻塞其余实现。

## 3. 通用 MemorySource adapter

1. 提供一个 concrete kit adapter，将既有 `Memory.retrieve` 结果转为 `MemorySource.contribute`，不为 Memdir/Markdown 各建一套协议。
2. 明确 query、namespace、record identity/revision、authority、priority、预算单位与 borrowed/owned 生命周期。默认只读检索；不可因为 engine reset 或 close 删除 cross-run 存储。memory 不能提升为 system 权限。
3. 以 MemdirMemory 为本轮 durable reference：进程 A 写记录并退出，进程 B 仅通过配置 reference/factory 重建并检索；第三个不同 namespace 不可见。记录修改/删除会改变贡献 identity 或 revision，不返回陈旧缓存。
4. MarkdownFileMemory 当前只从内存 `_records` 检索，不在构造时重载已有日志。必须测试并诚实标记这个边界：本轮为它提供同一个 adapter 和 run-scoped 消费，不把 append-only Markdown 日志说成无损跨进程 MemoryStore。不得用 eval/猜测字符串恢复旧 Python metadata。跨进程 Markdown reader/迁移如未实现仍列 02A 剩余项，不影响 Memdir reference 交付。
5. config 仅持久化 logical reference/JSON options，factory 在 composition 边界获得本地存储资源；不把 host path、callable、client、credential 写入 snapshot/provider diagnostics。missing resource/namespace mismatch 为可操作的 typed failure。

## 4. 一个现成、无模型的 compactor

1. 在 kit 实现确定性 closed-exchange window compaction，复用 `CompactionPolicy`、`CompactionReceipt` 和唯一 ExchangeLog/RequestView。
2. 默认框架仍是显式不压缩/拒绝损失；用户明确选用本策略后才允许它声明的有损窗口裁剪。不得静默开启 summary LLM。
3. 按完整 exchange 而非消息条数裁剪；保护未关闭 batch、call/result anchor、最近窗口、queued steering、required context/artifacts 与 continuation 约束。可裁剪项不足时 typed budget failure，不删除 required 来伪装满足预算。
4. selection/compaction 只生成派生 request，原 ExchangeLog 的 ID、completion order 和持久字节不被回写、重排或替换。
5. 输入选择 digest、policy/options、裁剪 IDs、单位/估计来源与 loss 必须准确。相同输入+选项确定性相同；原文已不可见后重新注入必要 contribution，不能仅凭相同 revision 永久跳过。
6. 历史 CompactHistory 保持原兼容行为与测试；本轮**不迁移模型摘要、不新增摘要 Engine**。把具体剩余 microcompact/summary/legacy-delegation 列入 02B 下一子包，不声称完整 02B 已退休。

## 5. 必需消费者与验收

新增 `tests/test_v5_memory_adapters.py`、`tests/core/test_v5_exchange_compaction.py` 和 installed consumer。至少覆盖：

- Memdir 两进程、独立 namespace、missing resource、更新 revision、borrowed 不关闭/清空。
- Markdown run-scoped 成功与 fresh-instance 不可恢复边界，不能误宣称 durable。
- 100 个 closed exchanges，含乱序完成工具，至少两次 compaction，保持原事实不变。
- open batch、missing required artifact、reasoning/continuation、steering、预算不足。
- 重复 selection 确定性、恢复后 visibility reset、serializer isolation。

安装后从 `examples/v5/r1_b_memory_context/` 的完整配置启动：进程 A 记忆写入 → 进程 B composition 检索 → 通过既有模型请求路径实际看到 memory 与裁剪后的 RequestView。允许 deterministic provider，但不能只直接调用 adapter 就宣称配置接线成功。

必跑旧 memory/history/context tests：`tests/test_memory_and_parser_and_critic.py`、`tests/test_compact_history.py`、`tests/test_coder_compact_history.py`、`tests/core/test_s4_context_extensions.py`、`tests/test_context_contributor_conformance.py`，再跑共同门禁。

## 6. 文档、交接、完成

公共文档 owner：EN/zh `guides/memory-and-history.mdx`、`reference/context.mdx`，及其完整教学源文件 `examples/tutorials/notes/context.py`。改写“仅自定义示例可用”的内容时，只宣称本轮已完成的 Memdir/窗口策略；保留 Markdown/summary 限制。

建议提交：memory adapter/两进程 → deterministic compactor → configured installed consumer → bilingual tutorial/API binding → shrink/evidence。

R1-B 完成不是整个 V5-02 完成。须清楚列出 deferred：摘要模型统一调用、Markdown 重建、完整 legacy history 退休、跨 Agent memory policy、大工作区与原 Agent 迁移。无需等待 A/D 新产物才交付；不 push、不删除 worktree，按共同 12 项报告结束。

## 7. 加强后的用户 API 与验收判据

以下为本轮要实现的 module-level API，不是已有 import：

- `qitos.kit.memory.adapter.MemorySourceAdapter(memory, *, namespace, query=None, required=False, priority=0)`；实现现有 `MemorySource.contribute`，持有 borrowed Memory，不擅自 close/reset。
- `qitos.kit.context.compaction.ClosedExchangeWindowCompactor()`；实现既有 `CompactionPolicy.compact`。窗口大小由现有 `ContextBudget.protected_recent_exchanges` 决定，不再创建第二 window 参数 owner。策略只为已验证可省略的 closed exchanges 生成确定性 loss receipt，selection 权威仍在 RequestView。

配置只需两个已有槽位：

```yaml
memory:
  sources: [project_memory]
compaction:
  provider: closed_window
```

程序将 `project_memory` 绑定 adapter、`closed_window` 绑定 compactor，通过 `build_agent_composition(config, extensions=extensions, ...)` 启动。普通用户不手写 receipt、不拼 messages。任何现有 loss opt-in 必须在例子中显式标明，不能内部偷偷开启 blanket allow_loss。更改 public 名称或新增必需参数须先说明具体不兼容原因，不自行再建一个 registry。

### Memory 判据

1. Memdir 中相同持久记录在写入进程与重建进程只贡献一次。当前 retrieve 同时合并 `_records` 和磁盘文件，必须防止同一条双计；不能仅按文本相等合并两条真实独立记录。
2. namespace 是 resolver/factory 绑定的逻辑域，不是获得任意目录权限的字符串；默认不挂 global memory。A 域写入固定文本 `remembered-value=17`，B 域看不到；重建 A 域才能读到。
3. 相同持久 record 的 identity 稳定，内容修改改变 revision/digest；host path 不能进 contribution ID、metadata 投影或模型提示。Memdir 文本记录是本轮支持子集，不声称任意 Python/JSON MemoryRecord 无损落盘。
4. 只读打开不存在的域必须在 composition/reference 校验边界 typed fail；明确的新域初始化可创建目录，不能把恢复缺失误认为新的空记忆。
5. reset/evict 只按已声明内存缓存语义；不在 adapter 构造、contribute 或 close 时做持久删除。Markdown 只交付 run-scoped，不推断可恢复性。

### Compaction 判据

1. 测试设置 protected_recent_exchanges=2，裁剪顺序固定为最旧 eligible closed exchange 优先。相同输入/policy/budget 必须选同一组 ID，优先级和权限不能被 memory 改写。
2. 两种断言分开：在固定预算下确实减少 request 内容；原 ExchangeLog 序列化前后完全相同。测试不能只断言生成 receipt。
3. 100 closed exchanges 的 fixture 至少两次预算触发，恢复后再次选择只依赖持久事实和重建配置。原 batch 中两个乱序 result 始终作为完整 exchange 一起保留/省略。
4. required context/最近保护窗口本身已超预算时 typed failure；不能删除它们、增加预算或生成虚假 summary。
5. 尚未闭合的 batch 不成为可压缩来源；pending steering 一次性消费，provider continuation 能力限制沿用现有 codec，不能因裁剪跨越约束。

安装验收分两个真实独立 Python 进程：seed 写文本并退出；run 从配置重建，模型请求可见 17 和真实 compaction 选择。框架 budget/trace/request hooks 验证内容，不只调用 adapter。新增模型摘要、任意远端 memory、跨 Agent 策略都不在 R1。
