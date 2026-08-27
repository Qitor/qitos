# Architecture Debt

Classified inventory of structural debt recovered by the [architecture audit](architecture-audit.md). Recorded, not fixed: this list is the input queue for future refactors (see `docs/internal/plans/v0.7_native_agent_kernel.md` and `docs/v4/` for the already-planned kernel work).

Legend: **P0** structural risk (blocks refactors / can break imports), **P1** important architecture debt (confuses agents and maintainers, grows entropy), **P2** local cleanup.

## P0 — Structural risk

### D1. `benchmark <-> recipes.benchmarks` dual implementations with a module-level cycle
- Where: `benchmark/{gaia,tau_bench,cybench,cybergym,osworld,desktop}/runner.py` import `qitos.recipes.benchmarks.*`; `recipes/benchmarks/*.py` import back `qitos.benchmark.*.adapter/port`.
- Why P0: the largest subpackage (89 files, 26k lines) is deprecated yet structurally entangled with its replacement; any edit on either side can break imports; agents cannot tell which copy is canonical.
- Exit: finish the declared migration (benchmark → recipes.benchmarks), then delete legacy adapters; the vendored `tau_bench/port` (22k lines, 82% of benchmark volume) should become an optional asset/package, not core source.

### D2. `core` mixes contracts with a convenience layer
- Where: `core/agent_module.py` lazily imports `engine.Engine`, `kit.env`, `kit` toolsets, `trace.TraceWriter`, `render.ClaudeStyleHook`, `harness`; `core/agent_spec.py` imports kit delegate/fanout/handoff tools.
- Why P0: the "core has no dependencies" invariant is only true at module level; the convenience path inverts the layer for every tutorial-style `agent.run()` call, so agents copying it propagate the inversion.
- Exit: extract the convenience path (`run()`, default toolset/env assembly) into a separate module (e.g. `qitos.kit.quickrun` or an `AgentModule.run()` that delegates upward explicitly), leaving `core/agent_module.py` as pure contract. Alternative: accept the convenience path as intended architecture and document it — but then it must be listed in the boundary matrix as a permanent exception, not an accident.

### D3. Engine's hidden downward edges via lazy imports
- Where: `engine/engine.py` (kit history/handoff tools, mcp bridge, cache CachedModel, tracing), `engine/_env_runtime.py` (kit envs by EnvSpec.type), `engine/_control_runtime.py` (compact history), `engine/_handoff_runtime.py` (tracing); plus `protocols.py:431` lazily importing kit parsers.
- Why P0: the kernel silently knows concrete kit implementations; any module-level promotion of these imports creates an import cycle (kit files already self-import the root package). The v0.7 conversation-kernel plan will rewrite most of this assembly — do not grow it before then.
- Exit: protocol/plugin points (registry callbacks or constructor injection) instead of kernel-side lazy lookups; `docs/v4/02` already replaces `_model_runtime` assembly.

### D4. Three event schemas and three artifact paths
- Where: `engine/states.py` (RuntimeEvent/StepRecord) → `trace/` (TraceEvent/TraceStep, `runs/{run_id}/`) → `tracing/` (SpanData, `.traces/`), plus `render/ClaudeStyleHook(output_jsonl=...)`; the v2→v1 bridge forces `step_id=0`.
- Why P0: qita (the product observability surface) reads only v1; tracing v2 is built, tested, and wired nowhere by default. Three writers duplicate state representation and drift risk is active.
- Exit: `docs/v4/05-trajectory-data-plane.md` is the planned consolidation; until then, treat the v1 artifact format as frozen contract and route all new fields through it.

### D5. ~~`harness <-> models` module-level import cycle~~ (RESOLVED)
- Resolved by moving the concrete adapter layer out of harness: `OpenAICompatibleAdapter`, `adapter_for_kind`, `resolve_context_window`, and `build_model_for_preset` now live in `qitos/models/harness_adapter.py`; harness keeps preset data, policy types, and `build_harness_policy` (transport-free). The only remaining edge is the target-direction `models -> harness`.
- D7 (harness naming) remains open and can proceed independently.

## P1 — Important architecture debt

