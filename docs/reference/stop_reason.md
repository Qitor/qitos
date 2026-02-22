# StopReason

## Goal

Stop reasons are a stable contract for debugging and evaluation.

## What it is

`StopReason` is a standardized enum (stored as a string in `StateSchema.stop_reason`).

It is how QitOS makes runs comparable across:

- different prompts/parsers/tools
- different Env backends
- different recovery policies

## Common stop reasons (with intent)

- `success`: run completed successfully (may be used by tasks/env wrappers)
- `final`: agent produced a final answer
- `max_steps` / `budget_steps`: hit step budget
- `budget_time`: hit runtime budget
- `budget_tokens`: hit token budget (model-side)
- `agent_condition`: `AgentModule.should_stop(...)` requested stop
- `critic_stop`: critic requested stop (if critic enabled)
- `stagnation`: stagnation detector stopped the run (if enabled)
- `env_terminal`: env indicated termination (e.g. container exited)
- `task_validation_failed`: Task/env_spec/budget invalid
- `env_capability_mismatch`: tools required ops groups not provided by Env
- `unrecoverable_error`: recovery policy stopped after non-recoverable failure

## How to set stop_reason correctly

Prefer setting stop reasons on the typed state:

```python
from qitos.core.errors import StopReason

state.set_stop(StopReason.FINAL, final_result="done")
```

Avoid ad-hoc strings: `StateSchema.validate()` enforces stop reasons must be one of `StopReason`.

## Source Index

- [qitos/core/errors.py](https://github.com/Qitor/qitos/blob/main/qitos/core/errors.py)
- [qitos/engine/recovery.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/recovery.py)
