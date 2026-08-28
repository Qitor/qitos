# Engineering Quality Audit

Status: actionable audit
Audited: 2026-08-29
Branch snapshot: `feat/campaign-absorption`
Scope: `qitos/`, `tests/`, packaging, CI, and the active `docs/v4/` program

---

## 1. Executive summary

QitOS has a credible architectural center: `AgentModule + Engine`, explicit
execution phases, a domain-neutrality gate, and a substantial test suite. The
main engineering risk is not a lack of abstractions. It is that several public
surfaces can currently report success while silently losing work, converting
failures into ordinary data, or escaping the checks that maintainers reasonably
assume cover the repository.

The highest-priority conclusions are:

1. **The green quality signal is narrower than the package surface.** CI lint
   and typing cover four stable directories, while `pyproject.toml` excludes or
   ignores entire implementation layers. A repository-wide diagnostic found
   204 flake8 findings and 48 mypy errors; the findings include undefined names
   and invalid method overrides, not only formatting debt.
2. **Some runtime APIs acknowledge work before it is durable.** Asynchronous
   checkpoint writes can be dropped or fail in the worker while `put()` still
   returns a checkpoint ID. `flush()` can fail to enqueue its own sentinel.
3. **Provider failures sometimes become normal model text.** Anthropic, Gemini,
   and local adapters return strings such as `HTTP Error: ...`; the Engine may
   parse or persist those strings as assistant output instead of applying a
   typed failure/recovery policy.
4. **Resource and cancellation semantics are fragmented.** Sync/async bridges,
   thread pools, tool timeouts, MCP transports, functional composition, hooks,
   and checkpoint workers each own different lifecycle rules. A timed-out
   thread may continue running, and several executors have no explicit owner or
   shutdown path.
5. **Parallel concepts have accumulated parallel representations.** The largest
   examples are `ActionResult` versus `ToolResult`, dataclass fields versus dict
   state in `Observation`, three event planes, seven token estimators, several
   JSON-repair paths, and the deprecated benchmark tree importing its intended
   replacement and vice versa.

The response should be a ratcheted quality program, not a repository-wide
rewrite. Tasks 02–05 remain the architectural mainline. This audit adds Tasks
08–10 for quality gates and packaging, runtime lifecycle/error semantics, and
surface consolidation. Each task has explicit coordination points so coding
agents do not create a second model kernel, executor, trace format, or utility
layer.

## 2. Method and evidence standard

This audit combined:

- repository-wide static diagnostics (`flake8 qitos`, `mypy qitos`);
- AST-based module, class, function, and constructor-size inspection;
- import-boundary and packaging configuration review;
- execution-path review from model call through decision, action, observation,
  checkpoint, hook, and trace;
- focused review of tests that claim the relevant behavior;
- comparison with the existing architecture audit and debt inventory;
- primary-source checks for Python executor behavior, Python packaging metadata,
  SQLite transactions, and the official MCP Python SDK.

An item is listed only when it has a concrete code/configuration location and a
plausible failure or maintenance mechanism. File length alone is not treated as
a defect.

### 2.1 Snapshot metrics

| Signal | Snapshot | Interpretation |
|---|---:|---|
| Python files under `qitos/` and `tests/` | 592 | Broad package surface; package-level gates matter |
| Python LOC under `qitos/` | ~100,491 | Includes large vendored benchmark data/ports |
| Python LOC under `tests/` | ~31,649 | Substantial suite, but distribution and assertion quality vary |
| Test functions | ~1,742 | Quantity is strong; lifecycle/route/conformance gaps remain |
| Flat files directly under `tests/` | 104 of 159 | Ownership and subsystem discovery are weak |
| Task 01 full-suite baseline | 1,694 passed, 50 skipped | Functional baseline was green on this branch snapshot |
| Stable-surface flake8 | clean | Current required gate covers `core`, `engine`, `models`, `trace` |
| Repository-wide flake8 diagnostic | 204 findings | 174 remain even excluding experimental security and vendored Tau code |
| Stable-surface mypy | clean, 76 files | Current required gate is intentionally narrow |
| Repository-wide mypy diagnostic | 48 errors in 13 files | Includes recipe override and functional API contract errors |

The repository-wide diagnostics are an audit baseline, not a proposal to make
all existing findings blocking in one commit. Task 08 defines a no-regression
ratchet and retires the baseline package by package.

## 3. Priority model

- **P0 — Structural risk:** can report false success, lose work,
  invalidate repository gates, or block safe evolution of the mainline.
- **P1 — High-value cleanup:** recurring ambiguity or duplication that will
  make Tasks 02–05 harder and more error-prone if left unresolved.
- **P2 — Maintainability improvement:** incomplete or low-adoption surface that should be
  proven, deprecated, or isolated without delaying the kernel.
- **P3 — Minor cleanup:** safe local readability work, only when the
  owning code is already being changed.

## 4. Top engineering issues

### [P0] EQ1. Quality gates do not describe the shipped package

**Directions:** testing, dependencies, readability, boundaries

