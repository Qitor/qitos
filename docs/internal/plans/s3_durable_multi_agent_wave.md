# S3 durable multi-agent wave

Status: closed and promoted; superseded for dispatch by Task 15
Updated: 2026-09-02
Owner: historical G4 integration owner
Source baseline before this documentation closure:
`3af0ee3b2c3b5b5575e4e07cc31ff7f652327ba7`

## 1. Outcome and dispatch rule

S3 has one goal: implement durable, recoverable, and observable multi-agent
execution over the existing `AgentModule + Engine + Session + CheckpointStore +
WorkGraph` architecture.

This document freezes ownership, producer/consumer handoffs, merge order,
interface budgets, and the G4 acceptance gate. The later convergence described
in section 15 implements and qualifies the deterministic candidate. The
only valid four-lane dispatch source is the complete remote SHA produced after
this documentation closure is fast-forwarded, revalidated, pushed, and verified.
The promotion receipt publishes that SHA; this file deliberately does not try
to record the SHA of its own eventual descendant commit.

All four lanes must receive the same 40-character dispatch SHA. Each lane uses
an independent branch and worktree. A branch created from an older G2, S1, S2
lane, G3 integration source, or local-only documentation commit is invalid.

## 2. Framework goal and non-goals

S3 supplies framework mechanisms for assigning, transferring, branching,
joining, supervising, cancelling, persisting, restoring, and inspecting agent
work. It does not encode manager, reviewer, coder, researcher, or other product
roles, and it does not include task- or domain-specific coordination strategy.

The work must extend the one current Engine loop and reuse the canonical
Session, checkpoint store, ToolResult, ArtifactRef, provider transaction path,
and candidate trajectory truth. It must not create a second Engine,
SessionStore, tool-result envelope, artifact contract, provider path, or
trajectory plane. Redis, Kubernetes, Celery, remote queues, and hosted
coordinators are not base dependencies; caller-owned implementations may later
bind to reviewed extension protocols.

S3 targets:

- Session fork and explicit parent/child lineage;
- handoff, delegate, spawn, fan-out, and join as distinct operations;
- generation-checked ownership transfer and child supervision;
- cancellation, request-and-wait, and detachment semantics;
- persisted declarations and terminal receipts;
- partial work-graph recovery and cross-process resume;
- deterministic joins and work-graph observability.

S3 does not claim:

- distributed cluster scheduling or a production control plane;
- exactly-once external side effects;
- hard cancellation of Python threads or arbitrary remote workers;
- a complete agent-authoring facade;
- a frozen Trajectory schema or a default candidate writer/store/reader;
- mutation or scheduler authority for qita.

## 3. Fixed current facts

The S2 durable single-agent vertical and clean-process restore are qualified.
The current runtime has an atomic Session head, immutable snapshots,
owner/generation compare-and-set, cooperative pause, resolver-only restore,
partial tool-batch recovery, and explicit runtime event facts.

The current `WorkGraph` is a strict, durable contract and record model. It is
not an execution scheduler. The current delegate path starts a nested Engine,
the fan-out path uses an in-process `ThreadPoolExecutor`, and handoff swaps live
agent/history/state. None survives process loss as a durable multi-agent
runtime. The Session contract permits `FORK` in selected lifecycles and has a
fork fixture, but the Session facade does not implement `fork()`.

The candidate Trajectory schema remains unfrozen. Its writer is not enabled by
default, and qita continues to use trace-v1 compatibility rather than the
candidate reader as its default.

## 4. Four-lane ownership matrix

| Lane | Mission | Primary ownership | Required producer | Forbidden expansion |
|---|---|---|---|---|
| A — Session Fork and Ownership | Fork immutable Session state and fence owners across fresh processes | `qitos/core/session.py`, `qitos/engine/session_runtime.py`, `qitos/checkpoint/`, Session fixtures/tests | fork/session/ownership bundle consumed by C | scheduler, provider codec, trajectory writer, second store |
| B — Context, Continuation and Authority Transfer | Select and transfer safe child input and least-privilege authority | `qitos/core/request_view.py`, `qitos/models/codec.py`, ExchangeLog/context/compaction/continuation/artifact contracts and fixtures/tests | transfer/authority bundle consumed by C | scheduler, second ArtifactRef, secret/live-object persistence, product roles |
| C — Durable Multi-Agent Scheduler | Execute the canonical WorkGraph through the existing Engine/Session runtime | `qitos/core/work_graph.py`, one Engine work-runtime seam, thin `qitos/kit/tool/agent/` adapters, runtime/recovery/cancellation/join tests | runtime facts consumed by D; real A/B contracts are inputs | second loop, closure serialization, thread-pool-as-durable claims, guessed unknown outcomes |
| D — Work-Graph Observability and DX | Qualify and inspect exact A/B/C facts and demonstrate two unrelated consumers | `qitos/tracing/`, `qitos/qita/`, `qitos/evaluate/`, qualification artifacts, framework-level examples/recipes | exact-source G4 evidence and read-only graph/timeline UX | qita mutation authority, inferred lineage, premature schema/default switch, domain strategy in core |

