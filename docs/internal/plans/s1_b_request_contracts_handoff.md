# S1 Lane B request-contract producer handoff

Status: local producer published; `waiting_on_lane_a`; not cross-lane qualified
Updated: 2026-08-30
Source baseline: `c1efb0f4adde3e673bf181af5b1760c19a451ae2`
Producer commit: `86b6f41ed68b4775a6e974c05200a6a76748d742`

## Published contracts

| Contract | Version | Owner/source |
|---|---|---|
| ExchangeLog | `qitos.exchange_log.v2` | existing `qitos.core.conversation` canonical truth |
| RequestView | `qitos.request_view/v1` | `qitos.core.request_view.RequestView` derived immutable request |
| Request builder | `qitos.exchange_request_builder/v1` | ExchangeLog-safe deterministic selection |
| Provider capabilities | `qitos.provider_capabilities/v1` | `qitos.models.codec.ProviderCapabilities` |
| CodecReport | `qitos.codec_report/v1` | `qitos.models.codec.CodecReport` |
| Provider failure | `qitos.provider_failure/v1` | typed exception boundary, never assistant text |
| Conversation component | `qitos.conversation_component/v1` | Lane B checkpoint-v2 component producer |
| Fixture envelope | `qitos.request_contract_fixture/v1` | direct stable fixture path |

`RequestView` contains ordered selected item projections, instruction roles,
tool schemas, target transport/API identity, required capabilities, separate
reasoning and continuation policies, deterministic context budget/selection,
compaction receipts, ArtifactRef references, steering boundary, parallel-call
correlation facts, and source provenance/digest. Its arbitrary JSON fields are
stored internally as canonical JSON text, so neither constructor inputs nor
returned inspection dictionaries alias the immutable boundary.

## Codec protocol and report

Every provider codec implements only `ProviderCodec.encode(request, ...)` and
returns `(provider_payload, CodecReport)`. Concrete codecs remain beside their
provider transport; this package deliberately does not add a cross-provider
compiler or switch dispatch. Default capability input is derived from the
configured model through `ProviderCapabilities.from_model()`.

`CodecReport` records supported/unsupported capabilities, reasoning outcome,
multimodal and tool-schema conversion, continuation outcome, selected/omitted
context, compaction receipts, lossy fields, warnings, fallback, and exact
provider/model/transport/API identity. `validate_codec_result()` rejects an
unsupported capability and rejects every lossy field unless the caller passes
`allow_loss=True`. Stateless continuation replay is represented by
`fallback="stateless_replay"`; it is never inferred silently.

## Steering contract

`submit_steering()` accepts plain text and allocates the internal item/receipt
identity. While a tool batch is open the item remains in ExchangeLog's durable
queue. Closing the batch appends queued items once in submission order.
`reconcile_steering_receipts()` changes a matching queued receipt to `applied`
exactly once and is idempotent after restore. Completed, failed, and cancelled
session states return typed `rejected` receipts without mutating ExchangeLog.

Lane A owns the eventual `session.steer(text)` façade, session lifecycle state,
and public receipt delivery. Lane B does not copy those identities.

## Continuation contract

`ContinuationRef` stores only a logical resolver key plus provider, exact model,
API mode, optional attachment correlation, payload digest, and expiry metadata.
It contains no credential, SDK object, client, or opaque token. A mismatch in
provider/model/API mode raises `incompatible_continuation`. Missing or expired
resolution remains a typed codec/provider failure. A snapshot component accepts
an ExchangeLog continuation attachment only when its payload is exactly
`{"resolver_ref": <reference_id>}` and the matching `ContinuationRef` exists.

Reasoning replay and continuation are independent fields and outcomes. Existing
G1 opaque attachments with inline payloads remain readable by the ExchangeLog
compatibility path but are typed-rejected by the new snapshot component until a
resolver migration externalizes them.

## Context and artifact contract

`ContextContributor` is an explicitly injected protocol returning immutable
`ContextContribution` records. Each contribution declares source, digest,
priority, placement, horizon, sensitivity, model visibility, runtime-context
visibility, revision, and whether omission is legal. Selection uses complete
ExchangeLog exchanges, keeps protected recent exchanges, and reports all
selected/omitted items, exchanges, categories, contributions, units, and
reasons. RequestView does not own or persist semantic memory.

