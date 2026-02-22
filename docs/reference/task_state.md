# Task & StateSchema

## Task

Use `Task` when you want structured, reproducible inputs:

- `objective`
- `resources`
- `budget` (max_steps/max_tokens/max_runtime)
- `env_spec`

### Minimal Task example

```python
from qitos import EnvSpec, Task, TaskBudget

task = Task(
    id="demo",
    objective="Open README.md and summarize it",
    env_spec=EnvSpec(type="host", config={"workspace_root": "./playground"}),
    budget=TaskBudget(max_steps=8),
)
```

Use plain string tasks (`Engine.run("...")`) when you are prototyping.
Use `Task(...)` when you need reproducibility, metadata, and consistent evaluation.

## StateSchema

`StateSchema` is the runtime single source of truth.

It already includes kernel-stable fields used by Engine and tooling:

- `task`, `current_step`, `max_steps`
- `final_result`, `stop_reason`
- `memory` (optional structured memory view)
- `metrics` (place to accumulate eval stats)
- `plan` (structured `PlanState` for plan/execute style agents)

Principles:

1. put all experiment-relevant fields in state
2. keep state bounded (truncate logs)
3. never rely on local variables for critical facts

### Minimal StateSchema subclass

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
