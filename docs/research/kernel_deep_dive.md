# Kernel Deep Dive

## One run, precisely

`Engine.run(task)`:

1. init state (`agent.init_state`)
2. preflight (task/env)
3. loop: `DECIDE -> ACT -> REDUCE -> CHECK_STOP`
4. finalize (trace/task_result)

## Phase semantics

### INIT

- resets runtime components
- prepares env/toolset
- emits run-start events

### DECIDE

Input:
- `state`
- previous `observation`

Two paths:
1. `agent.decide(...)` returns `Decision`
2. returns `None` -> Engine model path:
- `prepare(state)`
- build messages (`system + memory history + user`)
- `llm(messages)`
- parser -> `Decision`

### ACT

- executes tool actions via `ActionExecutor`
- updates `record.action_results`
- env step outputs are merged into action results

### REDUCE

- calls `agent.reduce(state, observation, decision)`
- `observation` contains step outputs (`action_results`, env data, state snapshot)
- computes `state_diff`

### CHECK_STOP

Stop sources include:
- `decision.mode == final`
- `agent.should_stop(state)`
- env terminal
- budget/criteria

## Memory semantics

- Memory is agent-owned (`agent.memory`).
- Engine appends runtime records and can retrieve history from `agent.memory` in default model path.
- Observation should not include memory by default.

## Hook model

Key hook families:
- run: `on_run_start`, `on_run_end`
- step: `on_before_step`, `on_after_step`
- phase: `on_before_decide/act/reduce/check_stop`, `on_after_*`
- recovery/events: `on_recover`, `on_event`

## Source Index

- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [qitos/engine/hooks.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/hooks.py)
