# V5 R1 Lane C execution

Source: `4dfb570fb7eef504c1e6d247c21a1984251b80e4`.
Branch: `codex/v5-r1-c-runtime-correctness`.
Initial HEAD and merge-base match source; worktree was clean. Main checkout drafts retained.

## Ordered implementation

1. Reproduce SQLite handoff owner race using two processes and Event barriers;
   preserve baseline failure. Persist transfer/admission before dispatch; fence
   stale callbacks and reconcile from durable facts. Qualify A–G crash matrix,
   with 20 independent forced A interleavings and a 30-second test deadline.
2. Fix Read pagination and Edit uniqueness with actual-file regressions through
   existing validation/permission/adapter paths.
3. Make Observation attribute and mapping mutations share one authority, with
   atomic validation and defensive snapshots.
4. Synchronize bilingual docs and tutorials; install wheel into independent
   Python 3.12.7 venv and run outside-checkout public consumers. Run all required
   quality, architecture, full test, packaging and documentation gates.

Commits follow these three behavior packages, then installed/tutorial/evidence
and required allowance shrink only. No model requests, push, deployment,
publication, other-lane merges, or worktree cleanup.

## Evidence

Preflight fetch succeeded and the fixed source is an ancestor of origin/master.
Lane C qualified after the final full-suite pass. Earlier failed attempts remain recorded below.

### Handoff implementation evidence

- Baseline real SQLite/Event regression failed with `CheckpointConflictError`
  from the source terminal callback after destination restore (1 failed, 1.06s).
  Full local log: `/tmp/qitos-v5-r1-c-evidence/handoff-baseline.txt`.
- Transfer order: declaration -> prepared descriptor/ownership transfer ->
  admitted invocation with execution unknown -> scheduler. No source callback
  writes after invocation; destination restore/CAS reconciles ownership and
  its own commits record execution/terminal state. No checkpoint CAS changes.
- Initial matrix: 6 passed (3.70s); targeted work/session/handoff/checkpoint: 75 passed.
- First matrix attempt: 4 passed, 1 test failed because a second explicit restore
  targeted lifecycle `restoring`; corrected fixture first pauses the winner.
  The same-generation competition itself had one CAS winner in both runs.

- Forced A interleaving: 20 independent pytest processes, 20 passed, 0 failed;
  each subprocess deadline 30s, observed 1.173–1.481s. All attempts retained.

### Read/Edit evidence

- Actual-file tests cover numbered pages, empty/blank files, EOF, invalid windows,
  explicit truncation, ambiguous/all/missing edits, SHA mismatch, denied permission,
  and Env missing-capability no-host fallback through ActionExecutor.
- Combined tests: 140 passed. First combined run: 139 passed, 1 failed due to
  existing toolset auto_approve mutating shared metadata; fixture now uses scoped
  executor approval and the existing permission pipeline. Intermediate fixture
  run correctly raised approval interrupts (5 failed, 22 passed); no runtime bypass added.
- Read/Edit direct return migration: canonical ToolResult replaces strings; no
  permission/sandbox authority changes. Known toolset metadata mutation remains
  outside this lane, as do func inert retry and other excluded extensions.

### Observation evidence

- One canonical dict storage; attributes route to fields, mapping action_results
  is an explicit fresh compatibility projection of validated canonical ToolResult.
- Constructor inputs and explicit serialization are deep-copied; schema fields
  reject deletion, extensions support normal removal. Atomic update checks both
  step aliases before changing any field.
- First targeted run: 479 passed, 1 failed on bool/int alias equality; fixed by
  validating both supplied aliases. Expanded core/reducer/Env/history suite:
  497 passed (3.73s). No ToolResult wire or root export changes.

### Full-suite compatibility finding and correction

- First full run: 1 failed, 3459 passed, 51 skipped in 301.72s.
  `test_engine_saves_checkpoints` exposed dataclasses.asdict attempting to
  reconstruct Observation as a plain dict subclass. Isolated reproduction also
  failed (1 failed, 0.40s); both logs retained.
- Preserve `@dataclass(init=False)` metadata with the explicit validated
  constructor and attribute routing. This preserves old checkpoint asdict and
  dataclasses.replace behavior without storing fields in __dict__. A regression
  explicitly proves __dict__ remains empty (one canonical state).

- Corrected Observation + old checkpoint + full core/engine/kernel suites:
  771 passed (11.96s).

### Final artifact and compatibility checks

- Runtime commits: `12001c9` (handoff), `40f1444` (Read/Edit), `5d3cd79`
  (Observation), `d1a4e42` (Observation dataclass/checkpoint regression).
- Final required target suites: 624 passed (7.62s). All core/engine/kernel
  regression suites had also passed (771 tests) after the dataclass correction.
- Final A qualification: a further 20 independent processes, 20 passed, 0 failed,
  1.273–1.541s per invocation with a 30s subprocess deadline. The first 20 passes
  and every earlier failing development attempt are retained, not replaced.
- Final wheel installed in a separate Python 3.12.7 venv; serial handoff,
  immediately concurrent destination handoff and public Read/Edit/Observation
  consumers all passed from outside the repository with PYTHONPATH removed.
  All 503 wheel Python files match the final source.
- Fixed tools: flake8 7.0.0, mccabe 0.7.0, mypy 1.19.1, pycodestyle 2.11.1,
  pyflakes 3.2.0. Final quality ratchet passed: 356 retained findings (334 active,
  22 vendored/generated); allowance/exception delta 0. Stable flake8 and mypy
  passed; architecture/public-surface/local-path gates passed (10 tests).
- Build (wheel and sdist), twine, validate_docs, API signature sync, tutorial
  sync and diff whitespace checks passed. Bilingual page-extracted installed
  consumers are included in the full suite. Tutorial JSON only adds one command.
- Root exports and Engine parameters: no growth. ToolResult/provider/context/
  Trajectory wire, CAS and permission/sandbox authority: unchanged. WorkGraph
  gains `transfer_admitted` and `ownership_committed` state values. Consumers
  must distinguish admission from business terminal completion. Read/Edit direct
  calls now return ToolResult; use status and output instead of parsing strings.
  Observation retains dict and dataclass compatibility with one field store.
- Unknown effects are not replayed, committed effects are not retried; application
  waiting/business retries/manual reconciliation remain explicit. No distributed
  scheduler or external exactly-once claim. Func inert retry, SharedMemory/MCP/
  benchmark expansion and shared toolset approval metadata remain outside scope.

Evidence files: [manifest](v5_r1_c_evidence/manifest.json),
[final checks](v5_r1_c_evidence/qualified-checks.json),
[final interleavings](v5_r1_c_evidence/final-interleavings.json),
[installed consumers](v5_r1_c_evidence/installed-consumers-final.json).

### Final outcome

- Final full pytest: **3461 passed, 51 skipped in 304.58s (0:05:04)**. The 51 existing conditional skips
  match the first full run; no skips, exceptions, masked exits or rerun-only
  clearing were added. Real-model endpoints/keys remained disabled.
- All three behavior scopes passed. EN/zh tutorials, declarations, architecture
  debt follow-up and installed consumer evidence are included in the final
  documentation/evidence commit. No quality allowance shrink was needed.
- Only remote operation: the required initial fetch. No push, merge of another
  lane, deployment, publication, model request, stash/reset or worktree deletion.
  The source checkout drafts were left in place.

- Final archive review detected pytest trailing whitespace in newly tracked raw
  failure logs. Archived copies were whitespace-normalized; raw originals and
  the baseline SHA remain retained. A separate evidence-only commit records
  this formatting correction; no runtime/test result or failing attempt changed.
