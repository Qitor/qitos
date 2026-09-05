# V5-05 — 可恢复交互、审批与实际工程沙箱

状态：`planned`。优先级：R2 主线；05D 为显式可选扩展。执行前先读 [共同合同](README.md)。
承接 v4 12 的交互恢复余项、14 的工程工作区/更广 backend 目标，以及 09 的资源/取消边界。

2026-09-05：新教程暴露的既有 handoff callback/restore ownership 竞态优先交由 R1 Lane C 修复。它是现有能力的 correctness 修复，不代表本组审批、control channel 或更强 sandbox 已启动。

## 1. 用户结果

用户可开发有人工审批、运行中输入、进程重启和安全文件产出的 Agent。前端、终端或服务通过同一 Session 机制控制运行；产品层决定 UI、认证部署与交互策略，框架不内置托管控制平台。

保留已完成的同步 Session/checkpoint/head、fork/ownership、partial batches、WorkGraph 和 Docker attestation。不会重新发明 Session façade、SessionStore、WorkScheduler 或 ToolResult。

## 2. 当前能力与未完成边界

- CLI inspect/restore/fork 可用；live pause/steer 返回 typed unsupported。
- unresolved approval 不能完整持久恢复；steering 不构成工具授权。
- durable Session 目前要求 SYNC；AsyncEngine 包装 sync Engine 不自动等于可恢复异步控制。
- Docker 有 private staging、network none、资源约束、generation 与 cleanup；workspace 恢复是 artifact 冷恢复，不是进程/内存快照。
- retained workspace 内容约 4 MiB、条目 4096；publication 限顶层普通文件。
- network allowlist、原生 sandbox pause/snapshot/fork、OS sandbox、gVisor/microVM/managed backend 没有完整资格证明。

这些限制有些是刻意安全边界，有些是用户功能缺口；必须经过设计/测试扩展，不能简单删掉限制。

## 3. 必读、Ownership 与开工前置

- [Session 目标](../v4/12-session-runtime-and-persistence.md)、[WorkGraph](../v4/13-durable-multi-agent-work-graph.md)、[sandbox 目标](../v4/14-sandboxed-agent-execution.md)。
- `qitos/core/session.py`、`qitos/engine/session_runtime.py`、`runtime.py`、`work_runtime.py`、`qitos/checkpoint/`。
- `qitos/kit/env/sandbox.py`、`_session_sandbox.py`、`_workspace_artifact.py`、`_publication.py`、`docker_env.py`。
- `qitos/config/builder.py`、`loader.py`、`qitos/cli.py`、`tests/checkpoint/`、`tests/test_g5_publication.py`、`tests/test_g5_session_public.py`。

先读取 master CI stabilization 已提交结果，不竞争 `_publication.py` 的 Python/platform 修复。若未提交，准备独立 tests/design，不接管工作树。

本组 owns Session/checkpoint/work ownership、sandbox/control；R2 从 01 接收 config/CLI 租约。01 owns transport/stream，02 owns context/memory，03 owns permission/validator/executor，04 owns artifact store/trajectory。qita 永远通过 reader 读数据；实际 mutation 发给 runtime，不能由 qita 改数据库或复制 trace 伪造 fork。

## 4. 子任务

### 05A — 持久审批与安全恢复

1. 在现有 Session、permission 与 snapshot 合同内定义 pending approval：operation/call/attempt、精确参数 digest、权限 scope、owner generation、状态与 expiry。第一笔提交冻结小型 ADR，不新增平行 permission manager。
2. request、decision、执行结果分开；queued/accepted 不等于 approved/executed。deny、expired、cancelled、duplicate、stale、changed-args 均明确。
3. 用户 approve 必须绑定 exact request/scope；参数、tool spec 或 owner 改变后重新判断。steering、模型文本、历史 approved receipt 不能自动授权新动作。
4. fresh process 从 paused/waiting-input snapshot 恢复后可查询和处理 pending request；resolver 缺失 fail closed，已 committed action 不重放。
5. 与 03 最终结构校验/permission pipeline 对齐，避免审批前合法但 interceptor 改写后越权。批准后的执行仍有 effect、timeout、unknown、cleanup 事实。
6. 提供完整 Python+CLI 例子：提出审批→退出→inspect→恢复→批准/拒绝→完成；不依赖私有字段，不在 snapshot 存 credential。

验收：两进程恢复、duplicate approval、stale owner、参数变化、expiry、deny、commit-then-process-loss 都不会越权或重复执行。

### 05B — 运行中控制与异步消费一致性

1. 用 existing Session 操作建立小而明确的控制协议；command ID、target Session、expected generation、提交/接受/应用/拒绝状态和 ack 可恢复。不是新 Agent loop。
2. 提供应用可注入的 control transport 及一个 task-local reference 实现；控制策略和产品 UI 在用户代码，基础包不依赖托管 daemon/数据库服务。
3. 最小支持 pause request、steering enqueue、cancel request、status。只有 lifecycle safe boundary 和已持久化 snapshot 才报告 paused；poll queued command 不冒充已生效。
4. CLI 只有在配置了可验证、授权的控制连接时才发送 mutation；没有连接仍 typed unsupported，不扫描同机 Session、不凭 Session ID 获得控制权。接收端必须鉴别 controller authority、operation identity、generation/replay 与消息大小。
5. 与 01 async/stream close 协作，关闭 consumer 后控制/worker/receipt 仍由显式 owner 管理。无法终止线程或远程请求时诚实保留 still-running/unknown。
6. Python sync API、async 调用适配、CLI control 必须作用于同一 durable Session。SYNC durability 继续是基础要求；ASYNC/EXIT Session 写入不是本子包偷偷附带的功能，仍需另行设计 accepted/persisted 策略才能支持。

