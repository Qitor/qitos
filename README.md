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
- benchmark-ready evaluation loops (GAIA/Tau-Bench/CyBench adapted).

- Chinese README: [README.zh.md](README.zh.md)
- Docs: [https://qitor.github.io/qitos/](https://qitor.github.io/qitos/)
- Repository: [https://github.com/Qitor/qitos](https://github.com/Qitor/qitos)

## Why QitOS

1. **One execution mainline, zero architecture ambiguity**
- `prepare -> decide -> act -> reduce -> check_stop`
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

5. **Evaluation-native benchmark workflow**
- `qitos.benchmark` adapters for GAIA, Tau-Bench, and CyBench
- `qitos.evaluate` for trajectory success judgement
- `qitos.metric` for benchmark-level reporting (success rate, pass@k, etc.)

## Architecture Snapshot

```text
Task -> Engine.run(...)
      -> prepare -> decide -> act -> reduce -> check_stop -> ...
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

### 5) Run Tau-Bench eval (single or full)

Single task:

```bash
python examples/real/tau_bench_eval.py \
  --workspace ./qitos_tau_workspace \
  --tau-env retail --tau-split test \
  --task-index 0
```

Full eval:

```bash
python examples/real/tau_bench_eval.py \
  --workspace ./qitos_tau_workspace \
  --tau-env retail --tau-split test \
  --run-all --num-trials 1 --concurrency 4 --resume
```

### 6) Run CyBench eval (single or full)

Single task (guided mode):

```bash
python examples/real/cybench_eval.py \
  --workspace ./qitos_cybench_workspace \
  --cybench-root ./references/cybench \
  --task-index 0
```

Full eval:

```bash
python examples/real/cybench_eval.py \
  --workspace ./qitos_cybench_workspace \
  --cybench-root ./references/cybench \
  --run-all --max-workers 2 --resume
```

## Minimal SWE-Agent Definition

```python
from dataclasses import dataclass, field
from typing import Any

from qitos import Action, AgentModule, Decision, Engine, EnvSpec, HistoryPolicy, StateSchema, Task, TaskBudget, ToolRegistry
from qitos.kit.env import HostEnv
from qitos.kit.history import WindowHistory
from qitos.kit.memory import MarkdownFileMemory
from qitos.kit.parser import ReActTextParser
from qitos.kit.tool.editor import EditorToolSet
from qitos.kit.tool.shell import RunCommand

SWE_REACT_SYSTEM_PROMPT = """
You are an expert software engineering agent.

Mission:
- Implement new requirements in the repository with minimal, correct, maintainable changes.
- Produce PR-ready results: what changed, why, and validation evidence.

Operating rules:
1. Use ReAct loop strictly: Think -> one Action -> observe -> repeat.
2. Do exactly one tool call per step.
3. Always inspect relevant code before editing.
4. Prefer small, reversible patches over broad rewrites.
5. Validate with tests or executable checks before finalizing.
6. If a check fails, diagnose and iterate; do not claim success.
7. Never fabricate command output, file content, or test results.

Output protocol (strict):
- Thought: concise reasoning and next intent.
- Action: tool_name(arg=value, ...)
- Final Answer: PR-ready result including:
  - Requirement implemented
  - Files changed + key diffs
  - Validation commands + outcomes
  - Remaining risks / follow-ups
"""

@dataclass
class SWEState(StateSchema):
    scratchpad: list[str] = field(default_factory=list)
    target_file: str = "buggy_module.py"
    test_command: str = 'python -c "import buggy_module; assert buggy_module.add(20, 22) == 42"'

class MinimalSWEAgent(AgentModule[SWEState, dict[str, Any], Action]):
    def __init__(self, llm: Any, workspace_root: str):
        reg = ToolRegistry()
        reg.include(EditorToolSet(workspace_root=workspace_root))
        reg.register(RunCommand(cwd=workspace_root))
        super().__init__(
            tool_registry=reg,
            llm=llm,
            model_parser=ReActTextParser(),
            memory=MarkdownFileMemory(path=f"{workspace_root}/memory.md"),
            history=WindowHistory(window_size=24),
        )

    def init_state(self, task: str, **kwargs: Any) -> SWEState:
        return SWEState(task=task, max_steps=int(kwargs.get("max_steps", 12)))

    def build_system_prompt(self, state: SWEState) -> str | None:
        tool_schema = self.tool_registry.get_tool_descriptions() if self.tool_registry else ""
        return f"{SWE_REACT_SYSTEM_PROMPT}\n\nAvailable tools:\n{tool_schema}"

    def decide(self, state: SWEState, observation: dict[str, Any]):
        return None  # use Engine model path: prepare -> llm -> parser

    def prepare(self, state: SWEState) -> str:
        mem = self.memory.retrieve(query={"max_items": 8}) if self.memory else []
        return (
            f"Task: {state.task}\n"
            f"Target file: {state.target_file}\n"
            f"Test command: {state.test_command}\n"
            f"Step: {state.current_step}/{state.max_steps}\n"
            f"Recent memory: {mem[-3:]}"
        )

    def reduce(self, state: SWEState, observation: dict[str, Any], decision: Decision[Action]) -> SWEState:
        if decision.rationale:
            state.scratchpad.append(f"Thought: {decision.rationale}")
        if decision.actions:
            state.scratchpad.append(f"Action: {decision.actions[0]}")
        results = observation.get("action_results", [])
        if results:
            state.scratchpad.append(f"Observation: {results[0]}")
            if isinstance(results[0], dict) and int(results[0].get("returncode", 1)) == 0:
                state.final_result = "Patch validated by test command."
        state.scratchpad = state.scratchpad[-40:]
        return state

# llm = ...  # your model adapter
# agent = MinimalSWEAgent(llm=llm, workspace_root="./playground")
# task = Task(
#     id="swe_minimal",
#     objective="Fix buggy_module.py and make the test pass.",
#     env_spec=EnvSpec(type="host", config={"workspace_root": "./playground"}),
#     budget=TaskBudget(max_steps=12),
# )
# result = Engine(
#     agent=agent,
#     env=HostEnv(workspace_root="./playground"),
#     history_policy=HistoryPolicy(max_messages=20),
# ).run(task)
# print(result.state.final_result, result.state.stop_reason)
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
- adapter: `qitos/benchmark/gaia/adapter.py`
- runnable example: `examples/real/open_deep_research_gaia_agent.py`

Current Tau-Bench integration:
- adapter: `qitos/benchmark/tau_bench/adapter.py`
- self-contained runtime: `qitos/benchmark/tau_bench/runtime.py` + `qitos/benchmark/tau_bench/port/*`
- runnable example: `examples/real/tau_bench_eval.py`

Current CyBench integration:
- adapter: `qitos/benchmark/cybench/adapter.py`
- runtime + scoring: `qitos/benchmark/cybench/runtime.py`
- runnable example: `examples/real/cybench_eval.py`

## Evaluate + Metric Architecture

QitOS separates success judgement from aggregate metrics:

- `qitos.evaluate`:
  - evaluates one trajectory against one task
  - returns structured `EvaluationResult` with evidence/reasons
- `qitos.metric`:
  - aggregates many task runs
  - returns benchmark reports (`success_rate`, `avg_reward`, `pass@k`, etc.)

Predefined implementations:
- evaluators in `qitos.kit.evaluate`:
  - `RuleBasedEvaluator`, `DSLEvaluator`, `ModelBasedEvaluator`
- metrics in `qitos.kit.metric`:
  - `SuccessRateMetric`, `AverageRewardMetric`, `PassAtKMetric`, `MeanStepsMetric`, `StopReasonDistributionMetric`

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
