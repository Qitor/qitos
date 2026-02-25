# AgentModule (API Reference)

## Role

`AgentModule` defines policy semantics. `Engine` owns orchestration.

You implement how state is initialized, how model input is prepared, how decisions are made, and how state is reduced.

## Required methods

- `init_state(task: str, **kwargs) -> State`
- `reduce(state, observation, decision) -> State`

## Optional methods

- `build_system_prompt(state) -> str | None`
- `prepare(state) -> str`
- `decide(state, observation) -> Decision | None`
- `build_memory_query(state, runtime_view) -> dict | None`
- `should_stop(state) -> bool`

## Decision semantics

- Return `Decision`: fully custom policy path.
- Return `None`: Engine model path (`prepare` -> messages -> llm -> parser -> `Decision`).

## Memory semantics

Memory is on the agent (`self.memory`).

- You can pass memory when constructing the agent (`super().__init__(..., memory=...)`).
- In `prepare`, you can retrieve memory via `self.memory.retrieve(...)` or `self.memory.retrieve_messages(...)`.
- Engine may also use `self.memory` in default model path when `decide` returns `None`.

## Minimal skeleton

```python
from dataclasses import dataclass, field
from typing import Any

from qitos import Action, AgentModule, Decision, StateSchema, ToolRegistry, tool
from qitos.kit.parser import ReActTextParser

@dataclass
class S(StateSchema):
    scratchpad: list[str] = field(default_factory=list)

@tool(name="add")
def add(a: int, b: int) -> int:
    return a + b

class A(AgentModule[S, dict[str, Any], Action]):
    def __init__(self, llm: Any):
        reg = ToolRegistry()
        reg.register(add)
        super().__init__(tool_registry=reg, llm=llm, model_parser=ReActTextParser())

    def init_state(self, task: str, **kwargs: Any) -> S:
        return S(task=task, max_steps=6)

    def build_system_prompt(self, state: S) -> str | None:
        return "Use ReAct. Return Action(...) or Final Answer: ..."

    def prepare(self, state: S) -> str:
        return f"Task: {state.task}\nRecent: {state.scratchpad[-6:]}"

    def decide(self, state: S, observation: dict[str, Any]):
        return None

    def reduce(self, state: S, observation: dict[str, Any], decision: Decision[Action]) -> S:
        if decision.rationale:
            state.scratchpad.append(f"Thought: {decision.rationale}")
        if decision.actions:
            state.scratchpad.append(f"Action: {decision.actions[0]}")
        results = observation.get("action_results", [])
        if results:
            state.scratchpad.append(f"Observation: {results[0]}")
        return state
```

## Source Index

- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [docs/research/agent_authoring.md](../research/agent_authoring.md)
