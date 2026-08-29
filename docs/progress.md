# v4 integration progress

Status: active integration ledger
Updated: 2026-08-29
Integration branch: `feat/campaign-absorption`
Integration HEAD: `fb75cd5902fedf50d5e67dd617e62cd981c3128f`
Source plan: [`docs/v4/11-four-lane-execution-playbook.md`](v4/11-four-lane-execution-playbook.md)

## 1. Purpose and maintenance rule

This file is the integration owner's continuously growing record for the v4
program. Lane plans and completion reports remain evidence, but they do not
change integration status by themselves.

Maintain it with these rules:

- record the exact source commit for every reviewed package;
- distinguish agent-reported validation from integration-owner reruns;
- do not mark a package integrated until its commits are present in the
  integration branch and the integrated gates pass;
- keep review findings until a fixing commit and regression test close them;
- append dated validation/integration entries rather than replacing historical
  evidence;
- update the current dashboard and next merge sequence after every accepted
  package.

## 2. Current decision

Gate G1 is **not closed**. All four first-wave branches are clean descendants of
the W1 baseline and contain useful work, but none is present in the integration
branch yet.

Lane A is the first integration candidate. Lanes B, C, and D require a short
contract-convergence package before they may be described as merge-ready. The
important issue is semantic, not a textual merge problem: pairwise branch
inspection found only `CHANGELOG.md`, `README.md`, and `README.zh.md` as shared
changed files, but Lane B and Lane C currently define incompatible tool-result
representations.

| Lane | Reviewed HEAD | Package | Integration disposition | Next package |
|---|---|---|---|---|
| A | `ab25edf9c6457ee40054aaaab4596d7bed30cbe5` | 08A / A1 | Candidate; rerun pinned ratchet after integration | A1-I, then 08E / A2 |
| B | `69a961f6f50656dff308db7a2f3e400439ef20d0` | 02A / B1 | Changes requested | B1-R contract integrity and C alignment |
| C | `1a36349b425e8c39d87b89e71ad4dcabd23d9e30` | 03A + 09A / C1 | Changes requested | C1-R canonical serialization and projection safety |
| D | `ad03cb0b63c62e2067a222d654f3879ba7c01bb5` | 10A + 05A readiness / D1 | Evidence useful; changes requested before integration | D1-R evidence-gate hardening |

## 3. Source and validation evidence

All four branches have merge-base
`fb75cd5902fedf50d5e67dd617e62cd981c3128f`, the W1 integration baseline.
Their worktrees were clean when reviewed.

| Lane | Worktree | Agent-reported full suite | Integration-owner targeted rerun |
|---|---|---:|---:|
| A | `WhitzardOS-lane-a` (local sibling) | 1,703 passed, 50 skipped | 17 passed |
| B | `WhitzardOS-lane-b` (local sibling) | 1,714 passed, 50 skipped | 28 passed |
| C | `WhitzardOS-lane-c` (local sibling) | 1,714 passed, 50 skipped | 28 passed |
| D | `WhitzardOS-lane-d` (local sibling) | 1,696 passed, 50 skipped | 107 passed |

The targeted reruns covered each new contract/scaffold plus architecture and
public-surface gates. `git diff --check` passed for every lane diff. The current
integration-owner shell uses Python 3.13.3 and does not have the pinned flake8
distribution, so it could not independently rerun Lane A's Python 3.12.7
ratchet. This is an environment limitation, not a replacement for the reported
ratchet result; the pinned command remains an integration gate.

## 4. Review findings

### 4.1 Lane A — quality ratchet

What is sound:

- the full-package diagnostic is separate from the zero-debt stable-surface
  checks;
- finding identity does not depend on line number alone;
- stale allowances, new findings, malformed diagnostics, expired exceptions,
  and toolchain drift have explicit failure paths;
- CI does not mask the new jobs with `|| true` or automatic reruns;
- no runtime, public API, or packaging semantics changed.

Open follow-up `A-Q1` (non-blocking for initial integration):

- `tests/test_static_quality_ratchet.py` tests parsers, identity,
  classification, exception fields, and toolchain mismatch, but the committed
  unit suite does not directly exercise `check()` for new findings, stale
  allowances, base-ref growth, and bootstrap/base-ref failure. The manual F401
  probe is good evidence; A2 should turn the critical ratchet transitions into
  deterministic tests.

