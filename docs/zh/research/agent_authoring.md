# 编写新 AgentModule

## 目标

只实现策略代码，把运行时编排留给 Engine。

## 最小必需方法

1. `init_state(task, **kwargs)`
2. `reduce(state, observation, decision)`

## 常用可选方法

1. `build_system_prompt(state)`
2. `prepare(state)`
3. `decide(state, observation)`
4. `should_stop(state)`

## 模板

```python
from dataclasses import dataclass, field
from typing import Any

from qitos import Action, AgentModule, Decision, StateSchema

@dataclass
class MyState(StateSchema):
    notes: list[str] = field(default_factory=list)

class MyAgent(AgentModule[MyState, dict[str, Any], Action]):
    def init_state(self, task: str, **kwargs: Any) -> MyState:
        return MyState(task=task, max_steps=int(kwargs.get("max_steps", 8)))

    def prepare(self, state: MyState) -> str:
        return f"Task: {state.task}\nStep: {state.current_step}"

    def decide(self, state: MyState, observation: dict[str, Any]):
        return None

    def reduce(self, state: MyState, observation: dict[str, Any], decision: Decision[Action]) -> MyState:
        state.notes.append(f"mode={decision.mode}")
        results = observation.get("action_results", [])
        if results:
            state.notes.append(f"result={results[0]}")
        state.notes = state.notes[-30:]
        return state
```