`ArtifactRef` contains content identity, resolver key, media type, byte length,
encoding, sensitivity, provenance digest, optional model summary, and required
behavior. It never contains artifact bytes or a host path. A missing required
artifact raises `missing_artifact` before encoding.

`CompactionReceipt` records input exchange IDs, output digest, policy, model
reference, and declared losses. This S1 contract does not implement full Task 04
compaction, memory integration, or an artifact store.

## Conversation snapshot component

`ConversationSnapshotComponent` contains exactly:

- the one ExchangeLog serialization, including queued steering and partial
  parallel results already canonical there;
- steering receipts correlated by item identity;
- resolver-backed continuation references;
- context selection state;
- compaction facts;
- ArtifactRef references;
- reconstruction requirements;
- component schema version and a deterministic SHA-256 integrity digest.

The component creates no store and owns no session/run/work/checkpoint identity.
Checkpoint v2 and the immutable envelope remain Lane A's sole persistence truth.

## Fixture manifest and exact digests

- Fixture:
  `tests/fixtures/conversation/request_contracts.json`
- Fixture SHA-256:
  `a42f6c8ede18acf408348b9f38d657095cbe32bd4613659c46258eb18eedc637`
- Evidence:
  `tests/fixtures/conversation/request-contracts-evidence.json`
- Evidence SHA-256:
  `843e731b9cbae684147f8b9ca8e8b1fe6f86fb8e3ab58d68849245ac60d57fb8`

The manifest covers ordinary text, multimodal content, one and native-parallel
tool calls, completion versus declaration order, multiple assistant tool rounds,
reasoning, compatible/incompatible continuation, queued/multiple/restored
steering, context omission, compaction, artifacts, provider mismatch/refusal/
exception/malformed response, and lossy/lossless codecs. Strict-reader tests add
unknown field/version/type, non-JSON, non-finite, ownership isolation, digest,
and raw-host-path rejection.

The evidence intentionally states `qualified=false` and
`status=waiting_on_lane_a`. Local tests are producer evidence, not independent
cross-lane qualification.

## Consumer instructions

### Lane A

Publish the reviewed 12A snapshot envelope and identity vocabulary first. Then
consume `ConversationSnapshotComponent.from_dict()` as a component payload,
without copying its fields into a second envelope and without naming its digest
a checkpoint/session identity. Add an independent reader test embedding the
exact fixture component. Report unsupported component versions and digest
mismatch through Lane A's typed snapshot failures. Until that producer commit is
available, this request is `waiting_on_lane_a`.

### Lane C

Use RequestView's selected/omitted context IDs, ArtifactRef values, and declared
losses as immutable context-transfer facts. Do not copy ToolResult into a child
result or modify `qitos/core/tool_result.py` from this branch. When Lane C's
accepted effect/quiescence producer lands, Lane B must rebase and run its exact
consumer fixture before G2 acceptance.

### Lane D

Bind the exact producer commit, fixture bytes, evidence bytes, schema versions,
and producer-owned evidence. Because the evidence is not qualified, it must
clear no G2 blocker yet. Keep trajectory v2 unfrozen and do not publish fixture
content as a provider payload or public privacy-safe export.

## Compatibility retirement

The removal ledger is in `s1_b_request_contracts.md`. Current direct writers are
ExchangeLog, RequestView/CodecReport fixtures, and the conversation component.
`ConversationCompatibilityReader` is the only supported historical envelope
reader and never writes that envelope. G1 `conversation/v3/` bytes remain
unchanged pending the existing Lane D receipt migration; new S1 fixtures use the
stable `tests/fixtures/conversation/` path.

## Unsupported claims and known gaps

- No Engine/session/provider runtime uses RequestView yet.
- No concrete OpenAI, Responses, Anthropic, Gemini, LiteLLM, Ollama, or local
  codec was enabled; Task 02C remains later work.
- Existing provider adapters still return error-shaped strings on some paths;
  the new typed boundary proves the target contract but does not change runtime.
- No live model, key, provider default, streaming behavior, retry behavior,
  checkpoint store, SessionStore, session runtime, trace schema, qita code,
  artifact store, or full compaction runtime changed.
- Cross-lane snapshot qualification is waiting on Lane A's reviewed producer;
  C and D consumption also remain pending.
