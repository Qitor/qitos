# QitOS AGENTS.md

Working agreement for AI coding agents in this repository. Architecture knowledge lives in `ARCHITECTURE.md` and `docs/architecture/` — this file is the map, not the encyclopedia. Nested rules: `qitos/AGENTS.md` (package map), `qitos/core|engine|kit/AGENTS.md` (module rules).

## Repository Purpose

QitOS is a research-first agent framework ("the PyTorch of agents"): one canonical `AgentModule + Engine` kernel with the lifecycle `observe -> decide -> act -> reduce -> check_stop`, plus `qita` observability. Product-grade agents live out-of-tree in `qitos-zoo`, not here.

## Architecture Map

```text
qitos/core/          framework contracts (AgentModule, StateSchema, Decision, Action, tools, Task, Env, errors)
qitos/protocols.py   model I/O protocol registry (root-level leaf shared by core/engine/kit)
qitos/prompting.py   prompt spec/builder (root-level leaf)
qitos/engine/        execution kernel: loop, hooks, stop, recovery, interrupts, AsyncEngine
qitos/harness/       model family presets (FamilyPreset) — kernel defaults source, despite the generic name
qitos/models/        provider abstraction (OpenAI/LiteLLM/Anthropic/Gemini/local)
qitos/kit/           concrete implementations: tools, toolsets, parsers, memory, history, critics, envs, REPL
qitos/trace/         v1 trace artifacts (runs/{run_id}/) — frozen compatibility contract, qita reads these
qitos/tracing/       v2 span plane + processors (not wired by default; do not point qita at it)
qitos/render/        Rich terminal rendering + EngineHooks
qitos/qita/          trajectory CLI (board/replay/export)
qitos/checkpoint/    v2 checkpoint stores (v1 manager deprecated)
qitos/evaluate|metric/  thin eval contracts; implementations in qitos/kit/evaluate|metric
qitos/recipes/       canonical recipes: method templates + benchmarks (the benchmark migration target)
qitos/benchmark/     DEPRECATED adapters migrating to recipes.benchmarks — port, don't extend
qitos/cli.py         `qit` CLI, thin dispatch
examples/            canonical learning path (product surface, not toy snippets)
templates/           cookiecutter scaffold + 12 teaching method templates
tests/               framework tests (agent-app e2e tests belong in qitos-zoo)
```

## Dependency Rules

Enforced by `tests/test_architecture_boundaries.py` (legacy violations on a shrinking allowlist). Full matrix: `docs/architecture/module-boundaries.md`.

```text
Allowed (downward):  edge(cli/demo/qita/experiment) -> recipes -> kit -> engine -> core -> protocols/prompting
                     engine -> models/harness/checkpoint/trace/tracing;  kit -> models/evaluate/metric/trace

Forbidden:  core -> engine/kit/models/benchmark          (contracts stay leaf)
            engine -> kit/benchmark/recipes/mcp/cache    (existing lazy imports are debt, not license)
            kit -> benchmark/recipes;  anything -> cli/qita/demo/experiment/leaderboard/hf/debug/cache
            subpackage self-import of root `qitos` (`from qitos import ...` inside qitos/*)
```

**Domain-neutrality test** (inclusion gate for `qitos/`): a change is framework material only if expressible in agent-execution vocabulary alone (state, observation, decision, action, tool, model, trace, budget, experiment, hook, protocol). Domain/strategy content goes to recipes, zoo, or user code.

## Core Engineering Principles

- One mainline architecture: no parallel tracks, no `V1/V2/Legacy/Next` duplicates in core APIs.
- Reuse before create: search `qitos.kit`/`qitos.core` for an existing abstraction before adding helpers.
- Stable contracts in `qitos.core`; swappable concrete code in `qitos.kit`; benchmark glue in `recipes`.
- Orchestration (engine) stays separate from mechanism (kit/tools/envs); parse/validate at boundaries.
- Prefer explicit contracts and hook points over hidden magic; no hidden global state or duplicated state representations.
- Never degrade: trace schema consistency, `run_id`/`step_id`/`phase` clarity, stop-reason auditability, `qita` replay/export, hook payload usefulness.
- Class tools implement `execute(args, runtime_context)`; `run(...)` is a compat path only.

