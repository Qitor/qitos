# S2 Lane D observability and developer-tooling evidence

Evidence date: 2026-08-31
Baseline: `446a347d1ac73636476ca2515a01da601b567c68`
Branch: `codex/v4-s2-d-observability-dx`
Worktree: `/Users/morinop/Desktop/WhitzardOS-s2-d`

## 1. Outcome

Lane D now has one unfrozen candidate `Trajectory` architecture, a structural
event-sink seam, replaceable stores/readers/exporters, safe projections,
reader-backed qita compatibility paths, declarative evaluator inputs, and an
exact-producer qualification gate. No Engine producer wiring was added and no
S2 runtime qualification is claimed.

## 2. Baseline and lease

`HEAD` started exactly at the required baseline. The change set is confined to
Lane D-owned tracing, qita, evaluate, metric, D-owned tests/fixtures/scripts,
internal plan/evidence, and a static-quality baseline shrink caused by fixing
18 findings in files this lane modified. No `qitos/core`, `qitos/engine`,
`qitos/trace`, checkpoint, provider, tool-executor, README, CHANGELOG, or shared
architecture document was changed.

## 3. Exact event-plane census

| Plane | Existing authority | Role in the candidate architecture |
|---|---|---|
| `engine.states.RuntimeEvent` | canonical in-process phase fact | structurally adapted producer fact |
| `engine.states.StepRecord` | canonical in-process step aggregate | structurally adapted with declared compatibility loss |
| `engine.events.EngineEvent` | runtime streaming view | derived stream; not storage authority |
| `trace.TraceEvent` / `TraceStep` | frozen persisted compatibility contract | additive reader input; writer unchanged |
| `tracing.Trace` / `Span` | v2 diagnostic span plane | derived view/processor input |
| `render.RenderEvent` JSONL | presentation stream | lossy derived view |
| `TrajectoryRecord` | Lane D future data-plane candidate | common record vocabulary, unfrozen |
| exporter output | transfer/projection artifact | exact or explicitly lossy representation |
| evaluate/metric input | declarative consumer view | store-independent downstream view |
| qita payload | official UI/client view | reader-produced public projection |

`RecordKind` covers session/run, model request/input/response/output,
reasoning/continuation, tool batch/slot, lifecycle, effect,
context/compaction, steering, snapshot/pause/restore, budget/stop, error/loss,
artifact, step, and future work-graph lineage. `classify_event` is the one
mapping boundary; the implementation does not introduce another runtime event
class and does not make core/engine import qita or render.

## 4. Event sink protocol

`EventSink` declares `receive`, `flush`, `close`, capabilities, safe projection,
failure policy, backpressure policy, and optional durability receipts.
`EventSinkDispatcher` raises required-sink failures, records optional-sink
failures in a typed dispatch report, and does not convert a sink failure into
run success. It depends only on structural sink behavior, not Engine private
attributes or vendor types.

## 5. Reference/custom sink conformance

The reference `InMemoryEventSink` and the independent structural fake sink in
`tests/fixtures/s2/lane_d/third_party.py` run through the same conformance
contract. The store-backed sink additionally exercises durable receipt and
flush/close behavior. Result: 5/5 sink tests passed.

## 6. Trajectory architecture

The only public Python candidate names are `Trajectory`, `TrajectoryRecord`,
`TrajectoryReader`, `TrajectoryStore`, and `TrajectoryExporter`; there are no
`TrajectoryV1`/`TrajectoryV2` classes. Candidate storage/export versions are
explicit strings, while the Python architecture remains singular. Records
carry session/run/step/span/work lineage, privacy view, artifact references,
content digest, source, role, sequence, timestamp, and loss metadata.

The candidate is exported only from `qitos.tracing`, not the package root.
Schema status is **unfrozen** because exact A/B/C producer facts are absent.

## 7. Store, reader, and exporter evidence

| Capability | Reference implementation | Independent/custom evidence |
|---|---|---|
| Store | isolated in-memory store; atomic single-file JSON store | structural fake store uses the same suite |
| Reader | store reader; frozen-trace compatibility reader | structural protocol use in qita/evaluation tests |
| Exporter | canonical JSON export and exact re-import | deliberately lossy event summary + invariant re-import |
| Integrity | record, trajectory, file-byte and content digests | tamper rejection tests |
| Query/replay | run/session query and ordered replay | reference/fake parity |
| Artifact | `ArtifactRef` remains a reference | payload is not duplicated |
| Size | actual encoded/on-disk byte counts | no compression or dedup estimate |

Results: store 6/6, exporter 5/5, reader tests included in tracing 78/78.
The JSON store uses atomic replacement and does not require SQLite.

The frozen trace adapter is additive and never promotes directory names or
legacy `parent_run_id` guesses into authoritative lineage. Missing session,
work-graph, loss, and other unavailable facts are declared in `LossReport`.

## 8. qita integration

Board discovery, replay/export loading, live polling, and candidate session
inspection now enter through a reader adapter. The default remains
`TraceCompatibilityReader`; the candidate store reader is available but is not
the default. Tool/effect, snapshot, and work-graph timelines are reader
projections. Run-scoped asset URLs replace portable in-run paths, and traversal
or outside-run host paths are rejected.

The historical in-process `_discover_runs` helper retains its private storage
path for compatibility. The HTTP `/api/runs` response uses the public reader
projection and omits that path. qita no longer implements trace-copy fork
semantics: the old mutation endpoint returns typed `runtime_not_ready` until a
runtime-owned client contract exists.

