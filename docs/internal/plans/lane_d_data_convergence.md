# Lane D data convergence

Status: D1 evidence package implemented and validated
Updated: 2026-08-29
Work package: Lane D / D1 — data-plane census, consumer ledger, and benchmark specification
Baseline: `fb75cd5902fedf50d5e67dd617e62cd981c3128f`
Branch: `codex/v4-lane-d-data-census`
Worktree: `/Users/morinop/Desktop/WhitzardOS-lane-d`

## Objective

Establish exact-source evidence for every current trajectory producer, writer,
reader, and public consumer; publish the public-surface/removal decision ledger;
select two independent representative trajectory fixture sources; and specify a
schema-neutral storage benchmark. D1 does not implement or freeze trajectory v2.

## Scope and stop gates

In scope:

- trace/runtime/tracing/render/qita/checkpoint/benchmark/evaluate/metric/hf
  producer-to-consumer call-chain evidence;
- correlation, privacy, duplication, lifecycle/failure, and test coverage;
- public-surface classification and removal decisions with explicit unknowns;
- fixture provenance/sanitization manifests and a typed schema-not-ready
  benchmark scaffold;
- explicit Lane B/C dependency requests.

Out of scope:

- changing the frozen trace v1 format or writer behavior;
- implementing or freezing trajectory v2;
- changing qita, Engine, provider/tool/context, checkpoint, privacy, benchmark,
  or recipe behavior;
- deleting, deprecating, or changing any public import;
- selecting SQLite as canonical storage, requiring zstd, or making compression
  claims before representative measurements exist.

Stop if a required B/C contract is absent. Record a dependency request instead
of copying or inferring its fields.

## File leases

Lease owner: Lane D / D1

File(s):

- `docs/internal/plans/lane_d_data_convergence.md`
- `docs/v4/05-trajectory-data-plane.md`
- `docs/v4/10-consolidation-and-surface-reduction.md`
- `docs/architecture/architecture-debt.md`
- `README.md`, `README.zh.md`, `CHANGELOG.md`

Semantic purpose: evidence/status only, plus user-visible notice that the D1
census and benchmark specification exist. No schema, runtime, CLI, import, or
release behavior changes.

Expected start/end package: D1 census through final validation and evidence
handoff.

Other lanes blocked or adapter supplied: no lane is blocked. Lane B/C contract
fields remain dependency requests and are not duplicated here. README,
CHANGELOG, and architecture-document edits must be rebased by the integration
owner if another lane changes the same sections.

No lease is requested for `qitos/trace/schema.py`, `qitos/trace/writer.py`,
`qitos/qita/_cli_app.py`, `qitos/core/__init__.py`, `qitos/__init__.py`,
`setup.py`, or `pyproject.toml`; D1 will not modify them.

## Work plan

1. Record source identity and verify a clean isolated worktree.
2. Trace concrete producer → serialization/writer → filesystem/store → reader
   → consumer chains and record symbols, schema/correlation/privacy/failure/tests.
3. Inventory root/module exports, commands, entry points, extras, registries,
   documentation/examples, shims, and named optional/deprecated surfaces.
4. Publish a removal decision ledger that distinguishes known consumers from
   unknown external usage; make no removal decision from repository grep alone.
5. Select one campaign-derived long trajectory and one unrelated agent source;
   record provenance, license, sanitization, portability, and coverage gaps.
6. Specify and scaffold `scripts/benchmark_trajectory_store.py` with a typed
   schema-not-ready result and no v2 record assumptions.
7. Update task/debt evidence, README/CHANGELOG, and explicit Lane B/C requests.
8. Run every required targeted/full/static check, review the complete diff, and
   commit in coherent evidence packages.

## Evidence artifacts

The completed plan will contain or link:

- exact-source data-plane census and canonical/derived/compatibility decisions;
- public-surface census and removal decision ledger;
- fixture source and sanitization manifests under
  `tests/fixtures/trajectories/`;
- benchmark specification and typed dry-run output;
- Lane B/C dependency request lists;
- exact validation results and final commit/status identity.

## Current status

- [x] Baseline, branch, worktree, and clean status verified.
- [x] Required architecture/task documents read.
- [x] Exact-source data-plane census complete.
- [x] Public-surface census and removal ledger complete.
- [x] Representative fixture manifests complete.
- [x] Benchmark specification/scaffold complete.
- [x] Documentation evidence/status synchronized.
- [x] Required verification complete.

## Explicit unsupported claims