## Where Changes Belong

Task-type navigation (full version with tests per task: `docs/architecture/change-guide.md`):

```text
Add a tool                    -> qitos/kit/tool/<domain>/ + toolset preset in qitos/kit/toolset/
Add a model provider          -> qitos/models/<provider>.py (subclass Model, @ModelFactory.register)
Add a model family preset     -> qitos/harness/_presets.py
Add/change parser or protocol -> qitos/protocols.py + qitos/kit/parser/
Change execution semantics    -> qitos/engine/ (read qitos/engine/AGENTS.md first)
Change prompts/context        -> qitos/prompting.py + core/agent_module.py assembly
Add memory / env / critic     -> contract in qitos/core, implementation in qitos/kit
Change trace/trajectory       -> qitos/trace (v1 format is frozen; v2 = qitos/tracing)
Add/fix a benchmark           -> qitos/recipes/benchmarks/ (NOT qitos/benchmark — deprecated)
Add a method recipe/template  -> qitos/recipes/<method>/ + templates/<method>/ kept in sync
Change CLI                    -> qitos/cli.py (thin dispatch; no inline data/preset lists)
Add MCP integration           -> qitos/mcp/ (engine wiring already exists)
```

## Verification

```bash
pytest -q                                   # default validation for every meaningful change
flake8 qitos/core qitos/engine qitos/models qitos/trace
mypy qitos/core qitos/engine qitos/models qitos/trace
python -m build && python -m twine check dist/*   # when touching packaging/release surfaces
```

Targeted suites: `tests/test_architecture_boundaries.py` (dependency rules), `tests/test_public_surface.py` (root exports), `tests/engine/` + `tests/test_engine_core_flow.py` (kernel), `tests/tracing/`, `tests/checkpoint/`, `tests/mcp/`. E2E tests requiring live LLM keys are marked `e2e`. Do not claim success without running the relevant checks; if a check cannot run, say so and why.

## Working Style

- Gather context before editing; follow existing patterns and naming; small, coherent, reviewable changes.
- Solve the root problem; keep all surfaces consistent: code, tests, docs, examples, changelog, README.
- For tasks spanning multiple subsystems, >30 min, or touching architecture/API: write/update a plan under `docs/internal/plans/` and keep it current.
- Review your own diff for regressions, overreach, and new boundary violations before finishing.

## Documentation Sync (mandatory)

Every meaningful change updates, in the same task:

1. `CHANGELOG.md` — user-facing entry under the appropriate `Unreleased` category (`Added`/`Changed`/`Fixed`/...).
2. `docs/` — the most relevant existing doc (EN/zh aligned when both exist); update `docs/architecture/*` + the boundary-test allowlist when architecture changes.
3. `README.md` — a short entry in `What's New` for user/contributor-visible progress.

## Safety and Scope Control

- No unrelated drive-by changes; no large rewrites without justification; no hidden breaking changes — call out migration implications.
- Never use destructive git commands (`git reset --hard`, `git checkout --`) or amend commits unless explicitly requested.
- Security-sensitive tools stay opt-in under `qitos.kit.tool.experimental.security_research`; never export them from defaults, demos, or quickstart. Credentials come from environment variables only.
- If a task reveals a larger issue, fix what is necessary and record the follow-up in `docs/architecture/architecture-debt.md`.

## Further Reading

- `ARCHITECTURE.md` — system design, control flow, stable boundaries, layer policy
- `docs/architecture/architecture-audit.md` — how the code actually works today
- `docs/architecture/module-boundaries.md` — boundary matrix + dependency graph + current violations
- `docs/architecture/change-guide.md` — task-oriented change navigation
- `docs/architecture/architecture-debt.md` — P0/P1/P2 debt inventory
- `docs/internal/plans/` — active plans (incl. v0.7 native agent kernel and `docs/v4/` tasks)
