# GAIA Benchmark Integration

## What is already supported

QitOS has a working GAIA adapter and runnable agent pipeline:

- Adapter: `qitos/benchmark/gaia.py`
- Canonical conversion: GAIA row -> `Task`
- Runtime: standard `Engine` loop (no benchmark-specific runtime fork)
- Example runner: `examples/real/open_deep_research_gaia_agent.py`

## Why this matters

You can evaluate agent designs with the same kernel used in product agents:

- same `AgentModule + Engine`
- same hooks/trace/qita inspection
- same env/tool abstractions

This keeps research and engineering on one path.

## Quick commands

### Run one GAIA sample

```bash
python examples/real/open_deep_research_gaia_agent.py \
  --workspace ./qitos_gaia_workspace \
  --gaia-download-snapshot \
  --gaia-split validation \
  --gaia-index 0
```

### Run a full split

```bash
python examples/real/open_deep_research_gaia_agent.py \
  --workspace ./qitos_gaia_workspace \
  --gaia-download-snapshot \
  --gaia-split validation \
  --run-all --concurrency 2 --resume
```

### Run only a subset window

```bash
python examples/real/open_deep_research_gaia_agent.py \
  --workspace ./qitos_gaia_workspace \
  --gaia-download-snapshot \
  --gaia-split validation \
  --run-all --start-index 100 --limit 50 --resume
```

## Output artifacts

- Per-task answer file in task workspace
- Standard run traces (manifest/events)
- Aggregate benchmark JSONL (in workspace root unless `--output-jsonl` is set)

Then inspect with:

```bash
qita board --logdir runs
```

## Source Index

- [qitos/benchmark/gaia.py](https://github.com/Qitor/qitos/blob/main/qitos/benchmark/gaia.py)
- [examples/real/open_deep_research_gaia_agent.py](https://github.com/Qitor/qitos/blob/main/examples/real/open_deep_research_gaia_agent.py)
