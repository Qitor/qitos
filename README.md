# QitOS

![QitOS Logo](assets/logo.png)

Research-first agentic framework with one canonical kernel:
`AgentModule + Engine`.

- Chinese README: [README.zh.md](README.zh.md)
- Docs: [https://qitor.github.io/QitOS/](https://qitor.github.io/QitOS/)
- Repository: [https://github.com/Qitor/qitos](https://github.com/Qitor/qitos)

## Why QitOS

- Single execution mainline for all agents: `observe -> decide -> act -> reduce -> check_stop`.
- Fast reproduction of research patterns: ReAct, PlanAct, ToT, Reflexion, SWE-style loops.
- Strong observability: hooks + standardized traces + `qita` board/view/replay/export.
- Modular composition: tools, env backends, memory, parser, critic, search.

## Install

```bash
pip install -e .
```

## Quick Start

Run a minimal kernel check:

```bash
python examples/quickstart/minimal_agent.py
```

Run an LLM-backed pattern agent:

```bash
export OPENAI_BASE_URL="https://api.siliconflow.cn/v1/"
export OPENAI_API_KEY="<your_api_key>"

python examples/patterns/react.py --workspace ./playground
```

Inspect runs:

```bash
qita board --logdir runs
```

## Core Design

- Policy contract: `qitos/core/agent_module.py`
- Runtime kernel: `qitos/engine/engine.py`
- Typed state: `qitos/core/state.py`
- Task + Env + Memory contracts:
  - `qitos/core/task.py`
  - `qitos/core/env.py`
  - `qitos/core/memory.py`
- Tool dispatch:
  - `qitos/core/tool.py`
  - `qitos/core/tool_registry.py`
  - `qitos/engine/action_executor.py`

## Documentation

- Docs home: [https://qitor.github.io/QitOS/](https://qitor.github.io/QitOS/)
- Kernel architecture:
  - [English](https://qitor.github.io/QitOS/research/kernel/)
  - [中文](https://qitor.github.io/QitOS/zh/research/kernel/)
- 30-min labs:
  - [English](https://qitor.github.io/QitOS/research/labs/)
  - [中文](https://qitor.github.io/QitOS/zh/research/labs/)
- Auto-generated API Reference (build-time synced from `qitos/*`):
  - [English](https://qitor.github.io/QitOS/reference/api_generated/)
  - [中文](https://qitor.github.io/QitOS/zh/reference/api_generated/)

## Local Docs Development

```bash
pip install -r docs/requirements.txt
mkdocs serve
```

Notes:

- The docs build uses `docs/hooks.py` to auto-generate API reference pages under:
  - `docs/reference/api_generated/`
  - `docs/zh/reference/api_generated/`

## GitHub Pages Deployment

The workflow file is:

- `.github/workflows/docs.yml`

It builds docs on push to `main` and deploys to GitHub Pages.
Target URL is:

- [https://qitor.github.io/QitOS/](https://qitor.github.io/QitOS/)
