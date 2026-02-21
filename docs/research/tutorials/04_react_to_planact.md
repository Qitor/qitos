# 04 ReAct -> PlanAct with Minimal Diffs

## ReAct Pattern

Typical ReAct state:
- scratchpad
- last tool result
- optional pending action

Decision style:
- think one step
- call one tool
- observe result
- finalize

Reference: `/Users/morinop/coding/yoga_framework/templates/react/agent.py`

## PlanAct Pattern

Add planning fields:
- `work_plan`
- `plan_cursor_local`
- `intermediate`

Decision style:
- if no plan: create plan and `Decision.wait(...)`
- else: execute current plan step via `Decision.act(...)`
- finalize when cursor reaches plan end

Reference: `/Users/morinop/coding/yoga_framework/templates/plan_act/agent.py`

## Minimal Change Strategy

1. Keep the same tools.
2. Extend state with plan fields.
3. Add `_build_plan(...)` helper.
4. Split `decide` into plan phase + execution phase.
5. In `reduce`, advance cursor only on successful action result.

## Why This Matters for Research

You can compare ReAct vs PlanAct behavior by changing only policy/state logic, while runtime/trace stays constant.
