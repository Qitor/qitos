# S2 single-agent continuity runtime wave

Status: S2 single-agent runtime closed, promoted, pushed, and cleaned up;
Trajectory publication remains blocked
Historical dispatch baseline: `446a347d1ac73636476ca2515a01da601b567c68`
Updated: 2026-08-31
Owner: v4 integration owner with four capability lanes
Source gate: [`g2_r2_promotion_audit.md`](g2_r2_promotion_audit.md)

## Outcome target

Turn the qualified contracts into one useful, beginner-friendly vertical slice:

```text
start session
  -> model request through RequestView/provider codec
  -> multiple tool calls execute concurrently
  -> some tool slots complete
  -> pause request reaches a proven safe boundary
  -> process exits
  -> a fresh process restores from the canonical checkpoint truth
  -> queued steering is applied exactly once
  -> missing tool slots close without repeating committed effects
  -> session completes with inspectable lineage
```

S2 proves single-agent continuity first. Persistent child scheduling and
cross-process multi-agent execution remain deferred to S3.

## Public developer experience

Ordinary use must converge on one small façade:

```python
session = Engine(agent).session(task)
result = session.run()

pause = session.pause()
session = Engine.restore(pause.session_id, resolvers=resolvers)
result = session.run(steering="continue with the new constraint")
```

Exact naming is reviewed before export, but the user must not construct
snapshot envelopes, CAS records, codec reports, durability receipts, or
component registries for the default path. Advanced APIs expose those facts for
research and custom infrastructure without creating a second runtime.

## Four lanes

### Lane A — durable session head and façade

Owns Task 12B and the minimal composition root.

- add generation-checked session-head operations to the canonical checkpoint
  package, not a second SessionStore;
- persist the qualified SessionSnapshot and durability receipt atomically;
- implement the minimal Session handle/façade without a second Engine loop;
- resolve model/tool/env/artifact/secret/checkpoint references through explicit
  resolvers;
- reject stale head, missing resolver, failed persistence, and non-migratable
  snapshots with typed failures;
- provide deterministic local memory/file/SQLite-store conformance only where
  those stores already belong to the checkpoint package.

Handoff: exact store/head API and snapshot producer used by C and D.

### Lane B — provider request execution and steering

Owns Tasks 02C, the bounded part of 02D, and typed provider failures from 09B.

- make the real model runtime derive one RequestView from ExchangeLog;
- route OpenAI Chat/Responses, Anthropic, Gemini/GLM, LiteLLM and local adapters
  through declared codecs/capabilities without changing unsupported defaults;
- preserve native reasoning/continuation and ordered heterogeneous items where
  supported; fail typed before silent loss otherwise;
- persist request/codec reports, opaque continuation references, context
  selection, compaction, and queued steering through A's snapshot component;
- ensure provider failure is never returned as assistant-authored text;
- keep live-key tests opt-in; offline semantic fixtures remain authoritative.

Handoff: exact request/continuation/steering runtime producer consumed by A/D.

### Lane C — concurrent tool batches and safe pause

Owns Task 12C plus the relevant 09C/09D tool and durability semantics.

- make native multiple tool calls persist terminal slots immediately in actual
  completion order;
- distinguish declared order as a derived view only;
- checkpoint partial batches, effect state, idempotency, worker-running,
  timeout/cancellation and durability receipts;
- define safe pause as quiesced or explicitly non-migratable; never equate
  `pause_requested` with `paused`;
- resume only missing/eligible slots and never rerun a committed effect;
- surface outcome-unknown work for reconciliation rather than automatic retry;
- use deterministic barriers and bounded deadlines, not sleeps.

Handoff: partial-batch/effect/quiescence producer used by A/D.

### Lane D — continuity trajectory and qita inspection

Owns the bounded S2 portion of Task 05A and runtime qualification evidence.

- consume exact A/B/C runtime events and receipts for session/run/snapshot,
  request, tool slot, effect, steering, pause and restore lineage;
- propose the one canonical Trajectory record/writer boundary without replacing
  the frozen trace compatibility path prematurely;
- implement an internal reader/adapter only when it can represent the complete
  S2 vertical slice and explicit loss;
