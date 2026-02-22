# Memory

## Goal

Understand how memory interacts with the Engine model-input build.

## Contract

`Memory` provides:

- `append(record)`
- `retrieve(query, state, observation)`
- `retrieve_messages(state, observation, query)`
- `summarize(max_items)`
- `reset(run_id)`

## Where memory lives (important)

Memory is a runtime component owned by `Engine`, not by the agent.

The agent influences memory usage via:

- `AgentModule.build_memory_query(state, env_view)` (per-step retrieval query)

Engine uses:

1. `memory.append(...)` to record messages/events
2. `memory.retrieve_messages(state, observation, query)` to build chat history for the model

## Where memory shows up

- In `env_view["memory"]` (observation-time context)
- In Engine message build (history injection)

## Minimal: attach a window memory

```python
from qitos import Engine
from qitos.kit.env import HostEnv
from qitos.kit.memory import WindowMemory

engine = Engine(agent=my_agent, env=HostEnv(workspace_root="./playground"), memory=WindowMemory(window_size=20))
result = engine.run("do something")
```

## Custom retrieval query from the agent

Use `build_memory_query` to bound or shape context:

```python
class MyAgent(...):
    def build_memory_query(self, state, env_view):
        return {"format": "messages", "max_items": 12, "roles": ["message"]}
```

## Source Index

- [qitos/core/memory.py](https://github.com/Qitor/qitos/blob/main/qitos/core/memory.py)
- [qitos/kit/memory/window_memory.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/memory/window_memory.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