Disposition: integrate A1 first, resolve the three shared documentation files,
install the pinned toolchain, and run `python scripts/static_quality.py check`
against the integrated tree before publishing the new baseline as active.

### 4.2 Lane B — conversation contract

What is sound:

- ordered assistant parts retain content, reasoning references, and tool calls;
- raw versus parsed arguments and provider-scoped call identity are explicit;
- out-of-order completion is correlated by call ID and projected in declaration
  order;
- mid-batch steering is queued and opaque continuation is not converted into
  assistant reasoning text;
- the module is not root-exported and does not prematurely modify Engine or
  provider behavior.

Gate blocker `B-C1` — duplicate result semantics:

- `qitos/core/conversation.py::ToolResultStatus` uses `succeeded`, `failed`,
  `permission_blocked`, `timed_out`, `cancelled`, and `missing_worker`;
- `qitos/core/tool_result.py::ToolResult` on Lane C uses `success`, `error`,
  `skipped`, `timed_out`, and `cancelled`, plus `error_kind` and `error_code`;
- `ToolResultItem` stores a second content/status/provenance result envelope
  rather than carrying or adapting the canonical outcome.

Task 02 and Task 03 cannot both call these representations canonical. Lane C
owns the execution outcome. Lane B must consume that outcome and keep only
conversation-specific call/batch/closure identity.

Gate blocker `B-I1` — append-only integrity is not enforced:

- frozen dataclasses contain mutable lists and dictionaries;
- `ExchangeLog.items` returns the internal item objects inside a tuple;
- a caller can append to `UserItem.content` or mutate `metadata`, changing a
  previously committed fact without an `append()` call. A reviewer probe
  changed a one-block committed item into two blocks through the returned
  object and the serialized log reflected the mutation.

Gate blocker `B-P1` — the safe projection name overclaims privacy:

- `OpaqueContinuationAttachment.to_safe_dict()` redacts only
  `opaque_payload`;
- ordinary item metadata, tool arguments, result content, and provenance
  details pass through unchanged;
- a reviewer probe placed `{"token": "secret"}` in item metadata and
  `ExchangeLog.to_safe_dict()` returned it unchanged.

This method may be a continuation-redacted diagnostic view, but it is not a
general public/privacy-safe projection until it applies a versioned policy and
returns a loss report.

Gate blocker `B-R1` — partial parallel completion has no durable form:

- `ToolBatchBuilder.record_result()` keeps results only in its private
  `_results` mapping until every slot closes;
- after one of two calls completed, `results_for_batch()` returned zero and
  persistence contained only the assistant declaration;
- a crash/checkpoint between completions therefore loses already completed
  slot facts. Task 02D must not discover this only after Engine migration.

Follow-up `B-T1`: the two claimed independent consumers are two test functions
in `tests/core/test_conversation.py` that simulate Lane C and Lane D. They are
useful fixture tests, but Gate B still requires actual execution and
trajectory/request consumers after cross-lane integration.

Disposition: do not integrate B1 as the accepted canonical contract. Land a
B1-R package that isolates internal state from caller mutation, names or
implements projections honestly, defines crash-safe partial-batch persistence,
and consumes Lane C's reviewed result serialization.

### 4.3 Lane C — tool outcome and lifecycle contract

What is sound:

- the existing `ToolResult` is evolved instead of adding a new top-level
  package;
- `ActionResult` has a named compatibility adapter;
- timeout/cancellation/skip states and `worker_still_running` survive the
  adapter;
- the structural argument gate executes before tool code in the executor and
  standalone registry path;
- the ownership matrix correctly rejects a fake universal lifecycle interface;
- the durability race reproducer explains a real scheduling window without
  changing durability behavior.

Gate blocker `C-P1` — model projection is not a strict safe view:

- `_ActionRuntime._model_visible_tool_result_dict()` and the matching Env path
  replace `output` with `model_output`, but retain `metadata`,
  `normalized_request`, `provenance`, `artifact_refs`, and other canonical
  fields;
