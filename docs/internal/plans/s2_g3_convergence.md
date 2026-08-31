# S2 G3 runtime vertical convergence plan

Status: S2 runtime closed on the qualified G3 candidate; promotion operational
steps pending
Updated: 2026-08-31
Owner: integration owner
Integration source: `47cd4dc5e1ed1b2b0d244bfc90fac031ec55be32`
Branch: `codex/v4-s2-g3-convergence`
Worktree: `/Users/morinop/Desktop/WhitzardOS-s2-g3`

## Outcome

Converge the independently qualified A/C/B/D S2 producers into one executable
single-agent runtime over the existing `AgentModule + Engine` loop, one
checkpoint-backed Session head, one ExchangeLog, one ToolResult, one canonical
ArtifactRef, and one extension-facing event-sink concept. Prove deterministic
pause, process exit, resolver-only restore, partial-batch continuation, steering
consume-once, stale/late rejection, and inspectable lineage without claiming
exactly-once external effects or freezing the candidate Trajectory schema.

## Fixed replay receipt

| Lane | Source commit | Replay commit |
| --- | --- | --- |
| A | `bc725e8b77576a7a0b5c165a5066c83c4d9965c8` | `110238aa6b4ea52ed3f01bd81ae768dd8bd04cc7` |
| A | `a075ea6e1e18064a79866a6f4cadecdb7536c746` | `f56d59c6d0897433b125d5b700dfd1fee8d21360` |
| C | `769422d4d6b5dfd0552fbe98a34def1885786848` | `2b61cd8fb601246d8758d409b084837a34c07436` |
| C | `c63917ab48aff65b3e5df615ea947ab183653d97` | `e6e450deb56c228a1f28a13e1b1b4b5340b2e662` |
| C | `6a8ff24ede400a549e1f3dafa593a23e61b845f3` | `ab255b333585cbf827127bbc800609f32363c478` |
| B | `60e8d94edb9a5f00434095a3489e1e1100185bea` | `25af41fa65886ff2fdf7e82094749e67681be4cc` |
| B | `0c7bde6ddb5ff2a61116793274ec706666d91e0f` | `cabb9e543c40d1ab783e6f6ddd85c27dad5a933a` |
| D | `f8f63b2e6dd29fd98135c644b2964c0814551749` | `f569db44a51fd6015156bc7b5b33168ea192c5df` |
| D | `c034988a628881b55630f6a149c6b40a9a619070` | `7308f1cfe2149ae601e485d8eab936e7309abe79` |

The only replay conflict was `quality/static_baseline.json`. Neither lane
version is the final answer. The complete replay tree independently produced
`376 total / 354 active / 22 vendored-generated` with no exception growth.

## Pre-fix baseline

- full suite: `2242 passed, 50 skipped`;
- combined A/C/B/D contract suites: `219 passed`;
- static ratchet: `376 total`, `354 active`, `22 vendored/generated`;
- stable flake8: clean;
- stable mypy: clean on 90 source files;
- architecture/public/no-local-path: `10 passed`;
- root exports: 41.

## High-conflict leases

Lease owner: S2 G3 integration owner

Files and semantic purpose:

- `qitos/core/artifact.py`, `qitos/tracing/trajectory.py`, tracing
  stores/readers/exporters/sinks: canonical ArtifactRef identity and an
  unfrozen internal Trajectory candidate;
- `qitos/engine/runtime.py`, `qitos/engine/session_runtime.py`,
  `qitos/engine/engine.py`, `qitos/engine/action_executor.py`: one composition
  root, runtime-owned components, safe pause, partial-batch recovery, and event
  delivery through the existing loop/executor;
- `qitos/core/request_view.py`, `qitos/models/provider.py`: direct use of the
  Lane B component and resolver-only continuation restore;
- `qitos/core/tool_runtime.py`, `qitos/engine/tool_runtime.py`,
  `qitos/checkpoint/pending_writes.py`: one persisted batch truth advanced only
  through Session-head CAS;
- `qitos/checkpoint/__init__.py`: reduce aggregation to reviewed extension
  contracts; keep CAS implementation records on explicit module paths;
- `qitos/tracing/__init__.py`, `qitos/models/__init__.py`: remove unfrozen and
  implementation-record aggregation from broad module surfaces;
- shared README/CHANGELOG/progress/v4/architecture documents: synchronize
  integration truth after executable qualification.

No other lane is active in this worktree. These leases end with the G3
promotion candidate. They do not authorize S3 child scheduling, trace-v1
replacement, or provider-default expansion.

## Implementation sequence

1. [complete] Delete the tracing-local ArtifactRef and prove repository-wide
   class identity and public/export uniqueness.
2. [complete] Adapt Lane B `ConversationSnapshotComponent` directly to the
   Engine-owned runtime component contract and restore it into the same model
   runtime before execution.
3. [complete] Make Lane C batch snapshots and terminal receipts canonical
   Session components; commit each terminal slot through generation-checked
   Session-head advancement before reporting persistence.
4. [complete] Connect Session pause to ActionExecutor quiescence using condition/
   event acknowledgements and monotonic deadlines; make non-quiesced snapshots
   non-migratable and late writes stale.
5. [complete] Restore open batches before any new model decision, execute only
   eligible missing slots with original identities, and reject committed or
   outcome-unknown replay.
6. [complete] Converge `RuntimeEventSink` and Lane D `EventSink` behind one public
   extension concept, bridge exact A/B/C facts to candidate records, and split
   runtime versus schema/publication readiness.
7. [complete] Enforce the S2/current interface budget, root 41, beginner façade,
   and internal/private candidate exports.
8. [complete] Add controlled-failure proofs, one deterministic subprocess E2E,
   and a 20-process driver with no sleep/rerun ordering.
9. [complete] Synchronize EN/zh and architecture/evidence documents, qualify all
   branch gates, review the diff, and only then consider promotion.

## Stop gates

- Any new executor, SessionStore, provider transaction path, ArtifactRef,
  trajectory truth, or default candidate writer stops the change.
- A live framework-owned worker, unknown effect, failed required sink, missing
  required resolver, stale owner, or failed Session-head commit cannot produce
  a persisted paused receipt.
- Runtime qualification and Trajectory schema/publication qualification remain
  separate. S2 runtime closure cannot imply S3, writer rollout, qita migration,
  compression/index performance, or external exactly-once effects.

## Qualification split

Exact-source receipts bind the G3 runtime fixture and A/B/C qualification bytes
to producer commit `42d6821e4ceee7a09d3dda9011e687a8cb64f5ba`.
`scripts/qualify_s2_lane_d.py --json` reports all twelve required runtime
scenarios with `s2_runtime_ready=true` and zero findings. It separately reports
`trajectory_schema/publication_ready=false`, `qita_store_reader_default=false`,
and no measurements or claims. The candidate writer is not enabled.

The authoritative E2E uses SQLite, a deterministic provider, Event barriers,
and two clean Python processes per round. Twenty independent rounds prove that
the restored owner executes only the eligible missing slot, applies steering
once, resolves continuation, preserves artifact/budget/cursor facts, rejects
the old owner, and leaves the committed-effect counter at one.
