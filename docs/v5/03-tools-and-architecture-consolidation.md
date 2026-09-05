# V5-03 — 一套工具入口、可信公共接口与旧架构收敛

状态：`in_progress`；R1-C 候选已交付，handoff 补充反例待融合修复。优先级：高。执行前先读 [共同合同](README.md)。
承接 v4 03D、08B/C/D、09E/F、10B–F；不是全仓库格式清理任务。

R1 仅执行 [Lane C 指令](../internal/plans/v5_r1_c_runtime_correctness.md)：当前 handoff ownership/terminal 竞态、Read/Edit 与 Observation。原 03B 的 func/SharedMemory 决策和 03C–E 仍开放，不能因本轮 C 合格就全部勾选完成。

独立复跑 45 项通过；额外探针显示同 Agent 的不同 work item 被共同关闭，以及明确队列
拒绝仍留下 admitted/unknown。按[融合计划](../internal/plans/v5_r1_integration_plan.md)精确修复，
不恢复旧 owner 的终态写入。Read/Edit 的 ToolResult 返回变化须保留迁移说明。

## 1. 用户结果

用户不再因为选择相近名称的工具/API 而得到两套行为；稳定接口的 retry/timeout、Observation、memory、MCP 和依赖承诺可相信。领域 benchmark 不反向拖住框架主线。无真实消费者的旧能力可以明确实验化/弃用，不要求全部生产化。

## 2. 源码与既知问题

- 必读 [原 ACI 计划](../v4/03-aci-toolset.md)、[收敛计划](../v4/10-consolidation-and-surface-reduction.md)、[架构债务](../architecture/architecture-debt.md)、[correctness handoffs](../../quality/correctness_handoffs.md)。
- 工具：`qitos/kit/toolset/coding.py`、`env_coding.py`、`qitos/kit/tool/internal/coding_impl.py`、`qitos/engine/action_executor.py`。
- 表面：`qitos/core/observation.py`、`shared_memory.py`、`qitos/func/`、`qitos/recipes/benchmarks/`、`qitos/benchmark/`。
- 生命周期/依赖：`qitos/engine/_trace_runtime.py`、`qitos/mcp/`、`qitos/kit/tool/cron/scheduler.py`、`qitos/kit/vectorstore/pgvector_store.py`、`setup.py`、`pyproject.toml`。

审计探针：旧 Read 重复 offset 得到空结果；旧 Edit 未传 replace_all；Observation 属性与 dict 可分叉；TaskFunction 配置重试仍只调用一次。另有普通 hook debug-only 吞错、Cron inert job、PgVector driver 不一致和 benchmark/recipes 反向依赖。

审计时 static baseline 为 356（334 active、22 vendored），其中 active correctness 30。它们是诊断条目，不等于 30 个已证实运行时 bug。先按当前源码重核，已经修复的项只 shrink，不重新制造旧错误。

## 3. Ownership 与禁改

本组 owns tool registry/validator/ActionExecutor、旧 coding adapters、Observation、func 决策、旧具体 SharedMemory、recipes/benchmark 迁移、普通 hook failure policy、MCP bridge/parity。只有取得共同租约后才能改 baseline、packaging、聚合 exports 和 shared docs。

01 owns provider；02 owns context/memory 召回及 compaction；04 owns Trajectory/qita；05 owns sandbox backend/publication 与 Session approval/control。MCP cancellation/approval 通过现有 ToolRuntime 与 05 协作，不另建 executor。不得接管正在进行的 master CI stabilization。

## 4. 子任务

### 03A — 工具行为修复与 preset 收敛

1. 为旧 Read double-slice、Edit replace_all、error/message 字段丢失建立实际 regression；验证负 offset、空文件、重复匹配、旧参数别名和部分结果，不仅 mock 方法存在。
2. 以现有 EnvCodingToolSet 机制作为安全文件/命令工具主线；复核 read/list/grep/write/edit/command/test/start/poll/terminate 的完整性、loss、ArtifactRef 和 effect 状态。
3. 冻结一份入口映射：`coding_tools`、FullCodingToolSet、CodingToolSet、现代名和历史别名分别怎样委托。兼容 adapter 只转换参数/结果，不能再实现自己的读写/进程逻辑。
4. 不把旧 host 调用悄悄改成 Docker，也不能使新入口退回 host。Host compatibility 必须显式 unsafe/迁移告警；缺少 Env 为 typed error，安全默认唯一。
5. 接入同一个 ReadBeforeWriteEnforcer/权限/final validation 机制；读取身份、SHA 并发冲突、replace_all、写后失效语义一致。不按工具字符串新增硬编码并发名单。
6. 补 glob/list/search 的 completeness、truncation、pagination 事实。rg 无匹配、命令失败和结果截断不能混为一类。todo/binary 工具只有具名消费者才扩充。

验收：公开 preset/alias 要么委托 canonical，要么有明确兼容/弃用状态；新老支持的输入产生等价结果。禁止通过只改工具名快照证明合并。

### 03B — Observation、functional API 与 SharedMemory

