# Tau-Bench 适配

## 当前支持

QitOS 已支持 Tau-Bench 的标准接入链路：

- 适配器：`qitos/benchmark/tau_bench.py`
- 内置运行时：`qitos/benchmark/tau_runtime.py` + `qitos/benchmark/tau_port/*`
- 转换：Tau task -> `qitos.core.task.Task`
- 评测脚本：`examples/real/tau_bench_eval.py`

不依赖外部 `tau_bench` Python 包。

## 价值

你可以在统一的 QitOS 内核和观测链路下做评测：

- 同一套 `AgentModule + Engine`
- 同一套 trace/qita
- 同一套 evaluate + metric 接口

## 快速命令

### 单题

```bash
python examples/real/tau_bench_eval.py \
  --workspace ./qitos_tau_workspace \
  --tau-env retail --tau-split test \
  --task-index 0
```

### 全量

```bash
python examples/real/tau_bench_eval.py \
  --workspace ./qitos_tau_workspace \
  --tau-env retail --tau-split test \
  --run-all --num-trials 1 --concurrency 4 --resume
```

### 多次 trial（用于 pass@k）

```bash
python examples/real/tau_bench_eval.py \
  --workspace ./qitos_tau_workspace \
  --tau-env retail --tau-split test \
  --run-all --num-trials 3 --concurrency 6 --resume
```

## 输出

- 每条 task/trial 的 JSONL 记录
- 聚合指标（成功率、平均 reward、pass@k 等）
- 标准 trace（可直接用 qita 复盘）

## Source Index

- [qitos/benchmark/tau_bench.py](https://github.com/Qitor/qitos/blob/main/qitos/benchmark/tau_bench.py)
- [examples/real/tau_bench_eval.py](https://github.com/Qitor/qitos/blob/main/examples/real/tau_bench_eval.py)
- [qitos/evaluate/base.py](https://github.com/Qitor/qitos/blob/main/qitos/evaluate/base.py)
- [qitos/metric/base.py](https://github.com/Qitor/qitos/blob/main/qitos/metric/base.py)
