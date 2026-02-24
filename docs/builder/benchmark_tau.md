# Tau-Bench Integration

## What is supported

QitOS supports Tau-Bench through a canonical adapter path:

- Adapter: `qitos/benchmark/tau_bench/adapter.py`
- Self-contained runtime: `qitos/benchmark/tau_bench/runtime.py` + `qitos/benchmark/tau_bench/port/*`
- Conversion: Tau task -> `qitos.core.task.Task`
- Eval runner: `examples/real/tau_bench_eval.py`

No external `tau_bench` python package is required.

## Why this matters

You can evaluate agent scaffolds with the same QitOS kernel and observability stack:

- same `AgentModule + Engine`
- same trace/qita workflow
- same evaluate + metric interfaces

## Quick commands

### Single task

```bash
python examples/real/tau_bench_eval.py \
  --workspace ./qitos_tau_workspace \
  --tau-env retail --tau-split test \
  --task-index 0
```

### Full eval

```bash
python examples/real/tau_bench_eval.py \
  --workspace ./qitos_tau_workspace \
  --tau-env retail --tau-split test \
  --run-all --num-trials 1 --concurrency 4 --resume
```

### Pass@k-style repeated trials

```bash
python examples/real/tau_bench_eval.py \
  --workspace ./qitos_tau_workspace \
  --tau-env retail --tau-split test \
  --run-all --num-trials 3 --concurrency 6 --resume
```

## Output

- per-run JSONL records
- aggregate metrics (success rate, avg reward, pass@k, etc.)
- standard traces for qita inspection

## Source Index

- [qitos/benchmark/tau_bench/adapter.py](https://github.com/Qitor/qitos/blob/main/qitos/benchmark/tau_bench/adapter.py)
- [examples/real/tau_bench_eval.py](https://github.com/Qitor/qitos/blob/main/examples/real/tau_bench_eval.py)
- [qitos/evaluate/base.py](https://github.com/Qitor/qitos/blob/main/qitos/evaluate/base.py)
- [qitos/metric/base.py](https://github.com/Qitor/qitos/blob/main/qitos/metric/base.py)
