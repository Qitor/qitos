# Stable effects, recovery, and WorkGraph

Status: S1 Lane C producer; contracts and fixtures only
Schema versions: `qitos.tool_result/v1`, `qitos.tool_batch_closure/v1`,
`qitos.work_graph/v1`, `qitos.work_graph.snapshot_component/v1`
Cross-lane qualification: `waiting_on_lane_a`

## Decision

QitOS has one outcome and one multi-agent ownership truth:

- `qitos.core.tool_result.ToolResult` is the only result for tools, actions, and
  child work. It evolves in place. `ActionResult` is accepted only by the named
  compatibility adapter.
- `qitos.core.work_graph.WorkGraph` is the only durable ownership graph.
  It records generation-checked facts and does not schedule workers.
- Checkpoint v2 remains the only persistence mechanism. The WorkGraph snapshot
  component is data placed in Lane A's envelope, not another store.
- Lane B owns the content/context transfer schema. Lane C persists only an
  opaque `context_transfer_ref`.

This package does not implement a child scheduler, replace nested `Engine`,
cancel Python threads, perform distributed work, freeze trajectory v2, or claim
exactly-once external effects.

## Beginner delegation API

The ordinary API is explicit by operation and returns handles whose eventual
outcomes are canonical `ToolResult` objects:

```python
session = Engine(agent).session(task)

review = session.delegate(reviewer, review_task)
results = session.fan_out(worker, items)
summary = session.join(results)

session.handoff(expert)
```

The final names are reviewed with Lane A before runtime implementation. The
shape is frozen: separate methods remain separate semantics. There will be no
`execute_child(mode="handoff|delegate|spawn|fan_out|fork")` API.

Ordinary users do not create `WorkItem`, increment generations, build edges,
hold leases, classify late results, or select scheduler mechanics. They do not
switch result type when work happens to run in a child agent.

### Sync/async symmetry

Each operation has one semantic transaction and symmetric blocking surfaces:

| Sync | Async | Meaning |
|---|---|---|
| `session.delegate(...)` | `await session.adelegate(...)` | create an attached child; parent retains responsibility |
| `session.spawn(...)` | `await session.aspawn(...)` | create independently supervised child work |
| `session.fan_out(...)` | `await session.afan_out(...)` | declare one group and ordered children |
| `session.join(...)` | `await session.ajoin(...)` | wait for only the declared handles |
| `session.handoff(...)` | `await session.ahandoff(...)` | transfer the current item with CAS |
| `session.steer(...)` | `await session.asteer(...)` | queue input for a declared safe boundary |
| `session.cancel(...)` | `await session.acancel(...)` | request stop; never imply worker termination |

Async cancellation cancels the wait and submits the same cooperative request;
it does not strengthen the worker-stop guarantee.

### Default ownership and budgets

- A session starts with one authoritative owner at generation zero.
- `handoff` advances that same work item's generation by one and removes the
  prior owner's commit authority.
- `delegate` and `fan_out` create attached children. The parent keeps its own
  work and lifecycle responsibility.
- `spawn` creates a separately supervised child. `detach` is still an explicit
  later lifecycle operation; spawn is not anonymous fire-and-forget.
- Awaited-child cancellation defaults to `request_and_wait`. Callers choose
  `propagate` or explicit `detach` when needed.
- Child budget is an explicit allocation bounded by the parent's available
  reservation and the destination policy. Unused budget defaults to
  `return_unused`; capability grant is the intersection of caller grant and
  destination policy. No secret, connector, writable environment, or tool is
  inherited merely because the parent owns it.

### Public surface budget

S1 adds no root exports. The future ordinary session surface is limited to the
seven explicit operations above plus opaque typed handles. Advanced contract
records live in `qitos.core.work_graph`, not `qitos.__init__`. Scheduler,
generation mutation, lease, effect reconciliation, and slot-closure mechanics
stay internal or inspection-only.

## Advanced work-graph API

Advanced users may inspect, persist, and validate:

- `WorkItem`, `WorkOwner`, `WorkAttempt`, and owner generation;
- `WorkEdge`, `OwnershipTransfer`, `DelegationRecord`, `SpawnRecord`, and
  `FanOutGroup`;
- `JoinDependency`, `CancellationRequest`, `DetachmentRecord`,
  `WorkCompletion`, and `LateResult`;
