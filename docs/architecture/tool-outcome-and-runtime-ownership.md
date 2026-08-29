# Tool outcome and runtime ownership (ADR C1)

Status: accepted; C1-R3 collision-safe projection hardening qualified
Schema versions: `qitos.tool_result/v1`, `qitos.tool_result.model_view/v1`,
`qitos.tool_result.trace_safe/v1`, `qitos.runtime_lifecycle/v1`,
`qitos.durability_receipt/v1`
Decision owners: Task 03A and Task 09A

## Decision

QitOS has one canonical action/tool outcome: the existing
`qitos.core.tool_result.ToolResult`. C1 evolves it in place. It does not add a
third envelope, a `V2` class, or `qitos.kit.aci`.

`ActionResult` remains the executor's compatibility record during migration.
The action runtime converts it immediately with
`ToolResult.from_action_result()`. If a tool already returned a typed
`ToolResult`, that nested result is authoritative and the adapter adds only
missing dispatch identity/timing metadata. Reducers, observations, model
projection, fixtures, and future trace integration consume `ToolResult`.

The v1 result represents:

- `tool_name` and `action_id` identity;
- the closed terminal status set `success|error|skipped|timed_out|cancelled`;
- canonical `output` and explicit model-facing `model_output`;
- `error_kind`, stable `error_code`, `recoverable`, and `recovery_hint`;
- validated `next_action` (`name`, object-valued `args`, optional `action_id`);
- `complete`, `truncated`, and non-negative named `omitted` counts;
- `attempts`, `latency_ms`, and honest `worker_still_running`;
- declared effects, filesystem changes, artifact-reference slots, normalized
  request metadata, provenance, and compatibility metadata.

`artifact_refs` intentionally remains a serialized `list[dict]` slot in C1.
Lane B owns the eventual `ArtifactRef` type and store; C1 neither exposes host
paths nor creates a competing artifact abstraction.

## Serialization and compatibility

`ToolResult.to_persistence_dict()` is the canonical serializer;
`ToolResult.to_dict()` is its compatibility name. It emits only declared v1
fields and never flattens arbitrary dictionary output keys into the envelope.
`ToolResult.from_canonical_dict()` is the strict parser. It rejects unknown
versions and fields, malformed list/dict slots, non-JSON values, invalid scalar
types/ranges, and contradictory terminal state. In particular:

- success carries no error fields and cannot report a running worker;
- error requires a semantic, execution, or policy `error_kind` plus a stable
  non-empty `error_code`;
- skipped requires `error_kind=policy`;
- timed out and cancelled require `error_kind=execution`;
- `worker_still_running` is legal only for timed out work;
- attempts and omitted counts are non-negative integers (booleans are not
  integers here), while latency is finite and non-negative.

JSON serialization failure raises typed `ToolResultContractError` with a stable
code. The action runtime converts an invalid tool return into an execution
outcome at that boundary rather than serializing with `default=str` or aborting
the whole action batch.

Legacy compatibility is separate. `ToolResult.to_legacy_dict()` is the only
projection that can flatten output, and `ToolResult.from_legacy_value()` is the
permissive adapter. `from_value()` first discriminates any payload containing
`schema_version` and sends it to the strict parser; versioned bad data never
falls through to guessed legacy repair. The current flattened consumers are
legacy reducers/examples reading result keys directly from the `Observation`
mapping. `Observation.to_legacy_dict()` supplies that projection explicitly;
canonical observation serialization remains nested.

The accepted inputs are therefore:

1. an existing `ToolResult`;
2. an `ActionResult` through the named adapter;
3. strict canonical v1 dictionaries;
4. unversioned legacy dictionaries with `status`, `error`, `message`, or
   `output.model_summary`;
5. strings and arbitrary values as legacy successful output.

Unknown legacy statuses are mapped conservatively. `model_summary` remains
readable but is normalized to `model_output`; canonical `output` is never
replaced by any projection.

## Model and trace-safe views

`ToolResult.to_model_dict(max_chars=...)` produces an allowlist model view. Its
fields are version, terminal status, bounded/redacted `model_output`, redacted
error and recovery text, stable error code, recoverability, validated/redacted
next action, and call identity. When a tool has no explicit `model_output`, the
fallback is a deterministic redacted and bounded text rendering; the canonical
raw output object itself is not inserted into model messages.

Metadata, normalized request, provenance, exception representations, host
paths, credentials/headers/tokens, unrestricted artifact dictionaries,
filesystem changes, and declared-effect internals are absent. Error content is
charged to the same per-result/aggregate text budget. A zero remaining budget
emits an empty projection, not an oversized truncation card. Action events,
hooks, native tool history, and environment observation events use this view;
they do not derive it by replacing fields in the persistence dictionary.

