# 发给 Agent D：V5 R1 严格完整性下的 Trajectory 效率

你负责 D 线实现。先读 [共同合同](v5_dispatch.md)、[修订后的 V5-04](../../v5/04-trajectory-and-research-data.md)。不重建 canonical schema，不重新切默认 reader，不重做 master 已完成的 verified-bytes parsing cache。

## 1. 固定起点

```bash
git worktree add -b codex/v5-r1-d-trajectory-efficiency ../WhitzardOS-v5-r1-d 4dfb570fb7eef504c1e6d247c21a1984251b80e4
```

共同预检后实施；记录：`docs/internal/plans/v5_r1_d_execution.md`。

## 2. 范围与现状

必读 `qitos/tracing/journal_store.py`、`store.py`、`readers.py`、`exporter.py`、`trajectory.py`、`qitos/qita/reader.py`、`_cli_app.py`，及 journal durability/readonly/default/historical tests。

可写上述 store/reader/export/qita read-only 代码与对应 tests/benchmarks；ArtifactRef 只按现有 resolver 消费。不得改 Session/checkpoint/WorkGraph/model/runtime facts、canonical wire、privacy 默认、publication 或新增第二持久化真相。不要在本轮加 GC、四种训练 exporter、compression dependency、强 sandbox 或重新发布原 campaign。

当前 verified cache 免于重复 JSON 解析，但每次 `_load` 仍 hash 整个文件；`_write_index` 仍重建/重写索引，完整 reader 仍全物化。**严格默认发现同 size/mtime 的历史修改必须保留。** 不用 stat、锁、cache 标记冒充任意历史字节未变的证据。

## 3. 先量工作量，再改机制

1. 新增 `tests/tracing/test_v5_journal_work_budget.py` instrumentation，分别计 read/hash bytes、decoded records、copied records、index entries visited/written、fsync calls。固定 record shape 和 warm/cold 条件，记录 baseline 实际结果。
2. 本轮主要降低 index 重建/重写与 page materialization 成本，不承诺严格单文件每次 integrity scan 的读字节为 O(1)。不得把“免解析”宣传成“免读取”。
3. index 仍 derived；可做增量维护、分段派生索引或明确 checkpoint/rebuild cadence，但必须可从 journal 全量恢复。index 失败/落后不能谎称其 committed head 与 journal 相同。
4. warm 单条 append 不遍历全部历史以重建索引；正常 append 可以不写派生索引，但必须有有界且明确的维护/刷新边界，不能永久放弃索引令所有查询全解码。选择的策略在首个实现提交说明。
5. 原子写入、fsync ack、duplicate retry、短写不确定性、recover tail、跨 writer lock 和 schema freeze 保持原合同。不能 raise timeout 代替优化。

## 4. 真正有界的 reader 与流式 canonical export

1. 提供明确 page/iterator 能力，复用现有 reader/store seam。旧 `read_run/read_session` 返回完整 Trajectory 的 API 不改类型；新调用者可明确选择不物化整条历史。
2. 不能让 iterator 先构造一个含全部历史的 JournalTrajectoryStore/tuple 再逐项 yield。新增路径自己的峰值 retained records 与 page/最大 frame 大小有关，不随总 record count 增长；已有全物化 writer cache 单独披露，不冒称整个进程常量内存。
3. cursor 绑定 filter、顺序与 read boundary/head；并发 append 不重复/丢记录，截断、替换、corrupt index 和旧 cursor 明确 reject/restart，不从文件名猜 lineage。
4. 完整性语义精确：在报告 export complete 前必须验证声明范围的 frame/chain/record。提前输出 partial bytes 的 export 只能标 partial；写文件使用 staging+成功后发布，失败不留下被误认 completed 的目标。只读 reader 不自动截断/恢复 journal。
5. 将现有 canonical exporter 的大输入读取/写出接入有界路径，保持同样可重导入的 canonical 事实。**输出路径不能先收集全 records 再 json.dumps 全对象。** EventSummary 等未迁移路径如仍物化要明确。
6. qita live poll 或 export 至少一个真实 consumer 使用新 reader 能力；qita 不新增执行/控制行为。第三方无分页 reader 有明确 fallback/capability，不强制外部包继承实现类。

## 5. 验收矩阵和收益声明

必测：两 writer、同尺寸且 mtime 还原的字节损坏、外部 append、index 缺失/陈旧/损坏、partial frame、fsync fail、duplicate retry、只读模式、page boundary、iterator close、filter/cursor mismatch、source truncated/replaced。

数据：相同 deterministic source 10k 和 100k records，加一个本线 wheel 生成的真实运行 journal。大样本用 bounded append_batch 生成，不用逐条严格全 hash 的平方成本污染 reader 测量。数据构造时间与读写测量分栏。

至少 5 次测量，保留全值、median/p95、Python/platform、frame/page 大小、warm/cold、tracemalloc 与 RSS 的区别。before 用固定 baseline，after 用本线 commit。快速 CI 以工作量断言为主，性能脚本不得拿平台偶发速度作为正确性判断。

