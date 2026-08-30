# ADR — one stable session runtime contract

Status: integrated and contract-qualified in G2; runtime behavior deferred
Date: 2026-08-30
Owner: Lane A / Task 12
Decision scope: identity, lifecycle, snapshot envelope, resolver references,
head generation, receipts, compatibility boundaries, and developer experience

## Decision

QitOS has one user-facing runtime concept: a **Session**. A session is a
long-lived execution container with one authoritative head. Its head points to
one immutable `SessionSnapshot` persisted through the existing checkpoint
mechanism. An invocation or resumed execution creates a distinct **Run**; a run
is never reused as a session ID.

Checkpoint is mechanism, not a competing user model. `RunState`, the deprecated
checkpoint manager, interrupt/resume, trace replay, and qita fork are migration
inputs or clients of the canonical session facts. They do not own another
session state.

Task 12A freezes contracts only. It does not claim that Engine pause, restore,
fork, or atomic head persistence is implemented.

G2 adds an explicit, extensible `SnapshotComponentRegistry`: the outer envelope
validates owner, slot, payload schema, requiredness, and digest, while each
semantic owner supplies exactly one codec. The stable composition directly
reads B's conversation component and C's effects and WorkGraph components.
Unknown owners/schemas, missing required components, and digest mismatches fail
typed; registration is explicit and contains no hidden global mutation.

## Beginner golden path

The intended public flow stays below twenty lines and hides persistence details:

```python
engine = Engine(agent)
session = engine.session(task)             # framework creates every identity
result = session.run()

pause = session.pause()                    # waits for a safe durable boundary
assert pause.persisted

# A new process constructs compatible defaults or explicit resolvers.
session = Engine.restore(
    pause.session_id,
    resolvers=my_resolvers,
)
result = session.run()

branch = session.fork(snapshot=pause.snapshot_id)
branch_result = branch.run()
```

The exact façade methods arrive in Task 12B–E. The contract proves that this
flow needs no manual ID, generation, CAS operation, component envelope, raw
receipt JSON, checkpoint directory knowledge, or resolver-reference assembly.

## Advanced recovery path

Advanced callers may:

1. inspect the current `SessionHead` and its generation;
2. select an older immutable snapshot for restore or fork;
3. provide a `ResolverRegistry` for model, tool registry, environment, artifact
   store, secret, checkpoint store, and provider continuation;
4. inspect `PauseSafety` and unresolved-effect facts;
5. reconcile `outcome_unknown` effects before permitting a retry;
6. receive typed generation-conflict, superseded-owner, persistence, resolver,
   integrity, and schema failures;
7. choose a policy after reloading the authoritative head.

Advanced control does not expose a second writer API. A caller can request an
expected generation, but only the store's atomic head operation may advance it.

## Sync/async symmetry

Sync and async handles share one identity, lifecycle, snapshot, resolver, and
receipt contract:

| Sync | Async | Same fact |
|---|---|---|
| `session.run()` | `await session.arun()` | one new `RunIdentity` |
| `session.pause()` | `await session.apause()` | one pause request and receipt |
| `Engine.restore(...)` | `await AsyncEngine.restore(...)` | one restore algorithm |
| `session.fork(...)` | `await session.afork(...)` | one isolated fork lineage |

`AsyncEngine` remains a façade over the same Engine kernel. It does not get an
async-only Session type or store. Cancellation of an awaiting task does not
prove the underlying sync worker or external effect stopped.

## Defaults

- The framework creates every session, run, snapshot, checkpoint, work-item,
  attempt, tool-call, and agent identity needed by the beginner path.
- One local checkpoint-store configuration is the persistence mechanism; a
  caller can inject another implementation of the same store contract.
- The composition root supplies a default resolver set for resources it built.
- `pause()` is cooperative and waits for a migratable boundary by default.
- The current snapshot writer emits `schema_version: 1` and SHA-256 integrity.
- Strict readers reject unknown top-level/component fields, wrong types,
  non-JSON values, non-finite numbers, missing required components, unsupported
  schemas, host-local paths, credential-bearing values, and digest mismatch.
