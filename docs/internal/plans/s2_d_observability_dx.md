# S2 Lane D observability and developer-tooling plan

Status: framework complete; runtime producer qualification is blocked
Baseline: `446a347d1ac73636476ca2515a01da601b567c68`
Branch: `codex/v4-s2-d-observability-dx`
Owner: S2 Lane D

## Outcome

Build the bounded Lane D framework layer around one future `Trajectory`
architecture without replacing the frozen `qitos.trace` writer or claiming
that the S2 runtime is qualified. The deliverable provides composable event
sinks, a lightweight candidate store, readers, exporters, safe projections,
and evaluation contracts. qita remains a compatibility consumer until exact
Lane A/B/C runtime facts are accepted.

## Lease and constraints

This lane changes only Lane D-owned tracing, qita, evaluate, metric, tests,
fixtures, scripts, and internal plan/evidence files. `qitos/trace` remains
read-only. Core, engine, checkpoint, provider adapters, tool execution, and
integration-owner documentation are not changed.

The runtime-facing target remains:

```python
engine.add_event_sink(my_sink)
```

That call is deliberately not wired in this branch because the Engine contract
is outside the Lane D lease and the reviewed Lane A/B/C producer facts are not
present at this baseline. Lane D supplies the sink boundary and qualification
gate that a later integration commit can consume.

## Current plane census

| Source | Current authority | Lane D disposition |
|---|---|---|
| `engine.states.RuntimeEvent` | canonical in-process phase fact | producer input; never redefined by Lane D |
| `engine.states.StepRecord` | canonical in-process step aggregate | producer input; converted with explicit compatibility loss |
| `engine.events.EngineEvent` | streaming runtime view | derived stream, not storage truth |
| `trace.TraceEvent` / `TraceStep` | frozen compatibility artifacts | remain readable through an additive compatibility reader |
| `tracing.Trace` / `Span` / processors | derived diagnostic/export plane | processor interoperability remains; not qita truth |
| `render.RenderEvent` JSONL | presentation plane | derived and lossy; never promoted to canonical storage |
| qita direct file parsing | official compatibility consumer | move behind a reader boundary without switching data source |
| `evaluate.EvaluationContext` | evaluator input coupled to v1-shaped lists | accept a structural declarative run/trajectory view |
| `metric.MetricInput` | store-independent aggregation row | add version/provenance/loss fields, no store dependency |

The candidate `TrajectoryRecord.kind` vocabulary covers session/run,
model request/response, reasoning/continuation, tool batch/slot, lifecycle,
effect, context/compaction, steering, snapshot/pause/restore, budget/stop,
error/loss, artifact, and work-graph lineage. Spans, compatibility events,
export records, evaluation inputs, and UI payloads are views over those facts.

## Work packages

1. Define one unfrozen `Trajectory`, `TrajectoryRecord`, `TrajectoryReader`,
   `TrajectoryStore`, and `TrajectoryExporter` candidate architecture inside
   `qitos.tracing`; add no root exports and no version-suffixed public types.
2. Add an event-sink protocol with capabilities, safe projection, durability
   receipts, flush/close, failure policy, and backpressure policy. Required
   failures raise; optional failures remain explicit in dispatch reports.
3. Add in-memory and atomic single-file JSON reference stores. Returned values
   are isolated, integrity is validated, artifact references remain references,
   and size reporting is factual byte measurement only.
4. Add a frozen-trace compatibility reader and a store reader. Adapt qita's
   board/replay/export loading path to the reader interface while keeping the
   compatibility reader as the default.
5. Add a canonical exporter with exact re-import and a deliberately lossy
   summary exporter with a machine-readable loss report and invariant re-import.
6. Add raw/private, redacted/public, and safe-diagnostic projections with
   bounded output, secret/header/cookie/token filtering, provider-raw policy,
   host-path rejection, and non-echoing findings.
7. Extend evaluator/metric contracts with declarative view, version,
   provenance, and loss metadata. Add a registry and third-party-style
   evaluator conformance without live-model scoring.
8. Add an exact-producer qualification runner for the S2 facts. Missing or
   unreviewed A/B/C receipts must yield `runtime_not_ready`; synthetic receipts
   cannot qualify runtime behavior.
9. Run all requested targeted, architecture, static-quality, full-suite, type,
   style, and diff checks. Record only observed results in the evidence file.

All nine work packages are complete. The runtime-facing Engine registration
step remains outside this lease and behind the exact-producer qualification
gate.

## Readiness states and stop gates

- Event protocol: candidate-ready after conformance.
- Reference store: candidate-ready after conformance and integrity tests.
- Runtime producer: `runtime_not_ready` until exact A/B/C facts qualify.
- qita reader: compatibility-reader ready; candidate-store reader not default.
- Trajectory schema: unfrozen.
- Publication: unready.
- Compression/index/performance claims: unavailable until representative
  licensed fixtures and measurements exist.

No schema receipt, fake sink/store test, or synthetic fixture may clear a
runtime producer blocker.

## Validation

The authoritative command list is the one in the Lane D assignment. In
addition, every changed file under `qitos/tracing`, `qitos/qita`,
`qitos/evaluate`, and `qitos/metric` receives targeted flake8 and mypy checks.
The evidence file records exit status, test counts, and any environment-limited
checks without converting an unavailable check into success.
