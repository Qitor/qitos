# V5-04 — 高效轨迹、Artifact 与研究数据消费

状态：`in_progress`；R1-D 的索引、bounded reader、流式 canonical export 与组合验收已完成。优先级：高。后续范围遵循 [共同合同](README.md)；当前状态统一见[本轮记录](../internal/plans/v5_r1_remote_sync.md)。
承接 v4 05A–E 中未完效率/export 工作、00 Gate D 和 10E/F。

本轮数据见[独立审查](../internal/plans/v5_r1_integration_review.md)：100k warm append 中位数
约 0.172→0.087 秒、导出 Python 分配峰值约 1.44 MB，均为 D 指定源码/样本的报告值。
旧字节仍全量 hash，writer 仍 O(N) 驻留，部分遍历更慢。不可将其描述为所有旧 API 有界内存
或 suffix-only I/O；GC、外部训练格式与数据出版没有因 canonical export 完成而关闭。

## 1. 用户结果与已完成边界

长任务不因每一步重读全部日志而越来越慢；用户能有界读取、导出、回放，并把正确声明损失的数据交给训练/eval 消费者。

G5 已冻结 Trajectory、默认 journal writer、qita 默认 reader 和历史 compatibility。**不重新设计另一套 canonical schema，不重做已完成默认切换。** 内部 wire 标识保留历史 spelling；性能改造不能偷偷破坏已写数据。

历史审计事实（非当前测量）：append/query 调用 `_load()` 读全部 frames，append 重建 index，完整读取物化全轨迹。10,003 records 约 10.86 MB journal，带 tracemalloc 的读取约 5.57–5.76 秒、Python 分配峰值约 196 MB。这是特定来源测量，不是 v5 性能门槛或总进程 RSS。

master CI 稳定化已减少重复 journal 解析，R1 基线包含该修复。当前每次仍逐字节 hash 历史 journal，以检测同尺寸、恢复 mtime 的原地修改。必须重测读字节/解析/index 成本，不能重复实施缓存修复，也不能把仅免解析等同于增量 I/O。

**完整性与性能的边界（2026-09-05 修订）：** 对可被外部原地修改的单文件，不能同时承诺每次发现任意历史字节变更与完全不读旧字节。R1 保持严格默认，不用 size/mtime/进程锁充当不可变性证明；优先完成索引增量维护与有界分页/导出。真正 suffix-only I/O 需要单独证明历史段不可变、验证策略与迁移合同，在该前提成立前保持未完成，不是降低安全标准后的“通过”。

已有两类合成 shape 的 gzip/zstd 比较和真实 installed consumers；原 239 MB campaign 仍为 selected source，许可/脱敏未完成。必须保留这种区别。

## 2. 必读与 Ownership

- [Trajectory contract](../architecture/trajectory-contract.md)、[原数据任务](../v4/05-trajectory-data-plane.md)、[G5 ledger](../internal/plans/s4_g5_convergence_execution.md)。
- `qitos/tracing/journal_store.py`、`store.py`、`readers.py`、`exporter.py`、`privacy.py`、`trajectory.py`。
- `qitos/qita/reader.py`、`_cli_app.py`、`qitos/kit/artifact/store.py`、`qitos/core/artifact.py`、`qitos/evaluate/`、`qitos/metric/`。
- `scripts/benchmark_trajectory_store.py`、`tests/tracing/`、`tests/qita/`、`tests/fixtures/trajectories/`、`tests/fixtures/s4/g5/`。

本组 owns store/reader/export/query/privacy 和 artifact 存储机制；不改 Session/checkpoint/WorkGraph 的执行权威。01/02/03/05 生产事实并消费引用；hook dispatch 由 03 改，config/default/CLI 接线按共同租约提交。

## 3. 子任务

### 04A — 增量 journal 与查询

