# Architecture Debt

Agent Design Lab follow-ups (not claims of completion): SQLite skill catalog is a
projection, not bounded-I/O search; dependency pinning, signed skill distribution
and malicious-code-resistant grading are not provided. Memdir forgetting is not
secure erasure or a multi-writer transaction. The course curriculum is bounded
mastery ordering, not an open-ended learned curriculum. These do not justify new
kernel loops or duplicated stores. See the [execution ledger](../internal/plans/agent_design_lab_execution.md).

The [v5 residual-goal roadmap](../v5/README.md) is the current iteration map.
The [R1 implementation review](../internal/plans/v5_r1_integration_review.md)
tracks candidate-only reasoning/cleanup, handoff attribution/admission and YAML
integration gaps. These require bounded repairs before R1 promotion; they do not
reopen completed G5 architecture or close the remaining V5-03 debt.
The dated entries below retain their audit context: some G5 mechanisms are now
implemented, while provider/legacy-interface, context/memory, data-efficiency
and optional-integration debt remains. Revalidate each item against the exact
implementation baseline; neither a historical P0 label nor a later stage closure
proves its current status. This pointer does not mark any open debt resolved.

Classified inventory of structural debt recovered by the
[architecture audit](architecture-audit.md) and the
[engineering-quality audit](../engineering-quality-audit.md). Recorded, not
fixed: this list is the input queue for future refactors (see
`docs/internal/plans/v0.7_native_agent_kernel.md` and `docs/v4/` for the active
kernel and quality work).

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
- D1 evidence (2026-08-29): the symbol-level producer/writer/reader chains, correlation/privacy/failure comparison, two independent fixture-source manifests, and benchmark readiness gate are recorded in `docs/internal/plans/lane_d_data_convergence.md`. Census is complete; schema/store consolidation is not started and trajectory v2 is not frozen.

### D5. ~~`harness <-> models` module-level import cycle~~ (RESOLVED)
- Resolved by moving the concrete adapter layer out of harness: `OpenAICompatibleAdapter`, `adapter_for_kind`, `resolve_context_window`, and `build_model_for_preset` now live in `qitos/models/harness_adapter.py`; harness keeps preset data, policy types, and `build_harness_policy` (transport-free). The only remaining edge is the target-direction `models -> harness`.
- D7 (harness naming) remains open and can proceed independently.

### D23. Whole-package quality is outside the required lint/type signal
- Where: CI and pre-commit check only `core`, `engine`, `models`, and `trace`; `pyproject.toml` excludes or ignores broad kit/render/benchmark surfaces. The 2026-08-29 full diagnostic found 204 flake8 findings and 48 mypy errors, including correctness-class findings.
- Why P0: a green required check can coexist with undefined runtime names and invalid public overrides in the shipped package.
- Exit: `docs/v4/08-quality-gates-and-packaging.md` establishes a full-surface no-regression baseline, preserves stable zero-error jobs, and retires debt package by package.

### D24. Runtime success, timeout, and durability receipts are not trustworthy
- Where: provider adapters return transport failures as text; ASYNC checkpointing returns intended IDs after queue drop and swallows worker errors; tool thread timeouts can leave workers running; hooks fail silently.
- Why P0: callers cannot distinguish model output from infrastructure failure, timeout from cancellation, accepted from persisted work, or complete from degraded observability.
- Exit: `docs/v4/09-runtime-lifecycle-and-error-semantics.md`, coordinated with Tasks 02, 03, and 05, defines typed failures, resource ownership, checkpoint receipts, and hook completeness.
- D1 evidence (2026-08-29): exact consumers and missing receipt joins are listed in the Lane D census. Benchmark/fixture materialization explicitly blocks on Lane C timeout/cancellation, durability, hook-failure, and redaction fixtures rather than inferring their fields.
- G3 convergence (2026-08-31): the single-agent Session path now records typed provider failure, lifecycle/effect uncertainty, partial-slot durability, required/optional sink delivery, and paused-head persistence. Python-thread/remote cancellation and external effect reconciliation remain capability-owned; generic hook swallowing outside the EventSink bridge remains D12 rather than being relabeled solved.