- Restore starts a new run and validates resolver capabilities before execution.
- Fork generates a new session and snapshot identity at generation zero; it
  never moves or mutates the source head.

## Public surface budget

The desired beginner surface has five concepts:

1. `Engine.session(task)`;
2. `Session.run()` / async peer;
3. `Session.pause()` / async peer;
4. `Engine.restore(session_id, resolvers=...)` / async peer;
5. `Session.fork(snapshot=...)` / async peer.

Task 12A adds no root export, Engine parameter, alternate Engine, or public
store. Its code-level owner module is `qitos.core.session`. Later work may expose
the façade above only after consumer tests; it must not promote component, CAS,
or codec internals into the beginner API.

## Concepts hidden from ordinary users

- ID prefixes and relationship records;
- snapshot/checkpoint distinction;
- head generation and compare-and-set;
- component envelope and per-component version;
- resolver reference namespace, alias, and expected capability;
- durability queue state and checkpoint addressing;
- trace cursor and checkpoint file/database layout;
- effect reconciliation and quiescence details unless recovery is unsafe;
- migration receipts and historical codec choice;
- raw receipt JSON.

## Identity model

The canonical types live only in `qitos.core.session`. B/C/D import them rather
than copying enums.

| Type | Meaning | Generated by | May outlive process |
|---|---|---|---|
| `SessionIdentity` | long-lived container with one head | Session façade | yes |
| `RunIdentity` | one execution interval/attempt | Engine on start/restore | yes |
| `SnapshotIdentity` | immutable runtime-state envelope | snapshot writer | yes |
| `CheckpointIdentity` | one persistence commit | checkpoint mechanism | yes |
| `WorkItemIdentity` | Task 13 unit of owned work | work-graph owner | yes |
| `AttemptIdentity` | one concrete attempt | action/work runtime | yes |
| `ToolCallIdentity` | provider/tool correlation slot | request/action runtime | yes |
| `AgentIdentity` | resolvable execution capability subject | composition root | yes |

Each identity serializes as `{kind, value}` and validates its own opaque prefix.
Concrete types do not compare equal. `HeadGeneration` is a non-negative integer
value type, not an attempt number. `IdentityRelationship` validates a closed
directional pair; no code parses parents, delegates, forks, or attempts from ID
text.

Explicit relationships currently cover session/run, session/snapshot,
snapshot/checkpoint, run/work item, work item/attempt, attempt/tool call,
agent/work ownership, restore source, and fork source.

## Lifecycle model

Canonical states:

```text
created -> running -> pause_requested -> pausing -> paused -> restoring -> running
                                      \-> waiting_input -> restoring
running -> completed | failed | cancelled
any active owner view -> superseded
```

`pause_requested` means cooperative intent was accepted. `pausing` means the
runtime is reaching and committing a safe boundary. `paused` means a verified
snapshot was durably committed and framework-owned workers cannot commit to
that head. They are not synonyms.

`completed`, `failed`, `cancelled`, and `superseded` are terminal for that owner
view. Superseding an old owner does not terminate the authoritative session; it
prevents the old run/process from committing after a newer owner acquires the
head.

Operation permissions:

| Operation | Allowed lifecycle |
|---|---|
| run | created, paused, waiting_input |
| request/await pause | running, pause_requested, pausing |
| restore | paused, waiting_input |
| fork a retained snapshot | paused, waiting_input, completed, failed, cancelled, superseded |

Fork operates on an immutable retained snapshot. A running process cannot label
its mutable in-memory state as a fork source.

## Safe pause boundary

`PauseSafety` names model-result, tool-result, recorded partial-parallel,
waiting-input, and unsafe in-flight boundaries. A pause is migratable only when:

- every completed parallel slot is recorded;
- every still-open slot is explicit;
- framework-owned workers are quiesced or barred from committing;
- no unresolved external effect remains;
- the boundary is not an in-flight operation.

An unresolved effect raises `unresolved_effect`; another unsafe condition raises
`unsafe_pause_boundary`. QitOS does not claim exactly-once external execution.

## Session head and generation

Every session has one `SessionHead`:

```text
session identity
  -> immutable snapshot identity
  -> checkpoint commit identity
  -> head generation
  -> current owner run identity
```