R1 硬条件：warm append 不逐次全索引重建；bounded reader/export 不保留全历史对象；与 canonical 完整读取逐 record 相同；完整性/崩溃/read-only 不退化。严格历史扫描仍 O(N) 可合格，但必须标 `suffix_only_io=not_implemented`；不通过暗改 trust model 宣布更高收益。

## 6. 验证、文档和交接

新增 `tests/tracing/test_v5_bounded_reader.py`、`tests/tracing/test_v5_streaming_export.py` 和工作量测试。必跑 `tests/tracing/`、`tests/qita/`、`tests/test_trajectory_exporter_conformance.py`、installed qita/public consumers 与共同门禁。

完整安装示例放 `examples/v5/r1_d_trajectory/`。公共文档 owner：EN/zh `guides/observability.mdx`、`reference/trajectory.mdx`、`reference/cli.mdx` 的 qita 部分，及 `notes/inspect_run.py`。运行教学 source/MDX/API checks；不重做站点结构。

建议提交：同源 workload instrumentation → derived index 优化 → bounded reader → streaming export/qita → benchmark/docs/shrink/evidence。交接给 A/B/C 的是现有事实的读取方式，不要求它们再制作 schema receipts。

明确未完成：真正 suffix-only I/O、Artifact GC/lifecycle、四类外部训练格式、原 campaign 出版资格、全路径 bounded RSS。不要用 R1-D 完成冒充整个 V5-04 完成。按共同 12 项报告交付 clean 本地 commits，不 push、不删除 worktree。

## 7. 加强后的 read boundary、index 与内存合同

### 用户可选入口

为既有 reader 增加可查询的分页能力；目标用法是 `page = reader.read_page(query, cursor=None)`，消费 `page.records`，续页传 `page.next_cursor`。该 API 是本轮目标，不是已有接口。新类型只放 tracing 模块级，旧 `read_run/read_session` 和第三方最小 reader protocol 保持可用。

bounded iterator 是这一路径的便利封装，不是另一个 Store。无分页能力的第三方 reader 必须在要求 bounded 模式时 typed unsupported，不能静默全量读取；旧非 bounded 接口仍可明确使用旧 fallback。

### 固定 cursor 语义

- 首页捕获 filter digest、source identity、head sequence/digest、committed byte boundary。后续页只读到该 head；新 append 不混入本次遍历。
- cursor 包含下一 sequence/offset 与必要校验字段，是不含 host path/secret 的 opaque continuation；不能信任调用方随便改的 offset，reader 必须重新验证绑定。
- 同一 cursor 重读同一页得到同样 records；按 sequence 严格递增，最后 next_cursor=None。更改 filter、错误 source、截断、替换、边界前损坏都 typed reject。
- live polling 完成一轮后显式开始新 head 读取；只消费上次 watermark 之后的新增记录。不要把一致性快照游标与移动 tail 隐式混合。
- 整个长遍历不持有阻塞 writer 的全程锁。每次有限读取使用当前既有锁/descriptor 校验；不承诺防御任意恶意宿主在验证后修改内存/磁盘。

### Index 与 durability

- journal 是 truth；索引只有经核验与 committed head 对齐才用于正确性敏感寻址。缺失/陈旧可受控 rebuild，损坏不能放行错误 record。
- 索引可记录落后 watermark、批量 checkpoint，但必须有显式 flush/rebuild 边界与 crash tests。journal fsync 成功、derived index 失败可区分报告；反过来绝不能给 persisted receipt。
- 已缓存 record-ID/positions 映射可增量更新；warm append 不每次遍历全部 records 建 dict/全索引。严格全字节 hash 单列保留，不能计作这项失败或藏到计时外。
- 最终 flush/close 或显式 rebuild 的 O(N) 成本可以存在，必须实测并披露；不得通过把所有成本挪到每次隐式 flush 达成纸面 append 优化。

### 有界读取的硬判据

测试数据固定为 1 KiB record payload、每 frame 最多 32 records；10k/100k 两个规模，page limit=128。构造 writer 在不同进程退出后再启动 measured reader，防止 writer cache 污染或掩盖读取成本。

必须有实际 retained-object instrumentation 证明：reader 不创建全日志 Trajectory、不保留与 N 同比例的 payload/record/全索引对象；工作集最多是当前 page、一个受 frame 限制的解析缓冲、固定大小 validation/I/O buffers 与 cursor。完整性扫描可解码历史，但不得积累全部历史。

tracemalloc/RSS 辅助记录峰值和增长，不以一个随意的 wall-time 数字代替上述机制断言。若代码仍全量 index/record cache，即使遍历 API 叫 generator 也不通过。

### Export 成功发布判据

canonical export 到 staging 文件，完整 frame/chain/record 验证和文件 flush 成功后再以现有安全 publication 机制发布目标；不修改 sandbox publication。格式/record 字节语义与旧 canonical exporter 一致，重新导入逐 record 等价。

late corruption、目标写失败、iterator cancel 时没有新 completed export，原目标存在则保持不变；staging 只清理本次自有文件。若用户要求直接 stream 输出，只能显式 partial-until-final，不提前发 completed receipt。raw/private 与 public redaction 的边界不变。
