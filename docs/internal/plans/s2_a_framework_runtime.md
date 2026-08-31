# S2 Lane A framework runtime composition and persistence ADR

Status: implementation-ready
Baseline: `446a347d1ac73636476ca2515a01da601b567c68`
Read-only ledger successor: `47cd4dc5e1ed1b2b0d244bfc90fac031ec55be32`
Branch: `codex/v4-s2-a-framework-runtime`
Worktree: `/Users/morinop/Desktop/WhitzardOS-s2-a`
Owner: S2 Lane A

## Outcome and scope

Lane A converges runtime construction, the single-agent Session facade, and
durable session-head persistence on the existing `AgentModule + Engine` kernel.
It does not create a second execution loop, a `SessionStore`, a scheduler, a
fork runtime, or a Python-stack serializer. The checkpoint package remains the
only persistence mechanism.

The ordinary path is:

```python
session = Engine(agent).session(task)
result = session.run()

session = Engine.restore(pause.session_id, resolvers=resolvers)
result = session.run(steering="new constraint")
```

`Session.run()` delegates to `Engine.run()`. A Session object is a scoped
client for a durable identity; it does not contain a second state machine or a
copy of agent state.

## Exact-source census

The census was performed at the exact baseline before implementation.

| Surface | Current source and behavior | Decision |
| --- | --- | --- |
| Agent policy | `qitos/core/agent_module.py`; owns state creation, decide/reduce hooks, model/tool references, and convenience `run()` construction | Keep policy ownership. Session restoration resolves an AgentModule; it does not persist the live agent. |
| Engine kernel | `qitos/engine/engine.py`; constructor has 30 parameters, `run()` is the canonical loop, `init_session()`/`step()` are the interactive path | Keep one loop. Add one composition parameter and a Session facade; retain existing constructor parameters as compatibility adapters. |
| Engine configuration | `qitos/engine/states.py::EngineConfig`; JSON-safe descriptive export, currently not a construction recipe | Extend only the runtime-composition portion. It records logical references and policy/capability identifiers, never live values or secrets. |
| Session contracts | `qitos/core/session.py`; already freezes typed identities, lifecycle, `SessionHead`, resolver references, component codecs, strict `SessionSnapshot`, and pause receipts | Reuse without a parallel contract. Add only missing runtime error/capability vocabulary and resolver namespaces required by more than one runtime package. |
| Snapshot composition | `qitos/core/snapshot_composition.py`; composes required S1 codecs owned by session, conversation, effects, and work graph | Runtime defaults use the core Session-owned codecs. B/C/D add their owned codecs through explicit composition; A never fabricates their facts. |
| RunState | `qitos/engine/run_state.py`; independently serializes agent state, records, events, checkpoint ID, trace, context, budget, and tokens | Compatibility reader/writer only. New Session runtime never writes RunState as persistence truth. A bounded adapter may project a canonical SessionSnapshot into RunState for old consumers. |
| Checkpoint v2 | `qitos/checkpoint/store.py`, memory and SQLite stores; addresses immutable checkpoints by `thread_id + checkpoint_id`, persists mostly `state_data`, and has no session head/CAS | Extend this package with atomic immutable-snapshot plus mutable-head operations. Public session APIs use `session_id`; the legacy `thread_id` field remains only on old checkpoint calls. |
| Checkpoint v1 | `qitos/checkpoint/checkpoint.py::CheckpointManager`; JSON files named by `run_id` and step | Do not extend. Existing Engine compatibility path remains; Session restoration reports typed incompatible when a canonical snapshot is absent. |
| Durability | `qitos/checkpoint/durability.py`; sync, background-thread async, and exit buffering; background failures are swallowed | Durable Session head commit requires synchronous atomic persistence. Async/exit remain legacy checkpoint policies and cannot produce a `paused` receipt. |
| Interrupt | `qitos/engine/interrupt.py` and `Engine._save_interrupt_checkpoint()`; re-executes a step and generates a transient ID without a store | Keep the old entry point. With Session runtime it adapts to cooperative pause; without durable capability it must not be represented as a durable paused session. |
| Resume | `Engine.resume_from_checkpoint()` reconstructs state from `_active_state` type or base `StateSchema`, sets run ID from checkpoint `thread_id`, and restores task from checkpoint metadata `run_id` | Preserve for compatibility. New `Engine.restore(session_id, resolvers=...)` reads a canonical snapshot, resolves the agent/state type, acquires ownership by CAS, and starts a new run ID. |
| Trace identity | `qitos/trace/*` and `qitos/engine/_trace_runtime.py`; trace directory and events use `run_id`; qita reads/forks trace run directories | Keep trace `run_id` as an execution-attempt identity. Do not infer session/checkpoint lineage from trace names. D subscribes to explicit lifecycle facts. |
| qita fork | `qitos/qita/_cli_app.py`; copies trace artifacts and synthesizes a fork run ID | Out of Lane A scope and not a durable Session fork. Task 12E/D must adapt it after reviewed runtime facts exist. |

