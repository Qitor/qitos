# Lab 1 - Build a ReAct Baseline (30 min, with code)

## Goal

Build a minimal, reproducible ReAct baseline using QitOS contracts (not by copy-editing an example).

You will produce:

1. a baseline `AgentModule`
2. a fixed `Task` + budget
3. trace artifacts you can compare later

---

## Part A: Define the experiment task (5 min)

Use a structured `Task`, not just natural language.

```python
from qitos import Task, TaskBudget, EnvSpec

task = Task(
    id="lab1_react_baseline",
    objective="Fix buggy_module.py so add(20,22)==42 and verify by command.",
    env_spec=EnvSpec(type="host", config={"workspace_root": "./playground"}),
    budget=TaskBudget(max_steps=8),
)
```

Why this matters:

- You need stable inputs to compare methods.
- Budget is part of the method contract.

---

## Part B: Design minimal ReAct state (5 min)

Keep state small and explicitly record the agent trajectory.

```python
from dataclasses import dataclass, field
from typing import List

from qitos import StateSchema

@dataclass
class ReactState(StateSchema):
    scratchpad: List[str] = field(default_factory=list)
```

---

## Part C: Implement the ReAct agent (10 min)

### C1. Wire tools + parser

```python
from qitos import Action, AgentModule, ToolRegistry
from qitos.kit.parser import ReActTextParser
from qitos.kit.tool import EditorToolSet, RunCommand

class ReactAgent(AgentModule[ReactState, dict, Action]):
    def __init__(self, llm, workspace_root: str):
        registry = ToolRegistry()
        registry.include(EditorToolSet(workspace_root=workspace_root))
        registry.register(RunCommand(cwd=workspace_root))
        super().__init__(tool_registry=registry, llm=llm, model_parser=ReActTextParser())
```

### C2. Implement lifecycle methods

```python
from qitos import Decision
from qitos.kit.planning import format_action

SYSTEM_PROMPT = """You are a concise ReAct agent.
Rules:
- Exactly one tool call per step.
Output:
Thought: <short reasoning>
Action: <tool_name>(arg=value, ...)
or
Final Answer: <result>
"""

class ReactAgent(AgentModule[ReactState, dict, Action]):
    # __init__ as above

    def init_state(self, task: str, **kwargs):
        return ReactState(task=task, max_steps=int(kwargs.get("max_steps", 8)))

    def observe(self, state: ReactState, env_view: dict):
        return {"task": state.task, "scratchpad": state.scratchpad[-8:]}

    def build_system_prompt(self, state: ReactState):
        return SYSTEM_PROMPT

    def prepare(self, state: ReactState, observation: dict) -> str:
        parts = [f"Task: {state.task}", f"Step: {state.current_step}/{state.max_steps}"]
        if state.scratchpad:
            parts.extend(["Recent:", *state.scratchpad[-6:]])
        return "\n".join(parts)

    def decide(self, state: ReactState, observation: dict):
        return None  # Engine will call llm + parser

    def reduce(self, state: ReactState, observation: dict, decision: Decision[Action], action_results: list):
        if decision.rationale:
            state.scratchpad.append(f"Thought: {decision.rationale}")
        if decision.actions:
            state.scratchpad.append(f"Action: {format_action(decision.actions[0])}")
        if action_results:
            state.scratchpad.append(f"Observation: {action_results[0]}")
        state.scratchpad = state.scratchpad[-30:]
        return state
```

---

## Part D: Run and validate (10 min)

If you want to run the repo’s ready-made pattern script (recommended for this lab):

```bash
python examples/patterns/react.py --workspace ./playground --max-steps 8
```

Validation checklist:

1. `stop_reason` is clear.
2. `steps` stays within budget.
3. the trajectory is readable (thought/action/observation).
4. failures are localized by phase (`parse`, `tool`, `env`, `model`).

---

## Source Index

- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [qitos/kit/parser/react_parser.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/parser/react_parser.py)
- [qitos/kit/tool/editor.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/tool/editor.py)
