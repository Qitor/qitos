# Task 10 — consolidation and public-surface reduction

Status: staged; inventory may begin, destructive migration waits for owners
Depends on: Task 08; most work waits for the relevant Tasks 02–05 and 09 contracts
Risk: high — deprecation, imports, packaging, and user migration

---

## 1. Goal

Reduce QitOS to one understandable mainline after the new contracts are proven.
Remove deprecated cycles, speculative APIs, duplicate helpers, and concrete
implementations in the wrong layer without deleting externally used behavior by
guesswork.

This is not a cleanup sprint. Consolidation follows a usage inventory,
compatibility window, and a named canonical replacement.

## 2. Admission and removal criteria

A public surface belongs in the framework only when all are true:

1. it is expressible in domain-neutral agent-execution vocabulary;
2. it has a named owner and at least one documented consumer;
3. behavior, failure, lifecycle, and optional dependencies are tested;
4. it does not duplicate a canonical contract elsewhere;
5. it has a stable import path or an explicit experimental label;
6. its maintenance cost is proportionate to research value.

Before deprecating/removing a surface, inspect repository usage, docs/examples,
release notes, known out-of-tree consumers, and public issue/discussion evidence
where available. Record confidence and unknowns.

## 3. Work packages

### 10A — surface census and decision ledger

1. Write `docs/internal/plans/task10_consolidation.md`.
2. Generate an inventory of public exports, CLI commands, extras, plugin/registry
   entries, docs/examples, and deprecated shims.
3. Classify each as canonical, compatibility-only, experimental, recipe/zoo
   candidate, or removal candidate.
4. Create a decision record with consumer evidence, replacement, warning
   release, removal release, and owner.
5. Add tests that prevent accidental expansion of root exports and deprecated
   package imports.

Inventory work may start after Task 08. Removal work waits for replacement
contracts and maintainer approval.

#### D1 inventory evidence (2026-08-29)

Lane D completed the first repository evidence pass in
`docs/internal/plans/lane_d_data_convergence.md`. It inventories root/module
exports, CLI commands and entry points, extras, registries, docs/examples,
deprecated shims, benchmark/recipes, func, qita/debug, evaluate/metric,
leaderboard/HF, SharedMemory, CronScheduler, PgVectorStore, and MCP. The joined
removal ledger records current owner, internal and known/unknown external use,
replacement, semantic lane, adapter/warning/removal gates, tests, status, and
blockers.

This evidence does not classify an API as unused from repository grep and does
not authorize a removal. All warning and earliest-removal releases remain
unannounced/TBD where external usage or a canonical replacement is unknown.
Trajectory v2 schema is not frozen, so trace v1 and its readers remain outside
the removal set.

### 10B — finish benchmark-to-recipes migration

1. Map every `qitos.benchmark` import, CLI route, test, fixture, and packaged
   data file to its canonical recipe or external asset.
2. Eliminate `benchmark <-> recipes.benchmarks` reverse imports in reviewable
   benchmark groups.
3. Move large vendored ports/data to an optional package or clearly isolated
   third-party subtree with license/provenance and version metadata.
4. Provide compatibility imports that emit one actionable deprecation warning
   per process during the announced window.
5. Delete legacy code only after CLI and artifact compatibility tests pass and
   the architecture boundary allowlist shrinks.

Do not port new features into the deprecated tree.

### 10C — decide the functional API

Choose exactly one path based on consumer evidence:

- **complete and teach:** enforce retry/timeout, define Engine integration,
  own/close executors, type decorators correctly, add docs and a second
  consumer; or
- **experimentalize/deprecate:** remove it from stable exports and learning
  paths, provide a warning and migration to plain functions/AgentModule, then
  remove on schedule.

Do not keep `max_retries` and `timeout_s` as inert public parameters.

### 10D — correct boundaries and optional integrations

1. Replace the dataclass+dict `Observation` with the canonical record/projection
   established by Tasks 02/03, with compatibility tests.