1. 先以读字节数、反序列化记录数、fsync/index 更新次数和 allocation 建立同源基线，不仅跑 wall time。
2. 分开优化解析、索引、读字节三个成本。跨进程写、owner lock、generation、digest chain、duplicate append 与 uncertain fsync 语义不变。只有在额外批准并验证的不可变历史段合同下，其他 writer 推进才可只校验新增 suffix；当前严格单文件默认仍检查历史字节，异常 typed fail/recovery。
3. index 为 derived、可重建；不能把它改成另一持久化真相。首次 open/rebuild/full integrity scan 的 O(N) 成本单独报告；正常每次 append 不再重建全索引。
4. query 通过持久 index/cursor 查候选记录，不因 limit 很小仍物化全部日志。新增 bounded iteration/page consumer 保持稳定顺序、一致 read boundary 和明确 snapshot/cursor 失效语义。
5. 现有完整 `read_run/read_session` 如需物化必须继续写明成本；新增流式能力不能改变旧返回类型。qita live polling 和 exporter 切到合适的增量接口。
6. append 短写、fsync 失败、半帧、崩溃、index 丢失/损坏、两个 writer、只读 reader 都有回归；不自动把 corrupted current 数据降级为旧 trace。

R1 机制验收：warm 单条 append 不重复解码全部历史、不逐次重建全索引；page/iterator 不创建全轨迹，遍历与完整读取逐记录等价。严格历史字节扫描的 O(N) 成本单列，不宣称消除。后续 suffix-only I/O 只有在前述完整性前提独立合格后才能计入 04A 全部完成。使用 instrumentation 断言工作量，不依赖不稳定耗时阈值。

### 04B — Artifact 引用化与数据生命周期

1. 复用唯一 ArtifactRef/resolver/store，让大 tool output、重复 context 和可引用 payload 存一次；同 digest 重用，权限/namespace/媒体/长度/完整性独立检查。
2. 不因内容相同允许跨 tenant/Agent 越权。公共导出不携带 resolver 私有路径、secret 或未授权 artifact body。
3. 02 compaction、03 工具、05 workspace retention 都能解析同一引用；不能只保存无法取回的摘要。
4. 增加显式 retention/GC：Session snapshot、fork、WorkGraph 和导出 pin 仍引用的对象不可删除；mark/plan 与实际删除分开，dry-run 列出 logical IDs。跨进程写入/崩溃不得产生错误 live reference。
5. raw/private 与 redacted/public 不互相覆盖；at-rest encryption 或禁存 raw 的需求用存储能力/部署合同表达。hash 不代表加密或脱敏，不自行实现密码算法。

验收：重复内容只写一份主体，required artifact 缺失/损坏失败；shared reference 的删除规则有两进程测试；默认不自动大范围 GC，不扫描或删除用户工作目录。

### 04C — 主流训练格式和 eval 消费

当前 CanonicalTrajectoryExporter/EventSummaryExporter 保留。逐项新增下面的 exporter，而非创建外部格式作为 canonical schema：

| 目标 | 必须明确的边界 |
|---|---|
| OpenAI Chat messages | assistant tools/results ID、顺序、多模态、reasoning 不能表达时的损失 |
| OpenAI Responses items | heterogeneous items、continuation reference、replay 与 provider-private 的边界 |
| ms-swift agent | 固定兼容版本/配置、role/tool convention、训练 loader 实际可消费 |
| Hermes/ShareGPT convention | 固定具体 convention，不能声称所有 ShareGPT 方言兼容 |

1. 实现前读取目标官方文档/实际 loader，并登记 exact version/ref；不得按名称猜格式。外部依赖保持 optional。
2. exporter 输出 format identity、source provenance、字段级 loss、privacy view 和不可恢复信息；用户未授权的损失 typed reject。
3. canonical raw roundtrip 必须精确；public roundtrip 只保证所选 projection，不能声称恢复已删私有数据。外部 lossy 格式做可证明的 invariant re-import，不伪称 exact。
4. 对每种格式用独立 loader/validator 消费真实多轮、并行、失败、reasoning、多模态 fixture；unsupported 数据按严格模式拒绝。仅 JSON 可解析不算训练可用。
5. evaluator 用 store-independent view；HF 等发布 wrapper 只消费显式公开导出，不直接上传 raw journal。此任务不授权上传任何数据。

