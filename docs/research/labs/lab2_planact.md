# Lab 2 - Upgrade ReAct to PlanAct (30 min, with code)

## Goal

Upgrade your baseline from reactive tool use to plan-first execution.

Constraints:

- keep the same task objective and evaluation criteria
- only change the policy architecture

---

## Part A: Write the upgrade hypothesis (5 min)

Make the research intent explicit.

```python
hypothesis = {
    "baseline": "ReAct",
    "candidate": "PlanAct",
    "expected_gain": "fewer invalid loops and better long-horizon stability",
    "fixed_budget": {"max_steps": 10},
}
print(hypothesis)
```

---

## Part B: Extend state minimally (5 min)

Add only plan-essential fields.

```python
from dataclasses import dataclass, field
from typing import List

from qitos import StateSchema

@dataclass
class PlanActState(StateSchema):
    plan_steps: List[str] = field(default_factory=list)
    cursor: int = 0
    scratchpad: List[str] = field(default_factory=list)
```

---

## Part C: Implement two-stage policy (10 min)

### C1. Planner: model -> numbered text -> structured list

```python
from qitos.kit.planning import parse_numbered_plan

PLAN_PROMPT = "Task: {task}\nReturn a numbered plan (3-5 steps)."

def build_plan(llm, task: str) -> list[str]:
    raw = llm([
        {"role": "system", "content": "Return numbered plan only."},
        {"role": "user", "content": PLAN_PROMPT.format(task=task)},
    ])
    return parse_numbered_plan(str(raw))
```

### C2. Decide: plan if missing, else execute one step

```python
from qitos import Action, AgentModule, Decision, ToolRegistry
from qitos.kit.parser import ReActTextParser

class PlanActAgent(AgentModule[PlanActState, dict, Action]):
    def __init__(self, llm, tool_registry: ToolRegistry):
        super().__init__(tool_registry=tool_registry, llm=llm, model_parser=ReActTextParser())

    def decide(self, state: PlanActState, observation: dict):
        if not state.plan_steps or state.cursor >= len(state.plan_steps):
            plan = build_plan(self.llm, state.task)
            if not plan:
                return Decision.final("Failed to build a valid plan")
            state.plan_steps = plan
            state.cursor = 0
            return Decision.wait("plan_ready")
        return None
```

### C3. Reduce: advance cursor and terminate on verification

```python
class PlanActAgent(AgentModule[PlanActState, dict, Action]):
    # ... init/prepare/prepare omitted

    def reduce(self, state: PlanActState, observation: dict, decision):
        if observation['action_results'] and isinstance(observation['action_results'][0], dict):
            r = observation['action_results'][0]
            if r.get("status") == "success":
                state.cursor += 1
            if int(r.get("returncode", 1)) == 0:
                state.final_result = "Verification passed"
                state.cursor = len(state.plan_steps)
        return state
```

---

## Part D: Run and compare (10 min)

```bash
python examples/patterns/planact.py --workspace ./playground --max-steps 10
```

Compare with Lab 1:

1. success rate
2. step count
3. dominant failure categories

---

## Source Index

- [examples/patterns/planact.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/planact.py)
- [qitos/kit/planning/plan.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/planning/plan.py)
- [qitos/core/state.py](https://github.com/Qitor/qitos/blob/main/qitos/core/state.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