### D6. Benchmark-specific code inside `kit`
- Where: `kit/evaluate/cybench.py` (imports `qitos.benchmark.cybench.runtime` — the only kit→benchmark edge), `kit/metric/cybench.py`, `kit/tool/cybench.py`.
- Fix: move all three into `qitos.recipes.benchmarks.cybench` (or benchmark cybergym-style) so kit stays domain-neutral.

### D7. `qitos.harness` naming collision
- The package is kernel-level model family presets, but "harness" is a generic term (and collides with agent-harness usage in this repo's own tooling docs). Nothing exports it at root. Fix: rename to `model_presets` (or fold into `models`) during D5.

### D8. Root-package self-imports (latent cycle)
- Where: `kit/agent/security_audit_agent.py`, `kit/tool/internal/subagents.py`, 9 `recipes/*` files, `demo/minimal.py`, `qita/_cli_app.py` use `from qitos import ...`.
- Fix: import from `qitos.core[.x]` / `qitos.engine[.x]` directly. Guarded by the boundary test (V6).

### D9. `evaluate`/`metric` top-level contract packages with kit mirrors
- ~310 lines of contracts at top level, implementations under `kit/evaluate/` and `kit/metric/` — three namespaces for one concern.
- Fix: either merge contracts into kit (single `qitos.kit.evaluate`) or merge the packages into one `qitos.eval` with contracts+implementations together.

### D10. Deprecation inversions
- `qita` (current product) depends on `qitos.debug` (deprecated) for run `fork`; `experiment/runner.py` still builds deprecated v1 `CheckpointManager` and deprecated `qitos.cache`.
- Fix: move `ReplaySession.fork` logic into qita or un-deprecate debug; port experiment to checkpoint v2.

### D11. God objects in the kernel
- `Engine` (~2,000 lines, 33-param constructor), `_ModelRuntime` (~1,800 lines), `ActionExecutor` (~1,150 lines), `AgentModule` (contract+convenience, ~740 lines). Mixins mitigate but construction and wiring remain monolithic.
- Fix direction: constructor config objects (`EngineConfig` exists — finish the migration), conversation kernel replaces `_model_runtime` assembly (v4/02).

### D12. Silent hook failure
- `engine/_trace_runtime.py:422` `dispatch_hook` swallows all hook exceptions with a debug log. Observability hooks failing invisibly undermines the observability contract.
- Fix: count failures into the run result/trace event, or make strictness configurable.

## P2 — Local cleanup

- **D13** `cli.py` inlines `known_benchmarks` and `gold_ids` preset set instead of sourcing from `benchmark/runner.py` / `harness/_presets.py`; duplicated `--help` registration blocks.
- **D14** `qitos_zoo/` is an empty directory yet `setup.py` still references `qitos_zoo*` and two tests target the missing package.
- **D15** `scripts/` contains cybergym campaign ops scripts (run_batch*.sh, tmux launchers) — archive per `docs/internal/plans/cybergym_campaign_absorption.md`.
- **D16** `core/errors.py` lazily imports `openai` for error classification — provider name inside core; move classification to `models`.
- **D17** Near-duplicates: `kit/critic/self_reflection.py` vs `react_self_reflection.py`; private `_try_fix_*` JSON repair in both `json_parser.py` and `terminus_json_parser.py`; deprecated top-level shims (`kit/tool/network_toolset.py` etc.).
- **D18** `qita/_cli_app.py` is a 186 KB single module — split per command when next touched.
- **D19** `tests/` layout: engine loop behavior tests live at tests root (`test_engine_core_flow.py` etc.) while mechanism unit tests live in `tests/engine/`; ~105 test files are flat at root.
- **D20** `kit/__init__.py` lazy-export machinery still eagerly imports `.tool`/`.toolset`; the laziness is cosmetic.
- **D21** `func` package is unused inside qitos and referenced only by one test — decide: document as public sugar or mark experimental.
- **D22** `leaderboard`/`hf` are operational features living in the core repo; candidates for out-of-tree tooling per the zoo policy.

## Explicit non-goals for debt cleanup

- No big-bone rewrites of the engine loop outside the already-planned v0.7 tasks.
- No renaming of public API surface (`qitos.core`/`qitos.engine` names stay).
- No removal of the v1 trace format before the trajectory data plane (v4/05) lands a versioned replacement.