验收：独立进程发送控制，执行进程在正确边界响应；断连/重复/过期/旧 generation 不产生假 ack 或重复 steering。支持边界以配置/能力可查询，不必要求所有应用运行后台服务。

### 05C — 更大工程工作区、嵌套产出与受限联网

1. 将 current workspace artifact 固定小上限演进为可配置、可查询的 quota/retention contract；04 提供分块/流式 artifact seam，本组不把整个大工程复制进 JSON snapshot。
2. 声明 staged/read-only/generated/private data 分别怎样处理，显式排除 Git credentials、controller 数据和 sibling inputs；支持实际工程的文件数/容量目标在开跑前登记。
3. nested publication 必须显式选择、权限批准并带 effect receipt；fd/目录锚定、symlink/hardlink/traversal/TOCTOU、父目录替换、同名冲突、目标源身份都要验证。不能只删“顶层文件”检查来获得功能。
4. 定义单文件原子提交与多文件发布之间的区别。若不支持整个目录事务，就记录逐文件结果/partial publication，不能承诺全目录原子；失败与恢复不能覆盖用户后续修改。
5. restore/fork 使用不同 attested sandbox 和最小权限；source head/文件不变，child 不继承其他 child 的 workspace/network/credential authority。
6. 为真实 Agent 的依赖安装/允许外部访问设计一条明确路径：仍默认 network none，优先 controller 预置依赖；需要 runtime egress 时以 opt-in proxy/backend policy 实现 allowlist、DNS变化、redirect、private/local deny 和资源限额。
7. 网络适配必须在选定受支持环境上实测；不能证明时保持该 profile unavailable，离线能力可独立交付。秘密只通过已声明 broker/reference，不能全量继承 controller 环境。

验收：选定真实项目规模的 read/edit/test/retain/restore/fork/publish 跑通；nested/sibling/secret/adversarial 测试和 cleanup 通过。新容量与平台结果记录在 capability matrix，不声称无限容量或所有 OS 等价。基础 offline 工作区交付与可选联网资格分栏。

### 05D — 更强 backend 的独立扩展，非基础阻断

在 maintainer 选择一个真实需求与执行环境后，从 OS-process sandbox、gVisor、microVM 或 managed 服务中选一个实现，先查官方当前能力/版本。不得同时承诺全部供应商。

第一步限定兼容性 spike 的时间/预算和结果：adopt/defer/reject。若 adopt，用同一 SandboxBackend/Env 和 conformance 实现，跑 policy、attestation、file/network/secret、resource、process-loss、snapshot capability、cleanup；fake 只能证明结构，不能证明隔离。

应用逻辑在 Docker 与该 backend 间切换不变，部署权限/依赖只在 composition 改。Firecracker/Kata 编排属于 operator service，不把生产 VM 集群管理嵌入 QitOS。缺平台则 typed qualification pending，不能牵连已有 Docker 功能。

## 5. 测试与平台结果

| 范围 | 最低验证 |
|---|---|
| approval/control | SQLite 两进程、authority、replay/expiry/generation、exact args、queue/ack/commit |
| work/effect | stale owner、child cancellation、duplicate terminal、commit-then-loss、unknown 不自动 retry |
| workspace | 超旧容量场景、大文件/大量文件、恢复缺块/损坏、fork 不变 source |
| publication | nested 路径、链接/父目录竞争、部分失败、用户并发修改、无隐式 cleanup publish |
| network（选择支持时） | deny 默认、允许目标、redirect 与 DNS 变化、private/local 拒绝、失效 proxy fail closed |
| platform | 当前支持 Python 的 Linux/macOS 实际目标；Windows 不支持则明确，不把 collection-only 当通过 |
| resources | 仅自有容器/进程、压力后 cleanup/absence、borrowed 不关闭、失败保持可对账 |

使用已有 Session/checkpoint/G5 publication/sandbox 测试，新增建议 `tests/checkpoint/test_v5_approval_restore.py`、`tests/engine/test_v5_session_control.py`、`tests/kit/test_v5_workspace_publication.py`。真实 Docker 串行运行或显式限并发，不清理其他任务容器，不用固定 sleep 排序。

required baseline regression 不能因平台波动删掉；新增未支持的平台可独立 pending。无可用环境时保留可复现命令、所需权限和未支持声明，不伪称 sandbox 安全通过。

## 6. 完成与交接

- [ ] 05A pending approval 可 fresh-process 恢复，准确授权一次，拒绝越权重放。
- [ ] 05B 可注入 control transport 和本地 reference 已执行；CLI/async 与 Session 同一语义，无连接仍安全拒绝。
- [ ] 05C 离线大工程/嵌套产出已通过实际平台与 adversarial 验收；联网能力单独标资格。
- [ ] sandbox/workspace/control events 被 04/qita 真实读取；01 installed 应用使用公共接口。
- [ ] EN/zh 教程明确支持范围，未把冷恢复写成进程快照、timeout 写成硬取消。
- [ ] 05D 仅在被选中时计入扩展验收，不阻断基础路线。

实施记录：`docs/internal/plans/v5_session_sandbox.md`。建议提交：approval regression/合同 → approval persistence → control protocol/reference → async/CLI 接线 → workspace retention → nested publication → 可选 egress/backend。共享 executor/config 修改由租约 owner 集成，不跨文件抢写。
