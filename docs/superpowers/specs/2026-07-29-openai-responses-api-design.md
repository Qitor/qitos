# OpenAI Responses API Adapter Design

Date: 2026-07-29  
Status: Design approved in conversation, pending written spec review  
Issue: https://github.com/WhitzardAgent/qitos/issues/29

## 1. Goal

Add an optional OpenAI Responses API transport to QitOS while preserving the
existing Chat Completions behavior and the canonical `AgentModule + Engine`
execution model.

The adapter must preserve Responses output items, correlate function calls and
tool results through `call_id`, support multi-turn tool continuation, expose
typed streaming information, and keep traces useful without exposing private
reasoning content.

## 2. Compatibility boundary

- `chat_completions` remains the default API mode.
- Existing OpenAI and OpenAI-compatible configurations continue to behave as
  they do today unless `api_mode: responses` is explicitly selected.
- Responses support is an adapter and normalization change. It must not add a
  second engine lifecycle or change `observe -> decide -> act -> reduce ->
  check_stop`.
- Existing `ToolRegistry`, `Action`, `ActionExecutor`, parser, and reducer
  contracts remain unchanged.
- Unsupported compatible providers fail with a clear capability error. The
  adapter must not silently retry through Chat Completions.
- No new production dependency is introduced. The existing optional OpenAI SDK
  dependency changes from `openai>=1.0.0` to `openai>=1.66.0`, the first
  official SDK release line that shipped the Responses resource.

## 3. Public configuration

Add `api_mode` to model configuration and model constructors:

```yaml
model:
  provider: openai
  model: gpt-5
  api_mode: responses
```

Accepted values are:

- `chat_completions`
- `responses`

The default is `chat_completions`. Invalid values raise a configuration error
before a request is sent.

## 4. Protocol adapter

The OpenAI adapter owns all endpoint-specific conversion:

- Chat-style QitOS history to Responses `input` items
- Chat function-tool schemas to Responses function-tool schemas
- Responses output items to canonical `ModelResponse`
- QitOS tool-result messages to Responses `function_call_output` items
- Responses usage fields to QitOS usage fields
- Responses typed stream events to `ModelStreamChunk`

The Engine must not branch on OpenAI model names or provider-specific response
classes.

### 4.1 Tool schema conversion

QitOS currently supplies Chat-style function definitions:

```python
{
    "type": "function",
    "function": {
        "name": "search",
        "description": "Search the index",
        "parameters": {"type": "object", "properties": {}},
        "strict": True,
    },
}
```

Responses mode converts that to:

```python
{
    "type": "function",
    "name": "search",
    "description": "Search the index",
    "parameters": {"type": "object", "properties": {}},
    "strict": True,
}
```

Unknown non-function tool definitions pass through unchanged so the adapter
does not preclude provider-supported built-in tools.

### 4.2 Function-call normalization

Each Responses `function_call` item maps to the existing canonical tool-call
shape:

```python
{
    "id": item.call_id,
    "type": "function",
    "function": {
        "name": item.name,
        "arguments": item.arguments,
    },
    "metadata": {
        "response_item_id": item.id,
        "status": item.status,
    },
}
```

`call_id`, not the Responses item `id`, becomes the canonical tool-call id.
The existing Engine therefore copies it to `Action.action_id`, and the current
action runtime writes the same value back on the tool result.

### 4.3 Usage normalization

Responses usage maps without changing existing telemetry consumers:

- `input_tokens` -> `prompt_tokens`
- `output_tokens` -> `completion_tokens`
- `total_tokens` -> `total_tokens`

Provider-native usage details remain optional metadata.

## 5. Native item preservation

Add one optional, backward-compatible field to the stable response and history
contracts:

```python
native_items: Optional[List[Dict[str, Any]]] = None
```

It is carried by:

- `ModelResponse`, for the ordered output returned by the provider
- `HistoryMessage`, for the ordered provider items required by the next request

The field preserves item type, ids, status, ordering, function arguments, and
opaque continuation data. Existing callers that do not use it observe no
behavior change.

