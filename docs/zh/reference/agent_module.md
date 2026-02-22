# AgentModule（API 参考）

## 职责

`AgentModule` 只负责“策略语义”：

- 观察怎么组织
- 决策怎么产生
- 行动结果如何写回状态

循环顺序、预算、hooks、trace 都由 Engine 统一负责。

## 两种运行方式

QitOS 支持两种入口：

1. `Engine(agent=...).run(task)`：更显式、便于做运行时编排
2. `agent.run(task, ...)`：对使用者更省事的便捷封装

`agent.run(...)` 默认直接返回 `final_result`；当 `return_state=True` 时返回 `EngineResult`（包含 state/trace 等）。

## 必须实现的方法

- `init_state(task, **kwargs)`
- `observe(state, env_view)`
- `reduce(state, observation, decision, action_results)`

## 可选覆盖的方法

- `build_system_prompt(state)`
- `prepare(state, observation)`
- `decide(state, observation)`
- `build_memory_query(state, env_view)`
- `should_stop(state)`

## decide 的关键语义

- 返回 `Decision`：你完全控制决策（确定性策略）。
- 返回 `None`：Engine 调用 `llm(messages)` 并用 parser 解析。

## 典型骨架（LLM 驱动）

大多数研究型 agent 最终都会收敛到这个最小形态：

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
        return None  # 交给 Engine：走默认模型路径

    def reduce(self, state: S, observation: dict[str, Any], decision: Decision[Action], action_results: list[Any]) -> S:
        if decision.rationale:
            state.scratchpad.append(f"Thought: {decision.rationale}")
        if decision.actions:
            state.scratchpad.append(f"Action: {decision.actions[0]}")
        if action_results:
            state.scratchpad.append(f"Observation: {action_results[0]}")
        return state
```

## Source Index

- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [docs/zh/research/agent_authoring.md](../research/agent_authoring.md)
