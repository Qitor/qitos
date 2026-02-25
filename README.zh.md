# QitOS

![QitOS Logo](assets/logo.png)

[![Python](https://img.shields.io/badge/python-3.9%2B-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-qitor.github.io/qitos-0A66C2)](https://qitor.github.io/qitos/)
[![PyPI](https://img.shields.io/pypi/v/qitos.svg)](https://pypi.org/project/qitos/)
[![Repo](https://img.shields.io/badge/github-Qitor%2Fqitos-black)](https://github.com/Qitor/qitos)

QitOS 是一个**研究优先（research-first）**的智能体框架，围绕唯一内核构建：

> **AgentModule + Engine**

它面向研究者与高级开发者，帮助你：
- 快速设计和迭代新的 agent scaffolding，
- 精细控制运行时行为，
- 用统一任务抽象跑 benchmark，
- 基于完整轨迹做可复现分析。

- English README: [README.md](README.md)
- 文档站点: [https://qitor.github.io/qitos/](https://qitor.github.io/qitos/)

---

## 为什么是 QitOS

### 1）单一主线，架构无歧义
QitOS 固定生命周期：

`prepare -> decide -> act -> reduce -> check_stop`

不再有并行 runtime 架构，不再有“隐藏策略层”与 AgentModule 冲突。

### 2）Memory 与 History 严格分离
QitOS 明确区分：
- `memory`：轨迹工件（`task/state/decision/action/observation/next_state/...`）
- `history`：模型消息（`system/user/assistant/...`）

这让策略研究更干净，也避免上下文耦合错误。

### 3）模块化但不碎片化
- `qitos.core`：核心契约
- `qitos.engine`：执行内核
- `qitos.kit`：可复用实现
- `qitos.benchmark`：benchmark 到 `Task` 的标准化适配
- `qitos.evaluate` + `qitos.metric`：评测判定与聚合指标

### 4）可观测性内建
- 标准化 trace
- 全生命周期 hooks
- `qita` 支持 board / view / replay / export

### 5）Benchmark 原生
已接入：
- GAIA
- Tau-Bench
- CyBench

---

## 架构速览

```text
Task -> Engine.run(...)
     -> prepare -> decide -> act -> reduce -> check_stop -> ...
     -> hooks + trace + qita replay
```

---

## 安装

```bash
pip install qitos
```

开发模式：

```bash
pip install -e .
```

按需安装扩展：

```bash
pip install -e ".[models,yaml,benchmarks]"
```

---

## 快速开始

### 1）运行最小内核链路

```bash
python examples/quickstart/minimal_agent.py
```

### 2）运行 LLM 驱动的 ReAct 示例

```bash
export OPENAI_BASE_URL="https://api.siliconflow.cn/v1/"
export OPENAI_API_KEY="<your_api_key>"

python examples/patterns/react.py --workspace ./playground
```

### 3）用 qita 查看轨迹

```bash
qita board --logdir runs
```

---

## 最小 SWE Agent（需求到 PR）示例

```python
from dataclasses import dataclass, field
from typing import Any

from qitos import Action, AgentModule, Decision, Engine, EnvSpec, HistoryPolicy, StateSchema, Task, TaskBudget, ToolRegistry
from qitos.kit.env import HostEnv
from qitos.kit.history import WindowHistory
from qitos.kit.memory import MarkdownFileMemory
from qitos.kit.parser import ReActTextParser
from qitos.kit.tool.editor import EditorToolSet
from qitos.kit.tool.shell import RunCommand

SWE_REACT_SYSTEM_PROMPT = """
你是一名顶级软件工程智能体。

目标：
- 在仓库中实现新的需求，改动应正确、最小、可维护。
- 产出可直接用于 PR 的结果，并附带验证证据。

规则：
1. 严格使用 ReAct：Thought -> 一次 Action -> 观察 -> 继续。
2. 每步仅允许一次工具调用。
3. 修改前先阅读相关代码。
4. 优先小而可回滚的补丁。
5. 没有测试/命令证据，不得宣称完成。

输出格式：
Thought: <推理>
Action: <tool_name>(...)
Final Answer: <需求覆盖 + 修改文件 + 验证结果 + 剩余风险>
"""

@dataclass
class SWEState(StateSchema):
    scratchpad: list[str] = field(default_factory=list)
    target_file: str = "buggy_module.py"
    test_command: str = 'python -c "import buggy_module; assert buggy_module.add(20, 22) == 42"'


class MinimalSWEAgent(AgentModule[SWEState, dict[str, Any], Action]):
    def __init__(self, llm: Any, workspace_root: str):
        reg = ToolRegistry()
        reg.include(EditorToolSet(workspace_root=workspace_root))
        reg.register(RunCommand(cwd=workspace_root))
        super().__init__(
            tool_registry=reg,
            llm=llm,
            model_parser=ReActTextParser(),
            memory=MarkdownFileMemory(path=f"{workspace_root}/memory.md"),
            history=WindowHistory(window_size=24),
        )

    def init_state(self, task: str, **kwargs: Any) -> SWEState:
        return SWEState(task=task, max_steps=int(kwargs.get("max_steps", 12)))

    def build_system_prompt(self, state: SWEState) -> str | None:
        tool_schema = self.tool_registry.get_tool_descriptions() if self.tool_registry else ""
        return f"{SWE_REACT_SYSTEM_PROMPT}\n\n可用工具：\n{tool_schema}"

    def decide(self, state: SWEState, observation: dict[str, Any]):
        return None  # Engine 默认模型路径：prepare -> llm -> parser

    def prepare(self, state: SWEState) -> str:
        records = self.memory.retrieve(query={"max_items": 8}) if self.memory else []
        return (
            f"Task: {state.task}\n"
            f"Target file: {state.target_file}\n"
            f"Test command: {state.test_command}\n"
            f"Step: {state.current_step}/{state.max_steps}\n"
            f"Recent memory: {records[-3:]}"
        )

    def reduce(self, state: SWEState, observation: dict[str, Any], decision: Decision[Action]) -> SWEState:
        if decision.rationale:
            state.scratchpad.append(f"Thought: {decision.rationale}")
        if decision.actions:
            state.scratchpad.append(f"Action: {decision.actions[0]}")
        results = observation.get("action_results", [])
        if results:
            state.scratchpad.append(f"Observation: {results[0]}")
            if isinstance(results[0], dict) and int(results[0].get("returncode", 1)) == 0:
                state.final_result = "需求已实现，且验证命令通过。"
        state.scratchpad = state.scratchpad[-40:]
        return state


# llm = ...
# agent = MinimalSWEAgent(llm=llm, workspace_root="./playground")
# task = Task(
#     id="swe_minimal",
#     objective="实现新需求并让检查通过。",
#     env_spec=EnvSpec(type="host", config={"workspace_root": "./playground"}),
#     budget=TaskBudget(max_steps=12),
# )
# result = Engine(
#     agent=agent,
#     env=HostEnv(workspace_root="./playground"),
#     history_policy=HistoryPolicy(max_messages=20),
# ).run(task)
# print(result.state.final_result, result.state.stop_reason)
```

---

## 实战示例

模式示例：
- `python examples/patterns/react.py --workspace /tmp/qitos_react`
- `python examples/patterns/planact.py --workspace /tmp/qitos_planact`
- `python examples/patterns/tot.py --workspace /tmp/qitos_tot`
- `python examples/patterns/reflexion.py --workspace /tmp/qitos_reflexion`

真实场景：
- `python examples/real/coding_agent.py --workspace /tmp/qitos_coding`
- `python examples/real/swe_agent.py --workspace /tmp/qitos_swe`
- `python examples/real/computer_use_agent.py --workspace /tmp/qitos_computer`
- `python examples/real/epub_reader_agent.py --workspace /tmp/qitos_epub`
- `python examples/real/open_deep_research_gaia_agent.py --workspace /tmp/qitos_gaia --gaia-from-local`

---

## Benchmark

QitOS benchmark 链路统一为：

`数据样本 -> adapter -> Task -> Engine`

已实现：
- `qitos.benchmark.gaia`
- `qitos.benchmark.tau_bench`（自包含移植）
- `qitos.benchmark.cybench`

对应示例：
- `examples/real/open_deep_research_gaia_agent.py`
- `examples/real/tau_bench_eval.py`
- `examples/real/cybench_eval.py`

---

## Evaluate 与 Metric

QitOS 将两类能力明确拆分：
- **轨迹判定**（`qitos.evaluate`）：单任务是否完成
- **指标聚合**（`qitos.metric`）：成功率、pass@k、平均 reward 等

`qitos.kit` 内置：
- evaluator：rule-based / DSL-based / model-based
- metric：success rate / average reward / pass@k / mean steps / stop reason distribution

---

## qita 可观测性

`qita` 用于快速评估 agent 行为质量：
- board：运行列表与统计
- view：结构化轨迹视图
- replay：浏览器回放
- export：导出原始 JSON 或渲染 HTML

```bash
qita board --logdir runs
```

---

## 项目结构

- `qitos/core/`：核心契约（`AgentModule`, `Task`, `Env`, `Memory`, `History`, `ToolRegistry`）
- `qitos/engine/`：唯一执行内核
- `qitos/kit/`：可复用工具、记忆、解析、规划、评测实现
- `qitos/benchmark/`：benchmark 适配
- `qitos/qita/`：轨迹可视化工具

---

## 文档

- 主文档: [https://qitor.github.io/qitos/](https://qitor.github.io/qitos/)
- API 参考: [https://qitor.github.io/qitos/reference/api_generated/](https://qitor.github.io/qitos/reference/api_generated/)
- 中文文档: [https://qitor.github.io/qitos/zh/](https://qitor.github.io/qitos/zh/)

---

## License

MIT，见 [LICENSE](LICENSE)。