- those fields may contain host paths, raw request material, or implementation
  details and are serialized into native tool history;
- the contract text calls `model_output` redacted/bounded, but changing one
  field does not make the enclosing result safe for model delivery.

Add an allowlisted model-view serializer with explicit size/redaction rules;
never reuse the persistence dictionary as the model message.

Gate blocker `C-S1` — the versioned result is not mechanically closed:

- `ToolResult.to_dict()` flattens arbitrary dictionary output keys into the
  top-level canonical payload;
- `ToolResult.from_value()` accepts an explicit
  `qitos.tool_result/v999` payload when its status happens to be known;
- canonical list fields silently drop non-mapping entries;
- contradictory states such as `status="success"` with an execution error are
  accepted.

Keep legacy adaptation permissive at a named compatibility boundary, but make
the `qitos.tool_result/v1` serializer/parser strict and lossless.

Gate blocker `C-V1` — malformed schemas can pass the hard gate:

- an unknown JSON Schema type currently matches every value;
- a string-valued `required` field is silently treated as no requirements;
- reviewer probes returned valid for both cases.

The validator must either support a documented subset or reject an unsupported
or malformed schema with `schema_contract_violation`; it must never interpret
an unknown constraint as permission.

Follow-up `C-D1`: the Lane D handoff calls for a versioned trace-safe redaction
contract. C1 provides prose requirements, not a policy implementation and
fixture that can gate arbitrary keys, values, paths, free-form strings, and
artifacts. D must continue to report this dependency as open.

Disposition: do not integrate C1 until C1-R separates strict canonical,
compatibility, persistence, and model projections and closes validator
fail-open behavior with regression tests.

### 4.4 Lane D — data-plane census and readiness scaffold

What is sound:

- the census distinguishes runtime truth, trace-v1 compatibility truth,
  derived tracing/render planes, and checkpoint durability;
- no v2 writer/store or compression result is fabricated;
- the campaign fixture remains hashes/structure only because license and
  sanitization are not qualified;
- SQLite is not selected as canonical storage;
- the removal ledger does not treat repository grep as proof of external
  disuse.

Gate blocker `D-G1` — the readiness checker is a shallow inventory, not a
publication gate:

- `_load_manifests()` checks only that JSON is an object;
- readiness checks source class and status but not manifest version, unique
  fixture ID, license decision, sanitization receipt, hash shape, portability,
  coverage, or unexpected fields;
- the result always reports B/C contracts as unversioned and has no input
  mechanism for verified contract receipts.

Keep `TRAJECTORY_SCHEMA_NOT_READY`, but validate the source-manifest schema and
make every required contract/sanitization gate machine-checkable before 05A can
freeze a schema.

Gate blocker `D-P1` — readiness output can publish a host path:

- `build_readiness_result()` emits `fixture_root.as_posix()`;
- invoking the documented script with an absolute fixture path returned the
  full host-local worktree path even though the same plan requires public
  fixtures and receipts to reject host-local paths.

Report a logical fixture identifier or repository-relative path in portable
evidence.

Correction `D-E1`: census row D15 names
`qitos/core/action.py::{ActionResult,ToolResult}`. `ToolResult` lives in
`qitos/core/tool_result.py`; the exact-source record must be corrected before
the census is integrated.

Dependency status: B has supplied ExchangeLog fixtures and C has supplied
ToolResult/receipt fixtures, but they do not yet form one compatible,
privacy-qualified contract. RequestView, CodecReport, ArtifactRef, compaction,
durability behavior, hook failure fields, and executable redaction remain open.
Trajectory 05A schema freeze is therefore still blocked.

Disposition: preserve the census and source manifests, harden the readiness
validator and portable evidence, correct D15, then rebase onto the accepted B/C
contracts. Do not start a v2 schema merely because fixture filenames now
exist.

## 5. Contract convergence and merge order

Use this order; later lanes rebase onto the accepted semantic owner rather than
resolving incompatible contracts in an integration merge:

1. **A1-I:** integrate Lane A, resolve README/CHANGELOG once, install the pinned
   quality toolchain, and run ratchet plus repository gates.
