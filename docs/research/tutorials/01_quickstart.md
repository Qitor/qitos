# 01 Quickstart: First Runnable Agent

## Goal

Build a minimal agent that calls a tool and returns a final answer.

## Code

```python
from dataclasses import dataclass
from typing import Any

from qitos import Action, AgentModule, Decision, StateSchema, ToolRegistry, tool


@dataclass
class CalcState(StateSchema):
    last_result: int | None = None


class CalcAgent(AgentModule[CalcState, dict, Action]):
    def __init__(self):
        registry = ToolRegistry()

        @tool(name="add", description="Add two integers")
        def add(a: int, b: int) -> int:
            return a + b

        registry.register(add)
        super().__init__(toolkit=registry)

    def init_state(self, task: str, **kwargs: Any) -> CalcState:
        return CalcState(task=task, max_steps=int(kwargs.get("max_steps", 4)))

    def observe(self, state: CalcState, env_view: dict) -> dict:
        return {"task": state.task, "step": state.current_step, "last_result": state.last_result}

    def decide(self, state: CalcState, observation: dict) -> Decision[Action]:
        if state.last_result is not None:
            return Decision.final(str(state.last_result), rationale="Result already computed")
        return Decision.act([Action(name="add", args={"a": 40, "b": 2})], rationale="Need calculation")

    def reduce(self, state: CalcState, observation: dict, decision: Decision[Action], action_results: list[Any]) -> CalcState:
        if action_results:
            state.last_result = int(action_results[0])
        return state


if __name__ == "__main__":
    agent = CalcAgent()
    print(agent.run("compute 40 + 2"))
```

## Why This Matters

- `AgentModule` is the only class you must implement.
- `agent.run(...)` is the default entry for fast experiments.
- You get step-wise orchestration from the engine automatically.

## Next

Move to `02_core_mental_model.md` to understand what to change when creating a new agent idea.
