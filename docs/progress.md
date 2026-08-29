# v4 integration progress

Status: active integration ledger
Updated: 2026-08-29
Integration branch: `codex/v4-g1-convergence`
Reviewed convergence source: `587f34b76245e71fe3362a51dbad40895d7c43c5`
Current gate: **G1 reopened on C-P3; S1 dispatch blocked**
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

The A -> C -> B -> D convergence tree is materially integrated at
`587f34b76245e71fe3362a51dbad40895d7c43c5`. The pinned ratchet, stable
flake8/mypy, targeted contracts, full suite, architecture/public-surface gates,
tool-schema qualification, and trajectory readiness behavior all passed an
independent rerun. The previously recorded A-CI1, C-J1/C-I1/C-P2, B-C1/B-V1,
and D-R1 blockers have executable fixing commits.

Gate G1 is nevertheless **reopened** on `C-P3`. A post-convergence adversarial
probe found that ToolResult mapping keys bypass the recursive redactor, and
trace-safe `omitted` keys bypass projection entirely. Host paths and token-like
text can therefore survive in model/trace-visible keys while the loss report
remains zero. This contradicts the claimed privacy/loss invariant. S1 remains
blocked until a bounded C-owned repair, D receipt requalification when producer
evidence changes, and a combined rerun close this finding.

The convergence report's provenance wording is also corrected: all 26 reviewed
source commits were applied by ordered cherry-pick, but the original source SHAs
are not ancestors of the convergence HEAD. Eighteen integrated commits are
patch-id equivalent; eight documentation/evidence commits were conflict-resolved
and therefore have new, non-equivalent patch identities. The resulting code and
evidence are present, but source identity was not literally preserved.

The v4 architecture now explicitly includes Codex-like durable sessions,
process-independent pause/resume/fork, and a native durable multi-agent work
graph. This is a planning decision, not an implementation claim and not a reason
to bypass G1. Existing `init_session`, `RunState`, checkpoint v2,
interrupt/resume, handoff, delegate, and fan-out paths are recorded as useful but
fragmented primitives. The next capability phase converges them into one
checkpoint-backed session truth and one generation-checked work graph.

| Lane | Integrated fixing HEAD | Package | Integration disposition | Next package |
|---|---|---|---|---|
| A | `f145cbe2df5f74418c9ccaae2f0a5cf5555b8daf` | A1/A2 + A-CI1 | Accepted in convergence tree | Stand by; retain cross-lane gates |
| B | `2e46fc8e0228af42d6eaeaa6a665ffe5998c0bd5` | B1-R + B-C1/B-V1 | Accepted in convergence tree | Stand by; rerun consumer tests after C-P3 |
| C | `ab1c501400fc2a8c47fcef1b4fe85c4e4db8d8f6` | C1-R2 | Changes requested: C-P3 mapping-key/omitted-key privacy and loss accounting | C1-R3 bounded projection repair |
| D | `30c182392d7392b2c74446102893b2f10f1666e3` | D1-R2 | Accepted; exact receipts may need producer refresh after C-P3 | Conditional receipt requalification only |

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

## 4. Historical review findings

This section preserves the blockers as they were discovered in the first and
convergence-wave branch reviews. Their old “open” wording is audit history, not
the current dashboard. The fixing commits and the new C-P3 disposition are
authoritative in Sections 2, 5–7, and the append-only entries below.

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

The historical A -> C -> B -> D order is complete in the convergence tree. It
correctly placed the execution-outcome owner before its conversation consumer
and then qualified D against accepted producer artifacts. The only active merge
sequence is now:

1. **C1-R3:** repair C-P3 on the exact convergence HEAD, without starting 03B–E.
2. **B consumer rerun:** prove ExchangeLog's delegated model/trace projections
   inherit the repaired behavior; change B only if a real consumer defect is
   exposed.
3. **D receipt refresh:** if the C fixture/evidence bytes or producer commit
   change, publish and consume a new exact producer-owned receipt; otherwise
   record why the current receipt remains valid.
4. **G1 requalification:** rerun the pinned ratchet, stable lint/type, targeted
   cross-lane suites, adversarial key probes, full suite, readiness modes, and
   `git diff --check` on the combined tree.

No A, B, or D feature work is authorized inside this repair. Shared release
documents remain integration-owner leases.

## 6. Next work

The immediate dispatch is one bounded C-owned repair, not four concurrent
feature branches.

### Lane C — C1-R3 / C-P3 projection-key closure

- recursively sanitize or replace mapping keys in model output and nested
  `next_action` arguments; raw host paths, token/header/secret-like text, and
  other sensitive identifiers must not survive as keys; the representation must
  be deterministic and collision-safe so two redacted keys cannot overwrite or
  silently discard values;
- make trace-safe `omitted` data use an explicitly safe representation instead
  of copying canonical keys verbatim;
- count key redactions and omitted-field projection losses in aggregate and
  per-field loss facts;
- add nested probes for host paths and secrets in keys, including model output,
  next-action arguments, trace-safe omitted data, and ExchangeLog delegation;
- preserve canonical persistence bytes and strict readers unless a versioned
  migration is genuinely required;
