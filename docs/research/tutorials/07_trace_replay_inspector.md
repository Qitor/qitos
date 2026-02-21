# 07 Trace, Replay, Inspector

## Why This Is Core for Research

A claim about an agent strategy is only convincing if others can replay and inspect the same run.

## What To Capture

- decisions and rationale
- actions and tool I/O
- state diff per step
- stop reason
- reproducibility metadata (`model_id`, `prompt_hash`, `tool_versions`, `seed`)

## Workflow

1. Attach a `TraceWriter` to your `Engine` run.
2. Produce `manifest.json`, `events.jsonl`, `steps.jsonl`.
3. Replay with `ReplaySession`.
4. Build inspector payloads for side-by-side run analysis.

## References

- `/Users/morinop/coding/yoga_framework/qitos/trace/writer.py`
- `/Users/morinop/coding/yoga_framework/qitos/debug/replay.py`
- `/Users/morinop/coding/yoga_framework/qitos/debug/inspector.py`
- `/Users/morinop/coding/yoga_framework/docs/inspector_schema.md`

## Research Habit

Before changing policy logic, keep a baseline trace set. Compare new runs against the baseline on both quality and behavior shifts (not only final success rate).