`ToolResult.to_trace_safe_dict()` is a bounded, versioned ToolResult-only handoff
for Lane D. It adds completeness/timing/worker facts and a `loss` object naming
excluded fields, redaction counts, and omitted characters. It is not a full
trajectory privacy policy and makes no claim about other event payloads.

C1-R3 applies the same rules to mapping keys at every visible depth. A key that
matches credential/header/token names or secret/path text becomes a
deterministic ordinal placeholder. Allocation is stable for the same mapping
and skips both caller-supplied placeholder-like keys and placeholders already
allocated in that mapping, so entries cannot collide or overwrite one another.
The placeholder contains neither the raw key nor its hash. Benign keys stay
unchanged, and values retain their recursive structure while secret-bearing
content is redacted and counted.

Trace-safe `omitted` is no longer copied from canonical persistence. It uses the
same collision-safe key projection and retains only entries that fit the
remaining per-result character budget. Every redacted key, omitted entry, and
omitted character is recorded in the `omitted` field facts and aggregate totals.
Canonical `qitos.tool_result/v1` persistence remains lossless and unchanged;
model-view and trace-safe version identifiers remain v1.

Until Lane B publishes `ArtifactRef`, canonical `artifact_refs` is an array of
objects with required non-empty `artifact_id` and optional `media_type`,
`byte_length`, `encoding`, `sensitivity`, and object-valued `provenance`.
Unknown keys, including host-path slots, fail canonical parsing.

## Failure and validation boundary

There is no `validation_mode="soft"`.

### Pre-execution hard gate

The registry/executor rejects before invoking a tool when any of these fail:

- arguments are not a JSON object;
- required fields are absent;
- a value violates a declared JSON primitive/container type;
- `additionalProperties: false` is violated;
- the permission pipeline/tool permission decision denies or requires input;
- an installed security policy rejects the call.

Structural failure is an execution-boundary error. It uses stable codes such as
`invalid_arguments_shape`, `missing_required_argument`,
`invalid_argument_type`, and `unexpected_argument`; the tool is not called.
Tool-specific `validate_input()` remains a hard gate for compatibility and
safety-sensitive local constraints.

The mechanically supported schema subset was derived from repository
`ToolSpec.input_schema` producers: top-level object, properties, required,
primitive/container type (including type arrays), nested objects, array items,
boolean or schema-valued additionalProperties, anyOf, oneOf, enum, and the
repository's OpenAPI-style nullable flag. Annotation-only title, description,
default, examples, comment, deprecated, readOnly, and writeOnly keys are
accepted. Unknown types or acceptance-changing unsupported keywords fail with
`schema_contract_violation`; malformed schemas are distinguished from invalid
arguments. The registry and executor use the same validator, and the executor
revalidates after interceptor and permission argument rewrites.

### Post-dispatch typed semantic result

A tool that successfully ran but discovered a user/domain problem returns
`ToolResult.semantic_error()`. Examples include missing path, stale snapshot or
version, invalid regular expression, unavailable backend, partial result, and
recoverable user input. Such a result has `status="error"`,
`error_kind="semantic"`, a stable code, recovery fields, and optional validated
`next_action`; it is data, not an implementation exception.

### Execution/programmer failure

Implementation exceptions, malformed result contracts, and impossible internal
states use `error_kind="execution"`. They are never recast as a successful
semantic result. Redacted diagnostics may be model-facing, while exception
objects, secrets, raw authorization values, and unrestricted host paths stay
out of public fixtures and trace-safe projections.

## Runtime lifecycle ownership matrix

“Borrowed” means the framework may use but must not close the resource.
“Owned” means the named creator must provide the terminal cleanup path. Native
methods remain authoritative; the matrix does not introduce a universal public
lifecycle interface.

