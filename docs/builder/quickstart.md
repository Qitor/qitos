# Quickstart

## Goal

Run your first QitOS agent and inspect one complete execution.

## Prerequisites

```bash
pip install -e .
```

Model/API configuration first:

- [Configuration & API Keys](configuration.md)

## Step 1: run minimal example

```bash
python examples/quickstart/minimal_agent.py
```

Expected:

- terminal output with final result
- step execution through Engine phases

## Step 2: run a pattern example

```bash
python examples/patterns/react.py
```

Then try:

```bash
python examples/patterns/planact.py
```

If you want to understand *why these examples are written this way* (method-by-method), read:

- [Example Walkthroughs](../tutorials/examples/index.md)

## Step 3: inspect traces

If your example writes to run artifacts, inspect:

- `runs/<run_id>/manifest.json`
- `runs/<run_id>/events.jsonl`
- `runs/<run_id>/steps.jsonl`

## Step 4: open board UI

```bash
qita board --logdir runs
```

Then continue with:

- [qita Guide](qita.md)

## Common issues

1. Model call not triggered:
- check if your `decide` always returns `Decision`; returning `None` is required for engine-driven LLM path.

2. No action executed:
- ensure your parser returns `Decision.act(...)` with valid action names.

3. Env capability mismatch:
- ensure selected `Env` supports tool-required ops groups.

## Source Index

- [examples/quickstart/minimal_agent.py](https://github.com/Qitor/qitos/blob/main/examples/quickstart/minimal_agent.py)
- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
- [qitos/qita/cli.py](https://github.com/Qitor/qitos/blob/main/qitos/qita/cli.py)
- [qitos/render/hooks.py](https://github.com/Qitor/qitos/blob/main/qitos/render/hooks.py)
