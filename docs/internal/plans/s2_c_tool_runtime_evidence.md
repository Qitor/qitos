# S2 Lane C tool runtime evidence

Status: qualified
Updated: 2026-08-31
Baseline: `446a347d1ac73636476ca2515a01da601b567c68`
Implementation commit: `769422d4d6b5dfd0552fbe98a34def1885786848`
Fixture producer commit: `c63917ab48aff65b3e5df615ea947ab183653d97`

## Qualified outcome

Lane C extends the existing `ActionExecutor`; it does not introduce a second
executor or a second canonical result. `ActionExecutor.execute_one()` and
`execute_batch()` return `ToolResult`-based runtime records. The legacy
`execute()` method is a compatibility projection over that same batch path.

The main tool-author path is unchanged:

```python
class SearchTool(BaseTool):
    def execute(self, args, runtime_context):
        ...
```

Function tools declared with `@tool` use the same boundary. `run()` delegates
to `execute()` for compatibility. Tool authors do not create thread pools,
batch ledgers, terminal callbacks, or checkpoint writes.

The implementation-neutral seam is in `qitos/core/tool_runtime.py`. The
reference mechanics are in `qitos/engine/tool_runtime.py` and the existing
`qitos/engine/action_executor.py`. The seam includes:

- one/batch execution and execution policy;
- immediate terminal-result and partial-batch callbacks;
- stable batch slot, attempt identity, and owner generation facts;
- lifecycle and effect receipts;
- capability-specific cancellation and quiescence;
- permission, validation, runtime context, progress, and artifact paths;
- typed terminal suppression and batch closure.

The advanced contracts are intentionally module-level and do not expand the
beginner root export surface.

## Parallel execution evidence

One model decision may declare multiple calls. `ActionExecutor` partitions the
declaration into ordered concurrency-safe segments, uses bounded worker pools,
and treats exclusive tools as barriers. The `ToolBatchLedger` records terminal
commit order as source truth and derives declaration order from immutable slot
indices. A per-batch publication barrier prevents a later terminal callback
from overtaking an earlier committed terminal.

Each committed terminal slot publishes:

1. `ToolTerminalReceipt` immediately;
2. its current `ToolBatchSnapshot` immediately;
3. the final closed snapshot when every declared slot is terminal.

Fail-fast cancels only work that has not started and drains already-running
work to its real result. Collect-all continues all declared segments. Timeout,
pre-cancel, fail-fast cancellation, and defensive missing-slot closure all
produce canonical terminal results. Duplicate and stale-owner submissions do
not mutate the authoritative slot.

## Executable lifecycle matrix

`TOOL_LIFECYCLE_MATRIX` is executable data, and its exact JSON representation
is fixture-qualified. All rows are non-migratable while unresolved; a terminal
or acknowledged-cancelled receipt may be quiesced.

| Resource | Owner | Cancellation capability | Timeout/process-loss truth |
| --- | --- | --- | --- |
| sync function | executor call frame | none | observer timeout does not stop its Python worker; process loss is unknown |
| async coroutine | executor-owned task | cooperative | deadline requests task cancellation and requires acknowledgement |
| thread | thread creator | none | Python threads are not hard-cancelled; late completion cannot replace terminal state |
| subprocess | process creator | terminate owned process | only the owner/adapter may terminate and reap; external effects may need reconciliation |
| HTTP client | client creator or borrowed-client owner | cooperative | transport cancellation does not prove the remote outcome |
| MCP request | MCP transport owner | cooperative | request timeout does not prove server-side cancellation |
| environment operation | environment implementation | none by default | behavior is capability-specific; unfinished external state is unknown |
| background operation | operation creator | none by default | deadline yields worker-still-running until adapter acknowledgement |

Lifecycle receipts identify the attempt, resource spec, owner generation,
terminal/unresolved state, timestamps, worker status, outcome uncertainty, and
migration truth. A lifecycle adapter may provide a stronger resource-specific
capability, but the generic executor never invents one.

## Effects and idempotency evidence

The effect grammar distinguishes `no_effect_declared`, `not_started`,
`started`, `committed`, `rejected`, `unknown`, and
`reconciliation_required`. A tool or replaceable effect policy supplies the
effect reference and optional idempotency key. The reference policy derives a
stable key when the tool omits one.

- committed effects are non-retryable;
- a live worker blocks retry even when no external effect was declared;
- failure after a declared effect was dispatched requires reconciliation;
- unknown external outcomes are never guessed;
- stale-owner and duplicate terminals cannot advance effect state.

The conformance fake backend executes a commit-then-fail tool with a retry
policy of three attempts. The runtime performs one attempt, records one key,
and observes zero duplicate effects. This proves the reference decision for
that backend; it is not an exactly-once claim about an external system.

## Pause, cancellation, and durability evidence

`QuiescenceBarrier` is condition-based and deadline-bounded. It publishes
pause-requested, quiescing, quiesced, non-migratable,
cancellation-requested, cancelled, worker-still-running, and outcome-unknown
facts. Correctness tests use events and completion acknowledgements rather than
sleep-based ordering.

A timed-out sync/thread worker remains non-migratable until its natural
completion event. Cooperative cancellation becomes quiesced only after its
terminal acknowledgement. An outcome-unknown receipt remains non-migratable
after local worker completion.

`DurabilityManager.flush()` now waits for monotonic store completion receipts,
not queue removal or sentinel insertion. The race proof blocks the backing
store after queue consumption and verifies that flush cannot complete until
the store acknowledges the write. Fast-store publication is also covered so a
terminal acknowledgement cannot regress to `queued`. Queue rejection is a
terminal failed durability fact rather than a silent drop.

