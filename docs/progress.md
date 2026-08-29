# v4 integration progress

Status: active integration ledger
Updated: 2026-08-29
Integration branch: `feat/campaign-absorption`
Reviewed integration source: `8441bef2f2024fd6c2ec01784708512222382471`
Source plan: [`docs/v4/11-four-lane-execution-playbook.md`](v4/11-four-lane-execution-playbook.md)
Next architecture: [`Task 12 durable sessions`](v4/12-session-runtime-and-persistence.md)
and [`Task 13 durable multi-agent work`](v4/13-durable-multi-agent-work-graph.md)

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

Gate G1 is **not closed**. The four convergence-wave branches are clean and
close most first-wave findings, but none of their commits is present in the
integration branch. Completion reports and branch-local green suites therefore
remain candidate evidence, not integrated qualification.

The current integration source is clean at `8441bef2...`. Lane A's ratchet
transitions, Lane B's ExchangeLog integrity, Lane C's strict result parser, and
Lane D's typed readiness output are substantive improvements. Code-level probes
nevertheless found one executable CI failure, three remaining ToolResult
boundary failures, the intentionally deferred B/C result convergence, and an
unverified receipt trust boundary in D. Those findings require one bounded
repair wave before the first merge.

The v4 architecture now explicitly includes Codex-like durable sessions,
process-independent pause/resume/fork, and a native durable multi-agent work
graph. This is a planning decision, not an implementation claim and not a reason
to bypass G1. Existing `init_session`, `RunState`, checkpoint v2,
interrupt/resume, handoff, delegate, and fan-out paths are recorded as useful but
fragmented primitives. The next capability phase converges them into one
checkpoint-backed session truth and one generation-checked work graph.

| Lane | Reviewed HEAD | Package | Integration disposition | Next package |
|---|---|---|---|---|
| A | `ec43f09c1d6926a146b2c3f80a4b351861c5ea87` | A1/A2 qualification | Changes requested: advisory workflow is not executable | A2-R executable workflow contracts |
| B | `5b0e8d54ab9dc95746b9e30fb2ce97a6165f0390` | B1-R Phase 1 | Phase 1 accepted as input; not merge-ready while temporary result contract remains | B1-R Phase 2 on accepted C HEAD |
| C | `86ad165cef56262d0d5b58e095a1452f8201bc79` | C1-R | Changes requested: JSON, aliasing, and projection/loss boundaries | C1-R2 boundary closure |
| D | `d80f4cc7e7c1532c33ea0cf057435447bf9261e7` | D1-R | Strict blocked scaffold accepted; not a contract qualification authority | D1-R2 verified B/C receipt consumption |

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

The convergence-wave review used the shared integration baseline
`8441bef2f2024fd6c2ec01784708512222382471`. All four worktrees were clean and
their reported HEADs matched the commits reviewed.

| Lane | Worktree | Agent-reported full suite | Integration-owner targeted rerun |
|---|---|---:|---:|
| A | `WhitzardOS-lane-a2` | 1,720 passed, 50 skipped | 34 passed; separate executable import probe failed |
| B | `WhitzardOS-lane-b2` | 1,720 passed, 50 skipped | 34 passed |
| C | `WhitzardOS-lane-c2` | 1,756 passed, 50 skipped | 277 passed; separate boundary probes failed |
| D | `WhitzardOS-lane-d2` | 1,720 passed, 50 skipped | 34 passed |

The reruns covered ratchet/workflow contracts, ExchangeLog, ToolResult and
structural validation, Engine action execution, trajectory readiness,
exact-source evidence, architecture boundaries, and public surface. Diff checks
passed for all four reviewed ranges. Pairwise merge-tree simulation found
content conflicts in `CHANGELOG.md`, `README.md`, and `README.zh.md` for every
lane pair; no other textual conflict was reported. These documentation conflicts
must be hand-merged, but they are secondary to the semantic blockers below.

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

### 4.5 Convergence-wave re-review

The earlier findings remain historical evidence. This section records which
ones the repair branches actually closed and which new boundary probes prevent
integration.

#### Lane A — ratchet improved; executable CI still broken

Closed from the first review:

