# Task 12 — durable session runtime and process-independent resume

Status: 12B–D single-agent runtime qualified at G3; 12E fork/qita migration remains
Depends on: Task 01; coordinates with Tasks 02, 03, 04, and 09
Unblocks: Task 05 schema freeze, Task 13 durable multi-agent work, and the v4
long-horizon reference flow
Risk: critical — execution identity, persistence truth, side-effect recovery, and
public runtime ergonomics

---

## 1. Goal

Make a QitOS session a durable, inspectable runtime object rather than an
in-memory convenience around `Engine.step()`.

The required north-star invariant is:

> At any declared safe boundary, QitOS can pause a run, terminate the process,
> restore it in a new process or node, and continue with the same conversation,
> state, tool-batch facts, context references, agent ownership, budgets, and
> trajectory lineage without duplicating any effect already recorded as
> committed.

This is framework infrastructure, not a hosted agent product or a distributed
scheduler. The first reference implementation is local and process-independent;
its contracts must allow a caller-owned scheduler or store to be substituted.

## 2. Current baseline and the gap

QitOS already has useful pieces:

- `Engine.init_session()`, `step()`, and `run()` for in-memory execution;
- `RunState` for an Engine-oriented resumable snapshot;
- the current checkpoint package with immutable checkpoints, pending writes, SQLite,
  durability modes, and fork/time-travel primitives;
- interrupts and `resume()`/`resume_from_checkpoint()`;
- trace run IDs and qita replay/fork surfaces.

They are not yet one durable session protocol:

- session, run, checkpoint `thread_id`, and trace identity are partly conflated;
- a checkpoint primarily persists `state_data`, not the complete execution head;
- a fresh process cannot reliably reconstruct the task, concrete state schema,
  agent/configuration, exchange log, open tool batch, context/artifact references,
  or active ownership from the checkpoint alone;
- `RunState` and checkpoint v2 can become competing persistence truths;
- an interrupt may return a checkpoint-shaped identifier even when no durable
  store exists;
- in-flight model calls, threads, subprocesses, and external effects do not yet
  have a unified quiescence and recovery contract.

Task 12 converges these pieces in place. It must not add a second Engine, a
parallel checkpoint store, or a durable Python-stack serializer.

Dispatch note: G2 closed from fixed S2 dispatch baseline
`446a347d1ac73636476ca2515a01da601b567c68`. G3 replayed the producers onto
integration source `47cd4dc5e1ed1b2b0d244bfc90fac031ec55be32`; later
documentation-only ledger commits do not redefine that ancestry.

### G3 implementation receipt (2026-08-31)

`Engine(agent).session(task)` is now the small façade over the one Engine loop.
The canonical checkpoint store atomically advances one Session head and stores
Engine-owned conversation and tool-batch components. Pause is cooperative and
becomes persisted only after quiescence and synchronous head commit. Restore
resolves the agent/model/tools/checkpoint/continuation resources, transfers the
owner generation, closes an original open batch before model execution, and
rejects stale parent or late terminal writes.

The authoritative offline proof uses SQLite and twenty independent pairs of
clean processes. It preserves state, budget, ExchangeLog, reasoning,
continuation, artifact and trajectory cursor facts; applies steering once;
does not rerun completed/committed slots; runs only the eligible missing slot;
and reduces the original decision once. This is Session-head replay safety, not
an exactly-once guarantee for external effects. Fork/qita migration and durable
multi-agent scheduling remain 12E/S3 work.

## 3. Identity and lineage contract

The following identities are distinct and must never be inferred from one
another:

| Identity | Meaning | Lifetime |
|---|---|---|
| `session_id` | Long-lived interactive or research container with one durable head | Across runs, pauses, and process restarts |
| `run_id` | One execution attempt between start/resume and a terminal or paused boundary | One attempt |
| `work_item_id` | One unit of work owned by one agent; Task 13 builds a graph from these | Across retries and ownership transfer |
| `checkpoint_id` | Immutable snapshot identity | Permanent while retained |
| `exchange_id` | One model transaction in Task 02 | One exchange |
| `tool_call_id` | Provider-scoped action slot | One declared call |
| `agent_id` | Resolvable agent specification identity, not a live Python object | Across restoration |

Lineage records include `parent_run_id`, `parent_work_item_id`, source
`checkpoint_id`, and fork/handoff cause where applicable. A resumed run gets a
new `run_id`; it advances the existing session/work item rather than pretending
the previous process never ended.

## 4. Session lifecycle and safe boundaries

The internal lifecycle vocabulary is:

```text
created -> running -> pause_requested -> paused -> restoring -> running
                    \-> waiting_input
running -> completed | failed | cancelled
```