**Evidence.** `.github/workflows/ci.yml:74-110` runs flake8 and mypy only over
`qitos/core`, `qitos/engine`, `qitos/models`, and `qitos/trace`.
`pyproject.toml:25-38` excludes benchmark/experimental paths and applies
`ignore_errors = true` to all of `qitos.kit.*`, `qitos.render.*`, and
`qitos.benchmark.*`. Repository-wide diagnostics expose undefined names such as
`List` in `kit/parser/json_parser.py` and `logdir_root` in
`qita/_cli_app.py:364`, plus incompatible recipe overrides.

`contribution-test.yml:16,53,104` attempts to inspect
`github.event.pull_request.changed_files.*.filename`, although
`changed_files` is a count, not a file collection. Its `CHANGED` variable is
unused, and the subset run is explicitly ignored with `|| true` at line 99.
`zoo-test.yml:43-46` is a stale, non-blocking workflow for an out-of-tree/absent
surface.

**Current Design.** A zero-debt stable surface is checked strictly; broad
implementation areas are ignored or selected by unreliable optional workflows.

**Why It Is a Problem.** A contributor can receive a green CI signal for code that
contains an undefined runtime name or violates the intended method contract.
This is worse than having no type checker because it overstates assurance.

**Recommended Direction.** Establish one committed full-surface diagnostic baseline,
fail CI only on new findings at first, immediately eliminate correctness-class
findings (`F821`, invalid overrides, unreachable imports), then shrink the
baseline by owner package. Replace fragile path expressions with a supported
changed-file action or simple always-on focused jobs. Remove or relocate the
zoo workflow.

**Expected Benefit.** Green CI becomes a trustworthy no-regression signal while
existing debt remains measurable and reviewable.

**Estimated Scope.** Large overall; medium for the initial ratchet.

**Do not do.** Do not land a single mechanical 200-finding cleanup mixed with
runtime refactors; it will destroy reviewability and hide behavior changes.

**Execution:** Task 08A, 08B, 08E.

### [P0] EQ2. Deprecated benchmark and replacement recipes form a dual mainline

**Directions:** duplicate implementations, boundaries, accidental complexity

**Evidence.** Existing architecture debt D1 records 89 files and roughly 26k
lines in `qitos/benchmark`, including a large vendored Tau port. Benchmark
runners import `qitos.recipes.benchmarks`, while recipe implementations import
legacy adapters/ports back from `qitos.benchmark`.

**Current Design.** The deprecated package and its intended replacement remain
mutual runtime dependencies.

**Why It Is a Problem.** There is no locally obvious canonical owner. Every bug fix
must decide whether to change a runner, recipe, adapter, or vendored port, and
imports can break during moves.

**Recommended Direction.** Inventory every public import and CLI route, finish the
declared migration to `recipes.benchmarks`, move large upstream ports to an
optional asset/package where feasible, provide compatibility imports for one
release, and delete the cycle. Treat benchmark behavior as recipe/product
content, not a kernel concern.

**Expected Benefit.** One benchmark mainline, safer imports, and a smaller core
distribution.

**Estimated Scope.** Large; stage by benchmark family and release window.

**Do not do.** Do not extend `qitos.benchmark` or copy another adapter into
recipes while the migration is open.

**Execution:** Task 10B; tracked as architecture debt D1.

### [P0] EQ3. Asynchronous checkpointing can report success after loss or failure

**Directions:** error handling, lifecycle, testing

**Evidence.** `qitos/checkpoint/durability.py:81-94` uses `put_nowait`; on a full
queue it logs that the checkpoint is being dropped and still returns a
`CheckpointConfig` containing the intended checkpoint ID. Lines 143-151 swallow
every store exception. Lines 101-110 may fail to enqueue the flush sentinel and
then only perform a bounded join. The per-write `result_event` and
`result_holder` created at lines 83-86 are never completed or observed.
`tests/test_bounded_queues.py:69-100` asserts warning behavior, not persistence,
failure visibility, or shutdown completeness.

**Current Design.** All durability modes preserve a synchronous-looking return
type, while the ASYNC worker communicates loss only through logs.

**Why It Is a Problem.** Callers cannot distinguish durable, queued, dropped, and
failed checkpoints. Resume/replay behavior can therefore disagree with the
successful return value.

**Recommended Direction.** Define a `CheckpointReceipt` (or equivalent internal
status) with `accepted`, `persisted`, `failed`, and `dropped` states; make queue
overflow policy explicit (`block`, `reject`, or lossy); retain worker errors and
surface them through flush/shutdown/run receipts; test queue saturation, store
failure, repeated flush, and process exit. Default research runs should not
silently choose lossy durability.

**Expected Benefit.** Resume, replay, and shutdown decisions become based on
explicit persistence evidence.

**Estimated Scope.** Medium; compatibility around `put()` is the main risk.

**Do not do.** Do not make background exceptions crash the Engine thread
arbitrarily. Surface them at an owned synchronization boundary.

**Execution:** Task 09D.

### [P0] EQ4. Provider failures are encoded as successful assistant text

**Directions:** error handling, abstractions, model protocols

