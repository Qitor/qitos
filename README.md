# QitOS

![QitOS Logo](assets/logo.png)

[![Python](https://img.shields.io/badge/python-3.9%2B-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](https://github.com/Qitor/qitos)
[![Docs](https://img.shields.io/badge/docs-online-0A66C2)](https://qitor.github.io/qitos/)
[![Repo](https://img.shields.io/badge/github-Qitor%2Fqitos-black)](https://github.com/Qitor/qitos)

**QitOS is a research-first agentic framework with one canonical kernel:**
`AgentModule + Engine`.

It is designed for researchers and advanced builders who need:
- full control of agent scaffolding,
- fast iteration on new agent designs,
- reproducible experiments with clear traces.
- benchmark-ready evaluation loops (GAIA already adapted).

- Chinese README: [README.zh.md](README.zh.md)
- Docs: [https://qitor.github.io/qitos/](https://qitor.github.io/qitos/)
- Repository: [https://github.com/Qitor/qitos](https://github.com/Qitor/qitos)

## Why QitOS

1. **One execution mainline, zero architecture ambiguity**
- `observe -> decide -> act -> reduce -> check_stop`
- no Runtime-vs-Engine split
- no hidden policy layer competing with `AgentModule`

2. **Modular without fragmentation**
- `qitos.core`: contracts
- `qitos.engine`: runtime kernel
- `qitos.kit`: concrete reusable implementations
- `qitos.benchmark`: external benchmark adapters -> canonical `Task`

3. **Research velocity**
- quickly implement ReAct, PlanAct, ToT, Reflexion, SWE-style loops
- benchmark adapters (e.g., GAIA) integrate through `Task` conversion

4. **Serious observability**
- standardized run traces
- hook system across lifecycle phases
- `qita` for board/view/replay/export

## Architecture Snapshot

```text
Task -> Engine.run(...)
      -> observe -> decide -> act -> reduce -> check_stop -> ...
      -> hooks + trace + qita replay
```

## Install

```bash
pip install -e .
```

Optional extras (if needed):

```bash
pip install -e ".[models,yaml]"
```

## Quick Start

### 1) Minimal kernel smoke test

```bash
python examples/quickstart/minimal_agent.py
```

### 2) Run an LLM-backed ReAct agent

```bash
export OPENAI_BASE_URL="https://api.siliconflow.cn/v1/"
export OPENAI_API_KEY="<your_api_key>"

python examples/patterns/react.py --workspace ./playground
```

### 3) Inspect runs with qita

```bash
qita board --logdir runs
```

## Product UI Snapshots

### QitOS CLI render

![QitOS CLI](assets/qitos_cli_snapshot.png)

### qita board

![qita board](assets/qita_board_snapshot.png)

### qita trajectory view

![qita trajectory view](assets/qita_traj_snapshot.png)

### 4) Run GAIA with the QitOS benchmark adapter

Single sample:

```bash
python examples/real/open_deep_research_gaia_agent.py \
  --workspace ./qitos_gaia_workspace \
  --gaia-download-snapshot \
  --gaia-split validation \
  --gaia-index 0
```

Full split (with resume):

```bash
python examples/real/open_deep_research_gaia_agent.py \
  --workspace ./qitos_gaia_workspace \
  --gaia-download-snapshot \
  --gaia-split validation \
  --run-all --concurrency 2 --resume
```

## Minimal Authoring Example

```python
from dataclasses import dataclass
from qitos import AgentModule, StateSchema, Decision, Action, Engine, ToolRegistry, tool

@dataclass
class MyState(StateSchema):
    pass

class MyAgent(AgentModule[MyState, dict, Action]):
    def __init__(self):
        reg = ToolRegistry()

        @tool(name="add")
        def add(a: int, b: int) -> int:
            return a + b

        reg.register(add)
        super().__init__(tool_registry=reg)

    def init_state(self, task: str, **kwargs):
        return MyState(task=task, max_steps=3)

    def observe(self, state, env_view):
        return {"task": state.task, "step": state.current_step}

    def decide(self, state, observation):
        if state.current_step == 0:
            return Decision.act(actions=[Action(name="add", args={"a": 19, "b": 23})])
        return Decision.final("done")

    def reduce(self, state, observation, decision, action_results):
        return state

result = Engine(agent=MyAgent()).run("compute 19+23")
print(result.state.final_result)
```

## Real Examples

- Pattern agents:
  - `python examples/patterns/react.py --workspace /tmp/qitos_react`
  - `python examples/patterns/planact.py --workspace /tmp/qitos_planact`
  - `python examples/patterns/tot.py --workspace /tmp/qitos_tot`
  - `python examples/patterns/reflexion.py --workspace /tmp/qitos_reflexion`
- Practical agents:
  - `python examples/real/coding_agent.py --workspace /tmp/qitos_coding`
  - `python examples/real/swe_agent.py --workspace /tmp/qitos_swe`
  - `python examples/real/computer_use_agent.py --workspace /tmp/qitos_computer`
  - `python examples/real/epub_reader_agent.py --workspace /tmp/qitos_epub`
  - `python examples/real/open_deep_research_gaia_agent.py --workspace /tmp/qitos_gaia --gaia-from-local`

## Benchmark Integration

QitOS uses a clean benchmark adapter path:

- External dataset row
- `qitos.benchmark.*Adapter`
- Canonical `Task`
- Standard `Engine` run loop

Current GAIA integration:
- adapter: `qitos/benchmark/gaia.py`
- runnable example: `examples/real/open_deep_research_gaia_agent.py`

## Predefined Kit Catalog (Torch-style)

QitOS ships reusable building blocks in `qitos.kit`, so users can compose instead of rewriting.

### `qitos.kit.tool` (predefined tool packages)

- Editor bundle:
  - `EditorToolSet` (`view`, `create`, `str_replace`, `insert`, `search`, `list_tree`, `replace_lines`)
- EPUB bundle:
  - `EpubToolSet` (`list_chapters`, `read_chapter`, `search`)
- File tools:
  - `WriteFile`, `ReadFile`, `ListFiles`
- Process tool:
  - `RunCommand`
- HTTP/Web tools:
  - `HTTPRequest`, `HTTPGet`, `HTTPPost`, `HTMLExtractText`
- Text-browser tools (for GAIA/OpenDeepResearch-style loops):
  - `WebSearch`, `VisitURL`, `PageDown`, `PageUp`, `FindInPage`, `FindNext`, `ArchiveSearch`
- Thinking toolset:
  - `ThinkingToolSet`, `ThoughtData`
- Tool library:
  - `InMemoryToolLibrary`, `ToolArtifact`, `BaseToolLibrary`
- Registry builders:
  - `math_tools()`, `editor_tools(workspace_root)`

### `qitos.kit.planning` (predefined planning primitives)

- LLM orchestration blocks:
  - `ToolAwareMessageBuilder`, `LLMDecisionBlock`
- Plan utilities:
  - `PlanCursor`, `parse_numbered_plan`
- Search strategies:
  - `GreedySearch`, `DynamicTreeSearch`
- State ops helpers:
  - `append_log`, `format_action`, `set_final`, `set_if_empty`

Quick import:

```python
from qitos.kit.tool import EditorToolSet, RunCommand, HTTPGet, ThinkingToolSet
from qitos.kit.planning import DynamicTreeSearch, PlanCursor, LLMDecisionBlock
```

## Core Package Map

- Contracts:
  - `qitos/core/agent_module.py`
  - `qitos/core/task.py`
  - `qitos/core/env.py`
  - `qitos/core/memory.py`
  - `qitos/core/tool.py`
  - `qitos/core/tool_registry.py`
- Runtime:
  - `qitos/engine/engine.py`
  - `qitos/engine/action_executor.py`
  - `qitos/engine/hooks.py`
- Reusable implementations:
  - `qitos/kit/*`
- Benchmarks:
  - `qitos/benchmark/*`

## Documentation

- Docs home: [https://qitor.github.io/qitos/](https://qitor.github.io/qitos/)
- Kernel architecture:
  - [English](https://qitor.github.io/qitos/research/kernel/)
  - [中文](https://qitor.github.io/qitos/zh/research/kernel/)
- 30-min labs:
  - [English](https://qitor.github.io/qitos/research/labs/)
  - [中文](https://qitor.github.io/qitos/zh/research/labs/)
- API reference (auto-generated from `qitos/*`):
  - [English](https://qitor.github.io/qitos/reference/api_generated/)
  - [中文](https://qitor.github.io/qitos/zh/reference/api_generated/)

## Local Docs

```bash
pip install -r docs/requirements.txt
mkdocs serve
```

Docs generation note:
- API pages are generated by `docs/hooks.py` into:
  - `docs/reference/api_generated/`
  - `docs/zh/reference/api_generated/`

## Contributing Direction

QitOS is optimized for one long-term objective:
- become a world-class open-source agentic Python framework for researchers and super-developers.

Before adding new abstractions, ensure they improve:
- composability,
- lifecycle clarity,
- reproducibility,
- developer ergonomics.
