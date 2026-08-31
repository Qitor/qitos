# Task 05 — trajectory store v2 and observability migration

Status: S3 deterministic lineage qualified; schema/publication remains blocked
on live execution evidence and the S4 rollout review
Depends on: Task 02 exchanges; Task 04 artifacts; Tasks 12–13 lineage
Milestone: final v4 data-plane migration
Risk: high — frozen v1 compatibility, replay, and research data fidelity

---

## G3 qualification split (2026-08-31)

Lane D now consumes explicit Session lifecycle commits and Engine runtime facts
through the one extension-facing `EventSink` seam. Internal adapters project
session/pause/restore, request/response/reasoning/continuation/loss, parallel
batch/slot/effect/artifact, budget/context, stop/error, and exact lineage fields
into the candidate `TrajectoryRecord` vocabulary without deriving identity from
directory or run names. Required sink failure blocks; optional sink failure and
flush/backpressure/durability remain observable reports.

Exact-source receipts qualify the twelve S2 runtime scenarios and report
`s2_runtime_ready=true`. Independently,
`trajectory_schema/publication_ready=false`: the candidate record/store/reader/
exporter types are absent from `qitos.tracing.__all__`, the candidate writer is
off by default, qita's default is still frozen trace-v1 compatibility, and no
schema-freeze, publication, compression, indexing, deduplication, or performance
claim is made. G4 durable multi-agent lineage and publication evidence remain
prerequisites.

The S3 convergence candidate does not promote this plane. Lane D consumes exact work-graph
facts and add read-only inspection only after real A/B/C producers exist; it may
not freeze the schema, switch the writer/store/reader defaults, or make qita a
mutation authority. Those rollout decisions remain S4 work after G4.

The deterministic G4 candidate now proves clean-process work/session/ownership/
join lineage and read-only qita graph/timeline inspection across twenty
independent SQLite rounds. That evidence qualifies the runtime input to this
task, but it does not freeze the candidate schema, enable its writer, change the
qita default from frozen trace-v1, or authorize publication. Three live-model
profiles are registered through external credential references, but no bounded
trajectory or agent execution receipt exists yet. Qualification is therefore
`profiles_configured_execution_pending`.

## 1. Goal

Create one lossless, space-efficient QitOS trajectory source for replay,
debugging, and dataset production while preserving the frozen `qitos/trace` v1
contract during migration. External ecosystem formats are versioned views of the
canonical data.

## 2. Migration rule

`qitos/trace` v1 (`manifest.json`, `events.jsonl`, `steps.jsonl`) remains readable
and supported throughout v4. `qitos/tracing` spans and renderer JSONL are current
separate planes; Task 05 must inventory them before consolidation.

The migration order is:

1. define v2 schema and lossless reader/writer;
2. add v1-to-v2 adapter and qita dual-read;
3. optionally dual-write representative runs;
4. prove replay/export/size parity;
5. select v2 as the default for new runs;
6. discuss v1 write deprecation in a later release.

No existing reader is pointed at a new layout without an adapter.

### D1 / D1-R evidence status (2026-08-29)

The exact-source producer/writer/reader census, canonical-versus-derived
decisions, fixture source manifests, privacy gates, and schema-neutral benchmark
specification are recorded in
`docs/internal/plans/lane_d_data_convergence.md`.

D1-R turns the source manifests into a strict versioned contract with an
executable stdlib validator and a matching repository schema. It adds typed
publication checks for license, deterministic transformation, privacy and loss
policy, secret/PII/path/artifact scans, and payload inventory digests. It also
uses a portable fixture-set identity, never serializes the local fixture root,
and rejects host-specific evidence without echoing inspected values.

D1 selected one independent 200-step campaign source for scale and one
repository-owned deterministic native-tool agent source for call/result shape.
Only provenance/sanitization manifests are committed: the campaign payload is
blocked on redistribution authorization and secret/path sanitization, while the
unrelated payload waits for versioned Lane B/C fixtures. The benchmark scaffold
therefore emits a typed `TRAJECTORY_SCHEMA_NOT_READY` result with no measurements
or compression claims. Contract readiness is now reported per stable Lane B/C
contract ID from caller-supplied version/digest/fixture qualification receipts;
missing fixture files do not become implicit qualifications, and the repository
contains no fabricated passing receipt.

