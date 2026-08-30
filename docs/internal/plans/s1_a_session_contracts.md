# S1 Lane A — stable session runtime contracts

Status: active (contract package only; no Engine pause/resume behavior)
Owner: Lane A / Task 12A
Source branch: `codex/v4-s1-a-session-contracts`
Source commit: `c1efb0f4adde3e673bf181af5b1760c19a451ae2`
Integration worktree lease: none; all changes are isolated in
`/Users/morinop/Desktop/WhitzardOS-s1-a`

## Objective and scope

Define the one canonical, JSON-safe session identity, lifecycle, immutable
snapshot envelope, resolver-reference, head-generation, receipt, and typed
failure contract that later Task 12 packages will implement over the existing
checkpoint store. This package deliberately does not implement Engine pause,
restore, fork, head CAS, scheduling, tool-effect semantics, ExchangeLog
semantics, trace writing, or qita behavior.

The public design target is one beginner-facing `Session` handle owned by
`Engine`, backed by checkpoint persistence. The contract types are initially
imported from their owning module and are not added to root exports in 12A.

## Exact-source census

This census follows writers into their readers rather than relying on matching
names. `Identity` names the actual identifier currently carried at that link;
`P/L` means process-local or persistent.

| Concern | Source file and symbol | Writer -> reader | Current owner | Identity | Mutability / P/L | Lifecycle and restart behavior | Compatibility | Target disposition |
|---|---|---|---|---|---|---|---|---|
| Interactive init | `qitos/engine/engine.py::Engine.init_session` | Engine creates state/observation -> REPL callers call `step` | engine | new `_active_run_id` only | mutable / process-local | resets Engine memory/history and loses everything at exit | public convenience | **adapt** behind future `Engine.session`; retain until migration evidence |
| Main run | `qitos/engine/engine.py::Engine.run` | Engine loop -> `EngineResult`, hooks, trace, checkpoints | engine | `_active_run_id` | mutable / process-local, with partial persistence | creates a fresh run ID even on `resume_from_checkpoint()` because `run()` resets it | public mainline | **retain**, later bind each invocation to a distinct run within a session |
| Async path | `qitos/engine/async_engine.py::AsyncEngine.{arun,run}` | async facade -> the same sync `Engine.run` in a worker thread | engine | underlying run ID | mutable / process-local | cancellation requests do not prove worker termination | public facade | **adapt** symmetrically; no separate async session model |
| Engine result | `qitos/engine/engine.py::EngineResult` | Engine writes -> callers, RunState, hooks | engine | `run_id` | immutable-ish dataclass / process-local | terminal result is not a durable session head | public | **retain** as run result, never session truth |
| RunState | `qitos/engine/run_state.py::RunState` | `from_engine_result`/JSON -> tests and compatibility consumers | engine | optional `checkpoint_id`; no session ID | mutable / independently persistent | serializes state, records, events; cannot reconstruct composition root | shipped compatibility | **migrate** through isolated historical reader, then **retire** as independent truth |
| Current checkpoint write | `qitos/engine/engine.py::_save_checkpoint` | Engine -> `DurabilityManager.put` -> `CheckpointStore.put` | engine + checkpoint | `thread_id == _active_run_id`; UUID checkpoint | mutable input / persistent store | stores only state data/version/pending writes; restart lacks task/config/type | current store | **adapt** store to carry canonical snapshot bytes; `thread_id` becomes compatibility addressing only |
| Current checkpoint read | `qitos/engine/engine.py::resume_from_checkpoint` | store tuple -> state type from live `_active_state` or base `StateSchema` -> `run()` | engine | checkpoint thread reused as active run | process-local reconstruction | needs original Engine/live type; task is incorrectly read from metadata `run_id` | current API | **migrate** to resolver-based restore; retain as deprecated adapter during rollout |
| Checkpoint store | `qitos/checkpoint/store.py::{Checkpoint,CheckpointConfig,CheckpointStore}` | Engine/durability/fork -> memory or SQLite stores | checkpoint | `CheckpointId`, `thread_id` | mutable dataclasses / persistent mechanism | immutable-by-convention records but no ownership isolation/CAS | canonical mechanism | **retain and adapt**; never create SessionStore |
| Memory store | `qitos/checkpoint/memory_store.py::InMemoryCheckpointStore` | store API -> tests/development | checkpoint | checkpoint/thread | mutable aliases / process-local | lost at process exit; list order is append order | current implementation | **retain**, later implement same head/CAS semantics for tests |
| SQLite store | `qitos/checkpoint/sqlite_store.py::SqliteCheckpointStore` | store API -> durable local DB | checkpoint | checkpoint/thread | JSON rows / persistent | `INSERT OR REPLACE`, no head generation CAS | current implementation | **retain**, later add atomic head operation without parallel store |
| Durability worker | `qitos/checkpoint/durability.py::DurabilityManager` | Engine -> sync/queue/buffer -> store | checkpoint | returns intended checkpoint ID | mutable queue/thread / process-local front to persistence | ASYNC drop and swallowed write failure can look accepted/persisted | current mechanism, known debt | **adapt** in later package to typed accepted/persisted/failed receipts; 12A defines vocabulary only |
| Pending writes | `qitos/checkpoint/pending_writes.py::PendingWriteManager` | Action-side manager -> store `put_writes`; resume loads values | checkpoint | `task_id` string | mutable / mixed | completed partial results can persist, started slots are only in memory | current mechanism | **adapt** as one snapshot component; Lane C owns effect semantics |
| Checkpoint fork | `qitos/checkpoint/fork.py::fork_checkpoint` | source checkpoint -> copied checkpoint under optional new thread | checkpoint | inferred thread/checkpoint lineage | copied mutable dictionaries / persistent | reuses `created_at`; shallow-copies nested state; no new session identity | current helper | **migrate** to session fork semantics; preserve as compatibility adapter |
| Deprecated manager | `qitos/checkpoint/checkpoint.py::{CheckpointData,CheckpointManager}` | Engine/experiment -> JSON files -> manager readers | checkpoint | run ID in filename/data | mutable / persistent files | skips corrupt files and stores competing Engine state/history truth | deprecated but imported | **retire** after historical migration reader and experiment migration; do not extend |
| Interrupt | `qitos/engine/interrupt.py::{interrupt,EngineInterrupt,InterruptInfo}` plus `Engine._save_interrupt_checkpoint` | contextvars -> exception -> `StepResult` -> caller `resume` | engine | positional `int_N`, checkpoint ID | process-local control + optional persistence | step re-executes; no-store path fabricates transient checkpoint-shaped ID | public mechanism | **adapt** to pause request/safe-pause receipts; keep interrupt primitive distinct |
| Cancellation | `qitos/engine/cancellation.py::CancelToken` and `Engine.cancel/run finally` | caller -> loop -> optional checkpoint/EngineResult | engine | run-local token | mutable / process-local | immediate may be mid-step; after-step saves state; worker may continue | public behavior | **retain**, map to lifecycle without claiming quiescence |
| Trace identity | `qitos/trace/writer.py::TraceWriter`, `runtime_event_to_trace`; `qitos/trace/schema.py` | Engine events/steps -> v1 files -> qita/evaluate/HF | trace | run ID + step ID; optional parent run | append artifacts / persistent | trace is replay evidence, not restorable head | frozen compatibility | **retain** reader/writer unchanged; later add explicit session lineage supplied by runtime owner |
| qita replay/fork | `qitos/qita/_cli_app.py::do_POST` -> `qitos/debug/replay.py::ReplaySession.fork_with_step_override` | qita copies trace rows and names `{run}_fork_s{step}` | qita/debug | derived run-name suffix | file mutation / persistent trace copy | does not fork execution state; parentage inferred by naming | deprecated dependency | **migrate** in Task 12E to runtime fork client; do not change in 12A |
| Task construction | `qitos/core/task.py::Task.{to_dict,from_dict}` and `Engine._normalize_task` | caller -> Engine -> state init/checkpoint metadata | core/engine | task ID (optional for string tasks) | mutable / mixed | current checkpoints do not preserve reconstructable task consistently | public contract | **retain**, snapshot slot stores JSON task fact plus component schema |
| State construction | `qitos/core/state.py::StateSchema.{to_dict,from_dict,migrate_payload}` | Agent init/Engine -> checkpoint -> live-type restore | core | state schema version, Python type currently implicit | mutable / mixed | fresh-process restore cannot safely select concrete class | public contract | **retain**, persist resolver reference + schema version; never live type/object |
| Runtime context | `qitos/engine/action_executor.py::_build_runtime_context` | Engine/executor builds live dict -> tools | engine | blank `parent_run_id`; no typed tool-call/session identity | mutable / process-local | contains live env/state/registry/callbacks/writer; cannot be snapshotted | internal mechanism | **retain as live projection**, rebuild from snapshot and resolvers; never persist it |
| Model construction | `qitos/models/base.py::ModelFactory.create`, `models.harness_adapter::build_model_for_preset` | config/preset -> live model -> Engine agent | models | provider/model name | live resource / process-local | credentials/config resolved in process | public mechanism | **adapt** via typed model resolver reference; defaults may auto-register resolver |
| Tool construction | `qitos/core/tool_registry.py::ToolRegistry` plus kit toolset builders | agent/composition -> registry -> Engine/ActionExecutor | core + kit | tool names/versions, no stable resolver ref | live registry / process-local | registry is not reconstructable from checkpoint | current extension point | **adapt** via toolset resolver reference and capability digest |
| Environment construction | `qitos/engine/_env_runtime.py::build_env_from_spec` | `Task.env_spec` -> lazy kit env -> Engine | engine + kit | env type/config, sometimes raw workspace/host handle | live resource / process-local | fresh process may recreate inconsistently; raw host paths appear in config | current composition | **adapt** via environment resolver ref; snapshot forbids raw host paths |
| Conversation/continuation | `qitos/core/conversation.py::{ExchangeLog,OpaqueContinuationAttachment}` | model runtime -> persistent exchange fixtures/readers | Lane B/core | exchange/item/call/continuation IDs | deep-isolated JSON facts / persistent-capable | Engine checkpoint does not yet carry it; opaque provider payload is not a live continuation | current contract | **retain by reference slot**; Lane B owns component schema/version |
| Partial parallel action | `qitos/core/conversation.py::ToolBatchBuilder`, `qitos/checkpoint/pending_writes.py` | declarations/results -> ExchangeLog and pending writes | B/C/checkpoint | batch/call/task strings | mixed | two partial representations are not yet one session snapshot component | current primitives | **adapt** through component slot; Lane A owns envelope only |
| Provider continuation | `qitos/core/conversation.py::OpaqueContinuationAttachment` and model response paths | provider codec -> exchange log -> later request | Lane B | attachment/ref identifiers | JSON payload / persistent-capable | capability/resolution rules are not part of restore | current B contract | **adapt** component slot + optional resolver namespace; Lane B owns payload |
| Public exports | `qitos/__init__.py`, `qitos/core/__init__.py`, `qitos/engine/__init__.py`, `qitos/checkpoint/__init__.py` | module exports -> users/tests | package owners | mixed | static / process-local API | root surface is guarded | compatibility gate | **retain unchanged** in 12A; future public handle budget is ADR-only |
| Examples/CLI | `examples/`, `qitos/cli.py`, qita routes | examples/commands -> Engine.run or trace operations | edge | mostly run IDs | process-local/file-based | no canonical durable-session golden path today | user surface | **migrate later** in 12E; 12A documents intended golden path only |

