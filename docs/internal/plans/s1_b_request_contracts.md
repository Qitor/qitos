# S1 Lane B request and continuation contracts

Status: local producer complete; `waiting_on_lane_a`; cross-lane qualification pending
Updated: 2026-08-30
Work package: S1 / Lane B / Task 02B contract package
Source branch: `feat/campaign-absorption`
Source commit: `c1efb0f4adde3e673bf181af5b1760c19a451ae2`
Branch: `codex/v4-s1-b-request-view`
Worktree: `/Users/morinop/Desktop/WhitzardOS-s1-b`

## Outcome and scope

Freeze one provider-neutral `RequestView`, one provider-codec protocol, one
loss-explicit `CodecReport`, durable steering/continuation/context references,
and one conversation snapshot component derived from the existing canonical
`ExchangeLog`. This package does not switch Engine assembly, provider defaults,
streaming, retries, checkpoints, or live model behavior.

The component producer is completeable before Lane A, but its envelope consumer
is `waiting_on_lane_a`: Lane A currently has only uncommitted 12A draft files and
has not published a reviewed producer commit. This branch will not copy Lane A
identity types or claim cross-lane qualification.

## File lease

Lease owner: Lane B / S1-B

File(s): `qitos/core/conversation.py`, new Lane-B-owned request/codec contract
module under `qitos/models/`, request-contract tests and fixtures, and this plan.

Semantic purpose: derive a stable request boundary from ExchangeLog, define
codec/loss/failure extension contracts, and publish the conversation snapshot
component consumed by Lane A.

Expected start/end package: S1 Lane B / Task 02B only.

Other lanes blocked or adapter supplied: Lane A receives an envelope-neutral
component producer/reader; Lane C receives immutable context/artifact transfer
facts; Lane D receives versioned fixtures and exact digests. No Lane A identity,
Lane C ToolResult, Lane D trajectory, Engine runtime, root export, shared release
document, or checkpoint store is edited.

## Exact-source census

Disposition labels: canonical, derived, provider-specific, persisted,
model-visible, diagnostic-only, compatibility-only, or target.

