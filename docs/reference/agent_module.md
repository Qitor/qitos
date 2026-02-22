# AgentModule (API Reference)

## Role

`AgentModule` is the only place you implement *policy semantics*:

- what to observe
- how to decide
- how state updates after actions

Everything else (loop order, budgets, hooks, trace) is owned by the Engine.

## Two ways to run

QitOS supports both entry points:

1. `Engine(agent=...).run(task)` for explicit orchestration control
2. `agent.run(task, ...)` as a convenience wrapper around Engine

`agent.run(...)` returns `final_result` by default, and returns `EngineResult` when `return_state=True`.

## Required methods

You must implement:

- `init_state(task: str, **kwargs) -> State`
- `observe(state, env_view) -> Observation`
- `reduce(state, observation, decision, action_results) -> State`

## Optional methods

You may override:

- `build_system_prompt(state) -> str | None`
- `prepare(state, observation) -> str`
- `decide(state, observation) -> Decision | None`
- `build_memory_query(state, env_view) -> dict | None`
- `should_stop(state) -> bool`

## Decide semantics (critical)

- Return a `Decision` when you want full control (deterministic policies).
- Return `None` when you want Engine to call `llm(messages)` and parse output.

## Canonical skeleton (LLM-driven)

This is the smallest useful shape most research agents converge to:

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

    def observe(self, state: S, env_view: dict[str, Any]) -> dict[str, Any]:
        return {"task": state.task, "recent": state.scratchpad[-6:]}

    def build_system_prompt(self, state: S) -> str | None:
        return "Use ReAct. Call add(a=..., b=...) or output Final Answer: ..."

    def prepare(self, state: S, observation: dict[str, Any]) -> str:
        return f"Task: {observation['task']}\nRecent: {observation['recent']}"

    def decide(self, state: S, observation: dict[str, Any]):
        return None  # delegate to Engine model path

    def reduce(self, state: S, observation: dict[str, Any], decision: Decision[Action], action_results: list[Any]) -> S:
        if decision.rationale:
            state.scratchpad.append(f"Thought: {decision.rationale}")
        if decision.actions:
            state.scratchpad.append(f"Action: {decision.actions[0]}")
        if action_results:
            state.scratchpad.append(f"Observation: {action_results[0]}")
        return state
```

## Minimal implementation checklist

1. State fields are initialized in `init_state`.
2. `observe` returns bounded context (no unbounded histories).
3. `reduce` records enough information for debugging.

## Source Index

- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [docs/research/agent_authoring.md](../research/agent_authoring.md)
