# S3 Lane C durable work runtime plan

Status: integrated A/B runtime qualification complete in G4 convergence
Source: `851f7902f15da670e72f4c04d7453cf37201aee7`
Branch: `codex/v4-s3-c-durable-work-runtime`
Worktree: `/Users/morinop/Desktop/WhitzardOS-s3-c`

## Exact-source census

The dispatch branch and `origin/feat/campaign-absorption` both resolve to the
source above (`docs(v4): close S2 truth and authorize S3 dispatch`). At that
source `qitos.core.work_graph.WorkGraph` is a strict record builder, not a
scheduler. `DelegateTool` constructs a nested `Engine`, `FanOutTool` owns a
`ThreadPoolExecutor`, and `_HandoffRuntime` replaces the live agent/history/state.
`Future.cancel()` is used only as an in-process request and does not prove the
worker stopped. `SessionSnapshot` plus `CheckpointStore` is the only durable
state truth and `ActionExecutor` is the only tool execution authority.

The brief names two documents that do not exist at this source. Their actual
source names are `docs/v4/03-aci-toolset.md` and
`docs/v4/09-runtime-lifecycle-and-error-semantics.md`.

## Current call graph

```text
Engine(runtime=RuntimeComposition)
  -> Engine.session(task) -> Session._create/_restore
  -> Session.run -> Engine.run (one canonical lifecycle loop)
  -> Engine act -> ActionExecutor -> BaseTool.execute(runtime_context)
  -> Decision.handoff -> _HandoffRuntime.execute_handoff (live compatibility)

AgentRegistry -> DelegateTool.execute -> nested Engine.run                 [debt]
AgentRegistry -> FanOutTool.execute -> ThreadPoolExecutor -> Engine.run    [debt]
WorkGraph mutators -> in-memory record lists/maps -> strict serialization  [no scheduler]
```

Target:

```text
Session direct verbs / agent tools
  -> WorkRuntime protocol on RuntimeComposition
  -> durable declaration committed in SessionSnapshot WorkGraph component
  -> injected WorkScheduler dispatches logical child references
  -> child Session uses the existing Engine loop and ActionExecutor
  -> terminal receipt committed -> deterministic Join state transition
```

## File leases

Lane C writes `qitos/core/work_graph.py`, Lane-C-owned modules under
`qitos/engine/`, thin adapters under `qitos/kit/tool/agent/` and existing agent
tool modules where compatibility requires it, Lane C tests, this plan, and
`tests/fixtures/s3/lane_c/`. It does not write root exports, Engine constructor
parameters, provider codecs/context-transfer ownership, trajectory/qita
readers, `docs/progress.md`, shared v4 status documents, README files, or the
changelog. A/B worktrees are read once only at final qualification.

## Runtime state machine

```text
declared -> queued -> dispatched -> running
   |           |          |          |
   |           +----------+----------+-> outcome_unknown
   +-> rejected                         |
running -> succeeded | failed | timed_out | cancelled

join: open -> closing -> closed
handoff: proposed -> committed -> target_dispatched
cancel: requested -> acknowledged -> quiesced | still_running
```

All transitions carry operation identity, payload digest, generation, attempt,
and a durable receipt. Terminal/unknown operations are never automatically
replayed. Stale, late, or superseded writes are fenced.

## Crash-window table

| Window | Durable truth / recovery action |
|---|---|
| before declaration commit | no operation; caller may retry same identity |
| declaration committed, not dispatched | eligible logical work may dispatch |
| dispatch begun, attempt absent | mark outcome unknown; reconcile, do not replay |
| child running at process loss | reattach by logical worker ref or mark unknown |
| child completion committed, parent unobserved | consume terminal receipt once |
| outcome accepted, join head uncommitted | generation-CAS replay of consumption |
| result after closed join | persist discarded/late fact; no reducer mutation |
| handoff before commit | old owner remains authoritative |
| handoff committed, target not started | new owner remains authoritative and dispatches |
| cancellation requested, worker live | report still-running; fence late commit |
| store commit failure | no persisted transition is claimed |
| reducer/scheduler unavailable | typed blocked/unavailable receipt, graph retained |

## Delivery sequence

1. Make every WorkGraph mutation copy-on-write and strengthen strict graph
   validation (identity, references, cycles, bounds, closed-state rules).
2. Add a replaceable scheduler/work-runtime protocol through
   `RuntimeComposition`, with a bounded reference local scheduler and an
   independent fake conformance implementation.
3. Implement durable operation identities, receipts, handoff/delegate/spawn/
   fan-out/join semantics, admission, cancellation, and restoration.
4. Route Session verbs and model-callable tools through the same runtime.
5. Add deterministic barrier/deadline tests, clean-process restoration, stable
   fixtures, and qualification evidence.
6. Perform exactly one read-only A/B manifest inspection. Bind real producer
   types/readers if available; otherwise publish `waiting_on_lane_a_b` with the
   exact missing commit/manifest requirements.

## A/B/D handoff

Lane A must supply its exact committed producer manifest, fork/session identity
types, strict reader, fixtures, digests, and test node IDs. Lane B must supply
the same for context/authority transfer types and receipts. Lane C will import
those real types and will not define temporary substitutes. Lane D receives
Lane C's producer manifest, scheduler conformance/crash/join/idempotency/runtime
fixtures, exact source commit and digests, supported/unsupported matrix, and
test node IDs. Full G4 remains the integration owner's responsibility.

G4 replay consumed the final Lane A bundle at source head
`9442647767bc9a7c45ed3bf07bc4f289412544ed` and replay head `1025f12`, including
the real `Session.fork`, `SessionForkReceipt`, child Session/head/generation,
fork lineage, and owner fencing. It consumed the repaired Lane B bundle at
source head `5efa1db19ae541234c562c4ba99e928d2381fc62` and repair commit
`8bbfd6580e03f77f51777e696d78ee783bc09f75`, including real strict
`ContextTransferPlan`/`ContextTransferReceipt` readers and
`execute_context_transfer`.

The integrated scheduler contract persists a reconstructable `WorkDescriptor`
instead of a callable, uses composition-root resolution, gives every default
call a fresh operation identity, restores eligible queued declarations, and
never automatically replays missing running or outcome-unknown work. Direct
Session verbs and model-callable adapters share this path. The candidate still
does not claim distributed scheduling, hard cancellation, or exactly-once
external effects.
