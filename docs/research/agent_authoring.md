# Author New Agent Modules

## Goal

Learn how to inherit QitOS core contracts and build a new agent module from scratch, method by method.

## 1) Minimum required methods

A custom `AgentModule` must implement:

1. `init_state(task, **kwargs)`
2. `observe(state, env_view)`
3. `reduce(state, observation, decision, action_results)`

You may optionally override:

1. `build_system_prompt`
2. `prepare`
3. `decide`
4. `build_memory_query`
5. `should_stop`

## 2) Step-by-step implementation template

```python
from dataclasses import dataclass, field
from typing import Any

from qitos import Action, AgentModule, Decision, Engine, StateSchema, ToolRegistry
from qitos.kit.parser import ReActTextParser

@dataclass
class MyState(StateSchema):
    notes: list[str] = field(default_factory=list)

class MyAgent(AgentModule[MyState, dict[str, Any], Action]):
    def __init__(self, llm, workspace_root: str):
        registry = ToolRegistry()
        # registry.register(...) / registry.include(...)
        super().__init__(tool_registry=registry, llm=llm, model_parser=ReActTextParser())

    def init_state(self, task: str, **kwargs: Any) -> MyState:
        return MyState(task=task, max_steps=int(kwargs.get("max_steps", 8)))

    def observe(self, state: MyState, env_view: dict[str, Any]) -> dict[str, Any]:
        return {
            "task": state.task,
            "step": state.current_step,
            "notes": state.notes[-6:],
        }

    def build_system_prompt(self, state: MyState) -> str | None:
        return "You are a reliable agent. Return one function-style action per step."

    def prepare(self, state: MyState, observation: dict[str, Any]) -> str:
        return f"Task: {state.task}\nStep: {state.current_step}\nObs: {observation}"

    def decide(self, state: MyState, observation: dict[str, Any]):
        # return None => let Engine use llm + parser
        return None

    def reduce(self, state: MyState, observation: dict[str, Any], decision: Decision[Action], action_results: list[Any]) -> MyState:
        state.notes.append(f"mode={decision.mode}")
        if action_results:
            state.notes.append(f"result={action_results[0]}")
        state.notes = state.notes[-30:]
        return state
```

## 3) Method-by-method design guidance

### `init_state`

Best practice:

1. initialize all fields used later in `observe/reduce`
2. keep defaults explicit and small
3. accept `kwargs` for experiment toggles

### `observe`

Best practice:

1. include task + minimal context needed for this step
2. include only bounded history slices
3. avoid dumping entire state every step

### `build_system_prompt`

Best practice:

1. state output format constraints explicitly
2. include tool schema summary
3. keep prompt stable to reduce parser drift

### `prepare`

Best practice:

1. map observation into concise model input text
2. include step counters to reduce looping
3. avoid redundant payload bloat

### `reduce`

Best practice:

1. append structured process records (thought/action/observation)
2. update termination hints carefully
3. cap history size

## 4) How to decide between custom decide vs Engine LLM path

Use custom `decide` when:

1. decision rule is deterministic
2. output shape is guaranteed

Use Engine LLM path (`decide -> None`) when:

1. you need model-driven policy
2. parser-governed output is acceptable

## 5) Debugging checklist when authoring agents

1. decision parse errors: verify prompt output protocol vs parser expectations
2. tool errors: verify action names/args and registry entries
3. env mismatch: verify required ops groups
4. silent loops: inspect `prepare` and stop criteria

## 6) Tiny test you should always add

At minimum, test:

1. one happy path run reaches final result
2. one malformed model output path fails gracefully
3. one env capability mismatch is caught preflight

## Source Index

- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
- [examples/patterns/planact.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/planact.py)
- [examples/patterns/reflexion.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/reflexion.py)
- [tests/test_engine_core_flow.py](https://github.com/Qitor/qitos/blob/main/tests/test_engine_core_flow.py)
