# QitOS Architecture

## Runtime responsibility boundary

QitOS guarantees runtime correctness; it does not guarantee task success for
every Agent/model. Session isolation, durable budget admission, persistence,
bounded/redacted model projection, typed provider stages, truthful sandbox
execution, and observable recovery are framework conformance. Prompts,
strategies, budget selection, tool output policy, child decomposition, and
final task correctness belong to the Agent developer. Endpoint availability,
rate limits, and actual model behavior belong to the provider. The normative
qualification split is documented in
[`docs/architecture/framework-responsibility-boundary.md`](docs/architecture/framework-responsibility-boundary.md).

High-level architecture map for the repository. Detailed material lives in `docs/architecture/`:

- [architecture-audit.md](docs/architecture/architecture-audit.md) — how the system actually works today, module by module
- [module-boundaries.md](docs/architecture/module-boundaries.md) — boundary matrix, target dependency graph, current violations
- [change-guide.md](docs/architecture/change-guide.md) — where a given change belongs
- [architecture-debt.md](docs/architecture/architecture-debt.md) — P0/P1/P2 debt inventory
- [tool-outcome-and-runtime-ownership.md](docs/architecture/tool-outcome-and-runtime-ownership.md) — canonical tool outcome ADR, validation boundary, lifecycle ownership matrix, and Lane B/D fixtures
- [engineering-quality-audit.md](docs/engineering-quality-audit.md) — implementation quality, lifecycle, dependency, and test audit

## System Purpose

QitOS is a research-first agent framework ("the PyTorch of agents"): one canonical kernel for prototyping methods, running benchmarks, and inspecting long-horizon trajectories. The core run model is a `AgentModule + Engine` pair executing an explicit lifecycle `observe -> decide -> act -> reduce -> check_stop`, producing replayable trace artifacts consumed by `qita`.

## Major Components

```text
qitos.core          framework contracts: AgentModule, StateSchema, Decision, Action,
                    BaseTool/ToolRegistry, Task, Memory, History, Env, specs, errors
qitos.protocols.py  model I/O protocol registry (react/json/xml/kimi/... renderers)   ← root-level leaf
qitos.prompting.py  prompt spec/builder, framework-owned sections                     ← root-level leaf
qitos.engine        execution kernel: Engine + runtime mixins + ActionExecutor,
                    hooks, stop criteria, recovery, cancellation, interrupts, AsyncEngine
qitos.harness       model family presets (FamilyPreset) — kernel-level defaults source
qitos.models        provider abstraction: Model/AsyncModel/ModelFactory + OpenAI/
                    OpenAI-compatible/LiteLLM/Anthropic/Gemini/local backends
qitos.kit           concrete implementations: tools, toolsets, parsers, prompts, memory,
                    history, planning, critics, envs, permissions, REPL, skills
qitos.trace         frozen historical trace format and explicit compatibility writer
qitos.tracing       canonical Trajectory journal/readers plus separate diagnostic span processors
qitos.render        Rich terminal rendering + EngineHooks
qitos.qita          trajectory CLI (board/replay/export); reads v1 artifacts
qitos.checkpoint    v2 checkpoint stores (memory/SQLite, versioning, durability, fork)
qitos.evaluate/metric  thin evaluation/metric contracts (implementations in kit)
qitos.recipes       canonical recipes: method templates + benchmarks (migration target)
qitos.benchmark     deprecated benchmark adapters, migrating to recipes.benchmarks
qitos.mcp/func/cache/debug/…  integration & deprecated leaves (see audit)
qitos.config       strict qitos.agent/v1 loader, credential references/resolvers,
                   and the sole declarative model/tool/Env/Session/Engine composition root
qitos.cli.py        `qit` CLI — thin dispatch over the packages above
```

Outside the package: `examples/` (canonical learning path), `templates/` (cookiecutter scaffold + 12 teaching templates), `tests/`, `docs/`, `qitos_zoo/` (planned out-of-tree apps, currently empty).

## Control Flow

One declarative launch and agent execution, mapped to real modules:

```text
agent.yaml → strict AgentConfig + explicit CredentialResolver (qitos/config)
           → ModelFactory + ToolRegistry + Env + RuntimeComposition + existing Engine
task in (Task/RunSpec, core/task.py, core/spec.py)
→ AgentModule.init_state (core/state.py StateSchema)
→ Engine.run loop (engine/engine.py)
    observe  engine/_env_runtime.py      → Observation (core/observation.py)
    decide   engine/_model_runtime.py    → agent.decide() or LLM call via qitos.models
                                         → parser (kit/parser) or native tool calls
                                         → Decision (core/decision.py), protocol via qitos.protocols
    act      engine/_action_runtime.py + action_executor.py → tools (core/tool.py via ToolRegistry)
                                         / env ops (kit/env) / handoff (engine/_handoff_runtime.py)
    reduce   engine/_control_runtime.py  → agent.reduce → state.reduce_update
    critic   engine/_control_runtime.py  → retry/stop modifications
    check_stop stop_criteria.py          → StopReason (core/errors.py)
    each phase: hooks (engine/hooks.py) dispatched via _trace_runtime
    checkpoints (qitos/checkpoint) if configured
→ EngineResult + canonical Trajectory journal (explicit historical writer remains compatible)
→ qita board/replay/export; benchmark scorers (metric/evaluate contracts)
```

## Dependency Direction

Layering (details and enforcement in [module-boundaries.md](docs/architecture/module-boundaries.md)):