Still blocked on Lane B: versioned ExchangeLog, RequestView, CodecReport,
provider-continuation opaque fields, ArtifactRef, and compaction report. Still
blocked on Lane C: versioned canonical tool outcome, timeout/cancellation and
durability receipts, hook failure fields, and trace-safe redaction. Trajectory
v2 schema is not frozen.

## 3. Canonical data model

The v2 store contains:

- run metadata and versioned configuration references;
- distinct session, run, work-item, checkpoint, agent, exchange, and tool-call
  identities plus parent/fork/restore lineage;
- ordered lifecycle/runtime events;
- Task 02 exchange transactions and provider continuation attachments;
- step/phase/run correlation IDs;
- canonical Task 03 tool outcomes;
- Task 04 content-addressed artifacts;
- compaction and codec reports;
- pause/resume, ownership-transfer, child-work, join, cancellation, durability,
  effect-uncertainty, and trace-completeness receipts;
- schema version, writer version, integrity hashes, and privacy policy.

Large repeated payloads are stored once by digest. Canonical records reference
them. A SQLite/search index, if added, is derived and rebuildable; it is never
the canonical truth.

## 4. Privacy and fidelity

Private raw capture and public/redacted export are separate policies.

- Ingest-time destruction is opt-in because it prevents exact replay.
- At-rest encryption or raw-data prohibition can be selected for sensitive runs.
- Default public/qita/export views apply `safe_projection` and secret redaction.
- Provider-encrypted reasoning payloads remain opaque and are never displayed.
- Every exporter emits a loss report and privacy-policy identifier.

## 5. Versioned exporters

Initial exporter IDs:

- `qitos_canonical_v2` — exact round-trip;
- `openai_chat_v1` — normalized chat/tool messages;
- `openai_responses_items_v1` — heterogeneous Responses items;
- `ms_swift_agent_v1` — documented ms-swift role/tool convention;
- `hermes_sharegpt_v1` — documented Hermes normalization convention.

Only canonical/native formats promise exact re-import. Lossy exporters declare
which invariants survive: user/assistant text, call names/arguments, call-result
correlation, reasoning summaries, multimodal refs, timestamps, or metadata.

## 6. Compression and size measurement

First commit a benchmark that compares:

- current v1 bytes;
- naive repeated JSON bytes;
- v2 references with no compression;
- optional gzip/zstd variants when dependencies are available.

The benchmark uses at least one long campaign run and one unrelated agent run.
Adopt zstd only if measured benefit justifies the optional compiled dependency.
The format records the actual compression algorithm and supports a safe fallback.

## 7. qita and render migration

qita first gains a storage-reader interface and v1/v2 implementations. UI or
signal generalization follows only after data parity.

- domain-specific signal extractors remain in the owning agent package;
- qita accepts typed, vocabulary-free signal providers;
- Engine emits generic diagnostic events instead of returning render types from
  `AgentModule` or core;
- renderer extensions live in render/qita, avoiding core-to-render coupling;
- truncation/detail levels are named knobs with conservative defaults.
- session inspection and work-graph navigation consume explicit Task 12/13
  records; they never infer parentage from run-ID suffixes;
- pause/resume/fork commands are thin clients of Task 12 runtime semantics, not
  qita-owned execution implementations.

Task 05 does not rewrite the whole qita CLI in the same PR as the store.

## 8. Work packages

### 05A — schema, benchmark, and decision record

- Inventory all current event/artifact paths and readers. **D1 census complete;
  D1-R link/symbol checks guard D01–D16 against drift.**
- Prepare v2 schemas and privacy modes with fixtures, but freeze them only after
  Task 12 session lineage and Task 13 work-graph receipts are reviewed.
- Commit the storage-size benchmark before choosing compression/index features.
  **Strict readiness scaffold complete; measurements wait for sanitized,
  contract-qualified fixtures.**

05A is not complete: its schema freeze, representative fixtures, benchmark
measurements, and decision record remain open.

