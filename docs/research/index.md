# Research Overview

## Goal

Use QitOS as a research kernel to:

1. Reproduce classic and recent agent patterns quickly.
2. Isolate one variable per experiment (parser/planning/memory/critic/env).
3. Compare methods under a consistent runtime contract.

## Prerequisites

- Python 3.10+
- Basic familiarity with ReAct/PlanAct/ToT/Reflexion ideas
- This repository installed in editable mode

```bash
pip install -e .
```

## Suggested reading order

1. [Kernel Architecture](kernel.md)
2. [Kernel Deep Dive](kernel_deep_dive.md)
3. [Reproduce Paper Agents](reproduce.md)
4. [Design New Agents](design.md)
5. [Author New Agent Modules](agent_authoring.md)
6. [Trace & Evaluation](trace_eval.md)
7. [30-Min Labs](labs/index.md)

## First research loop (30 minutes)

1. Run baseline pattern:

```bash
python examples/patterns/react.py
```

2. Run another pattern on similar tasks:

```bash
python examples/patterns/planact.py
```

3. Compare generated traces in your run directory (for example `runs/` or `examples/runs/`).

4. Record differences in:
- stop reason
- step count
- error category distribution
- final answer quality

## Researcher checklist

1. Keep tasks fixed while changing one design axis.
2. Keep budgets fixed (`max_steps`, `max_runtime_seconds`, `max_tokens`).
3. Track parser and prompt changes explicitly.
4. Store run IDs and manifests for later regression analysis.

## Source Index

- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
- [examples/patterns/planact.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/planact.py)
- [examples/patterns/reflexion.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/reflexion.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [qitos/trace/writer.py](https://github.com/Qitor/qitos/blob/main/qitos/trace/writer.py)