- expose inspectability through tests and a thin qita prototype only after A/C
  runtime facts exist; do not infer lineage from names;
- materialize only licensed, sanitized, portable fixtures;
- keep performance/compression/index claims blocked until real measurements.

Handoff: exact runtime qualification matrix and the decision whether the
Trajectory schema is ready for the next gate. S2 does not require a default
writer rollout.

## Concurrency and freeze points

All four lanes branch from one exact G2-R2 baseline:
`446a347d1ac73636476ca2515a01da601b567c68`, not the promoted contract code
head `c0f19cd...` and not a later documentation-only successor. They may
concurrently perform census, local implementation, fixtures, and failing
consumer tests, subject to these freeze points:

1. A freezes session-head/store operations before C persists pause state.
2. C freezes partial-batch/effect/quiescence records before A's clean-process
   vertical slice is accepted.
3. B freezes runtime request/steering components before A's fresh-process
   restore proof.
4. D cannot freeze Trajectory or qita migration until it consumes the reviewed
   A/B/C producers.

High-conflict files receive one owner lease. `Engine` integration is sequenced,
not concurrently edited without a lease. Shared README/CHANGELOG/progress/task
status remains integration-owner only.

## Integration gate

The first S2 convergence order is A -> C -> B -> D because persistence truth and
effect/quiescence determine whether provider continuation and trajectory facts
can be restored honestly. A combined clean-process test must use a bounded
subprocess and no live model.

Required proof:

- completed parallel slots are not rerun after process death;
- missing slots close once;
- committed effects remain committed and duplicate effect count is zero;
- outcome-unknown effects require reconciliation;
- queued steering survives and is consumed once;
- provider continuation is either restored by resolver or reports typed
  stateless/loss behavior;
- state, budget, artifact references, head generation, trace cursor and
  ExchangeLog match the last safe snapshot;
- stale processes and late workers cannot advance the restored head;
- ordinary users need only the small Session façade.

## Historical deferral ledger at S2 dispatch

- durable handoff/delegate/spawn/fan-out/join execution;
- persistent child scheduler and parent/child process-loss drills;
- distributed queues or hosted coordination;
- default Trajectory writer/store and qita migration;
- compression/index selection and published performance claims;
- broad compatibility deletion or public API deprecation.

Current disposition: S3 owns durable fork/handoff/delegate/spawn/fan-out/join,
child scheduling, recovery, and graph observability. Default Trajectory rollout,
qita default-reader migration, broad public-surface retirement, and authoring
facade work are S4. The current allocation is authoritative in
[`s3_durable_multi_agent_wave.md`](s3_durable_multi_agent_wave.md).

## Entry gate — satisfied

- [x] `docs/progress.md` records the G2-R2 fixing commits and independent validation.
- [x] Local, tracking, and remote refs were verified at
      `446a347d1ac73636476ca2515a01da601b567c68` with `0/0` divergence.
- [x] The primary worktree was clean and the retirement receipt was complete.
- [x] All 17 retired-worktree branch refs remain available.
- [x] No G2 contract/privacy/receipt/interface blocker remains.

The A -> C -> B -> D producers were replayed onto integration source
`47cd4dc5e1ed1b2b0d244bfc90fac031ec55be32` and converged by G3. The single-
agent vertical is exact-source qualified through a deterministic 20-round
parent/child process proof: canonical Session head, conversation, partial batch,
safe pause, resolver-only restore, stale rejection, steering once, and eligible-
missing recovery all pass without replaying the committed effect.

This closes S2 runtime qualification only. Trajectory schema/publication,
default writer rollout, qita migration, S3 persistent child scheduling,
agent-authoring sugar, and external-world exactly-once effects remain explicitly
unqualified.

## Promotion closure receipt

The G3 candidate was fast-forwarded into `feat/campaign-absorption`; the primary
checkout repeated the required gates, the branch was pushed normally, and
local/tracking/remote identities were verified at
`3af0ee3b2c3b5b5575e4e07cc31ff7f652327ba7` with `0/0` divergence. The
temporary S2 worktree and all previous-wave non-primary worktrees were removed
without force after clean-state and retained-ref checks. Statements above about
entry readiness at `446a347...` are historical S2 dispatch evidence, not the S3
dispatch instruction.
