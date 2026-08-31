# S2 Lane C tool runtime implementation plan

Status: qualified
Updated: 2026-08-31
Owner: S2 Lane C — Tool Runtime, Parallel Execution and Lifecycle Extension
Baseline: `446a347d1ac73636476ca2515a01da601b567c68`
Branch: `codex/v4-s2-c-tool-runtime`
Worktree: `/Users/morinop/Desktop/WhitzardOS-s2-c`
Read-only wave ledger: `47cd4dc5e1ed1b2b0d244bfc90fac031ec55be32`

## Outcome

Evolve the existing `ActionExecutor` into the one canonical tool-runtime seam.
The runtime must publish each terminal slot in actual completion order, retain a
declaration-order view, persist partial batches through acknowledged writes,
and state lifecycle/effect/cancellation truth without claiming universal hard
cancellation or exactly-once external effects.

Ordinary tool authors continue to implement only:

```python
class SearchTool(BaseTool):
    def execute(self, args, runtime_context):
        ...
```

or:

```python
@tool()
def search(query: str) -> str:
    ...
```

`run()` remains a compatibility route into `execute()`.

## Scope and invariants

- Reuse `ActionExecutor`; do not add a second executor or Engine loop.
- Keep `ToolResult` as the only canonical outcome. `ActionResult` remains a
  bounded compatibility projection for existing callers.
- Provide a stable batch/attempt identity, owner generation, lifecycle receipt,
  terminal callback, partial snapshot, effect facts, artifact facts, and
  capability-driven cancellation/quiescence boundary.
- Preserve the validation -> interceptor -> validation/permission -> rewritten
  argument validation -> execute order. Permission blocks are canonical
  `ToolResult` values and product approval UI remains outside the executor.
- Never automatically retry a committed or outcome-unknown effect. Late and
  stale-owner results are observable but cannot replace an authoritative slot.
- Do not persist live threads, futures, clients, transports, callbacks,
  credentials, closures, or stacks.
- Do not modify the leased `engine.py`, `_protocol.py`, `_model_runtime.py`,
  checkpoint store backends, `core/session.py`, `core/conversation.py`, provider
  adapters, trace/tracing/qita, or shared release documents.
- Persistent child scheduling, supervisor/worker strategy, spawn policy, and
  join policy remain S3 work.

## Contract decisions

1. `qitos.core.tool_runtime` owns implementation-neutral lifecycle, effect,
   slot, batch, receipt, callback, and policy protocols. It is an advanced
   module surface, not a new root export.
2. `ActionExecutor.execute_one()` and `execute_batch()` are canonical and
   return `ToolResult`-based receipts. Existing `execute()` projects the same
   canonical results back to `ActionResult` for compatibility.
3. A terminal callback runs once per slot as soon as that slot settles.
   Duplicate, stale-owner, and late terminal submissions are suppressed by the
   batch ledger and reported with a typed disposition.
4. Completion order is stored truth. Declaration order is derived from stable
   slot indices.
5. Lifecycle adapters declare what they can cancel. Sync function, coroutine,
   thread, subprocess, HTTP, MCP, environment, and background families retain
   distinct owner/completion/timeout/cleanup/process-loss/migration facts.
6. Effect behavior is replaceable through an `EffectPolicy`. The reference
   policy derives declarations from tool metadata, exposes started/committed/
   rejected/unknown/reconciliation states, and decides retry eligibility from
   typed facts only.
7. Quiescence uses attempt registration plus condition/event acknowledgements
   and a monotonic deadline. A running non-cancellable thread yields
   non-migratable/worker-still-running, never a false cancelled or paused fact.
8. Partial persistence uses monotonic accepted/completed sequence barriers.
   `flush()` waits for real write completion or returns an incomplete receipt;
   it does not use sentinel insertion as proof of durability.

## Implementation sequence

1. [complete] Freeze contracts and tests from the exact baseline.
2. [complete] Add lifecycle/effect/batch contracts and ToolSpec/decorator
   metadata without growing the beginner root surface.
3. [complete] Refactor `ActionExecutor` around canonical `ToolResult` execution,
   immediate terminal publication, bounded segmented concurrency, fail-fast /
   collect-all, missing-slot closure, and compatibility projection.
4. [complete] Add deterministic quiescence/cancellation tracking and late-result
   handling for non-cancellable workers.
5. [complete] Replace durability sentinel/drop ambiguity with acknowledged
   receipts and wire terminal-slot persistence through `PendingWriteManager`.
6. [complete] Add implementation, executor-policy, lifecycle-adapter,
   effect-policy, partial-persistence, and cancellation-capability conformance
   suites, including one third-party-style executor/policy.
7. [complete] Publish sanitized Lane C fixtures, exact digests, lifecycle matrix,
   unsupported claims, and A/B/D handoff evidence.
8. [complete] Run the requested targeted/static/full gates, review the diff,
   make coherent commits, and record the final clean HEAD.

## Cross-lane handoffs

- Lane A consumes partial-batch snapshots, unresolved-effect counts,
  quiescence barriers, non-migratable reasons, and durability receipts.
- Lane B consumes stable batch/call/result correlation and completion-order
  versus declaration-order views.
- Lane D consumes exact lifecycle/effect/slot/batch receipt fixtures and must
  preserve their identity and loss semantics rather than infer them.

## Open integration gates

- Lane A's session-head/store operations are not modified here. Lane C exposes
  producer records and acknowledged persistence primitives for later wiring.
- Shared README/CHANGELOG/progress/task status are integration-owner files in
  this wave and therefore intentionally remain outside this branch.