## 9. Evaluation extension

`DeclarativeRunView` is a structural, store-independent evaluator input.
Evaluation context/results and metric input/reports carry schema version,
provenance, and loss. `EvaluatorRegistry` supports third-party registration;
the custom evaluator conformance uses deterministic data and no live-model
score. Benchmark-domain semantics were not added to core.

## 10. Privacy, portability, and logging

The projection boundary supports `raw_private`, `redacted_public`, and
`safe_diagnostic` views. Public/diagnostic output enforces bounded depth,
mapping/sequence size, string size, and total nodes; filters secret-bearing
keys and values, bearer/API keys, tokens, raw authorization/cookie headers,
provider raw payloads, host paths, file URLs, and local endpoints; and reports
only non-echoing locations/actions. Hashes verify integrity and are never used
as sanitization. Canonical raw data is copied before projection and is not
irreversibly overwritten. Result: 12/12 privacy/portability tests passed.

## 11. A/B/C qualification matrix

The checked-in receipt set is intentionally empty. The runner validates exact
committed bytes, SHA-256 bindings, the producer commit, current-worktree byte
identity, qualification authority, non-synthetic runtime execution, exact
scenario sets, and per-scenario pass status.

| Lane | Required exact runtime facts | Observed status |
|---|---|---|
| A | session continuity, pause/restore, stale rejection, trace cursor, artifact reference, budget continuity | missing; unqualified |
| B | request/reasoning/continuation, steering applied once, loss declaration | missing; unqualified |
| C | parallel tool slots, effect receipt, late-result rejection | missing; unqualified |

Observed runner result: `runtime_not_ready`, exit 2, zero qualified lanes,
zero qualified scenarios, 15 non-secret findings (three lane blockers and
twelve missing facts). A committed valid-receipt test proves the gate, while
synthetic evidence is explicitly rejected; neither test is reported as live
runtime qualification.

## 12. Readiness truth table

| Claim | Status | Evidence/constraint |
|---|---|---|
| event protocol | **ready** as a Lane D structural/conformance seam | sink suite passed; Engine wiring outside lease |
| reference store | **ready** as an internal candidate | reference/custom conformance and integrity passed |
| runtime producer | **unqualified** | exact A/B/C receipts absent |
| qita reader | compatibility reader **ready and default** | parity tests passed |
| candidate store reader | **ready, not default** | runtime gate remains blocked |
| Trajectory schema | **unfrozen** | producer facts insufficient |
| publication | **unready** | schema/runtime not qualified |
| measurement claims | **unavailable** | only factual byte measurement exists |

## 13. Unsupported claims

This lane does not claim complete S2 runtime execution, stable/frozen
Trajectory schema, Engine `add_event_sink` availability, qita-owned
pause/resume/fork execution semantics, W&B/MLflow integration, compression,
deduplication, indexing, performance gains, production scalability, or
publication readiness.

## 14. Validation receipts

All commands below used `/opt/anaconda3/bin/python` 3.12.7, the runtime pinned
by `quality/toolchain.json`, unless explicitly noted.

| Command | Observed result |
|---|---|
| `pytest -q tests/tracing` | 78 passed |
| `pytest -q tests/qita tests/test_qita_cli.py` | 23 passed |
| `pytest -q tests/test_event_sink_conformance.py` | 5 passed |
| `pytest -q tests/test_trajectory_store_conformance.py` | 6 passed |
| `pytest -q tests/test_trajectory_exporter_conformance.py` | 5 passed |
| `pytest -q tests/test_evaluator_conformance.py` | 3 passed |
| `pytest -q tests/test_privacy_portability_conformance.py` | 12 passed |
| `pytest -q tests/test_benchmark_trajectory_store.py tests/test_s1_d_lineage_readiness.py` | 79 passed |
| `pytest -q tests/test_architecture_boundaries.py tests/test_public_surface.py tests/test_no_local_paths.py` | 10 passed |
| targeted flake8 over 16 changed Python source files | pass, no output |
| targeted mypy over the same 16 files | success, no issues |
| `python scripts/static_quality.py check` with shell default Python 3.13.3 | environment failure: flake8 package metadata absent |
| `/opt/anaconda3/bin/python scripts/static_quality.py check` | pass: 381 baselined findings, 359 active and 22 vendored/generated |
| `/opt/anaconda3/bin/python -m pytest -q` | 2149 passed, 50 skipped |
| `git diff --check` | pass |

The static baseline changed only by removing 18 resolved findings: 12 contract,
3 correctness, and 3 hygiene findings from Lane D-modified qita/evaluate files.
It added no exception and no new finding.

## 15. Known gaps

- Engine registration/configuration is not wired because core/engine contracts
  are outside the lease.
- Exact A/B/C runtime receipts and their producer fixtures are not merged.
- Candidate schema migration beyond the frozen-trace adapter is not frozen.
- qita mutation commands require a runtime-owned client API before enablement.
- No representative licensed benchmark supports compression/index/performance
  selection.

## 16. Commit intent

The implementation, conformance fixtures, plan, and this evidence are delivered
as one coherent Lane D commit. The final handoff records its exact commit ID.
No push or integration-branch mutation is performed.

## 17. Final cleanliness contract

Before handoff, rerun `git diff --check`, targeted qita parity/full tests after
the compatibility fix, verify the branch/base, commit, and require an empty
`git status --short`. The final handoff reports the resulting clean `HEAD`.