- Trajectory v2 schema is not frozen.
- No v2 writer, store, reader, exporter, or qita adapter exists from this work.
- No compression, deduplication, read/write/replay, or query performance result
  is claimed until the versioned B/C contracts and sanitized fixtures exist.
- No public surface is unused or safe to remove merely because an internal
  caller was not found.

## Exact-source writer/reader census

The identifiers below join three tables. “Canonical” means canonical for the
current runtime or compatibility workflow, not a trajectory-v2 decision.

### Producers, storage, and consumers

| ID | File and symbol | Producer → writer/store → reader → consumer | Schema/version | Present role |
|---|---|---|---|---|
| D01 | `qitos/engine/states.py::RuntimeEvent`; `qitos/engine/_trace_runtime.py::_TraceRuntime.emit` | Engine phase helpers → in-memory `Engine.events` and current `StepRecord.phase_events`; then D04 and hooks | Dataclass, unversioned | Canonical runtime event in memory |
| D02 | `qitos/engine/states.py::StepRecord`; `_TraceRuntime.finalize_step` | Engine decide/act/reduce helpers → `Engine.records` → D04 and hook summaries → `EngineResult` | Dataclass, unversioned | Canonical runtime step in memory |
| D03 | `qitos/trace/writer.py::TraceWriter`, `qitos/trace/schema.py::TraceSchemaValidator` | recipe/demo/Engine assembly → `runs/{run_id}/manifest.json` → qita, replay, evaluate, leaderboard, HF | Frozen `v1` manifest | Canonical compatibility artifact |
| D04 | `qitos/trace/events.py::{TraceEvent,TraceStep}`; `qitos/trace/writer.py::{runtime_event_to_trace,runtime_step_to_trace,TraceWriter.write_event,TraceWriter.write_step}` | D01/D02 → recursive key-redacted `events.jsonl`/`steps.jsonl` → qita, replay, evaluate, HF | Frozen `v1` JSONL | Canonical compatibility artifact |
| D05 | `qitos/tracing/models.py::{SpanData,Span,Trace}`; `provider.py::TracingProvider` | opt-in instrumentation → `SynchronousMultiTraceProcessor` → JSON/JSONL, console, MLflow, W&B, or D06 | Tracing models, unversioned | Optional derived observability plane |
| D06 | `qitos/tracing/legacy_processor.py::LegacyTraceWriterProcessor` | D05 span → forced v1-like event → D03/D04 writer; no step write → v1 readers | Compatibility bridge, unversioned | Compatibility-only and lossy |
| D07 | `qitos/render/events.py::RenderEvent`; `qitos/render/_hooks_impl.py::RenderStreamHook._emit` | Engine hooks plus copied D01 events → in-memory render stream and optional `render_events.jsonl` → `ClaudeStyleHook`/TUI | Unversioned JSONL | Derived presentation plane |
| D08 | `qitos/qita/_cli_app.py::{_discover_runs,_load_run_payload,_build_replay_records,_cmd_board,_cmd_replay,_cmd_export}` | D03/D04 files → tolerant loaders/group-by-step → board, replay, JSON/HTML export, live SSE | v1 reader/view | Compatibility product consumer |
| D09 | `qitos/debug/replay.py::ReplaySession`; qita fork endpoint | D03/D04 files → strict replay session → step view/forked copied v1 artifacts | v1 reader/writer | Deprecated compatibility dependency used by qita |
| D10 | `qitos/checkpoint/checkpoint.py::{CheckpointData,CheckpointManager}`; `qitos/checkpoint/{store,memory_store,sqlite_store}.py`; Engine save/resume/fork helpers | Engine state plus, for legacy only, D01/D02 → JSON checkpoint or state-oriented v2 checkpoint stores → Engine resume/fork | Checkpoint schema v1/v2, not trajectory v2 | Durability plane, not trajectory truth |
| D11 | `qitos/recipes/benchmarks/_shared.py::build_example_specs`; GAIA/CyBench/Tau/CyberGym runners; `qitos/benchmark/common.py` | benchmark runner → D03/D04 plus benchmark results JSONL containing `trace_run_dir` → CLI/evaluation | trace v1 plus benchmark-specific result records | Recipe consumer/producer edge |
| D12 | `qitos/evaluate/base.py::{EvaluationContext,load_run_artifacts}`; `qitos/metric/base.py::MetricInput` | D03/D04 → tolerant evaluation context → rule/DSL/multi-agent evaluators; recipe-normalized result → metrics | v1 input, evaluator/metric contracts unversioned | Derived evaluation consumers |
| D13 | `qitos/leaderboard/store.py::submit_run_dir`; `qitos/hf/hub.py::{push_run,pull_run}` | D03 manifest → leaderboard SQLite pointer; D03/D04 and extra run files → HF upload/download → remote users | v1-oriented edge protocols | Distribution/registry consumers |
| D14 | `qitos/core/model_response.py::ModelResponse.to_summary_dict`; `qitos/engine/_model_runtime.py` | provider response/native items → summary in D02 plus raw/model-output D01 payload → D04/D07 | Lane B contract not yet versioned | Current duplicated projection; future B-owned input |
| D15 | `qitos/core/action.py::{ActionResult,ToolResult}`; `qitos/engine/_action_runtime.py`; `qitos/core/runtime_context.py` | action executor → rich `ActionResult` → lossy `ToolResult` reducer projection, D02 invocation/result fields and metadata artifacts → D04/D07 | Lane C outcome and B artifact contracts not yet versioned | Current runtime data awaiting owned contracts |
| D16 | `qitos/kit/history/compact_history.py`; Engine compaction emit path | history strategy → ad hoc compaction dict D01 payload → D04/D07 | No versioned `CodecReport` or compaction report | Derived diagnostic awaiting Lane B contract |

