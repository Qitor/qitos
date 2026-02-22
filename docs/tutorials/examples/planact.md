# PlanAct Example Walkthrough (Plan First, Execute Step-by-Step)

## What this agent is

`examples/patterns/planact.py` implements a simple PlanAct pattern:

1. build a numbered plan
2. execute exactly one plan step per loop iteration
3. advance the plan cursor only when a step succeeds

It intentionally mixes two decision mechanisms:

- a deterministic “planner” (`_plan`) that calls LLM directly
- Engine-driven ReAct execution (`decide -> None`) once a plan step exists

## Core idea

PlanAct separates “global structure” from “local action choice”.

In QitOS terms:

- planning is a state transition: it populates `state.plan_steps` and resets `state.cursor`
- execution uses the same stable kernel phases as ReAct

## Method-by-method design

### `PlanActState`: plan is state, not hidden control flow

Design principle:

- Plans must be inspectable and comparable. Put them in typed state.

What the example does:

- stores `plan_steps` and `cursor`
- uses `scratchpad` to log the plan and step outcomes

### `observe`: expose plan cursor + current step

Design principle:

- The model should know “where it is” in the plan.

What the example does:

- includes `plan_steps`, `cursor`, and computed `current_step`
- includes recent scratchpad only (bounded)

### `build_system_prompt`: execution prompt depends on current plan step

Design principle:

- Execution policy should be conditioned on the plan step, not the whole plan.

What the example does:

- injects `current_step` into system prompt
- includes tool schema and ReAct output constraints

### `decide`: deterministic plan gate, then delegate to Engine

Design principle:

- Use deterministic gates to keep long-horizon behavior stable.

What the example does:

- if no plan exists (or cursor is beyond the end), call `_plan(state)`
- after plan exists, return `None` so Engine calls LLM and parses ReAct output
- uses `Decision.wait("plan_ready")` to make the transition explicit in trace

### `_plan`: smallest “planner” that still supports reproduction

Design principle:

- Planning is a separate prompt/protocol from execution.

What the example does:

- uses a strict “numbered plan only” system instruction
- parses with `parse_numbered_plan(...)`
- records the plan into `scratchpad` for traceability

### `reduce`: advance cursor only on successful step

Design principle:

- The plan cursor is the real control variable. Advance it based on evidence.

What the example does:

- logs thought/action/observation
- advances cursor on tool success
- ends early when verification command succeeds (`returncode == 0`)

## What to change for research variants

1. Hierarchical plans:
   - store nested structure in state (e.g. `plan: list[list[str]]`)
2. Dynamic replanning:
   - set cursor to end when verification fails, then `_plan` again
3. Search-based plan selection:
   - emit `Decision.branch(candidates=[...])` and attach `Engine(search=...)`

## Source Index

- [examples/patterns/planact.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/planact.py)
- [qitos/core/state.py](https://github.com/Qitor/qitos/blob/main/qitos/core/state.py)
- [qitos/kit/planning/plan_parser.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/planning/plan_parser.py)
- [qitos/kit/parser/react_parser.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/parser/react_parser.py)
