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

## Parameters

- `task`: user task string.
- `return_state`: return structured engine result when `True`.
- `engine_kwargs`: forwarded to engine constructor.
- additional kwargs: forwarded to `init_state(...)`.