### Correlation and representation comparison

| ID | `run_id` | `step_id` | `phase` | Tool call/result correlation | Privacy/redaction | Raw/summary duplication |
|---|---|---|---|---|---|---|
| D01 | Injected into `payload`, not a field | Top-level and payload | Enum field and payload | Only payload-specific | No in-memory redaction | Can carry raw model output beside D02 summary |
| D02 | Absent | Top-level | Only inside `phase_events` | `action_id`, invocation metadata, native IDs indirectly through history | No in-memory redaction | `model_response`, actions, results, invocation and execution projections overlap |
| D03 | Manifest field and directory identity | Summary count only | Status/summary only | Tool manifest, not per-call join | Recursive key redaction on write | Repeats normalized config/spec metadata |
| D04 | Event top-level from writer; step has none | Event/step top-level | Event only; step has none | Action IDs exist but result correlation is not one normalized contract | Recursive exact-key redaction; unknown objects become `repr` | Events and steps repeat observation/model/action/result data |
| D05 | Uses `trace_id`, no common run ID | `StepSpanData.step_number` only | Span type implies phase | Tool span fields are not a shared outcome contract | Provider mode can replace selected fields with `__redacted__` | Span input/output can duplicate runtime payloads |
| D06 | Writer run ID versus payload `span.trace_id` can diverge | Forced to `0` | Span-type mapping | Not preserved as a normalized join | Inherits span mode then v1 writer redaction | Writes span export again as event payload |
| D07 | Absent | Top-level | Channel/event name; copied runtime phase can be nested | Display payload only | Same key-redactor at JSONL boundary | Deliberately repeats raw output, reasoning, actions, and results |
| D08 | Manifest/directory | Groups on event top-level and joins step | Event field | Heuristic replay records, not canonical outcome join | No second redaction | Replay/export combines full event with step projections |
| D09 | Manifest/directory | Event index/group | Event field | No additional normalization | No second redaction | Fork copies and mutates full v1 artifacts |
| D10 | Legacy checkpoint field; new store uses thread/checkpoint IDs | Legacy field/new `step` | None | Not a trajectory join | JSON serialization only | Legacy duplicates runtime records/events; new store persists state only |
| D11 | Trace manifest and result pointer | In trace only | In trace only | Benchmark-specific | Results writer uses key redaction; trace uses v1 redaction | Results point to traces rather than embedding them |
| D12 | Manifest | Reads event/step IDs | Reads event phase | Evaluator-specific | No extra projection policy | DSL/multi-agent consumers may load all duplicated records |
| D13 | Manifest/pointer/remote directory | Uploaded as-is | Uploaded as-is | Uploaded as-is | HF sanitizes selected manifest environment keys only; extra files are not projected | Upload includes v1 plus arbitrary extras |
| D14 | Inherited through D01 payload | Current step | DECIDE/model-output event | Native call IDs exist in native history/items, but `encrypted_content` is removed from summaries | Summary sanitizer removes opaque encrypted content; v1 key redaction later | Raw output event plus model-response step summary |
| D15 | Runtime context | Step and action IDs | ACT | Native result association uses action/call ID with index fallback; rich outcome becomes lossy `ToolResult` | Later v1/render key redaction only | `action_results`, `tool_invocations`, execution metadata, reducer projection overlap |
| D16 | D01 payload | D01 step | `COMPACT` or diagnostic payload stage | Not applicable | Later v1/render key redaction only | Before/after/count metadata can repeat context report facts |

