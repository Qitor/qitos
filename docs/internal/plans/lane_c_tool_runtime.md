# Lane C C1 — canonical tool outcome and runtime ownership

Status: C1 complete; Lane A rebase/ratchet gate open
Baseline: `fb75cd5902fedf50d5e67dd617e62cd981c3128f`
Branch: `codex/v4-lane-c-outcome-lifecycle`
Worktree: `/Users/morinop/Desktop/WhitzardOS-lane-c`
Work package: Task 03A contract layer + Task 09A lifecycle ownership matrix

## Scope and stop gates

This package evolves the existing `ToolResult`, adapts `ActionResult` at the
runtime boundary, adds structural argument validation, publishes versioned
fixtures, and records lifecycle/durability decisions. It does not refactor
Read/Grep/Glob/Bash/Edit/Write, change checkpoint durability behavior or
`put()` return types, replace MCP transports, change provider/history/trace
schemas, or add a universal lifecycle interface.

Implementation beyond the contract and compatibility boundary remains gated on
Lane A's integrated ratchet. This branch must not be described as merge-ready
until it is rebased onto that ratchet and the ratchet command passes.

## Shared-file leases

Lease owner: Lane C / C1

File(s): `CHANGELOG.md`, `README.md`, `README.zh.md`

Semantic purpose: announce the canonical result contract, validation boundary,
and published cross-lane fixtures.

Expected start/end package: C1 documentation synchronization only.

Other lanes blocked or adapter supplied: no code owner is blocked; additions
are confined to the existing Unreleased/What's New sections.

Lease owner: Lane C / C1

File(s): `docs/v4/03-aci-toolset.md`,
`docs/v4/09-runtime-lifecycle-and-error-semantics.md`, `ARCHITECTURE.md`

Semantic purpose: record C1 evidence and status without changing later work
packages or their ownership.

Expected start/end package: C1 outcome/lifecycle evidence.

Other lanes blocked or adapter supplied: Lane B/D consume versioned fixtures;
no Task 04/05 schema is edited.

## Decisions

1. `ToolResult` is the only canonical action/tool outcome. Its serialized
   schema version is `qitos.tool_result/v1`.
2. `ActionResult` remains an executor compatibility record. The action runtime
   immediately adapts it through `ToolResult.from_action_result()`; a nested
   `ToolResult` returned by a tool remains authoritative.
3. Status is closed to `success`, `error`, `skipped`, `timed_out`, and
   `cancelled`. Semantic and execution failures share the envelope but are
   discriminated by `error_kind` and stable `error_code`.
4. `model_output` is the explicit model-facing projection. Legacy
   `output.model_summary` is accepted by the adapter and projected without
   changing canonical `output`.
5. `artifact_refs` is a provider-neutral serialized slot (`list[dict]`) until
   Lane B publishes the canonical `ArtifactRef` type. It deliberately does not
   define a competing artifact class.
6. Structural JSON shape, required fields, declared primitive types,
   permission, and security policy are pre-execution hard gates. Tool-discovered
   domain problems use `ToolResult.semantic_error()` after dispatch. There is
   no soft validation mode.
7. Resource families retain their native lifecycle methods. The ownership
   matrix is documentation/test vocabulary, not a universal public protocol.
8. Task 09D owns durability behavior. C1 records the race and receipt fixture
   vocabulary but does not change `DurabilityManager`.

## Implementation sequence

- [x] Verify clean source identity and read required architecture/task sources.
- [x] Land ADR, lifecycle ownership matrix, and validation boundary.
- [x] Evolve `ToolResult` and add ActionResult/legacy adapters.
- [x] Add structural validation helper and wire existing registry/executor gates.
- [x] Add versioned outcome/durability/lifecycle fixtures and contract tests.
- [x] Add a deterministic durability race-window proof without behavior change.
- [x] Publish Lane B and Lane D handoff locations/redaction requirements.
- [x] Synchronize docs, README EN/zh, and CHANGELOG.
- [x] Run required targeted/full/static validation and review the diff.
- [ ] Rebase/run Lane A ratchet when integrated; until then report the gate open.

## Lifecycle vocabulary

- Resource states: `new -> opening -> open -> closing -> closed`, plus `failed`.
- Work states: `submitted -> accepted -> running ->
  succeeded|failed|timed_out|cancelled|dropped`.
- Durability states: `accepted -> queued -> persisted|failed|dropped`.
- Shutdown guarantees: `drained`, `abandoned`, `still_running`, with deadline.
- Failure receipt fields: `phase`, `category`, `retryable`, `safe_to_retry`,
  redacted diagnostic, correlation IDs, and source-exception class only.

Detailed ownership rows and fixture handoffs are maintained in
`docs/architecture/tool-outcome-and-runtime-ownership.md`.

## Validation evidence

Completed on the source identity above:

- new result/validation/lifecycle tests: `20 passed`;
- result/model projection plus Engine compatibility group: `50 passed`;
- tool migration, permission, registry, and core-flow group: `114 passed`;
- `tests/test_bounded_queues.py`: `8 passed`;
- `tests/engine`: `199 passed`;
- `tests/checkpoint tests/mcp`: `59 passed`;
- architecture/public-surface gates: `8 passed`;
- full suite: `1714 passed, 50 skipped`;
- stable flake8 command: zero findings;
- stable mypy command: `Success: no issues found in 76 source files`;
- `git diff --check`: clean.

The final Lane A rebase/ratchet gate remains intentionally open because its
integrated command/baseline is not present on this C1 source branch.