Exact consumer inventories were generated with `rg` for `RunState`,
`CheckpointData`, `CheckpointStore`, `CheckpointConfig`, `thread_id`, `run_id`,
`session_id`, interrupt/resume, qita fork, and trace writers. No source was
inferred from a class or database private attribute.

## ADR-1: ownership and one runtime truth

| Object | Identity and owner | Mutable truth |
| --- | --- | --- |
| `AgentModule` | Resolvable agent policy/configuration identity | No durable execution ownership; live model/tools remain process-local. |
| `Engine` | One process-local executor for one run at a time | Owns the canonical lifecycle loop and transient execution mechanics. |
| `EngineConfig` | JSON-safe description of construction choices | No live object, secret, lock, client, path identity, or registry contents. |
| `Session` | Long-lived `SessionIdentity`; facade owned by engine runtime | No copied agent state. It reads and advances the checkpoint head. |
| Run | New `RunIdentity` per start/restore attempt | Current head owner while its expected generation remains current. |
| Snapshot | Immutable `SnapshotIdentity`; semantic owners produce components | Canonical complete durable runtime truth. |
| Checkpoint | Immutable `CheckpointIdentity`; checkpoint store owns bytes | Storage envelope and lineage node for one SessionSnapshot. |

The only durable truth is `SessionSnapshot` stored in a canonical Checkpoint.
`RunState` is a compatibility projection, not a writer for Session runtime.
Legacy checkpoints are read only by their existing entry points or rejected by
the Session reader with a typed incompatible-checkpoint failure.

## ADR-2: checkpoint session-head protocol

`CheckpointStore` gains optional-by-default capability methods so old third-
party checkpoint stores remain instantiable and report a typed unsupported
capability rather than failing ABC construction. Conforming Session stores
implement:

```text
commit_session_snapshot(request) -> durability receipt
get_session_head(session_id) -> head record | None
get_session_snapshot(snapshot_id) -> immutable snapshot record | None
list_session_lineage(session_id, limit=...) -> newest-first immutable records
session_capabilities() -> stable capability identifiers
```

The commit request contains distinct session, snapshot, checkpoint, old/new
owner, expected generation, expected checkpoint, lifecycle, and strict JSON
payload fields. Creation expects no head and creates generation zero. Every
advance requires both expected generation and expected checkpoint. A normal
owner commit also requires the expected owner; restore may explicitly transfer
ownership from that owner to a newly generated run.

The reference implementations use:

- memory: one lock protects immutable checkpoint insertion, snapshot index,
  and head CAS;
- SQLite: one transaction protects those same facts. `session_heads` and the
  snapshot-to-checkpoint index contain pointers only; snapshot payload bytes
  live once in `checkpoints.state_data`.

All values returned from the store are deep-isolated. Conflict, corruption,
unsupported capability, incompatibility, and persistence failure have distinct
typed exceptions. A success receipt says whether durable atomic persistence
occurred; an accepted request is never reported as paused.

## ADR-3: runtime composition boundary

One `RuntimeComposition` value is passed through `Engine`, with Engine-created
defaults when omitted. It composes:

- canonical checkpoint store and durability policy;
- explicit `ResolverRegistry`;
- existing ActionExecutor policy;
- the B-owned context/model runtime binding;
- lifecycle policy and cooperative pause support;
- snapshot component producers/codecs;
- runtime event sink.

The value is process-local and may hold live implementations. Its exported
`RuntimeCompositionConfig` is separate, strict JSON-safe metadata containing
only logical resolver references, policy identifiers, component schemas, and
capability names. No global resolver or component registry is introduced.