验收：四个目标分别有成功 fixture、不可表达输入、损失断言和独立消费证据；不通过删除复杂样例或静默拼字符串通过。

### 04D — 可重复长轨迹测量与 qita 闭环

1. 使用三个来源：固定 synthetic 10k/100k规模、真实生成的 installed Agent、经许可的原 campaign（或明确标注的替代真实长任务）。不得把合成扩增称为原 campaign 实测。
2. 同机同环境比较旧 G5、naive JSON、优化 journal、artifact references、gzip/zstd 候选；记录 bytes、read/write/query/replay/index、RSS 和 tracemalloc、token 与 artifact 去重。
3. 每组至少 5 次记录 median/p95 与所有结果，说明 warm/cold、cache、fsync、Python/平台。性能目标和退化容忍带在看优化结果前登记；无效对比不能产生 speedup 宣传。
4. 对 iterator/export 的有界缓存设计给出可计算 memory budget，在固定 record/page 大小下从 10k 到 100k 不随总历史线性增长。完整 materializing API 不套用这个承诺。
5. 根据测量选择是否/如何启用 compression；未证明收益不强制新 dependency。journal framing 变化要有旧 reader/迁移/rollback 测试，不能暗改冻结格式。
6. qita board/replay/export/live polling 全部消费 reader，移除 selector-directory workaround；按已有数据/路由/render seam 小步拆分，不新增另一份 fork/执行语义。
7. 两个无关消费者在安装环境中完成 record→read→query→export→eval；大 payload/license 未获授权只影响该来源/publication，不阻断无敏感数据的 store 实现。

## 4. 验证与完成

运行 `tests/tracing/`、`tests/qita/`、`tests/test_trajectory_exporter_conformance.py` 和 G5 durability/default-reader/schema-freeze 回归；新增建议 `tests/tracing/test_v5_incremental_io.py`、`tests/tracing/test_v5_training_exporters.py`。性能测试与快速 correctness 测试分开，不把平台噪声引入普通 CI。

- [ ] 04A append/query/iteration 达到增量机制验收，损坏/短写/恢复行为不退化。
- [ ] 04B 可解析且受权限保护的 artifact 去重/retention；GC 不删除活跃引用。
- [ ] 04C 四类独立训练消费者通过，loss/privacy/version 明确。
- [ ] 04D 同源可重复测量与 qita/installed consumer 通过；未获许可的数据不发布。
- [ ] 原 canonical/default/historical compatibility 均保留，无第二 truth、无假的 bounded-memory 或压缩收益。

实施记录：`docs/internal/plans/v5_trajectory_research_data.md`。提交顺序：instrumentation/regression → incremental I/O/index → artifact lifecycle → 各 exporter 独立提交 → qita → benchmark/双语使用说明。大型 private 轨迹留仓库外，只提交可发布 fixture 和有界摘要。

## R1 integration closure — 2026-09-06

D 的 incremental derived index、snapshot cursor、bounded iteration、原子 export、source integrity 和失败保护在融合源码保留，组合 journal 逐项 page/iterator/export/reimport 等价。没有重测性能：继续绑定 df9316415db7ec76f1e5d70a11ceabfd47744169 的原始报告（准确 SHA 以报告为准），不能将旧数字贴到融合 HEAD。full historical-byte hashing、writer O(N) retention、cold-open 成本、部分遍历更慢，以及 Python allocation 与 RSS 的区别均仍成立。

完整来源、修复和验证见[融合执行](../internal/plans/v5_r1_integration_execution.md)。本轮 live_not_run，R1 不等于 V5 全完成。
