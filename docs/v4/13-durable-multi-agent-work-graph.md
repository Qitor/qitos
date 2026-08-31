# Task 13 — durable multi-agent work graph and ownership transfer

Status: S3 durable runtime deterministic candidate qualified; live promotion blocked
Depends on: Task 12A–12D; consumes Tasks 02, 03, and 04 contracts
Feeds: Task 05 lineage/observability, Task 10 convergence, and native multi-agent
research methods
Risk: critical — ownership, recovery, cancellation, effects, and graph lineage

---

## 1. Goal

Turn QitOS's existing handoff, delegate, and fan-out helpers into one durable,
domain-neutral work graph that survives process restart and is understandable to
researchers through public APIs and qita.

The target is not an autonomous-agent product, a role marketplace, or a built-in
distributed cluster. It is a small execution contract for assigning, transferring,
branching, joining, pausing, and recovering agent work on the existing
`AgentModule + Engine` kernel.

## 2. Current baseline and the gap

QitOS already provides:

- `AgentSpec`, `AgentRegistry`, `ContextStrategy`, and `HandoffContext`;
- Engine handoff logic and handoff hooks/traces;
- `HandoffTool`, `DelegateTool`, and `FanOutTool`;
- nested Engine execution for delegation and a thread-pool fan-out path.

These are valuable in-process mechanisms, but not a durable multi-agent runtime:

- handoff swaps the live agent and mutates live history/state instead of
  committing an ownership-transfer record;
- delegation returns a child result as an ordinary tool result without a durable
  child session/work identity;
- fan-out futures are not durable and `future.cancel()` cannot stop an already
  running worker;
- parent/child budgets, cancellation, artifacts, effect receipts, checkpoints,
  and trace lineage are incomplete or implicit;
- process exit cannot reconstruct pending children or join decisions.

Task 13 evolves these mechanisms in place. It does not create a second agent
loop or encode manager/reviewer/coder strategies into the framework.

Historical dispatch note: S2 tool/effect/work-graph work branched from
`446a347d1ac73636476ca2515a01da601b567c68`; that instruction is superseded for
S3. S2 was subsequently converged, promoted, revalidated, pushed, and cleaned
up at fixed pre-S3-closure source
`3af0ee3b2c3b5b5575e4e07cc31ff7f652327ba7`. The executable
[`S3 durable multi-agent wave`](../internal/plans/s3_durable_multi_agent_wave.md)
assigned fork/ownership to A, context/authority transfer to B, durable
scheduling to C, and work-graph observability/DX to D. The convergence receipt
below records the resulting deterministic candidate.

## 3. Exact operation semantics

The public vocabulary must preserve these distinctions:

| Operation | Ownership semantics | Durable result |
|---|---|---|
| `handoff` | Transfer the same `work_item_id` from agent A to B; after commit A is no longer owner | Ownership-transfer receipt and new run |
| `delegate` | Parent retains its work item and creates a child work item, then awaits or later joins its typed result | Parent-child edge and child outcome |
| `fan_out` | Parent creates N durable children and a declared join policy | Child set, per-child states, join receipt |
| `spawn` | Parent creates a detached child and does not synchronously join it | Durable child reference and supervision policy |
| `fork` | Create a new session/work lineage from an immutable checkpoint | New session head linked to source checkpoint |
| `steer` | Queue human input for a safe boundary of an existing work item | Input receipt; no ownership change |

A method may compose these primitives, but it may not silently reinterpret one
operation as another. In particular, a delegate is not a handoff, and a detached
spawn is not a thread-pool fire-and-forget call.

## 4. Canonical work graph

The graph is a durable control-plane view over Task 12 sessions/snapshots. It
does not duplicate conversation, state, tool outcomes, or artifacts.

Minimum records:

- `WorkItem`: identity, session, current owner agent, parent edge, lifecycle,
  task/input reference, head checkpoint, budget allocation, and policy digest;
- `WorkEdge`: operation kind, parent/source, child/target, declaration order,
  creation checkpoint, and provenance;
- `OwnershipTransfer`: expected owner/generation, from/to agent, context-transfer
  receipt, commit checkpoint, and reason;
- `ChildRef`: child identity, session/run head, status, cancellation relationship,
  and result reference;
- `JoinState`: policy, expected child set/order, terminal children, outstanding
  children, accepted results, deadline, and final join receipt;
- `WorkOutcome`: canonical Task 03 result or a typed terminal work failure, with
  artifact references rather than copied payloads.

Every mutation uses Task 12 generation checks. Exactly one active owner may
advance a work-item head. Graph records are versioned and reference immutable
session checkpoints; they are not a process-global registry of live objects.

## 5. Context, conversation, and state transfer

Transfer is explicit and receipt-producing:

- `ContextStrategy` becomes a policy for selecting references/exchanges, not a
  license to destructively rewrite the source history;