- `BudgetAllocation`, `CapabilityAllocation`, opaque context-transfer
  references, and `WorkGraphSnapshotComponent`;
- canonical child `ToolResult` data, including effect uncertainty and
  reconciliation state.

Mutation helpers are record builders with compare-and-set checks. They do not
run a worker. Persisted fields are JSON data and references only. Thread,
future, executor, subprocess, client, credential, closure, and Python stack
objects fail the JSON boundary.

## Effect vocabulary on ToolResult

The existing v1 envelope now has the following recovery fields:

| Field | Meaning |
|---|---|
| `attempt_id` | identity of this execution attempt, distinct from call/work/run IDs |
| `effect_ref` | public/reconcilable identity for the declared external effect |
| `effect_state` | closed effect state below |
| `idempotency_ref` | backend-supported deduplication reference; not an exactly-once claim |
| `retry_disposition` | evaluated result of retry policy, not merely requested retry count |
| `reconciliation_required` | caller must reconcile before another effectful attempt |
| `worker_still_running` | prior worker is not proven stopped |
| `outcome_unknown` | no trustworthy terminal effect receipt exists |
| `late_result` / `stale_owner` | outcome arrived after closure or from non-authoritative generation |
| `owner_generation` | generation under which the result attempted to commit |
| `batch_closure` | per-slot terminal/open facts for a partial parallel batch |

Effect states are deliberately not collapsed:

1. `no_effect_declared` — read-only or no effect contract exists;
2. `not_started` — a declared effect did not begin;
3. `started` — dispatch began, but completion may still be open;
4. `committed` — a trustworthy commit receipt exists;
5. `rejected` — the target rejected the effect before commit;
6. `unknown` — observation was severed and the final effect is unknowable;
7. `reconciliation_required` — unknown effect must be inspected through an
   explicit reconciliation path before retry.

`outcome_unknown` may accompany `started`, `unknown`, or
`reconciliation_required`; it can never be silently projected to failed or
absent. `reconciliation_required` is mechanical and cannot accompany settled
effect states.

## Retry and reconciliation rules

Automatic retry is permitted only when all of these are true:

1. `recoverable` is true;
2. `retry_disposition == "retryable"`;
3. no prior worker is still running;
4. the prior outcome is not unknown and reconciliation is not required;
5. no committed effect would be repeated, unless a backend idempotency contract
   and policy explicitly authorize another request.

`not_started` and `rejected` are normally safe candidates after policy review.
Pure execution failure before dispatch can also be retryable. A timeout with a
continuing Python thread is `blocked_worker_running`, not retryable. A severed
HTTP/MCP/subprocess result is `requires_reconciliation`. A committed effect is
non-retryable as an execution attempt even when later application-level work
can refer to its receipt.

An idempotency key narrows duplicate risk; it does not prove exactly once.
Retry without a trustworthy backend key may duplicate a started effect. The
only honest response for an unreconcilable unknown effect is to report unknown
and request user/policy disposition.

## Partial batches, late results, and steering

`qitos.tool_batch_closure/v1` lists every declared action slot by `action_id`
and records `open|success|error|skipped|timed_out|cancelled`. Completed slots
remain terminal across restore and are never rerun because a sibling is open.
Every open slot carries its attempt identity when available.

WorkGraph commit applies these rules:

- owner generation must match the authoritative item generation;
- a stale-generation result is appended as `LateResult(reason="stale_owner")`
  and cannot create a completion;
- a different result after terminal completion is a rejected late result;
- an identical duplicate completion returns `duplicate_ignored` and produces
  no second completion or effect;
- a cancelled child's later result is recorded as late/cancelled and cannot
  reopen the item or its join;
- a join consumes only its explicitly declared child set and each accepted
  child at most once.

Queued steering can be accepted while a model/tool/child operation is unsafe,
but it enters the exchange only after the owning runtime has durably closed the
current model result or every relevant tool/child slot. Lane B owns the queued
input record; Lane C supplies the safe/unsafe boundary facts.

## Operation semantics