### Failure behavior, tests, and v2 disposition

| ID | Lifecycle/failure behavior | Existing evidence tests | Planned v2 disposition | Semantic owner |
|---|---|---|---|---|
| D01 | Emission precedes hook dispatch; trace/hook failures are debug-logged and fail-open | `tests/test_engine_core_flow.py`, `tests/engine/`, `tests/test_engine_result_traces.py` | Adapt only after common correlation/lifecycle policy; preserve v1 emission | D runtime envelope; C failure receipt |
| D02 | Finalization writes v1 then hooks; failures are swallowed | engine tests | Lossless step view over owned B/C records, not a second truth | D envelope, B/C payloads |
| D03 | Append-only writes; final manifest validation; partial/crashed runs remain possible | `tests/test_config_security.py`, `tests/test_qita_cli.py`, reproducible-run tests | Keep v1 readable; v2 atomicity/integrity is future D work | D |
| D04 | Unknown values degrade to `repr`; validator checks required v1 fields, not all cross-record joins | trace/config/qita tests | Versioned v1 importer and parity fixtures, after schema freeze | D |
| D05 | Processor fan-out catches/logs exceptions; no durable receipt | `tests/tracing/`, MLflow/W&B processor tests | Either derived view/exporter or adapter; never a second canonical store | D with C failure semantics |
| D06 | Export errors can be silently ignored; step is always zero; no step records | `tests/tracing/test_legacy_processor.py` | Retire only after all consumers use an explicit adapter | D |
| D07 | Hook failure is fail-open; file append has no schema/version/atomicity receipt | render tests, recipe tests | Derived renderer view from canonical reader | D |
| D08 | Tolerates invalid JSONL as synthetic error objects; live tail skips incomplete/invalid lines | `tests/test_qita_cli.py` | Dual-read only after v2 reader exists; behavior frozen in D1 | D |
| D09 | Replay parser is strict; fork copies records and is coupled to deprecated debug | qita/replay coverage is incomplete | Move/promote adapter before debug removal | D/Task 10 |
| D10 | Legacy JSON uses replace; async durability may drop/fail while intended checkpoint ID survives | `tests/checkpoint/`, `tests/test_checkpoint.py`, e2e resume | Link receipts/references, do not merge checkpoint and trajectory truths | C durability, D references |
| D11 | Runner failures and partial results are benchmark-specific; some recipes also emit D07 | benchmark/recipe tests | Read/write via storage abstraction after parity | D plus recipe owners |
| D12 | Loader skips invalid JSONL lines; evaluators differ in material loaded | evaluate/metric and multi-agent evaluator tests | Versioned reader API plus declared loss/query needs | D/evaluation owners |
| D13 | Leaderboard stores pointer; HF errors can be masked in listing; upload is not an export privacy boundary | `tests/test_leaderboard.py`, `tests/test_hf_hub.py` | Versioned public exporter and loss/privacy report before v2 upload | D |
| D14 | Empty/provider errors become engine recovery events; opaque continuation currently omitted from trace summary | model response, OpenAI Responses, engine recovery tests | Consume Lane B versioned ExchangeLog/continuation fixture without inventing fields | B |
| D15 | Timeout can leave worker running; failures/retries/cancellation lack one receipt shared by hooks and trace | native tool, action executor, cancellation tests | Consume Lane C versioned outcome/receipt plus Lane B ArtifactRef | C outcome; B artifact |
| D16 | Strategy reports are dictionaries; failures are not a versioned codec/loss record | compact-history tests | Consume Lane B `CodecReport` and compaction report | B |

### Current canonical/derived decisions

- The current qita/replay compatibility truth remains trace v1
  `manifest.json + events.jsonl + steps.jsonl`. D1 makes no write-default change.
- `RuntimeEvent` and `StepRecord` remain the Engine's in-memory truth. Their
  overlapping persisted projections are measured debt, not permission to add
  more projections.
- `qitos/tracing` processors and renderer JSONL are derived observability and
  presentation planes. D1 does not nominate either as canonical.
- Checkpoints are continuation/durability state. They may reference future
  trajectory records but are not a replacement trajectory store.
- Benchmark results, leaderboard rows, and HF repositories are edge views or
  pointers. Future public exports require an explicit privacy policy and loss
  report.
