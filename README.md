# QitOS Framework

QitOS is a research-oriented agent framework with one canonical kernel:

- `AgentModule`
- `Decision`
- `Policy`
- `Runtime`
- `ToolRegistry` / `ToolSet`
- `Trace`

## Why QitOS

- Fast agent iteration for ReAct, PlanAct, ToT-style workflows.
- Strong observability with step traces and replayability.
- Modular components without runtime rewrites.

## Quick Start

```python
from qitos import Action, AgentModule, Decision, ToolRegistry, tool
from qitos.core.state import StateSchema


class MyState(StateSchema):
    pass


class MyAgent(AgentModule[MyState, dict, Action]):
    def __init__(self):
        registry = ToolRegistry()

        @tool(name="add")
        def add(a: int, b: int) -> int:
            return a + b

        registry.register(add)
        super().__init__(toolkit=registry)

    def init_state(self, task: str, **kwargs):
        return MyState(task=task)

    def observe(self, state, env_view):
        return {"task": state.task, "step": state.current_step}

    def decide(self, state, observation):
        if state.current_step == 0:
            return Decision.act([Action(name="add", args={"a": 40, "b": 2})])
        return Decision.final("42")

    def reduce(self, state, observation, decision, action_results):
        return state


agent = MyAgent()
answer = agent.run("compute 40 + 2")
print(answer)
```

## Core Docs

- `/Users/morinop/coding/yoga_framework/docs/kernel_scope.md`
- `/Users/morinop/coding/yoga_framework/docs/kernel_invariants.md`
- `/Users/morinop/coding/yoga_framework/docs/agent_run.md`
- `/Users/morinop/coding/yoga_framework/docs/PROJECT_FULL_DOC.md`
- `/Users/morinop/coding/yoga_framework/docs/adr/ADR-001-single-kernel.md`
- `/Users/morinop/coding/yoga_framework/PRD.md`
