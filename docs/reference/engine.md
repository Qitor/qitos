# Engine (API Reference)

## Role

`Engine` is the canonical runtime kernel. It owns:

- loop orchestration
- task/env preflight checks
- action execution dispatch
- budgets and stop criteria
- hooks/events/trace

## Runtime chain

Per step:

1. DECIDE
2. ACT
3. REDUCE
4. CHECK_STOP

`prepare(state)` is used inside DECIDE when `agent.decide(...)` returns `None`.

## Default model path

When `decide` returns `None`, Engine does:

1. `prepared = agent.prepare(state)`
2. build messages (`system` + history + current user input)
3. `raw = agent.llm(messages)`
4. parser -> `Decision`

## Common runtime knobs

- `env`
- `history_policy`
- `hooks`
- `trace_writer`

## EngineResult

`Engine.run(...)` returns:

- `state`
- `records`
- `events`
- `step_count`
- `task_result` (optional)

## Minimal usage

```python
from qitos import Engine

result = Engine(agent=my_agent, env=my_env).run(task)
print(result.state.final_result, result.state.stop_reason)
```

## Source Index

- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [qitos/engine/states.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/states.py)
