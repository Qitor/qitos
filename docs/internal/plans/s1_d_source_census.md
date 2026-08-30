# S1-D exact-source trajectory and lineage census

Status: complete for source identity
`c1efb0f4adde3e673bf181af5b1760c19a451ae2`

This census follows concrete writers and readers. “Canonical” below means the
current owner of a fact, not that a future Trajectory schema or writer exists.
Future disposition uses only canonical, derived, or compatibility. No row
authorizes a removal.

## Runtime and current observability

| ID | File / symbol; writer -> reader | Owner | Identity, ordering, persistence | Loss and redaction | Current public status | Target disposition and removal prerequisite |
|---|---|---|---|---|---|---|
| D01 | `qitos/engine/states.py::RuntimeEvent`; `qitos/engine/_trace_runtime.py::_TraceRuntime.emit` writes `Engine.events`, current step events, trace and hooks | Engine runtime | `step_id`, phase and timestamp; run ID copied into payload; append order in memory only | Arbitrary payload; no in-memory privacy projection | Internal runtime fact | Canonical producer input by reference; removal requires an Engine event replacement and parity |
| D02 | `qitos/engine/states.py::StepRecord`; `_TraceRuntime.finalize_step` writes trace step and hooks | Engine runtime | Step order in `Engine.records`; no top-level run ID; process memory until trace/checkpoint copies | Repeats observation/model/action/result; no in-memory redaction | Internal result field | Canonical producer input, not a second record truth; removal requires EngineResult and hook migration |
| D03 | `qitos/trace/writer.py::TraceWriter`; recipes/Engine write `manifest.json`, `events.jsonl`, `steps.jsonl`; qita/replay/evaluate/HF read | Lane D compatibility | Directory/run identity and file append order; manifest counters; durable local files | Recursive key redaction, unknown objects become representations; cross-file joins incomplete | Frozen compatibility contract | Compatibility reader source; writer retirement requires archive, parity, external-consumer, and release evidence |
| D04 | `qitos/trace/events.py::{TraceEvent,TraceStep}` and `qitos/trace/writer.py::{runtime_event_to_trace,runtime_step_to_trace}` | Lane D envelope over Engine facts | Event has run/step/phase; step lacks run/phase; JSONL line order | Normalization can stringify unknown objects; event/step duplication | Compatibility schema | Compatibility codec only; normalized records must declare absent lineage/loss |
| D05 | `qitos/tracing/models.py::{SpanData,Span,Trace}`; `qitos/tracing/provider.py::TracingProvider`; processors consume completed spans | Lane D derived observability | Trace/span IDs and start/end time; span order from processor delivery; optional files/services | Selective span input/output; redacting wrapper covers selected fields | Optional tracing API | Derived span plane; cannot become qita or storage truth |
| D06 | `qitos/tracing/legacy_processor.py::LegacyTraceWriterProcessor`; spans -> forced trace events -> current writer | Lane D compatibility | Span trace ID can differ from writer run ID; step forced to zero; no trace-step output | Lossy span-to-event projection; errors may fail open | Compatibility bridge | Retire after an explicit derived/compatibility adapter with correlation/failure parity |
| D07 | `qitos/render/events.py::RenderEvent`; `qitos/render/_hooks_impl.py::{RenderStreamHook._emit,ClaudeStyleHook}` writes memory and optional `render_events.jsonl` | Lane D presentation | Hook/event order, step and channel; no durable session/work identity | Display selection, truncation and repeated output; writer redaction is insufficient as public policy | Curated render API; JSONL is optional | Derived presentation/cache; persistence removal requires renderer parity from `TrajectoryReader` |
| D08 | `qitos/qita/_cli_app.py::{_discover_runs,_load_run_payload,_build_replay_records,_cmd_board,_cmd_replay,_cmd_export}` reads current files | Lane D reader/DX | Directory name treated as run ID; group by step; file order | Tolerant JSONL inserts invalid-line findings; no independent public projection | Canonical qita product over compatibility data | Future `TrajectoryReader` consumer; direct file reads retire only after behavior parity |
| D09 | `qitos/debug/replay.py::ReplaySession`; qita fork reads/copies current files | Lane D compatibility/deprecated debug | Event cursor and step lookup; copy-based fork has no durable session/snapshot lineage | Shallow copied views; no new redaction or effect semantics | Deprecated dependency used by qita | Compatibility replay adapter; remove after runtime-owned fork and reader parity |