- A future content-addressed layout may use a rebuildable index; SQLite is not
  selected as canonical storage.

## Public-surface census

Repository references prove internal use, not external disuse. “Unknown” below
therefore remains a first-class result.

| Surface | Evidence and internal/known consumers | Classification | Owner / next decision |
|---|---|---|---|
| Root `qitos` exports | `qitos/__init__.py` kernel contracts; guarded by `tests/test_public_surface.py`; examples import them | Canonical | core/engine; preserve |
| CLI commands | `qitos/cli.py`: demo, skill, bench, experiment, new, list-templates, leaderboard, push, pull; benchmark subcommands and qita commands documented/tested | Canonical edge, with compatibility routes | CLI and recipe owners; migration requires command tests |
| Entry points | `setup.py`: console scripts `qit` and `qita` | Canonical edge | packaging/CLI; preserve in D1 |
| Extras | `setup.py` model/benchmark/W&B/MLflow/HF/web/dev/all groups; cron/MCP HTTP/PgVector driver coverage is inconsistent | Canonical packaging metadata with gaps | Task 08; no D1 edit |
| Registries | model factory, protocol, skill/tool and benchmark runner registries | Canonical extension seams | owning modules; test discovery/versioning |
| Docs/examples | canonical learning path plus benchmark and MCP guides; benchmark docs still teach legacy imports | Mixed canonical/compatibility | docs and Task 10 migration |
| Deprecated shims | kit toolset/security shims, cache/debug compatibility modules, benchmark family facades | Compatibility-only | owning replacement plus warning window |
| `qitos.benchmark` | tests, CLI resolution, docs and recipe reverse imports; explicit deprecated package | Compatibility-only | recipes/Task 10; adapter required |
| `qitos.recipes.benchmarks` | examples, CLI, tests; canonical migration target but still imports legacy adapters/ports | Canonical recipe surface | recipes; finish dependency inversion |
| `qitos.func` | its own tests; no repository learning-path consumer found; external use unknown; retry/timeout/executor promises incomplete | Experimental / removal candidate pending evidence | Task 10 + C lifecycle |
| qita / `qitos.debug` | qita is canonical product CLI; fork imports deprecated `ReplaySession` | qita canonical, debug compatibility-only | D/Task 10; remove inversion first |
| `evaluate` / `metric` | recipe/evaluator tests and benchmark flows use their thin contracts and kit implementations | Canonical contracts, thin | evaluate/metric owners |
| leaderboard / HF | CLI routes and tests; leaderboard uses manifest pointer, HF transports run directories | Recipe/zoo candidate edge | Task 10/D exporter design |
| SharedMemory | Engine handoff, templates, docs and tests; abstract and concrete classes currently share core | Contract canonical; concrete stores recipe/kit candidate | B/C/Task 10 placement decision |
| CronScheduler | directly tested, but not taught in canonical docs; silently degrades without APScheduler | Experimental / removal candidate pending evidence | C/Task 10 + Task 08 extras |
| PgVectorStore | public kit implementation; no direct repository test/doc consumer found; external use unknown; dependency check/driver mismatch | Recipe/zoo candidate / removal candidate pending evidence | Task 10 + Task 08 extras |
| MCP | Engine lazy integration, tests, and bilingual tutorials consume server/stdio/http/bridge/filter APIs | Canonical extension, transport debt | C lifecycle; retain until SDK migration parity |

## Removal decision ledger

No row authorizes a deletion. `TBD` means a release cannot be named from current
evidence.