## File leases

| Lease owner | File(s) | Semantic purpose | Start/end package | Other lanes blocked or adapter supplied |
|---|---|---|---|---|
| Lane A | `qitos/core/session.py` (new) | canonical identity, lifecycle, snapshot envelope, resolver refs, receipts, failures | 12A | B/C/D must import identities; no copied enums |
| Lane A | `tests/core/test_session_contract.py`, `tests/fixtures/session/` | strict contract and cross-lane producer fixtures | 12A | consumer instructions and digest supplied |
| Lane A | `docs/architecture/session-runtime-contract.md` | API/ownership/compatibility ADR | 12A | read-only handoff to B/C/D |
| Lane A | this plan and Lane A evidence | census, decisions, qualification | 12A | integration owner consumes evidence |
| Integration owner | `README.md`, `README.zh.md`, `CHANGELOG.md`, `docs/progress.md` | shared release/status text | S1 integration | Lane A records suggested text in evidence; does not edit |

No lease is taken on `Engine`, `AsyncEngine`, `RunState`, checkpoint store,
trace, qita, CLI, root exports, ToolResult, or ExchangeLog in 12A.

## Target API and public-surface budget

Future beginner surface (names remain ADR commitments, not implemented behavior):

- `Engine.session(task)` creates or obtains a framework-generated session;
- `Session.run()` / `AsyncSession.arun()` execute one new run attempt;
- `Session.pause()` / `AsyncSession.apause()` request and await a safe pause;
- `Engine.restore(session_id, resolvers=...)` restores through checkpoint truth;
- `Session.fork(snapshot=...)` creates an isolated session identity.

