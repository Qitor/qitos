# Task 03 — tool outcome contract and coding-toolset consolidation

Status: 03A contract and C1-R hardening integrated for G1 repair; 03B–E remain staged
Depends on: Task 01
Feeds: Task 04 artifacts, Task 12 recovery, Task 13 work outcomes, and v4 DX
Risk: medium — broad kit surface, stable tool-result compatibility

---

## 1. Goal

Make QitOS's existing coding tools reliable enough for long-horizon agents while
turning proven recovery, pagination, budgeting, and effect reporting into generic
contracts. The result must reduce out-of-tree glue without introducing a second
tool hierarchy.

## 2. Package decision

Do not create `qitos.kit.aci`.

- contracts stay in `qitos.core` only when they are provider/domain neutral;
- atomic tools stay in `qitos/kit/tool/<domain>/`;
- presets/factories stay in `qitos/kit/toolset/`;
- the existing `coding_tools()`/`CodingToolSet` surface remains the migration
  entrypoint;
- old aliases are deprecated only after their callers and tests migrate.

## 3. Tool-result contract

Evolve the existing `ToolResult`; do not add a wrapper envelope that duplicates
status/output/error/metadata.

The target contract must represent:

- canonical structured output;
- model-facing content/projection;
- stable error code and recoverability;
- copyable `next_action` with validated arguments;
- completeness and explicit truncation/omission counts;
- declared effects, including filesystem changes;
- artifact references;
- normalized request and timing metadata;
- attempt/effect identity, idempotency/reconciliation facts, and explicit
  `outcome_unknown` when execution may have escaped without a trustworthy
  terminal receipt.

`model_summary` remains readable during migration, then becomes a compatibility
projection into the formal model-facing field. Trace/replay always retains the
canonical result subject to the configured privacy policy.

Task 12 persists terminal results per completed slot. Recovery must not rerun a
completed slot merely because another call in the batch is open, and a late
worker cannot commit to a superseded session generation. Task 13 uses the same
`ToolResult` for a child work outcome; it does not add another result envelope.

## 4. Validation decision

There is no `validation_mode="soft"` bypass.

- Engine/registry validates JSON shape, required keys, and declared primitive
  types before execution.
- Permission and security checks always remain hard gates.
- Semantic problems discovered by a tool—missing path, stale file version,
  invalid regex, unavailable backend—return a typed recoverable `ToolResult`.
- Programmer errors and schema-contract violations remain execution errors.

This preserves recovery guidance without making invalid schemas executable.

## 5. Tool-owned model projections

Avoid a hidden global renderer registry. A tool or injected renderer object owns
the conversion from its canonical output to model-facing content. Generic
fallback rendering is deterministic and vocabulary-free. Error results use the
same tool-owned projection path as success results.

## 6. Coding tool behavior

Refactor the current implementation in place. First-wave tools:

- `read`: numbered lines, line/page budget, explicit omissions, continuation;
- `grep`: literal default, safe `rg --json`, complete/no-match/partial status,
  context-aware page cap, backend attestation, no false absence inference;
- `glob`: explicit enumeration completeness and policy-exclusion diagnostics;
- `bash`: caller timeout honored, non-zero exit retained as evidence, separate
  stdout/stderr budgets, explicit head/tail truncation;
- `write`/`edit`: reuse the existing `ReadBeforeWriteEnforcer`, detect stale
  snapshots, report atomic effects, and make replace-all behavior explicit.

Second wave:

- task/todo operations using the existing task store;
- optional binary inspection tools such as hex view and structure probe;
- injected neutral path scorers or budgets, with no campaign ranking defaults.

Campaign-tuned numeric limits are measurements to evaluate, not universal
defaults. Defaults must be benchmarked and overridable by a typed toolset policy.

## 7. Known defects to close first

Before adding features, reproduce and fix these current compatibility-layer
problems:

- Read can apply offset twice;
- aliases sometimes inspect `error` while implementations return `message`;
- Grep renderer expects `file` while canonical hits use `path`;
- Edit does not consistently honor `replace_all`;
- Bash can ignore the per-call timeout;
- documented absolute-path behavior conflicts with some workspace resolvers.

Each defect gets a failing regression test before its fix.

## 8. Work packages

### 03A — result and validation contract