| ID | Surface | Current owner | Internal consumers | Known external consumers / unknown usage | Canonical replacement | Lane | Classification |
|---|---|---|---|---|---|---|---|
| R01 | `qitos.benchmark` package/families | benchmark/recipes | CLI, recipes reverse imports, examples, many tests/docs | Campaign and benchmark users are known; exact import population unknown | `qitos.recipes.benchmarks` plus out-of-tree family packages | D/Task 10 | Compatibility-only |
| R02 | benchmark kit/deprecated shims | kit/benchmark | legacy imports and tests | Unknown | canonical kit module or recipe adapter per shim | D/Task 10 | Compatibility-only |
| R03 | `qitos.debug.ReplaySession` | debug/qita | qita fork | qita users known; direct debug imports unknown | promoted storage-reader/fork adapter outside deprecated debug | D | Compatibility-only |
| R04 | `qitos.cache` | cache/experiment/engine | experiment runner and cache tests | Model-cache users possible; population unknown | decided cache contract/implementation after lifecycle audit | C/Task 10 | Compatibility-only |
| R05 | `qitos.func` | func | func tests only found | All external usage unknown | complete canonical kernel facade or none | C/Task 10 | Experimental/removal candidate |
| R06 | concrete SharedMemory stores/manager in core | core/engine | Engine handoff, templates, docs/tests | Multi-agent users known; direct class usage unknown | core interface plus kit concrete implementations, if migration approved | B/C/Task 10 | Recipe/kit relocation candidate |
| R07 | CronScheduler | kit tools | cron tests | All external usage unknown | fully supported optional kit tool or out-of-tree recipe | C/Task 10 | Experimental/removal candidate |
| R08 | PgVectorStore | kit vectorstore | no repository caller found | All external usage unknown | supported kit store with correct extra, or zoo integration | Task 10 | Recipe/zoo/removal candidate |
| R09 | leaderboard | leaderboard/CLI | CLI and tests | CLI users possible; unknown | out-of-tree service/recipe if product policy chooses | D/Task 10 | Recipe/zoo candidate |
| R10 | HF run transport | hf/CLI | CLI and tests | Hub dataset users possible; unknown | versioned trajectory exporter/importer edge | D | Recipe/zoo candidate |
| R11 | `qitos.evaluate` / `qitos.metric` thin namespaces | evaluate/metric | recipes and tests | Evaluator implementers possible; unknown | same contracts unless evidence supports consolidation | D/Task 10 | Canonical; not candidate now |
| R12 | MCP manual transports | mcp/engine | Engine, tests, tutorials | MCP users known; transport mix unknown | SDK-backed adapter with protocol parity | C | Canonical extension with replacement candidate |
| R13 | tracing legacy processor | tracing/trace | opt-in tracing-to-v1 bridge, tests | Unknown | explicit v1 adapter from future canonical reader/writer | D | Compatibility-only |
| R14 | renderer JSONL as stored data | render/recipes | TUI and selected recipe runs | Render log consumers unknown | derived renderer view from canonical store | D | Derived; persistence removal candidate |
| R15 | trace v1 writer | trace/qita | Engine recipes, qita, evaluate, HF, replay | Existing run archives and external readers are known | future versioned v2 plus v1 adapter, not yet implemented | D | Canonical compatibility; not removable now |

| ID | Compatibility adapter | Warning release | Earliest removal release | Required tests | Decision status | Blocker |
|---|---|---|---|---|---|---|
| R01 | legacy import facade and runner-name mapping | Not announced | TBD, at least one release after complete migration | family import/CLI/recipe/result parity | Keep and inventory | reverse imports, docs, unknown external imports |
| R02 | import forwarding shim | Existing warnings vary | TBD | shim warning and canonical import tests | Keep | consumer-by-consumer mapping incomplete |
| R03 | qita storage/fork adapter | Not announced | TBD | qita fork/replay parity | Promote before deprecating | qita directly depends on deprecated module |
| R04 | cache facade | Existing deprecation status | TBD | cache behavior, concurrency, cleanup | Defer | owner and lifecycle contract unresolved |
| R05 | decorator compatibility facade if deprecated | Not announced | TBD | retry/timeout/executor lifecycle and public import | Decide complete-or-deprecate | external usage and promised semantics unknown |
| R06 | re-export old core paths | Not announced | TBD | handoff, file/in-memory concurrency, public import | Keep contract; placement pending | concrete/core split and migration not approved |
| R07 | warning facade or recipe package | Not announced | TBD | missing-dependency, scheduling, restart, cleanup | Decide after extras/consumer evidence | silent degradation and unknown users |
| R08 | old import facade if moved | Not announced | TBD | driver integration, missing dependency, migrations | Decide after extras/consumer evidence | driver mismatch and unknown users |
| R09 | CLI/service adapter | Not announced | TBD | submit/show/summary and trace pointer | Defer | product ownership and external usage unknown |
| R10 | CLI plus versioned import/export adapter | Not announced | TBD | privacy/loss report, upload/download round-trip | Keep until v2 exporter | no v2 schema/public projection |
| R11 | none planned | None | Not a removal candidate | evaluator/metric contract and recipes | Keep canonical | no replacement case |
| R12 | same public MCP types over SDK transport | Not announced | TBD | stdio/http negotiation, cancellation, cleanup, Engine integration | Retain and migrate behind adapter | lifecycle receipts and parity |
| R13 | explicit tracing-to-v1 compatibility adapter | Not announced | TBD | correlation, steps, errors, public imports | Keep until bridge replacement | forced step zero and unknown opt-in users |
| R14 | renderer reader/view adapter | Not announced | TBD | TUI/qita/render parity and truncation | Stop treating as truth later | canonical store/reader absent |
| R15 | v1 reader/writer adapter | No write deprecation announced | Later than v2 default plus release review | all trace/qita/replay/export/evaluate/HF parity | Frozen and retained | trajectory v2 schema is not frozen |