12A adds zero root exports and zero Engine constructor parameters. The only
code-level surface is the owner module `qitos.core.session`; future façade work
must stay within the five concepts above rather than exposing CAS, component
envelopes, or resolver internals to beginners.

## Canonical ownership

- Lane A owns all identity types, lifecycle vocabulary, snapshot envelope,
  resolver reference shape, head generation/CAS rules, pause/persistence
  receipts, and session failure codes.
- Lane B owns ExchangeLog, queued steering, context/artifact, request/codec, and
  provider-continuation component schemas.
- Lane C owns tool attempt/effect/quiescence and child/work-graph component
  schemas.
- Lane D reads lineage and receipts; it does not mutate session truth.
- Checkpoint remains the only persistence mechanism. Session is the user mental
  model; `RunState` and historical checkpoint readers are compatibility inputs.

## Compatibility strategy and retirement ledger

| Path | Existing consumer | Migration | Warning gate | Removal prerequisite | Contract test | Owner |
|---|---|---|---|---|---|---|
| `Engine.init_session` tuple API | step-by-step REPL/e2e | adapt to a session handle while retaining tuple adapter | after golden path exists | two releases/consumer evidence | future Engine integration | Lane A |
| `RunState` JSON | Snowl/tests/out-of-tree unknown | isolated historical reader -> current snapshot or typed unreconstructable error | when reader lands | consumer census + migration docs | historical fixture reader | Lane A |
| `CheckpointData/Manager` | experiment/tests | historical checkpoint reader into current snapshot | already deprecated; no new writes | experiment uses current store + fixture migration | legacy fixture tests | Lane A/integration |
| `resume_from_checkpoint`/`resume` | Engine tests/e2e | adapter resolves session by checkpoint and creates a new run | after restore façade lands | fresh-process parity | process restore suite | Lane A |
| checkpoint `thread_id` | all current stores | codec maps old thread address to explicit session identity | internal warning only | all current writers emit explicit identity | checkpoint migration fixtures | Lane A |
| qita/debug trace fork | qita UI | runtime client forks immutable session snapshot | qita deprecation notice in 12E | qita dual-read + runtime fork | qita route behavior | Lane A/D |
| example helpers | examples/out-of-tree copies | replace with golden path | docs warning | examples and two consumers migrated | examples smoke | Lane D/A |

