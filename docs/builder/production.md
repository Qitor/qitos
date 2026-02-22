# Production Guide

## Goal

Move from prototype to stable service behavior.

## P0 safeguards

1. Budget limits configured (`steps`, `runtime`, `tokens`).
2. Stop reasons monitored.
3. Trace persisted for every production run.
4. Failure report retained for debugging.

## Suggested deployment checklist

1. Pin model + parser versions.
2. Add regression taskset (small but representative).
3. Run daily/PR regression with threshold gates.
4. Add runtime dashboards from trace summaries.

## Incident debugging playbook

1. Locate failing `run_id`.
2. Read `manifest.summary.stop_reason`.
3. Find first `ok=false` event in `events.jsonl`.
4. Inspect corresponding step in `steps.jsonl`.
5. Classify root cause:
- parser robustness
- tool input schema
- env capability/config
- model output drift

## Guardrails worth adding early

1. Strict parser mode for critical actions.
2. Tool allowlist per agent.
3. Max retries per action.
4. Safety filters for shell/web tools.

## Source Index

- [qitos/engine/stop_criteria.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/stop_criteria.py)
- [qitos/engine/recovery.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/recovery.py)
- [qitos/engine/hooks.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/hooks.py)
- [qitos/trace/schema.py](https://github.com/Qitor/qitos/blob/main/qitos/trace/schema.py)
- [qitos/qita/cli.py](https://github.com/Qitor/qitos/blob/main/qitos/qita/cli.py)
