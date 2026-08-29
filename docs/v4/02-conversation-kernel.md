# Task 02 — model I/O transaction kernel

Status: Task 02A candidate integrated for G1 convergence; Tasks 02B–02E remain pending
Depends on: Task 01
Unblocks: Task 04, Task 12 durable snapshots, and Task 05
Risk: high — core persistence and every provider adapter

---

## 1. Goal

Replace ad-hoc message assembly with one provider-neutral transaction model
without flattening provider-native continuation state. Researchers should be
able to inspect what happened, control what enters the next request, preserve
reasoning when a provider requires it, and steer a running agent at safe
boundaries.

## 2. The three-layer contract

### 2.1 Persistent `ExchangeLog` — core

Location: `qitos/core/conversation.py` or a better name chosen in the Task 02A
plan. It stores completed facts only and is append-only.

Required properties:

- multimodal content uses existing QitOS content blocks, not `str` only;
- assistant output is an ordered sequence of text, reasoning references, and
  tool calls, preserving provider order;
- each tool call stores raw arguments, parsed arguments when valid, and parse
  status;
- a tool batch remains open until every call has one result;
- missing/interrupted results are explicit synthetic results with provenance;
- tool-call IDs are unique within their provider scope;
- human steering is a distinct entry type;
- provider-native continuation attachments are opaque, typed by provider and
  never reformatted into user-visible reasoning text.

`HistoryMessage` remains a compatibility adapter during v4. It is not the new
source of truth after Engine migration.

### 2.2 Ephemeral `RequestView` — engine

A request view is derived for one model call. It may select exchanges, apply a
budget, add transient `ContextBlock`s, and include queued steering. It is not
written back into the persistent log merely because a provider requires a
particular message placement.

Required policies:

- exchange-safe selection and compaction;
- deterministic budget report;
- stable prefix/cache-anchor report;
- steering accepted only after a completed tool batch;
- explicit reasoning mode: drop, inline replay, signed block replay, or native
  item continuation;
- no `MERGE_TOOL` mutation of historical records.

### 2.3 Provider codecs — models

Each provider module owns its request/response codec beside the transport it
serves. Do not create a second giant `qitos/models/compilers.py` parallel to the
existing provider adapters.

Codecs must:

- compile a `RequestView` to provider payloads;
- decode provider output into ordered exchange items;
- preserve required signed/encrypted/native continuation data;
- emit a `CodecReport` describing preserved, dropped, synthesized, and merged
  fields;
- keep Chat Completions and Responses behavior separate where their state
  models differ;
- reject unsupported policy/capability combinations instead of silently
  degrading.

## 3. Parallel tool calls

Native parallel execution is already present through `Decision.actions` and
ActionExecutor. This task does not create a scheduler. It closes protocol gaps:

- one assistant item can declare N ordered calls;
- results correlate by call ID and return in declaration order;
- execution failure, permission block, timeout, or missing worker each closes
  its slot explicitly;
- human steering received mid-batch is queued until the batch is closed;
- max actions is configuration/capability driven, not a universal value of 4.

## 4. Work packages

### 02A — contracts and invariants

- Write the detailed internal plan and an API decision record.
- Add ordered exchange types, validation errors, batch builder, and adapters
  from/to `HistoryMessage`.
- Unit-test multimodal content, duplicate IDs, raw/parsed arguments, synthetic
  results, and incomplete batches.
- Do not touch provider payload builders yet.

#### 02A evidence (Lane B / B1)

- Decision record and compatibility matrix:
  `docs/internal/plans/lane_b_conversation_context.md` (`B1-ADR-001`).
- Module-level contract: `qitos/core/conversation.py`; it is intentionally not
  exported from `qitos.core.__init__` or the root package in this wave.
- Schema `qitos.exchange_log.v1` preserves ordered multimodal/assistant items,
  provider-scoped call IDs, raw and parsed argument states, batch identities,
  typed terminal results, synthetic provenance, queued steering, and opaque
  continuation attachments.
- `ToolBatchBuilder` accepts out-of-order completion but commits results in call
  declaration order. An incomplete batch rejects the next normal transaction;
  queued steering is committed once after closure.
