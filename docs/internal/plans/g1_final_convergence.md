# G1 final convergence plan

Status: active
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

## Current stage

- [x] Confirm integration checkout is clean at the fixed baseline.
- [x] Create the isolated worktree and branch directly from the fixed baseline.
- [x] Read root/nested agent rules, architecture, task designs, progress ledger,
      and all four Lane plans/fixtures/evidence.
- [x] Integrate Lane A and close A-CI1.
- [x] Integrate Lane C and close C-J1, C-I1, and C-P2.
- [x] Integrate Lane B and close B-C1 and B-V1 against accepted C.
- [ ] Integrate Lane D and close D-R1 against accepted B/C fixtures.
- [ ] Run combined reviewer probes and qualification matrix.
- [ ] Synchronize progress/task evidence, README EN/zh, and changelog.
- [ ] Close G1 only if every checklist item passes and the worktree is clean.

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
- C-P2: every model/trace-visible field uses one bounded redaction path, with
  aggregate and per-field loss facts covering model output, error, recovery
  hint, identifiers, and next action.

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
`git diff --check` were clean. The B-C1/B-V1 fixing commit is recorded after
this plan update.

### Lane D integration and D-R1

Pending. Required repair: reviewed authorities and receipts bound to contract
ID, version, producer commit, exact committed fixture path and digest, plus
producer-owned qualification evidence. Unimplemented dependencies remain typed
blocked and trajectory v2 remains unfrozen.

## Reviewer probes

- [ ] Workflow qualification entrypoint imports and executes successfully.
- [x] Nested arbitrary objects, NaN, Infinity, and -Infinity fail pre-execution.
- [x] ToolResult caller/serialization mutations are isolated in both directions.
- [x] Tokens and host paths cannot survive any model/trace-visible field.
- [x] Trace loss accounts for output, error, hint, next action, and identifiers.
- [x] Every malformed ExchangeLog v2 input fails with the typed conversation error.
- [x] ExchangeLog directly round-trips the exact C canonical fixture.
- [ ] Forged receipt digest/path/commit/version/authority cannot clear a blocker.
- [ ] Exact committed B/C receipts clear only their owned blockers.

## Qualification matrix

Each phase records exact commands/counts before the next phase starts. Combined
qualification includes all targeted suites named in the G1 instruction,
stable flake8/mypy with Python 3.12.7 and the pinned tools, the full-package
ratchet, the full pytest suite, architecture/public-surface/no-local-path gates,
both readiness script exit modes, reviewer probes, and `git diff --check`.

Automatic reruns, `|| true`, masked exits, live keys/models, pushes, deploys,
server 149, and regenerated substitute source commits are prohibited.

## G1 checklist

- [ ] All supplied Lane commits are present with source identity preserved.
- [x] A-CI1 has an executable shared entrypoint and controlled failure proof.
- [ ] Pinned ratchet and stable flake8/mypy are green on the combined tree.
- [x] ToolResult is the only canonical outcome and has strict JSON/ownership rules.
- [x] Model/trace views are allowlisted, bounded, redacted, and loss-accounted.
- [x] ExchangeLog uses C serializers and has a typed strict v2 reader.
- [ ] D receipts verify exact committed producer evidence and clear one blocker only.
- [x] Cross-lane fixture tests consume real producer artifacts.
- [ ] Full suite, boundary, public surface, no-local-path, and diff checks pass.
- [ ] Required documentation is synchronized without implementing Task 12/13.
- [ ] Final branch status is clean.

## Remaining blockers

Two reviewed blockers (D-R1 and combined G1 qualification) remain
open until their integration-owned fixing commits and regression evidence are
recorded above. Consequently G1 is open and S1 dispatch is blocked.
