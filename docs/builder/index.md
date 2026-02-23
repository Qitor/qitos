# Builder Overview

## Goal

Get a useful agent running fast, then integrate it safely into your own system.

## Who this is for

- Engineers shipping agent features.
- Students building course or lab projects.
- Teams that need predictable runtime behavior instead of demo-only flows.

## 60-minute path

1. [Quickstart](quickstart.md)
2. [Configuration & API Keys](configuration.md)
3. [qita Guide](qita.md)
4. [Model Integration](model.md)
5. [From Core to Agent](from_core_to_agent.md)
6. [Tools & Env](tools_env.md)
7. [GAIA Benchmark Integration](benchmark_gaia.md)
8. [Tau-Bench Integration](benchmark_tau.md)
9. [Production Guide](production.md)

## Builder principles in QitOS

1. Start with one simple agent and one task shape.
2. Use `Task` and budgets from day one.
3. Keep tool contracts strict and testable.
4. Keep traces for every important run.

## Source Index

- [examples/quickstart/minimal_agent.py](https://github.com/Qitor/qitos/blob/main/examples/quickstart/minimal_agent.py)
- [examples/real/coding_agent.py](https://github.com/Qitor/qitos/blob/main/examples/real/coding_agent.py)
- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
