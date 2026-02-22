# Trace & Hooks

## Goal

Use QitOS observability as a stable contract for research and production debugging.

## Hooks

Hooks receive canonical metadata and structured payloads:

- `run_id`, `step_id`, `phase`, `ts`
- `state_digest`, `decision_digest`, `action_digest`

In code, hooks are implemented by subclassing `EngineHook` and receiving a `HookContext` at each phase callback.

### Minimal hook example

```python
from qitos.engine import EngineHook

class PrintDecisions(EngineHook):
    def on_after_decide(self, ctx, engine) -> None:
        print(f"[{ctx.run_id}] step={ctx.step_id} phase={ctx.phase} decision={ctx.decision}")
```

### Attaching hooks

You can attach hooks either via `Engine(...)` or via `agent.run(..., hooks=[...])`:

```python
from qitos import Engine
from qitos.kit.env import HostEnv

engine = Engine(agent=my_agent, env=HostEnv(workspace_root="./playground"), hooks=[PrintDecisions()])
result = engine.run("do something")
```

## Trace artifacts

A run typically produces:

- `manifest.json`
- `events.jsonl`
- `steps.jsonl`

Trace is written by `TraceWriter` and is designed to be:

- append-only (`*.jsonl`) for large runs
- schema-versioned for long-term compatibility
- replayable (qita reads the same artifacts)

## qita

Use `qita` to view/replay/export traces:

- [qita Guide](../builder/qita.md)

## Source Index

- [qitos/engine/hooks.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/hooks.py)
- [qitos/trace/writer.py](https://github.com/Qitor/qitos/blob/main/qitos/trace/writer.py)
- [qitos/qita/cli.py](https://github.com/Qitor/qitos/blob/main/qitos/qita/cli.py)
