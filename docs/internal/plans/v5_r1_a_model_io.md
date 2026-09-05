# 发给 Agent A：V5 R1 Model I/O 与真实开发路径

你负责 A 线实现，不是继续设计文档。先完整读取主工作树里的 [共同合同](v5_dispatch.md)、[V5-01](../../v5/01-developer-loop-and-model-io.md) 和本文件。范围以本文件为准：01A/B 的 stream 子包 + 01C 前三行离线安装消费，不做整个 01D 迁移实验。

## 1. 固定起点

按共同预检确认后，在主仓库执行：

```bash
git worktree add -b codex/v5-r1-a-model-io ../WhitzardOS-v5-r1-a 4dfb570fb7eef504c1e6d247c21a1984251b80e4
```

进入该 worktree，记录 clean/HEAD/merge-base。自己的实施记录创建为 `docs/internal/plans/v5_r1_a_execution.md`。不改变主工作树的 v5 草稿。

## 2. 具体源码与可写范围

必读：`qitos/models/base.py`、`openai.py`、`_openai_responses.py`、`anthropic.py`、`gemini.py`、`litellm.py`、`local.py`、`provider.py`、`codec.py`；`qitos/engine/_model_runtime.py`、`async_engine.py`、`stream/`；provider conformance 与 G5 retry/budget tests。

允许编辑这些 model/stream 模块、其测试，以及确有消费者需求的 config/CLI/scaffold 接线。不得改 ExchangeLog/RequestView、Session/WorkGraph/checkpoint、ToolResult/Observation、sandbox 或 Trajectory schema。缺少外部 schema 字段的需求写交接，不在 A 复制新合同。

## 3. 先固定失败，再修主路径

1. 在 `tests/models/test_v5_stream_failure_semantics.py` 固定已复现问题：让真实 OpenAIModel 使用的 SDK client 构造/请求抛 synthetic ConnectionError。当前 `qitos_stream_transport` 返回正常 ModelResponse、finish_reason=stop，还向 delta 发出 Error 文本；修复后必须 typed failure，无正常 final。
2. 同时测试真正由模型返回、以 `Error:` 开头的正常文本仍成功。禁止文本前缀分类错误。
3. 表格列出所有内置 adapter 的 canonical request/stream 与保留 public stream 入口。搜索同类 catch-yield-error，将相同基础设施错误接入已有 ProviderFailure 归一化。保留 phase/request_sent/retry/usage/partial facts，错误详情脱敏。
4. 流在完整协议终态前 EOF、args 中断、多个 done、consumer early break、回调抛错、取消时，不执行半截工具、不生成伪 final、不重复计费。区分 token-length stop、正常 stop 与 transport failure，不把聚合器的 finish_reason 永远写为 stop。
5. 覆盖 usage-only chunk（choices 为空）、usage 晚于 finish、usage 缺失。已知数据保留，未知不是零；dispatch attempt、SDK retry 和框架 retry 有且只有一个准确计数 owner。
6. OpenAI-compatible stream 与非 stream 使用一致 options relocation；`chat_template_kwargs` 不被错误传成 SDK 顶层参数。不为 GLM/Qwen 名称在 Engine 增加分支。
7. 自有 client/response/iterator 在完成、异常、GeneratorExit/CancelledError 后清理一次；借用 client 不关闭。async active loop、early break 与 worker 未终止事实有测试；不把 task cancellation 当线程硬停。

不得新增第二 Model/Engine；不得默认切 provider、丢 reasoning 或强制 allow_loss。无法表达的能力继续 typed unsupported，不为得到成功放宽 codec。

## 4. 多轮与安装消费者

在仓库外安装本线 wheel，使用公开 config/composition/Session 路径和**真实内置 provider adapter + 可控 SDK transport**完成：

1. 模型声明两个只读工具，工具以不同顺序完成。
2. 下一次模型请求收到两个正确 call/result pairing，再声明第二批工具。
3. 最终回答确实使用第二批结果；记录 exchange、terminal 数、usage/dispatch 与 journal identity。
4. 另跑一次中途 stream failure，断言不会执行半截 arguments、伪造成功 Session 或写重复结果。

这是离线框架资格，不是 live 模型成功。新增例子放 `examples/v5/r1_a_model_io/`，测试不得 monkeypatch Engine/ExchangeLog/ToolRuntime 来跳过真实路径。

## 5. 验证、文档、提交