## Representative fixture selection

The committed files are source/sanitization manifests, not trajectory payloads:

- `tests/fixtures/trajectories/campaign-long/fixture-manifest.json` selects an
  independently produced 200-step, 2,782-event campaign run (238,779,383 source
  bytes). SHA-256 identities are recorded without a host path. The source
  contains sensitive key names and has no confirmed redistribution license, so
  publication is blocked.
- `tests/fixtures/trajectories/unrelated-agent/fixture-manifest.json` selects the
  repository-owned deterministic native-tool agent from
  `tests/test_native_tool_calling_runtime.py`. It uses a fake provider and local
  tool, requires no model, key, network, or campaign runtime, and proves an
  independent consumer shape.

| Required feature | Campaign long source | Unrelated native-tool source | Coverage action |
|---|---|---|---|
| Long scale | Yes | No | Campaign source supplies scale |
| Run/step/phase correlation | Yes, v1 event/step facts | Yes when materialized | Benchmark must validate joins, not infer missing IDs |
| Multimodal | No evidence | No | Add a repository-owned visual agent fixture after ArtifactRef |
| Parallel/out-of-order tools | No evidence | Single native call | Request Lane C parallel/out-of-order fixture |
| Reasoning continuation | Not safely classifiable from raw string payloads | No | Request Lane B opaque continuation fixture |
| Context injection/compaction | Not versioned/classifiable | No | Request Lane B reports |
| Artifact | No normalized evidence | No | Request Lane B ArtifactRef fixture |
| Provider failure | No failed decide events observed | No | Request Lane B failure exchange fixture |
| Tool failure/retry | No normalized receipt evidence | No | Request Lane C outcome fixture |
| Cancellation/timeout | No | No | Request Lane C receipt fixture |
| Native call/result correlation | Not normalized | Yes | Retain unrelated source |

### Sanitization and privacy gate

1. Never copy either source payload until its manifest reports
   `sanitized_payload_ready`.
2. Confirm redistribution license; record source hash and transformation tool
   version. The campaign source remains `authorization_required`.
3. Apply Lane C's versioned trace-safe redaction contract to keys and values;
   reject rather than merely warn on a secret/credential finding.
4. Replace absolute paths, usernames, hosts, task IDs, and environment-specific
   endpoints with stable logical references. Reject `file://`, home-directory,
   drive-letter, and repository-external path patterns.
5. Separate `raw_private` and `redacted_public`; never derive replay-fidelity
   claims from the public projection.
6. Record a deterministic transform receipt with input/output hashes, dropped or
   rewritten field paths, privacy policy ID, license decision, and loss report.
7. Review free-form strings and artifact bytes, not only key names. Current v1
   key redaction is necessary but insufficient as a fixture-publication proof.

## Storage benchmark specification

`scripts/benchmark_trajectory_store.py` is deliberately a readiness checker.
With `--dry-run` it exits successfully and emits
`trajectory-store-benchmark-readiness-v1`; without it, the same typed
`TRAJECTORY_SCHEMA_NOT_READY` result exits 2. It never loads raw payloads or
creates measurements while contracts are missing.

After B/C fixtures are versioned and both manifests are sanitized, the future
benchmark must use the same semantic record set and deterministic serialization
for every candidate:

| Candidate/view | Definition |
|---|---|
| Current v1 | Exact bytes of manifest/events/steps generated by the frozen writer |
| Naive repeated JSON | Fully expanded canonical records with repeated payloads, stable key ordering |
| Digest references, no compression | Content-addressed candidate with no compression and index bytes counted separately |
| Optional gzip | Same logical files, fixed documented level/version; never a requirement |
| Optional zstd | Same logical files, fixed documented level/version when dependency exists; missing dependency is `skipped`, not failure |
| Raw/private | Fidelity-preserving policy, access-controlled test fixture |
| Redacted/public | Versioned safe projection with policy ID and machine-readable loss report |

Measurement protocol:

- report fixture ID, source class, schema/writer/codec versions, policy ID,
  Python/platform/dependency versions, warm-up count, repetitions, and median plus
  distribution (at least p25/p75); never merge the two consumer results;
