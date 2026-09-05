# 发给 Agent C：V5 R1 Handoff 与公共接口 Correctness

你负责 C 线实现。先读 [共同合同](v5_dispatch.md)、[V5-03](../../v5/03-tools-and-architecture-consolidation.md)、[V5-05](../../v5/05-interactive-session-and-sandbox.md) 的当前边界。**顺序固定：handoff 竞态 → Read/Edit → Observation**；不做 func/MCP/benchmark/SharedMemory 大清理。

## 1. 固定起点

```bash
git worktree add -b codex/v5-r1-c-runtime-correctness ../WhitzardOS-v5-r1-c 4dfb570fb7eef504c1e6d247c21a1984251b80e4
```

遵循共同预检；实施记录：`docs/internal/plans/v5_r1_c_execution.md`。

## 2. 租约与必读

- `docs/internal/plans/docs_self_contained_learning.md` 的 handoff 重现、`examples/tutorials/notes/handoff.py`、`multi_agent.py`。
- `qitos/engine/session_runtime.py`、`work_runtime.py`、`core/work_graph.py`、checkpoint Memory/SQLite CAS（只读，不放宽其语义）。
- `core/observation.py`、`kit/tool/internal/coding_impl.py`、`kit/toolset/coding.py`、`env_coding.py`、registry/permission/ActionExecutor 对应调用链。

允许修 existing Session/WorkRuntime 的 handoff terminal/ownership 顺序、Observation 与上述 alias。不得改 provider/context、Trajectory wire、sandbox isolation、permission authority、Session CAS fencing。不能新建 control daemon、scheduler、SessionStore、ObserverV2 或第二类 ToolResult。

## 3. Handoff：先重现 owner 竞态，再关闭状态窗口

已知来源不是 live 模型失败：paused SQLite Session → LocalWorkScheduler handoff callable 立即启动 destination 对**同一 Session** restore/run → destination 推进 owner → source terminal callback 以旧 owner 调 `_commit_work_graph` → CAS conflict，源 receipt 可能留在 dispatched。最新教程通过串行调用绕开，不能当成框架已经支持并发。

要求：

1. 写真实两进程 Event/barrier reproducer，强制 destination owner 已推进而 source terminal 尚未提交，不用 sleep 猜顺序。保存 baseline 的失败，不仅 monkeypatch persist 抛异常。
2. 在现有 handoff 协议中分清 admission、ownership commit、dispatch、destination completion、source acknowledgement。选择一个明确的 authoritative 持久化顺序与恢复 owner；旧 owner 绝不获得写新 head 的特权。
3. destination 正常启动不再因 source callback 卡死。source 返回的 receipt 必须准确描述 transfer/ack；不能把它标为 destination task success。终态由其真实 owner 写入，pending/unknown 有可恢复对账路径。
4. duplicate callback、late callback、相同 operation retry、不同 payload conflict、两次 destination restore、旧 source 再 run 都要保持 fencing。不能 catch CAS 后丢失 terminal、偷偷重试 committed action 或永远吞异常。
5. 对 loss before ownership、after ownership before dispatch、destination restore 后 source abrupt exit 三个窗口做恢复测试。完整动作结果与 effect facts 不丢；unknown 不自动重放。
6. 只使用同一 WorkItem handoff；不通过“改成 fork 新 child”规避同一 Session owner 问题。不以撤销公共能力或只改教程继续串行化代替修复。
7. 修复后更新 installed handoff 教程测试，使并发 destination 模式通过；原串行 consumer 保持兼容。高级例子仍可串行，不再把串行外部编排写成框架 correctness 必需条件。

如果实际 fixed baseline 无法重现，先用现有来源执行证明差异；保留调查结果而不凭空改 runtime。新扩大需求需 maintainer 决策，不能利用本任务放宽权限。

## 4. Read/Edit：实际内容与参数语义

1. 修旧 Read 对已分页 content 的第二次 slice；offset=2/limit=2 必须返回相应两行，行号正确。测试真实临时文件、空文件、EOF、负数/非法参数与截断事实。
2. 修 Edit `replace_all` 未传递：多个匹配且 false 要拒绝；true 实际替换全部；零匹配、旧参数别名、并发内容变化有确定结果。先核对底层 API，不只增加无效 keyword。
3. 保持同一 validation/permission/final validation/effect 路径；Env 新工具不退回 Host。历史 host alias 明确 compatibility，不新增权限，不把用户原调用悄悄变为 Docker。
4. 新旧入口支持交集有真实内容 parity；本轮不要求重写十个工具或删除 FullCodingToolSet。保留可观察迁移边界，不能只改名称快照。

## 5. Observation：一个真相与兼容映射

1. 当前 attribute mutation 与 dict lookup 分叉必须有 before/after test；同时覆盖 mapping write、update/pop/clear、nested state/metadata、action_results 和序列化。
2. 一个 authoritative typed state；旧 mapping 是同步视图或显式只读投影。优先保留已存在 reducer 读/写能力；如果拒绝某个旧 mutation，给明确异常与迁移说明，不静默成功。不保留两份 construction-only 快照。
3. canonical ToolResult、flattened legacy projection 边界不混淆；`to_dict` 仍 canonical，legacy reducer 得到已声明的兼容 shape。新机制不修改 ToolResult schema。
4. 外部输入/输出的嵌套 alias 行为有测试，不能用浅拷贝掩盖状态分叉。

## 6. 验证、文档与交付

