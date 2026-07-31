# Issue #32 Native Tool History Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent message-window trimming from sending orphan native tool results whose declaring assistant tool call is no longer present.

**Architecture:** Keep every history strategy and its public limits unchanged. Repair the final canonical message list at the existing provider-boundary consistency gate by discarding only invalid orphan tool results, then run the existing missing-result placeholder recovery unchanged.

**Tech Stack:** Python 3.10+, pytest, QitOS `AgentModule + Engine`, OpenAI-compatible native tool-call messages.

## Global Constraints

- Preserve valid native tool-call chains byte-for-byte and in order.
- Preserve the existing placeholder behavior for assistant tool calls whose result is missing.
- Do not change `HistoryPolicy`, `WindowHistory`, `CompactHistory`, token budgets, or public APIs.
- Keep model-request histories valid after message-count window trimming.
- Update tests, bilingual docs, `CHANGELOG.md`, and both README progress sections.
- Do not modify or revert the existing Issue #31 worktree changes.

---

### Task 1: Lock the invalid-history behavior with regression tests

**Files:**
- Modify: `tests/test_model_runtime_text_tool_calls.py`
- Modify: `tests/test_native_tool_calling_runtime.py`

**Interfaces:**
- Consumes: `_ModelRuntime._ensure_chain_consistency(messages)` and default `Engine` history assembly.
- Produces: Regression coverage for orphan removal, valid-chain preservation, existing placeholder recovery, and the 24-message parallel-tool boundary.

- [x] **Step 1: Add a focused unit test for orphan tool results**

Construct canonical messages containing an orphan `role="tool"` entry plus unrelated valid messages. Assert that consistency repair removes only the orphan.

- [x] **Step 2: Add compatibility assertions for existing behavior**

Assert that a complete assistant/tool pair remains unchanged and that a dangling assistant tool call still receives the existing interrupted-result placeholder.

- [x] **Step 3: Add a complete Engine boundary regression**

Use a deterministic native-tool model that emits three calls in the first round and one per later round. Run beyond the default 24-message boundary and assert every provider-bound request has no tool result without a retained assistant declaration.

- [x] **Step 4: Run the new tests and verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider \
  tests/test_model_runtime_text_tool_calls.py \
  tests/test_native_tool_calling_runtime.py
```

Expected: the orphan-removal assertion or boundary regression fails because `_ensure_chain_consistency()` currently returns orphan tool results unchanged.

### Task 2: Implement the minimal provider-boundary repair

**Files:**
- Modify: `qitos/engine/_model_runtime.py`
- Test: `tests/test_model_runtime_text_tool_calls.py`
- Test: `tests/test_native_tool_calling_runtime.py`

**Interfaces:**
- Consumes: `List[Dict[str, Any]]` canonical messages.
- Produces: a new ordered message list containing no tool response whose `tool_call_id` is absent from retained assistant `tool_calls`.

- [x] **Step 1: Filter orphan tool responses before the existing forward check**

Collect retained assistant tool-call IDs, copy all non-tool messages, and retain a tool message only when its non-empty `tool_call_id` is declared. Do not mutate the caller's list.

- [x] **Step 2: Run existing missing-result recovery on the filtered list**

Keep the current placeholder text and append behavior unchanged. Derive responded IDs from the filtered result.

- [x] **Step 3: Run focused tests and verify GREEN**

Run the Task 1 command and require all tests to pass.

### Task 3: Document the repaired invariant

**Files:**
- Modify: `docs/guides/memory-and-history.mdx`
- Modify: `docs/zh/guides/memory-and-history.mdx`
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `README.zh.md`

**Interfaces:**
- Produces: user-facing explanation that message limits remain hard caps while the request boundary removes incomplete orphan tool results.

- [x] **Step 1: Update bilingual history guidance**

Document that native assistant tool calls and tool results are correlated by `tool_call_id`, and QitOS sanitizes incomplete chains before provider dispatch.

- [x] **Step 2: Add release-facing progress entries**

Add one `Unreleased / Fixed` item and concise English/Chinese README news entries referencing stable long-running native tool use.

### Task 4: Verify behavior and regression safety

**Files:**
- Review: all files changed for Issue #32 only.

**Interfaces:**
- Produces: fresh evidence that the original reproduction passes and stable surfaces remain clean.

- [x] **Step 1: Run targeted history and native-tool suites**

```bash
PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider \
  tests/test_native_tool_calling_runtime.py \
  tests/test_model_runtime_text_tool_calls.py \
  tests/test_compact_history.py \
  tests/test_engine_core_flow.py \
  tests/test_openai_responses.py
```

- [x] **Step 2: Run the full test suite**

```bash
PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider
```

- [x] **Step 3: Run stable-surface static checks**

```bash
flake8 qitos/core qitos/engine qitos/models qitos/trace
mypy qitos/core qitos/engine qitos/models qitos/trace
```

- [x] **Step 4: Review the Issue #32 diff separately from pre-existing changes**

Inspect `git diff` for the touched production, test, documentation, changelog, and README files. Confirm no unrelated behavior or Issue #31 edits were altered.

## Verification results

- RED: 2 expected failures exposed orphan tool results in the focused unit test and the ninth default-history Engine request.
- GREEN: 13 focused tests passed after the provider-boundary repair.
- Targeted regression: 55 history, native-tool, Engine, compact-history, and Responses API tests passed.
- Full collection: blocked by 10 pre-existing missing `qitos_zoo`, PentAGI, and externally synchronized CyberGym modules.
- Broad available suite: 1,558 passed and 52 skipped; 156 pre-existing environment/component failures remained, with no failures in the Issue #32 production or test files.
- Static checks: `flake8` and `mypy` were unavailable in both the base and `qitos` environments; Python compilation and `git diff --check` passed instead.
