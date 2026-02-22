# Engine (API Reference)

## Role

`Engine` is the canonical runtime kernel. It owns:

- the step loop ordering
- preflight validation (task + env capabilities)
- action execution dispatch
- stop criteria and budgets
- hooks + events + trace writing

## Runtime phases

1. `OBSERVE`
2. `DECIDE`
3. `ACT`
4. `REDUCE`
5. `CRITIC` (optional)
6. `CHECK_STOP`

## Relationship with AgentModule.run(...)

`AgentModule.run(...)` is a thin convenience wrapper:

- it builds an Engine via `agent.build_engine(...)`
- it forwards `hooks`, `engine_kwargs`, and state kwargs
- it returns `final_result` unless `return_state=True`

Use `Engine.run(...)` directly when you want explicit ownership of env/memory/trace/hook wiring.

## Run signatures

Typical usage:

```python
from qitos import Engine

result = Engine(agent=my_agent, env=my_env, memory=my_memory).run(task)
print(result.state.final_result, result.state.stop_reason)
```

## Common run-time knobs

You typically pass these to Engine (either directly, or via `agent.run(..., engine_kwargs=...)`):

- `env`: execution backend (host/docker/remote)
- `memory`: message/record retrieval for DECIDE context
- `hooks`: structured phase callbacks
- `trace_writer`: run artifacts writer (manifest/events/steps)

## EngineResult

`Engine.run(...)` returns `EngineResult` containing:

- `state`
- `records` (step records)
- `events` (phase events)
- `step_count`
- `task_result` (optional)

## Minimal: Engine + LLM path

This example shows the important contract: if `AgentModule.decide(...)` returns `None`, Engine will call your model.

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
