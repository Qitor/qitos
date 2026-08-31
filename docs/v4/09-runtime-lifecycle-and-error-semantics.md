# Task 09 — runtime lifecycle and error semantics

Status: 09A/C1-R integrated; additional contracts are in the unpromoted G2 candidate; G2-R2 and runtime packages pending
Depends on: Task 01 and Task 08A
Coordinates with: Tasks 02, 03, 05, 12, and 13
Risk: high — failure, timeout, durability, and shutdown behavior

---

## 1. Goal

Give every runtime resource and failure one explicit owner, one observable
terminal state, and one synchronization boundary. A caller must be able to tell
the difference between model failure and model text, timeout and cancellation,
accepted and durable checkpoint, best-effort hook and complete trace, open and
closed external resource.

Task 09 is a semantic contract, not a second execution kernel. Changes to model
transactions land in Task 02-owned modules; tool execution changes land in Task
03-owned modules; trace event changes land in Task 05-owned schemas. Task 12 owns
the durable session lifecycle and safe pause/restore protocol; Task 13 owns
multi-agent ownership and child-work semantics. Task 09 supplies the shared
resource, timeout, failure, and durability receipts they consume.

## 2. Lifecycle vocabulary

Before code changes, define an internal lifecycle vocabulary used by tests and
receipts:

- resource states: `new -> opening -> open -> closing -> closed`, plus `failed`;
- work states: `submitted -> accepted -> running -> succeeded|failed|timed_out|cancelled|dropped`;
- durability states: `accepted -> queued -> persisted|failed|dropped`;
- shutdown guarantees: `drained`, `abandoned`, `still_running`, and deadline;
- failure fields: phase, category, retryable, safe-to-retry, source exception,
  redacted diagnostic, and correlation IDs.

Session states (`created`, `running`, `pause_requested`, `paused`,
`waiting_input`, `restoring`, and terminal states) are defined in Task 12. Work
ownership operations and child/join states are defined in Task 13. They may
reuse Task 09 receipts but must not overload generic `work states` until
submission, durability, session lifecycle, and ownership are indistinguishable
in every consumer—which they are not today.

Public names are a Task 09A decision. Do not export a universal enum before the
model/tool/checkpoint cases prove that the vocabulary is coherent.

## 3. Work packages

### 09A — ownership matrix and conformance harness

1. Write `docs/internal/plans/task09_runtime_lifecycle.md`.
2. Inventory every owned thread, executor, subprocess, async client, scheduler,
   MCP session, stream, checkpoint worker, trace processor, and environment.
3. For each resource record creator, owner, close method, implicit close path,
   idempotency, deadline behavior, and failure surface.
4. Build reusable conformance fixtures that detect leaked resources and call
   shutdown twice.
5. Define which resources Engine owns versus borrows. Borrowed caller objects
   must never be closed implicitly.

Decision gate: stop before adding a public lifecycle protocol if existing
`Env`, `Model`, tool, and store contracts cannot adopt it without fake methods.

Evidence (Lane C C1, 2026-08-29):

- the complete creator/owner/open/close/partial-open/idempotency/deadline/
  cancellation/failure/test/package matrix is published in
  `docs/architecture/tool-outcome-and-runtime-ownership.md`;
- the decision gate rejects a universal public lifecycle interface: native
  owner-specific `close`, `aclose`, `cleanup`, and `shutdown` methods remain;
- `tests/fixtures/tool_results/v1/lifecycle_receipts.json` fixes repeated-close
  and borrowed-resource-open semantics for later conformance work;
- `tests/checkpoint/test_durability_flush_race_window.py` deterministically
  proves the known full-queue/flush warning race without changing durability
  behavior; Task 09D retains implementation ownership.

C1-R adds no lifecycle interface or durability behavior. It makes terminal
ToolResult invariants mechanical, turns non-JSON/malformed tool returns into a
typed contract-boundary execution outcome, and publishes a versioned
ToolResult-only trace-safe view with explicit loss facts. This is Lane D input,
not a claim that full trajectory privacy or hook failure policy is complete.

### 09B — typed model/provider failures

Coordinate with Task 02C.

1. Define a typed model-call failure at the model boundary with provider/API
   mode, phase, retryability, HTTP/status metadata, request ID where available,
   and redacted details.
2. Remove success-text error returns from Anthropic, Gemini, and local adapters.
3. Make streaming and non-streaming failures equivalent.
4. Apply retry only to typed retryable failures and only when the configured
   policy permits it; preserve default-off behavior where currently promised.
5. Record a failure event/receipt without storing secrets or full raw payloads.

Migration tests must prove that a genuine model response beginning with
`"Error:"` remains ordinary content.

### 09C — sync/async bridge and timeout semantics

Coordinate with Task 03.

1. Separate three operations: await a returned awaitable, invoke async code from
   a sync API, and enforce a deadline.
2. Specify behavior with and without an active event loop and from Engine versus
   standalone executor entry points.
3. Consolidate duplicate bridge mechanics only when their ownership and
   exception semantics match.
4. Label thread timeout as non-cancelling and preserve
   `worker_still_running`; prohibit commit of late results into closed steps.
5. Provide process-isolated execution as an opt-in capability only for tools
   that require hard cancellation.