- `A-Q1`: twenty deterministic tests now exercise new/stale findings,
  base-reference growth, exceptions, expiry, bootstrap, rules upgrades, and
  explicit update behavior;
- the required/advisory/stale ownership table and workflow path repairs are
  documented without claiming knowledge of GitHub branch protection.

New blocker `A-CI1`:

- `.github/workflows/contribution-test.yml` imports `ToolSpec` from
  `qitos.core.tool_schema`;
- the class is defined and exported from `qitos.core.tool`, and the workflow's
  exact import raises `ImportError`;
- `tests/test_workflow_contracts.py` parses YAML and checks paths/tokens, but
  does not execute or import-check embedded Python, so all 34 targeted tests
  pass while the job itself fails before validating any schema.

Disposition: keep A first in merge order, but require A2-R to move non-trivial
inline code into a repository script or otherwise execute it in tests. Correct
the import and prove that the schema check discovers real registered/class tool
specs rather than merely walking modules without assertions.

#### Lane C — strict parser improved; the safe boundary is incomplete

Closed from the first review:

- the canonical parser now rejects unknown versions/fields, malformed lists,
  contradictory terminal states, and non-JSON canonical values;
- legacy flattening is explicit, model fields are allowlisted, and unsupported
  schema keywords/types fail closed;
- argument validation is repeated after permission/interceptor rewriting.

New blocker `C-J1` — runtime arguments are not required to be JSON values:

- `validate_tool_arguments({"x": float("nan")}, {"type": "object"})` returns
  valid;
- an arbitrary `object()` under an open object schema also returns valid;
- a declared `number` accepts `NaN`, despite the gate being described as a JSON
  structural boundary.

New blocker `C-I1` — canonical result ownership is aliased:

- construction and `from_canonical_dict()` retain nested caller-owned values;
- `to_persistence_dict()` returns nested output/metadata references rather than
  an isolated JSON tree;
- mutating either the source payload or serialized result changed the existing
  `ToolResult` in reviewer probes.

New blocker `C-P2` — allowlisted projections still leak and under-report loss:

- `tool_name`, `action_id`, and `error_code` are emitted without identifier
  validation or redaction; token-like values and host paths survive unchanged;
- error and recovery-hint strings are redacted, but `to_trace_safe_dict()`
  reports loss counters only from `model_output`, producing zero redactions for
  redacted error/hint content;
- the trace-safe receipt therefore cannot yet qualify Lane D's full redaction
  dependency.

Disposition: C1-R2 must deep-isolate canonical inputs/outputs, reject every
non-finite/non-JSON runtime argument recursively, validate or redact all
model-visible identifiers, and aggregate loss facts across every projected
field.

#### Lane B — Phase 1 integrity is sound; C convergence remains deliberately open

Closed from the first review:

- `B-I1`: append, read, restore, and serialization boundaries now use isolated
  snapshots for nested values;
- `B-P1`: the old safe-name overclaim is replaced by an explicitly
  continuation-only redacted diagnostic projection;
- `B-R1`: each terminal result is appended immediately in completion order,
  partial logs round-trip, missing slots resume, and queued steering commits
  once after final closure.

Still-open blocker `B-C1`:

- `ToolResultStatus` and `ToolResultItem` remain explicitly temporary and still
  encode a second status/content/provenance result representation;
- this was an intentional Phase 1 stop, so B cannot be merged as the canonical
  conversation result contract until it consumes the accepted C serializer,
  model view, status/error mapping, and artifact slot.

New blocker `B-V1`:

- malformed persisted values do not consistently fail with
  `ConversationValidationError`; for example a string-valued item `metadata`
  escapes as a built-in `ValueError` from `dict(...)`;
- Phase 2 must make the versioned external reader mechanically strict while
  keeping any permissive legacy conversion behind a named adapter.

`B-T1` also remains open: the current consumer simulations are useful, but
actual Engine/request and trajectory consumers arrive in later packages.

#### Lane D — strict default blocking is sound; receipts are not yet verified

Closed from the first review:

- `D-G1`: manifest fields, state consistency, publication evidence, identities,
  coverage, receipts, and blocker categories now have typed checks;