## Persistence, evaluation, exchange, result, and context

| ID | File / symbol; writer -> reader | Owner | Identity, ordering, persistence | Loss and redaction | Current public status | Target disposition and removal prerequisite |
|---|---|---|---|---|---|---|
| D10 | `qitos/checkpoint/checkpoint.py::{CheckpointData,CheckpointManager}` and `qitos/checkpoint/store.py::{Checkpoint,CheckpointStore}`; Engine saves/resumes | Lane A persistence; current legacy compatibility | Legacy run/step versus store `thread_id`, checkpoint ID, parent ID, step; JSON/files/memory/SQLite | Primarily state data; incomplete conversation/ownership/effect facts; no public projection | Checkpoint APIs, with old/new migration debt | Canonical continuation reference, never trajectory truth; legacy retirement needs Task 12 migration |
| D11 | `qitos/recipes/benchmarks/_shared.py::build_example_specs`; `qitos/benchmark/common.py::write_benchmark_results` writes benchmark result JSONL pointing to traces | Recipe owners / Lane D migration | Task/trial/result order, run directory reference | Benchmark-specific fields and redaction; not lossless execution | Mixed canonical recipes and deprecated benchmark adapter | Derived result/export view; migrate family consumers before legacy package removal |
| D12 | `qitos/evaluate/base.py::{EvaluationContext,load_run_artifacts}` and `qitos/metric/base.py::MetricInput` consume current files/results | Evaluate/metric owners | Manifest run plus event/step file order; metric rows by caller order | Invalid JSONL silently skipped by evaluator; evaluator-specific selection | Public thin contracts | `TrajectoryReader` consumers; compatibility behavior and loss must be explicit before migration |
| D13 | `qitos/leaderboard/store.py::LeaderboardStore.submit_run_dir`; `qitos/hf/hub.py::{push_run,pull_run}` consumes/transports run directories | Edge owners / Lane D exporter policy | Leaderboard pointer/submission identity; remote directory named by run | Manifest-only sanitizer; events/steps/extras can contain raw data | Edge products | Derived registry/export; require versioned privacy/loss reports before canonical exporter status |
| D14 | `qitos/core/model_response.py::ModelResponse.to_summary_dict`; `qitos/engine/_model_runtime.py::_ModelRuntime` writes summary and runtime payload | Lane B | Current step/run context; native call IDs and item order exist, but no RequestView/CodecReport identity | Summary omits encrypted continuation while other runtime paths may retain raw output | Internal provider/runtime contract | Canonical B payload references after exact receipt; no Lane D field inference |
| D15 | `qitos/core/tool_result.py::ToolResult`; `qitos/engine/_action_runtime.py::_ActionRuntime`; `qitos/engine/action_executor.py::ActionExecutor._build_runtime_context` writes canonical/persistence/model/trace projections | Lane C | Action ID, timing, status and effect-related metadata; action declaration/completion order split across runtime | Persistence is lossless for contract; model/trace projections redact and declare loss | Core contract, not root-export expansion in S1-D | Canonical C payload reference; migration waits for recovery/effect/attempt facts |
| D16 | `qitos/kit/history/compact_history.py::CompactHistory`; `qitos/engine/_context_runtime.py::_ContextRuntime.normalize_history_events` emits compaction dictionaries/events | Lane B | Message/step order; summaries retained in memory/history; no stable report identity | Micro/summary compaction is intentionally lossy; metadata is ad hoc | Curated history implementation | Derived from B `CodecReport`/snapshot component after exact producer handoff |
| D17 | `qitos/core/conversation.py::ExchangeLog`; `ExchangeLog.to_persistence_dict`, `to_model_dict`, and `to_trace_safe_dict` feed current consumers/tests | Lane B | Log/item/exchange/batch/provider-call IDs; append/declaration/completion order; in-memory persistence payload | Canonical, model, trace, and continuation-redacted views separated; opaque payload private | Core module contract | Canonical B payload reference; RequestView/steering/snapshot components remain blocked |
| D18 | `qitos/core/conversation.py::OpaqueContinuationAttachment`; `qitos/models/_openai_responses.py::_model_response_from_responses` writes provider-native items | Lane B | Provider scope/API mode/attachment and response-item/call IDs; provider order | Persistence retains opaque data; diagnostic view redacts; current summary can omit | Internal provider and core conversation support | Canonical private attachment by reference; public display forbidden; codec evidence required |
| D19 | `qitos/core/tool_result.py::ToolResult.artifact_refs`; `qitos/core/multimodal.py::{ContentBlock,observation_visual_assets}`; `qitos/kit/tool/library/base.py::ToolArtifact` | Lane B artifact contract pending; C outcome slot | Artifact IDs/media/path/data vary; no single ArtifactRef/store identity; some in-memory only | Host paths/raw data may exist; ToolResult projections apply bounded policies | Fragmented internal/curated fields | Blocked canonical artifact reference; no trajectory-only artifact store may be added |
| D20 | `qitos/kit/history/compact_history.py::{CompactionController,CompactHistory}` and Engine context normalization | Lane B | Input message order, retained windows and summary continuity; runtime events are consumed once | Declared counts/previews but no versioned cross-lane loss report | Curated history API | B-owned compaction report referenced by Trajectory; implementation not copied |