6. Ensure retry does not overlap a still-running prior attempt unless an
   explicit idempotency/cancellation contract permits it.

### 09D — checkpoint durability receipts

1. Choose explicit ASYNC overflow policies: blocking with deadline, rejection,
   or lossy drop. The policy is configuration, not an implementation accident.
2. Return/record a receipt that does not imply persistence before the store
   confirms it.
3. Retain worker failures and surface them at `flush`, `shutdown`, run result,
   and trace boundaries as appropriate.
4. Make flush drain deterministically or return an incomplete receipt; do not
   rely on a sentinel that can itself be dropped.
5. Test queue saturation, failed writes, slow writes, repeated flush/shutdown,
   EXIT-mode exception behavior, and interpreter/process exit assumptions.
6. Supply Task 12 with typed accepted/persisted/failed/dropped/incomplete
   receipts and a deterministic drain boundary. Task 12 owns immutable snapshot
   content, atomic session-head advancement, and stale-owner conflicts.

Decision gate: changing the existing `put()` return type requires a compatibility
adapter and migration plan. An internal receipt plus a new explicit method may
be safer for the first release.

### 09E — hook and observability failure policy

Coordinate with Task 05.

1. Classify hooks/processors as critical or best effort.
2. Add a policy such as `fail_open` versus `strict`; defaults must preserve
   compatibility but may no longer be silent.
3. Count hook failures by hook/phase and expose redacted diagnostics in the run
   receipt and canonical trace.
4. Mark trace completeness when events/artifacts fail to persist.
5. Prevent recursive failure when recording a trace-writer failure.

### 09F — external integrations and cleanup

1. Add lifecycle conformance for MCP stdio/HTTP, model HTTP clients, Docker/host
   environments, cron schedulers, functional executors, and trace processors.
2. Run a version-pinned official MCP SDK spike covering initialization,
   tools/list, tools/call, errors, notification handling, cancellation, and
   cleanup. Record adopt/defer/reject with dependency and compatibility data.
3. Add `close/aclose` or context managers only to actual owners; borrowed
   resources keep caller ownership.
4. Resolve functional API and unsupported integrations through Task 10 rather
   than adding lifecycle surface to code selected for deprecation.
5. Provide resolver/ownership contracts needed for Task 12 clean-process restore
   and Task 13 child workers without serializing live clients or handles.

## 4. Required test matrix

| Dimension | Cases |
|---|---|
| Entry point | Engine sync, AsyncEngine, standalone model/tool, context manager |
| Loop state | no loop, active loop, worker thread |
| Result | success, typed failure, malformed result, timeout, cancellation |
| Resource | borrowed, internally owned, partially opened |
| Shutdown | normal, repeated, deadline exceeded, failure during close |
| Retry | disabled, retryable, non-retryable, prior worker still running |
| Durability | sync, async accepted, full queue, failed store, exit flush |
| Hooks | best effort, strict, trace sink failure |
| Session consumer | pause boundary, clean-process restore, stale owner, missing resolver |
| Multi-agent consumer | handoff, child timeout, parent cancellation, late join result |

Tests must use bounded deadlines and deterministic fakes; no test may rely on a
real network or an unbounded sleep.

## 5. Acceptance criteria

- [ ] Model transport/provider failures cannot be mistaken for assistant text.
- [ ] Streaming and non-streaming calls share failure categories and receipts.
- [ ] Every framework-owned resource has an idempotent close path and a tested
  partial-open failure path.
- [ ] Borrowed resources are not closed by the framework.
- [ ] Tool timeout documentation and metadata state whether work is still
  running; late results cannot mutate a closed step.
- [ ] Retry never overlaps a non-cancelled attempt without explicit permission.
- [ ] Checkpoint callers can distinguish queued, persisted, failed, and dropped.
- [ ] Flush/shutdown reports incomplete durability instead of silently passing.
- [ ] Hook failures are counted and visible; strict mode is tested.
- [ ] No new global thread pool, background thread, or event loop is created
  without an owner in the lifecycle inventory.
- [ ] Task 12/13 can state whether a worker/resource is quiesced, still running,
  failed to close, or unsafe to restore without inventing duplicate receipts.
- [ ] Full tests, architecture boundaries, and Task 08 ratchet stay green.

## 6. Verification

```bash
pytest -q tests/models tests/engine tests/checkpoint tests/mcp
pytest -q -k "timeout or cancel or retry or lifecycle or shutdown or durability"
pytest -q
pytest -q tests/test_architecture_boundaries.py
flake8 qitos
mypy qitos
```

Use the Task 08 ratchet wrapper if repository-wide baseline findings still
exist; do not weaken the stable zero-error commands.

## 7. Stop-and-escalate decisions

Stop for review before:

- changing a public return type or default retry/overflow policy;
- claiming thread cancellation or durability that the backend cannot provide;
- closing an object supplied by the caller;
- adding process isolation to the base path;
- coupling provider-native error types into `qitos.core`;
- replacing MCP transports without a pinned compatibility report;
- making observability failures fatal by default;
- putting session identity/snapshot or multi-agent ownership semantics into a
  generic lifecycle enum owned solely by Task 09.
