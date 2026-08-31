# S3 Lane D work-graph observability

Status: in progress; independent D surfaces authorized, runtime qualification waiting on A/B/C
Updated: 2026-08-31
Baseline: `851f7902f15da670e72f4c04d7453cf37201aee7`
Branch: `codex/v4-s3-d-graph-observability`
Worktree: sibling Lane D worktree (the host-specific absolute path is intentionally not persisted)

## Scope and stop gates

Lane D owns read-only work-graph observability, candidate-Trajectory adapters,
privacy projection, qita inspection, evaluator-facing read models, qualification
artifacts, and offline framework consumers. It does not own scheduler behavior,
WorkGraph mutation semantics, Session fork, context/authority transfer, the
Engine constructor, aggregate exports, trace-v1 writers, or rollout defaults.

The candidate Trajectory remains unfrozen and off by default. Frozen trace-v1
remains qita's default reader. Missing A/B/C executable facts produce
`waiting_on_lane_a_b_c`, no claims, no measurements, and a typed non-zero normal
qualification exit. A dry run may exit zero while retaining the blocked status.

## D01-D16 exact-source census

The full historical producer-to-consumer census remains in
`lane_d_data_convergence.md`. This S3 delta rechecks each exact source at the
fixed baseline and records the intended S3 treatment.

| ID | Exact source | Authority / S3 treatment |
|---|---|---|
| D01 | `qitos/engine/states.py::RuntimeEvent`; `qitos/engine/_trace_runtime.py::_TraceRuntime.emit` | Canonical in-memory runtime fact; adapt explicit fields only. |
| D02 | `qitos/engine/states.py::StepRecord`; `_TraceRuntime.finalize_step` | Derived aggregate; never ownership truth. |
| D03 | `qitos/trace/writer.py::TraceWriter`; `qitos/trace/schema.py::TraceSchemaValidator` | Frozen compatibility writer; unchanged. |
| D04 | `qitos/trace/events.py::{TraceEvent,TraceStep}` and writer adapters | Compatibility records; report missing lineage as loss. |
| D05 | `qitos/tracing/models.py::{Span,Trace}` and processors | Derived span plane; no promotion. |
| D06 | `qitos/tracing/legacy_processor.py::LegacyTraceWriterProcessor` | Lossy compatibility bridge; unchanged. |
| D07 | `qitos/render/events.py::RenderEvent` and render hooks | Derived presentation plane. |
| D08 | `qitos/qita/_cli_app.py`, `qitos/qita/reader.py` | Read-only client; add one budgeted inspection command family. |
| D09 | qita fork endpoint | Runtime-owned typed block remains; no copy-fork. |
| D10 | checkpoint v2 Session head/snapshot stores | Durability reference, not trajectory truth. |
| D11 | recipe/benchmark result writers | Edge consumer; no S3 schema authority. |
| D12 | `qitos/evaluate/base.py` reader context | Independent declarative consumer of the read model. |
| D13 | leaderboard/HF run transport | Distribution edge; no public raw projection added. |
| D14 | `ModelResponse` / model-runtime projections | Consume B facts when exact source exists; do not copy. |
| D15 | `ToolResult` / action-runtime outcomes | Consume C facts when exact source exists; do not simulate readiness. |
| D16 | compact-history/context diagnostics | Derived diagnostic awaiting exact B transfer/loss facts. |

No identity relationship is derived from a run name, directory name, ID suffix,
tool name, or message body.

## Reader/writer matrix

| Plane | Writer authority | Reader | Role | Default |
|---|---|---|---|---|
| RuntimeEvent | Engine/runtime producer | structural candidate adapter | canonical runtime fact | runtime-owned |
| candidate Trajectory | optional EventSink/store | `StoreTrajectoryReader` plus graph read model | candidate persistent plane | writer off; reader non-default |
| tracing spans/render/index | tracing/render processors | existing processors/views | derived | opt-in |
| trace v1 | `TraceWriter` | `TraceCompatibilityReader` | frozen compatibility | qita default |
| qita | none | replaceable structural reader | read-only client | trace-v1 adapter |

The graph reader consumes the existing `TrajectoryReader` protocol. Candidate
store, trace compatibility, and a third-party-style fake therefore traverse the
same read-model builder. Compatibility input reports unavailable session,
work-item, ownership, join, and restore facts as explicit loss.

## Candidate event vocabulary

Work-graph records use the one `TrajectoryRecord` architecture with explicit
session/run/work/attempt identity, parent/source edge, owner generation,
operation identity, timestamp/sequence, producer authority, integrity digest,
provenance, and loss/uncertainty. Event names cover session create/restore/fork,
run start/termination, work declaration/attempt/owner assignment and transfer,
delegate/spawn/fan-out, child lifecycle, cancellation, detachment/supervision,
join progress/closure, accepted/discarded/stale/unknown outcomes, budget and
capability allocation, context/continuation transfer, artifacts, process-loss
recovery, generation conflict, and privacy/loss projection.