- `D-P1`: readiness output no longer emits fixture roots or rejected raw values;
- `D-E1`: D15 exact sources are corrected and D01-D16 symbols are AST-checked.

Remaining blocker `D-R1`:

- a caller can supply any syntactically valid 64-hex digest with
  `qualified=true` and remove the corresponding contract blocker;
- `qualification_authority` is optional, the digest is not resolved against a
  committed B/C artifact, and no producer-owned qualification proof is
  verified;
- this is safe while the default remains blocked and no receipts are supplied,
  but it is not yet a trustworthy cross-lane qualification mechanism.

Follow-up `D-S1`: the JSON Schema file and the stdlib typed validator are two
representations. Current tests compare a few constants but do not prove that
the documented schema and executable validator accept/reject the same fixture
corpus. Add parity fixtures or make one representation generated/authoritative.

Disposition: D1-R may be preserved as a strict blocked scaffold, but D1-R2 must
consume producer-owned receipts bound to exact fixture bytes/versions and a
reviewed authority before any contract becomes qualified.

## 5. Contract convergence and merge order

Use this order; later lanes rebase onto the accepted semantic owner rather than
resolving incompatible contracts in an integration merge:

1. **A2-R:** repair and executable-test the workflow script, then integrate A
   onto `8441bef2...`; hand-merge all three shared release documents and run the
   pinned ratchet plus repository gates.
2. **C1-R2:** close C-J1, C-I1, and C-P2 on the accepted A integration HEAD;
   publish corrected canonical/model/trace fixtures and integrate C.
3. **B1-R Phase 2:** rebase B Phase 1 onto integrated C; remove the temporary
   outcome status/envelope, add strict typed external parsing, and prove exact C
   fixture consumption before integrating B.
4. **D1-R2:** rebase D onto integrated B/C; pin reviewed contract versions and
   verify producer-owned receipt identity/digests plus schema-validator parity;
   keep all unsatisfied Task 02/04/09 dependencies typed blocked.
5. **G1 qualification:** run the full suite, architecture/public-surface gates,
   workflow executable tests, stable flake8/mypy, the full-package ratchet,
   cross-lane fixture consumers, privacy/portability scans, and
   `git diff --check` on the combined tree.

This order deliberately places the execution outcome owner before its
conversation consumer. Textual conflicts in README/CHANGELOG are resolved by
the integration owner; lane agents should not discard another lane's entries.

## 6. Next four-lane work

The next dispatch is the final G1 repair wave, not the full W2 feature wave.

### Lane A — A2-R executable workflow trust

- fix the `ToolSpec` import and put non-trivial schema validation in a normal
  repository module/script;
- execute the same entrypoint in a deterministic test, including a controlled
  invalid-spec failure and the real tool inventory;
- preserve the 20 ratchet transition tests and required/advisory matrix;
- do not broaden scope into packaging, runtime behavior, or GitHub ruleset
  claims before A is integrated.

### Lane B — B1-R Phase 2 canonical outcome consumption

- wait for the exact accepted C1-R2 HEAD, then rebase and consume its
  persistence/model/trace contracts without copying its status vocabulary;
- retain call, batch, completion-order, and closure-provenance facts while
  removing the temporary duplicate outcome envelope;
- make malformed versioned persistence payloads fail with stable typed errors;
- add real C serializer/reader fixture tests; do not begin RequestView/provider
  default work until this package is integrated.

### Lane C — C1-R2 JSON, ownership, and projection closure

- reject nested non-JSON objects and all non-finite numbers at the runtime
  argument boundary, before permission or tool execution;
- deep-isolate construction, canonical parsing, adapters, and persistence
  serialization, with mutation probes in both directions;
- constrain/redact every model-visible identity/code and aggregate trace loss
  across output, error, hint, next action, and identifiers;
- publish corrected fixtures for B/D; do not start coding tools, durability, or
  MCP work in this repair package.

### Lane D — D1-R2 verified receipt convergence

- define the trust source for `qualified`, require a reviewed authority, and
  bind every accepted receipt digest to exact committed producer fixture bytes;