## Session, replay/fork, and multi-agent lineage

| ID | File / symbol; writer -> reader | Owner | Identity, ordering, persistence | Loss and redaction | Current public status | Target disposition and removal prerequisite |
|---|---|---|---|---|---|---|
| D21 | `qitos/engine/engine.py::{Engine.init_session,Engine.run}` creates `_active_run_id`, active state and records | Lane A future session owner | “Session” is an in-process handle; generated run ID; no distinct durable session/head/snapshot IDs | Live objects and incomplete persistence; no public safe projection | Public Engine methods with ambiguous session semantics | Compatibility API over Task 12; retire ambiguity only after adapter and migration evidence |
| D22 | `qitos/engine/run_state.py::RunState` serializes EngineResult records/events/state | Lane A compatibility decision | Schema version, checkpoint ID, step and agent name; list order persisted in JSON | Duplicates trace and runtime state; lacks ExchangeLog/work/effect/resolver completeness | Public engine submodule type | Adapter or retirement into one SessionSnapshot truth; cannot remain second persistence truth |
| D23 | `qitos/engine/engine.py::{Engine._save_checkpoint,Engine.resume_from_checkpoint,Engine.resume}` writes/reads checkpoint store | Lane A with Lane C durability | Current code uses run as checkpoint `thread_id`; parent checkpoint and step order; durable store dependent | Restores state type from live active state and task from metadata; fresh-process facts missing | Public resume methods | Task 12 canonical persistence path; D records references only |
| D24 | `qitos/checkpoint/fork.py::{fork_checkpoint,list_fork_history}` copies checkpoint state and parent chain | Lane A | New checkpoint/thread ID, parent checkpoint; store order by step | Shallow top-level state copy; no session/work ownership lineage | Public checkpoint helper | Canonical fork producer after Task 12; qita remains a client |
| D25 | `qitos/qita/_cli_app.py::_build_handler` POST fork path uses `ReplaySession` and writes copied current files | Lane D compatibility UI | New run directory suffix encodes source step; no snapshot/session identity | Copy/override is replay data, not resumable runtime; returns host directory today | Current qita route | Replace with thin runtime fork client; public output must not expose host path |
| D26 | `qitos/engine/_handoff_runtime.py::_HandoffRuntime.execute_handoff` mutates live agent/history/state and emits handoff events | Lane C work ownership | Agent names and step; no work item or owner generation; in-memory order | Context filtering can summarize/drop; no transfer/loss/authority receipt | Engine internal behavior plus public Decision/tool adapters | Compatibility operation over future WorkGraph; requires generation-checked transfer receipt |
| D27 | `qitos/kit/tool/delegate.py::{DelegateTool.execute,DelegateTool._build_sub_engine,DelegateTool._build_sub_trace_writer}` runs nested Engine | Lane C | Child identity is generated run-name suffix plus `parent_run_id`; synchronous result order | Context string transformation and child result summary; no durable child/effect lineage | Curated model-callable tool | Compatibility adapter over explicit delegate operation; suffix must never be parsed |
| D28 | `qitos/kit/tool/fanout.py::{FanOutTool.execute,FanOutTool._run_sub_agent,FanOutTool._build_sub_trace_writer}` runs thread-pool children | Lane C | Dictionary key and run suffix encode agent/index; completion collected from futures; no durable join generation | Timeout/cancel can leave workers running; result aggregation is lossy | Curated model-callable tool | Compatibility adapter over durable fan-out/join; requires late-result and quiescence receipts |
| D29 | `qitos/kit/tool/delegate.py::DelegateTool._build_sub_trace_writer`; `qitos/kit/tool/fanout.py::FanOutTool._build_sub_trace_writer`; `qitos/trace/writer.py::TraceWriter` | Lane C producer convention / D compatibility | `__delegate_...` and `__fanout_...` suffixes plus optional `parent_run_id` metadata; directory order only | Names do not prove edge, ownership, attempt, or generation; redaction does not repair semantics | Compatibility naming convention | Never canonical; display as unverified metadata until explicit producer lineage exists |

