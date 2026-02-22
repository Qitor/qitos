# Task 与 StateSchema

## Task

使用 `Task` 可以把实验输入结构化：

- `objective`
- `resources`
- `budget`（steps/tokens/runtime）
- `env_spec`

### 最小 Task 示例

```python
from qitos import EnvSpec, Task, TaskBudget

task = Task(
    id="demo",
    objective="Open README.md and summarize it",
    env_spec=EnvSpec(type="host", config={"workspace_root": "./playground"}),
    budget=TaskBudget(max_steps=8),
)
```

当你在快速试错时，可以直接用字符串任务（`Engine.run(\"...\")`）。
当你要做可复现实验、做横向对比、做评测时，建议用 `Task(...)`。

## StateSchema

`StateSchema` 是运行时唯一事实来源。

它已经包含了内核稳定字段，供 Engine 与工具链使用：

- `task`, `current_step`, `max_steps`
- `final_result`, `stop_reason`
- `memory`（可选：结构化记忆视图）
- `metrics`（用来积累评测指标）
- `plan`（结构化 `PlanState`，用于 plan/execute 风格 agent）

原则：

1. 所有实验相关字段都要进入 state
2. 状态必须有界（截断日志）
3. 不要把关键事实放在局部变量

### 最小 StateSchema 子类

```python
from dataclasses import dataclass, field
from qitos import StateSchema

@dataclass
class MyState(StateSchema):
    scratchpad: list[str] = field(default_factory=list)
    tool_errors: int = 0
```

## Source Index

- [qitos/core/task.py](https://github.com/Qitor/qitos/blob/main/qitos/core/task.py)
- [qitos/core/state.py](https://github.com/Qitor/qitos/blob/main/qitos/core/state.py)