Shared `README`, `CHANGELOG`, progress, architecture, public-surface, and final
convergence documents remain leased to the G4 integration owner. High-conflict
Engine and aggregate `__init__` files require an explicit integration-owner
lease even when a lane owns the underlying semantics.

## 5. Lane A — Session Fork and Ownership

### Deliverables

- `session.fork(snapshot=...)` over an immutable source snapshot;
- distinct child `SessionIdentity`, `RunIdentity`, `WorkItemIdentity`, and
  `AttemptIdentity` values with explicit parent/source relationships;
- child Session head creation and generation CAS without copying mutable
  checkpoint payloads;
- owner-generation supersession and stale-owner rejection;
- fresh-process restoration of the forked child;
- typed invalid-lifecycle, missing-snapshot, integrity, resolver, generation,
  and ownership failures.

Relationships are recorded as typed facts. Implementations must not parse ID
suffixes or names to infer lineage. Lane A must not implement a child scheduler,
modify provider codecs or trajectory writers, or introduce another Session
store.

### Producer freeze

Before Lane C may claim consumption, A publishes one committed manifest naming:

- the exact producer commit;
- every committed fixture and evidence path;
- SHA-256 for every producer file;
- the contract/schema identifiers and supported/unsupported cases;
- producer test node IDs;
- a consumer contract that identifies the public/module-level types and strict
  reader entrypoints C must use.

The bundle must prove immutable-source fork, distinct identities, new child
head, parent/source lineage, owner fencing, and clean-process restore. A copied
fixture or a C-owned stand-in does not satisfy this freeze.

## 6. Lane B — Context, Continuation and Authority Transfer

### Deliverables

- module-level `ContextTransferPlan` and `ContextTransferReceipt` candidates,
  subject to public API review;
- typed state/context projection and immutable child input;
- provider-continuation compatibility and typed reconstruction failure;
- explicit capability and budget allocation;
- canonical ArtifactRef transfer;
- selected, transformed, omitted, and loss facts;
- least-privilege authority transfer with safe diagnostics.

The transfer format must not persist secret values, credentials, host paths,
live models/clients, SDK objects, workers, or other process-local objects. A hash
does not sanitize secret material. Lane B must not implement scheduling, create
a second ArtifactRef, or embed product role strategy.

### Producer freeze

Before Lane C may claim consumption, B publishes one committed manifest with
the same exact commit/path/SHA-256/schema/test/consumer fields required of A.
The bundle must cover capability, budget, artifact reference, continuation
compatibility, projection, omission/loss accounting, immutable input,
least-privilege reconstruction, and typed failure. C must import the real B
types and read the committed bytes through B's strict reader.

## 7. Lane C — Durable Multi-Agent Scheduler

### Deliverables

Lane C extends the canonical `WorkGraph`; direct Python calls and model-callable
tools use the same runtime protocol and produce the same facts. It must keep
`handoff`, `delegate`, `spawn`, `fan_out`, and `join` semantically distinct.

Required behavior:

- persist every child/transfer/join declaration before dispatch;
- persist each terminal receipt after completion and before join publication;
- restore a partial graph in a fresh process;
- never recreate a completed child;
- never automatically replay `outcome_unknown` work;
- reject duplicate, stale, late, cancelled, and superseded terminal writes;
- fence every owner mutation by generation;
- implement explicit cancellation propagation, request-and-wait, detachment,
  and supervision policies;
- enforce allocated budget and capability authority;
- make join completion deterministic and consume each accepted outcome once.

Minimum join policies are `all`, `all_successful`, `first_success`, `quorum(n)`,
and an explicitly injected deterministic reducer. The reducer must be referenced
through a reconstructable protocol; closures, lambdas, threads, futures, live
workers, and other process-local objects are never serialized.