**Evidence.** `qitos/models/anthropic.py:91-95,252-256`,
`qitos/models/gemini.py:84-88,117`, and `qitos/models/local.py:129-133` (with
similar branches at 292, 410-412, and 552) return or stream strings beginning
with `HTTP Error`, `Connection Error`, or `Error`. Those values satisfy ordinary
text response types.

**Current Design.** Several adapters normalize both success and transport
failure into the same string or stream-chunk channel.

**Why It Is a Problem.** Parser fallback, stop detection, history, and traces can
treat transport/auth/rate-limit failures as model-authored content. Engine
recovery cannot classify an exception that the adapter already converted into
data.

**Recommended Direction.** Provider transports must raise a typed model failure or
return a discriminated failure result before decoding. Preserve provider status,
retryability, request ID, and a redacted diagnostic. Streaming must terminate
with the same typed failure semantics as non-streaming. Task 02 codecs decode
only successful protocol responses; Task 09 owns the cross-runtime failure
taxonomy and recovery policy.

**Expected Benefit.** Recovery, retry, tracing, and user output can distinguish
infrastructure failure from genuine model content.

**Estimated Scope.** Medium; four provider families plus conformance fixtures.

**Do not do.** Do not infer failure later by matching strings such as
`"Error:"`; model-authored text may legitimately contain them.

**Execution:** Task 02C coordinated with Task 09B.

### [P0] EQ5. Sync/async bridges and executor lifecycles have no single owner

**Directions:** lifecycle, accidental complexity, concurrency

**Evidence.** `models/base.py`, `mcp/bridge.py`, and `engine/engine.py` each
bridge async work into sync execution using their own `asyncio.run`/thread
strategy. `ActionExecutor` has separate behavior and may close/reject a
coroutine when invoked under an active loop. Tool timeouts return a timed-out
result while recording `worker_still_running=True`; the worker thread is not
cancelled. `func/task.py:64-72` allocates a one-off `ThreadPoolExecutor` without
an owner, and `func/compose.py:40-77` owns another executor without `close()` or
context-manager semantics.

