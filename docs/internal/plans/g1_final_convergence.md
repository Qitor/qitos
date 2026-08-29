# G1 final convergence plan

Status: integrated candidate; G1 reopened on C-P3 after independent audit
Updated: 2026-08-29
Owner: G1 integration owner
Branch: `codex/v4-g1-convergence`
Worktree: `/Users/morinop/Desktop/WhitzardOS-g1`
Fixed baseline: `a02ce05e9a364eb484ef339fe5cbd623910cf525`

## Objective and scope guard

Integrate the reviewed G1 candidates in the fixed semantic order A -> C -> B ->
D, close only the recorded A-CI1, C-J1/C-I1/C-P2, B-C1/B-V1, and D-R1
blockers, then qualify the combined tree. This plan does not authorize Task 02B,
03B-E, 05A schema freeze, Task 12/13 implementation, a provider-default flip,
trajectory v2, qita redesign, packaging migration, or new multi-agent behavior.

The integration owner resolves shared documents manually, preserves historical
audit evidence append-only, and does not reinterpret branch-local validation as
integrated qualification.

## Fixed source identities

| Phase | Branch | Reviewed HEAD | Commits applied in order |
|---|---|---|---|
| A | `codex/v4-lane-a-ci-trust` | `ec43f09c1d6926a146b2c3f80a4b351861c5ea87` | `f908d78`, `4d84237`, `9082f5f`, `92262f8`, `4747bc2`, `afdb88a`, `ec43f09` |
| C | `codex/v4-lane-c-contract-hardening` | `86ad165cef56262d0d5b58e095a1452f8201bc79` | `9a284c2`, `3d86bf1`, `5602ca6`, `39be089`, `86bdb42`, `5d6b40e`, `86ad165` |
| B | `codex/v4-lane-b-exchange-integrity` | `5b0e8d54ab9dc95746b9e30fb2ce97a6165f0390` | `d1b6c05`, `adf036c`, `3d3e5b2`, `2561ef2`, `e1174c5`, `5b0e8d5` |
| D | `codex/v4-lane-d-evidence-gates` | `d80f4cc7e7c1532c33ea0cf057435447bf9261e7` | `f48605d`, `82bb7bc`, `f6969d0`, `140c3b8`, `e284757`, `d80f4cc` |

Full SHAs remain authoritative; abbreviations above are display-only. Every
cherry-pick is checked against the supplied full identity before execution.
The integrated commits intentionally have new SHAs. Post-convergence patch-id
comparison found 18 of the 26 source/integrated pairs exact; the remaining eight
are shared documentation/evidence commits with manual conflict resolutions.
The original 26 source SHAs are not ancestors of the convergence HEAD, so
“source identity preserved” is not used as a reachability claim.

## Current stage

- [x] Confirm integration checkout is clean at the fixed baseline.
- [x] Create the isolated worktree and branch directly from the fixed baseline.
- [x] Read root/nested agent rules, architecture, task designs, progress ledger,
      and all four Lane plans/fixtures/evidence.
- [x] Integrate Lane A and close A-CI1.
- [x] Integrate Lane C and close C-J1, C-I1, and C-P2.
- [x] Integrate Lane B and close B-C1 and B-V1 against accepted C.
- [x] Integrate Lane D and close D-R1 against accepted B/C fixtures.
- [x] Run combined reviewer probes and qualification matrix.
- [x] Synchronize progress/task evidence, README EN/zh, and changelog.
- [ ] Reclose G1 only after C-P3 and the combined requalification pass.

## Conflict policy

Expected shared conflicts are `README.md`, `README.zh.md`, `CHANGELOG.md`,
`docs/progress.md`, `docs/v4/*`, and `docs/internal/plans/*`. Resolve individual
hunks; never replace a whole file with ours/theirs. Preserve the fixed
baseline's Task 12/13 design and post-G1 lane map, each Lane's implementation
and evidence, and branch-local versus integrated status distinctions.

Semantic ownership for any unexpected code conflict is fixed: A owns ratchet/CI,
C owns ToolResult/outcome, B owns ExchangeLog/conversation, and D owns trajectory
readiness. A blocker is closed only by a fixing commit plus executable regression
coverage.

## Stage records

### Pre-integration audit

- Baseline branch/status: `feat/campaign-absorption`, clean.
- Baseline HEAD/subject: `a02ce05e9a364eb484ef339fe5cbd623910cf525`,
  `docs(v4): plan durable sessions and multi-agent runtime`.