| Concern | Exact source today | Classification today | Target disposition |
|---|---|---|---|
| Exchange append/read/serialize | `qitos/core/conversation.py::ExchangeLog`, `ToolBatchBuilder` | canonical, persisted | remain the sole conversation truth and current writer |
| Tool results | `qitos/core/tool_result.py::ToolResult`; `conversation.py::ToolResultItem` | canonical outcome plus correlation | unchanged; RequestView delegates model projection to ToolResult |
| HistoryMessage | `qitos/core/history.py::HistoryMessage` and conversation adapters | persisted by concrete histories, compatibility-only for conversation | isolated compatibility reader; never a second request truth |
| Prompt/instruction assembly | `qitos/prompting.py::PromptBuilder`, `qitos/protocols.py::ModelProtocol` | derived, model-visible | feed typed instruction/tool-schema inputs into RequestView later |
| Engine message assembly | `qitos/engine/_model_runtime.py::_run_llm_decide` | derived ad hoc provider-message dicts | migration consumer after this S1 package; no behavior change now |
| Native chain repair | `_model_runtime.py::_ensure_chain_consistency` | derived provider workaround; synthesizes placeholders | retire after ExchangeLog migration; never mutate canonical history |
| Provider dispatch | `_model_runtime.py::_call_llm` / `_call_llm_streaming` | provider-specific runtime | later consume `model.codec.encode(request)` without default flip |
| OpenAI Chat | `qitos/models/openai.py::_to_openai_messages`, `_chat_completion` | provider-specific, model-visible | provider-owned codec implementation after protocol freeze |
| OpenAI Responses | `qitos/models/_openai_responses.py::_to_responses_input`, `_request_payload` | provider-specific; native continuation items | separate Responses codec; resolver-scoped continuation refs |
| Anthropic | `qitos/models/anthropic.py::_anthropic_messages` | provider-specific; currently text-flattening | Messages codec must preserve supported blocks or typed-reject |
| Gemini | `qitos/models/gemini.py::_gemini_contents` | provider-specific; currently text-flattening | native codec must preserve supported parts or typed-reject |
| LiteLLM | `qitos/models/litellm.py::_call_api` | provider-specific OpenAI-style pass-through | codec selected by resolved transport/API mode, not family guess |
| Local/OpenAI-compatible | `qitos/models/openai.py::OpenAICompatibleModel`; `qitos/models/local.py` | provider-specific; mixed native/OpenAI-compatible paths | reuse matching provider codec; Ollama remains its own transport |
| Parallel declaration | `AssistantItem.parts`, `ToolCall.batch_id` | canonical, persisted | selected atomically with the complete exchange |
| Completion order | ExchangeLog item order and `results_for_batch` | canonical, persisted | preserved in RequestView provenance/correlation facts |
| Declaration order | assistant part order and `results_for_batch_in_declaration_order` | canonical declaration; derived result query | codec may project explicitly without rewriting facts |
| Reasoning | `ReasoningReference`, `OpaqueContinuationAttachment`; `ModelResponse.reasoning_*` | canonical reference plus provider-native runtime fields | distinct reasoning policy and continuation compatibility report |
| Opaque continuation | `OpaqueContinuationAttachment`; Responses `native_items` | persisted opaque JSON and provider-specific runtime | snapshots/request views use resolver-backed `ContinuationRef`; no SDK object/credential |
| Multimodal | `qitos/core/multimodal.py`; provider normalizers | canonical blocks, provider-specific conversion | codec declares conversion/preservation/loss per block |
| Context trimming | `_context_runtime.py`; `_trim_native_tool_history` | derived runtime policy | deterministic exchange-safe selection report in RequestView |
| Compact history | `qitos/kit/history/compact_history.py` | persisted legacy history plus diagnostic event dicts | consume compaction receipts; full Task 04 compaction remains later |
| Memory | `qitos/core/memory.py`, `qitos/kit/memory/*` | agent-owned persisted/runtime state | context contributor only; RequestView never owns long-term memory |
| Artifacts | canonical ToolResult `artifact_refs` dictionaries | canonical slot without Lane B type | typed `ArtifactRef` reference only; no copied blob or host path |
| runtime_context | tool `execute(args, runtime_context)` callers | runtime-only, tool-visible | context contribution declares source and model visibility; no hidden string |
| Steering | `ExchangeLog.queue_steering`; builder releases after closure | canonical queued/committed fact | versioned receipt vocabulary; exactly-once item correlation across restore |
| Retry | `Model._run_with_retry`, Engine recovery/interceptors | runtime policy | codec/provider failure stays typed and never becomes assistant content |
| Provider error | providers currently return `"Error: ..."` strings in several paths | provider-specific, incorrectly model-shaped | typed `ProviderFailure`; runtime migration is later Task 02C/09B |
| Streaming | `ModelStreamChunk`, provider `stream`, Engine streaming adapter | provider/runtime derived | same codec/failure categories later; no S1 behavior change |
| Checkpoint readers | checkpoint v1/v2 plus future Lane A snapshot | persisted compatibility/current stores | Lane B supplies one component only; checkpoint v2 remains sole store |
| Trace readers | Engine events, trace v1, tracing v2 | diagnostic/compatibility planes | future reports may be projected safely; no trace schema change here |
| Conversation fixtures | `tests/fixtures/conversation/v3/*` | qualified G1 compatibility envelope | keep bytes/path stable; new current fixtures live directly under `conversation/` |

## API decision record S1-B-ADR-001

### Beginner API

The target user path remains compact and hides request/codec internals:

```python
agent = AgentModule(model=model, tools=tools)
session = Engine(agent).session(task)
result = session.run()
```

This S1 package freezes the producer contracts only. The `Engine.session()`
runtime belongs to Lane A and later S2 integration; it is not implemented here.
Users never assemble message dictionaries, pair call IDs, provide capability
matrices, or handle opaque continuation tokens.

### Advanced inspection API

The target inspection path is:

```python
request = session.exchange.request(model=model, context=context_policy)
payload, report = model.codec.encode(request)
```

The concrete S1 boundary is an ExchangeLog-derived builder plus a codec protocol.
`RequestView` and `CodecReport` are imported from their owning submodules, not
from the root package. Reports are observable and JSON-safe but do not block the
ordinary path unless the request would lose data without explicit permission.

