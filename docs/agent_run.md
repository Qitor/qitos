# Agent Run

## Default Path

Use `agent.run(...)` as the default execution entrypoint.

```python
result = agent.run("compute 40 + 2")
```

Return the final answer string by default.

## Structured Return

```python
result = agent.run("compute 40 + 2", return_state=True)
print(result.state.final_result)
```

## Explicit Engine Path

For advanced control, build and run engine directly:

```python
engine = agent.build_engine()
result = engine.run("compute 40 + 2")
```

Both paths must follow canonical runtime semantics.

## Hook System

Engine exposes a runtime hook pipeline for advanced users.

```python
from qitos.engine.hooks import EngineHook


class MyHook(EngineHook):
    def on_after_decide(self, ctx, engine):
        print("decision:", ctx.decision)

    def on_after_act(self, ctx, engine):
        print("action_results:", ctx.action_results)


engine = agent.build_engine()
engine.register_hook(MyHook())
result = engine.run("compute 40 + 2")
```

You can also pass hooks from `agent.run(...)`:

```python
result = agent.run("compute 40 + 2", hooks=[MyHook()], return_state=True)
```

For built-in rich terminal visualization:

```python
from qitos.render import ClaudeStyleHook

result = agent.run("compute 40 + 2", hooks=[ClaudeStyleHook()], return_state=True)
```

`HookContext` includes:
- `task`, `step_id`, `phase`
- `state`, `env_view`
- `observation`, `decision`, `action_results`
- `record`, `payload`, `error`, `stop_reason`

Useful callbacks:
- `on_before_observe` / `on_after_observe`
- `on_before_decide` / `on_after_decide`
- `on_before_act` / `on_after_act`
- `on_before_reduce` / `on_after_reduce`
- `on_before_critic` / `on_after_critic`
- `on_before_check_stop` / `on_after_check_stop`
- `on_recover`

For frontend pipelines, use:
- `RenderStreamHook(output_jsonl="...")`
- it emits structured `RenderEvent` entries (`plan`, `thinking`, `action`, `memory`, `observation`, `critic`, `done`).

## Parameters

- `task`: user task string.
- `return_state`: return structured engine result when `True`.
- `engine_kwargs`: forwarded to engine constructor.
- additional kwargs: forwarded to `init_state(...)`.
