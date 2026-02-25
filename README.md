# QitOS

![QitOS Logo](assets/logo.png)

[![Python](https://img.shields.io/badge/python-3.9%2B-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Docs](https://img.shields.io/badge/docs-qitor.github.io/qitos-0A66C2)](https://qitor.github.io/qitos/)
[![PyPI](https://img.shields.io/pypi/v/qitos.svg)](https://pypi.org/project/qitos/)
[![Repo](https://img.shields.io/badge/github-Qitor%2Fqitos-black)](https://github.com/Qitor/qitos)

QitOS is a **research-first agent framework** built around one canonical kernel:

> **AgentModule + Engine**

It is designed for researchers and advanced builders who need to:
- design new agentic scaffolding quickly,
- control every important runtime detail,
- run reproducible benchmark experiments,
- inspect trajectories with production-grade observability.

- Chinese README: [README.zh.md](README.zh.md)
- Documentation: [https://qitor.github.io/qitos/](https://qitor.github.io/qitos/)

---

## Why QitOS

### 1) One Mainline, No Ambiguity
QitOS enforces one runtime lifecycle:

`prepare -> decide -> act -> reduce -> check_stop`

No parallel architecture tracks. No hidden policy layer competing with your agent code.

### 2) Explicit Separation of Concerns
QitOS treats **Memory** and **History** as different primitives:
- `memory`: trajectory artifacts (`task/state/decision/action/observation/next_state/...`)
- `history`: model-facing messages (`system/user/assistant/...`)

This keeps agent research clean and avoids context coupling mistakes.

### 3) Modular, Not Fragmented
- `qitos.core`: contracts
- `qitos.engine`: execution kernel
- `qitos.kit`: reusable implementations
- `qitos.benchmark`: benchmark adapters to canonical `Task`
- `qitos.evaluate` + `qitos.metric`: evaluation and reporting

### 4) Observability as a First-Class Feature
- standardized run traces
- full hook system across lifecycle phases
- `qita` for board / view / replay / export

### 5) Benchmark-Native by Design
Integrated adapters for:
- GAIA
- Tau-Bench
- CyBench

---

## Architecture Snapshot

```text
Task -> Engine.run(...)
     -> prepare -> decide -> act -> reduce -> check_stop -> ...
     -> hooks + trace + qita replay
```

---

## Installation

```bash
pip install qitos
```

Development mode:

```bash
pip install -e .
```

Optional extras:

```bash
pip install -e ".[models,yaml,benchmarks]"
```

---

## Quick Start

### 1) Minimal kernel smoke test

```bash
python examples/quickstart/minimal_agent.py
```

### 2) Run an LLM-backed ReAct pattern

```bash
export OPENAI_BASE_URL="https://api.siliconflow.cn/v1/"
export OPENAI_API_KEY="<your_api_key>"

python examples/patterns/react.py --workspace ./playground
```

### 3) Inspect trajectories with qita

```bash
qita board --logdir runs
```

---

## Minimal SWE Agent (Requirement-to-PR style)

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
- Produce PR-ready results with concrete validation evidence.

Rules:
1. Follow ReAct strictly: Thought -> one Action -> observe -> iterate.
2. Exactly one tool call per step.
3. Read relevant code before editing.
4. Prefer small, reversible patches.
5. Do not claim success without test/command evidence.

Output format:
Thought: <reasoning>
Action: <tool_name>(...)
Final Answer: <requirement coverage + changed files + validation + remaining risks>
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
        return None  # Engine model path: prepare -> llm -> parser

    def prepare(self, state: SWEState) -> str:
        records = self.memory.retrieve(query={"max_items": 8}) if self.memory else []
        return (
            f"Task: {state.task}\n"
            f"Target file: {state.target_file}\n"
            f"Test command: {state.test_command}\n"
            f"Step: {state.current_step}/{state.max_steps}\n"
            f"Recent memory: {records[-3:]}"
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
                state.final_result = "Requirement implemented and validation command passed."
        state.scratchpad = state.scratchpad[-40:]
        return state


# llm = ...
# agent = MinimalSWEAgent(llm=llm, workspace_root="./playground")
# task = Task(
#     id="swe_minimal",
#     objective="Implement the new requirement and make checks pass.",
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

---

## Real Examples

Pattern examples:
- `python examples/patterns/react.py --workspace /tmp/qitos_react`
- `python examples/patterns/planact.py --workspace /tmp/qitos_planact`
- `python examples/patterns/tot.py --workspace /tmp/qitos_tot`
- `python examples/patterns/reflexion.py --workspace /tmp/qitos_reflexion`

Practical examples:
- `python examples/real/coding_agent.py --workspace /tmp/qitos_coding`
- `python examples/real/swe_agent.py --workspace /tmp/qitos_swe`
- `python examples/real/computer_use_agent.py --workspace /tmp/qitos_computer`
- `python examples/real/epub_reader_agent.py --workspace /tmp/qitos_epub`
- `python examples/real/open_deep_research_gaia_agent.py --workspace /tmp/qitos_gaia --gaia-from-local`

---

## Benchmarks

QitOS benchmark path is standardized:

`dataset row -> adapter -> Task -> Engine`

Implemented adapters:
- `qitos.benchmark.gaia`
- `qitos.benchmark.tau_bench` (self-contained port)
- `qitos.benchmark.cybench`

Examples:
- `examples/real/open_deep_research_gaia_agent.py`
- `examples/real/tau_bench_eval.py`
- `examples/real/cybench_eval.py`

---

## Evaluation & Metrics

QitOS separates:
- **trajectory evaluation** (`qitos.evaluate`) for per-task success judgement
- **metric aggregation** (`qitos.metric`) for benchmark-level reporting

Pre-implemented in `qitos.kit`:
- evaluators: rule-based, DSL-based, model-based
- metrics: success rate, average reward, pass@k, mean steps, stop-reason distribution

---

## qita Observability

QitOS includes `qita` to inspect run quality quickly:
- board: run discovery + summary stats
- view: structured trajectory page
- replay: browser replay of agent execution
- export: raw JSON / rendered HTML

```bash
qita board --logdir runs
```

---

## Project Layout

- `qitos/core/`: contracts (`AgentModule`, `Task`, `Env`, `Memory`, `History`, `ToolRegistry`)
- `qitos/engine/`: canonical runtime kernel
- `qitos/kit/`: reusable tool/memory/parser/planning/eval implementations
- `qitos/benchmark/`: benchmark adapters
- `qitos/qita/`: trace UI tooling

---

## Documentation

- Main docs: [https://qitor.github.io/qitos/](https://qitor.github.io/qitos/)
- API reference: [https://qitor.github.io/qitos/reference/api_generated/](https://qitor.github.io/qitos/reference/api_generated/)
- Chinese docs: [https://qitor.github.io/qitos/zh/](https://qitor.github.io/qitos/zh/)

---

## License

MIT. See [LICENSE](LICENSE).
