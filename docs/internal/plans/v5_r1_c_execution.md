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
Qualification pending; no passing claim yet.

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
