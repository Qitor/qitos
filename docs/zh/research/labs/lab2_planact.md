# Lab 2 - 从 ReAct 升级到 PlanAct（30 分钟，含代码分步）

## 适用场景

ReAct 在长任务中容易局部贪心，你要引入显式规划提升稳定性。

## 学习目标

1. 在同一内核下把策略从即时反应升级为先规划后执行。
2. 保持对照公平：任务集与预算口径不变。
3. 用 trace 验证收益与代价。

---

## Part A：定义升级假设（5 分钟）

先明确实验假设：

```python
hypothesis = {
    "baseline": "ReAct",
    "candidate": "PlanAct",
    "expected_gain": "fewer invalid loops on long-horizon tasks",
    "fixed_budget": {"max_steps": 10},
}
print(hypothesis)
```

这段不是业务代码，而是实验协议代码。建议和结果一起保存。

---

## Part B：状态升级（5 分钟）

在 ReAct 状态上新增“计划执行必需字段”：

```python
from dataclasses import dataclass, field
from typing import List
from qitos import StateSchema

@dataclass
class PlanActState(StateSchema):
    plan_steps: List[str] = field(default_factory=list)
    cursor: int = 0
    scratchpad: List[str] = field(default_factory=list)
```

可选辅助字段：`target_file`、`test_command`。

---

## Part C：实现两阶段策略（10 分钟）

### C1. Planner 生成计划

```python
from qitos.kit.planning import parse_numbered_plan

PLAN_PROMPT = "Task: {task}\nReturn a numbered plan (3-5 steps)."

def build_plan(llm, task: str):
    raw = llm([
        {"role": "system", "content": "Return numbered plan only."},
        {"role": "user", "content": PLAN_PROMPT.format(task=task)},
    ])
    return parse_numbered_plan(str(raw))
```

### C2. Agent 的 decide/reduce 逻辑

```python
from qitos import Decision

class PlanActAgent(...):
    def decide(self, state: PlanActState, observation: dict):
        if not state.plan_steps or state.cursor >= len(state.plan_steps):
            plan = build_plan(self.llm, state.task)
            if not plan:
                return Decision.final("Failed to build a valid plan")
            state.plan_steps = plan
            state.cursor = 0
            return Decision.wait("plan_ready")
        return None  # 让 Engine+LLM 执行当前计划步骤

    def reduce(self, state: PlanActState, observation: dict, decision):
        if observation['action_results'] and isinstance(observation['action_results'][0], dict):
            r = observation['action_results'][0]
            if r.get("status") == "success":
                state.cursor += 1
            if int(r.get("returncode", 1)) == 0:
                state.final_result = "Verification passed"
                state.cursor = len(state.plan_steps)
        return state
```

---

## Part D：运行与对照评测（10 分钟）

### D1. 运行

```bash
python examples/patterns/planact.py --workspace ./playground --max-steps 10
```

### D2. 对照统计片段

```python
import json
from pathlib import Path

def read_summary(run_dir: str):
    m = json.loads(Path(run_dir, "manifest.json").read_text(encoding="utf-8"))
    return m.get("summary", {})

react = read_summary("runs/react_run")
planact = read_summary("runs/planact_run")
print("react steps:", react.get("steps"), "stop:", react.get("stop_reason"))
print("planact steps:", planact.get("steps"), "stop:", planact.get("stop_reason"))
```

你至少要回答：

1. PlanAct 是否减少了空转步骤？
2. 新增问题是否来自“规划质量”而不是“执行质量”？

---

## Source Index

- [examples/patterns/planact.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/planact.py)
- [qitos/kit/planning/plan.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/planning/plan.py)
- [qitos/core/state.py](https://github.com/Qitor/qitos/blob/main/qitos/core/state.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
