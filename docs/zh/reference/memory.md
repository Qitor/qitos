# Memory

## 目标

理解 memory 如何参与模型输入构建与运行复盘。

## 契约

`Memory` 提供：

- `append(record)`
- `retrieve(query, state, observation)`
- `retrieve_messages(...)`
- `summarize(max_items)`
- `reset(run_id)`

## memory 放在哪一层（很关键）

memory 是由 `Engine` 持有的运行时组件，而不是 agent 自己管理的东西。

agent 会影响 memory 的方式主要是：

- `AgentModule.build_memory_query(state, env_view)`：每一步的检索 query

Engine 会做两件事：

1. 用 `memory.append(...)` 记录交互/事件
2. 用 `memory.retrieve_messages(state, observation, query)` 取回 messages，拼入模型输入

## memory 出现在哪里

- `env_view["memory"]`
- Engine 构建 messages 时注入历史

## 最小：挂一个窗口记忆

```python
from qitos import Engine
from qitos.kit.env import HostEnv
from qitos.kit.memory import WindowMemory

engine = Engine(agent=my_agent, env=HostEnv(workspace_root="./playground"), memory=WindowMemory(window_size=20))
result = engine.run("do something")
```

## 让 agent 控制检索 query

通过 `build_memory_query` 让上下文有界、可控：

```python
class MyAgent(...):
    def build_memory_query(self, state, env_view):
        return {"format": "messages", "max_items": 12, "roles": ["message"]}
```

## Source Index

- [qitos/core/memory.py](https://github.com/Qitor/qitos/blob/main/qitos/core/memory.py)
- [qitos/kit/memory/window_memory.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/memory/window_memory.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