- publish updated C evidence/fixtures if their bytes change, then hand the exact
  identity to D; do not start coding tools, durability, MCP, or Task 13 behavior.

Lanes A, B, and D remain on standby. B reruns its consumer suite after the C
fix; D only refreshes exact receipts when producer evidence changes; A provides
the integrated quality gate. The conditional S1 packages are specified in
[`docs/internal/plans/s1_contract_wave.md`](internal/plans/s1_contract_wave.md)
and become dispatchable only after G1 is reclosed.

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

- [x] A1 changes are in the integration branch through ordered cherry-picks.
- [x] Pinned full-package ratchet passes on the integrated tree.
- [x] Stable flake8/mypy remain zero-debt.
- [x] B and C use one canonical tool outcome.
- [x] ExchangeLog persistence cannot be mutated through returned references.
- [x] Persistence and model/public projections have explicit privacy contracts.
- [x] D manifests reject malformed, unlicensed, unsanitized, or host-bound
      publication evidence.
- [x] Cross-lane fixtures have actual consumer tests, not labels alone.
- [x] Full suite, architecture boundaries, public surface, and diff checks pass.
- [x] Workflow-owned Python checks are executed by repository tests, not merely
      parsed as YAML strings.
- [x] Tool arguments reject every recursively non-JSON/non-finite value.
- [x] ToolResult canonical serialization has no caller-visible nested aliases.
- [ ] Trace-safe loss facts cover every redacted or omitted projected field.
- [ ] Model/trace-safe projections sanitize sensitive mapping keys at every
      nesting level, including trace-safe omitted data (`C-P3`).
- [x] Cross-lane qualification receipts bind to reviewed producer artifacts.

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

### 2026-08-29 — G1 final convergence provisionally closed (superseded below)

- Created `codex/v4-g1-convergence` in the isolated `WhitzardOS-g1` worktree
  directly from fixed baseline
  `a02ce05e9a364eb484ef339fe5cbd623910cf525`.
- Integrated every supplied source commit in the fixed A → C → B → D order,
  using reviewed heads `ec43f09c1d6926a146b2c3f80a4b351861c5ea87`,
  `86ad165cef56262d0d5b58e095a1452f8201bc79`,
  `5b0e8d54ab9dc95746b9e30fb2ce97a6165f0390`, and
  `d80f4cc7e7c1532c33ea0cf057435447bf9261e7` as ordered cherry-pick sources.
  The resulting integrated commits have new SHAs; later audit records exact
  patch-equivalence and conflict-resolution facts.
- Closed A-CI1 in `f145cbe`: the workflow and tests execute one checked-in real
  tool-schema qualification entrypoint; 61 modules, 74 class definitions, and
  62 qualified/registered class tools passed, while the controlled invalid
  input exited 1 with `invalid_tool_name`.
- Closed C-J1 in `c509bd0` and C-I1/C-P2 in `ab1c501`: recursive JSON admission
  precedes interceptor/permission/tool execution, canonical and legacy result
  values are deeply ownership-isolated, and scalar model/trace-visible result
  values are bounded and redacted. A later adversarial audit reopened the
  stronger all-fields/loss claim as C-P3.
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
- Provisional decision at this point in the audit trail: **G1 CLOSED** and S1
  capability-lane dispatch authorized. The independent entry immediately below
  supersedes this decision. This does
  not mark Task 02B, 03B–E, 04/05A, Task 12/13 runtime, provider defaults,
  trajectory v2, qita redesign, packaging migration, or deprecated-surface
  removal as implemented.

### 2026-08-29 — independent post-convergence audit reopens G1

- Verified the convergence worktree was clean at
  `587f34b76245e71fe3362a51dbad40895d7c43c5`, with the fixed baseline as its
  merge base and the documented A -> C -> B -> D integration history present.
- Corrected provenance: none of the 26 original source SHAs is an ancestor of
  the convergence HEAD because the work used cherry-picks. Patch-id comparison
  found 18 exact patch equivalents; eight shared documentation/evidence commits
  were manually conflict-resolved and therefore have new patch identities.
- Independently reran the fixed Python 3.12.7 toolchain: 179 targeted tests,
  tool-schema qualification (61 modules, 74 classes, 62 qualified/registered),
  the 399-finding ratchet, stable flake8, stable mypy on 77 files, and the full
  suite (`1863 passed, 50 skipped`) all passed.
- Independently verified trajectory readiness: normal execution exits 2,
  dry-run exits 0, both remain `schema_not_ready`, measurements/claims remain
  empty, default input qualifies no contracts, and the exact receipt input
  clears only the B ExchangeLog and C ToolResult contracts.
- Reproduced `C-P3`: sensitive host-path and token-like text in mapping keys
  survives `ToolResult.to_model_dict()` and `to_trace_safe_dict()`; nested
  `next_action` argument keys and trace-safe `omitted` keys also survive. The
  corresponding loss counters remain zero because `_redact_value()` processes
  mapping values but preserves keys, while trace-safe `omitted` is copied
  outside the shared projection path.
- Decision: the convergence tree remains a strong integration candidate, but
  **G1 is reopened and S1 is blocked**. Only the bounded C1-R3 repair, dependent
  B/D requalification, and combined gate rerun are authorized next.