`PendingWriteManager` stages each terminal slot once, persists it immediately
when a checkpoint head exists, suppresses equal duplicates, rejects conflicting
terminals, rejects stale generations, and returns acknowledged wait receipts.

## Permission and safety evidence

The existing permission pipeline remains authoritative. Structural and
tool-authored validation run before permission evaluation. Interceptor rewrites
are structurally revalidated. Permission-provided argument rewrites pass both
structural and tool-authored validation again before dispatch. Permission
denials and approval needs become canonical policy results.

Callbacks and approval interaction remain injectable; no product-specific UI
was added. Canonical permission diagnostics do not copy raw tool arguments, and
the conformance test proves that a secret-like argument is absent from the
persistence record. No security-research tool was added to a default toolset.

## Third-party conformance

The conformance suite exercises:

- class, decorated function, async, MCP-bridged, and environment-operation
  tools through the same canonical executor;
- canonical artifact output;
- the reference executor and a third-party-style composed executor/policy;
- a replaceable third-party effect policy;
- sync, async, thread, and subprocess lifecycle families plus fake adapters;
- a non-cancellable thread, cooperative cancellation, outcome unknown,
  committed effect, partial persistence, duplicate terminal, and stale old
  generation.

## Cross-lane handoff

### Lane A — session runtime

Consume:

- `ToolBatchSnapshot` for declared/open/terminal slots and partial progress;
- `ToolEffectReceipt` and `ToolResult` effect fields for unresolved-effect
  accounting;
- `QuiescenceBarrier.request_pause()` and `QuiescenceReceipt` for safe pause;
- `PendingWriteFlushReceipt` and `DurabilityFlushReceipt` for completion
  acknowledgement.

Do not persist live callbacks, workers, futures, clients, or adapters. A pause
is migratable only when the receipt says `quiesced`; worker-still-running and
outcome-unknown are explicit blockers.

### Lane B — model I/O

Correlate using:

- `batch_id` for the decision batch;
- `slot_id`/`action_id` for the declared call;
- typed `attempt_id` plus `owner_generation` for the execution attempt;
- `completion_index` for observed terminal order;
- `declaration_index` for the derived model declaration view;
- `result_ref` in batch closure for the canonical terminal result.

Never infer completion order from declaration order. Preserve missing/cancelled
slots in batch closure rather than shortening the result list.

### Lane D — runtime events and observability

`_ActionRuntime` emits the safe stages `tool_batch_snapshot` and
`tool_slot_terminal`. The terminal event carries slot/completion correlation,
trace-safe `ToolResult`, lifecycle facts, effect facts, persistence receipt,
and current batch snapshot. Preserve the published schema versions and loss
facts; do not reconstruct uncertainty from status strings.

The fixture is sanitized and contains no local path, secret, callback, live
resource, or transport object.

## Exact fixtures

Fixture producer commit:
`c63917ab48aff65b3e5df615ea947ab183653d97`

| Fixture | SHA-256 |
| --- | --- |
| `tests/fixtures/s2/lane_c/lifecycle_matrix.v1.json` | `cac608a75a0c29330da1c6e1c2147971d6c24ebcc50981dd6e80cbafeaaa246c` |
| `tests/fixtures/s2/lane_c/runtime_handoff.v1.json` | `db86d8004a2543760365f25f4cb451839115b72bc0120e8731cb793a69a2d5a6` |

Schema versions represented:

- `qitos.s2_lane_c.lifecycle_matrix/v1`;
- `qitos.s2_lane_c.runtime_handoff/v1`;
- `qitos.tool_batch_snapshot/v1`;
- `qitos.tool_terminal_receipt/v1`;
- `qitos.tool_lifecycle_receipt/v1`;
- `qitos.tool_effect_receipt/v1`;
- `qitos.tool_result/v2` through the canonical runtime writers.

## Unsupported cancellation and delivery claims

The following claims are explicitly unsupported:

- hard cancellation of a Python function or thread;
- server-side cancellation from an MCP client timeout;
- remote rollback from an HTTP client timeout;
- termination of a subprocess not owned by the lifecycle adapter;
- universal cancellation for environment or background operations;
- migratability while any worker may still commit;
- safe retry while an effect outcome is unknown;
- exactly-once external delivery or effect execution;
- terminal replacement by a late or stale-owner result.

## Validation ledger

The final implementation/fixture head `c63917a` passed:

| Gate | Result |
| --- | --- |
| core function/tool-result/recovery/structural group | 123 passed |
| engine concurrent/cancellation/interrupt group | 44 passed |
| durability flush race suite | 2 passed |
| tool runtime conformance | 18 collected and passed in the final full suite |
| tool lifecycle conformance | 14 collected and passed in the final full suite |
| architecture/public/no-local-path group | 10 passed |
| `python scripts/static_quality.py check` under pinned Python 3.12.7 | passed; 399 baselined findings, no new debt |
| direct flake8 core/engine/models/trace | passed |
| direct mypy core/engine/models/trace | passed; 86 files |
| full `pytest -q` | 2137 passed, 50 skipped |
| `git diff --check` | passed |

The shell's default `python` is 3.13.3, so the reproducible static-quality gate
was run with the repository-pinned Python 3.12.7 interpreter recorded in
`quality/toolchain.json`.

## Known gaps and integration ownership

- Lane A still owns durable session-head/restore integration and pause API
  wiring; Lane C supplies the records and barriers.
- External effect reconciliation remains tool/policy-owned.
- Generic lifecycle metadata does not seize ownership of a tool-created
  client, process, or background worker; a lifecycle adapter must expose the
  real owner capability.
- Persistent child scheduling, supervisor/worker strategy, spawn policy, and
  join policy are intentionally not implemented.
- Shared README, changelog, progress, and integration ledgers remain the
  integration owner's responsibility under the wave lease.