Reasoning items are treated as opaque protocol state. QitOS does not interpret
or expose private chain-of-thought. User-visible traces contain safe item
descriptors and provider-authorized summaries only; encrypted or opaque
continuation payloads are retained only where required to continue or replay a
request.

## 6. Multi-turn continuation

The default implementation uses explicit item replay instead of mutable
adapter-local `previous_response_id` state.

For a native tool round, the next Responses request contains:

1. the prior ordered Responses output items;
2. one `function_call_output` item per executed tool call, using the same
   `call_id`;
3. any subsequent user input.

This keeps runs isolated and makes request construction reproducible. It also
avoids coupling correctness to server-side response storage.

History compaction treats an active native tool round as atomic. It may compact
older completed rounds, but it must not split or summarize away the output
items or tool results still required for the next Responses request.

`previous_response_id` is out of scope for the first implementation. It can be
added later as an explicit storage/continuation policy.

## 7. Streaming and async behavior

Responses streaming is normalized from typed events rather than Chat deltas.
The adapter must support:

- text deltas;
- function-call argument deltas;
- completed output items;
- response completion and usage;
- provider error events.

`ModelStreamChunk` receives optional event metadata sufficient to preserve item
type, item id, output index, and sequence number. Existing consumers continue
to use `text`, `tool_calls`, `usage`, and `done`.

Synchronous, asynchronous, and streaming OpenAI model classes share the same
pure conversion helpers so endpoint semantics do not drift between paths.

## 8. Trace and replay behavior

`ModelResponse.to_summary_dict()` includes sanitized native item descriptors.
Step traces retain:

- response id and status;
- ordered item types and ids;
- function `call_id`, name, and status;
- permitted reasoning summaries;
- normalized usage.

Raw private reasoning is never synthesized or logged. Large encrypted or
opaque continuation payloads are excluded from normal summaries.

## 9. Error handling

- Invalid `api_mode` fails during configuration or model construction.
- An OpenAI SDK without `responses` support raises an actionable dependency
  error.
- A compatible endpoint that rejects `/v1/responses` raises a provider error
  identifying the selected API mode.
- Malformed function-call items are retained in native items but are not
  executed as tools.
- Missing `call_id` prevents execution of that function call and produces a
  normalization diagnostic.
- The adapter never silently changes API mode after a request failure.

## 10. Test strategy

Tests use fake OpenAI clients and SDK-shaped response objects; they do not
require network credentials.

Required coverage:

1. Existing Chat Completions sync, async, streaming, and native tool-call tests
   remain green.
2. Default configuration resolves to `chat_completions`.
3. Invalid `api_mode` fails before invoking a client.
4. Responses text output normalizes to `ModelResponse.text`.
5. Single and parallel `function_call` items normalize in source order.
6. `call_id` survives `ModelResponse -> Action -> tool result -> next input`.
7. Reasoning and message items survive a consecutive tool round.
8. Responses usage maps to current token fields.
9. Typed text and function-argument stream events are assembled correctly.
10. Async Responses calls use the same request and response conversion.
11. Active native tool rounds survive history selection and compaction.
12. Unsupported compatible endpoints fail without Chat fallback.

The final verification set is:

```bash
pytest -q
flake8 qitos/core qitos/engine qitos/models qitos/trace
mypy qitos/core qitos/engine qitos/models qitos/trace
```

Packaging checks are also required because the optional OpenAI SDK version
constraint changes:

```bash
python -m build
python -m twine check dist/*
```

## 11. Documentation and release communication

The implementation updates:

- `CHANGELOG.md` under `Unreleased`;
- the model configuration/reference documentation;
- an English and Chinese Responses API usage guide or aligned configuration
  section;
- the README news section.

Documentation explicitly states that Responses mode is opt-in, that compatible
providers may implement only a subset, and that no automatic fallback occurs.

## 12. Out of scope

- Replacing Chat Completions as the default
- Automatic endpoint capability discovery
- Silent Chat/Responses fallback
- Raw chain-of-thought collection
- A provider-specific Engine lifecycle
- A new tool registry or action execution contract
- Broad relocation or redesign of the existing model package
