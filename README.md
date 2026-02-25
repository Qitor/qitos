# QitOS

![QitOS Logo](assets/logo.png)

[![Python](https://img.shields.io/badge/python-3.9%2B-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-qitor.github.io/qitos-0A66C2)](https://qitor.github.io/qitos/)
[![PyPI](https://img.shields.io/pypi/v/qitos.svg)](https://pypi.org/project/qitos/)
[![Repo](https://img.shields.io/badge/github-Qitor%2Fqitos-black)](https://github.com/Qitor/qitos)

**QitOS is a research-first framework for building serious LLM agents.**  
It gives you one clean execution kernel, composable modules, and benchmark-ready workflows so you can move from idea to reproducible results without rewriting your stack.

- 中文 README: [README.zh.md](README.zh.md)
- Documentation: [https://qitor.github.io/qitos/](https://qitor.github.io/qitos/)

## Why Teams Choose QitOS

- **Research-first by design**: built for rapid iteration on ReAct, Plan-Act, ToT, Reflexion, and custom scaffolds.
- **One canonical kernel**: `AgentModule + Engine` with a stable lifecycle that is easy to reason about and extend.
- **Modular architecture**: use only what you need from `core`, `engine`, `kit`, `benchmark`, and `evaluate`.
- **Ecosystem compatibility**: works naturally with OpenAI-compatible model APIs, host environments, and tool registries.
- **Benchmark-native workflow**: unified adapters for GAIA, Tau-Bench, and CyBench.
- **Production-grade observability**: traces, hooks, replay, and export via `qita`.

## Core Advantage

```text
Task -> Engine.run(...)
     -> prepare -> decide -> act -> reduce -> check_stop -> ...
     -> hooks + trace + replay + metrics
```

One architecture for research, evaluation, and real deployment.

## Install

```bash
pip install qitos
```

Development:

```bash
pip install -e .
pip install -e ".[models,yaml,benchmarks]"
```

## Quick Start

Run a minimal end-to-end flow:

```bash
python examples/quickstart/minimal_agent.py
```

Run a pattern-based agent:

```bash
export OPENAI_BASE_URL="https://api.siliconflow.cn/v1/"
export OPENAI_API_KEY="<your_api_key>"
python examples/patterns/react.py --workspace ./playground
```

Inspect trajectories:

```bash
qita board --logdir runs
```

## What You Can Build

Agent patterns:
- `examples/patterns/react.py`
- `examples/patterns/planact.py`
- `examples/patterns/tot.py`
- `examples/patterns/reflexion.py`

Real scenarios:
- `examples/real/coding_agent.py`
- `examples/real/swe_agent.py`
- `examples/real/computer_use_agent.py`
- `examples/real/epub_reader_agent.py`

## Benchmark and Evaluation

QitOS standardizes the path:

`dataset row -> adapter -> Task -> Engine -> evaluate -> metric report`

Built-in adapters:
- `qitos.benchmark.gaia`
- `qitos.benchmark.tau_bench`
- `qitos.benchmark.cybench`

Evaluation stack:
- `qitos.evaluate` for per-task outcome judgment
- `qitos.metric` for benchmark-level reporting
- `qitos.kit` with rule-based / DSL-based / model-based evaluators and common metrics

## Observability with qita

- `qita board`: run overview and summary
- `qita view`: structured trajectory inspection
- `qita replay`: execution playback
- `qita export`: JSON / HTML artifact export

## Project Structure

- `qitos/core/`: interfaces and contracts
- `qitos/engine/`: execution kernel
- `qitos/kit/`: reusable modules (tools, parsers, planning, memory, eval)
- `qitos/benchmark/`: benchmark adapters
- `qitos/qita/`: trajectory tooling

## Docs

- Main docs: [https://qitor.github.io/qitos/](https://qitor.github.io/qitos/)
- API reference: [https://qitor.github.io/qitos/reference/api_generated/](https://qitor.github.io/qitos/reference/api_generated/)
- Chinese docs: [https://qitor.github.io/qitos/zh/](https://qitor.github.io/qitos/zh/)

## License

MIT. See [LICENSE](LICENSE).