### D32. ~~Session and multi-agent continuity are fragmented across in-process primitives~~ — RESOLVED FOR THE LOCAL DURABLE RUNTIME
- Where: `Engine.init_session`/`step`, `RunState`, checkpoint v2 `thread_id`, interrupt/resume, qita fork, `_handoff_runtime`, `DelegateTool`, and `FanOutTool` each carry part of session or child-work state.
- Why P0: a fresh process cannot reconstruct one authoritative execution head with task, concrete state schema, exchanges, partial tool batch, context/artifacts, owner, children, budgets, and trace cursor. Handoff mutates live ownership and delegate/fan-out workers have no durable work graph, so restart can duplicate or orphan work.
- Resolution: Tasks 12–13 now provide one checkpoint-backed Session head,
  immutable snapshots, safe pause/restore/fork, generation/owner fencing,
  explicit context transfer, reconstructable work descriptors, and one durable
  local WorkGraph runtime for handoff/delegate/fan-out/spawn/join. G4 qualified
  deterministic clean-process and process-loss recovery before the result was
  promoted in the S3 closure baseline.
- Remaining boundary: this resolution does not claim a distributed scheduler,
  external-world exactly-once effects, or hard cancellation. S4 owns public DX,
  sandbox binding, and Trajectory/qita rollout; those are follow-on graduation
  work rather than evidence that the local continuity architecture remains
  fragmented.

## P1 — Important architecture debt

### D6. Benchmark-specific code inside `kit` — RESOLVED
- Resolved: `kit/evaluate/cybench.py`, `kit/metric/cybench.py`, and `kit/tool/cybench.py` were folded into `qitos/recipes/benchmarks/cybench.py` (evaluator, guided/unguided metrics, and the `SubmitAnswer` tool). The kit→benchmark edge is gone and the {benchmark, kit, recipes} SCC shrank to {benchmark, recipes} (D1 remains).