Python documents that program exit still waits for pending
`ThreadPoolExecutor` futures even when executor shutdown does not wait. A
reported timeout is therefore not a cancellation or process-lifetime guarantee
([Python `concurrent.futures` documentation](https://docs.python.org/3.11/library/concurrent.futures.html)).

**Current Design.** Loop bridging, execution, timeout, and cleanup are solved
locally at each entry point with mixed implicit and explicit ownership.

**Why It Is a Problem.** The same callable can have different legality, timeout,
cleanup, and failure semantics depending on which entry point invoked it.
Long-running tools may mutate state after the Engine has declared a timeout.

**Recommended Direction.** Write an execution ownership matrix first. Define separate
contracts for awaiting an already-returned awaitable, running async code from a
sync boundary, and imposing a timeout. Make thread timeout explicitly
non-cancelling; require process isolation for hard cancellation. Every owned
executor, client, subprocess, worker, and scheduler needs `close/aclose` plus
idempotent shutdown and conformance tests.

**Expected Benefit.** Predictable Engine/AsyncEngine/standalone behavior, fewer
resource leaks, and honest cancellation guarantees.

**Estimated Scope.** Large; changes span model, tool, MCP, and functional paths.

**Do not do.** Do not hide all cases behind one magical `run_sync()` helper.
Calling context and cancellation capability must remain visible.

**Execution:** Task 09A, 09C, 09F; tool behavior coordinated with Task 03.

### [P0] EQ6. Three event planes and silent hook failure undermine observability

**Directions:** duplicate implementations, error handling, boundaries

**Evidence.** Architecture debt D4 identifies runtime events/step records,
frozen `qitos.trace` v1 artifacts, `qitos.tracing` v2 spans, and an additional
renderer JSONL path. qita reads v1, while v2 is not the default data plane. In
addition, `engine/_trace_runtime.py` catches all hook exceptions and records
only a debug log (D12).

**Current Design.** Runtime, trace v1, tracing v2, and rendering own overlapping
representations, while hook dispatch defaults to invisible fail-open.

**Why It Is a Problem.** A run can be operationally successful while its audit trail
is incomplete, and consumers cannot know which event representation is
authoritative.

**Recommended Direction.** Keep the v1 reader contract frozen, execute Task 05's
canonical lossless event/artifact plane and compatibility bridge, and add an
explicit hook failure policy (`fail_open` with counted diagnostics or `strict`).
Every run receipt must state trace completeness and hook failures.

**Expected Benefit.** One replayable source of truth and explicit observability
completeness without breaking existing qita artifacts.

**Estimated Scope.** Large; Task 05 migration plus Task 09 hook semantics.

**Do not do.** Do not add a fourth “simpler” JSONL writer or point qita directly
at unfinished v2 spans.

**Execution:** Task 05 coordinated with Task 09E.

### [P1] EQ7. `Observation` has two mutable representations that can diverge

**Directions:** wrong abstractions, readability, error handling

**Evidence.** `qitos/core/observation.py:11-39` declares a dataclass that also
subclasses `dict`. `_sync_mapping()` is called only in `__post_init__`. Mutating
`observation.state` does not update `observation["state"]`; mutating the mapping
does not update the field. Runtime code consequently alternates field access,
`isinstance` branches, and `.get()` compatibility access.

**Current Design.** One object serves as a typed record and a legacy mutable
mapping, with only construction-time synchronization.

**Why It Is a Problem.** Reducers, trace serializers, and compatibility adapters can
observe different state from the same object. Type checkers also cannot express
the real mutation invariant.

**Recommended Direction.** Choose one canonical immutable/typed record and provide an
explicit `to_mapping()` compatibility projection, or choose a validated mapping
schema. Introduce an adapter and deprecation test before removing dict behavior.

**Expected Benefit.** One observable state, simpler typing, and fewer
compatibility branches in reducers and serializers.

**Estimated Scope.** Medium; public compatibility makes this more than a local edit.

**Do not do.** Do not add more synchronization hooks to every field and mapping
method; that preserves the wrong abstraction at higher complexity.

**Execution:** Task 10D, after Tasks 02/03 determine the final observation
payload.

### [P1] EQ8. `ActionResult` and `ToolResult` describe one transition differently

**Directions:** duplicate abstractions, wrong abstractions

**Evidence.** `qitos/core/action.py:14-62` defines five `ActionStatus` states and
an `ActionResult` with identity, attempts, latency, and metadata.
`qitos/core/tool_result.py:10-71` defines a second result with only
`success/error`; it coerces other statuses and flattens dict outputs for legacy
reducers. The action runtime converts executor results into tool results before
building observations.

**Current Design.** Executor outcomes are converted into a narrower observation
result and then reinterpreted by history, rendering, and tracing.

**Why It Is a Problem.** Timeout, cancellation, skip, attempt count, and action
identity can be lost or reconstructed inconsistently between execution,
history, rendering, and tracing.

**Recommended Direction.** Task 03 should define one lossless action outcome envelope
with an explicit model-facing projection. Keep legacy `ToolResult` conversion
at the boundary for a migration window.

**Expected Benefit.** Execution status and identity remain lossless from tool
dispatch through replay, with one model-facing projection.

**Estimated Scope.** Medium to large; central contract with broad call sites.

**Do not do.** Do not force raw tool return values to carry execution metadata;
the outcome envelope belongs to the runtime.

**Execution:** Task 03A/03B; tracked by Task 10 only for cleanup after migration.

### [P1] EQ9. Context budgets use seven incompatible token estimators

**Directions:** duplicate implementation, utilities, correctness

**Evidence.** `_estimate_tokens` exists in prompting, Engine, its private
protocol, content rendering, and three history implementations. Some use a
model counter, some whitespace words, some `len(text) // 4`, and the renderer
uses a regex-oriented display estimate.

**Current Design.** Each budget/history/render owner estimates tokens locally,
using different algorithms and no accuracy/source label.

**Why It Is a Problem.** The same request can be accepted by one budget component and
rejected or compacted by another. Telemetry numbers are not comparable.

**Recommended Direction.** Define one injectable `TokenCounter` result with source
(`provider_exact`, `tokenizer_exact`, `estimated`) and one lightweight fallback.
Request selection/history use it; display-only estimates must be labeled and
kept out of control decisions.

**Expected Benefit.** Consistent compaction decisions and comparable occupancy
telemetry without forcing a heavy tokenizer dependency.

**Estimated Scope.** Medium; seven helpers migrate after the contract lands.

**Do not do.** Do not require a heavyweight tokenizer package for the base
install. Exact provider/model counters remain optional capabilities.

**Execution:** Task 02B and Task 04C; Task 10F removes old helpers afterward.

### [P1] EQ10. JSON extraction and repair logic is duplicated without policy layers

**Directions:** duplicate implementation, utilities, model protocols

**Evidence.** Generic JSON repair/extraction appears in
`core/_json_repair.py`, parser utilities, `json_parser.py`,
`terminus_json_parser.py`, evaluator parsing, and REPL formatting. Some paths
repair control characters or truncation; others extract fenced/substr JSON or
apply protocol-specific terminus rules.

**Current Design.** Generic extraction/repair and protocol-specific salvage are
implemented independently in each consumer.

**Why It Is a Problem.** Parser success, recovered arguments, and diagnostics vary by
entry point, while similarly named helpers imply a consistency that does not
exist.

**Recommended Direction.** Keep one conservative generic extraction/repair primitive
with structured diagnostics; layer protocol/provider-specific salvage above it.
Conformance fixtures must distinguish accepted repair from rejected ambiguity.

**Expected Benefit.** Consistent recovery diagnostics and less duplicated edge-
case code without erasing protocol-specific policy.

**Estimated Scope.** Medium; fixture design is more important than code volume.

**Do not do.** Do not merge all salvage rules into a permissive “parse
anything” utility. Protocol-specific behavior is intentional.

**Execution:** Task 02A/02C; cleanup in Task 10F.

### [P1] EQ11. Retry configuration has duplicated mechanics and dead knobs

**Directions:** wrong abstractions, error handling, readability

**Evidence.** `core.tool.RetryPolicy` is consumed independently by
`models/base.py` and `engine/action_executor.py`, which each implement their own
attempt/backoff loop. `kit/interceptor/retry.py:26-64` exposes
`retry_on_exception` and `backoff_factor`, but `before_execute()` only raises
`Action.max_retries`; neither option affects execution.

**Current Design.** A shared policy shape exists, but model and tool loops own
separate mechanics and the interceptor exposes knobs it does not apply.

**Why It Is a Problem.** The public configuration suggests behavior that is not
implemented, and future fixes risk applying retries at both interceptor and
executor layers.

**Recommended Direction.** Keep model-call, tool-action, and whole-step recovery as
separate semantic policies, but share a small backoff calculation/attempt
receipt. Remove or deprecate ignored knobs; require an idempotency decision for
automatic tool retry.

**Expected Benefit.** Public knobs become truthful, retry receipts comparable,
and double-retry or unsafe overlap risks are reduced.

**Estimated Scope.** Small for dead-knob correction; medium for shared receipts.

**Do not do.** Do not add Tenacity solely to replace a small, explicit loop; it
does not solve ownership or semantic duplication.

**Execution:** Task 09B/09C, coordinated with Tasks 02 and 03.

### [P1] EQ12. Optional dependencies are undocumented runtime branches

**Directions:** dependency management, lifecycle, testing

**Evidence.** Packaging metadata remains in `setup.py`, while `pyproject.toml`
contains only build/tool configuration. Declared extras do not cover all
optional behavior: MCP HTTP requires `httpx`; local embeddings import
`sentence-transformers`; coding utilities import `PyPDF2` and `nbformat`;
CronScheduler imports APScheduler; PgVectorStore checks `asyncpg` but its sync
wrapper imports `psycopg2`. The `all` extra omits even the declared `web`
dependency.

CronScheduler catches missing APScheduler and still tracks jobs that will never
auto-fire. PgVectorStore advertises asyncpg while executing through a different
driver.

The standard `[project]` and `[project.optional-dependencies]` tables provide a
single metadata source in `pyproject.toml`
([PyPA specification](https://packaging.python.org/en/latest/specifications/pyproject-toml/),
[PyPA packaging guide](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)).

**Current Design.** Optional imports are guarded ad hoc at runtime while extras
and the `all` bundle cover only a subset of those branches.

**Why It Is a Problem.** Users discover missing packages only after selecting a
feature; some features degrade silently rather than failing at construction.

**Recommended Direction.** Publish a feature-to-extra matrix, make missing capability
errors explicit, add isolated install/import smoke tests for every extra, fix
driver mismatches, and then migrate metadata to PEP 621 with a build-equivalence
test.

**Expected Benefit.** Reproducible installations, actionable errors, and one
auditable source of packaging metadata.

**Estimated Scope.** Medium; PEP 621 migration follows isolated install parity.

**Do not do.** Do not put every optional SDK/database/browser dependency in the
base install.

**Execution:** Task 08C; unsupported/dead features resolved in Task 10D.

### [P1] EQ13. QitOS hand-rolls MCP transports that the official SDK owns

**Directions:** reinventing wheels, dependencies, lifecycle

**Evidence.** `qitos/mcp/stdio.py` implements JSON-RPC construction/parsing,
subprocess lifecycle, initialization negotiation, request IDs, and content
decoding. `qitos/mcp/http.py` independently implements Streamable HTTP request
and notification behavior. Protocol version `2024-11-05` is embedded in both.

The official MCP Python SDK provides typed clients, stdio and Streamable HTTP
transports, and lifecycle-managed sessions
([official repository](https://github.com/modelcontextprotocol/python-sdk),
[client documentation](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/client/index.md)).

**Current Design.** QitOS owns two MCP transports, JSON-RPC framing, protocol
negotiation, response correlation, content decoding, and cleanup.

**Why It Is a Problem.** Protocol negotiation, transport evolution, cancellation,
notifications, sessions, and typed content are interoperability work rather
than QitOS research differentiation.

**Recommended Direction.** Run a version-pinned compatibility spike against the
official client. If its dependency and Python-version envelope fit, replace the
transport/session implementation behind QitOS's existing `MCPServer` and
`FunctionTool` bridge. Retain QitOS filtering, schema conversion, runtime
context, permission, and tracing integration.

**Expected Benefit.** Less protocol maintenance and stronger interoperability
while preserving QitOS-specific tool/runtime integration.

**Estimated Scope.** Medium spike; medium-to-large migration if adopted.

**Do not do.** Do not delete the current implementation before stdio and HTTP
fixtures prove initialization, tools/list, tools/call, errors, cancellation,
and cleanup through the adapter.

**Execution:** Task 09F spike; adoption decision in Task 10D.

### [P1] EQ14. Concrete storage and orchestration implementations leak into `core`

**Directions:** boundaries, wrong abstractions, lifecycle

**Evidence.** `qitos/core/shared_memory.py` contains the abstract contract,
in-memory implementation, file implementation, namespace view, and manager.
`FileSharedMemory` claims “file locking” at line 75 but uses only a process-local
`threading.Lock`; each write performs a non-atomic read-modify-write of the JSON
file. Concurrent processes can lose updates or expose partial data.

**Current Design.** The core contract module also owns concrete in-memory/file
stores and namespace/manager policy; file safety is process-local only.

**Why It Is a Problem.** `core` becomes responsible for filesystem policy, and the
advertised multi-agent use does not have multi-process correctness.

**Recommended Direction.** Keep the minimal `SharedMemory` contract in core. Move
concrete stores/manager policy to kit with compatibility re-exports. If
multi-process persistence is a supported goal, use an atomic/transactional
backend such as stdlib SQLite and test two-process contention; Python's sqlite3
module exposes transaction control without adding a base dependency
([Python `sqlite3` documentation](https://docs.python.org/3/library/sqlite3.html)).

**Expected Benefit.** A leaf core contract and persistence behavior whose
concurrency guarantee matches its documentation.

**Estimated Scope.** Medium; compatibility re-exports reduce migration risk.

**Do not do.** Do not add a “global utils lock”; process-local locks cannot
provide the stated guarantee.

**Execution:** Task 10D, after usage inventory.

### [P1] EQ15. Provider and process adapters duplicate existing framework mechanisms

**Directions:** reinventing wheels, duplicate implementation

**Evidence.** `qitos/models/local.py` contains repeated urllib request, JSON
decode, and error-string conversion for multiple local servers, even though
OpenAI-compatible model infrastructure already exists. LM Studio and vLLM are
OpenAI-compatible modes; Ollama has a distinct native API. Process execution is
also scattered across `CommandCapability`, Host/Docker environments, worktree,
REPL, tmux, coding tools, and several experimental tools.

**Current Design.** Similar HTTP and process operations are implemented inside
individual providers/tools despite existing compatible transports and env
capabilities.

**Why It Is a Problem.** Timeout, environment, output, encoding, and failure
behavior drift between adapters that perform the same protocol operation.

**Recommended Direction.** Make LM Studio/vLLM configurations of a shared
OpenAI-compatible transport/codec; retain native Ollama behavior. Define one
structured process result and cleanup policy in the appropriate kit/env layer,
then migrate domain tools opportunistically.

**Expected Benefit.** Fewer transport/process code paths and consistent timeout,
error, encoding, and cleanup behavior.

**Estimated Scope.** Medium for providers; process migration should be incremental.

**Do not do.** Do not force every subprocess through the Engine or add a third-
party process library without a demonstrated process-tree/cancellation need.

**Execution:** Task 02C for providers; Task 03D/Task 10F for process helpers.

### [P1] EQ16. Kernel construction has multiple composition roots and oversized owners

**Directions:** accidental complexity, readability, boundaries

**Evidence.** `Engine` is roughly 2,100 class lines with 91 methods, a 33-argument
constructor, and a `run()` method of roughly 605 lines. `_ActionRuntime.run_act`
and `ActionExecutor._execute_one_inner` are each hundreds of lines.
`AgentModule._merge_run_defaults` accepts 19 inputs and constructs concrete env,
trace, renderer, and parser objects through lazy imports, while
`config/builder.py` provides another assembly path. `EngineConfig` is primarily
an exported snapshot rather than the construction contract.

**Current Design.** Engine remains the façade and a composition root, while
AgentModule convenience and config builders also assemble concrete dependencies.

**Why It Is a Problem.** Private protocols expand to mirror shared mutable Engine
state, and tests/mocks need internal knowledge. New features naturally land in
the largest owner even when they belong to a policy or adapter.

**Recommended Direction.** Keep `Engine` as the public façade, but establish one typed
construction specification/composition root. Tasks 02–05 should extract only
cohesive transaction owners (conversation, action outcome, context/artifact,
trace) and pass explicit dependencies. Measure reduced constructor and private-
state coupling, not file count.

**Expected Benefit.** One discoverable construction path, smaller private
protocols, and better-isolated tests without decorative layers.

**Estimated Scope.** Large; deliver through the ownership seams in Tasks 02–05.

**Do not do.** Do not split files into manager classes that all mutate the same
Engine object; that is indirection without ownership.

**Execution:** Task 02B/02D and existing debt D2, D3, D11.

### [P1] EQ17. qita's monolith hides an untested runtime route failure

**Directions:** readability, testing, error handling

**Evidence.** `qitos/qita/_cli_app.py` is roughly 3,420 lines. Its largest HTML
renderer is roughly 1,625 lines and `_build_handler` roughly 478 lines.
`do_POST` resolves fork runs using undefined `logdir_root` at line 364. Current
tests at `tests/test_qita_cli.py:300-306` and 428-431 assert that a handler class
or method exists; renderer tests mostly search generated HTML strings. They do
not issue the POST request that would execute the undefined name.

**Current Design.** Routing, data discovery, fork behavior, SSE, and large
HTML/JavaScript renderers share one module; tests mostly inspect symbols/strings.

**Why It Is a Problem.** A user-visible qita route is broken despite a green suite,
and large embedded templates make route/data/render responsibilities difficult
to test independently.

**Recommended Direction.** First add socket-level or handler-level HTTP integration
tests for routes, status codes, traversal rejection, fork behavior, SSE, and
shutdown. Fix correctness-class errors separately. Then split routing, run data
queries, and static rendering/assets along tested seams.

**Expected Benefit.** Runtime route defects become reproducible, and structural
splits can preserve behavior behind integration tests.

**Estimated Scope.** Medium for tests/fix; large only if the split follows.

**Do not do.** Do not rewrite qita in a web framework merely because the file is
large; a new framework is not required to establish these ownership seams.

**Execution:** Task 08D for tests/correctness ratchet; Task 10E for structure.

### [P2] EQ18. Speculative public surfaces contain unimplemented promises

**Directions:** wrong abstractions, lifecycle, testing, surface area

**Evidence.** `qitos.func` is referenced internally mainly by its own tests and
is not part of the canonical learning path. `TaskFunction` stores
`max_retries` and `timeout_s` (`func/task.py:31-42`) but direct, async, and
submitted calls never enforce them. Its executors lack ownership. PgVectorStore
has a driver mismatch and little live coverage. Cron jobs may be accepted
without a functioning scheduler. `leaderboard` and `hf` remain operational
surfaces in the core repository.

**Current Design.** Low-adoption APIs and integrations remain publicly shaped as
stable features despite incomplete policy, dependency, or lifecycle semantics.

**Why It Is a Problem.** Every exported feature multiplies compatibility, dependency,
documentation, and test obligations. Placeholder knobs are worse than a small
honest API.

**Recommended Direction.** Apply a public-surface admission test: documented consumer,
contract tests, lifecycle, dependency extra, and active maintainer owner. For
each surface, either complete and teach it, mark it experimental, move it out of
tree, or deprecate it with a measured migration window.

**Expected Benefit.** A smaller, more honest API and focused maintenance on
features with demonstrated research value.

**Estimated Scope.** Medium for census/decisions; removal depends on evidence.

**Do not do.** Do not delete based only on internal grep; first inspect external
imports, release notes, and package download/user reports where available.

**Execution:** Task 10A, 10C, 10D.

## 5. Reinventing-wheels decisions

| Area | Decision | Reason |
|---|---|---|
| MCP transports/session | Evaluate official SDK behind the current bridge | Protocol interoperability and lifecycle are upstream responsibilities |
| LM Studio/vLLM HTTP | Reuse QitOS OpenAI-compatible adapter | Same wire protocol; current local copies add no research value |
| Retry/backoff | Keep a small internal primitive | Semantics/ownership are the problem; another dependency is not |
| File-backed shared memory | Prefer SQLite if multi-process support is real | Standard-library transactions are safer than JSON read-modify-write |
| Packaging metadata | Adopt PEP 621 after equivalence tests | One standardized metadata source reduces setup drift |
| CLI dispatch | Keep argparse | Replacing it with Click/Typer would add churn without solving current defects |
| Engine lifecycle/state machine | Keep QitOS implementation | This is the framework's differentiating research kernel |
| JSON repair | Consolidate conservative primitives, keep protocol layers | External permissive repair does not encode QitOS diagnostics/invariants |
| Tool schema | Keep lightweight core schema | Pulling Pydantic into the base solely for style is unjustified |
| Process execution | Consolidate on existing capability/env contracts | Add a dependency only if hard process-tree cancellation is required |

## 6. Refactoring Opportunities

The table is ordered for delivery, not by file size.

| Priority | Area | Problem | Evidence | Recommendation | Benefit | Effort |
|---|---|---|---|---|---|---|
| P0 | Quality gates | Green required checks omit broad shipped surfaces | CI stable jobs; `pyproject.toml` ignores; 204 flake8/48 mypy diagnostic findings | Task 08A/B no-regression ratchet | Trustworthy CI without a mass cleanup | Medium initial / Large staged |
| P0 | CI workflow | Changed-path predicates are invalid and intended checks use `|| true` | `contribution-test.yml:16,53,98-100`; `zoo-test.yml:43-46` | Repair predicates; remove stale/non-blocking jobs | Required jobs exercise what they claim | Small |
| P0 | Model errors | Provider failures become ordinary assistant text | Anthropic/Gemini/local error-return branches | Typed failure envelope in Task 02/09 | Correct recovery, retry, and traces | Medium |
| P0 | Checkpoints | Queue drop/worker failure still returns intended checkpoint ID | `durability.py:81-151`; bounded-queue tests | Explicit durability receipts and overflow policy | Honest resume and shutdown state | Medium |
| P0 | Lifecycle | Sync/async bridges and executors have inconsistent ownership | Engine/model/MCP bridges; ActionExecutor; `qitos.func` | Task 09 ownership matrix and conformance | Predictable cleanup/cancellation | Large |
| P0 | Observability | Three event planes plus silent hook failure | runtime events, trace v1, tracing v2, render JSONL | Task 05 canonical plane + Task 09 hook policy | Lossless, auditable runs | Large |
| P0 | Benchmarks | Deprecated and replacement packages import each other | Architecture debt D1; 89-file legacy tree | Finish benchmark → recipes migration | One canonical implementation | Large |
| P1 | Tool outcomes | `ActionResult` loses semantics through `ToolResult` | `core/action.py`; `core/tool_result.py` | One lossless outcome + model projection | Stable execution/replay semantics | Medium–Large |
| P1 | Observation | Dataclass and dict state can diverge | `core/observation.py:11-39` | Typed canonical record + compatibility projection | One state representation | Medium |
| P1 | Token budgets | Seven estimators use incompatible algorithms | prompting, Engine, render, three histories | Labeled injectable token counter | Comparable budget decisions | Medium |
| P1 | JSON parsing | Generic repair and protocol salvage are copied/interleaved | `_json_repair`, parser utilities, evaluator, REPL | Conservative primitive + protocol layers | Consistent diagnostics, less code | Medium |
| P1 | Packaging | Optional imports and extras disagree | MCP/httpx, embeddings, cron, PDF, pgvector, `all` | Feature/extra matrix + clean install smoke | Reproducible optional features | Medium |
| P1 | MCP | Framework hand-rolls transport/session protocol | `mcp/stdio.py`; `mcp/http.py` | Official SDK parity spike behind QitOS bridge | Less protocol/lifecycle maintenance | Medium spike |
| P1 | Construction | Engine, AgentModule convenience, and builders compose runtime differently | 33-arg Engine; 19-input defaults merger | One typed composition root | Clear ownership and easier tests | Large |
| P1 | qita | Broken POST path is not executed by tests; module is monolithic | `_cli_app.py:364`; handler/string-only tests | Route integration tests, then seam-based split | User-facing correctness and safe evolution | Medium then Large |
| P1 | Local/process adapters | Compatible HTTP/process mechanics are reimplemented | `models/local.py`; scattered subprocess wrappers | Reuse OpenAI-compatible codec and env/process result | Fewer divergent paths | Medium |
| P2 | Functional API | Retry/timeout knobs are inert; executors are ownerless | `func/task.py`; `func/compose.py` | Complete and teach, or deprecate | Smaller, truthful API | Medium |
| P2 | Optional surfaces | Cron/PgVector/ops integrations are silent or under-proven | APScheduler fallback; asyncpg/psycopg2 mismatch | Admit, experimentalize, move, or remove | Lower maintenance and install risk | Medium |

## 7. Things We Should NOT Refactor

1. **Do not replace the QitOS lifecycle with a generic graph/state-machine
   library.** `observe -> decide -> act -> reduce -> check_stop` is the core
   research contract and already has QitOS-specific hooks, receipts, and replay
   requirements.
2. **Do not build parallel v2 public APIs beside existing APIs.** Migrations need
   adapters and one declared canonical owner, not `Legacy/New/Next` classes.
3. **Do not remove `qitos.trace` v1 before Task 05 proves dual-read/write parity.**
   qita and existing research artifacts depend on it.
4. **Do not collapse model retry, tool retry, and whole-step recovery into one
   policy.** Share mechanics and receipts; keep their semantics explicit.
5. **Do not make every tool asynchronous.** Many tools are blocking or process-
   based; explicit execution capability is more honest than coroutine wrappers.
6. **Do not replace provider-specific response handling with one universal JSON
   shape.** Provider-native continuation, reasoning, and item ordering must be
   preserved behind codecs.
7. **Do not add a generic `utils.py` or `common.py`.** Shared code should move
   only after an owning contract is identified: token counting to request
   policy, JSONL to tracing, process results to env/tool execution, JSON repair
   to protocol parsing.
8. **Do not split every long file solely by line count.** Split Engine and qita
   only at ownership seams with tests; otherwise the same shared state will be
   distributed across more files.
9. **Do not move domain recipes back into kit for reuse.** Framework mechanisms
   must remain expressible in agent-execution vocabulary alone.
10. **Do not expand the base dependency set for optional providers, databases,
    browsers, or evaluators.** Use tested extras and clear capability errors.

## 8. Delivery map

```text
Task 01 (closed baseline)
    ├── Task 02 model I/O ───────┐
    ├── Task 03 action/tool ─────┼── Task 04 context/artifacts ── Task 05 trace
    └── Task 08 quality ratchet ─┴── Task 09 lifecycle/errors
                                      │
                     Tasks 02–05 + 08–09 proven
                                      │
                             Task 10 consolidation
```

- Task 08 can start immediately and should land its baseline/CI work before
  large Task 02 or 03 diffs.
- Task 09 is a cross-cutting contract task. Provider changes land with Task 02,
  tool timeout changes with Task 03, trace-hook diagnostics with Task 05, and
  checkpoint/lifecycle conformance in Task 09-owned packages.
- Task 10 is deliberately last for most deletions. Consolidation follows proven
  canonical contracts; it does not invent them.

## 9. Audit acceptance and re-audit cadence

This audit is complete when its findings are represented in the active plan and
architecture debt, not when every issue is fixed. Each Task 08–10 work package
must update this document's opportunity status or link a superseding decision.

Re-run the engineering audit at these boundaries:

1. after Task 08A establishes the committed static baseline;
2. after Tasks 02 and 03 stabilize conversation and outcome contracts;
3. before deleting v1 trace or deprecated benchmark compatibility;
4. before the next minor release candidate.

Future audits must report both absolute repository findings and the delta from
this snapshot. A smaller checked surface is not an improvement.