Public names are frozen only in 12A after compatibility review. Required
semantics:

- a pause request is cooperative and becomes durable only at a declared safe
  boundary;
- the canonical safe boundary is after a model response or a tool result has
  been durably recorded and before the next externally visible operation;
- a partially completed parallel tool batch is safe only when every completed
  slot and every still-open slot is explicit in the snapshot;
- steering is queued and consumed once at the next exchange-safe boundary;
- `paused` means the session head is persisted and no framework-owned worker is
  permitted to commit into that head;
- `waiting_input` is a durable pause with an input requirement, not a successful
  terminal result;
- `cancelled` is terminal for that work item; `fork` creates a new lineage rather
  than reopening it.

QitOS does not serialize the Python call stack. A thread or subprocess that
cannot be quiesced produces `worker_still_running`/`quiescence_required`; the
snapshot is not migratable until policy declares or proves a safe boundary.

## 5. One persistence truth

Checkpoint v2 remains the persistence mechanism. Task 12 must not introduce a
parallel `SessionStore` containing a second copy of runtime state.

The durable model has two layers:

1. a small mutable session index containing lifecycle, current head checkpoint,
   generation, and compare-and-swap ownership information;
2. immutable, versioned session snapshots stored through the checkpoint store.

`RunState` becomes an Engine-facing view/adapter of that canonical snapshot or is
retired through Task 10. It must not remain an independently serialized truth.
The deprecated v1 `CheckpointManager` receives adapters only; it is not extended.

Atomic head advancement must use an expected generation/checkpoint. A stale
process cannot overwrite a newer owner or checkpoint. Store implementations may
offer stronger transactions, but all must expose the same typed conflict and
durability outcomes.

## 6. Durable session snapshot

A versioned snapshot contains at least:

- all identities and lineage from Section 3;
- lifecycle state, pause reason, requested input, and resume generation;
- task identity/content and concrete `StateSchema` type reference plus canonical
  state data;
- resolvable `AgentSpec` identity and the active agent owner;
- Engine construction/configuration, policy versions, and capability digests;
- Task 02 `ExchangeLog` head, provider continuation references, queued steering,
  and open/partial tool-batch closure facts;
- Task 03 canonical tool outcomes, attempt/effect receipts, and `outcome_unknown`
  markers;
- budgets, counters, stop/recovery state, and deterministic random seed/state
  when framework-owned;
- Task 04 context, memory, and artifact references plus retention/sensitivity
  metadata, never host paths as identities;
- Task 13 child work items, ownership transfers, and join state once available;
- trace cursor/completeness and versioned migration receipts;
- durability status for the snapshot and its referenced pending writes.

Snapshots never serialize live clients, locks, file descriptors, threads,
subprocess handles, closures, raw credentials, or opaque caller objects.
Provider, model, tool, environment, secret, and artifact dependencies are stored
as typed resolver references. The caller-owned composition root resolves them on
restore and QitOS validates identity/capability digests before execution.

## 7. Side effects and recovery truth

QitOS cannot promise exactly-once external effects when the remote system lacks
idempotency or transactional receipts. The framework contract is narrower and
honest:

- exactly-once **commit to the session head** through generation checks;
- stable idempotency keys where the tool/provider supports them;
- effect receipts separating `not_started`, `started`, `committed`, `failed`,
  and `outcome_unknown`;
- no automatic retry of `outcome_unknown` without an explicit safe-to-retry or
  reconciliation policy;
- completed parallel slots are never re-executed merely because their siblings
  were incomplete;
- late results from timed-out or superseded workers cannot mutate the head.

Likewise, QitOS does not resume a provider's in-memory streaming stack. It
checkpoints before dispatch, or records the complete decoded provider result
before advancing. A severed call has a typed unknown/retry decision, never a
fabricated continuation.

## 8. Restore, resume, and fork algorithm

A process-independent restore must:

1. load the session index and immutable head with integrity verification;
2. validate schema/writer versions and apply explicit migrations;
3. acquire ownership with an expected generation lease;
4. resolve the agent, model, tools, environment, stores, and secrets through the
   caller's composition root;
5. validate configuration and capability digests, failing typed on mismatch;
6. reconstruct state, exchanges, contexts, batches, budgets, children, and trace
   cursor without replaying committed effects;
7. apply queued human input exactly once if supplied;
8. start a new `run_id` and append a restore receipt linked to the prior run;
9. continue from the recorded phase boundary.

`fork(checkpoint_id)` creates a new `session_id` and work lineage pointing to an
existing immutable snapshot. Forking never moves the source session head and
never shares a mutable state object.

## 9. Public developer experience

The exact public API is a 12A decision, but it must support a compact workflow of
this shape without private Engine helpers:

