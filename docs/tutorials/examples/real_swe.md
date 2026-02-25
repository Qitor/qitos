# Practical SWE Agent Walkthrough (Dynamic Planning + Branch Selection)

## What this agent is

`examples/real/swe_agent.py` is a minimal “SWE-style” closed loop:

- plan first (numbered plan)
- execute one step at a time
- when uncertain, propose multiple candidates and let search/selection pick one
- always verify via a command before finishing

It uses:

- XML decision protocol (`XmlDecisionParser`)
- `Decision.branch(...)` to represent multiple action candidates
- `RepoEnv` for repo/workspace semantics (SWE-style tasks)

## Core design choices

1. **Planning is explicit state** (`plan_steps`, `cursor`).
2. **Execution is one-action-per-step** (strict XML output).
3. **Robustness comes from candidate sets** (LLM + deterministic fallbacks).
4. **Verification drives termination**, not narrative confidence.

## Method-by-method design

### `SWEPlanState`: plan cursor is the control variable

Fields:

- `plan_steps`, `cursor`: explicit planning state
- `scratchpad`: bounded execution trail
- `target_file`, `test_command`: stable constraints
- `replan_count`: tracks instability (useful for eval)

### `prepare`: expose plan cursor and memory view

Why:

- the model needs “where am I in the plan”
- the agent should see a bounded memory/debug view

### `build_system_prompt`: XML protocol reduces parser ambiguity

Why XML here:

- JSON often breaks under nested quoting in code contexts
- XML is easier to constrain structurally for tool calls

The prompt enforces:

- exactly one `<decision>` root
- `mode="act|final|wait"`
- one tool action per step

### `prepare`: make the plan and constraints legible

It includes:

- task + file + verification command
- full plan with a cursor marker
- recent execution trace

Design principle:

- the model should not “reconstruct the plan” from scratch each step.

### `decide`: dynamic planning + candidate branching

This method implements three layers:

1. If no plan (or plan ended): `_make_or_refresh_plan(...)` then `Decision.wait("plan_ready")`
2. Else: build action candidates:
   - candidate 1: LLM-proposed action (via `_llm_step_action`)
   - candidate 2+: deterministic fallbacks based on step keywords (inspect/edit/test)
3. Return `Decision.branch(candidates=...)` so Engine can select

Design principle:

- you want one place to add robustness without rewriting the entire agent.

### `reduce`: advance only on tool evidence

Advancement rules:

- on tool `status == "success"` => advance
- on verification `returncode == 0` => set `final_result` and finish
- on failed verification => trigger replanning next step

## Engine wiring (what makes it “SWE-like”)

The example uses:

- `RepoEnv(...)` so file/process ops are scoped to a repo workspace
- `DynamicTreeSearch(...)` (optional) to select branch candidates

## Source Index

- [examples/real/swe_agent.py](https://github.com/Qitor/qitos/blob/main/examples/real/swe_agent.py)
- [qitos/kit/parser/xml_parser.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/parser/xml_parser.py)
- [qitos/kit/env/repo_env.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/env/repo_env.py)
- [qitos/kit/planning/dynamic_tree_search.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/planning/dynamic_tree_search.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