- All supplied commits and four reviewed HEADs resolve to commit objects.
- Candidate worktrees `WhitzardOS-lane-a2`, `-b2`, `-c2`, and `-d2` point to the
  supplied reviewed HEADs.
- Remaining blockers reproduced in the existing integration ledger: A-CI1,
  C-J1, C-I1, C-P2, B-C1, B-V1, and D-R1.

### Lane A integration and A-CI1

Applied all seven supplied Lane A commits in order. Conflicts occurred only in
`README.md`, `README.zh.md`, and `CHANGELOG.md`; each hunk retained Task 12/13,
the post-G1 lane map, integration-ledger wording, and Lane A evidence.

A-CI1 fixing commit: `f145cbe`.

- Replaced the broken inline import/check with
  `python scripts/qualify_tool_schemas.py`.
- The entrypoint imports 61 real repository tool modules, identifies 74 public
  class definitions, constructs and validates 62 class tools, and registers all
  62 through the real `ToolRegistry`; 12 constructor-dependent classes remain
  inventoried rather than fabricated.
- Repository tests execute the exact workflow entrypoint as a subprocess and
  assert non-empty module/class/registration inventories.
- A controlled JSON fixture with an empty tool name executes the same entrypoint,
  exits 1, and returns stable `invalid_tool_name` evidence.
- Python 3.12.7 pinned ratchet: 399 findings matched (377 active, 22 vendored).
- Phase gate tests: 20 ratchet, 8 workflow, 4 architecture, and 4 public-surface
  tests passed. No automatic rerun or masked command was used.

### Lane C integration and boundary repairs

Applied all seven supplied Lane C commits in order after accepted A. Shared-file
conflicts preserved the fixed baseline Task 12/13 designs and the post-G1 lane
map. The integration repair then closed all three reviewed blockers:

- C-J1: recursive JSON admission rejects arbitrary objects, non-string keys,
  NaN, Infinity, and -Infinity before interceptor, permission, or execution;
- C-I1: construction, strict canonical read, named legacy adaptation, canonical
  serialization, and explicit legacy serialization recursively detach values;
- C-P2: scalar model/trace-visible values use one bounded redaction path, with
  aggregate and per-field loss facts covering model output, error, recovery
  hint, identifiers, and next action. The stronger mapping-key/omitted-key
  invariant was not covered and is reopened below as C-P3.

Producer-owned qualification evidence is published beside the C fixture for
Lane D's later commit/path/digest/authority verification. C-J1 fixing commit:
`c509bd0`; C-I1/C-P2 fixing commit: `ab1c501`.

Phase evidence: 75 ToolResult/structural/projection tests passed; the stable
flake8 gate was clean; the repository ratchet passed with 399 findings (377
active and 22 vendored/generated); `git diff --check` was clean. No automatic
rerun or masked exit was used.

### Lane B integration and B/C convergence

Applied all six supplied Lane B commits in order after accepted C. B-C1 removed
the temporary result enum and the duplicate content/status/error/provenance
envelope: ToolResultItem now owns only correlation and closure facts around the
sole canonical ToolResult. Persistence, model, and trace-safe result mappings
call C's public entrypoints directly.

B-V1 publishes strict `qitos.exchange_log.v2`: prior envelopes, unknown fields,
wrong shapes/types, non-JSON values, non-finite numbers, and malformed nested C
results all raise `ConversationValidationError`. The v3 producer fixture and
evidence directly consume and round-trip C's committed canonical fixture.

Phase evidence: 29 conversation tests and 71 combined B/C projection tests
passed; stable mypy succeeded on 77 source files; stable flake8 and
`git diff --check` were clean. B-C1/B-V1 fixing commit: `2e46fc8`.

### Lane D integration and D-R1

Applied all six supplied Lane D commits in order after accepted B/C. D-R1 no
longer accepts caller-owned `qualified=true`: qualification is derived only
from the reviewed authority, pinned producer contract/version and commit, exact
repository-relative fixture/evidence paths, current and committed byte hashes,
and matching producer-owned evidence.

The committed receipt set binds B `2e46fc8` and C `ab1c501` and qualifies only
their two owned contracts. Forged digest, evidence digest, path, source commit,
version, authority, or producer contract ID is a typed blocker. Default input
still qualifies no contracts. The JSON Schema and executable manifest validator
share a full accepted/rejected parity corpus. Both CLI modes retain
`schema_not_ready`, zero publication-qualified fixtures, and empty measurements
and claims; normal exits 2 and dry-run exits 0. Trajectory v2 remains unfrozen.
D-R1 fixing commit: `30c1823`.

### Combined G1 qualification