| Operation | Stable meaning |
|---|---|
| `handoff` | CAS transfer of the same `work_item_id`; old owner loses commit authority after the transfer record commits |
| `delegate` | parent retains responsibility and creates an attached child that it awaits or explicitly joins |
| `spawn` | create separately supervised child work; it is not an implicit detach |
| `fan_out` | create ordered children sharing one `group_id`; declaration and completion order remain distinct |
| `join` | explicitly wait for a named set and policy; undeclared work is rejected |
| `fork` | Lane A operation creating a new session/work lineage from an immutable snapshot; never an edge inferred from names |
| `steer` | queue input to a still-controlled work item for its next safe boundary; no ownership change |
| `cancel` | request stop with propagation policy; accepted request does not prove worker stopped |
| `detach` | remove parent lifecycle constraint and name a new supervisor/retention reference |

## Ownership generation rules

- exactly one `WorkOwner(agent_id, generation)` is authoritative per item;
- generation is a non-negative monotonic integer, never a timestamp;
- handoff/restore use expected-generation compare-and-set and advance by one;
- stale owners cannot start an authoritative attempt or commit completion;
- last-writer-wins is forbidden;
- restore advances generation before any reconstructed worker may commit;
- detached work keeps an explicit owner and supervisor; it is not ownerless;
- completion is immutable, and late/duplicate receipts cannot overwrite it.

## Snapshot component

`qitos.work_graph.snapshot_component/v1` contains a `graph_ref` and the sorted
set of unresolved work identities. Lane A's immutable snapshot envelope owns
session/head/checkpoint generation and resolver identities. It stores this
component by reference/version and resolves the full graph through checkpoint
v2. Missing graph references, unknown component versions, stale owner
generation, and unresolved non-quiescent children are typed restore blockers.

The provisional component is C-owned and does not qualify G2 until it is read
inside the reviewed Lane A envelope. Current disposition:
`waiting_on_lane_a`.

## Compatibility retirement

| Current surface | S1 disposition | Final path |
|---|---|---|
| `ActionResult` | compatibility input only | executor adapts immediately to `ToolResult`; remove after all executor consumers migrate |
| flattened `Observation` mapping | explicit legacy projection | reducers consume nested `ToolResult`; remove flattening after consumer inventory |
| `_HandoffRuntime` live agent/history mutation | behavior unchanged | 13B adapter submits one transfer record before target runs |
| `DelegateTool` nested `Engine` | behavior unchanged | 13C adapter creates durable child then returns its `ToolResult` |
| `FanOutTool` thread pool and aggregate dict | behavior unchanged | 13D adapter declares group/children/join and retains per-child `ToolResult` |
| `AgentTool.AgentResult` | compatibility-only duplicate outcome | map to canonical `ToolResult`; do not teach or extend `AgentResult` |
| run-id suffix lineage | trace compatibility only | explicit graph/session references; never parse names for ownership |
| timeout metadata booleans | accepted legacy input | canonical fields become the read/write truth |
| lifecycle helper methods | owner-specific | no universal public lifecycle interface |

No compatibility method above appears in the beginner API.

## Rejected alternatives

- `ToolResultV2`, `AgentResult`, or a separate child outcome: rejected because
  outcome semantics would diverge.
- `WorkGraphV2`, `MultiAgentRuntimeV2`, or another scheduler: rejected because
  ownership/runtime truth would split.
- one universal operation with a `mode` string: rejected because it obscures
  ownership, cancellation, budget, and join differences.
- timestamps or last-writer-wins ownership: rejected because stale processes
  could overwrite authoritative work.
- serializing live worker handles: rejected because snapshots would be local,
  secret-bearing, and non-restorable.

## Fixtures and qualification

- `tests/fixtures/tool_results/recovery_outcomes.json` covers successful,
  semantic/execution failure, stopped/continuing timeout, committed/unknown
  effects, retryable/non-retryable outcomes, reconciliation, partial batches,
  and stale/late results.
- `tests/fixtures/work_graph/contracts.json` is the stable scenario manifest for
  handoff, delegate, spawn, fan-out/partial join, cancellation uncertainty,
  detach, transfer, stale/late results, budget/capability failure, and restore
  with unresolved child work.
- `tests/core/test_tool_result_recovery_contract.py` and
  `tests/core/test_work_graph.py` enforce strict reads/writes, unknown fields and
  versions, JSON-only persistence, ownership isolation, stale generation,
  duplicate completion, redaction, snapshot shape, and operation distinctions.

Exact producer commit/digests and A/B/D consumer instructions are published in
Lane C evidence after the producer commit exists.