1. Observation 只保留一份 authoritative state；Mapping compatibility 是该状态的实时视图或明确 immutable projection，不再 construction-only 同步。测试字段写、mapping 写/只读拒绝、嵌套修改、序列化、旧 reducer 和 ToolResult conversion。
2. `qitos.func` 先收集真实消费者并作一个决定：完成且教学，或实验化/弃用。决定应在本子包第一笔提交确定，不能留下“待研究”继续广告功能。
3. 若完成：retry/timeout 真正执行、async await 正确、Engine 接入符合实际、owned executor 可幂等关闭，borrowed 不关闭；不自行建立 durable task scheduler。
4. 若弃用：明确 warning、替代的普通函数/AgentModule 路径和最早移除版本，经 maintainer 认可后实施；尚未移除的参数不得默默忽略，应真实执行或拒绝非默认值。不因 grep 未发现使用就删除公共模块。
5. SharedMemory 抽象留 core，具体存储/namespace 实现迁 kit，保留薄旧 import adapter。FileSharedMemory 要么用真正跨进程协调与原子持久化通过竞争/崩溃测试，要么明确限为 process-local/experimental 并拒绝广告的跨进程模式；不能用 threading.Lock 证明跨进程安全。

### 03C — 活跃 correctness 与 benchmark 依赖收敛

1. 给 active correctness 条目建立 current-source → test/reproducer → disposition；同源重复 flake8/mypy finding 可以共享测试，不每项造一份报告。
   属于 provider/context/Session 等其他组的修复由对应语义 owner 实施，本组只维护闭环清单，不借静态清理争夺其文件租约。
2. 首先修活跃 recipe 的 prepare/reduce override、未定义名称和实际运行错误；annotation-only 问题按事实分类，不夸大危害，也不改成 hygiene 躲避。
3. 逐 benchmark 将共享 contract、adapter、runner 移到已批准的 recipes/资源归属，消除 recipes→deprecated benchmark 的反向依赖及模块环；旧 imports 只保留 warning/delegation。
4. vendored 数据/代码保持 license/provenance/version；有实质体积或维护成本时移到独立资源包/外部工程。没有已批准资源发布目标时，先完成依赖解环和明确隔离，不伪称已剥离 wheel。
5. review `experiment`、HF/leaderboard、evaluate/metric 等外围入口：保留有价值合同，具体实现不进入 core；删除/搬迁由 consumer ledger 与 maintainer 决定，不强行合并所有 namespace。

验收：当前 stable 活跃 correctness 都有修复或已实施的正式退出稳定支持路径；只登记未来 owner 不算完成。已解环的依赖 allowlist 必须缩小，旧 import/CLI/数据内容兼容通过。

### 03D — Hooks、MCP 与可选集成的真实承诺

1. 普通 Engine hooks 补 required/best-effort 或等价显式策略；失败计数、阶段、bounded diagnostics、trace completeness 可观测，strict 行为有测试。避免用捕获 hook 内部 TypeError 的方式重复调用产生副作用。
2. 与 04 对接已有 EventSink/loss，不能因记录 hook 失败再次递归失败。不得默认把所有 observability 异常变成致命错误。
3. 运行固定版本官方 MCP SDK parity spike：initialize、tools/list 分页、tools/call、schema/errors、notifications、cancel、stdio/HTTP shutdown、partial-open、最小环境和权限。
4. 结果必须为 adopt/defer/reject 之一，附版本、差距、消费者、依赖代价和实际测试。adopt 则在现有 bridge 后迁移；defer/reject 则将支持子集/缺能力明确化并测试失败语义，不能把未做实验写成“已决定不需要”。
5. Cron/PgVector/local embedding/PDF/notebook 等逐项映射为 supported extra、experimental 或 retired。缺依赖在构造/使用的约定边界 actionable fail；Cron 不返回虚假的可运行 job，PgVector 的依赖、driver、SQL parameter style 和 cleanup 一致。

### 03E — 后续发行维护，单独实施

在功能/extra 行为稳定后迁移 PEP 621 单一元数据源，比较版本、entry points、extras、wheel 文件/许可证、sdist 和 base import。剩余 hygiene、无行为收益的命名/文件拆分按 owning package 渐进减少。

03E 不是首批功能闭环前提；未完成必须在发行账本保持 pending。不能让“all 安装成功”代替所有 retained 功能可用，也不为死代码加入重依赖。

## 5. 验证、交接与完成

必须覆盖：旧 alias/new Env parity；Observed mapping mutation；func retry/timeout/async/close；SharedMemory 两进程；recipe override 实际执行；benchmark 双向 import-order；hook 自身 TypeError/failed sink；MCP 生命周期；present/missing extras。

运行实际存在的 `tests/engine/`、`tests/core/`、`tests/mcp/`、`tests/test_shared_memory.py`、`tests/test_public_surface.py`、`tests/test_architecture_boundaries.py` 中对应测试；新增 regression 文件后记录确切 node IDs。共用门禁在 integration 精确 baseline 上复验。未改 package 不必每笔重装所有 extras，最终相关发行子包必须 fresh-install。

- [ ] 03A 已知 alias bugs 修复，一套安全 coding 主线与明确迁移表。
- [ ] 03B Observation 单状态；func 有已实施决定；SharedMemory 层次/一致性诚实。
- [ ] 03C 活跃 correctness 关闭或正式退出稳定支持；benchmark 依赖解环；未迁出的资源不虚报完成。
- [ ] 03D 普通 hooks 可观察；MCP spike 有实际决定；可选能力不再静默 inert。
- [ ] 修改的 allowance shrink-only；未增加 blanket ignore、隐藏 skip 或无消费者 helper。
- [ ] 03E 单独报告，不混入基础交付完成率。

实施记录：`docs/internal/plans/v5_consolidation.md`。提交按工具、Observation、func、SharedMemory、recipe/benchmark、hook/MCP/extra 分开；不要一笔同时移动文件和改变所有运行语义。公共删除、警告版本、重依赖需要 maintainer 决策；其余修复不等待清理全仓库才能交付。