Compatibility code must use names such as `historical_checkpoint_reader` and
`migration_adapter`; it may not define a second public Session API.

## Fixtures

Stable root: `tests/fixtures/session/` with `schema_version` inside payloads.

- producer fixture: exact identity vocabulary and relationship examples;
- semantic fixtures: created, running, pause requested, safely paused, partial
  parallel batch, pending steering, persistence failure, generation conflict,
  superseded owner, missing resolver, unavailable secret, corrupt snapshot,
  unsupported component, restore candidate, and forked session;
- validation corpus: unknown field, wrong type, non-JSON, non-finite number,
  ownership isolation, deterministic canonical bytes/digest, corrupt integrity,
  unsupported envelope/component schemas.

Fixture values are synthetic, portable, and contain no secret, credential,
provider payload, or host-local path.

## Tests

1. identity construction/generation/serialization/equality and relationship
   validation;
2. lifecycle transition/action matrix including request vs safe pause;
3. strict resolver reference and resolver-set validation with safe failures;
4. strict component and snapshot readers/writers, immutability, JSON admission,
   unknown field/type rejection, deterministic digest, and integrity failure;
5. generation/CAS and persistence receipt semantics as pure contracts;
6. every required typed failure code, recovery/remediation fields, and metadata
   redaction/local-path safety;
7. fixture-manifest coverage and independent B-like/C-like consumer simulations;
8. no root export or Engine behavior delta.

## Validation matrix

Run without reruns or masked failures:

1. new session contract tests;
2. `tests/checkpoint/` and `tests/test_checkpoint.py`;
3. `tests/engine/` and `tests/test_engine_core_flow.py`;
4. architecture, public surface, and no-local-path tests;
5. `/opt/anaconda3/bin/python3.12 scripts/static_quality.py check`;
6. stable flake8 and stable mypy commands;
7. `/opt/anaconda3/bin/python3.12 -m pytest -q`;
8. `git diff --check`.

## Stop conditions

Stop before any change that requires a second store/result/trace truth, Engine
behavior, work scheduling, ToolResult/ExchangeLog semantics, trace/qita writer,
provider defaults, root export, live object/credential persistence, exactly-once
effect claim, shared release-document edit, or incompatible B/C component
definition. Return such a need to its semantic owner.

## Phase ledger

| Phase | Deliverable | Status |
|---|---|---|
| 0 | exact baseline/worktree verification | complete |
| 1 | mandatory reading and exact-source census | complete |
| 2 | plan, leases, target API, ownership, compatibility | complete |
| 3 | independent identity producer commit + fixture digest | in progress |
| 4 | lifecycle/resolver/snapshot/failure contracts | pending |
| 5 | semantic fixtures, strict readers, consumer simulations | pending |
| 6 | ADR and producer evidence/handoff | pending |
| 7 | targeted and full validation | pending |
| 8 | self-review, final clean commits/status | pending |