- count total bytes and bytes by record/index/artifact; state whether filesystem
  allocation or logical bytes are reported;
- measure write, cold read, warm read, replay reconstruction, and the same
  qita-like query/render workload; validate semantic invariants before timing;
- report unique artifact bytes, referenced artifact bytes, digest count, and
  `1 - unique/reference` dedup ratio, including zero-denominator handling;
- verify run/step/phase joins, call/result joins, ordering, opaque continuation,
  artifact digests, lifecycle receipts, and exporter loss reports;
- isolate setup and sanitization from timed regions; use a fresh temporary
  directory per repetition and retain no raw fixture after the run;
- treat SQLite/search indexes as derived and rebuildable. No benchmark result may
  nominate them as canonical;
- publish measurements only after both sources complete all required workloads.
  A compression decision requires measured benefit, fallback behavior, and
  optional-dependency review.

## Cross-lane dependency requests

### Lane B — Conversation, Providers, and Context

Lane B should publish fixtures and version identifiers, not implementation
objects imported by this plan:

1. `ExchangeLog` fixture/version with stable request/response/tool transaction
   order and declared run/step correlation.
2. `RequestView` report including projection policy/version and a machine-readable
   loss report.
3. `CodecReport` with input/output identity, codec version, loss/fidelity facts,
   and failure representation.
4. Provider continuation opaque-field fixture, including display prohibition,
   storage/export privacy classification, and round-trip invariant.
5. `ArtifactRef` fixture/version with content identity, media/type metadata,
   ownership, portability, and missing/corrupt behavior.
6. Compaction report fixture/version covering ranges, before/after accounting,
   strategy, summary/reference identity, and loss/failure facts.

Acceptance for handoff: synthetic and redistributable fixtures; no secrets or
host paths; owner/version declared; compatibility projection to current runtime
facts documented; no Lane D-invented fields required.

### Lane C — Tools, Execution, and Runtime Safety

Lane C should publish:

1. Canonical `ToolResult`/outcome fixture and version, including one parallel
   call set, out-of-order completion, stable call/result correlation, structured
   result, failure, and retry.
2. Timeout/cancellation receipt fixture distinguishing requested, observed,
   worker-still-running, terminal status, and cleanup outcome.
3. Durability receipt fixture distinguishing intended ID, enqueue, persist,
   flush, failure/drop, and recovery visibility.
4. Hook-facing failure fields/fixture so processor, renderer, and persistence
   failures are auditable without changing Engine semantics in D1.
5. Versioned trace-safe redaction contract for keys, values, free-form strings,
   paths, nested artifacts, opaque provider content, and typed redaction failures.

Acceptance for handoff matches Lane B and must include lifecycle ordering and
failure tests. Lane D will consume the versioned fixture; it will not copy or
guess the contract.

## Known gaps and next gate

- The campaign source is selected but cannot be committed until licensing and
  sanitization gates pass.
- The unrelated source is deterministic but not materialized because doing so
  now would freeze pre-contract exchange/outcome fields.
- Required multimodal, parallel/out-of-order, compaction, artifact, provider
  failure, tool failure/retry, and cancellation/timeout coverage awaits B/C
  fixtures.
- No complete trace-v1 reader contract exists: qita is tolerant while debug
  replay is strict and evaluation silently skips malformed JSONL.
- HF upload is not yet a versioned public/redacted export boundary.
- Hook/processor/durability failures do not yet share an auditable receipt.
- Trajectory v2 schema is not frozen. D2/05A may start schema work only after
  the B/C handoff fixtures and sanitization gates are satisfied.

## Validation record

Exact results on the fixed baseline worktree:

- [x] `pytest -q tests/tracing tests/test_engine_result_traces.py` → 77 passed
- [x] `pytest -q tests/test_qita_cli.py` → 20 passed
- [x] `pytest -q tests/test_public_surface.py` → 4 passed
- [x] `pytest -q tests/test_architecture_boundaries.py` → 4 passed
- [x] `pytest -q` → 1,696 passed, 50 skipped
- [x] `flake8 qitos/core qitos/engine qitos/models qitos/trace` → clean
- [x] `mypy qitos/core qitos/engine qitos/models qitos/trace` → success, 76 files
- [x] `git diff --check` → clean
- [x] `python scripts/benchmark_trajectory_store.py --fixture tests/fixtures/trajectories --dry-run` → typed `schema_not_ready`, 0 measurements/claims
- [x] `pytest -q tests/test_benchmark_trajectory_store.py` → 2 passed