Missing capabilities identify the exact capability and remediation. Default
users do not construct a registry: `Engine.session()` binds the current agent,
store, model, tools, and environment into the Engine-owned local resolver set.
Fresh-process users provide a compatible resolver set explicitly.

## ADR-4: Session runtime seam

The stable seam supports create, run, inspect, request pause, restore,
lifecycle, capability discovery, current head, and snapshot commit.

- `Session.run()` invokes the existing Engine loop.
- `Session.pause()` is a cooperative request. It does not create a worker or
  promise Python-thread hard cancellation.
- A lifecycle policy may deterministically request pause at an Engine boundary.
- Only a recorded, quiescent `PauseSafety` may commit `paused`.
- An executor/policy without pause support raises typed unsupported capability.
- Terminal Session run/pause/restore operations raise typed invalid lifecycle.
- Restore validates snapshot integrity and component schemas before resolving
  live resources, then transfers head ownership with expected-generation CAS.
- A resumed run receives a new run ID. The session and work lineage do not
  masquerade as the previous process.

Fork and multi-agent scheduling remain out of scope.

## Compatibility routes

- `Engine.init_session()` and `step()` remain unchanged for interactive callers.
- `Engine.resume_from_checkpoint()` and `resume()` remain available for v2
  run-state checkpoint callers.
- `CheckpointManager` remains deprecated and unextended.
- New Session persistence never uses checkpoint `thread_id` as a run ID; it
  stores the session identity in that legacy storage-address field only inside
  the checkpoint adapter.
- `RunState` remains importable and round-trippable, but is explicitly a
  compatibility projection.

## Extension conformance and fixtures

The protocol suite will exercise memory, SQLite, and a test-owned third-party
store using public methods only. It covers custom resolver and snapshot
component producers, unsupported pause/store capability, stale generation and
owner, corrupt/incompatible snapshots, fresh-process SQLite restoration,
serialization isolation, and equivalent reference/third-party semantics.

`tests/fixtures/s2/lane_a/` contains portable JSON fixtures plus a manifest with
exact SHA-256 digests and producer commit. No fixture records a secret, live
object, or host path as identity.

## Interface budget

- Beginner path: `AgentModule`, `Engine`, `Session`, `Task`, and result/pause
  receipt. Persistence/CAS records are absent from the root `qitos` export.
- `Engine.__init__` grows by at most one `runtime` composition parameter.
- Advanced engine APIs live under `qitos.engine.runtime` and
  `qitos.engine.session_runtime`.
- Persistence protocols live under `qitos.checkpoint.session` and are exported
  only from `qitos.checkpoint`.
- No public type name contains `V1`, `V2`, `Legacy`, `Next`, or `NewSessionStore`.
- Existing root exports do not grow in Lane A.

## B/C/D handoff contract

- Lane B supplies a `RuntimeSnapshotComponent` with its exact conversation,
  request/codec report, context selection, continuation, and queued-steering
  schema. A stores its envelope without interpreting provider payloads.
- Lane C supplies a `RuntimeSnapshotComponent` with partial-batch, effect,
  worker-running, and quiescence facts plus the `PauseSafety` producer. A does
  not infer completion or exactly-once effects.
- Lane D receives Session lifecycle/head commit events from the runtime event
  sink. It must preserve explicit session/run/snapshot/checkpoint identities
  and cannot infer lineage from a trace directory name.
- Each producer handoff binds API/schema, portable fixture path, SHA-256 digest,
  and producer commit. A's evidence records the unsupported-capability matrix.

## Implementation and verification ledger

- [ ] Canonical checkpoint session protocol and typed failures
- [ ] In-memory atomic CAS implementation
- [ ] SQLite atomic CAS implementation and schema upgrade
- [ ] Runtime composition/configuration
- [ ] Session facade and Engine adapters
- [ ] Cooperative pause and terminal rejection
- [ ] Fresh-process restoration
- [ ] Third-party conformance implementation
- [ ] Portable fixtures, digests, evidence, and handoffs
- [ ] Focused, architecture, static, and full-suite verification

Shared `README`, `CHANGELOG`, `docs/progress.md`, and `docs/v4` status files are
leased to the integration owner by the S2 dispatch and are intentionally not
modified in this lane. The final evidence names the exact integration updates
required by the repository-wide documentation policy.
