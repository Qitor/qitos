# OpenAI Responses API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in OpenAI Responses API support that preserves structured output items and tool-call continuity without changing default Chat Completions behavior.

**Architecture:** Keep endpoint-specific conversion in `qitos.models.openai`, extend canonical response/history contracts with optional native items, and reuse the existing native-tool execution lane by mapping Responses `call_id` to canonical tool-call ids. Use explicit stateless item replay; do not add provider state to the Engine.

**Tech Stack:** Python 3.10+, OpenAI Python SDK >=1.66.0, pytest, flake8, mypy.

## Global Constraints

- `chat_completions` remains the default API mode.
- Accepted API modes are exactly `chat_completions` and `responses`.
- Responses mode is opt-in and never silently falls back to Chat Completions.
- `call_id`, not Responses item `id`, is the canonical tool-call id.
- No changes to the `AgentModule + Engine` lifecycle, `ToolRegistry`, `Action`, or `ActionExecutor` contracts.
- Raw chain-of-thought is never synthesized or exposed in trace summaries.
- The optional OpenAI SDK dependency is `openai>=1.66.0`.

---

### Task 1: Canonical native-item and streaming contracts

**Files:**
- Modify: `qitos/core/model_response.py`
- Modify: `qitos/core/history.py`
- Modify: `qitos/models/base.py`
- Modify: `qitos/engine/engine.py`
- Modify: `qitos/engine/_model_runtime.py`
- Test: `tests/test_model_response.py`
- Test: `tests/test_native_tool_calling_runtime.py`

**Interfaces:**
- Produces: `ModelResponse.native_items`, `HistoryMessage.native_items`, and `ModelStreamChunk.event_type/event_metadata/native_item`.
- Consumes: existing Chat-shaped `tool_calls` and Engine history APIs.

- [x] **Step 1: Write failing contract tests**

Add tests proving that `ModelResponse.to_summary_dict()` sanitizes native item
descriptors, Engine assistant history carries native items, and streaming
normalization returns native items.

- [x] **Step 2: Run focused tests and verify feature-missing failures**

Run:

```bash
pytest tests/test_model_response.py tests/test_native_tool_calling_runtime.py -q
```

- [x] **Step 3: Add optional fields and Engine propagation**

Add defaulted optional fields so current constructor call sites remain valid.
Pass native items through `_history_append`, `_normalize_history_messages`,
assistant history creation, and streaming result assembly.

- [x] **Step 4: Run focused tests**

Run the same focused command and require all tests to pass.

### Task 2: Responses protocol conversion and sync transport

**Files:**
- Modify: `qitos/models/openai.py`
- Test: `tests/test_openai_responses.py`

**Interfaces:**
- Produces: `_normalize_api_mode`, `_to_responses_input`,
  `_to_responses_tools`, `_model_response_from_responses`, and Responses-aware
  `OpenAIModel.call_raw`.
- Consumes: QitOS message dictionaries, Chat-style tool schemas, and SDK-shaped
  Responses objects.

- [x] **Step 1: Write failing pure-conversion tests**

Cover message conversion, function tool flattening, text extraction, ordered
function-call normalization, usage mapping, malformed calls, and native item
sanitization using literal SDK-shaped fixtures.

- [x] **Step 2: Run focused tests and verify failures**

```bash
pytest tests/test_openai_responses.py -q
```

- [x] **Step 3: Implement pure conversion helpers**

Convert tool results to `function_call_output`, preserve native items, map
`call_id` to canonical ids, and normalize usage.

- [x] **Step 4: Write and fail a sync transport test**

Patch only the external `openai.OpenAI` constructor and assert the real model
adapter returns `ModelResponse`, sends `input`, uses `max_output_tokens`, and
never calls Chat in Responses mode.

- [x] **Step 5: Implement sync Responses routing**

Keep the existing Chat branch byte-for-byte compatible where practical. Raise
an actionable error if the client has no `responses.create`.

- [x] **Step 6: Run focused tests**

```bash
pytest tests/test_openai_responses.py tests/test_model_providers.py -q
```

### Task 3: Configuration, harness, history replay, and Engine integration

