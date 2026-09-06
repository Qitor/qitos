# Architecture Audit

September 2026 implementation addendum: [Agent Design Lab](../internal/plans/agent_design_lab_execution.md)
keeps the same kernel. Custom policies enter the existing config composition via
`agent_factory`; ownership and Session creation stay at the composition root.
`BaseToolLibrary` / `ToolArtifact` remain the skill seam, with a concrete SQLite
revision store in kit. Full-body skill selection and memory deletion are mechanisms;
curriculum, planner, review and retention policy stay in the six external-style
learning projects. No core-to-kit or engine-to-kit dependency is added.
External child snapshot resources are restored before authorized conversation
projection, and historical pause receipts cannot suppress continuation completion.
The following original audit retains its dated source scope.

Status: recovered from code as of 2026-08 (v0.6.0). This document records how the repository **actually works**, distinguished from intended architecture and debt.
Method: full-repo review plus AST-verified import analysis (module-level vs function-level imports, absolute and relative).
Companion documents: [module-boundaries.md](module-boundaries.md) · [architecture-debt.md](architecture-debt.md) · [change-guide.md](change-guide.md).

---

## 1. What the system actually is

QitOS is a research agent framework built around one execution kernel:

```text
AgentModule (decide / reduce / should_stop)
        +
Engine    (observe -> decide -> act -> reduce -> critic -> check_stop)
        -> Decision -> ActionExecutor -> Env/Tools
        -> TraceWriter artifacts (events.jsonl / steps.jsonl / manifest.json)
        -> qita (board / replay / export)
```

The stable product is the kernel loop plus the trajectory artifacts it emits. Everything else (kit implementations, recipes, benchmark adapters, CLI) is expected to compose on top of this loop, not bypass it.

## 2. First-class modules (recovered, not assumed)

| Module | Real responsibility | Verified by |
| --- | --- | --- |
| `qitos.core` | Framework contracts: `AgentModule`, `StateSchema`, `Decision`, `Action`, `BaseTool`/`FunctionTool`, `ToolRegistry`, `Task`, `Memory`, `History`, `Env`+capabilities, errors, specs, agent registry. **Also** a convenience layer (`AgentModule.run()` builds an Engine, toolsets, writers). | 25 files, no third-party deps |
| `qitos.protocols.py` | Root-level leaf: `ModelProtocol` registry (react/json/xml/kimi/minimax/terminus/...), prompt/schema renderers, protocol resolution chain. | 708 lines, stdlib-only |
| `qitos.prompting.py` | Root-level leaf: `PromptSpec`/`PromptBuilder`, framework-owned prompt sections. Consumed by `core/agent_module.py`. | 307 lines, stdlib-only |
| `qitos.engine` | The kernel runtime: `Engine` + 7 runtime mixins + `ActionExecutor`; hooks, stop criteria, recovery, cancellation, interrupts, checkpoint integration, single-step/session API, `AsyncEngine`. | 36 files |
| `qitos.harness` | **Model family presets** (`FamilyPreset`, tool/context policy, `OpenAICompatibleAdapter`). Kernel-level despite the generic name. | 4 files, 661 lines |
| `qitos.models` | Provider abstraction: `Model`/`AsyncModel`/`ModelFactory` (`base.py`), OpenAI/OpenAI-compatible/Azure, LiteLLM, Anthropic, Gemini, local backends, Responses-API transport, profile/context registries. | 10 files |
| `qitos.kit` | Concrete implementations: ~20 tool domains, toolsets, parsers, prompts, memory, history, planning, critics, envs, permissions, REPL, skills, search, embeddings, vectorstores, multi-agent patterns, evaluate/metric implementations. | 196 files |
| `qitos.trace` | **v1 observability (production path)**: `TraceEvent`/`TraceStep`, `TraceWriter` (`runs/{run_id}/` artifacts), schema validator. | 4 files |
| `qitos.tracing` | **v2 span system** (OpenAI-Agents-SDK style): `Trace`/`Span`/`SpanData`, provider/processors (console/JSON/W&B/MLflow), legacy bridge to v1 writer. Not wired by default. | 10 files |
| `qitos.render` | Rich terminal rendering + `EngineHook`s (`ClaudeStyleHook`); a third artifact path via `output_jsonl`. | 8 files |
| `qitos.qita` | Trajectory CLI (`board`/`replay`/`export`); reads v1 trace artifacts. Implementation is a single 186 KB `_cli_app.py`. | 7 files |
| `qitos.checkpoint` | v2 checkpoint stores (LangGraph-borrowed: memory/SQLite, versioning, durability, pending writes, fork) + deprecated v1 `CheckpointManager`. | 9 files |
| `qitos.evaluate` / `qitos.metric` | Thin contract packages (~310 lines total): per-trajectory evaluation vs benchmark-level metric aggregation. Implementations live in `qitos/kit/evaluate/` and `qitos/kit/metric/`. | 3 + 2 files |
| `qitos.benchmark` | **Deprecated** benchmark adapters (gaia/cybench/cybergym/osworld/tau_bench/desktop) migrating to `qitos.recipes.benchmarks`. Includes 22k-line vendored `tau_bench/port`. | 89 files |
| `qitos.recipes` | Canonical reproducible recipes: method templates (lats/moa/reflexion/self_refine/magentic_one) + `benchmarks/` (the migration target) + `desktop/`. | 14 files |
| `qitos.mcp` | MCP integration (server ABC, stdio/http transports, schema conversion, bridge to FunctionTools). Consumed only by `Engine._connect_mcp_servers` (lazy). | 7 files |
| `qitos.func` | Function-style sugar (`@task`, `@agent`, composition) over the kernel. Not used inside qitos. | 5 files |
| Periphery | `cli.py` (`qit`), `demo/`, `config/` (YAML→Engine assembly), `experiment/` (sweep runner), `leaderboard/`, `hf/` (artifact push/pull), `cache/` (deprecated LLM cache), `debug/` (deprecated Python replay API). | small leaves |
| Outside the package | `examples/` (canonical learning path), `templates/` (cookiecutter scaffold + 12 teaching method templates), `tests/` (166 files), `scripts/` (cybergym campaign ops scripts), `docs/`, `qitos_zoo/` (empty placeholder). | |

