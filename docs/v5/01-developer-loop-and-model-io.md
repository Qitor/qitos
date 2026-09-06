# V5-01 — 真实 Agent 开发闭环与统一模型 I/O

状态：`in_progress`；R1-A 与 M1/M2 已融合并验收；新增 Python 3.10 cleanup 兼容性另由当前同步任务修复。优先级：最高。后续范围遵循 [共同合同](README.md)；当前状态统一见[本轮记录](../internal/plans/v5_r1_remote_sync.md)。
承接 v4 00 Gate A/B/C、02C–E、09B/C，以及 G5 之后的功能性 E2E。

历史反例和已执行修复见[实现审查](../internal/plans/v5_r1_integration_review.md)与[融合执行](../internal/plans/v5_r1_integration_execution.md)。12 adapter 离线测试与安装消费者是机制证据，不代替 01C/D 的真实 Agent 迁移、胶水减少及 live 对照。

## 1. 用户结果与范围

用户按公开教程、安装后的 wheel 和自己的 agent.yaml，能完成多轮工具 Agent；模型失败不是正常回答，stream 取消不是假停止。迁移已有仓库外 Agent 后，能量化少写的框架胶水，而不是仅展示一个新 toy example。

本组不负责选择用户策略、保证模型答对所有任务、改 sandbox 权限，或开发第二 execution loop。只修与实际调用链相关的 provider/API/配置问题；不同时重写所有模型 SDK。

## 2. 必读与源码起点

- [v4 模型目标](../v4/02-conversation-kernel.md)、[责任边界](../architecture/framework-responsibility-boundary.md)。
- [旧 E2E 场景清单](../internal/plans/post_g5_functional_e2e.md)：场景复用；基线/预算以本轮派发配置为准。
- `qitos/models/base.py`、`provider.py`、`codec.py`、`openai.py`、`_openai_responses.py`、`anthropic.py`、`gemini.py`、`litellm.py`、`local.py`。
- `qitos/engine/_model_runtime.py`、`async_engine.py`、`qitos/config/`、`qitos/config/scaffold.py`。
- `tests/models/`、`tests/test_docs_golden_paths.py`、`tests/test_tutorial_snippets.py`、`examples/tutorials/`。

历史审计（已由 R1 修复）：模拟 SDK 连接异常后，`qitos_stream_transport()` 返回带 `Error:` 文本、`finish_reason=stop` 的 ModelResponse，并向 delta 发送该文本。保留真正以 `Error:` 开头的正常模型回答，禁止通过文本前缀猜错误。

## 3. Ownership

独占 provider/codec/transport、model runtime request/stream dispatch、开发者安装/config/scaffold 问题。R1 持有 README 所列 config/CLI 接线租约；R2 明确转交给 05。

02 owns context/memory/compaction 语义；03 owns ToolResult/Observation/permission；04 owns Trajectory/store/export；05 owns Session/checkpoint/approval/control。不要在这些目录复制实现；新增 context 接线与 02 联合验证。

## 4. 子任务

### 01A — 错误与请求事实统一，先修确定性缺陷

1. 把当前所有公开模型入口列成表：`__call__`、call_raw、canonical request、stream/astream、Engine、AsyncEngine；标明 canonical、compatibility、unsupported，不仅检查类是否存在。
2. 对实际 transport/stream 中的异常建立 typed failure；保留阶段、request_sent、已发生 usage、重试次数和 redacted details。中途失败不能生成正常 final/done 结论。
3. canonical 与保留的 public adapter 共享失败归一化；确需保留旧文本行为时只能是显式、有迁移说明的边界，不能默认或混入 canonical。
4. auth/rate-limit/timeout/connection/decode/malformed/取消分类一致；网络已发送后失败不得退回 sent=false，未发请求不得扣真实 dispatch 次数。
5. 每个缺陷先落最小失败测试；无隐藏 SDK retry、自动 provider 切换或未经用户授权的 loss fallback。

验收：模拟 SDK 抛错不再返回正常 ModelResponse/delta；普通 `Error: ...` 模型文本仍成功；每次请求有且仅有准确的 admission/dispatch/outcome 记录。

### 01B — 多轮 tools、reasoning、stream 与异步消费

1. 在现有 codecs 上跑 Chat/Responses/Anthropic/Gemini、GLM/Qwen-compatible、LiteLLM/local 的实际支持子集；unsupported 明确，不虚构全能力 parity。
2. 两轮以上 native tool exchange 必须保留 call ID、实际完成顺序、批次闭合、reasoning/opaque continuation 和 multimodal 顺序。特定 provider 不可表达时报告具体 loss，不默默降级文本。
3. 覆盖 stream 在首 token 前、文本中、tool args 中、usage 后失败；partial response 不得被重复计费或当完整工具声明执行。
4. 覆盖 async iterator 提前 break、consumer cancellation、close/aclose、借用/自有 client、活跃 event loop 和 worker thread。超时后仍运行的 worker 必须保留 owner/receipt；不把 Future.cancel 当硬取消。
5. 收敛同语义 bridge，保持单一 Engine；原生 async 内核重写不是验收条件。AsyncEngine 包装 sync Engine 不是缺陷，但不能丢取消、终态或资源事实。

验收：官方支持的每条路径有真实 adapter+mock transport 测试；第三方 structural adapter 用相同 conformance；不以 fake adapter 测试代替内置 provider 的异常路径。

### 01C — 安装后真实功能路径

在仓库外从 wheel 构建 Agent，不使用 tests helpers、私有 Engine 字段或 source PYTHONPATH。修复发现的 scaffold credentials root、CLI selector-directory workaround 等 DX 缺口；用 public regression 固定结果。

