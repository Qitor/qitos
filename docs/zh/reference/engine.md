# Engine（API 参考）

## 职责

`Engine` 是唯一内核执行器，负责：

- 标准循环顺序
- 预检（task + env）
- 动作执行分发
- budget 与 stop
- hooks + events + trace

## 运行阶段

1. `OBSERVE`
2. `DECIDE`
3. `ACT`
4. `REDUCE`
5. `CRITIC`（可选）
6. `CHECK_STOP`

## 与 AgentModule.run(...) 的关系

`AgentModule.run(...)` 是一个非常薄的便捷封装：

- 通过 `agent.build_engine(...)` 构造 Engine
- 透传 `hooks` / `engine_kwargs` / state kwargs
- 默认返回 `final_result`，当 `return_state=True` 时返回 `EngineResult`

当你想显式掌控 env/memory/trace/hook 的接线时，直接用 `Engine.run(...)` 更清晰。

## 基本用法

```python
from qitos import Engine

result = Engine(agent=my_agent, env=my_env).run(task)
print(result.state.final_result, result.state.stop_reason)
```

## 常用运行参数（推荐你先理解）

你通常会把这些参数交给 Engine（无论你是直接 new Engine，还是通过 `agent.run(..., engine_kwargs=...)` 间接传入）：

- `env`：执行后端（host/docker/remote）
- `memory`：为 DECIDE 阶段提供可检索的上下文 messages/records
- `hooks`：阶段级回调（结构化）
- `trace_writer`：写入 run artifacts（manifest/events/steps）

## 最小：Engine 触发模型调用路径

关键契约：当 `AgentModule.decide(...)` 返回 `None`，Engine 会调用你提供的 `llm(messages)`，并用 parser 把输出转成 `Decision`。

```python
from dataclasses import dataclass
from typing import Any

from qitos import Action, AgentModule, Decision, Engine, StateSchema, ToolRegistry, tool
from qitos.kit.env import HostEnv
from qitos.kit.parser import ReActTextParser
from qitos.models import OpenAICompatibleModel

@dataclass
class S(StateSchema):
    pass

@tool(name="add")
def add(a: int, b: int) -> int:
    return a + b

class A(AgentModule[S, dict[str, Any], Action]):
    def __init__(self, llm: Any):
        reg = ToolRegistry()
        reg.register(add)
        super().__init__(tool_registry=reg, llm=llm, model_parser=ReActTextParser())

    def init_state(self, task: str, **kwargs: Any) -> S:
        return S(task=task, max_steps=4)

    def observe(self, state: S, env_view: dict[str, Any]) -> dict[str, Any]:
        return {"task": state.task}

    def build_system_prompt(self, state: S) -> str | None:
        return "Use ReAct. Call add(a=..., b=...) or output Final Answer: ..."

    def decide(self, state: S, observation: dict[str, Any]):
        return None

    def reduce(self, state: S, observation: dict[str, Any], decision: Decision[Action], action_results: list[Any]) -> S:
        return state

llm = OpenAICompatibleModel(model="Qwen/Qwen3-8B", base_url="https://api.siliconflow.cn/v1/", api_key="...")
env = HostEnv(workspace_root="./playground")
result = Engine(agent=A(llm), env=env).run("compute 19+23 using add")
print(result.state.final_result, result.state.stop_reason)
```

## Source Index

- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [qitos/engine/states.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/states.py)
