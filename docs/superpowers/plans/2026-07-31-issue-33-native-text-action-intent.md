# Issue #33 Native Text Action Intent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent malformed structured action text from being reported as a successful final answer while preserving natural-language final fallback behavior.

**Architecture:** Add one private, format-tolerant action-intent classifier to the model runtime. Use it only after the existing parser chain returns a parser-error wait in the native text lane, leaving all native tool-call, parser-success, and ordinary natural-language paths unchanged.

**Tech Stack:** Python 3, dataclasses, regular expressions, pytest, flake8, mypy.

## Global Constraints

- Keep `AgentModule + Engine` as the single runtime architecture.
- Do not change public parser, model, decision, trace, or family-preset contracts.
- Preserve ordinary natural-language `native_text_final` behavior.
- Preserve raw response and parser diagnostics in existing trace surfaces.
- Add no production dependency.

---

### Task 1: Lock the regression boundary with tests

**Files:**
- Modify: `tests/test_model_runtime_text_tool_calls.py`

**Interfaces:**
- Consumes: `Engine._model_runtime.normalize_decision(raw_decision, step, record)` and `ModelResponse`.
- Produces: Regression coverage for malformed structured actions, native
  protocol markers, natural-language finals, and valid parser results.

- [x] **Step 1: Write failing structured-action tests**

Add tests that configure native preference and pass `ModelResponse` values containing malformed labeled and JSON-like action schemas. Assert the returned decision remains `wait`, carries `parser_error`, keeps `decision_source="parser"`, and never exposes a final answer.

- [x] **Step 2: Add control cases**

Assert that plain natural language still returns `final` with
`decision_source="native_text_final"`, while a valid ReAct action and valid
`Final Answer:` remain parser decisions.

- [x] **Step 3: Run the new tests to verify RED**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider tests/test_model_runtime_text_tool_calls.py -k 'native_text'
```

Expected: the structured-action cases fail because current code returns
`Decision.final`; the natural-language and valid parser controls pass.

### Task 2: Add the minimal native text guard

**Files:**
- Modify: `qitos/engine/_model_runtime.py`
- Test: `tests/test_model_runtime_text_tool_calls.py`

**Interfaces:**
- Consumes: raw response text and the `Decision` returned by the parser chain.
- Produces: `_looks_like_structured_action_intent(text: Any) -> bool` and corrected native text branch selection.

- [x] **Step 1: Implement the classifier**

Add a private runtime method that detects unambiguous action carriers
(`action`, `tool_call`, and native protocol markers) in structured positions.
Require corroborating schema fields for ambiguous `tool`, `call`, and `command`
labels, and do not classify words embedded in prose.

- [x] **Step 2: Guard `native_text_final`**

Preserve non-wait parser results. When a parser-error wait also has structured
action intent, emit a DECIDE event with the rejection reason and return the
wait. Preserve explicit JSON/XML waits, and keep the historical
`native_text_final` behavior for unmarked parser-specific heuristic waits.

- [x] **Step 3: Run the focused tests to verify GREEN**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider tests/test_model_runtime_text_tool_calls.py -k 'native_text'
```

Expected: all selected tests pass.

- [x] **Step 4: Run related runtime tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider tests/test_model_runtime_text_tool_calls.py tests/test_native_tool_calling_runtime.py tests/test_memory_and_parser_and_critic.py tests/test_runtime_recovery.py
```

Expected: all tests pass.

### Task 3: Synchronize user-facing project history

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `README.zh.md`
- Modify: `docs/guides/qwen-family-best-practice.mdx`
- Modify: `docs/zh/guides/qwen-family-best-practice.mdx`

**Interfaces:**
- Consumes: corrected native text fallback semantics.
- Produces: concise English and Chinese documentation of the behavior.

- [x] **Step 1: Update release and news surfaces**

Add an Unreleased fix entry and matching README news entries explaining that
malformed structured action text now enters parser recovery instead of false
completion.

- [x] **Step 2: Update the native lane guide**

Document the distinction between an ordinary text conclusion and structured
action intent that failed parsing. Keep English and Chinese guides aligned.

### Task 4: Verify the complete change

**Files:**
- Review: all modified files.

**Interfaces:**
- Consumes: implementation, tests, and documentation from Tasks 1-3.
- Produces: evidence that Issue #33 is fixed without regressions.

- [ ] **Step 1: Run the full test suite** *(attempted; blocked during collection
  by missing optional/migrated modules in this checkout)*

```bash
PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider
```

- [ ] **Step 2: Run stable-surface static checks** *(attempted; `flake8` and
  `mypy` are not installed in the available environments)*

```bash
flake8 qitos/core qitos/engine qitos/models qitos/trace
mypy qitos/core qitos/engine qitos/models qitos/trace
```

- [x] **Step 3: Review the diff and workspace status**

Confirm the implementation is limited to the native text branch, tests exercise
observable decisions, documentation is synchronized, and no unrelated files
changed.

## Verification notes

- Focused native-text and structured-intent tests: 22 passed.
- The four-file related-runtime command in Task 2: 48 passed.
- Expanded Engine/parser/runtime regression matrix: 318 passed, 3 skipped.
- Exact end-to-end reproduction now follows `wait -> act -> final`, executes one
  native tool call, and finishes with the real final answer.
- The repository-wide suite cannot complete in this checkout: collection fails
  for missing migrated `qitos_zoo`, CyberGym, and Pentagi modules. An expanded
  run still completed 1,563 passing tests before reporting unrelated dependency,
  environment, and pre-existing behavior failures.
- `flake8` and `mypy` are not installed in either the default or `qitos` Conda
  environment. `git diff --check` and targeted Python compilation pass.