G1 D-R1 verifies only the accepted B/C contract handoffs. Receipts bind contract
and schema IDs, exact producer commits, committed fixture/evidence paths and
hashes, and a reviewed authority; callers cannot self-declare qualification.
The executable manifest validator and the published JSON Schema share an
accepted/rejected parity corpus. These readiness receipts do not qualify the two
trajectory payload manifests, produce measurements or claims, complete 05A, or
freeze trajectory v2.

G1-R3 refreshed only the C receipt after accepting ToolResult producer
`d50f41fb3b8190a953f9f37f278bf0b197af286b`; receipt commit
`72d5d11bd924466aeff8282a5b0aa5ef8341de9e` verifies the committed fixture and
evidence bytes while retaining the exact B producer binding. Exact-receipt
readiness still qualifies only B/C, reports `schema_not_ready`, emits no
measurements or claims, and leaves trajectory v2 unfrozen.

G1-R4 refreshes that C binding again after forced-secret scalar qualification.
D receipt `e41eb6ea68375b1064b30044e66ae58bcba67c67` accepts only producer
`9a0c5ed5d6c1c959ff277d3888f54c927be3e183` and its committed fixture/evidence
digests; the prior R3 receipt is explicitly rejected. Exact-receipt readiness
still has nine contract blockers, qualifies only B/C and zero publications,
reports `schema_not_ready`, emits no measurements or claims, and keeps
trajectory v2 unfrozen. This is not 05A implementation or schema freeze.

### 05B — store, artifacts, and v1 bridge

- Implement atomic writer/reader and integrity validation.
- Reuse Task 04 ArtifactStore rather than creating a trace-only blob store.
- Add v1 import and optional dual-write parity fixtures.

### 05C — exporters and loss reports

- Implement canonical and OpenAI exporters first.
- Add ms-swift and Hermes adapters from their documented conventions.
- Add exact canonical re-import and invariant-based lossy re-import tests.

### 05D — qita dual-read

- Introduce the reader interface behind board/replay/export.
- Run existing qita tests against both v1 and v2 fixtures.
- Preserve URLs/CLI output unless a separately documented migration is needed.

### 05E — observability extensions and default rollout

- Add generic signal/diagnostic extension seams outside core.
- Benchmark query and render behavior.
- Make v2 the default only after parity, migration docs, and release review.

## 9. Acceptance criteria

- [ ] Canonical v2 write/read/re-import preserves all declared exchange, event,
  outcome, artifact, and correlation fields.
- [ ] Existing v1 fixtures remain readable by qita and replay.
- [ ] Dual-write/import parity is demonstrated on representative runs.
- [ ] Every external exporter has a version and machine-readable loss report.
- [ ] Raw private data and redacted export views are tested separately.
- [ ] Integrity failures and missing blobs produce typed diagnostics.
- [ ] Size claims come from the committed benchmark and include both consumers.
- [ ] qita board/replay/export tests run against v1 and v2.
- [ ] No domain vocabulary or render dependency enters core/engine.
- [ ] Clean-process pause/resume and partial multi-agent recovery retain exact
      lineage and can be navigated without run-name conventions.

## 10. Verification

```bash
pytest -q tests/trace tests/tracing
pytest -q tests/qita tests/test_qita_cli.py
python scripts/benchmark_trajectory_store.py --fixture tests/fixtures/trajectories
pytest -q
flake8 qitos/core qitos/engine qitos/trace qitos/tracing qitos/qita qitos/render
mypy qitos/core qitos/engine qitos/trace qitos/tracing qitos/qita qitos/render
```

If qita/render are not yet fully typed, the implementing plan must first state
and mechanically enforce a shrinking baseline; it may not silently omit them.

## 11. Stop-and-escalate decisions

Stop for review before:

- changing or deleting the v1 on-disk contract;
- redacting canonical raw data irreversibly by default;
- adding SQLite as canonical state;
- requiring zstd without benchmark and fallback evidence;
- claiming exact round-trip for a lossy external format;
- coupling `qitos.core` or `qitos.engine` to qita/render types.
- freezing v2 while session/run/work-item or ownership-transfer lineage is still
  represented only by metadata conventions.
