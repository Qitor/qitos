# S3 Lane A — Session fork, lineage, and ownership fencing

Status: producer implementation and qualification complete
Updated: 2026-08-31
Owner: S3 Lane A
Dispatch source: `851f7902f15da670e72f4c04d7453cf37201aee7`
Branch: `codex/v4-s3-a-session-fork`

## Outcome

Implement `session.fork(snapshot=...)` as a thin operation over the existing
Session facade and canonical `CheckpointStore` Session-head protocol. A fork
creates one new authoritative child head and explicit lineage without changing
the source head, source snapshot, deprecated checkpoint manager, Engine loop,
or root exports.

## Exact-source census

- `qitos/core/session.py` owns distinct Session/Run/Snapshot/Checkpoint/
  WorkItem/Attempt identities, `FORKED_FROM`, lifecycle gating, strict snapshot
  integrity, and the operation matrix. `FORK` is allowed only from `paused`,
  `waiting_input`, and terminal lifecycles; `created`, `running`,
  `pause_requested`, `pausing`, and `restoring` are rejected.
- `qitos/engine/session_runtime.py` owns the small Session facade, creation,
  cooperative pause, resolver-only restoration, state reconstruction, and
  snapshot commits. It has no fork method at dispatch.
- `qitos/checkpoint/session.py` owns the atomic snapshot-plus-head request and
  typed CAS/persistence failures. `CheckpointStore` exposes optional Session
  capabilities, implemented by Memory and SQLite.
- `qitos/checkpoint/fork.py` copies a legacy `Checkpoint` into a thread/time-
  travel branch. Its API and semantics remain unchanged and are not Session
  fork truth.
- `RunState`, `Engine.restore`, `Engine.resume_from_checkpoint`, interrupt
  compatibility, and deprecated `CheckpointManager` remain adapters/compat
  surfaces; none becomes a new fork store or execution path.
- Existing S1 fixture `tests/fixtures/session/forked-session.json` proves only
  contract shape, not a runtime fork or atomic child-head creation.

## Contract and compatibility path

1. Add an explicit fork-lineage snapshot component under a new writer/schema
   identifier; do not mutate existing component identifiers or snapshot v2.
2. Add module-level fork request/receipt records to the checkpoint Session
   protocol and a store capability for atomic child declaration/head creation.
3. Implement that capability transactionally in Memory and SQLite. An operation
   identity is the idempotency key: an exact retry returns the original receipt;
   a contradictory retry is typed duplicate rejection.
4. Add `Session.fork(snapshot=None, operation_id=None)`. `None` captures the
   authoritative head at call time; an explicit identity must resolve to the
   same source Session. The source snapshot is strictly decoded and integrity-
   verified before the store transaction.
5. Child Session/Run/WorkItem/Attempt/Snapshot/Checkpoint identities are all
   fresh. The child begins with generation zero and a distinct owner. A usable
   child facade is reconstructed through the existing resolver/runtime seam;
   clean-process restore continues to use `Engine.restore`.

## File lease and modification scope

Lane-owned implementation files: `qitos/core/session.py`,
`qitos/engine/session_runtime.py`, `qitos/engine/runtime.py`, and
`qitos/checkpoint/{session,store,memory_store,sqlite_store}.py`; focused tests
and `tests/fixtures/s3/lane_a/`; this plan/evidence only. Aggregate `__init__`
files and all shared README/CHANGELOG/progress/v4 documents are frozen for the
G4 owner and will not be edited.

## Failure model and crash windows

| Case | Required fact |
|---|---|
| declaration write fails | typed persistence failure; no child head |
| source verified, child not committed | no child head or runnable child |
| child committed, caller loses result | same operation id returns the same receipt |
| source owner continues | source CAS remains independent of child generation |
| child resolver missing/incompatible | typed restore failure; committed child remains inspectable |
| another generation advances child | stale/superseded owner commit is rejected |
| missing/corrupt/mismatched snapshot | typed rejection before child commit |
| unsupported third-party store | typed capability error |
| unresolved worker/effect | snapshot is not migratable and fork is rejected |

Persistence failure and uniqueness conflicts occur inside one Memory lock or
one SQLite `BEGIN IMMEDIATE` transaction. No successful receipt is returned
before child snapshot, head, lineage declaration, and operation id are durable.

## C/D handoff

Lane C consumes `Session.fork`, the module-level fork receipt and lineage
component, source identities, child Session/head identities, owner generation,
stale-owner failure, and the clean-process fixture. It must not copy enums or
parse identifiers.

Lane D consumes the same persisted fork declaration/receipt, source snapshot
and checkpoint, source/child work identities, child run/attempt, owner and
restore generations, and typed failure codes. It must use strict readers and
must not infer lineage from paths or names.

## Verification ledger

- [x] focused core/checkpoint/engine Lane A tests
- [x] Memory, SQLite, and independent third-party-style store conformance
- [x] bounded clean-process restore and source/child continuation isolation
- [x] required regression suites and interface budgets
- [x] static-quality ratchet, stable flake8, stable mypy, full `pytest -q`
- [x] producer fixtures, digests, manifest, qualification evidence
- [x] `git diff --check`, self-review, committed clean worktree

## Qualification result

- implementation producer: `ae62ba1ea5fef7a472609dcb11d23a5f21733410`;
- producer fixture commit: `feba1bf6d2312b82c7f03ce0b3c1f07e50712938`;
- focused Lane/regression group: 264 passed;
- producer bundle tests: 17 passed, including spawn-process Event fencing and
  incompatible resolved-state rejection;
- architecture/public-interface/no-local-path group: 16 passed;
- pinned static-quality ratchet: 376 findings matched (354 active, 22
  vendored/generated);
- stable flake8: clean; stable mypy: 91 source files clean;
- full suite: 2269 passed, 50 skipped.

No Engine constructor parameter, root export, aggregate checkpoint export,
SessionStore, execution loop, or alternate checkpoint truth was added. The
existing `qitos.checkpoint.fork` API and deprecated manager remain unchanged.

## Known gaps and unsupported claims

This producer does not claim distributed scheduling, remote lease renewal,
hard worker cancellation, or exactly-once external effects. An
`outcome_unknown` effect remains non-forkable until reconciled. Lane C still
owns durable child scheduling/join behavior; Lane D still owns graph/timeline
projection. Shared README, changelog, progress, and Task 12/13 documentation
updates remain a recorded G4 handoff because their integration-owner lease was
not granted to Lane A.