```text
allowed (downward):
  cli/demo/qita/experiment/…  → recipes → kit → engine → core → protocols/prompting
  engine → models/harness/checkpoint/trace/tracing; kit → models/evaluate/metric/trace
  render → engine/tracing;  recipes → kernel+kit+render

forbidden:
  core → engine/kit/models/benchmark/… (contracts stay leaf)
  engine → kit/benchmark/recipes/mcp/cache (current lazy imports are legacy debt, not license)
  kit → benchmark/recipes/periphery
  benchmark ↔ recipes (module-level cycle tolerated only during migration)
  anything → cli/qita/demo/experiment/leaderboard/hf/debug/cache
  subpackages importing root `qitos` package (self-import)
```

`tests/test_architecture_boundaries.py` enforces these rules with a shrinking legacy allowlist.

## Stable Boundaries

- **Public contract**: root `qitos.__init__` export list (guarded by `tests/test_public_surface.py`); `qitos.core` data model; `Engine`/`AsyncEngine` semantics, `EngineHook` payloads, `StopReason` vocabulary.
- **Extension points**: `BaseTool.execute(args, runtime_context)` + `ToolRegistry`; `Model`/`ModelFactory`; `FamilyPreset`; parser/protocol registry (`qitos.protocols._protocol_table`); `EngineHook`; critic and stop-criteria contracts; checkpoint `CheckpointStore`; tracing processors.
- **Compatibility boundary**: the v1 trace artifact format (`manifest.json`/`events.jsonl`/`steps.jsonl`) consumed by qita, benchmark runners, evaluate, hf push/pull.
- **Declarative composition boundary**: `qitos.config.AgentConfig` is the one YAML/Python launch description. Its canonical view contains only credential references; resolved secrets exist only transiently at model composition and are re-resolved after process restore. The CLI is a thin caller of this boundary.
- **Internal implementation** (free to change): engine mixins, `_model_runtime` assembly, kit internals, qita `_cli_app`.

## Known Architecture Debt

Headlines (full inventory with exit plans in [architecture-debt.md](docs/architecture/architecture-debt.md)):

1. `benchmark ↔ recipes.benchmarks` dual implementations with a module-level cycle (deprecated adapters still alive).
2. `core` mixes contracts with the `AgentModule.run()` convenience layer (lazy reverse imports).
3. Engine reaches kit/mcp/cache via lazy imports — kernel knows implementations.
4. Three event schemas / artifact paths (engine states, trace v1, tracing v2 + render jsonl); qita reads only v1.
5. Whole-package lint/type coverage is narrower than the shipped surface.
6. Runtime failure, timeout, durability, and hook receipts do not yet share trustworthy semantics.
7. `qitos.harness` name collision; `evaluate`/`metric` contract-vs-kit-mirror split; god objects in the kernel.

The `harness ↔ models` module-level cycle is resolved; concrete model construction
now lives in `qitos.models.harness_adapter`. The next architecture and quality
steps are planned in `docs/v4/`: canonical model/action/context/trajectory
contracts in Tasks 02–05 and quality gates, lifecycle semantics, and
consolidation in Tasks 08–10, durable Session/work ownership in Tasks 12–13,
and safe-by-default sandboxed agent execution in Task 14. The existing Docker
Env is an execution backend, not yet an untrusted-code security qualification.
Multi-agent delivery follows the
[four-lane execution playbook](docs/v4/11-four-lane-execution-playbook.md), which
assigns one semantic owner per contract and shared-file leases for integration.

## Repository Layer Policy

- **Stable framework surface**: `qitos.core`, `qitos.engine`, `qitos.trace`, `qitos.qita`, root-level model/provider abstractions. Top-level `qitos` imports stay limited to kernel contracts.
- **Curated extensions**: `qitos.kit`, `qitos.kit.tool*`, `qitos.models`, `qitos.render`, `qitos.protocols` — generic, reusable, no product naming or workflows.
- **Recipes and benchmarks**: `qitos.recipes` may hold reusable research baselines and canonical benchmark methods, callable from thin examples. `qitos.benchmark` (deprecated) must not vendor datasets or product workflows; the 22k-line vendored `tau_bench/port` is migration debt.
- **Examples policy**: `examples/` is a small canonical learning path (one concept per example, runs locally); full applications belong in `qitos-zoo`.
- **qitos-zoo**: product-grade apps (`qitos_coder`, `qitos_cyber`, `qitos_auditor`) live out-of-tree. Promotion into core requires: generic, tested, documented, needed by ≥2 independent apps. Agent-app e2e tests belong in the zoo, not core `tests/`.
- **Domain neutrality test**: a change is framework material only if expressible in agent-execution vocabulary (state, observation, decision, action, tool, model, trace, budget, experiment, hook, protocol). Everything else stays in recipes, zoo, or user code.

## Security-Sensitive Rule

Cybersecurity/offensive research tooling must never be part of the default public surface: not exported from `qitos.__init__`, `qitos.kit` defaults, `qit demo`, or quickstart. It may exist only as explicit opt-in modules under `qitos.kit.tool.experimental.security_research` or as zoo applications with controlled, documented use.

## Non-Goals

- No parallel architecture tracks, no `V1/V2/Legacy/Next` duplicates in core APIs (existing v1/v2 pairs — trace/tracing, checkpoint, benchmark — are migration states with exit plans, not long-term design).
- No hiding execution semantics behind opaque abstractions.
- No benchmark datasets, product dependencies, secrets, or local absolute paths in the framework.
