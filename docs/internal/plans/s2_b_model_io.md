# S2 Lane B model I/O runtime plan

Status: in progress
Baseline: `446a347d1ac73636476ca2515a01da601b567c68`
Branch: `codex/v4-s2-b-model-io`
Worktree: `/Users/morinop/Desktop/WhitzardOS-s2-b`
Read-only ledger successor: `47cd4dc5e1ed1b2b0d244bfc90fac031ec55be32`

## Outcome

Converge real Engine model execution on one provider-neutral transaction:

```text
ExchangeLog
  -> explicit context contributors and exchange-safe selection
  -> immutable RequestView
  -> adapter-declared capabilities and provider-owned codec
  -> transport
  -> typed decoded response or ProviderFailure
  -> ExchangeLog
```

`HistoryMessage` and OpenAI-shaped dictionaries remain compatibility inputs and
outputs only. They are not a second canonical conversation model.

## Owned changes

- extend `qitos/core/conversation.py` only where modern ordered reasoning and
  response semantics are not already expressible;
- extend `qitos/core/request_view.py` for continuation/component receipts;
- add provider-neutral context contracts under `qitos/core/`;
- add the provider extension/runtime boundary and provider-owned codecs under
  `qitos/models/`;
- switch `qitos/engine/_model_runtime.py` and `_context_runtime.py` to derive and
  execute a `RequestView`;
- add Lane B tests and stable fixtures under `tests/fixtures/s2/lane_b/`;
- publish exact Lane A/C/D handoff evidence in
  `docs/internal/plans/s2_b_model_io_evidence.md`.

The Lane lease forbids edits to Engine composition, action execution,
checkpoint stores, session/work-graph contracts, tracing/qita, and shared
README/CHANGELOG/progress documents. Shared documentation synchronization is an
integration-owner handoff for this branch.

## Contract decisions

1. `ExchangeLog` remains the only durable conversation truth. Provider SDK
   objects, clients, credentials, headers, endpoints, and raw exceptions never
   enter it or `RequestView`.
2. A provider adapter declares an exact request target, closed capability
   vocabulary, provider-owned codec, transport behavior, response decoding,
   streaming behavior, continuation resolution rules, and failure
   normalization. Generic Engine code has no provider-name branch.
3. Capability mismatch rejects before transport. Codec loss rejects by default;
   explicit loss produces a complete `CodecReport`.
4. Context contributors are explicit injected values with stable identity,
   provenance, deterministic ordering, required/optional behavior, and an
   explicit unit budget. Selection and compaction emit receipts.
5. Reasoning remains an ordered reasoning reference/block and may carry an
   opaque resolver-backed continuation attachment. It is never promoted to
   assistant text merely because a compatibility path cannot represent it.
6. Continuations bind provider, exact model, and API mode. Snapshots retain only
   resolver identity, digest, and expiry. Cross-target reuse rejects typed;
   explicit stateless replay records loss.
7. Provider failures are exceptions with stable category/code, retryability,
   status, remediation, correlation digest, and optional codec report. They are
   sanitized at construction and never appended as assistant output.
8. Existing callable models are supported through one explicit legacy adapter.
   That adapter still receives a `RequestView`, declares its compatibility
   capabilities, and reports any loss; Engine does not bypass the transaction.

## Implementation slices

### Slice 1 — extension contracts

- context contributor/selection/budget/compaction protocols and default
  policies;
- continuation resolver and provider transaction result contracts;
- typed provider failure normalization with optional `CodecReport`;
- provider adapter conformance helpers used equally by official and fake
  third-party adapters.

### Slice 2 — provider codecs and adapters

- OpenAI Chat Completions and Responses stay separate codecs;
- Anthropic Messages, Gemini generateContent, LiteLLM, Ollama chat/generate,
  and OpenAI-compatible local transports declare their supported matrix;
- successful responses decode into ordered assistant parts, stable calls,
  reasoning references/blocks, continuation references, usage, and safe
  metadata;
- sync and stream errors normalize to equivalent typed failure categories.

### Slice 3 — Engine/context migration

- ingest legacy history through the one compatibility reader;
- add current system/developer/user instructions and default/custom context;
- derive one `RequestView`, validate capabilities, select the provider codec,
  execute transport, and append only successful decoded assistant facts;
- retain `ModelResponse` only as the downstream Decision compatibility view;
- expose sanitized request/codec/context facts on existing runtime events.

### Slice 4 — conformance and handoff evidence

- provider adapter, codec fidelity/loss, context contributor, continuation
  resolver, and steering consume-once suites;
- at least one provider-independent fake adapter and two structurally different
  custom context contributors run the same conformance assertions;
- stable semantic fixtures, digest manifest, provider matrix, unsupported/loss
  matrix, and exact A/C/D producer handoff.

## Validation gates

Run the requested targeted suites first, then architecture/public/privacy
ratchets, static quality, flake8, mypy, the full test suite, and
`git diff --check`. Live-key checks remain opt-in and cannot qualify this work.

## Integration handoffs

- Lane A consumes the conversation/context snapshot component and resolver
  requirements without copying fields into a second session truth.
- Lane C consumes stable call/batch identity and declaration/completion
  correlation; Lane B does not modify tool execution files.
- Lane D consumes sanitized request, codec, continuation, context selection,
  compaction, steering, and provider-failure facts with exact fixture digests.

