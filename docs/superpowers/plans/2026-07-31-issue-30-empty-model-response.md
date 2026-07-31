# Issue #30 Empty Model Response Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject model responses that contain neither usable text nor tool calls before parsing, route them through bounded model-error recovery, and preserve existing parser-feedback and decision behavior.

**Architecture:** Add the response-validity guard in the Engine's private model runtime after `AgentModule.interpret_model_response()` has had an opportunity to handle the normalized response. Raise the existing typed `ModelExecutionError` with a diagnostic error code and an error-scoped recovery limit; teach the default `RecoveryPolicy` to honor that optional limit without changing its global default or the handling of existing errors.

**Tech Stack:** Python 3.10+, dataclasses, pytest, QitOS `AgentModule + Engine`, existing runtime tracing and recovery contracts.

## Global Constraints

- Preserve the canonical `AgentModule + Engine` lifecycle and all existing public APIs.
- Do not change `JsonDecisionParser`, general parser-error feedback, explicit `Decision.wait`, or native tool-call behavior.
- Preserve `finish_reason`, usage, model, and provider diagnostics in `StepRecord.model_response` and runtime events.
- Permit one retry for an unhandled empty model response, then stop through the existing `unrecoverable_error` path.
- Do not change the default `QITOS_MAX_RECOVERIES=100` behavior for unrelated failures.
- Add no production dependency.

---

### Task 1: Reproduce the Engine-Level Failure

**Files:**
- Modify: `tests/test_model_runtime_text_tool_calls.py`

**Interfaces:**
- Consumes: `Engine.run()`, `ModelResponse`, `RecoveryPolicy`, and `JsonDecisionParser`.
- Produces: an end-to-end regression test for empty model-response classification and bounded recovery.

- [x] **Step 1: Write the failing regression test**

Add a deterministic model returning an OpenAI-compatible HTTP-success payload with `content=None`, `tool_calls=None`, `finish_reason="length"`, and usage. Configure an Engine budget of at least three steps and assert that the model is called twice, the parser is never called, both failures are `model_error`, the normalized diagnostics remain on both records, and the final stop reason is `unrecoverable_error`.

- [x] **Step 2: Run the regression test and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 conda run -n qitos pytest -q -p no:cacheprovider tests/test_model_runtime_text_tool_calls.py::test_empty_model_response_uses_bounded_model_recovery
```

Expected: FAIL because the current runtime invokes the parser and consumes the step budget.

### Task 2: Add the Minimal Runtime Guard

**Files:**
- Modify: `qitos/engine/_model_runtime.py`
- Modify: `qitos/engine/recovery.py`
- Test: `tests/test_model_runtime_text_tool_calls.py`

**Interfaces:**
- Consumes: `ModelExecutionError`, `RuntimeErrorInfo`, `ErrorCategory.MODEL`, normalized `ModelResponse`, and `RuntimeErrorInfo.details`.
- Produces: `_raise_for_empty_model_response(response, step)` behavior and an optional, code-keyed `max_recoveries` policy override used only by explicitly tagged errors.

- [x] **Step 1: Raise a typed model error before parser normalization**

After agent interpretation returns `None`, detect `not response.text.strip()` and no response tool calls. Raise `ModelExecutionError(RuntimeErrorInfo(...))` with `recoverable=True` and details containing:

```python
{
    "code": "empty_model_response",
    "finish_reason": response.finish_reason,
    "usage": response.usage,
    "model_name": response.model_name,
    "provider": response.provider,
    "max_recoveries": 1,
}
```

- [x] **Step 2: Honor the error-scoped recovery limit**

In `RecoveryPolicy.handle()`, keep the existing global consecutive-failure counter and add an independent scoped streak keyed by `info.details["code"]` when a valid non-negative integer `info.details["max_recoveries"]` is present. Stop when either limit is exhausted. Unrelated recoverable failures must not consume the empty-response retry, and existing errors without both fields retain the current global behavior.

- [x] **Step 3: Run the regression test and verify GREEN**

Run the Task 1 command. Expected: PASS.

### Task 3: Protect Existing Behavior

**Files:**
- Modify: `tests/test_model_runtime_text_tool_calls.py`
- Modify: `tests/test_runtime_recovery.py`

**Interfaces:**
- Consumes: custom `interpret_model_response`, native tool calls, parser errors, and generic `RecoveryPolicy` errors.
- Produces: regression coverage proving the new guard and scoped limit do not broaden into existing paths.

- [x] **Step 1: Add boundary tests**

Cover these behaviors:

```text
empty response handled by AgentModule.interpret_model_response -> accepted
empty text plus native tool_calls -> existing action path
non-empty malformed JSON -> existing parser_error feedback path
generic recoverable error without max_recoveries -> configured global limit
unrelated recoverable error before empty response -> does not consume empty-response retry
```

- [x] **Step 2: Run focused tests**

```bash
PYTHONDONTWRITEBYTECODE=1 conda run -n qitos pytest -q -p no:cacheprovider tests/test_model_runtime_text_tool_calls.py tests/test_runtime_recovery.py tests/test_memory_and_parser_and_critic.py tests/test_engine_core_flow.py
```

Expected: all pass.

### Task 4: Synchronize Repository-Facing Documentation

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `README.zh.md`
- Modify: `docs/concepts/engine.mdx`
- Modify: `docs/zh/concepts/engine.mdx`

**Interfaces:**
- Consumes: the verified runtime behavior from Tasks 1–3.
- Produces: concise user-facing descriptions of empty-response classification, bounded recovery, preserved trace diagnostics, and unchanged parser feedback.

- [x] **Step 1: Add Unreleased and News entries**

Document that empty model responses are now model errors with one bounded retry instead of parser waits, while valid tool calls and ordinary parser repair are unchanged.

- [x] **Step 2: Update bilingual Engine documentation**

Add the failure behavior near the existing lifecycle/recovery description and keep English and Chinese meaning aligned.

### Task 5: Verify the Complete Change

**Files:**
- Review all files changed by Tasks 1–4.

**Interfaces:**
- Consumes: the complete implementation and documentation diff.
- Produces: verified repository state ready for user review.

- [ ] **Step 1: Run the full test suite**

```bash
PYTHONDONTWRITEBYTECODE=1 conda run -n qitos pytest -q -p no:cacheprovider
```

- [ ] **Step 2: Run stable-surface static checks**

```bash
conda run -n qitos flake8 qitos/core qitos/engine qitos/models qitos/trace
conda run -n qitos mypy qitos/core qitos/engine qitos/models qitos/trace
```

- [x] **Step 3: Review the final diff and workspace state**

```bash
git diff --check
git diff --stat
git status --short
```

Confirm no unrelated files changed and every requirement has direct test or documentation coverage.

## Execution Notes

- The focused Engine/model/parser/recovery suite passes: 97 tests passed.
- The broad available suite reached 1,545 passes and 52 skips, but the repository baseline also has 156 unrelated failures from missing `qitos_zoo`/CyberGym/PentAGI checkouts, a missing async pytest plugin, and pre-existing executor/provider expectations.
- The prescribed `flake8` and `mypy` executables are not installed in the existing `qitos` conda environment. Python bytecode compilation and `git diff --check` pass.
