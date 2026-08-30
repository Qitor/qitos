# S1-D lineage readiness and handoff evidence

Status: all G1/G2 contracts exact-receipt qualified; runtime/Trajectory typed blocked
Source branch: `feat/campaign-absorption`
Source commit: `c1efb0f4adde3e673bf181af5b1760c19a451ae2`
Lane branch: `codex/v4-s1-d-lineage-intake`

## Outcome

S1-D defines one future `Trajectory` target, extends the writer/reader census to
31 exact source rows, publishes future qita session/work DX, and implements a
strict A/B/C receipt/readiness inventory. It adds no writer, store, qita runtime,
producer schema, compression/index choice, or performance claim.

The current state remains intentionally `schema_not_ready`, but contract intake
is complete: the two accepted G1 foundations and all 17 G2 S1 requirements are
exact-receipt qualified. No receipt finding remains. Independent runtime,
writer/store, publication, qita, and measurement blockers remain.

The G2 producer bundles are:

| Owner | Producer commit | Bundle / evidence | Version | Qualified requirement count |
|---|---|---|---|---:|
| A | `58864253a169d1bac5749ad2b2de5de6872c0da2` | `tests/fixtures/session/fixture-manifest.json`; adjacent qualification evidence | `qitos.session_contract_bundle/v2` | 5 |
| C | `bd7fca95e9ba9acfbbd9e8d0655a14ece066bcb6` | `tests/fixtures/work_graph/g2-contract-manifest.json`; adjacent qualification evidence | `qitos.work_effect_contract_bundle/v2` | 6 |
| B | `3cc29bea2bd311a2343862fd0b4f32636524bbb6` | `tests/fixtures/conversation/request_contracts.json`; adjacent qualification evidence | `qitos.request_contract_bundle/v1` | 6 |

G2 validation observes 19 qualified contract IDs, zero receipt findings, and
the unchanged normal exit policy: exit 2 with `schema_not_ready`, no
measurements, and no claims. The full integrated suite is `2010 passed, 50
skipped`.

## Canonical, derived, and compatibility decision

- Canonical target: one proposed `Trajectory` composed of ordered
  `TrajectoryRecord` facts plus explicit `Lineage`. The schema is unfrozen and
  no canonical writer exists.
- Derived: tracing spans/processors, renderer JSONL, indexes/caches, and external
  exports. They are rebuildable and declare privacy/loss.
- Compatibility: current `manifest.json`, `events.jsonl`, and `steps.jsonl`
  remain readable through a bounded compatibility codec/reader. This adapter
  does not become another architecture.
- Persistence: checkpoint is session continuation truth and is referenced by
  identity; it is not copied into a trajectory store.

Detailed decision and qita flow:
[`s1_d_trajectory_adr.md`](s1_d_trajectory_adr.md). Exact sources:
[`s1_d_source_census.md`](s1_d_source_census.md).

## Historical pre-G2 readiness inventory

The table below records the S1 intake state before G2. It is retained for
provenance; `scripts/benchmark_trajectory_store.py` and the receipt set are the
current executable inventory.

`—` means the semantic owner has not published an accepted fact. It is not a
placeholder that Lane D may fill.