```python
session = engine.start_session(task, session_id="research-42")
result = session.run()
pause = session.pause()

# A different process builds a compatible Engine/composition root.
session = engine.resume_session("research-42", input=user_message)
branch = session.fork(checkpoint_id=pause.checkpoint_id)
```

`Engine.init_session()` remains compatible through an adapter until deprecation
evidence exists. A handle is not the persisted object; it is a scoped client for
the durable session identity.

## 10. Work packages

### 12A — identity, lifecycle, and snapshot ADR

- Write the implementation plan and ADR with an exact census of `RunState`,
  checkpoint v1/v2, interrupt/resume, qita fork, and trace identity consumers.
- Freeze identity meanings, lifecycle transitions, safe boundaries, snapshot
  schema, resolver references, and typed errors.
- Provide versioned single-agent and partial-parallel fixtures.
- Decide the `RunState` adapter/retirement path before adding fields to it.

### 12B — session index and checkpoint convergence

- Add atomic session-head/generation operations to checkpoint v2 without a
  second state store.
- Persist complete versioned snapshots and pending-write/durability receipts.
- Add migrations from supported existing checkpoints and fail typed on an
  unreconstructable legacy snapshot.
- Prevent stale-owner writes and deep-isolate all returned data.

### 12C — safe pause and same-process resume

- Make pause, waiting-input, interrupt, and cancellation transitions explicit.
- Checkpoint partial parallel completion and queued steering at safe boundaries.
- Prove same-process pause/resume with no duplicate completed tool slot.
- Refuse migratable-paused status while a non-quiesced worker may still commit.

### 12D — clean-process restore vertical slice

- Restore through a fresh Engine and resolver composition root; do not depend on
  `_active_state` or another live object from the original process.
- Exercise start -> model -> parallel tools -> pause -> process exit -> restore
  -> steering -> completion.
- Verify committed-effect, trace, budget, state, exchange, and artifact parity.
- Add deterministic store-failure, schema-mismatch, missing-secret, and
  `outcome_unknown` recovery cases.

### 12E — fork, qita/CLI integration, and compatibility

- Expose typed inspect/pause/resume/fork operations through thin CLI/qita
  adapters after the runtime contract is stable.
- Move qita fork away from the deprecated debug dependency.
- Document migration from `init_session`, `RunState`, interrupt IDs, and v1
  checkpoints.
- Add one unrelated-agent consumer and the compact public-API example.

## 11. Acceptance criteria

- [ ] Session, run, work item, checkpoint, exchange, tool call, and agent
  identities are distinct in schema, trace, and tests.
- [x] One versioned persistence truth restores in a fresh process without any
  live object from the original process.
- [x] A partial parallel batch survives restore; completed slots are not rerun
  and missing slots close exactly once.
- [x] Queued steering survives restart and is consumed exactly once.
- [x] Stale owners and late workers cannot advance the session head.
- [x] Snapshot callers can distinguish accepted, persisted, failed, dropped,
  conflicted, non-migratable, and outcome-unknown states.
- [x] Secrets and host-only handles are resolver references, not snapshot data.
- [ ] Fork creates isolated lineage without mutating the source session.
- [ ] Existing supported checkpoints either migrate through fixtures or fail
  with a documented typed incompatibility.
- [ ] One campaign-derived and one unrelated-agent fixture pass the clean-process
  vertical slice.
- [x] No second Engine, scheduler, checkpoint store, or runtime-state truth is
  introduced.

## 12. Verification

```bash
pytest -q tests/checkpoint
pytest -q tests/engine/test_run_state.py tests/engine/test_interrupt.py
pytest -q tests/e2e/test_checkpoint_resume.py
pytest -q tests/engine/test_session_runtime.py
pytest -q tests/e2e/test_session_process_restore.py
pytest -q tests/test_architecture_boundaries.py tests/test_public_surface.py
python scripts/static_quality.py check
pytest -q
git diff --check
```

The two session-specific paths are Task 12 deliverables. Process-restoration
tests use deterministic local stores, bounded subprocesses, and no live model.

## 13. Stop-and-escalate decisions

Stop for review before:

- naming a checkpoint `thread_id`, `run_id`, and `session_id` interchangeably;
- adding a `SessionStore` that duplicates checkpoint payloads;
- claiming a thread or external effect was cancelled/executed exactly once
  without backend proof;
- serializing a live agent/model/tool/env object or a raw secret;
- automatically retrying `outcome_unknown` effects;
- extending deprecated checkpoint v1 instead of adapting it;
- freezing Task 05 trajectory v2 without session/run/work-item lineage;
- making a distributed queue, hosted daemon, or product-specific coordinator a
  dependency of the base framework.
