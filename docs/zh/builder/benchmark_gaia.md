# GAIA Benchmark 适配与运行

## 当前已支持

QitOS 已完成 GAIA 的可运行适配链路：

- 适配器：`qitos/benchmark/gaia/adapter.py`
- 标准转换：GAIA 样本 -> `Task`
- 执行内核：统一 `Engine` 循环（不做 benchmark 特化 runtime）
- 示例入口：`examples/real/open_deep_research_gaia_agent.py`

## 价值

你可以用与生产 Agent 相同的内核做 benchmark：

- 相同 `AgentModule + Engine`
- 相同 hooks/trace/qita 观测方式
- 相同 env/tool 抽象

研究到落地不需要切换框架路径。

## 快速命令

### 跑单题

```bash
python examples/real/open_deep_research_gaia_agent.py \
  --workspace ./qitos_gaia_workspace \
  --gaia-download-snapshot \
  --gaia-split validation \
  --gaia-index 0
```

### 跑整集合

```bash
python examples/real/open_deep_research_gaia_agent.py \
  --workspace ./qitos_gaia_workspace \
  --gaia-download-snapshot \
  --gaia-split validation \
  --run-all --concurrency 2 --resume
```

### 跑区间子集

```bash
python examples/real/open_deep_research_gaia_agent.py \
  --workspace ./qitos_gaia_workspace \
  --gaia-download-snapshot \
  --gaia-split validation \
  --run-all --start-index 100 --limit 50 --resume
```

## 产物说明

- 每个 task 的答案文件（在对应 task workspace）
- 标准 run traces（manifest/events）
- 聚合 benchmark JSONL（默认在 workspace 根目录，可用 `--output-jsonl` 指定）

完成后可用：

```bash
qita board --logdir runs
```

## Source Index

- [qitos/benchmark/gaia/adapter.py](https://github.com/Qitor/qitos/blob/main/qitos/benchmark/gaia/adapter.py)
- [examples/real/open_deep_research_gaia_agent.py](https://github.com/Qitor/qitos/blob/main/examples/real/open_deep_research_gaia_agent.py)