| Contract ID | Owner | Producer commit | Fixture / evidence | Schema / digests | Authority | Compatibility | Exact blocker and remediation |
|---|---|---|---|---|---|---|---|
| `lane_b.exchange_log_fixture_version` | B | `2e46fc8e0228af42d6eaeaa6a665ffe5998c0bd5` | `tests/fixtures/conversation/v3/semantic_fixtures.json`; adjacent qualification evidence | `qitos.exchange_log.v2`; fixture `927e0ace…`; evidence `86d52fd2…` | `qitos.g1.integration_owner/v1` | qualified foundation | Qualified only as G1 foundation; does not clear RequestView or G2 behavior |
| `lane_c.canonical_tool_result_fixture_version` | C | `9a0c5ed5d6c1c959ff277d3888f54c927be3e183` | `tests/fixtures/tool_results/v1/contract_hardening.json`; adjacent qualification evidence | `qitos.tool_result/v1`; fixture `b7f4dc6d…`; evidence `96b0e641…` | `qitos.g1.integration_owner/v1` | qualified foundation | Qualified only as G1 foundation; does not clear effect/work-graph behavior |
| `lane_a.identity_vocabulary` | A | — | — | — | `qitos.s1.integration_owner/v1` | not established | `producer_version_unestablished`; publish distinct identity bindings and reviewed evidence |
| `lane_a.session_lifecycle` | A | — | — | — | same | not established | `producer_version_unestablished`; publish lifecycle, transitions, and typed invalid cases |
| `lane_a.session_snapshot` | A | — | — | — | same | not established | `producer_version_unestablished`; publish immutable snapshot and explicit lineage evidence |
| `lane_a.session_head_generation` | A | — | — | — | same | not established | `producer_version_unestablished`; publish authoritative head, generation conflict, and stale rejection facts |
| `lane_a.resolver_reference` | A | — | — | — | same | not established | `producer_version_unestablished`; publish resolver reference/mismatch evidence with no live secret/object |
| `lane_b.request_view` | B | — | — | — | same | not established | `producer_version_unestablished`; publish selection, budget, identity, and loss facts |
| `lane_b.provider_codec` | B | — | — | — | same | not established | `producer_version_unestablished`; publish transport/API-mode capabilities and typed failures |
| `lane_b.codec_report` | B | — | — | — | same | not established | `producer_version_unestablished`; publish input/output identity, fidelity, and loss |
| `lane_b.steering` | B | — | — | — | same | not established | `producer_version_unestablished`; publish queued/applied-once lineage at an explicit safe boundary |
| `lane_b.provider_continuation` | B | — | — | — | same | not established | `producer_version_unestablished`; publish opaque retention, display prohibition, transfer, and loss policy |
| `lane_b.context_artifact_snapshot` | B | — | — | — | same | not established | `producer_version_unestablished`; publish context/compaction/ArtifactRef references and corrupt/missing behavior |
| `lane_c.effect_recovery` | C | — | — | — | same | not established | `producer_version_unestablished`; publish attempt/effect/idempotency/reconciliation/outcome-unknown facts |
| `lane_c.safe_boundary_matrix` | C | — | — | — | same | not established | `producer_version_unestablished`; publish safe/unsafe/quiescence facts for every owned resource class |
| `lane_c.work_graph` | C | — | — | — | same | not established | `producer_version_unestablished`; publish explicit work, parent/child, fan-out, join, and outcome references |
| `lane_c.ownership_generation` | C | — | — | — | same | not established | `producer_version_unestablished`; publish one owner/generation, transfer, and stale-owner rejection facts |
| `lane_c.operation_semantics` | C | — | — | — | same | not established | `producer_version_unestablished`; publish distinct handoff/delegate/fan-out/spawn/fork/steer semantics |
| `lane_c.late_stale_result_behavior` | C | — | — | — | same | not established | `producer_version_unestablished`; publish late/stale rejection, uncertainty, and no-head-change proof |

The executable inventory contains full, non-abbreviated digests for qualified
foundations and `null` for unestablished producer facts. The report exposes
owner, required artifact, short message, remediation, compatibility state, and
current qualification state for every contract.

## Receipt validation behavior

The validator covers:

- missing, unknown, duplicate, malformed, and caller-self-authorized receipts;
- producer version unestablished and unsupported receipt schema;
- stale producer, wrong expected commit, nonexistent commit, and source commit
  that does not contain the exact fixture/evidence paths;
- wrong path, wrong digest, committed digest mismatch, and current working bytes
  differing from committed bytes;
- unapproved authority and producer-owned evidence mismatch;
- conflicting identity bindings, missing lineage, and inferred parent edge;
- exact qualified receipt; one receipt clearing only one owned blocker;
- all exact receipts while runtime behavior remains `consumer_not_qualified`.

Receipt qualification is derived. A receipt cannot contain `qualified=true`.
The accepted authority, version, producer commit, paths, and digests are pinned
by the inventory. Both current and committed bytes are verified. A producer
fixture present in the working tree does not qualify itself.

The stable readiness fixture root is `tests/fixtures/readiness/`. Scenario files
contain behavior labels only. Tests create temporary Git commits to obtain real
test commit IDs and digests; no A/B/C producer identity is fabricated.

## Privacy and portability

- Public output never includes an inspected fixture root, repository-external
  absolute path, home expansion, file URI, local endpoint, secret/token/header/
  cookie value, raw provider payload, or unauthorized campaign payload.
- Mapping-key locations are emitted as safe positional paths. Unknown/rejected
  keys and values are never used as finding subjects or field names.
- `raw_private` and `redacted_public` remain separate planned views. Public
  qualification requires a named policy, deterministic transform receipt,
  zero-finding scans, loss report, and payload inventory.
- Hashing verifies exact bytes. Sanitization rewrites/removes unsafe content.
  One does not substitute for the other.
- Fixture-set payload digest is deterministic over sorted logical path, digest,
  and byte-count tuples; tests recompute it from actual payload bytes.

## Readiness output

The report is deterministic JSON with `result_type` and independent
`schema_version`. It retains low-cardinality `status`, `reason_code`, blocker
codes/categories, sorted contract IDs, and empty `measurements`/`claims`.

Every blocker includes:

- `code` and `owner`;
- human `short_message` and actionable `remediation`;
- `required_artifact`;
- `current_qualification_state`.

Normal execution exits 2. Dry-run exits 0 but still reports
`schema_not_ready`. Global blockers keep these honest boundaries explicit:
no frozen schema, no canonical writer, no store benchmark, no runtime consumer
qualification, no publication/compression/deduplication/performance claim, and
no qita migration qualification.

## A/B/C producer status and consumer requests

Observed from the S1-D worktree:

- Lane A branch still pointed to the dispatch baseline and had no accepted
  producer commit.
- Lane B branch still pointed to the dispatch baseline and had no accepted
  producer commit.