- The strict `HistoryMessage` adapters preserve compatible fields without
  changing the legacy dataclass. Unsupported reasoning replay or assistant
  interleaving raises a typed conversion error instead of flattening data.
- Lossless persistence and safe/public projection are separate: persistence
  retains opaque provider payloads while `to_safe_dict()` redacts them. Signed
  or encrypted reasoning is never converted into assistant text.
- Versioned semantic handoff fixtures live in
  `tests/fixtures/conversation/v1/semantic_fixtures.json`; Lane C-like execution
  and Lane D-like persistence consumers both exercise them in
  `tests/core/test_conversation.py`.
- Engine/provider/checkpoint/request-view paths and defaults remain unchanged.
  The branch must still rebase onto the integration HEAD containing Lane A/A1
  and pass its ratchet before it can be described as merge-ready.

### 02B — request-view and capability policy

- Add request-view selection and reporting in `qitos/engine/`.
- Separate human steering from control context.
- Define provider capabilities by transport/API mode, not only family name.
- Keep `EngineConfig` as a serializable runtime snapshot; introduce a dedicated
  conversation/request policy input instead of overloading that snapshot.

### 02C — provider codecs

- Migrate OpenAI Chat and Responses first, then Anthropic, then Gemini/GLM.
- Keep small semantic fixtures rather than full SDK payload snapshots.
- Add explicit tests for signed/opaque reasoning and heterogeneous Responses
  items.
- Add opt-in live `e2e` cases; offline tests remain authoritative in CI.

### 02D — Engine and checkpoint migration

- Make `_model_runtime` consume the new layers and delete duplicated assembly.
- Supply a versioned ExchangeLog snapshot component to Task 12; do not write an
  independent conversation checkpoint or use `run_id` as session identity.
- Persist queued steering, open/partial batch state, completion order, and opaque
  continuation references with a v1 adapter.
- Preserve old public model-call behavior until deprecation is announced.
- Update trace events to include request/codec reports without sensitive data.

### 02E — preset rollout and cleanup

- Enable new defaults only for transport/preset combinations that pass the
  conformance matrix.
- Decide the GLM multi-action default here, based on evidence.
- Delete superseded builders only after compatibility tests and migration docs.

## 5. Acceptance criteria

- [ ] A completed multi-turn parallel-tool exchange round-trips losslessly in
  the canonical model.
- [ ] OpenAI Chat, OpenAI Responses, Anthropic, and Gemini/GLM fixtures pass.
- [ ] Required native reasoning/continuation data survives; unsupported replay
  raises a typed error.
- [ ] Multimodal blocks and assistant item order are preserved.
- [ ] Mid-batch steering is queued and appears exactly once at the next safe
  boundary.
- [ ] Persistent history is unchanged by provider-specific context placement.
- [ ] v1 checkpoint/history fixtures migrate and resume.
- [ ] Task 12 can restore the ExchangeLog and queued steering through a fresh
      process without retaining the original Engine/provider object.
- [ ] Existing parallel executor behavior and ordering tests remain green.
- [ ] Two independent consumers exercise the public contract.

## 6. Verification

```bash
pytest -q tests/core/test_conversation.py
pytest -q tests/engine/test_request_view.py tests/engine/test_model_runtime_conversation.py
pytest -q tests/models/test_conversation_codecs.py
pytest -q tests/checkpoint
pytest -q
flake8 qitos/core qitos/engine qitos/models qitos/trace
mypy qitos/core qitos/engine qitos/models qitos/trace
```

Test paths may be split by provider, but the categories and invariants above are
mandatory.

## 7. Stop-and-escalate decisions

Stop for review before:

- changing public `HistoryMessage` semantics rather than adding an adapter;
- exposing provider-native encrypted/signed fields through public serialization;
- flipping any family preset default;
- adding a provider-neutral field that only one codec consumes;
- rewriting checkpoint formats without a tested migration path;
- introducing a conversation-owned session store or persisting a live provider
  client instead of a typed resolver/continuation reference.