## 3. Module responsibilities: owns / does not own

- **`core`** owns agent-execution vocabulary contracts. It does **not** own runtime mechanics, provider specifics, or tool implementations — yet `AgentModule`/`AgentSpec` lazily import engine, kit, trace, render, harness to power the `run()` convenience path (see debt D2).
- **`engine`** owns loop mechanics, hooks, stop logic, recovery. It does not own tools, parsers, prompt templates, or benchmark semantics — but it constructs kit envs (`_env_runtime.py`), lazily pulls `CompactHistory`, handoff tools, MCP bridge, cached models, so the boundary is porous in practice (debt D3).
- **`kit`** owns swappable implementations. It does not own contracts, and must not know benchmark specifics — violated once by `kit/evaluate/cybench.py` importing `qitos.benchmark.cybench` (debt D6).
- **`trace`** owns the v1 artifact format that qita and every benchmark runner consume. This format is the **de facto compatibility contract** of the project.
- **`tracing`** owns the v2 span plane; it must remain a leaf. Currently `trace -> tracing` (module) and `tracing -> trace` (lazy, legacy bridge) form a tolerated cycle (debt D4).
- **`harness`** owns family presets that engine, models, and cli consult. It is kernel infrastructure with a misleading name (debt D7).
- **`benchmark`/`recipes.benchmarks`** are two generations of the same concern, mutually importing (debt D1).

## 4. Actual dependency graph (AST-verified)

Module-level edges only (function-level "lazy" edges in parentheses):

```text
(root) __init__  -> core, engine
core             -> prompting                                  (lazy: engine, kit x3, harness, trace, render, protocols)
engine           -> core, models, checkpoint, trace, protocols (lazy: kit x3, mcp, cache, tracing x2, checkpoint, trace)
models           -> core, harness                              (lazy: harness)
harness          -> models, protocols
kit              -> core, engine, models(lazy), protocols(lazy), evaluate, metric, trace,
                    benchmark [legacy], (root) [legacy]
evaluate         -> core
metric           -> (none)
trace            -> tracing
tracing          -> (none)                                     (lazy: trace, engine)
render           -> core, engine, tracing
checkpoint       -> (none, self-contained)
mcp              -> core
cache            -> models
recipes          -> core, engine, kit, models, trace, render, evaluate, metric, harness,
                    benchmark [migration-era], (root) [legacy]
benchmark        -> core, engine, kit, trace, tracing, recipes [migration-era]
experiment       -> core, engine, config, cache, checkpoint
config           -> core, models
demo             -> (root), kit, models
leaderboard      -> benchmark, core
qita             -> (root)(lazy), debug(lazy)
cli              -> benchmark, core, demo, kit, qita           (lazy: config, experiment, harness, hf, leaderboard)
debug, func      -> core(func only); essentially leaves
```

