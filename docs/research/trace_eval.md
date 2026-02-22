# Trace & Evaluation

## Goal

Turn runtime traces into comparable experiment evidence.

## What to capture per run

1. Task metadata.
2. Model/parser/tool metadata.
3. Phase events with `run_id`, `step_id`, `phase`, `ts`, `ok`.
4. Stop reason and final result.
5. Failure report when errors happen.

## Tutorial: quick regression gate

1. Prepare a small task set (5-20 tasks) using `Task`.
2. Run baseline implementation and collect run summaries.
3. Run candidate implementation with same budgets and env.
4. Compare:
- success rate
- average step count
- top failure categories
- token/runtime budget pressure

5. Fail the change if success drops or failure categories regress.

## Suggested metrics table template

| Metric | Baseline | Candidate | Delta |
|---|---:|---:|---:|
| Success rate |  |  |  |
| Avg steps |  |  |  |
| Unrecoverable error ratio |  |  |  |
| Budget stop ratio |  |  |  |

## Practical tip

Do not compare only final answer quality. Always combine quality + cost + stability metrics.

## Source Index

- [qitos/trace/events.py](https://github.com/Qitor/qitos/blob/main/qitos/trace/events.py)
- [qitos/trace/schema.py](https://github.com/Qitor/qitos/blob/main/qitos/trace/schema.py)
- [qitos/trace/writer.py](https://github.com/Qitor/qitos/blob/main/qitos/trace/writer.py)
- [qitos/render/hooks.py](https://github.com/Qitor/qitos/blob/main/qitos/render/hooks.py)
- [qitos/qita/cli.py](https://github.com/Qitor/qitos/blob/main/qitos/qita/cli.py)