Reviewer suites passed with counts 20 static-ratchet, 8 workflow-contract, 39
ToolResult, 24 tool-schema, 29 conversation, 3 projection, 35 trajectory
readiness, 2 Lane D source-link, 4 architecture, 4 public-surface, and 2
no-local-path tests. The stable flake8 command was clean; stable mypy succeeded
on 77 source files; the full-package ratchet matched 399 findings (377 active,
22 vendored/generated); the full suite passed with 1863 passed and 50 skipped;
`git diff --check` was clean.

The initial combined command stopped after the first three passing suites
because the integration owner mistyped `test_tool_schema.py` as the nonexistent
`test_schema.py`. No code test failed, no test was automatically rerun, and no
exit was masked; qualification resumed from the correct original fourth command.
The real workflow entrypoint then reported 61 imported modules, 74 class
definitions, and 62 qualified/registered class tools; the same entrypoint's
controlled invalid spec exited 1 with `invalid_tool_name`.

## Reviewer probes

- [x] Workflow qualification entrypoint imports and executes successfully.
- [x] A controlled invalid tool spec fails the same entrypoint.
- [x] Nested arbitrary objects, NaN, Infinity, and -Infinity fail pre-execution.
- [x] ToolResult caller/serialization mutations are isolated in both directions.
- [ ] Tokens and host paths cannot survive mapping keys in any
      model/trace-visible field (`C-P3`).
- [ ] Trace loss accounts for sensitive mapping keys and trace-safe omitted
      projection as well as output, error, hint, next action, and identifiers.
- [x] Every malformed ExchangeLog v2 input fails with the typed conversation error.
- [x] ExchangeLog directly round-trips the exact C canonical fixture.
- [x] Forged receipt digest/path/commit/version/authority cannot clear a blocker.
- [x] Exact committed B/C receipts clear only their owned blockers.

## Qualification matrix

Each phase records exact commands/counts before the next phase starts. Combined
qualification includes all targeted suites named in the G1 instruction,
stable flake8/mypy with Python 3.12.7 and the pinned tools, the full-package
ratchet, the full pytest suite, architecture/public-surface/no-local-path gates,
both readiness script exit modes, reviewer probes, and `git diff --check`.

Automatic reruns, `|| true`, masked exits, live keys/models, pushes, deploys,
server 149, and regenerated substitute source commits are prohibited.

## G1 checklist

- [x] All supplied Lane changes were applied in order by cherry-pick; source and
      integrated identities are recorded separately.
- [x] A-CI1 has an executable shared entrypoint and controlled failure proof.
- [x] Pinned ratchet and stable flake8/mypy are green on the combined tree.
- [x] ToolResult is the only canonical outcome and has strict JSON/ownership rules.
- [ ] Model/trace views redact sensitive keys and account for every projected
      loss (`C-P3`).
- [x] ExchangeLog uses C serializers and has a typed strict v2 reader.
- [x] D receipts verify exact committed producer evidence and clear one blocker only.
- [x] Cross-lane fixture tests consume real producer artifacts.
- [x] Full suite, boundary, public surface, no-local-path, and diff checks pass.
- [x] Required documentation is synchronized without implementing Task 12/13.
- [x] Final branch status is clean.

## Post-convergence independent audit

The code and gate evidence above were independently rerun at
`587f34b76245e71fe3362a51dbad40895d7c43c5`. The 179 targeted tests, full suite
(`1863 passed, 50 skipped`), pinned ratchet, stable lint/type gates,
tool-schema qualification, and both trajectory readiness modes passed.

Two report corrections are required:

1. ordered cherry-picks do not make the 26 original source SHAs ancestors of
   the convergence HEAD. Eighteen integrated commits are patch-id equivalent;
   eight documentation/evidence commits contain manual conflict resolutions and
   therefore have distinct patches and SHAs;
2. adversarial probes found that `_redact_value()` preserves mapping keys and
   trace-safe serialization copies `omitted` keys outside the shared projection.
   Host paths and token-like text can remain visible with zero reported loss.

## Remaining blocker

`C-P3` is the sole newly reproduced G1 blocker. Lane C must sanitize sensitive
mapping keys recursively, define a safe trace representation for omitted data,
and include both in loss accounting. B must rerun delegated projection tests;
D must refresh exact receipts if C producer fixtures/evidence change. The full
combined matrix must then pass again. Until that record exists, G1 is open and
S1 capability-lane dispatch is not authorized.

Task 02B, 03B–E, 04/05A, Task 12/13 runtime, trajectory v2, qita redesign,
provider-default changes, and packaging work remain separate future packages.
