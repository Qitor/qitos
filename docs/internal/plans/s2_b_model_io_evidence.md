# S2 Lane B model I/O evidence

Status: offline contract qualified

Producer commit: `60e8d94edb9a5f00434095a3489e1e1100185bea`

Baseline: `446a347d1ac73636476ca2515a01da601b567c68`

Read-only ledger successor: `47cd4dc5e1ed1b2b0d244bfc90fac031ec55be32`

Branch: `codex/v4-s2-b-model-io`

## Qualified outcome

The real synchronous Engine model transaction now has one canonical flow:

```text
ExchangeLog
  -> explicit context contribution and selection
  -> immutable RequestView
  -> adapter-declared capabilities and provider-owned codec
  -> optional JSON request transform
  -> transport or stream transport
  -> ProviderDecodedResponse or ProviderFailure
  -> ExchangeLog
```

`HistoryMessage` and OpenAI-shaped dictionaries are isolated compatibility
inputs/outputs. They do not own conversation truth. A successful decoded
assistant item is appended only after the complete provider transaction;
provider failure exits through a typed exception and sanitized event fact.

## Provider extension boundary

`qitos.models.provider.ProviderAdapter` declares the request target,
capabilities, codec, sync/stream transport, and failure normalization.
`ConversationProviderCodec` owns encode, continuation application, and ordered
response decode. `RequestTransform` is a replaceable JSON-only post-codec
extension. `ContinuationResolver` owns opaque payload capture/resolution while
the conversation/snapshot contains only logical identity, resolver key,
digest, target scope, attachment identity, and expiry.

The independent `AcmeAdapter` fixture is not a `Model` subclass and passes the
same transaction protocol used by official adapters, including streaming,
ordered reasoning/text/multiple calls, transport options, a custom request
transform, codec reporting, and sanitized failure.

## Official provider matrix

The exact offline-declared matrix is in
`tests/fixtures/s2/lane_b/provider-capability-matrix.json` and is checked
against live adapter declarations without contacting providers. OpenAI Chat
Completions and Responses are separate codecs. Anthropic Messages and Gemini
generateContent preserve their native reasoning continuation shapes. LiteLLM,
Ollama, LM Studio, and vLLM remain conservative where backend/model support
cannot be proved by configuration alone.

This matrix is an offline contract qualification, not a live-key or model-
specific service qualification.

## Message and context semantics

The ordered assistant part vocabulary now includes distinct
`ReasoningBlock`, text/multimodal `AssistantContent`, and multiple `ToolCall`
parts. Provider scope plus call ID remains stable, while batch declaration and
completion order are reported separately. Opaque provider continuation bytes
remain resolver-owned.

Context has explicit contributor identity/provenance, deterministic
collection, declared unit budgets, replaceable selection/budget/compaction
policies, required-context failure, and selection/compaction receipts. The
conformance suite covers a request-aware structured contributor and a legacy
zero-argument contributor with a different output shape, plus runtime
instruction and artifact-reference contributors.

## Steering and continuation

Steering receipts preserve stable sequence/item identity, queue only behind an
open tool batch, survive a conversation snapshot round trip, reconcile at a
safe boundary, and remain applied exactly once on repeated reconciliation.
Completed, failed, and cancelled session states return typed rejected
receipts. Lane A remains responsible for durable Session assembly.

Continuation references bind provider, exact model, and API mode. Resolver
miss, expiry, digest mismatch, and target mismatch are explicit. Stateless
replay is available only with explicit loss acceptance and records
`continuation.state` plus `fallback=stateless_replay` in `CodecReport`.

## A/C/D handoff

Lane A consumes `ConversationSnapshotComponent` (`qitos.conversation_component/v1`):
the canonical ExchangeLog, steering receipts, continuation refs, context
selection, compaction receipts, artifact refs, reconstruction requirements,
and component digest. Lane B does not copy these into Session fields.

Lane C consumes `RequestView.correlation_facts`: `batch_id`, stable provider-
scoped call IDs in `declaration_order`, independently observed
`completion_order`, and `provider_scopes`. Lane B does not modify tool
execution or result contracts.

Lane D consumes sanitized model-runtime event stages:

- `request_view`: complete provider-neutral request and selection facts;
- `provider_transaction`: request/assistant identity, codec report, and
  conversation-component digest;
- `provider_failure`: typed sanitized failure, correlation digest, and optional
  codec report.

Raw responses, SDK exceptions, headers/cookies, credentials, endpoints, and
host paths are not emitted by these facts.

## Exact fixtures

All three producer fixtures were committed by
`60e8d94edb9a5f00434095a3489e1e1100185bea`:

| Fixture | SHA-256 |
| --- | --- |
| `tests/fixtures/s2/lane_b/provider-capability-matrix.json` | `41f07ab2f383238f208550d1b3081ab11d3c59146788b04e8dbaa34b4fd19cca` |
| `tests/fixtures/s2/lane_b/semantic-contracts.json` | `5dbde62e9d35dd3021a4a07c3ea504c2653a7ab0f73f14ab5798011cc1596fac` |
| `tests/fixtures/s2/lane_b/unsupported-loss-matrix.json` | `87e2ea70b4dae30aa3394f6ed853c262e7f0c0f3c9596ac0e03ae25f4771a893` |

The machine-readable receipt is
`tests/fixtures/s2/lane_b/evidence.json`. The unsupported/loss fixture is the
authoritative offline matrix for typed rejection and explicitly accepted loss.

## Validation evidence

The producer commit was qualified with:

- required conversation/request/codec suite: 93 passed;
- Lane B provider/context/continuation/steering conformance: 34 passed;
- `tests/engine -k "model or context or protocol"`: 35 passed, 164 deselected;
- architecture/public-surface/local-path ratchets: 10 passed;
- full suite: 2138 passed, 50 skipped;
- static quality ratchet: passed with the existing baseline only;
- flake8: passed;
- mypy: passed for 86 source files;
- `git diff --check`: passed.

No live provider keys were used. No provider is claimed live-qualified.

## Unsupported claims and integration gaps

- The historical direct `model(messages)` compatibility APIs remain available;
  the Engine transaction path is the qualified typed-failure boundary.
- Backend/model-specific LiteLLM and local-model capabilities remain
  conservative until an adapter configuration explicitly declares more.
- Durable continuation storage and Session lifecycle assembly belong to Lane A;
  this lane provides resolver/component contracts and process-local defaults.
- The beginner `AgentModule(model=..., tools=..., instructions=...)` constructor
  spelling requires integration-owner work in the Lane A-owned AgentModule
  surface. Existing `llm`, tool registry, and prompt bundle inputs already flow
  through the unified transaction.
- Async Engine convergence and live-provider streaming qualification are not
  claimed by this synchronous Lane B producer.
- Shared README, changelog, progress ledger, and integration files were not
  edited because they are outside the Lane B file lease.