新增 `tests/engine/test_v5_handoff_owner_race.py`、`tests/core/test_v5_observation_consistency.py`、legacy alias regression。必跑 `tests/engine/test_work_runtime.py`、`tests/engine/test_session_runtime.py`、`tests/engine/test_handoff_context.py`、`tests/checkpoint/`、`tests/core/`、`tests/test_coding_toolset_review.py`、`tests/test_permission_pipeline.py`，以及新 installed consumer 和共同门禁。

公共文档 owner：EN/zh `guides/multi-agent-patterns.mdx`、`reference/work-graph.mdx`、`concepts/tools-and-registry.mdx`、`reference/tools.mdx`；教学源 `notes/handoff.py`、`multi_agent.py`。更新“源清理与目标恢复必须外部串行”限制时必须绑定修复与真实测试。Observation 的兼容说明放实际 API 所在页，若与 A/B/D 页重叠只交具体片段给 integration，不覆盖整页。

建议三组行为独立提交：handoff reproducer/fix → Read/Edit → Observation → installed/tutorial/shrink/evidence。报告 source/destination 持久状态和 effect 次数，不只测试数量。func inert retry 虽已复现，仍由下一子包处理；不得在本轮报告为已解决。

达到 R1-C 完成必须三个范围均通过且不放松 ownership/sandbox；遵循共同 12 项报告。无 push、无 deploy、无其他 worktree 清理。

## 7. 加强后的 ownership 与兼容合同

### Handoff 持久事实顺序

1. 准备 transfer 时，源拥有 Session head 写权；目标不可根据仅存在的临时 descriptor 提前执行。
2. 调用可能立即运行 destination 的 scheduler 前，必须持久化足够的 transfer/admission/operation 事实，使目标不依赖源未来再写一次才具备恢复能力。不要把这一 checkpoint 写成目标业务已完成。
3. destination 必须通过既有 restore/CAS 取得 Session owner，之后只有当前 owner 可以推进 head；源所有未来 callback 不得用旧 facade 持久化整个 graph。
4. handoff operation 的 transfer/ack 与 destination 业务终态分开。前者可以由已提交的 ownership/目标 head 验证，后者由目标真实执行写入；不能用 scheduler callable 返回 None 证明任务完成。
5. 原 owner 的迟到通知不能覆盖目标新状态，也不能仅 swallow exception 丢失未持久事实。可由当前 owner reconcile 已有持久事实；如果实际结果不可获知，持久标明 unknown，不编造成功。恢复不依赖已退出源进程的 callback/内存。
6. 不自动后台恢复或重跑 unknown effect。框架负责可恢复事实与明确操作结果；应用仍选择等待、重试策略和人工 reconciliation。

以下 test oracle 固定，不预设内部锁或队列实现：目标先完成 restore，再释放源 callback；无 uncaught stale-CAS callback、source wait 有界返回准确 transfer receipt、目标继续 run 并持久完成、旧源不能 run/write、重放相同 operation 不重复 execution。不能仅测“CAS 如期失败”就算修复。

### Crash/duplicate 矩阵

| 注入点 | 必须证明 |
|---|---|
| transfer commit 前源退出 | 没有已授权目标执行；已留 intent 能区分未提交 |
| 已提交 transfer、尚未实际 dispatch | 新进程能定位可恢复 operation，不虚报 destination completed |
| 目标 restore 后源 SIGKILL | 目标不依赖源 callback，可完成；旧 owner 不复活 |
| 目标完成后重复/迟到源 callback | 目标 head/结果不回滚，终态不重复 |
| 两目标竞争同一 expected generation | 至多一个获得那一代 ownership；合法后续显式 restore 不被误称重复竞争 |
| operation ID 相同、payload 不同 | typed conflict，零额外 dispatch |

用真实 SQLite + spawn-process Event/barrier，对核心强制交错独立执行 20 次。每次最多 30 秒（本地确定性基准，不是 runtime 全局 timeout），超时保留失败，不自动 rerun 重置计数；成功与失败分报。

### Observation 与 aliases 的明确预期

- `obs.task='after'` 后 `obs['task']` 和两种显式序列化均为 after；`obs['task']='mapped'` 反向更新 attribute。保留这些已公开读写入口，不通过全对象冻结规避。
- `step` mapping 对应 `step_id`；不同别名输入矛盾必须原子拒绝，不以最后一个值悄悄覆盖。
- `state`/`metadata` 的嵌套更新在两种访问方式一致；外部构造输入防御性复制。已返回的 `to_dict/to_legacy_dict` 是独立快照，改它们不修改 Observation。
- `action_results` attribute 和 `to_dict` 维持 canonical ToolResult；legacy projection 可显式生成兼容 dict。映射写入须立即按现有 ToolResult adapter 校验，不能保留未验证的另一份权威。
- update/pop/clear 的可支持操作需明确定义；删除必需 identity 或非法类型整次拒绝且对象不变。不能把所有 dict 操作都声称支持却只实现 __getitem__。
- 四行文件 L1/L2/L3/L4，Read offset=2/limit=2 返回且仅返回 L3/L4，显示行号 3/4；offset=0/limit=2 为 L1/L2。
- 文件 `x x x`，Edit replace_all=false 不改文件并报告非唯一；true 写出 `y y y`；不存在的 old_text 不修改文件。零/多匹配、权限拒绝与 SHA 冲突都验证实际内容，不只测试 kwargs。

公共模块移除、改变 ToolResult wire、弱化安全策略、新 store/schema 都超出本轮。必要的内部函数/字段可调整；先有消费者兼容测试，不批量重写整个 Session runtime。
