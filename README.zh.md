# QitOS

![QitOS Logo](assets/logo.png)

[![Python](https://img.shields.io/badge/python-3.9%2B-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](https://github.com/Qitor/qitos)
[![Docs](https://img.shields.io/badge/docs-online-0A66C2)](https://qitor.github.io/qitos/)
[![Repo](https://img.shields.io/badge/github-Qitor%2Fqitos-black)](https://github.com/Qitor/qitos)

**QitOS 是一个研究优先的智能体框架，且只保留一条内核主线：**
`AgentModule + Engine`。

它面向两类核心用户：
- 研究者：快速试验、复现、对比新 agent 设计；
- 高阶开发者：精细控制 agent scaffolding，充分发挥模型能力。
- 基准评测用户：可直接接入 benchmark（GAIA/Tau-Bench/CyBench 已适配）。

- English README: [README.md](README.md)
- 文档站点: [https://qitor.github.io/qitos/](https://qitor.github.io/qitos/)
- 仓库地址: [https://github.com/Qitor/qitos](https://github.com/Qitor/qitos)

## 为什么是 QitOS

1. **执行主线唯一且清晰**
- 生命周期固定为：`prepare -> decide -> act -> reduce -> check_stop`
- 不存在 Runtime/Engine 双线并存
- 不引入与 `AgentModule` 冲突的隐式策略层

2. **模块化但不碎片化**
- `qitos.core`：核心契约
- `qitos.engine`：运行时内核
- `qitos.kit`：可复用具体实现
- `qitos.benchmark`：外部 benchmark 到 `Task` 的标准转换

3. **研究迭代速度优先**
- 可快速实现 ReAct、PlanAct、ToT、Reflexion、SWE-style 等范式
- benchmark 统一接入 `Task`，便于横向比较与复现实验

4. **可观测性是第一公民**
- 标准化 trace
- 全生命周期 hooks
- `qita` 支持 board/view/replay/export

5. **评测原生的 benchmark 工作流**
- `qitos.benchmark` 已适配 GAIA、Tau-Bench 与 CyBench
- `qitos.evaluate` 用于单轨迹任务完成判定
- `qitos.metric` 用于多任务聚合评测（成功率、pass@k 等）

## 架构速览

```text
Task -> Engine.run(...)
      -> prepare -> decide -> act -> reduce -> check_stop -> ...
      -> hooks + trace + qita replay
```

## 安装

```bash
pip install -e .
```

按需安装额外依赖：

```bash
pip install -e ".[models,yaml]"
```

## 快速开始

### 1) 运行最小内核链路

```bash
python examples/quickstart/minimal_agent.py
```

### 2) 运行一个 LLM 驱动的 ReAct 示例

```bash
export OPENAI_BASE_URL="https://api.siliconflow.cn/v1/"
export OPENAI_API_KEY="<your_api_key>"

python examples/patterns/react.py --workspace ./playground
```

### 3) 使用 qita 查看运行轨迹

```bash
qita board --logdir runs
```

## 产品界面截图

### QitOS CLI 渲染效果

![QitOS CLI](assets/qitos_cli_snapshot.png)

### qita board

![qita board](assets/qita_board_snapshot.png)

### qita 轨迹视图

![qita trajectory view](assets/qita_traj_snapshot.png)

### 4) 运行 GAIA Benchmark（QitOS 适配版）

单题运行：

```bash
python examples/real/open_deep_research_gaia_agent.py \
  --workspace ./qitos_gaia_workspace \
  --gaia-download-snapshot \
  --gaia-split validation \
  --gaia-index 0
```

整集合运行（支持断点续跑）：

```bash
python examples/real/open_deep_research_gaia_agent.py \
  --workspace ./qitos_gaia_workspace \
  --gaia-download-snapshot \
  --gaia-split validation \
  --run-all --concurrency 2 --resume
```

### 5) 运行 Tau-Bench 评测（单题 / 全量）

单题：

```bash
python examples/real/tau_bench_eval.py \
  --workspace ./qitos_tau_workspace \
  --tau-env retail --tau-split test \
  --task-index 0
```

全量：

```bash
python examples/real/tau_bench_eval.py \
  --workspace ./qitos_tau_workspace \
  --tau-env retail --tau-split test \
  --run-all --num-trials 1 --concurrency 4 --resume
```

### 6) 运行 CyBench 评测（单题 / 全量）

单题（Guided 模式）：

```bash
python examples/real/cybench_eval.py \
  --workspace ./qitos_cybench_workspace \
  --cybench-root ./references/cybench \
  --task-index 0
```

全量：

```bash
python examples/real/cybench_eval.py \
  --workspace ./qitos_cybench_workspace \
  --cybench-root ./references/cybench \
  --run-all --max-workers 2 --resume
```

## 最小可改的 Agent 编写示例

```python
from dataclasses import dataclass
from qitos import AgentModule, StateSchema, Decision, Action, Engine, ToolRegistry, tool

@dataclass
class MyState(StateSchema):
    pass

class MyAgent(AgentModule[MyState, dict, Action]):
    def __init__(self):
        reg = ToolRegistry()

        @tool(name="add")
        def add(a: int, b: int) -> int:
            return a + b

        reg.register(add)
        super().__init__(tool_registry=reg)

    def init_state(self, task: str, **kwargs):
        return MyState(task=task, max_steps=3)

    def decide(self, state, observation):
        if state.current_step == 0:
            return Decision.act(actions=[Action(name="add", args={"a": 19, "b": 23})])
        return Decision.final("done")

    def reduce(self, state, observation, decision):
        return state

result = Engine(agent=MyAgent()).run("compute 19+23")
print(result.state.final_result)
```

## 实战示例

- 模式示例：
  - `python examples/patterns/react.py --workspace /tmp/qitos_react`
  - `python examples/patterns/planact.py --workspace /tmp/qitos_planact`
  - `python examples/patterns/tot.py --workspace /tmp/qitos_tot`
  - `python examples/patterns/reflexion.py --workspace /tmp/qitos_reflexion`
- 真实场景示例：
  - `python examples/real/coding_agent.py --workspace /tmp/qitos_coding`
  - `python examples/real/swe_agent.py --workspace /tmp/qitos_swe`
  - `python examples/real/computer_use_agent.py --workspace /tmp/qitos_computer`
  - `python examples/real/epub_reader_agent.py --workspace /tmp/qitos_epub`
  - `python examples/real/open_deep_research_gaia_agent.py --workspace /tmp/qitos_gaia --gaia-from-local`

## Benchmark 接入方式

QitOS 的 benchmark 接入遵循统一路径：

- 外部数据集样本
- `qitos.benchmark.*Adapter`
- 标准化 `Task`
- 标准 `Engine` 循环执行

当前 GAIA 接入：
- 适配器：`qitos/benchmark/gaia/adapter.py`
- 运行示例：`examples/real/open_deep_research_gaia_agent.py`

当前 Tau-Bench 接入：
- 适配器：`qitos/benchmark/tau_bench/adapter.py`
- 内置运行时：`qitos/benchmark/tau_bench/runtime.py` + `qitos/benchmark/tau_bench/port/*`
- 运行示例：`examples/real/tau_bench_eval.py`

当前 CyBench 接入：
- 适配器：`qitos/benchmark/cybench/adapter.py`
- 运行时 + 评分：`qitos/benchmark/cybench/runtime.py`
- 运行示例：`examples/real/cybench_eval.py`

## Evaluate 与 Metric 架构

QitOS 将“任务完成判定”和“评测聚合指标”拆开：

- `qitos.evaluate`：
  - 面向单个 task + trajectory 的完成判定
  - 产出结构化 `EvaluationResult`（原因、证据、分数）
- `qitos.metric`：
  - 面向多任务运行结果的聚合指标
  - 产出成功率、平均 reward、pass@k 等报告

预实现：
- `qitos.kit.evaluate`：
  - `RuleBasedEvaluator`、`DSLEvaluator`、`ModelBasedEvaluator`
- `qitos.kit.metric`：
  - `SuccessRateMetric`、`AverageRewardMetric`、`PassAtKMetric`、`MeanStepsMetric`、`StopReasonDistributionMetric`

## 预定义组件目录（Torch 风格）

QitOS 在 `qitos.kit` 内提供可复用组件，强调“组合优先、少造轮子”。

### `qitos.kit.tool`（预定义工具包）

- 编辑器工具包：
  - `EditorToolSet`（`view`、`create`、`str_replace`、`insert`、`search`、`list_tree`、`replace_lines`）
- EPUB 工具包：
  - `EpubToolSet`（`list_chapters`、`read_chapter`、`search`）
- 文件工具：
  - `WriteFile`、`ReadFile`、`ListFiles`
- 命令执行工具：
  - `RunCommand`
- HTTP/Web 工具：
  - `HTTPRequest`、`HTTPGet`、`HTTPPost`、`HTMLExtractText`
- 文本浏览器工具（GAIA/OpenDeepResearch 常用）：
  - `WebSearch`、`VisitURL`、`PageDown`、`PageUp`、`FindInPage`、`FindNext`、`ArchiveSearch`
- 思维工具集：
  - `ThinkingToolSet`、`ThoughtData`
- 工具库：
  - `InMemoryToolLibrary`、`ToolArtifact`、`BaseToolLibrary`
- 注册表快捷构造：
  - `math_tools()`、`editor_tools(workspace_root)`

### `qitos.kit.planning`（预定义规划模块）

- LLM 编排模块：
  - `ToolAwareMessageBuilder`、`LLMDecisionBlock`
- 计划工具：
  - `PlanCursor`、`parse_numbered_plan`
- 搜索策略：
  - `GreedySearch`、`DynamicTreeSearch`
- 状态辅助函数：
  - `append_log`、`format_action`、`set_final`、`set_if_empty`

快速导入示例：

```python
from qitos.kit.tool import EditorToolSet, RunCommand, HTTPGet, ThinkingToolSet
from qitos.kit.planning import DynamicTreeSearch, PlanCursor, LLMDecisionBlock
```

## 核心目录映射

- 契约层：
  - `qitos/core/agent_module.py`
  - `qitos/core/task.py`
  - `qitos/core/env.py`
  - `qitos/core/memory.py`
  - `qitos/core/tool.py`
  - `qitos/core/tool_registry.py`
- 运行时：
  - `qitos/engine/engine.py`
  - `qitos/engine/action_executor.py`
  - `qitos/engine/hooks.py`
- 可复用实现：
  - `qitos/kit/*`
- benchmark 适配：
  - `qitos/benchmark/*`

## 文档导航

- 文档首页: [https://qitor.github.io/qitos/](https://qitor.github.io/qitos/)
- 内核架构：
  - [English](https://qitor.github.io/qitos/research/kernel/)
  - [中文](https://qitor.github.io/qitos/zh/research/kernel/)
- 30 分钟实验课：
  - [English](https://qitor.github.io/qitos/research/labs/)
  - [中文](https://qitor.github.io/qitos/zh/research/labs/)
- API 参考（构建时自动从 `qitos/*` 生成）：
  - [English](https://qitor.github.io/qitos/reference/api_generated/)
  - [中文](https://qitor.github.io/qitos/zh/reference/api_generated/)

## 本地文档开发

```bash
pip install -r docs/requirements.txt
mkdocs serve
```

文档生成说明：
- API 页面由 `docs/hooks.py` 自动生成到：
  - `docs/reference/api_generated/`
  - `docs/zh/reference/api_generated/`

## 贡献方向

QitOS 的长期目标是：
- 成为面向研究者与高阶开发者的世界级开源 agentic Python 框架。

新增抽象前，请先确认它是否真正提升了：
- 组合性、
- 生命周期清晰度、
- 可复现性、
- 开发者体验。

- 文档构建会执行 `docs/hooks.py`，自动生成 API 参考到：
  - `docs/reference/api_generated/`
  - `docs/zh/reference/api_generated/`

## GitHub Pages 部署

工作流文件：

- `.github/workflows/docs.yml`

该工作流会在 `main` 分支更新时自动构建并发布到 GitHub Pages，目标地址：

- [https://qitor.github.io/qitos/](https://qitor.github.io/qitos/)