Lane C must consume the reviewed A and B producer commits, types, fixtures, and
strict readers directly. It may not copy their enums/schemas/fixtures or build a
consumer-like simulation. The existing `ThreadPoolExecutor` fan-out is an
in-process compatibility mechanism, not the durable scheduler. Unknown effects
after process loss remain unknown; they are not guessed successful or failed.

## 8. Lane D — Work-Graph Observability and DX

### Deliverables

Lane D consumes exact runtime facts for work items, attempts, owners, ownership
transfers, fan-out declarations, join decisions, pause/restore, cancellation,
and late/stale/superseded rejection. It provides read-only qita session graph,
timeline, inspection, parent/child navigation, join inspection, ownership
inspection, and safe diagnostic projection without decoding IDs or path names.

D publishes exact-source qualification bound to the reviewed A/B/C producer
commits and byte digests. Runtime readiness requires executable consumer tests;
complete receipts alone are insufficient.

G4 must include:

- two unrelated multi-agent consumer patterns using the same primitives; and
- one roughly 50–100 line public-API coding-agent acceptance example.

The coding-agent example is a framework DX test, not permission to move software
development roles or policy into core/engine. qita remains a read-only consumer.
Lane D must not freeze Trajectory v2, change writer/store/reader defaults, or
infer lineage from run names, directories, or identity strings.

## 9. Producer, consumer, and merge order

Initial census, implementation, negative tests, and local fixtures may proceed
concurrently after all four independent branches/worktrees are created from the
same verified remote dispatch SHA. Contract freeze and convergence are ordered:

```text
Lane A producer freeze
    -> Lane B producer freeze
    -> Lane C real A/B consumption and runtime facts
    -> Lane D real A/B/C qualification and DX
    -> G4 convergence
```

A and B own their contracts even when their early implementation overlaps in
time. C cannot claim completion until it consumes both exact producers. D cannot
claim completion until it consumes executable C facts plus exact A/B lineage.

At every integration step the integration owner:

1. records source commit, replay commit, paths, and digests;
2. replays the package onto the latest integration candidate in the fixed
   A -> B -> C -> D order;
3. runs the focused producer/consumer tests and repository no-regression
   ratchet;
4. rejects copied enums, copied fixtures, inferred lineage, simulated consumers,
   or changed ownership hidden inside a consumer patch;
5. updates the convergence ledger before accepting the next producer.

Only a closed G4 may create the next formal baseline.

## 10. Public API direction and interface budget

The intended beginner direction is deliberately small; names remain subject to
G4 public API review:

```python
session = Engine(agent).session(task)

child = session.delegate(agent, task=...)
worker = session.spawn(agent, task=...)
children = session.fan_out(specs, join="all_successful")
outcomes = session.join(children)
transfer = session.handoff(agent)
branch = session.fork(snapshot=...)
```

Model-callable tools are thin adapters over the same runtime protocol. Advanced
records remain module-level imports unless G4 approves broader exposure.

The measured dispatch budget is:

| Surface | Frozen count |
|---|---:|
| root `qitos.__all__` | 41 |
| `qitos.engine.__all__` | 27 |
| `qitos.checkpoint.__all__` | 24 |
| `qitos.models.__all__` | 28 |
| `qitos.tracing.__all__` | 22 |
| reviewed aggregate exports | 101 |
| `Engine.__init__` parameters including `self` | 34 |

Root exports do not grow without item-by-item G4 public-surface approval.
`Engine.__init__` gains no parameters. S3 adds no public type suffixed `V1`,
`V2`, `Legacy`, `Next`, or equivalent parallel-track spelling, and no second
Agent, Session, or Runtime. Authoring uses thin Session methods and replaceable
protocols rather than widening the Engine constructor.

## 11. G4 convergence owner and acceptance gate

One independent G4 integration owner controls shared-file leases, consumes the
four packages in order, reruns evidence, and rejects unsupported readiness
claims. G4 requires a real bounded subprocess/process-loss test that proves all
of the following:

1. create a parent Session;
2. fork or delegate multiple children;
3. reach one completed child;
4. reach one paused or running child;
5. reach one `outcome_unknown` child or lose it at a commit boundary;
6. terminate the original process;
7. restore in a clean process;
8. do not re-execute the completed child;
9. resume the eligible child;
10. do not automatically replay the unknown effect;
11. consume every join outcome exactly once;
12. prevent stale, late, or superseded children from changing a closed join;
13. keep at most one authoritative handoff owner at every point;
14. exercise explicit cancellation propagation, detachment, and
    request-and-wait semantics;
