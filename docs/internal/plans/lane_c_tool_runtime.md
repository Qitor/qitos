# Lane C C1 — canonical tool outcome and runtime ownership

Status: C1-R4 in progress; C-P4 forced-secret scalar repair required
Integration baseline: `8441bef2f2024fd6c2ec01784708512222382471`
C1 source HEAD: `1a36349b425e8c39d87b89e71ad4dcabd23d9e30`
Branch: `codex/v4-lane-c-contract-hardening`
Worktree: `/Users/morinop/Desktop/WhitzardOS-lane-c2`
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

## C1-R review-blocker closure

C1-R is limited to C-P1, C-S1, C-V1, and the ToolResult-specific portion of
C-D1. It does not authorize coding-tool behavior refactors, checkpoint
durability changes, MCP migration, trace-v1/qita changes, provider/request-view
changes, or a universal lifecycle interface.

- [x] Create the worktree at the integration baseline and cherry-pick all four
  C1 source commits in order, preserving both sides of shared docs.
- [x] Split strict canonical persistence, explicit legacy flattening, model
  allowlist, and trace-safe views.
- [x] Fail canonical v1 closed on unknown version/field, malformed collection,
  contradictory state, invalid types/ranges, and non-JSON values.
- [x] Replace Action/Env full-dictionary model projection with the allowlist and
  enforce per-result plus aggregate text budgets.
- [x] Inventory the repository schema subset and make malformed schemas fail
  before execution with a distinct code.
- [x] Revalidate interceptor and permission-pipeline argument rewrites.
- [x] Publish `contract_hardening.json` for Lane B/D and document the temporary
  ArtifactRef slot.
- [x] Keep `docs/progress.md` byte-for-byte outside the branch diff.
- [x] Complete final validation/static checks and record exact results below.
- [ ] Rebase onto the eventual Lane A integrated HEAD and run its ratchet.

## G1 integration-owner boundary repair

- [x] C-J1: reject arbitrary nested objects, non-string object keys, NaN,
  Infinity, and -Infinity at the initial executor/registry boundary before any
  interceptor, permission decision, or tool code.
- [x] C-I1: recursively detach constructor, canonical-reader, legacy-reader,
  canonical serializer, and explicit legacy serializer values in both mutation
  directions.
- [x] C-P2: apply one bounded redaction path to model output, error, recovery
  hint, tool/action/error identifiers, and next action, with aggregate and
  per-field trace loss facts.
- [x] Publish producer-owned qualification evidence beside the versioned fixture
  for Lane D to verify against an exact committed producer source.
- [x] C-P3: sanitize sensitive mapping keys recursively in model/trace views,
  replace raw trace-safe omitted keys with a deterministic collision-safe
  representation, and include both in aggregate/per-field loss facts.
- [x] Prove C-P3 through nested output, next-action, omitted, and ExchangeLog
  consumer regression tests, then republish exact producer evidence if changed.

The earlier source-branch rebase gate is satisfied by the G1 integration branch:
the Lane A ratchet passed with 399 baselined findings (377 active and 22
vendored/generated). The combined gates are green at the reviewed convergence
source. C-P3 is closed by core commit `94bfe80aae110f6ee7471478e6ab7eabdc13bba1`
and producer commit `d50f41fb3b8190a953f9f37f278bf0b197af286b`.
Sensitive keys now use deterministic collision-safe ordinal placeholders,
trace-safe omitted entries share the remaining budget, and `redacted_keys` plus
omitted facts reconcile per field and in aggregate. The C fixture/evidence
SHA-256 values are respectively
`a3eccdbf4d0c5da282c8118ea8308b901216415e4e26bd44bb9c2f3dde8e5775`
and `16ace4464b4c5325f63ed9a9092eef00701cc15f35d0f691a07f5043dc438a19`.

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

## C1-R shared-file lease

Lease owner: Lane C / C1-R

File(s): `CHANGELOG.md`, `README.md`, `README.zh.md`,
`docs/v4/03-aci-toolset.md`,
`docs/v4/09-runtime-lifecycle-and-error-semantics.md`,
`docs/architecture/tool-outcome-and-runtime-ownership.md`, and the single
missing-slot constructor in `qitos/engine/engine.py`

Semantic purpose: close the reviewed canonical serialization, model projection,
schema-contract, and ToolResult trace-safe handoff blockers.

Expected start/end package: C1-R only.

Other lanes blocked or adapter supplied: Lane B receives canonical/legacy/model
entrypoints and ArtifactRef-slot shape; Lane D receives only the versioned
ToolResult trace-safe fixture. No provider, RequestView, trace-v1, qita, or
durability behavior is changed.

## Validation evidence

Completed on the C1-R source identity above:

- `tests/core/test_tool_result.py`: `34 passed`;
- `tests/core/test_tool_structural_validation.py`: `23 passed`;
- `tests/engine/test_tool_result_projection.py`: `3 passed`;
- `tests/engine`: `199 passed`;
- real registry/permission substitute (`tests/test_tool_registry_and_toolset.py`
  plus `tests/test_permission_pipeline.py`): `85 passed`;
- deterministic durability race: `1 passed`;
- architecture and public-surface gates: `4 passed` each;
- full suite: `1756 passed, 50 skipped`;
- stable flake8 command: zero findings;
- stable mypy command: `Success: no issues found in 76 source files`;
- `git diff --check`: clean.

The final Lane A rebase/ratchet gate remains intentionally open because its
integrated command/baseline is not present on this C1 source branch.