Head advancement is an atomic compare-and-set against expected generation and
owner. A successful commit advances the generation exactly once. A retry of the
same persistence request must return its existing commit outcome rather than
advance again. Store idempotency details arrive in Task 12B.

- wrong expected generation -> `generation_conflict`;
- wrong owner at the current generation -> `superseded_owner`;
- rejected/failed persistence does not advance generation;
- failed persistence cannot emit a `paused` receipt;
- restore acquires the next owner/generation; the old process becomes
  superseded;
- fork creates a new session/head at generation zero and leaves the source
  unchanged.

This is exactly-once **head commit under CAS**, not exactly-once external effect.

## Persistence and pause receipts

`PauseReceipt` has mutually distinguishable outcomes:

| Status | Meaning | May report lifecycle paused? |
|---|---|---|
| accepted | request accepted but not durably committed | no |
| persisted | snapshot verified and head CAS committed | yes |
| rejected | policy/store rejected before commit | no |
| failed | persistence attempt failed | no |
| conflict | expected generation/owner lost | no |

Only `persisted` carries both snapshot and checkpoint identities and advances
generation by one. `require_persisted()` converts other statuses to stable typed
failures without requiring callers to inspect raw receipt JSON.

## SessionSnapshot envelope

`SessionSnapshot` is frozen, deep-owns nested values, emits deterministic
canonical JSON, and verifies a SHA-256 digest over every field except the
integrity record itself. It contains:

- internal envelope `schema_version`;
- snapshot and session identities;
- typed head generation and lifecycle;
- timezone-aware creation/capture/pause/safe-boundary time facts;
- ordered, unique versioned components;
- ordered, unique resolver references;
- integrity algorithm and digest.

The current required slots are `agent_state`, `engine_progress`,
`budget_capability`, and `trace_lineage`. The stable complete slot vocabulary is:

| Slot | Semantic owner | Envelope purpose |
|---|---|---|
| agent_state | A (state schema remains core/agent-owned) | Agent ref, StateSchema ref/data, task fact |
| engine_progress | A | phase, stop/recovery, pause boundary |
| exchange_context | B | ExchangeLog/context/artifact references |
| partial_parallel_batch | B with C outcomes | declared/completed/open slots |
| tool_effects | C | ToolResult/effect/reconciliation/quiescence facts |
| queued_steering | B | accepted/applied safe-boundary input facts |
| provider_continuation | B | opaque continuation reference/capability facts |
| work_graph | C | child/work ownership and joins |
| budget_capability | A with C allocations | budget/capability state and digests |
| trace_lineage | A facts, D reader | explicit runtime lineage and completeness refs |

Lane A owns only slot names and envelope validation. B/C own their payload
schemas and migrations; D consumes facts without becoming their writer. A
component declares `schema_version`, `required`, semantic `owner`, and a JSON
object payload. Missing required or unsupported component schemas fail typed.

The envelope never contains live agent/model/tool/environment/store objects,
locks, file descriptors, threads, futures, subprocess handles, callables,
credentials, raw host paths, or an executable Python stack.

## Resolver contract

Snapshots persist `ResolverReference`, never a live resource. Its strict shape
is:

```json
{
  "namespace": "model",
  "reference_id": "default:model",
  "expected_capability": "model.call",
  "version": 1
}
```

Namespaces are model, tool registry/toolset, environment, artifact store,
secret, checkpoint store, and optional provider continuation. The logical alias
cannot be a host path or credential. The new process supplies a
`ResolverRegistry`; each resolver returns a process-local resource with matching
namespace and capability.

- no namespace resolver -> `missing_resolver`;
- wrong result namespace/capability/type -> `resolver_type_mismatch`;
- secret alias not available -> `unavailable_secret`.

Diagnostics name only safe namespace/capability facts. They do not echo aliases,
secret values, provider payloads, credentials, or host paths. Framework-created
resources populate the beginner default resolver set; explicit injection is an
advanced capability.

## Typed failures

Every `SessionContractError` has `error_code`, concise message, `recoverable`,
remediation, and redaction-safe scalar metadata. The closed codes are:

- `missing_resolver`, `resolver_type_mismatch`, `unavailable_secret`;
- `unsupported_snapshot_schema`, `unsupported_component_schema`;
- `generation_conflict`, `superseded_owner`;
- `unsafe_pause_boundary`, `unresolved_effect`;
- `corrupt_snapshot`, `invalid_identity_relationship`;
- `persistence_rejected`, `persistence_failed`.

Unknown fields, wrong types, non-finite numbers, non-JSON/live objects, missing
components, duplicate slots/references, non-portable values, and digest mismatch
fail rather than being silently dropped.

## Compatibility convergence

Only the current snapshot writer emits new session snapshots. Historical input
may be read by isolated migration adapters, never by a second public API.

| Existing path | Disposition | Warning gate | Removal prerequisite |
|---|---|---|---|
| `Engine.init_session()` tuple | adapt to future handle | after golden path | REPL/examples and two consumers migrated |
| `RunState` JSON | historical reader, then retire independent truth | reader availability | state/task/composition migration fixtures |
| checkpoint `thread_id == run_id` | historical address mapping | internal migration warning | current writers store explicit identities |
| `CheckpointData`/`CheckpointManager` | historical reader only; do not extend | already deprecated | experiment migrated and fixtures qualified |
| `resume_from_checkpoint()`/`resume()` | adapter over session restore | restore façade | clean-process parity and deprecation window |
| qita/debug trace fork | runtime fork client | Task 12E | qita dual-read and runtime fork behavior tests |
| example helpers | replace with golden path | docs migration | canonical examples and unrelated consumer |

Each adapter records its consumer, migration, warning, removal prerequisite,
test, and owner in the Lane A plan. Names use `historical checkpoint reader`,
`migration adapter`, and `deprecated compatibility path`; no public versioned,
legacy, next, or parallel Session type is introduced.

## Rejected API alternatives

### Session ID supplied by ordinary users

Rejected because uniqueness, validation, and lineage become caller burden. A
logical label may be metadata, never identity.

### Run ID as session ID

Rejected because restore must create a new run while advancing the same session.

### Checkpoint as snapshot

Rejected because a snapshot is immutable state content while a checkpoint is a
persistence commit. Retries and storage migration must not change snapshot
meaning.

### `SessionStore` beside checkpoint store

Rejected because it creates two persistent truths and cross-store atomicity.

### Expand `RunState` into the durable model

Rejected because it currently depends on EngineResult/live reconstruction and
would compete with checkpoint-backed snapshots. It becomes an adapter or is
retired.

### Serialize the Engine, agent, registry, environment, or provider client

Rejected because live objects contain process ownership, credentials, handles,
and non-portable behavior. Persist resolver references and canonical data only.

### Pause returns a checkpoint ID immediately

Rejected because queue acceptance or a transient ID is not durable pause. A
typed receipt must distinguish accepted from persisted.

### Fork by copying trace files or parsing run-name suffixes

Rejected because trace is evidence, not execution state, and names are not
lineage.

### Exactly-once tool/external execution claim

Rejected because external systems may not support transactions or idempotency.
The portable guarantee is generation-checked head commit plus honest effect
receipts and no automatic retry of unresolved outcomes.

### Separate sync and async session architectures

Rejected because it would duplicate identity, lifecycle, persistence, and
recovery semantics. Async is an execution façade over the same session truth.

## Consequences and later work

Positive consequences:

- one vocabulary crosses Engine, checkpoint, B/C components, trace, and qita;
- beginner API remains compact while recovery facts stay inspectable;
- stale processes, unsafe pauses, corrupt snapshots, and missing resources fail
  with stable, safe diagnostics;
- B/C/D can develop independent payload/readers against one envelope.

Required later work, not claimed by 12A:

- atomic session-head persistence in both current store implementations;
- persistence idempotency and complete durability receipts;
- historical checkpoint/RunState migration codecs;
- Engine/AsyncEngine session handles and pause boundary integration;
- same-process then fresh-process restoration;
- effect/quiescence inputs from Lane C and conversation/context inputs from B;
- qita/CLI clients and compatibility rollout;
- integration-owner updates to progress, README, changelog, and release evidence.