- Lane C branch still pointed to the dispatch baseline; an uncommitted plan draft
  is not a producer fact and is ignored.

Requests to Lane A:

1. Publish the identity vocabulary, lifecycle, SessionSnapshot envelope,
   head/generation conflict facts, and resolver-reference contract.
2. Evidence must name distinct identity bindings and explicit pause/restore/fork
   lineage, last safe snapshot, recoverability, and typed failure states.

Requests to Lane B:

1. Publish RequestView, provider codec/capabilities, CodecReport, queued steering,
   opaque continuation, and context/compaction/artifact snapshot components.
2. Evidence must separate private opaque bytes from public projection and state
   every loss/missing-reference behavior.

Requests to Lane C:

1. Publish effect/recovery, safe-boundary matrix, WorkGraph, ownership
   generation, operation semantics, and late/stale behavior.
2. Evidence must contain explicit producer edges; no run-name parentage. It must
   prove rejected late/stale results do not mutate the authoritative head.

After integration-owner acceptance in A, C, B order, D may mechanically refresh
only the matching requirement bindings in a separate commit. One accepted
producer does not imply G2 readiness.

## Compatibility retirement

Current trace/qita compatibility remains unchanged. Retirement prerequisites are
listed in the ADR removal ledger and include reader/replay/export parity,
runtime-owned fork, external-consumer evidence, privacy/loss qualification, an
announced release window, and archive policy. Repository grep alone is not
removal evidence.

## Unsupported claims and known gaps

- No Trajectory runtime, writer, store, reader migration, exporter, or qita
  session/graph command is implemented.
- No schema is frozen and no store technology, compression, or index is chosen.
- No representative store benchmark ran; there are no measurements or claims.
- Session/work lineage, safe pause/restore/fork, ownership generation, joins,
  steering, effects, and late-result behavior await producer/runtime evidence.
- Current trace compatibility remains asymmetric and lossy; those gaps are now
  visible census facts rather than inferred lineage.

## Validation evidence

All required targeted gates executed without a skip and passed:

- Lane D readiness, both fixture schemas, D01-D31 exact-source checks, tracing,
  qita, architecture boundaries, public surface, and no-local-path:
  `162 passed`.
- Stable flake8: exit 0.
- Stable mypy: `Success: no issues found in 77 source files`, exit 0.
- Static quality ratchet: `399 findings baselined (377 active, 22
  vendored/generated)`, exit 0.
- Complete suite: `1899 passed`, exit 0. The repository's 50 conditionally
  skipped tests are reported for transparency and are not used as evidence for
  any required Lane D gate.
- Dry-run without receipts: exit 0, `schema_not_ready`, zero qualified
  contracts, empty measurements/claims.
- Dry-run with available G1 receipts: exit 0, `schema_not_ready`, exactly the
  ExchangeLog and ToolResult foundation contracts qualified, empty
  measurements/claims.
- Normal execution with available G1 receipts: typed exit 2,
  `TRAJECTORY_SCHEMA_NOT_READY`, empty measurements/claims.
- `git diff --check`: exit 0.

## Historical S1 fixture and evidence digests

These values identify the original S1 handoff. Current G2 receipts carry the
authoritative non-abbreviated producer and readiness digests.

SHA-256 values are over committed logical files; they identify bytes and do not
claim sanitization:

| Logical file | SHA-256 |
|---|---|
| `tests/fixtures/readiness/contract-qualification-receipts.json` | `4cdbfe1f7917e1921f904169dd3f2184cb1332aab70a524017e822c7a1366028` |
| `tests/fixtures/readiness/receipt-set.schema.json` | `610c7bae191a8d7dfc9e37f6f17b123621ad188616bfd13414d823d712ba1a0b` |
| `tests/fixtures/readiness/scenarios.json` | `01d1c4481ffc3ec50923691fccf133e3d6564529c58c8d1c4bed44a0c9ea7299` |
| `tests/fixtures/readiness/scenario.schema.json` | `36d9357aeec9d1b31b390782053e6f5d2b47981ca841d224313bf6c4203eb0fc` |
| `docs/internal/plans/s1_d_source_census.md` | `c12e8404d1674959a42b6137e6ba0558e36c22c8acb1572c825b52a69a26695c` |
| `docs/internal/plans/s1_d_trajectory_adr.md` | `9e32c7c06c622f9d7e5beeab361ee9566a0afb790e5b13a20763eb31646d3043` |
| `docs/internal/plans/assets/s1_d_trajectory_architecture.drawio` | `2c84360bd6ef604acc9d486cff93cc3f2b5d8b21b30b51d35e30245b48ff7064` |

## Evidence identity

The reviewable implementation commits preceding this evidence are:

1. `53956b6` — source census and plan;
2. `6c72696` — single Trajectory target, qita UX, and editable diagram;
3. `cd6becf` — strict G2 readiness inventory;
4. `50eca95` — receipt/privacy/portability fixtures and tests.

The exact final evidence commit and clean branch HEAD are reported by the
handoff after committing this document, avoiding a self-referential hash.