- Write an API decision record covering compatibility and serialization.
- Extend `ToolResult` and registry/executor projection paths.
- Add structural schema validation and typed semantic-error helpers.
- Preserve old result dictionaries and `model_summary` through adapters.
- Publish persistence/model/trace fixtures and effect-recovery fields for Tasks
  12 and 13.

Evidence (Lane C C1, 2026-08-29):

- ADR and compatibility/serialization decision:
  `docs/architecture/tool-outcome-and-runtime-ownership.md`;
- canonical schema: evolved `qitos.core.tool_result.ToolResult`, version
  `qitos.tool_result/v1`; `ActionResult.to_tool_result()` is the executor
  compatibility adapter;
- structural hard gate: `validate_tool_arguments()` plus registry/executor
  integration; semantic failures use typed `ToolResult` helpers;
- versioned Lane B/D fixtures: `tests/fixtures/tool_results/v1/`;
- contract/projection tests: `tests/core/test_tool_result.py`,
  `tests/core/test_tool_structural_validation.py`, and
  `tests/engine/test_tool_result_projection.py`.

C1-R hardening (2026-08-29) separates strict canonical persistence from
explicit legacy flattening and from allowlisted model/trace-safe views.
Canonical v1 now rejects unknown versions/fields, malformed slots,
contradictory terminal state, invalid scalar ranges, and non-JSON data. The
schema hard gate validates the repository's actual object/properties/required/
type/nesting/items/additionalProperties/anyOf/oneOf/enum/nullable subset and
fails malformed schemas with `schema_contract_violation` before tool code.
Interceptor and permission argument rewrites are revalidated. Cross-lane cases
are fixed in `tests/fixtures/tool_results/v1/contract_hardening.json`.

This evidence completes the C1/03A contract layer only. Coding-tool behavior,
durability implementation, MCP replacement, and executor lifecycle refactors
remain explicitly deferred.

### 03B — filesystem and search foundations

- Extract reusable workspace/path, budgeting, pagination, and backend services.
- Refactor Read, Grep, and Glob onto those services.
- Keep all host/container access behind Env capabilities.

### 03C — execution and mutation tools

- Refactor Bash, Write, and Edit.
- Reuse permission pipeline and read-before-write state.
- Add optimistic-staleness and effect-report tests.

### 03D — preset consolidation

- Make `coding_tools()` the canonical composition path.
- Migrate internal callers away from duplicated aliases.
- Add deprecation notes, examples, and a compact coding-agent smoke test.

### 03E — optional tools and measured defaults

- Add task/todo and binary tools only after the first wave is stable.
- Benchmark result sizes and call recovery on representative repositories.
- Promote only domain-neutral defaults.

## 9. Acceptance criteria

- [ ] Canonical results survive model projection, trace, and replay unchanged.
- [ ] Every truncation declares what was omitted and provides a continuation.
- [ ] Partial search never becomes a false no-match result.
- [ ] Semantic errors retain code, recovery hint, and next action.
- [ ] Read-before-write and stale-version behavior use one shared enforcer.
- [ ] Parallel safety derives from `ToolSpec`, never tool-name lists.
- [ ] Existing `coding_tools()` callers have a documented migration path.
- [ ] The compact example uses only public APIs.
- [ ] A non-campaign repository fixture exercises the same tools.
- [ ] A Task 12 recovery fixture distinguishes not-started, committed, failed,
      still-running, and outcome-unknown attempts without duplicating effects.
- [ ] Task 13 consumes the canonical result directly for child outcomes.

## 10. Verification

```bash
pytest -q tests/core/test_tool_result.py tests/engine/test_tool_result_projection.py
pytest -q tests/kit/tool tests/test_predefined_atomic_tools.py
pytest -q tests/test_permission_pipeline.py tests/engine/test_concurrent_execution.py
pytest -q
flake8 qitos/core qitos/engine qitos/kit
mypy qitos/core qitos/engine qitos/kit
```

Exact test paths may evolve with the package consolidation. Semantic assertions
are preferred over large golden Markdown snapshots.

## 11. Stop-and-escalate decisions

Stop for review before:

- adding a new top-level tool package or a second result envelope;
- weakening schema, permission, or security validation;
- introducing process-global registries;
- changing workspace escape/absolute-path policy;
- placing task-specific ranking or submission logic in the default toolset;
- claiming exactly-once external execution from a checkpoint without an
  idempotency or reconciliation receipt;
- creating a separate result envelope for session or multi-agent work.