必跑现有 `tests/models/`、`tests/test_provider_adapter_conformance.py`、`tests/test_config_provider_transport.py`、`tests/engine/stream/`、`tests/engine/test_stream_transformer_async.py`、`tests/test_docs_golden_paths.py`，加新 regression 与 installed consumer，再执行共同最终门禁。

公共文档 owner：EN/zh `guides/third-party-extensions.mdx`、`reference/extensions.mdx` 的 provider/stream 部分；source-synchronized provider 教学文件。不要重写 B 的 memory 或 C 的 handoff 教程。新增 public symbol 要更新其 API binding，不扩 root exports。

建议提交：stream failure 回归/修复 → termination/usage/lifecycle → installed multi-round consumer → docs + shrink baseline + evidence。交接给 B 的只有 canonical request/usage 接入方式；D 消费现有 events。无 live 配置仍完成代码验收并报告 live_not_run。

完成条件：新旧公开支持路径不再错误文本化，终态/usage/cleanup 可信；安装后的两批工具消费者实际通过。不是“所有 provider 所有能力 parity”，也不声称原 Agent 迁移或 v5 全完成。共同合同的 12 项报告、无 push、保留 worktree 规则全部适用。

## 6. 加强后的固定实现合同

### 用户入口与 provider 矩阵

用户仍通过 `load_agent_config`、`build_agent_composition`、`composition.session(task).run()` 调用；本轮不增加必须由用户处理的 stream assembly、call ID 或 usage bookkeeping。不改现有构造默认，只证明显式 10240/更高合法预算不会被隐藏截断。

| 必须检查的 adapter | 本轮要求 |
|---|---|
| OpenAIModel + OpenAICompatibleModel，Chat 模式 | public stream + canonical aggregation 全失败/终态矩阵；两批工具 installed consumer |
| OpenAIModel，Responses 模式 | 实际 `_openai_responses` streaming transport 的成功、拒绝、中断和 cleanup；不猜 Chat 的终态 |
| AsyncOpenAIModel + AsyncOpenAICompatibleModel | 已支持模式的 astream、active loop、early close/cancel；不新增未支持 API mode |
| AnthropicModel | 内置 stream 的 native stop、工具部分输入、失败与清理 |
| AzureOpenAIModel | 继承路径的 endpoint/API mode/options 不丢失；至少正常与失败两项回归 |
| LiteLLMModel、GeminiModel、OllamaModel/OllamaGenerateModel、LMStudioModel、VLLMModel | 核验已有 declared 能力与实际 fallback；实际 public adapter 的正常/失败测试。非 native streaming 不广告逐 token；不要求新增 native backend |

测试替换 SDK/HTTP transport，不替换待测 provider、codec、Engine 或 assembler。支持路径不得靠改成 unsupported 逃过验收；原不支持路径可维持明确 unsupported。

### 终态判据

- client 构造/encode/admission 失败：本轮实际 provider dispatch=0，不生成回答；预算 reservation 必须释放。
- transport 已进入但没有可证明发送状态：保守记录 dispatch/可能发送，不臆断 request_sent=false；字段若表示“开始 dispatch”而非线上已发送，在报告中明确。
- 部分文本已展示后异常：允许已有 partial delta 留在诊断，但不能再发 normal success/end；error terminal 一次。
- tool arguments 中断、length 截断而工具未闭合：tool execution=0；不是接受解析出的 JSON 前缀。
- protocol complete 后 usage-only 尾帧：保留 provider finish reason，usage 最多记一次；不同 provider 的 terminal grammar 分别测试。
- 终态前 EOF：不生成 finish_reason=stop；一致重发的 final/usage 不重复，矛盾终态或终态后新 tool/content 为协议失败。
- consumer break 与 callback failure：资源 owner 可关闭/对账；异常不得被转成模型内容。原生 async 取消保留 asyncio cancellation 语义，不包装成正常返回。

### 固定端到端 fixture

三个 model requests：第一批 read-only 工具 `add(2,3)` 与 `multiply(2,3)`，用 Event 令 multiply 先完成；第二个请求必须同时看到 5 和 6 并声明 `add(5,6)`；第三个请求看到 11，返回 final 11。硬断言 request_count=3、tool_count=3、每 call 一项 terminal、两 batch closure、final=11、完整 completion order 与 declaration-order 派生视图均正确。第二批工具参数中途截断的对照场景必须不执行该工具、不记录成功 final。

Live 未授权不阻断该确定性矩阵。所有新事实分别报告，不把 scripted SDK 的 final=11 当作模型能力实测。