### D7. `qitos.harness` naming collision
- The package is kernel-level model family presets, but "harness" is a generic term (and collides with agent-harness usage in this repo's own tooling docs). Nothing exports it at root. Fix: rename to `model_presets` (or fold into `models`) during D5.

### D8. Root-package self-imports (latent cycle) — module-level cases RESOLVED
- Resolved: the 13 module-level `from qitos import ...` sites (`kit/agent/security_audit_agent.py`, `kit/tool/internal/subagents.py`, 9 `recipes/*` files, `demo/minimal.py`) now import `qitos.core.*` / `qitos.engine.*` directly; V6 removed from the boundary allowlist. `demo`'s allowed set now includes `core` (edge aggregator, see the matrix prose).
- Remaining (function-level, invisible to the boundary test): `cli.py` and `qita/_cli_app.py` lazily import `__version__` from the root package — the version string is root-owned, so these stay until version metadata moves to `importlib.metadata`.

### D9. `evaluate`/`metric` top-level contract packages with kit mirrors
- ~310 lines of contracts at top level, implementations under `kit/evaluate/` and `kit/metric/` — three namespaces for one concern.
- Fix: either merge contracts into kit (single `qitos.kit.evaluate`) or merge the packages into one `qitos.eval` with contracts+implementations together.

### D10. Deprecation inversions
- `qita` (current product) depends on `qitos.debug` (deprecated) for run `fork`; `experiment/runner.py` still builds deprecated v1 `CheckpointManager` and deprecated `qitos.cache`.
- Fix: move `ReplaySession.fork` logic into qita or un-deprecate debug; port experiment to checkpoint v2.

### D11. God objects in the kernel
- `Engine` (~2,000 lines, 34-param constructor including `self`), `_ModelRuntime` (~1,800 lines), `ActionExecutor` (~1,150 lines), `AgentModule` (contract+convenience, ~740 lines). Mixins mitigate but construction and wiring remain monolithic.
- Fix direction: constructor config objects (`EngineConfig` exists — finish the migration), conversation kernel replaces `_model_runtime` assembly (v4/02).

### D12. Silent hook failure
- `engine/_trace_runtime.py:422` `dispatch_hook` swallows all hook exceptions with a debug log. Observability hooks failing invisibly undermines the observability contract.
- Fix: count failures into the run result/trace event, or make strictness configurable.

### D25. `Observation` and action outcomes have competing representations
- `Observation` is both a mutable dataclass and `dict`, synchronized only at construction. `ActionResult` has five terminal states and execution identity while `ToolResult` collapses to success/error and legacy-flattens outputs.
- Risk: reducers, history, traces, and renderers can observe divergent or lossy state.
- Exit: Task 03 owns one lossless action outcome; Task 10 replaces dual-state `Observation` after Tasks 02/03 stabilize compatibility projections.

### D26. Request control uses duplicated token and JSON-repair policies
- Seven `_estimate_tokens` implementations use provider counts, word counts, character heuristics, or renderer regexes. Generic and protocol-specific JSON salvage is interleaved across core, parsers, evaluators, and REPL code.
- Risk: budget/compaction decisions and parse diagnostics vary by entry point.
- Exit: Tasks 02/04 establish a labeled token-counter capability and layered JSON parsing; Task 10 removes superseded helpers.

### D27. Optional dependencies do not match advertised feature behavior
- MCP HTTP, local embeddings, cron, PDF/notebook helpers, and pgvector drivers are not represented consistently in extras. Cron can accept inert jobs; PgVectorStore checks asyncpg but executes through psycopg2.
- Risk: clean installations fail late or silently degrade, and the `all` extra is not actually comprehensive.
- Exit: Task 08C owns the feature/extra matrix, isolated install smoke, and PEP 621 migration; Task 10 decides unsupported surfaces.

### D28. MCP transport/session protocol is maintained in-framework
- `qitos.mcp.stdio/http` manually own JSON-RPC, protocol negotiation, request correlation, transport, and cleanup while an official Python SDK provides these facilities.
- Risk: protocol and lifecycle drift consume maintenance without differentiating QitOS.
- Exit: Task 09F runs a pinned parity spike; Task 10 adopts or explicitly defers the SDK behind the existing QitOS tool bridge.

### D29. Engine construction has multiple composition roots
- `Engine` has a reviewed 34-parameter signature including `self`; `runtime` is the S2 migration entry while historical checkpoint/action/context arguments still adapt into it. `AgentModule._merge_run_defaults` constructs concrete env/trace/render/parser objects through reverse lazy imports; `config/builder.py` is another assembly path; `EngineConfig` is not yet the construction contract.
- Risk: private protocols mirror shared mutable state and new mechanisms land in oversized owners.
- Exit: S2 establishes `RuntimeComposition` as the typed migration root while keeping Engine as the façade. Move repeated historical argument groups behind it, document deprecation before removing spelling, and do not add manager wrappers or another mutable root.

### D30. qita route/data/render ownership is untested and monolithic
- `_cli_app.py` is ~3,420 lines; the fork POST route references an undefined variable, while tests assert handler existence and HTML substrings rather than executing the route.
- Risk: user-facing behavior can be broken under a green suite; large embedded renderers make isolated change difficult.
- Exit: Task 08D adds route integration coverage; Task 10E splits only along proven route/data/render seams.
- D1 evidence (2026-08-29): qita board/replay/export, live-tail, replay grouping, and the deprecated debug fork dependency are mapped as v1 compatibility consumers in the Lane D census; no qita behavior or route was changed.

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
- **D31** `func`, CronScheduler, and PgVectorStore expose incomplete promises (inert retry/timeout knobs, ownerless executors, silent scheduler degradation, driver mismatch). Task 10 must complete, experimentalize, move, or deprecate them using consumer evidence.

## Explicit non-goals for debt cleanup

- No big-bone rewrites of the engine loop outside the already-planned v0.7 tasks.
- No renaming of public API surface (`qitos.core`/`qitos.engine` names stay).
- No removal of the v1 trace format before the trajectory data plane (v4/05) lands a versioned replacement.
- No repository-wide mechanical lint/type cleanup in the same PR as runtime behavior changes; Task 08 uses a ratchet.
- No generic `utils.py`/`common.py`; consolidation follows a named contract owner.

## Documentation-discovered handoff scheduling boundary

At runtime source 60809b3, a same-Session handoff destination that restores inside
the source LocalWorkScheduler callback can claim the head before the source
terminal callback persists, causing an owner CAS conflict. The teaching example
serializes transfer admission, source cleanup and destination execution. Concurrent
same-head dispatch requires separate runtime investigation; see
[reproduction and scope](../internal/plans/docs_self_contained_learning.md).
No runtime or ownership checks were weakened for the tutorial.

Lane C follow-up: the fixed `4dfb570` baseline reproduced this conflict with
SQLite and process Events. Admission now commits before scheduler invocation;
source callbacks do not write the transferred head, and the destination records
ownership/execution/terminal facts through the existing CAS. Both serial and
concurrent installed examples are exercised. See the
[Lane C evidence](../internal/plans/v5_r1_c_execution.md). This does not provide
a distributed scheduler, automatic replay of unknown effects, or external exactly-once.

The same lane's tests also exposed existing `CodingToolSet(auto_approve=True)`
mutation of shared tool metadata. That broader permission-authority issue remains
open; Lane C tests use executor-scoped approval instead and do not change the
permission implementation.