## Unified read model

The store-independent model contains session summary, authoritative head, work
items and explicit edges, attempts, ownership history, fan-out groups, joins,
cancellation/detachment, terminal and unknown outcomes, restore generations,
timeline entries, and completeness/loss. Selectors are explicitly typed as
session, run, work item, or attempt; ambiguous strings are never decoded.

Conformance covers:

1. `MemoryTrajectoryStore` through `StoreTrajectoryReader`;
2. frozen trace-v1 through `TraceCompatibilityReader`, with truthful loss; and
3. an independent fixture implementation of `TrajectoryReader`.

## Privacy boundary

Canonical raw/private input is never overwritten. Public and safe-diagnostic
projections operate on isolated data and emit non-echoing, low-cardinality
findings for secret/token/API-key/JWT/PEM material, authorization/header/cookie,
raw provider payload, POSIX/Windows/UNC/file/home paths, local/private endpoints,
credential or secret references, artifact bodies, unsupported/cyclic/nested or
oversized values. Hashing is integrity, not sanitization. Host paths never serve
as identities. HTTP assets remain run-scoped; new inspection output exposes no
raw provider body or storage path.

## qita command budget

The dispatch surface has three top-level commands (`board`, `replay`, `export`).
S3 adds exactly one top-level read-only family:

```text
qita inspect session <id>
qita inspect graph <session-or-work-id> --kind session|work
qita inspect timeline <session-or-work-id> --kind session|work
qita inspect item <work-or-attempt-id> --kind work|attempt
```

This provides the requested UX without four unrelated top-level additions.
`inspect` never calls handoff/delegate/spawn/join/fork/resume. Candidate-store
absence and unsupported compatibility queries return typed blocked JSON.

## A/B/C readiness inventory

The machine-readable source is
`tests/fixtures/s3/lane_d/readiness-inventory.json`. Every dependency records
contract ID, owner lane, exact producer commit, path, digest, schema identifier,
authority, compatibility, executable test binding, qualification state, and
blocker/remediation. At plan creation the three local producer branches all
point to the dispatch baseline and no remote producer refs/manifests exist, so
all remain unqualified. Unknown commit/path/digest is a blocker, never a
wildcard. One receipt cannot discharge multiple contract rows.

Finalization performs read-only ref and committed-byte checks for:

- `codex/v4-s3-a-session-fork`;
- `codex/v4-s3-b-transfer-authority`; and
- `codex/v4-s3-c-durable-work-runtime`.

Only exact producer types, committed fixtures, and executable scenario evidence
can change a row to qualified.

## Independent consumer designs

### Consumer 1: bounded research fan-out

User code declares a parent and bounded child tasks with the existing
Session/WorkGraph contracts, records deterministic child outcomes, declares an
`all_successful` join, and inspects graph/timeline output. Research roles remain
user data; no scheduler is copied and no model is called.

### Consumer 2: proposal/critique transfer

Unrelated user code declares proposal work, performs an explicit generation-
checked owner transfer to a reviewer, records an attempt/outcome, and inspects
ownership history and timeline. Roles and policy remain outside core/engine.

Both consumers use identical framework primitives and the same read model.

## Coding-agent acceptance example

A 50-100 line example (prompts/config excluded) exercises only public or
reviewed module-level APIs for AgentModule/Engine/Session run, pause, fresh
restore, delegate, join, and inspection. Until A/B/C runtime contracts are
present it exits with the typed `runtime_not_ready`/`waiting_on_lane_a_b_c`
result rather than pretending the durable workflow completed.

## Implementation and verification ledger

- [x] Fixed baseline, branch, worktree, and source rules verified.
- [x] Required architecture, Session, WorkGraph, trajectory, trace, qita,
  evaluate, tests, and S2 qualification sources inspected.
- [ ] Candidate work-graph event adapter and unified read model.
- [ ] Candidate/compatibility/third-party conformance tests.
- [ ] One-family qita read-only inspection UX and typed blocks.
- [ ] Privacy/portability regression corpus and non-echoing diagnostics.
- [ ] Exact-source readiness validator, script, inventory, and evidence output.
- [ ] Two independent offline consumers and coding-agent acceptance example.
- [ ] Targeted, S2, architecture/interface, static, lint/type, full pytest, and
  `git diff --check` validation.
- [ ] Read-only A/B/C finalization check, coherent commits, and clean worktree.

## Unsupported claims

No S3 completion, durable multi-agent readiness, distributed scheduling,
exactly-once external effects, hard cancellation, frozen Trajectory schema,
candidate default writer/reader, qita mutation authority, publication readiness,
compression/performance measurement, or release readiness is claimed here.
