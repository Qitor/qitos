# Lab 1 - 从零构建 ReAct 研究基线（30 分钟，含代码分步）

## 适用场景

你要做一个“工具驱动 + 可解释轨迹”的最小研究基线，用来作为后续方法升级的对照组。

## 学习目标

1. 自己定义一个可研究的 Agent 任务。
2. 用 QitOS 从零实现 ReAct 策略。
3. 输出可比较的 trace 与指标。

---

## Part A：定义研究问题与任务对象（5 分钟）

先把实验对象结构化成 `Task`，不要只写自然语言。

```python
from qitos import Task, TaskBudget, EnvSpec

task = Task(
    id="lab1_react_baseline",
    objective="Fix buggy_module.py so add(20,22)==42 and verify by command.",
    env_spec=EnvSpec(type="host", config={"workspace_root": "./playground"}),
    budget=TaskBudget(max_steps=8),
)
```

说明：

1. `objective` 是统一比较口径，不要每轮改写。
2. `budget` 是实验边界，后续对比必须一致。
3. `env_spec` 保证后端一致，避免“环境差异伪提升”。

---

## Part B：设计最小 ReAct 状态（5 分钟）

```python
from dataclasses import dataclass, field
from typing import List
from qitos import StateSchema

@dataclass
class ReactState(StateSchema):
    scratchpad: List[str] = field(default_factory=list)
```

说明：

1. 只新增 `scratchpad` 就够做 ReAct 基线。
2. `StateSchema` 已带 `task/current_step/max_steps/final_result`。
3. 状态越小，越容易复盘失败原因。

---

## Part C：实现 ReAct Agent（10 分钟）

### C1. 构造函数：工具 + parser + llm

```python
from qitos import Action, AgentModule, ToolRegistry
from qitos.kit.tool import EditorToolSet, RunCommand
from qitos.kit.parser import ReActTextParser

class ReactAgent(AgentModule[ReactState, dict, Action]):
    def __init__(self, llm, workspace_root: str):
        registry = ToolRegistry()
        registry.include(EditorToolSet(workspace_root=workspace_root))
        registry.register(RunCommand(cwd=workspace_root))
        super().__init__(tool_registry=registry, llm=llm, model_parser=ReActTextParser())
```

### C2. 生命周期最小实现

```python
from qitos import Decision
from qitos.kit.planning import format_action

SYSTEM_PROMPT = """You are a concise ReAct agent.
Rules:
- Exactly one tool call per step.
Output:
Thought: <short reasoning>
Action: <tool_name>(arg=value, ...)
or
Final Answer: <result>
"""

class ReactAgent(AgentModule[ReactState, dict, Action]):
    # __init__ 同上

    def init_state(self, task: str, **kwargs):
        return ReactState(task=task, max_steps=int(kwargs.get("max_steps", 8)))

    def observe(self, state: ReactState, env_view: dict):
        return {"task": state.task, "scratchpad": state.scratchpad[-8:]}

    def build_system_prompt(self, state: ReactState):
        return SYSTEM_PROMPT

    def prepare(self, state: ReactState, observation: dict):
        parts = [f"Task: {state.task}", f"Step: {state.current_step}/{state.max_steps}"]
        if state.scratchpad:
            parts.extend(["Recent:", *state.scratchpad[-6:]])
        return "\n".join(parts)

    def decide(self, state: ReactState, observation: dict):
        return None  # 交给 Engine 走 llm + parser

    def reduce(self, state: ReactState, observation: dict, decision: Decision[Action], action_results: list):
        if decision.rationale:
            state.scratchpad.append(f"Thought: {decision.rationale}")
        if decision.actions:
            state.scratchpad.append(f"Action: {format_action(decision.actions[0])}")
        if action_results:
            state.scratchpad.append(f"Observation: {action_results[0]}")
        state.scratchpad = state.scratchpad[-30:]
        return state
```

说明：

1. `decide -> None` 是 ReAct 常见模型驱动路径。
2. `reduce` 是“可解释过程”落地关键，不要省略。

---

## Part D：运行与评估（10 分钟）

### D1. 运行代码

```python
from qitos import Engine
from qitos.kit.env import HostEnv

engine = Engine(agent=agent, env=HostEnv(workspace_root="./playground"))
result = engine.run(task, max_steps=8)
print(result.state.final_result, result.state.stop_reason)
```

### D2. 命令行快速跑

```bash
python examples/patterns/react.py --workspace ./playground --max-steps 8
```

### D3. 评估脚本片段（最小）

```python
import json
from pathlib import Path

run_dir = Path("runs")  # 选择你这次 run 对应目录
manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
summary = manifest.get("summary", {})
print("stop_reason:", summary.get("stop_reason"))
print("steps:", summary.get("steps"))
```

至少记录：

1. 成功率（跑 3 次）
2. 平均步数
3. 失败主类型

---

## Source Index

- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
- [qitos/kit/parser/react_parser.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/parser/react_parser.py)
- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