- consume the final B/C versions only after those branches are accepted;
- prove parity between the documented manifest schema and executable validator;
- preserve `schema_not_ready`, empty measurements/claims, and typed blockers for
  RequestView, ArtifactRef, compaction, hook failure, and full redaction.

### Post-G1 capability remap (planned, not dispatched)

After the integration owner closes G1, quality becomes a mandatory cross-lane
gate and the four implementation lanes change to:

| Lane | First package | Scope |
|---|---|---|
| A — Session Runtime & Persistence | Task 12A | identity, lifecycle, safe boundaries, one snapshot truth, resolver references |
| B — Conversation, Context & Continuation | Task 02B | RequestView, steering, provider capabilities, Task 12 snapshot handoff |
| C — Tools & Durable Multi-Agent | Task 03 recovery handoff + Task 13A | effects/quiescence and work-graph ownership/join contracts |
| D — Trajectory, qita & DX | lineage intake | session/work graph reader census and readiness only; no v2 freeze |

S2's required vertical slice is: start -> parallel tools -> pause -> process exit
-> restore through a fresh Engine/composition root -> apply steering once ->
finish, with no duplicate committed effect. Multi-agent behavior starts only
after this single-agent continuity proof. Task 05 v2 remains blocked from schema
freeze until Task 12/13 lineage is available.

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
- [ ] Workflow-owned Python checks are executed by repository tests, not merely
      parsed as YAML strings.
- [ ] Tool arguments reject every recursively non-JSON/non-finite value.
- [ ] ToolResult canonical serialization has no caller-visible nested aliases.
- [ ] Trace-safe loss facts cover every redacted or omitted projected field.
- [ ] Cross-lane qualification receipts bind to reviewed producer artifacts.

### G2 prerequisites exposed by this review

- [ ] RequestView and CodecReport are versioned and transport/API-mode aware.
- [ ] Provider failures cannot become assistant text.
- [ ] Partial parallel completion survives checkpoint/recovery.
- [ ] Timeout receipts state whether work continues and prevent late commit.
- [ ] Durability callers distinguish accepted, persisted, failed, and dropped.
- [ ] Hook/trace incompleteness is visible without recursive failure.
- [ ] Session/run/work-item/checkpoint/exchange/tool-call/agent identities are
      distinct and versioned.
- [ ] Checkpoint v2 is the only session persistence truth; `RunState` has an
      adapter/retirement decision and no parallel SessionStore exists.
- [ ] A fresh process restores task, concrete state, ExchangeLog, partial tool
      batch, steering, context/artifacts, budgets, owner, and trace cursor.
- [ ] Stale owners and late workers cannot advance a newer session head.
- [ ] Handoff, delegate, fan-out, spawn, fork, and steering have distinct
      ownership semantics over one durable work graph.
- [ ] Task 05 schema freeze waits for explicit session/work/ownership lineage.

## 8. Append-only integration log

### 2026-08-29 — first-wave branch audit

- Confirmed all four lane branches descend from the W1 baseline and have clean
  worktrees.
- Reviewed their actual diffs rather than accepting completion summaries.
- Re-ran 17 Lane A, 28 Lane B, 28 Lane C, and 107 Lane D targeted tests.
- Confirmed pairwise textual conflicts are limited to README/README.zh and
  CHANGELOG; identified the independent semantic conflicts above.
- Kept all lane implementation commits out of the integration branch while
  review blockers remain open; only this integration-owned review ledger and
  its documentation pointers were committed.

### 2026-08-29 — convergence-wave branch audit

- Verified the exact A2/B2/C2/D2 worktrees, branches, clean status, common
  `8441bef2...` baseline, and reported final HEADs.
- Re-ran 34 Lane A, 34 Lane B, 277 Lane C, and 34 Lane D targeted tests; all
  selected suites passed after correcting one nonexistent path in the supplied
  C validation list to the repository's real test layout.
- Executed reviewer probes that reproduced A-CI1, C-J1, C-I1, C-P2, B-V1, and
  D-R1 rather than inferring them from prose.
- Confirmed the original B integrity/privacy/persistence findings and original
  D strictness/portability/source findings are materially closed.
- Simulated every pairwise merge and recorded the three shared release-document
  conflicts; no lane commit was merged into integration while executable and
  semantic blockers remain.

