# AgentModule（API 参考）

## 职责

`AgentModule` 只定义策略语义，`Engine` 负责运行时编排。

你主要实现：状态初始化、模型输入准备、决策以及状态归约。

## 必须实现

- `init_state(task: str, **kwargs) -> State`
- `reduce(state, observation, decision) -> State`

## 可选覆盖

- `build_system_prompt(state) -> str | None`
- `prepare(state) -> str`
- `decide(state, observation) -> Decision | None`
- `should_stop(state) -> bool`

## 决策语义

- 返回 `Decision`：完全自定义策略路径。
- 返回 `None`：使用 Engine 默认模型路径（`prepare -> messages -> llm -> parser`）。

## Memory 与 History 语义

Memory 在 agent 上（`self.memory`），用于任务相关运行工件。
History 在 agent 上（`self.history`），用于模型消息上下文。

- 建议在 agent 构造时传入 memory。
- 在 `prepare` 中可直接通过 `self.memory` 检索上下文。
- 当 `decide` 返回 `None` 时，Engine 会用 `self.history` + `history_policy` 组装消息。

## 最小骨架

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

    def prepare(self, state: S) -> str:
        return f"Task: {state.task}\nRecent: {state.scratchpad[-6:]}"

    def decide(self, state: S, observation: dict[str, Any]):
        return None

    def reduce(self, state: S, observation: dict[str, Any], decision: Decision[Action]) -> S:
        if decision.rationale:
            state.scratchpad.append(f"Thought: {decision.rationale}")
        results = observation.get("action_results", [])
        if results:
            state.scratchpad.append(f"Observation: {results[0]}")
        return state
```