- full, recent-window, summary, custom, or no-context strategies report what was
  selected, transformed, omitted, and why;
- opaque provider continuation is transferred only when the destination codec
  and policy can preserve it; otherwise the operation is rejected or records an
  approved loss;
- `StateSchema` transfer is by typed projection/migration, never blind mutation
  across unrelated state types;
- Task 04 artifacts and memory remain referenced by identity with access and
  sensitivity checks;
- credentials, host paths, and private runtime handles never enter handoff
  payloads.

A handoff commits the transfer receipt before the new owner runs. Delegate and
fan-out children receive immutable input snapshots; later parent mutations do
not retroactively change child input.

## 6. Child lifecycle, join, and recovery

Child work uses the Task 12 lifecycle plus parent-aware states. A parent can
observe `created`, `running`, `paused`, `waiting_input`, and terminal states
without reaching into a live child Engine.

Required join policies include a small, typed base set:

- `all`: wait for all declared children;
- `all_successful`: require all children to succeed;
- `first_success`: accept the first success, then apply an explicit policy to
  remaining children;
- `quorum(n)`: accept a declared number of successful outcomes;
- caller-supplied deterministic reducer as an injected policy, not a registry
  name or arbitrary serialized closure.

Join state is checkpointed after every terminal child receipt. On restore, the
parent attaches to existing child identities and must not recreate completed
children. Declaration order, completion order, and reduction order are all
recorded separately.

If the process dies after child completion but before parent observation, the
child's durable outcome is consumed once through a join-generation check. If a
child outcome is unknown, the parent receives a typed unresolved state rather
than a fabricated failure or automatic duplicate spawn.

## 7. Cancellation, timeout, and budgets

Cancellation is cooperative and scoped:

- parent cancellation policy declares `propagate`, `detach`, or
  `request_and_wait`; the default for awaited children is reviewed in 13A;
- cancelling a future does not prove a running thread stopped;
- late child results cannot commit into a closed/superseded join generation;
- a detached child has an explicit supervisor/retention policy;
- timeouts record `worker_still_running` and outcome uncertainty where relevant;
- hard cancellation is an opt-in process-isolated capability from Task 09C, not
  a promise of the default thread runtime.

Budgets are allocated, not copied invisibly. The graph records parent reservation,
child allocation, actual use, return/reclaim policy, and global ceilings. A child
cannot obtain model/tool capabilities or budget beyond the parent's explicit
grant and the destination agent's policy.

## 8. Security and authority

Multi-agent composition must not become an authority escalation path.

- each agent has a resolvable capability profile;
- handoff/delegate/spawn validates the intersection of caller grant, destination
  policy, tool permissions, environment capabilities, and artifact access;
- a child cannot inherit secrets, writable environments, or external connectors
  merely because the parent has them;
- injected agents/resolvers remain caller-owned; framework defaults are minimal;
- ownership transfer and permission decisions emit redacted audit receipts;
- remote or untrusted workers require authenticated transport supplied by an
  integration layer; Task 13 does not invent one.

## 9. Execution interface and adapters

The exact public names are a 13A decision, but the coherent user experience
should support this shape:

```python
child = session.delegate("researcher", task="inspect the parser")
review = session.spawn("reviewer", task="watch the evidence")
session.handoff("operator")

children = session.fan_out(specs, join="all_successful")
outcomes = session.join(children)
```

Existing `HandoffTool`, `DelegateTool`, and `FanOutTool` remain model-callable
adapters. They submit operations to the work graph and return canonical Task 03
outcomes; they do not own a separate nested-runtime protocol. Direct Python API
and tool-triggered operations therefore share the same semantics and receipts.

The base implementation may use a local executor, but scheduling is behind an
injected interface. No distributed coordinator or server is required by the base
install.

## 10. Trace and qita requirements

Task 05 must represent, without inference:

- session/run/work-item/agent identities and parent lineage;
- work creation, ownership transfer, pause/resume, cancellation, and restore;
- per-child declaration and completion order;
- context-transfer and capability receipts;
- join policy, outstanding children, accepted results, and discarded late
  results;
- effect/durability uncertainty and trace completeness.

qita should render a work graph and event timeline, then allow navigation to a
child session or source checkpoint. It must not reconstruct ownership from run-ID
string conventions such as delegate-name suffixes.

## 11. Work packages

### 13A — semantics, graph contracts, and fixtures

- Write the internal implementation plan and ADR.
- Census all existing handoff/delegate/fan-out paths, nested Engine construction,
  trace conventions, and public examples.
- Freeze operation distinctions, graph records, lifecycle/cancellation policies,
  permission boundaries, and typed failures.
- Publish versioned fixtures covering ownership transfer, partial fan-out,
  process death, and outcome uncertainty.

### 13B — durable handoff