15. enforce least privilege for capabilities, budgets, artifacts, and secrets;
16. produce the same WorkGraph facts through direct API and model-callable tools;
17. display complete lineage in qita without parsing IDs;
18. pass two unrelated multi-agent consumer patterns; and
19. pass the full suite, static ratchet, stable lint/type, architecture, and
    public-surface gates.

Before all nineteen items pass, no document, release note, example, receipt, or
CLI output may claim `S3 complete`, `durable multi-agent ready`, `Trajectory
schema frozen`, `production distributed scheduler`, or `release ready`.

## 12. Validation contract

Every producer package runs its focused tests plus:

- architecture boundaries and module cycles;
- exact public-surface budget;
- documentation local-path and EN/zh parity gates where documentation changes;
- repository static-quality ratchet;
- stable-surface flake8 and mypy;
- complete `pytest -q`;
- `git diff --check` and modification-scope review.

G4 additionally runs the real process-loss scenario, A/B/C exact-source
qualification, D qualification, both unrelated consumer patterns, and the
public coding-agent example. No masked exit, rerun-only pass, sleep-based order,
live model key, unavailable-test skip, or receipt-only simulation qualifies a
gate.

## 13. S4 deferred boundary

S4, not S3, owns:

- the stable Agent authoring facade;
- Engine constructor contraction;
- Task 14's canonical sandbox contract, hardened task-exclusive local backend,
  stronger/remote adapter conformance, and Session/WorkGraph sandbox binding;
- fail-closed research/coding defaults, pre-model attestation, redacted sandbox
  receipts, and removal of silent host-execution fallback;
- final Trajectory schema freeze;
- canonical writer/store rollout;
- qita default-reader migration;
- Task 10 public-surface retirement;
- packaging, extras, and release hardening;
- beginner tutorials and the formal coding-agent reference.

S3 first proves the runtime mechanisms. S4 then concentrates on making the
proven mechanisms smaller, easier, stable, and safe by default for general agent
authors. Existing `DockerEnv` is an execution mechanism, not an untrusted-code
sandbox qualification.

## 14. Known gaps at dispatch (historical)

- `SessionOperation.FORK` and semantic fixtures exist, but no Session fork
  runtime/facade exists.
- `WorkGraph` persists strict records but has no durable scheduler or Engine
  execution seam.
- current handoff mutates live state/history; current delegate/fan-out paths are
  nested-Engine/in-process mechanisms and do not restore child work after
  process loss.
- durable join execution, reducer reconstruction, child supervision, and
  cancellation propagation are not implemented.
- direct API/tool parity for durable multi-agent facts is unproved.
- qita has no default candidate work-graph reader; Trajectory v2 remains
  unfrozen and its candidate writer/store/reader remain non-default.
- external-effect exactly-once and hard worker termination remain deliberately
  unsupported without backend-specific proof.

## 15. G4 convergence disposition

The fixed-source convergence replay completed A -> B -> C -> D and qualified
all nineteen deterministic items. The authoritative G4 scenario uses twenty
independent SQLite graph databases plus twenty preparation-crash databases,
event barriers, bounded subprocesses, and abrupt original-process termination.
It proves declarations precede child preparation, committed forks are reused,
completed work is not recreated,
eligible queued work resumes with the original operation identity, missing
running work becomes `outcome_unknown` without replay, join decisions are
single-consumption and closed against duplicate/late results, and handoff,
cancellation, detachment, budgets, capabilities, privacy, direct/tool parity,
consumer, example, and qita facts remain coherent.

The frozen public-surface counts remain 41/27/24/28/22/101/34. Candidate
Trajectory remains unfrozen and off; qita's default remains the historical
trace compatibility reader. R5 subsequently separated required deterministic
framework conformance from informational live Agent/model capability, closed
the remaining isolation/budget/projection/provider-stage defects, and promoted
the integrated result. The final pushed S4 baseline is
`f07b38647cf3b18a5235581224a1153b88fac397`; all five clean S3 worktrees were
removed without force while their branch refs were retained. This does not make
the default branch or a release ready. Exact convergence history remains in
[`s3_g4_convergence_evidence.md`](s3_g4_convergence_evidence.md), and final R5
qualification is recorded in
[`s3_g4_l3_qualification_evidence.md`](s3_g4_l3_qualification_evidence.md).