2. **C1-R:** rebase Lane C onto A1-I; close C-P1, C-S1, and C-V1; publish the
   strict outcome/model-view fixtures; integrate C.
3. **B1-R:** rebase Lane B onto integrated C; close B-C1, B-I1, B-P1, and B-R1;
   make conversation results consume canonical `ToolResult`; integrate B.
4. **D1-R:** rebase Lane D onto integrated B/C; close D-G1, D-P1, and D-E1;
   record which required contracts are genuinely satisfied; integrate D.
5. **G1 qualification:** run the full suite, architecture/public-surface gates,
   stable flake8/mypy, the full-package ratchet, fixture privacy/portability
   scans, and `git diff --check` on the combined tree.

This order deliberately places the execution outcome owner before its
conversation consumer. Textual conflicts in README/CHANGELOG are resolved by
the integration owner; lane agents should not discard another lane's entries.

## 6. Next four-lane work

The next dispatch is a convergence wave, not the full W2 feature wave.

### Lane A — A1-I and A2 / Task 08E

- qualify and integrate A1;
- add deterministic end-to-end ratchet tests for new, stale, growth, expiry,
  toolchain, and base-ref cases;
- repair invalid changed-file predicates and masked intended checks;
- publish a required/advisory CI job table;
- do not change runtime semantics to make a diagnostic disappear.

### Lane B — B1-R, then 02B

- make ExchangeLog facts externally immutable or return isolated snapshots;
- define crash-safe partial batch persistence and recovery fixtures;
- replace the second result envelope with an adapter to Lane C's canonical
  outcome;
- rename or implement the purported safe projection with a policy/loss report;
- after B1-R integration, implement ephemeral RequestView and transport/API-mode
  capabilities in 02B; do not begin provider default flips.

### Lane C — C1-R, then 03B/09C

- split strict canonical serialization from legacy and model projections;
- use an allowlist for model-visible result fields and add secret/path/size
  regression tests;
- reject unsupported result versions, contradictory outcomes, malformed list
  fields, and unsupported/malformed schema constraints;
- after contract integration, start filesystem/search foundations and honest
  timeout/late-result semantics; do not claim hard thread cancellation.

### Lane D — D1-R, then 09E preparation

- turn fixture manifests into versioned, strict, portable validation inputs;
- accept verifiable B/C contract receipts rather than a permanent hardcoded
  blocker;
- correct exact-source evidence and add a public-evidence path scan;
- prepare hook/trace completeness receipts, but keep trajectory v2 schema
  frozen only after RequestView/ArtifactRef/compaction and redaction contracts
  exist.

## 7. Gate checklist

### G1 — trustworthy change surface

- [ ] A1 commits are in the integration branch.
- [ ] Pinned full-package ratchet passes on the integrated tree.
- [ ] Stable flake8/mypy remain zero-debt.
- [ ] B and C use one canonical tool outcome.
- [ ] ExchangeLog persistence cannot be mutated through returned references.
- [ ] Persistence and model/public projections have explicit privacy contracts.
- [ ] D manifests reject malformed, unlicensed, unsanitized, or host-bound
      publication evidence.
- [ ] Cross-lane fixtures have actual consumer tests, not labels alone.
- [ ] Full suite, architecture boundaries, public surface, and diff checks pass.

### G2 prerequisites exposed by this review

- [ ] RequestView and CodecReport are versioned and transport/API-mode aware.
- [ ] Provider failures cannot become assistant text.
- [ ] Partial parallel completion survives checkpoint/recovery.
- [ ] Timeout receipts state whether work continues and prevent late commit.
- [ ] Durability callers distinguish accepted, persisted, failed, and dropped.
- [ ] Hook/trace incompleteness is visible without recursive failure.

## 8. Append-only integration log

### 2026-08-29 — first-wave branch audit

- Confirmed all four lane branches descend from the W1 baseline and have clean
  worktrees.
- Reviewed their actual diffs rather than accepting completion summaries.
- Re-ran 17 Lane A, 28 Lane B, 28 Lane C, and 107 Lane D targeted tests.
- Confirmed pairwise textual conflicts are limited to README/README.zh and
  CHANGELOG; identified the independent semantic conflicts above.
- Kept the integration branch unchanged while review blockers remain open.
