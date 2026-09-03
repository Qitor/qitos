# S4 Lane B — provider-neutral model transactions and context

Status: offline producer complete; host-resource exceptions recorded
Owner: Lane B
Fixed baseline and merge-base: `c4e621d05960a4e2f06cb4864f6a8cb8275ac067`
Branch: `codex/v4-s4-b-model-context`
Worktree: `/Users/morinop/Desktop/WhitzardOS-s4-b`

## Scope and leases

This lane owns model transactions, provider codecs, conversation/request
views, context, memory, compaction, artifacts, and continuation surfaces. It
does not modify configuration, CLI, Session or Engine public APIs, checkpoint,
tool/Env, tracing/qita, root/core/engine exports, shared release documents, or
the S4 integration ledger.

## Transaction census

The fixed baseline already contained the canonical spine:

```text
ExchangeLog -> RequestView -> ProviderCodec.encode -> adapter transport
            -> typed ProviderDecodedResponse -> ExchangeLog
```

The durable runtime path is `qitos.engine._model_runtime`; provider-neutral
contracts and enforcement are in `qitos.models.codec` and
`qitos.models.provider`. Provider modules own wire codecs and transports.
`HistoryMessage`, `Model.__call__`, and `LegacyCallableAdapter` remain
compatibility inputs into the same transaction, not a second canonical store.

The census found no provider-local canonical history on this spine. S4 closes
capability inference for the new declaration shape, normalizes raw SDK values
to typed decoded responses with `raw=None`, and makes diagnostics allowlisted.
Tool results remain per-slot durable in `ExchangeLog`; completion order is
preserved independently of the declaration-order derived view.

## Transaction ADR

Decision S4-B-ADR-001: retain the promoted S2/S3 spine and graduate its
structural extension contracts. An adapter declares an exact `RequestTarget`,
strict `ProviderCapabilities`, a `ProviderCodec`, transport operations, and
failure normalization. The Engine receives only typed decoded responses and
redacted transaction facts. No adapter reads Engine private state, and no
provider-native object becomes a Session component.

Admission occurs before transport; encode/projection rejection consumes no
request; invoking transport consumes exactly one request even when transport
or decode fails. Hidden retry is zero. Reasoning is an ordered assistant part
or opaque continuation reference, never ordinary message text unless an
explicit codec policy declares and reports that transformation.

## Capability grammar and matrix

Schema `qitos.provider_capabilities/v2` is strict and closed. Exact API styles
are `chat_completions`, `responses`, `messages`, `generate_content`,
`generate`, and `compatibility`. The schema declares native/parallel tool
calls, tool schemas/choice, multimodal input, reasoning input/output,
continuation, stateless replay, streaming, usage, cancellation, structured
output, input window, and output budget. Boolean fields accept only booleans;
budgets are positive integers or null; unknown fields are typed errors.

The committed matrix covers OpenAI chat/responses, Anthropic, Gemini,
LiteLLM, Ollama chat/generate, LMStudio, and vLLM. Declarations are
conservative adapter/API facts, not claims that every upstream model supports
every feature. Unsupported request features are rejected or recorded as an
explicit `CodecReport` loss requiring `allow_loss=True`.

## Message, reasoning, and continuation semantics

The conformance vectors cover multi-round user/assistant/tool exchanges,
parallel declarations, out-of-order completion, partial batch persistence,
steering queues, ordered multimodal blocks, stream assembly, usage, and
stateless replay. `ReasoningBlock` and `ReasoningReference` preserve ordering
without converting reasoning into ordinary content.

Opaque provider state stays behind a resolver. Durable continuation identity
includes provider, exact model, API mode, resolver/reference identity, digest,
expiry, and capability. Ordinary diagnostics store only reasoning presence,
source, and field names; they exclude reasoning text, signed/encrypted data,
headers, tokens, and raw provider bodies.

## Third-party extension conformance

`qitos.models.conformance` publishes a reusable runner over the structural
`ProviderAdapter`; the fixture adapter inherits no concrete QitOS adapter and
reads no Engine private state. The same runner exercises it and every declared
built-in mode. Checks include declaration/request/report round trips, safe
request projection, encode/decode ordering, tools, reasoning, multimodal,
continuation, usage, streaming, typed failure, non-echoing diagnostics, and
serialization isolation.

## Context architecture

`ExchangeLog` remains the only canonical history. Context contributors,
`MemorySource`, selectors, budget policy, compactors, and `ArtifactResolver`
are injected structural extensions. Selection is deterministic and
receipt-backed. Projection, persistence, and diagnostics remain separate.
Compaction selects/transforms complete exchanges without rewriting the log.

Artifact references are path-free, content-addressed identities. Resolver
bodies are ephemeral and length/SHA verified; a body is not copied into every
turn. Required unresolved or corrupt material fails with a typed code. Context
budget intersects policy limits, provider input window, provider output
ceiling, and reserved output. Traversal is bounded at depth 64, 100,000 nodes,
and 8 MiB, so 10 MiB, cyclic, and deeply nested inputs fail closed.

## Transfer authority

`ContextTransferPlan` and `ContextTransferReceipt` remain the only transfer
authority. Effective child context is the intersection of parent grant,
destination need, tool/sandbox environment, artifact access, caller policy,
budget ceilings, and destination codec replay capability. Selected
multimodal/tool/reasoning history now requires corresponding codec facts.

Unselected parent history, provider credentials, raw continuation, host paths,
sandbox tokens, artifact bodies, and caller-private metadata are not
transferred. A missing required semantic capability yields
`provider_context_capability_mismatch`.

## Failure and budget matrix