| Resource | Creator | Owner / borrower | Open / start | Close / shutdown | Partial-open failure | Repeated close | Timeout / deadline | Cancellation | Failure surface | Current tests | Planned package |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Action batch `ThreadPoolExecutor` | `ActionExecutor._execute_segment_concurrently` | executor owns | context entry / `submit` | context exit drains | context manager closes after submit failure | local instance, one close | no batch deadline; per-action policy only | queued futures only; running futures drain | slot `ActionResult`, defensive missing-slot card | `tests/engine/test_issue35_action_contract.py`, `tests/engine/test_concurrent_execution.py` | 09C conformance |
| Timed sync-tool worker pool/thread | `ActionExecutor._call_tool_with_timeout` | executor owns pool; worker is abandoned after deadline | pool construction / `submit` | `shutdown(wait=False)` | `finally` shuts pool | local instance, one close | action/tool deadline | cannot kill running Python thread | `timed_out`, `worker_still_running=true`; late result not committed | `tests/engine/test_issue35_action_contract.py` | 09C late-commit proof |
| Generic background thread | concrete subsystem (checkpoint, REPL spinner, coding background task) | creator owns | subsystem-specific `start()` | subsystem-specific stop/join | creator unwinds already-open children | must be idempotent per owner | bounded join required | cooperative event where available | owner receipt/log; never implied cancellation | `tests/test_bounded_queues.py`, REPL/tool tests | 09F per-owner conformance |
| Tool subprocess | concrete tool/Env operation | call owns `run`; `Popen` owner is implementation | `subprocess.run/Popen` | communicate/wait/terminate/kill as implementation supports | close pipes/kill child created here | process-state guarded | tool/process timeout | process termination can be hard when owned | typed semantic backend error or execution failure; stdout/stderr retained per policy | tool/env suites | 03C/09C, not C1 |
| Asyncio bridge | Engine/model/MCP/action entry point | sync boundary owns bridge loop/thread; returned awaitable belongs to caller until handed off | await directly, `asyncio.run`, or explicit worker depending context | await completion; close rejected coroutine | close coroutine created but not scheduled | local bridge only | `asyncio.wait_for` where declared | task cancellation only, not arbitrary thread cancellation | typed timeout/bridge execution error | issue35 async tests, MCP tests | 09C consolidation decision |
| HTTP/async client | provider or `MCPServerStreamableHttp` constructor | internally created client is owned; injected client is borrowed | client construction/connect | `close/aclose` only for owned client | close client if handshake fails after allocation | native close should be repeat-safe | configured request deadline | transport/task-dependent | typed provider/MCP failure, redacted request IDs | provider tests, `tests/mcp/test_mcp.py` | 09B/09F; no C1 transport change |
| MCP stdio | `MCPServerStdio.connect` | server instance owns spawned subprocess | create subprocess + initialize handshake | `cleanup`: terminate, bounded wait, then kill | handshake failure must clean spawned process | current `_process=None` guard | cleanup 5 s; requests currently unbounded | owning process may terminate; request cancellation incomplete | MCP error/cleanup exception | `tests/mcp/test_mcp.py`, `tests/mcp/test_agent_mcp_integration.py` | 09F SDK parity spike |
| MCP HTTP | `MCPServerStreamableHttp.connect` | server owns internally created `AsyncClient` | client create + handshake | `cleanup/aclose` | handshake failure currently leaves client for caller cleanup | `_client=None` guard | httpx 30 s | asyncio/transport dependent | HTTP/JSON-RPC exception | `tests/mcp/test_mcp.py` | 09F partial-open test |
| Host Env | Engine/user | usually borrowed service; owns no persistent external process | `setup/reset` | no-op unless a concrete Env owns resources | setup raises; no child cleanup normally | no-op | command call timeout | owned subprocess call only | `EnvStepResult`/tool semantic result | `tests/test_env_host_and_engine_interpretation.py` | 09F conformance |
| Docker Env | user/Engine; optional auto-create | borrowed existing container; owns only `_created_here` container | `setup/_ensure_container` | `close`, remove only when created here and configured | failed create/start must not remove borrowed container | close must remain harmless after removal | bounded Docker CLI calls | can remove owned container; not borrowed one | health/error result or setup exception | `tests/test_docker_env.py` | 09F ownership tests |
| Cron scheduler | `CronScheduler` | scheduler owns internally created APScheduler; injected callback borrowed | lazy first valid scheduled job | `shutdown(wait=False)` | import/invalid cron currently degrades silently | `_started` guard | no close deadline | scheduler-native job cancellation | currently missing dependency/invalid schedule may be silent | cron tool coverage is limited | 10C/10D admission decision |
| Checkpoint queue/worker | `DurabilityManager(ASYNC)` | manager owns queue and daemon worker; store borrowed | constructor starts worker | `flush`, `shutdown` | constructor start failure propagates | repeated shutdown behavior under-specified | worker join 10 s | cooperative shutdown event; queued writes not cancellable safely | logs/drop/swallowed store exception today | `tests/test_bounded_queues.py`, `tests/checkpoint/` | Task 09D; no C1 behavior change |
| Trace processor chain | `TracingProvider` or global provider | provider owns configured chain only by configuration convention; processor resources may be caller-supplied | provider construction/add | `shutdown`, `force_flush` | child failure logged and fan-out continues | implementation-specific, not guaranteed | no deadline | none generally | logged best-effort failure | `tests/tracing/`, W&B/MLflow processor tests | Lane D 09E + C 09F |
| Engine event stream | `AsyncEngine.arun_stream*` | AsyncEngine owns primary stream; subscriber queues borrowed | create before worker task | `close` in worker/finally | run setup failure closes in worker path | `_closed` makes repeat close safe | consumer/run deadline external | run task cancellation; full queue can drop sentinel | dropped events/sentinel currently silent | `tests/test_bounded_queues.py`, stream tests | Lane D 09E receipt semantics |
| Model token stream | model adapter; consumed by Engine | adapter owns transport iterator; Engine borrows iterator | `stream/astream` request | iterator/context close per SDK | provider must close response on decode failure | SDK-specific | request/model deadline | SDK/task-specific | typed model failure owned by Lane B | provider/streaming tests | 09B with Lane B |
| `qitos.func` task executor | `TaskFunction.submit` or `_Composer` | caller-supplied executor borrowed; implicit executors owned but currently leaked | `ThreadPoolExecutor` construction | no close today | allocation/submit failure has no explicit cleanup | undefined | public timeout knob inert | future cancellation only before run | raw future exception | `tests/func/test_functional_api.py` | Task 10C decision, no C1 behavior change |
| Agent background executor | `AgentTool` | tool owns its persistent pool | constructor | shutdown path requires audit | constructor failure local | undefined | per-task future timeout | future cancellation limitations | tool result/future exception | agent tool tests | 09F later package |