| 场景 | 独立验收，不只看 final text |
|---|---|
| 初始化与配置 | qit new、安装、真实 provider 请求、Session ID 与 journal 可重新读取 |
| 多轮工具 | 工具结果实际为正确值，第二轮消费它；codec loss 原因可判定 |
| 串行/并行 | call/result 对齐、完成顺序正确、无重复 terminal/effect |
| pause/exit/restore/steer | fresh process 重开，已完成工具不重做，steering 一次消费 |
| fork | parent head/digest 不变，child 身份与输出独立 |
| delegate/spawn/fan-out/join/handoff | 真实 child checkpoints、join receipts、旧 owner 被 fencing |
| sandbox/artifact | Env 内执行、artifact 可解析、source 不隐式修改、cleanup 已确认 |
| qita/export | 新进程读取同一轨迹，身份、损失和可见结果一致 |

R1 可先完成前 3 行；后 5 行先使用 G5 已支持边界，02/04/05 增强后回归。审批、联网等新场景由 owner 提交，不擅自绕过限制。

每行结果分成框架通过/失败、provider/model 观察、功能任务是否完成。真实功能未完成可报告外部原因，但不能把 typed failure 当成功闭环。框架修复无需等待所有模型都答对。

### 01D — 原 Agent 迁移收益与非劣对照

1. 经 maintainer 指定一个真实仓库外 Agent，保存 old/new 源码 commit、配置与 fixtures；无授权源码不得复制到 QitOS。
2. 冻结同一 prompts、模型/profile、任务集合、预算、环境和随机参数；本轮只迁移框架胶水。策略变化要拆为另一实验，不混入非劣比较。
3. 分类统计 removed/added/remaining glue LOC：provider/messages、parallel bookkeeping、validation/recovery、context/compaction、artifacts/trajectory。排除 prompt、配置、生成代码、改名搬文件；公布计数脚本和逐模块差异。
4. 运行至少一个无关应用，证明同一机制不是为第一个应用定制。领域 E2E 放在 zoo/外部工程，主仓库只保留通用 regression 和脱敏摘要。
5. 在实验前登记样本选择、质量指标、非劣容忍带、成本/延迟指标和预算。模型随机性或样本不足时只给观察，不声称统计非劣。

验收：有可复核的迁移差异、确实消除的至少一种胶水机制，以及事先定义的行为比较。没有减少就如实报告设计未达到目标；不得用框架新增 LOC 或 88 行演示替代该结论。

## 5. Live 配置、预算与秘密

- 必须由当轮提供的 agent.yaml/profile 和显式 CredentialRef resolver 启动；credentials 在仓库外受限文件，绝不读聊天记录、扫描环境凭据、复制私有 endpoint/key 到 docs/fixtures/日志。
- 单次输出默认建议 `max_tokens: 10240`，不是框架硬上限；更高/更低预算由用户 profile 决定，不偷偷恢复 2048/4096 限制。
- starter 场景建议最多 8 requests、80,000 measured tokens、16 tool calls、2 并发、10 分钟；复杂场景需要在启动配置里明确另定。模型请求包含 children、重试、compactor 调用。
- 全轮 aggregate request/token/time/cost ceiling 必须另行明确；不能将单场景额度隐式乘以全部 profiles。无 aggregate 授权只执行离线部分，记录所缺配置，不假定零成本。
- 默认一次只选一个已授权 profile；不自动轮换三个模型。usage 缺失报告 unknown，使用保守预留防止越预算，不报零用量。
- 外部配置缺失不阻断 01A/B 的修复交付；01C/D live 维度保持未资格化。不得无限重试“凑成功”。

## 6. 验证与交接

先跑 `tests/models/`、`tests/engine/` 中相关 provider/stream/cancel 测试，以及 docs golden paths；再执行共同门禁。新增建议测试：`tests/models/test_v5_stream_failure_semantics.py`、`tests/engine/test_v5_stream_lifecycle.py`，创建后必须实际执行，不能把计划文件路径当测试成绩。

交接：02 获得统一 request/failure/usage seam；03/05 获得取消与 worker 状态；04 获得有界 provider event、loss、usage；integration 获得 installed consumer 和真实迁移报告。

建议提交顺序：错误回归与修复 → stream/async ownership → 配置/scaffold DX → 离线消费者 → 有界 live/迁移证据及双语教程。不得更改 model、prompt、loss policy 后继续把前后两次当同一次实验。

## 7. V5 整体完成清单（R1 子集完成不等于下列整项完成）

- [ ] 01A 内置入口不再将基础设施错误冒充模型内容。
- [ ] 01B 支持的多轮/stream/async 路径有同等合同和资源清理。
- [ ] 01C 八类流程逐项给出框架结果与真实功能结果，至少选定 profile 的多轮工具路径真实完成。
- [ ] 01D 同一 Agent 前后胶水差异和行为对照已执行；未建立非劣证据不得宣称非劣。
- [ ] installed wheel/public API、双语教程、兼容迁移与共同门禁通过。
- [ ] 无新 Engine、未读私有凭据、未隐式扩大 live 预算或改变安全策略。

## R1 integration closure — 2026-09-06

M1/M2 已修复：Chat reasoning 分段独立保留，声明支持时恢复 provider 表达，否则显式处理 loss；owned cleanup 不覆盖 typed 主失败，保留 sent/usage/partial。组合消费者先用五轮 streaming，再在干净进程恢复后用内置非流式 adapter 完成；十次请求和九轮工具不代表模型智能已获验证。

完整来源、修复和验证见[融合执行](../internal/plans/v5_r1_integration_execution.md)。本轮 live_not_run，R1 不等于 V5 全完成。