Typed stages are encode, projection, admission, connection, transport,
timeout, authentication, rate-limit, provider-rejection, provider-server,
cancellation, stream, decode, malformed-structured-response, and
capability-loss. Facts include stable code/category/stage, retryable,
request-sent, retry count, and remediation. Exceptions never echo URLs,
headers, tokens, cookies, credentials, host paths, or raw response bodies.

Admission is callable before transport and cancellation is checked on both
sides of admission. Request accounting therefore distinguishes pre-transport
failure from a sent request. Existing durable restore logic keeps request
counts monotonic. No hidden retry was added.

## Lane A / G5 configuration handoff

`tests/fixtures/s4/lane_b/config-handoff.json` and `config_consumer.py` cover
adapter selection, codec/API mode, contributor/memory registries, selector,
compactor, artifact resolver, capability/loss policy, request/context/output
budgets, and continuation resolver. The executable consumer imports only
public structural contracts and checks exact target/codec facts and zero
hidden retries. It contains logical IDs only; credential resolution remains an
external mapping.

## A/C/D consumer handoffs

- Lane A: compose the declared adapter/API and extension factories; keep
  credentials external and enforce budgets/loss policy.
- Lane C: consume `ProviderTransaction` and `ContextTransferReceipt`; persist
  admission before transport and retain partial batches/request counts.
- Lane D: consume diagnostic projections and typed failure/request-sent facts;
  never render raw reasoning, credentials, continuation payload, or host path.

The machine-readable handoff is
`tests/fixtures/s4/lane_b/a-c-d-handoff.json`.

## Live testing policy and result

Live qualification is informational and permitted only when the task supplies
an explicit local AgentConfig path and credentials-mapping path. This task
supplied neither, so no environment scan or credential lookup was performed:

```text
live_model_qualification=blocked_configuration
```

If a later owner supplies both paths, each logical profile must use
`max_tokens=10240`, zero hidden retries, and explicit per-request,
per-profile, total-request, total-token, and wall-clock ceilings. Only logical
profile ID, declared capability facts, counts, typed outcome, redacted digest,
and framework-invariant status may be retained.

## Work packages

- [x] Census, ADR, capability/failure/context grammar.
- [x] Provider capability v2 and independent conformance runner.
- [x] Messages, reasoning, continuation, streaming, usage, cancellation.
- [x] Context, memory, budget, compaction, artifact resolver, transfer gates.
- [x] Semantic fixtures, producer manifest, config and A/C/D handoffs.
- [x] Offline scoped qualification and privacy/adversarial tests.

## Shared-document patch-ready text

This branch does not modify leased shared files. Their owners can apply:

`README.md` / What's New:

> Provider integrations now share a strict, provider-neutral transaction and
> conformance contract. Context, memory, artifacts, reasoning continuation,
> streaming, usage, cancellation, and failure facts are capability-gated and
> keep durable, model, and diagnostic projections separate.

`CHANGELOG.md` / Unreleased / Added:

> Added provider capability schema v2, a reusable structural provider
> conformance runner, structural memory and artifact resolver protocols, and
> S4 Lane B producer fixtures. Provider failures now retain typed stages and
> request-sent facts; diagnostics redact opaque reasoning and
> credential-bearing metadata.

`docs/progress.md` / S4 ledger:

> Lane B offline producer complete on `codex/v4-s4-b-model-context`; exact
> evidence is under `tests/fixtures/s4/lane_b/producer-manifest.json`. Live
> qualification is `blocked_configuration`. Do not infer G5, release, CLI,
> sandbox, or Trajectory completion from this lane.

`docs/v4/` / model-context section:

> Canonical flow is `ExchangeLog -> RequestView -> ProviderCodec.encode ->
> transport -> typed decode -> ExchangeLog`. Third-party adapters implement
> the public structural `ProviderAdapter` and use the same conformance runner
> as declared built-in modes. Transferred context also intersects the
> destination codec's semantic replay capabilities.

Navigation/index owner:

> Link the Lane B plan and fixture manifest; describe S2/S3 readers as
> compatibility inputs, not alternate canonical stores.

## Validation ledger

- `scripts/static_quality.py check`: passed.
- `flake8 qitos/core qitos/engine qitos/models qitos/trace`: passed.
- `mypy qitos/core qitos/engine qitos/models qitos/trace`: passed, 94 files.
- `pytest -q tests/core`: passed, 433.
- `pytest -q tests/engine`: passed, 241.
- `pytest -q tests/test_model_providers.py`: passed, 10.
- Lane B conformance/context/fixture plus partial-batch checks: passed, 24.
- Full `pytest -q`: 2457 passed, 50 skipped, 2 host-resource failures. Both
  were outside Lane B: a Docker backend temporarily unavailable and a
  20-round clean-process child exceeding its fixed 20-second timeout while
  several full pytest jobs shared the host. Both failed nodes passed on final
  serial recheck: Docker process recovery in 53.40 seconds and 20-round
  clean-process loss recovery in 386.17 seconds. No assertion failure
  implicated Lane B semantics.
- Twenty-round fresh-process continuation continuity: passed in 33.54 seconds.
- 10 MiB, cyclic, and depth-bound projections: passed.
- Independent adapter conformance and privacy/non-echoing checks: passed.
- Producer manifests: passed and bound to committed source/fixture bytes.
- Live models: not run, `live_model_qualification=blocked_configuration`.

## Known gaps and non-claims

- Live model qualification remains blocked only by missing explicit config and
  credential mapping paths; it does not block the offline producer.
- Built-in adapters do not yet advertise native transport cancellation.
- Compatibility adapters remain while downstream callers migrate.
- This lane does not claim every provider supports every feature or every
  model can drive an Agent.
- This lane does not qualify Session/public CLI, sandbox, Trajectory freezing,
  S4/G5 completion, release readiness, deployment, or server 149.