2. Keep the `SharedMemory` contract in core; move concrete storage and namespace
   management to kit. Prove or withdraw the multi-process claim for file-backed
   storage.
3. Decide CronScheduler and PgVectorStore using Task 08's extras matrix: fully
   support with explicit degraded/error state, mark experimental, or remove.
4. Apply the Task 09 MCP SDK decision behind the existing QitOS bridge.
5. Revisit top-level evaluate/metric, leaderboard, and hf placement using the
   same admission criteria.

Every move includes an old-import compatibility test and an architecture
boundary update.

### 10E — split qita along tested ownership seams

Prerequisite: Task 08D route tests are green.

1. Separate run discovery/data loading from HTTP routing.
2. Separate board/run/replay rendering and static assets without changing
   generated behavior in the same commit.
3. Keep CLI dispatch thin and preserve command-line compatibility.
4. Add focused unit tests for data/query code and retain HTTP integration tests
   for the assembled server.
5. Remove the deprecated `qitos.debug` dependency by moving or promoting the
   replay/fork capability to its canonical owner.

File size is not an acceptance metric; dependency direction and test isolation
are.

### 10F — consolidate helpers after ownership is established

Remove superseded copies only after the owning tasks land:

- token estimation → Task 02/04 request-budget owner;
- JSON extraction/repair → Task 02 protocol/parser owner;
- action/tool result conversion → Task 03 outcome owner;
- JSONL append/read → Task 05 trace owner;
- process execution results → Task 03/env owner;
- OpenAI-compatible local transport → Task 02 provider owner;
- retry/backoff mechanics → Task 09 owner.

No `utils.py`, `common.py`, or dependency-free dumping ground may be introduced.

## 4. Migration rules

1. One canonical implementation is selected before compatibility adapters are
   written.
2. Adapters translate at the old boundary and delegate immediately; they do not
   contain new behavior.
3. Deprecation warnings identify replacement and earliest removal version.
4. Root/public export snapshots and import-order tests cover both new and old
   paths during the window.
5. Changelog, README, reference docs, examples, and EN/zh pages change in the
   same PR as a public migration.
6. Delete compatibility code only after usage evidence and release policy permit
   it.

## 5. Acceptance criteria

- [ ] `qitos.benchmark` no longer participates in a cycle and has an announced
  compatibility/removal state.
- [ ] Every stable root export has an owner, documentation, tests, and lifecycle
  semantics.
- [ ] `qitos.func` is complete and taught or explicitly experimental/deprecated;
  no inert policy knobs remain.
- [ ] `Observation` has one canonical state representation.
- [ ] Concrete shared-memory storage is outside core; persistence claims are
  tested accurately.
- [ ] Optional integrations match declared extras and cannot silently become
  inert.
- [ ] qita routes/data/rendering are independently testable and fork no longer
  depends on deprecated debug code.
- [ ] Duplicate token, JSON repair, JSONL, process, result, and retry helpers are
  removed only after their canonical owners land.
- [ ] Architecture boundary allowlists strictly shrink.
- [ ] Wheel contents and public import compatibility are verified.
- [ ] Full tests and Task 08 ratchets remain green throughout.

## 6. Verification

```bash
pytest -q tests/test_public_surface.py tests/test_architecture_boundaries.py
pytest -q
flake8 qitos
mypy qitos
python -m build
python -m twine check dist/*
```

Also run import-order smoke tests in fresh interpreters and the old/new import
compatibility matrix for each migrated surface.

## 7. Stop-and-escalate decisions

Stop for maintainer review before:

- deleting a public module, CLI command, registry entry, or packaged data;
- choosing “unused” based only on in-repository grep;
- adding another compatibility layer without a removal version;
- moving domain content into core/engine/kit for convenience;
- changing trace/checkpoint formats without the owning migration task;
- combining a behavior change with a large file move;
- retaining an unsupported feature by silently adding heavy dependencies.