### Steering API

Target: `session.steer("Focus on the failing parser")`. Lane B supplies
`SteeringReceipt` and snapshot correlation rules. Lane A owns session lifecycle
rejection and the public handle. A steering item is queued while a tool batch is
open, appended once when it closes, and never inserted inside that batch.

### Custom context API

Advanced callers inject a small `ContextContributor` protocol returning typed
`ContextContribution` values. Selection owns wrapping, digesting, visibility,
placement, and budgets. Long-term memory and artifact stores remain external;
only immutable references and declared model-visible summaries enter a request.

### Provider extension API

A provider exposes one codec implementing the shared `ProviderCodec` protocol.
It accepts a `RequestView`, provider capabilities, and transport/API-mode
identity, and returns `(payload, CodecReport)`. Provider-native codecs live
beside their transports; there is no cross-provider compiler module or provider-
specific canonical request type.

### Public surface budget

- zero root `qitos` exports;
- zero `qitos.core.__init__` exports in S1;
- one owning conversation module for canonical and derived contract records;
- one small models-layer codec protocol module;
- provider codecs remain beside providers when implemented;
- no `V1`/`V2`/`Legacy`/`Next` public class names.

### Rejected API designs

- provider message dictionaries as canonical history;
- `ConversationV2`, `HistoryV2`, `RequestViewV2`, or `NextMessages`;
- a giant configuration dictionary or caller-supplied capability matrix;
- a second conversation/session store;
- raw SDK objects, clients, credentials, host paths, or opaque tokens in a
  request/snapshot/diagnostic;
- one boolean conflating reasoning replay with provider continuation;
- silent lossy codecs or automatic stateless fallback;
- hidden context strings or mutation of ExchangeLog for provider placement.

## Implementation sequence

1. Add immutable, strict, JSON-safe request/context/continuation/report records
   and deterministic ExchangeLog-derived selection.
2. Add the single codec/failure protocol and conservative model capability
   inference without changing provider dispatch.
3. Add steering and conversation snapshot component records with integrity
   digest, strict readers, compatibility-only legacy intake, and redaction.
4. Publish direct-path fixtures covering the required matrix and exact digests.
5. Add unit/consumer tests, then run targeted and repository-wide gates.
6. Publish the Lane A/C/D consumer instructions and `waiting_on_lane_a` status.

## Compatibility retirement ledger

| Surface | Current role | Replacement | Removal gate |
|---|---|---|---|
| `HistoryMessage` conversation use | compatibility input/output | ExchangeLog -> RequestView | Engine/checkpoint migration plus one deprecation window |
| provider message dictionaries | runtime-derived request payload | provider codec output | all supported provider conformance and S2 switch |
| `native_items` continuation path | provider-specific compatibility | resolver-backed `ContinuationRef` | Responses migration and restore fixtures |
| `PromptBuilder.message_injections` | ad hoc request contribution | typed instructions/context | protocol migration with no prompt regression |
| `_ensure_chain_consistency` placeholder results | runtime repair | explicit ExchangeLog closure | S2 Engine migration and recovery tests |
| compact-history message-count grouping | legacy history strategy | complete-exchange selection/receipts | Task 04C after RequestView adoption |
| `tests/fixtures/conversation/v3/` | G1 producer evidence | stable direct-path S1 fixtures | integration-owner/D receipt migration; bytes remain untouched now |

## Validation ledger

- New request/conversation/codec contract suites plus existing conversation:
  `58 passed`.
- Combined conversation, provider/model, context/history/memory, ToolResult
  consumers, architecture/public-surface, and no-local-path matrix:
  `219 passed`.
- `/opt/anaconda3/bin/python3.12 scripts/static_quality.py check`: exit 0.
- Stable flake8 over `qitos/core qitos/engine qitos/models qitos/trace`: exit 0.
- Stable mypy over the same surface: success; only the existing unchecked-body
  note in `qitos/core/state.py` was emitted.
- Full `/opt/anaconda3/bin/python3.12 -m pytest -q`:
  `1899 passed, 50 skipped in 24.52s`.
- `git diff --check`: pending this documentation update, then required clean.
- Live provider calls/keys: not used.
- Architecture allowlist delta: zero.
- Root/public export delta: zero.