### 2026-08-29 — durable session and multi-agent architecture expansion

- Inspected the existing Engine session/step API, `RunState`, checkpoint v2,
  interrupt/resume, handoff, delegate, fan-out, trace, and qita ownership paths.
- Recorded that they are fragmented primitives rather than a complete
  process-independent session protocol: checkpoint content and identity are
  incomplete for a fresh-process reconstruction, and child work is not durable.
- Added Task 12 for one checkpoint-backed session head/snapshot model, safe
  pause, clean-process restore, fork, resolver references, and honest effect
  recovery.
- Added Task 13 for distinct handoff/delegate/fan-out/spawn/fork/steer semantics,
  single-owner work items, durable children/joins, budget/capability boundaries,
  and qita graph lineage.
- Remapped post-G1 concurrency to four capability lanes while keeping the static
  ratchet, full tests, architecture/public surface, packaging, and docs parity as
  cross-lane acceptance gates.
- Made G1 closure an explicit prerequisite for implementation dispatch and made
  the clean-process single-agent vertical slice a prerequisite for multi-agent
  behavior and trajectory-v2 schema freeze.

### 2026-08-29 — G1 final convergence closed

- Created `codex/v4-g1-convergence` in the isolated `WhitzardOS-g1` worktree
  directly from fixed baseline
  `a02ce05e9a364eb484ef339fe5cbd623910cf525`.
- Integrated every supplied source commit in the fixed A → C → B → D order,
  preserving reviewed heads `ec43f09c1d6926a146b2c3f80a4b351861c5ea87`,
  `86ad165cef56262d0d5b58e095a1452f8201bc79`,
  `5b0e8d54ab9dc95746b9e30fb2ce97a6165f0390`, and
  `d80f4cc7e7c1532c33ea0cf057435447bf9261e7` without squashing or amending the
  source identities.
- Closed A-CI1 in `f145cbe`: the workflow and tests execute one checked-in real
  tool-schema qualification entrypoint; 61 modules, 74 class definitions, and
  62 qualified/registered class tools passed, while the controlled invalid
  input exited 1 with `invalid_tool_name`.
- Closed C-J1 in `c509bd0` and C-I1/C-P2 in `ab1c501`: recursive JSON admission
  precedes interceptor/permission/tool execution, canonical and legacy result
  values are deeply ownership-isolated, and all model/trace-visible result
  fields are bounded, redacted, and covered by aggregate/per-field loss facts.
- Closed B-C1/B-V1 in `2e46fc8`: ExchangeLog v2 embeds the sole canonical
  ToolResult, delegates persistence/model/trace views to C, preserves completion
  and recovery semantics, strictly normalizes malformed reads to
  `ConversationValidationError`, and directly consumes C's committed fixture.
- Closed D-R1 in `30c1823`: qualification is derived from an approved authority,
  exact producer commit, committed fixture/evidence paths, current and committed
  SHA-256 bytes, and matching producer-owned evidence. The B/C receipts clear
  only their two contracts; all unimplemented dependencies remain typed blocked.
- Combined qualification passed: targeted suites 20/8/39/24/29/3/35/2/4/4/2;
  stable flake8 clean; stable mypy success on 77 files; full ratchet 399 findings
  (377 active, 22 vendored/generated); full suite 1863 passed, 50 skipped;
  architecture, public-surface, no-local-path, and `git diff --check` clean.
- The initial combined command contained one operator typo for a nonexistent
  `tests/core/test_schema.py` path after three passing suites. No code test
  failed or was rerun; execution resumed at the correct original
  `tests/core/test_tool_schema.py` command and the remaining matrix passed.
- Both trajectory readiness modes remain honestly blocked:
  `schema_not_ready`, zero publication-qualified fixtures, empty measurements
  and claims; dry-run exits 0 and normal execution exits 2. Trajectory v2 remains
  unfrozen.
- Decision: **G1 CLOSED**. S1 capability-lane dispatch is authorized. This does
  not mark Task 02B, 03B–E, 04/05A, Task 12/13 runtime, provider defaults,
  trajectory v2, qita redesign, packaging migration, or deprecated-surface
  removal as implemented.
