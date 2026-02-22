# 从 Core 实现新 Agent

## 目标

学会基于 QitOS core 接口逐步实现一个新 Agent 模块，而不是“复制例子改几行”。

## 1）必须实现的方法

自定义 `AgentModule` 时，至少要实现：

1. `init_state`
2. `observe`
3. `reduce`

可选实现：

1. `build_system_prompt`
2. `prepare`
3. `decide`
4. `build_memory_query`
5. `should_stop`

## 2）最小模板（建议从这个模板起步）

```python
from dataclasses import dataclass, field
from typing import Any

from qitos import Action, AgentModule, Decision, StateSchema, ToolRegistry
from qitos.kit.parser import ReActTextParser

@dataclass
class MyState(StateSchema):
    logs: list[str] = field(default_factory=list)

class MyAgent(AgentModule[MyState, dict[str, Any], Action]):
    def __init__(self, llm):
        registry = ToolRegistry()
        super().__init__(tool_registry=registry, llm=llm, model_parser=ReActTextParser())

    def init_state(self, task: str, **kwargs: Any) -> MyState:
        return MyState(task=task, max_steps=int(kwargs.get("max_steps", 8)))

    def observe(self, state: MyState, env_view: dict[str, Any]) -> dict[str, Any]:
        return {"task": state.task, "step": state.current_step, "logs": state.logs[-6:]}

    def build_system_prompt(self, state: MyState) -> str | None:
        return "你是一个稳定、谨慎的智能体。"

    def prepare(self, state: MyState, observation: dict[str, Any]) -> str:
        return f"Task: {state.task}\nStep: {state.current_step}\nObservation: {observation}"

    def decide(self, state: MyState, observation: dict[str, Any]):
        return None  # 让 Engine 调模型

    def reduce(self, state: MyState, observation: dict[str, Any], decision: Decision[Action], action_results: list[Any]) -> MyState:
        state.logs.append(f"mode={decision.mode}")
        if action_results:
            state.logs.append(f"result={action_results[0]}")
        state.logs = state.logs[-30:]
        return state
```

## 3）方法级设计建议

### `init_state`

1. 所有后续要用的字段都初始化
2. 预算参数显式化
3. 支持 `kwargs` 便于做实验开关

### `observe`

1. 只给当前 step 需要的信息
2. 历史信息必须截断
3. 输出尽量结构化

### `build_system_prompt`

1. 明确输出格式
2. 明确工具使用约束
3. 避免冲突规则

### `prepare`

1. 把 observation 转成可读且紧凑的输入
2. 包含 step 信息，减少空转

### `reduce`

1. 写入可追踪过程信息
2. 控制状态增长
3. 只做状态更新，不做流程编排

## 4）什么时候自己 decide，什么时候让 Engine decide

自己 `decide`：

- 决策确定性强
- 不依赖模型

Engine 兜底模型决策（`decide -> None`）：

- LLM 驱动策略
- 需要 parser 约束输出

## 5）实现新 Agent 的调试清单

1. parser 是否能稳定解析
2. tool 名与参数是否匹配
3. env 能力是否满足工具需求
4. stop 条件是否合理
5. trace 是否能复盘完整过程

## Source Index

- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
- [examples/patterns/planact.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/planact.py)
- [examples/patterns/reflexion.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/reflexion.py)
- [tests/test_engine_core_flow.py](https://github.com/Qitor/qitos/blob/main/tests/test_engine_core_flow.py)