**Files:**
- Modify: `qitos/config/loader.py`
- Modify: `qitos/config/builder.py`
- Modify: `qitos/harness/_types.py`
- Modify: `qitos/harness/_adapters.py`
- Modify: `qitos/kit/history/compact_history.py`
- Modify: `setup.py`
- Test: `tests/test_config.py`
- Test: `tests/test_harness.py`
- Test: `tests/test_openai_responses.py`
- Test: `tests/test_native_tool_calling_runtime.py`

**Interfaces:**
- Produces: public `api_mode` config propagation and active native-round replay.
- Consumes: Task 1 native-item contracts and Task 2 conversion helpers.

- [x] **Step 1: Write failing config and end-to-end tool-loop tests**

Prove the default, explicit Responses mode, invalid mode, harness propagation,
parallel tool call correlation, and second-request
`function_call_output.call_id`.

- [x] **Step 2: Run focused tests and verify failures**

```bash
pytest tests/test_config.py tests/test_harness.py tests/test_openai_responses.py tests/test_native_tool_calling_runtime.py -q
```

- [x] **Step 3: Implement configuration propagation and replay preservation**

Validate API mode at construction, pass it through builders/adapters, preserve
native items in history selection, and ensure active native rounds are not
discarded by compaction.

- [x] **Step 4: Raise the optional SDK floor**

Change only the `models` extra from `openai>=1.0.0` to `openai>=1.66.0`.

- [x] **Step 5: Run focused integration tests**

Run the same focused test command and require all tests to pass.

### Task 4: Responses streaming and async transport

**Files:**
- Modify: `qitos/models/openai.py`
- Test: `tests/test_openai_responses.py`

**Interfaces:**
- Produces: Responses-aware sync `stream`, async `acall_raw`, and async
  `astream` behavior using Task 2 conversion helpers.
- Consumes: SDK typed events and Task 1 stream metadata.

- [x] **Step 1: Write failing typed-stream tests**

Cover `response.output_text.delta`, function argument delta/completion,
`response.output_item.done`, `response.completed`, usage, ordering, and errors.

- [x] **Step 2: Run stream tests and verify failures**

```bash
pytest tests/test_openai_responses.py -q
```

- [x] **Step 3: Implement Responses stream event normalization**

Accumulate function arguments by item/call id and emit a final chunk containing
canonical tool calls, native items, and normalized usage.

- [x] **Step 4: Write failing async transport tests**

Use an async fake client to prove async routing and async stream parity.

- [x] **Step 5: Implement async routing with shared helpers**

Do not duplicate protocol normalization logic.

- [x] **Step 6: Run focused and existing provider tests**

```bash
pytest tests/test_openai_responses.py tests/test_model_providers.py -q
```

### Task 5: Documentation, release communication, and verification

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `docs/reference/configuration.mdx`
- Modify: `docs/zh/reference/configuration.mdx`
- Modify: `docs/docs.json` only if a new page is required

**Interfaces:**
- Documents: opt-in configuration, continuation behavior, compatible-provider
  limitations, no-fallback semantics, and privacy-safe tracing.

- [x] **Step 1: Update user-facing docs**

Add an `Unreleased` changelog entry, a concise README news item, and aligned
English/Chinese configuration documentation.

- [x] **Step 2: Run all tests**

```bash
pytest -q
```

- [x] **Step 3: Run static checks**

```bash
flake8 qitos/core qitos/engine qitos/models qitos/trace
mypy qitos/core qitos/engine qitos/models qitos/trace
```

- [x] **Step 4: Run packaging checks**

```bash
python -m build
python -m twine check dist/*
```

- [x] **Step 5: Review final diff**

Run:

```bash
git diff --check
git status --short
git diff --stat
```

Confirm every changed production behavior has a regression test and no
unrelated files changed.

## Verification result

- Responses/Engine/config/provider regression selection: 131 passed.
- Existing provider compatibility selection: 9 passed, 2 pre-existing retry
  tests deselected because they target retry behavior absent from the baseline.
- Full `pytest -q` remains blocked during collection by 10 pre-existing missing
  `qitos_zoo`, `pentagi`, and CyberGym modules.
- New Responses module/tests pass flake8 and targeted mypy checks. Repository-wide
  flake8/mypy still report pre-existing baseline findings.
- Source distribution, wheel build, and `twine check` passed.
