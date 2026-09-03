# S4 Lane B — provider-neutral model transactions and context

Status: active implementation
Owner: Lane B
Fixed baseline and merge-base: `c4e621d05960a4e2f06cb4864f6a8cb8275ac067`
Branch: `codex/v4-s4-b-model-context`
Worktree: `/Users/morinop/Desktop/WhitzardOS-s4-b`

## Scope and leases

This lane owns the model-transaction, provider-codec, conversation,
request-view, context, memory, compaction, artifact, and continuation surfaces
listed in the S4 dispatch. It will not modify configuration, CLI, Session or
Engine public APIs, checkpoint, tool/Env, tracing/qita, root/core/engine export
files, shared release documentation, or the S4 integration ledger.

## Transaction census

The fixed baseline already contains the intended canonical spine:

```text
ExchangeLog -> RequestView -> ProviderCodec.encode -> adapter transport
            -> typed ProviderDecodedResponse -> ExchangeLog
```

The durable runtime path is `qitos.engine._model_runtime`; provider-neutral
contracts and transaction enforcement are in `qitos.models.codec` and
`qitos.models.provider`. Provider modules own their codecs and transport
adapters. `HistoryMessage` and legacy `Model.__call__` remain compatibility
boundaries, not a second canonical store. The implementation census will track
and eliminate provider-local history assembly, capability inference in the
transaction path, duplicated repair policy, raw SDK persistence, and deferred
tool-result persistence wherever they remain reachable from the canonical
path.

## Transaction ADR

Decision S4-B-ADR-001: retain the promoted S2/S3 transaction spine and graduate
its structural extension contracts. A provider adapter declares an exact
`RequestTarget`, strict `ProviderCapabilities`, a `ProviderCodec`, transport
operations, and failure normalization. The Engine receives only typed decoded
responses and redacted transaction facts. No adapter reads Engine private
state, and no provider-native object becomes a Session component.

Admission is recorded before transport; encode/projection rejection consumes
no request; any invoked transport consumes exactly one request even when
transport or decode later fails. Hidden retry remains zero. Reasoning is an
ordered assistant part or opaque continuation reference, never ordinary text
unless an explicit codec policy declares and reports that transformation.

## Capability grammar

Capabilities form a strict, closed vocabulary declared by each adapter/API
mode. The S4 grammar covers API mode, native and parallel tool calls, tool
choice, multimodal input, reasoning input/output, continuation, stateless
replay, streaming, usage, cancellation, context window, output budget, and
structured output. Boolean fields accept only real booleans; budgets are
positive bounded integers; unknown keys are typed errors. Unsupported request
features are rejected or appear as explicit `CodecReport` losses, and losses
require `allow_loss=True`.

## Context architecture

The canonical history remains `ExchangeLog`. Context contributors, memory
sources, selectors, budget policy, compactors, and artifact resolvers are
structural injected extensions. Selection is deterministic and receipt-backed.
Projection, diagnostics, and persistence are separate. Compaction selects or
transforms complete exchanges without rewriting the log. Artifact references
are content-addressed, path-free identities; bodies are resolved only for an
ephemeral request projection and are not copied into every durable turn.

Budget calculation intersects the declared context policy with provider input
and output limits. Traversal of caller containers is cycle-aware and bounded by
depth, item count, and byte/unit ceilings. Required material that cannot be
resolved or admitted fails with a stable typed code.

## Transfer authority

`ContextTransferPlan` and `ContextTransferReceipt` remain the sole transfer
authority. Effective child context is the intersection of parent authority,
child need, provider capability, sandbox authority, artifact permission, and
budget. Raw continuation, credentials, host paths, sandbox tokens, artifact
bodies, unselected history, and caller-private metadata are excluded unless a
typed reference is explicitly selected and authorized.

## Failure matrix

Provider failures retain one stable phase/code pair across sync and streaming
paths: encode, projection, admission, connection, transport, timeout,
authentication, rate-limit, provider-rejection, provider-server, cancellation,
stream, decode, malformed-structured-response, and capability-loss. Diagnostic
payloads are allowlisted and never echo exception text, URLs, headers, tokens,
cookies, host paths, credentials, or provider raw bodies. Retry, usage, token,
latency, and request-sent facts remain explicit.

## Work packages

- [ ] B1 census and ADR: inventory canonical and compatibility paths, freeze
  capability/failure/context grammar, and add test vectors for every gap.
- [ ] B2 provider capabilities and independent conformance: publish a
  third-party-style adapter/codec plus a runner used by declared built-in modes.
- [ ] B3 messages and continuation: prove ordered multi-round tool exchanges,
  parallel completion order, steering/recovery, multimodal order, reasoning,
  stateless replay, streaming assembly, cancellation, and usage.
- [ ] B4 context extensions: graduate contributor/memory/selector/budget/
  compactor/artifact-resolver protocols with deterministic receipts and bounded
  adversarial projections.
- [ ] B5 fixtures and handoffs: publish `tests/fixtures/s4/lane_b/`, exact
  path/digest/test-node manifests, config consumer fixture, qualification
  evidence, and A/C/D handoffs.
- [ ] B6 qualification: run all required targeted/full/static/privacy checks,
  record live qualification only if an explicit preconfigured AgentConfig and
  credential mapping are present, and finish with a clean branch.

## Lane A / G5 configuration handoff

Lane A must compose, without inspecting private fields: provider adapter
selection, codec/API mode, contributor and memory factories, compactor,
artifact resolver, capability/loss policy, request/context/output budgets, and
continuation resolver. The committed consumer fixture will contain only logical
IDs and public constructor inputs. It will assert that no credential, endpoint,
header, raw continuation payload, or live object is present in canonical config
or Session material.

## Live testing policy

Live qualification is informational and is permitted only when the task
environment supplies an explicit local AgentConfig path and credentials-mapping
path. The lane will not scan environment variables. Each selected logical
profile uses `max_tokens=10240`, zero hidden retries, explicit per-request
timeout, per-profile and total request ceilings, total-token ceiling, and wall
clock ceiling. If those paths are absent, evidence records
`live_model_qualification=blocked_configuration` without blocking offline
completion.

## Shared-document patch text

The final handoff will include patch-ready text for README, CHANGELOG, progress,
v4, and navigation owners. This branch will not modify those leased files.

## Validation ledger

Pending. Results must distinguish passed, failed, and not-run checks and bind
the final fixture manifest to committed bytes.