Notable hard facts:

1. **`harness <-> models` is a true module-level package cycle.** `harness/__init__ -> _adapters -> models.context_registry/openai`, while `models/__init__ -> profile_registry -> harness._presets`. It imports successfully only because Python tolerates partially-initialized parents when the importee is a submodule. Any refactor that makes either side import package attributes (not submodules) will break at import time.
2. **`benchmark <-> recipes` is a true module-level package cycle** (5 files each direction): `benchmark/*/runner.py -> recipes.benchmarks.*` while `recipes/benchmarks/* -> benchmark.*.adapter/port`.
3. **Subpackages importing the root package** (`from qitos import ...`): `kit` (2 files), `recipes` (9), `demo` (1), `qita` (1, lazy). Combined with `engine -> (lazy) kit`, `qitos -> engine`, this forms a latent cycle that only function-level imports keep from exploding.
4. `protocols.py` — a module the engine imports at module level — lazily imports `qitos.kit.parser` (`protocols.py:431`), so the engine↔kit coupling also hides inside the protocol registry.

## 5. Which dependencies are reasonable

- `engine -> core/protocols/prompting`: kernel needs contracts and protocol registry. Correct direction.
- `kit -> core/engine/protocols/models/evaluate/metric/trace`: implementations may build on kernel and contracts; kit tools writing traces is accepted (delegate/fanout tools are run observers).
- `trace -> tracing`: v1 reuses v2's redaction helper. Direction is inverted chronologically but harmless as a leaf utility reuse; the lazy `tracing -> trace` bridge is the tolerated inverse.
- `render -> core/engine/tracing`: hooks are engine contracts; redaction reuse. Fine.
- `recipes -> kernel + kit + render`: recipes are the intended aggregation layer for reference implementations.
- `periphery (cli/demo/experiment/config/leaderboard/hf/qita) -> anything below`: aggregators at the edge. Correct direction.
- `models/harness -> core/protocols`: correct.
- `evaluate/metric -> core`: correct thin contracts.

## 6. Layering violations / hidden coupling

See [architecture-debt.md](architecture-debt.md) for the classified list. Headlines:

- Upward: `kit -> benchmark` (`kit/evaluate/cybench.py:9`); `core -> kit/engine/render/trace` (lazy convenience); `protocols -> kit` (lazy).
- Cycles: `harness <-> models` (module-level); `benchmark <-> recipes` (module-level); `trace <-> tracing` (lazy bridge); latent `subpackages -> root __init__ -> engine -> (lazy) kit`.
- God objects: `Engine` (~2,000 lines, 33-param constructor), `_ModelRuntime` (~1,800 lines), `ActionExecutor` (~1,150 lines), `AgentModule` (contract + convenience).
- Provider leakage: `core/errors.py` imports `openai` (lazily) to classify API errors — the only provider reference inside core.
- Three event schemas and three artifact paths (engine states / trace v1 / tracing v2 + render output_jsonl); the v2→v1 bridge is lossy (`step_id` forced to 0).
- Deprecation inversion: qita's `fork` feature depends on deprecated `qitos.debug`.

## 7. Overloaded modules

1. `qitos/engine/engine.py` — orchestration + construction + checkpoint + MCP + handoff + budgeting in one class; mitigated by mixins but the public object is monolithic.
2. `qitos/engine/_model_runtime.py` — LLM I/O, streaming, parsing recovery, protocol chains, native tool calls, branch handling. Already slated for replacement by the v0.7 conversation kernel (`docs/v4/02-conversation-kernel.md`).
3. `qitos/kit/` — unavoidable breadth, but contains benchmark-specific code, deprecated shims, and near-duplicate critics/parsers.
4. `qitos/qita/_cli_app.py` — 186 KB single file holding the entire product surface of qita.
5. `qitos/cli.py` — acceptable (730 lines, lazy periphery) but inlines data that belongs to packages (`known_benchmarks` list, `gold_ids` preset set).