## Exporters, readiness, and target intake

| ID | File / symbol; writer -> reader | Owner | Identity, ordering, persistence | Loss and redaction | Current public status | Target disposition and removal prerequisite |
|---|---|---|---|---|---|---|
| D30 | `qitos/qita/_cli_app.py::_cmd_export`, `qitos/hf/hub.py::push_run`, `qitos/benchmark/common.py::write_benchmark_results` | Lane D export policy plus edge owners | HTML/run-directory/result-row identity and caller/file order | HTML embeds compatibility payload; HF only sanitizes manifest subset; benchmark rows are derived | Public/edge exporters | Future `TrajectoryExporter` implementations with versioned privacy/loss; none is canonical today |
| D31 | `scripts/benchmark_trajectory_store.py::{validate_contract_receipts,build_readiness_result}` reads fixture manifests and exact receipt sets | Lane D readiness | Stable contract IDs; deterministic sort; exact commit/path/digest/authority; no runtime persistence | Rejects host paths/privacy findings without value echo; hashing verifies bytes and is not sanitization | Development/CI evidence tool | Canonical readiness gate only, not writer/store/benchmark; retire blockers only through owned evidence |

## Cross-cutting findings

1. No current record carries distinct session, run, snapshot, work item,
   attempt, owner generation, and head generation as one qualified lineage.
2. Current trace events and steps preserve useful compatibility facts but have
   asymmetric IDs and duplicated payloads. This is a codec problem, not a
   license to create another trace product.
3. Checkpoints are continuation state. A future trajectory references their
   immutable identity and durability receipts; it does not absorb checkpoint
   state as a second copy.
4. ExchangeLog and ToolResult have reviewed G1 foundation fixtures. S1
   RequestView/session/effect/WorkGraph facts are still absent.
5. Current handoff/delegate/fan-out relations are in-process behavior plus
   metadata/name conventions. qita must reject inferred edges.
6. Existing exporters are not a qualified public/redacted Trajectory export.
   Hashes prove identity only; sanitization requires a named transform and loss
   policy.

## Current producer status

At this source identity all S1 A/B/C branches still point at the dispatch
baseline; no accepted producer commit exists. A/C working-copy drafts do not
qualify because uncommitted or unreviewed bytes have no exact producer identity.
The acceptance order remains A, C, B, then mechanical D receipt refresh.

The readiness inventory therefore reports `producer_version_unestablished` for
every S1 contract, while retaining only the accepted G1 ExchangeLog and
ToolResult foundation receipts. This is not G2 readiness.