- Route direct and tool-triggered handoff through one ownership-transfer path.
- Commit context/state transfer receipts and generation-checked ownership before
  the target agent runs.
- Restore a handed-off work item in a fresh process without the source agent
  object.
- Preserve compatibility hooks/traces through adapters.

### 13C — durable delegate and spawn

- Replace nested-Engine-only identity with durable child work/session refs.
- Implement awaited delegate and detached spawn supervision semantics.
- Add child capability/budget allocation and parent cancellation policies.
- Return canonical outcomes and artifact refs without copying child trajectory
  payloads into parent history.

### 13D — durable fan-out and join

- Persist child declarations before scheduling and terminal outcomes as they
  complete.
- Implement the reviewed base join policies and deterministic reduction.
- Resume a partially completed fan-out without duplicating terminal children.
- Prevent cancelled/late children from mutating a closed join.

### 13E — observability, recovery, and compatibility rollout

- Add Task 05 graph/timeline records and qita navigation after schema handoff.
- Run parent/child process-loss and store-failure qualification.
- Migrate `HandoffTool`, `DelegateTool`, `FanOutTool`, examples, and trace naming
  to adapters over the graph.
- Demonstrate two independent multi-agent research methods without embedding
  their role strategy in QitOS.

## 12. Acceptance criteria

- [x] Handoff, delegate, fan-out, spawn, fork, and steer have distinct tested
  ownership semantics.
- [x] Exactly one owner/generation may advance a work item.
- [x] Handoff survives process death before and after ownership commit without
  two active owners.
- [x] Delegated/spawned children have durable identities, checkpoints, outcomes,
  budgets, capability grants, and trace lineage.
- [x] Partial fan-out restores without recreating completed children; join
  consumes each child outcome once.
- [x] Parent cancellation, detachment, timeout, and late-result behavior are
  explicit and observable.
- [x] Context/state transfer reports selections and losses and never leaks
  secrets or host-only handles.
- [x] Direct API and model-callable tool adapters use the same graph protocol.
- [x] qita can navigate parent/child/handoff lineage without parsing run-ID
  naming conventions.
- [x] A local executor proves the protocol; no distributed service is required
  by the base package.
- [x] Two unrelated multi-agent patterns consume the primitives without adding
  strategy vocabulary to core/engine.

## 13. Verification

```bash
pytest -q tests/test_handoff.py tests/engine/test_handoff_context.py
pytest -q tests/test_delegate_tool.py tests/test_fanout_tool.py
pytest -q tests/engine/test_work_graph.py
pytest -q tests/e2e/test_multi_agent_process_restore.py
pytest -q tests/checkpoint tests/tracing tests/qita
pytest -q tests/test_architecture_boundaries.py tests/test_public_surface.py
python scripts/static_quality.py check
pytest -q
git diff --check
```

The work-graph and process-restore test paths are Task 13 deliverables. All
concurrency tests use deterministic barriers and bounded deadlines, not sleeps or
live models.

## 14. Stop-and-escalate decisions

Stop for review before:

- implementing handoff by mutating shared live history/state without a transfer
  receipt;
- treating delegation, handoff, spawn, and fork as aliases;
- creating a second execution loop, conversation log, checkpoint store, result
  envelope, or trace truth;
- claiming `Future.cancel()` stopped a running worker;
- retrying or respawning an outcome-unknown child automatically;
- escalating child tools, secrets, environment, budget, or artifact access;
- serializing Python callables or agent instances into the work graph;
- making Redis, a queue server, Kubernetes, or any product/role strategy a base
  dependency;
- freezing Task 05 v2 before work-item and ownership lineage are represented.

## 15. S3 deterministic convergence receipt

The integrated runtime persists reconstructable JSON-only work descriptors and
real fork/context-transfer receipts before dispatch, supports bounded admission
and queued recovery, marks missing running workers `outcome_unknown` without
automatic replay, and gives handoff/delegate/spawn/fan-out/join distinct graph
facts. Generation fences, cancellation propagation, request-and-wait,
detachment, least-privilege budget/capability allocation, direct/tool parity,
deterministic join closure, and read-only qita lineage are executable facts.

The authoritative G4 scenario passed twenty independent SQLite graph rounds
plus twenty declaration/preparation-crash rounds with abrupt original-process
termination and fresh restore. Both
unrelated consumer patterns and the compact coding-agent example pass. The
candidate intentionally makes no distributed scheduler, hard-cancellation, or
external-effect exactly-once claim.

Live-model qualification is `blocked_configuration`, so this receipt does not
promote or push a baseline and does not authorize source-worktree cleanup or a
default-branch readiness claim. Candidate Trajectory remains unfrozen/off and
qita remains on frozen trace-v1. Exact evidence is in
[`s3_g4_convergence_evidence.md`](../internal/plans/s3_g4_convergence_evidence.md).