## 8. Duplicate implementations

| Concept | Copies | Note |
| --- | --- | --- |
| Event/step schema | `engine/states.py` RuntimeEvent/StepRecord; `trace/events.py` TraceEvent/TraceStep; `tracing/models.py` SpanData family | (b) is a serialization projection of (a); (c) is a re-classification; bridge (c)->(b) is lossy |
| On-disk artifacts | `runs/{run_id}/` (trace v1), `.traces/trace_*.json[l]` (tracing v2), render `output_jsonl` | Three writers, none aware of the others; qita reads only v1 |
| Benchmark implementations | `qitos/benchmark/*` vs `qitos/recipes/benchmarks/*` | Declared migration, both alive, mutually importing |
| Checkpoint | v1 `CheckpointManager` vs v2 `CheckpointStore` | engine uses v2; `experiment/runner.py` still builds v1 |
| Self-reflection critics | `kit/critic/self_reflection.py` vs `react_self_reflection.py` | Near-isomorphic |
| JSON repair | `core/_json_repair.py`, `kit/parser/parser_utils.py`, private `_try_fix_*` in json/terminus parsers | Layered but overlapping |
| Method templates | `templates/<method>/` (teaching) vs `qitos/recipes/<method>` (canonical) | Intentional split, must not drift |
| Replay/debug | `qitos/debug` (deprecated) vs qita replay | qita depends on the deprecated one |

## 9. Implicit shared kernel (utilities that became load-bearing)

- `qitos.protocols` and `qitos.prompting` — stdlib-only root leaves shared by core/engine/kit/harness. They are de facto kernel substrate, not "utils".
- `qitos.tracing.config._redact_dict` — imported by `trace/writer.py`, `benchmark/common.py`, `render/_hooks_impl.py`. A private helper acting as public redaction utility.
- `qitos/harness/_presets.known_family_presets` — the single source of family defaults consumed by models registries, engine, cli.
- `qitos/core/tool.py` + `tool_registry.py` — the tool contract everything (engine, kit, mcp, benchmark) builds on.

## 10. Stable boundaries for future refactors

1. **Kernel contracts**: `qitos.core` data model (`AgentModule`, `StateSchema`, `Decision`, `Action`, `ToolRegistry`, `Task`, specs, errors) and the root `qitos.__init__` export list (guarded by `tests/test_public_surface.py`).
2. **Engine public API**: `Engine`/`AsyncEngine` constructor and run semantics, `EngineHook` payload shapes, stop-reason vocabulary, `EngineEvent` stream.
3. **Trace v1 artifact format**: `manifest.json` + `events.jsonl` + `steps.jsonl` — consumed by qita, benchmark runners, evaluate (`load_run_artifacts`), hf push/pull, debug replay. Any observability overhaul must keep or version this format.
4. **Tool contract**: `BaseTool.execute(args, runtime_context)` + `ToolRegistry` composition; `run()` is a compat shim.
5. **Protocol registry**: protocol names and their prompt/schema renderers (`qitos.protocols._protocol_table`), resolution chain order.
6. **Family presets**: `FamilyPreset` field set in `harness/_presets.py` — defaults source for models/engine/cli.
7. **Benchmark entrypoints**: `qit bench` surface and `BenchmarkRunResult` shape during the recipes migration.

## 11. Existing guardrails (do not duplicate)

`tests/test_public_surface.py` (root exports, no product/security leakage), `tests/test_experimental_boundary.py` (experimental shims warn), `tests/test_p0_freeze_guards.py`, `tests/test_cli_governance.py`, `tests/test_no_local_paths.py`, `tests/test_architecture_layout.py` (kit layout only). This audit adds `tests/test_architecture_boundaries.py` (dependency-direction ratchet + cycle detection + doc link check).

## 12. Alignment with existing plans

The repository already plans its next architectural step: `docs/internal/plans/v0.7_native_agent_kernel.md` with task decomposition in `docs/v4/01..05` (conversation kernel, ACI toolset, context injection, trajectory data plane). The debts recorded here (D1–D12) are inputs to that plan; nothing in this harness contradicts it. The intended end state keeps `AgentModule + Engine` as the mental model while making the message stack the kernel object.
