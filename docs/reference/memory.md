# Memory

## Goal

Clarify memory ownership and usage in QitOS.

## Ownership

Memory belongs to `AgentModule` (`self.memory`).

- Prefer passing memory at agent construction.

## Memory contract

`Memory` provides:

- `append(record)`
- `retrieve(query, state, observation)`
- `summarize(max_items)`
- `reset(run_id)`

## How memory is used

1. During runtime, Engine appends relevant records to `agent.memory`.
2. In custom agents, you can read memory directly in `prepare(state)`.

Typical memory stream:

- `task`
- `state`
- `decision`
- `action`
- `observation`
- `next_state`
- ...

## Important boundary

`observation` should not embed memory by default.

- `observation` is for world/action/env outputs of the step.
- memory should be consumed explicitly from `self.memory`.

## Example

```python
class MyAgent(...):
    def prepare(self, state):
        records = []
        if self.memory is not None:
            records = self.memory.retrieve(state=state, observation=None, query={"roles": ["observation"], "max_items": 8})
        return f"Task: {state.task}\nRecords: {records[-4:]}"
```

## Source Index

- [qitos/core/memory.py](https://github.com/Qitor/qitos/blob/main/qitos/core/memory.py)
- [qitos/kit/memory/window_memory.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/memory/window_memory.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