## Durability race finding (C1 investigation)

The historical test fills the live ASYNC queue and then expects `flush()` to
observe `queue.Full`. The worker concurrently executes `get()`. A valid
interleaving is:

1. the test fills the last slot;
2. the durability worker removes one item;
3. `flush()` calls `put_nowait(None)` and succeeds;
4. no “queue full during flush” warning exists.

Therefore queue fullness before `flush()` is not a stable precondition for the
sentinel insertion. The deterministic regression test uses events to prove this
interleaving without sleeps: the worker removes the item and blocks inside the
fake store, `flush()` enqueues its sentinel, then the store is released. This
proves the race window; it does not change `DurabilityManager`.

Task 09D must choose one explicit ASYNC overflow policy:

- block with a caller deadline;
- reject with an observable receipt; or
- lossy drop with an observable receipt.

For flush, the preferred candidate is a monotonic accepted/completed sequence
barrier (or `queue.join()` plus retained failures) that returns an incomplete
receipt on deadline. A sentinel whose insertion can fail cannot prove a drain.
The legacy `put()` return type remains unchanged until the compatibility plan is
reviewed.

## Versioned fixtures and handoffs

Fixtures live under `tests/fixtures/tool_results/v1/`:

- `canonical_outcomes.json`: success, semantic error, execution error,
  permission skipped, timeout with continuing worker, cancellation, missing
  parallel slot, retries, truncation/continuation, filesystem effects,
  artifact-reference slot, and legacy/model-summary compatibility;
- `durability_receipts.json`: accepted, queued, persisted, failed, and dropped;
- `lifecycle_receipts.json`: repeated shutdown and borrowed-resource-open.
- `contract_hardening.json`: unknown-version, contradictory-state and malformed
  canonical rejections plus executable host-path/token key, nested mapping,
  collision, pre-existing placeholder, next-action, omitted-budget, and loss
  expectations.
- `qualification-evidence.json`: producer-owned G1 probes for recursive JSON
  admission, nested ownership isolation, all-field redaction, and per-field loss
  accounting. Lane D must bind this exact committed file and fixture rather than
  trusting an unverified success flag.

Lane B consumes `to_persistence_dict()`, `from_canonical_dict()`,
`from_legacy_value()`, `to_model_dict()`, the allowed `artifact_refs` shape,
status/error mapping, and the timeout receipt. Lane D consumes
`to_trace_safe_dict()` plus its exact fixture, durability and
lifecycle failure fields. Before trace persistence, Lane D must redact secrets,
authorization material, raw exception objects, unrestricted request payloads,
and host-local paths; only stable codes, declared public refs, redacted
diagnostics, and correlation identifiers cross that boundary.

Every structural tool boundary first enforces recursive JSON values: object keys
must be strings and floats must be finite. This check precedes interceptor,
permission-pipeline, tool permission, semantic validation, and tool execution.
ToolResult owns a recursive copy of all accepted JSON trees, and every serializer
returns another recursive copy. Model and trace-safe projections share one text
budget and account redaction or omission separately for model output, errors,
recovery hints, identifiers, next actions, and trace-safe omitted data. The
accepted C producer commit is
`d50f41fb3b8190a953f9f37f278bf0b197af286b`.

## Consequences and deferred behavior

- Existing dict/string tool returns remain compatible.
- Flattened result compatibility is explicit rather than part of canonical
  persistence.
- Model projection becomes explicit without losing canonical structured output.
- No resource is forced into fake `close/aclose` methods.
- C1 does not claim hard thread cancellation, durable ASYNC acceptance, or MCP
  SDK parity.
- Tool behavior refactors, durability receipts, lifecycle implementations, and
  functional API disposition remain in Tasks 03B/C, 09C/D/F, and 10C.
