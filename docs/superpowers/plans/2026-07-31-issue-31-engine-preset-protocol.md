# Issue 31 Engine Preset Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make directly constructed `Engine(agent=...)` instances honor protocol declarations attached by `build_model_for_preset(...)` without changing the existing explicit protocol, parser, model-profile, or framework-default precedence.

**Architecture:** Extend only `Engine.resolve_protocol()` with two validated, model-declared candidates between parser inference and model-name inference: `llm.qitos_protocol`, then `llm.qitos_harness_metadata["protocol"]`. Keep all existing higher-priority branches unchanged, ignore unknown model-declared protocol identifiers, and preserve observability through distinct resolution-source values.

**Tech Stack:** Python 3.10+, pytest, QitOS `AgentModule + Engine`, Markdown/MDX documentation.

## Global Constraints

- Preserve the single `AgentModule + Engine` architecture.
- Do not add a `k3` matcher as a substitute for the root-cause fix.
- Preserve this precedence: Engine protocol, Agent protocol, parser inference, model declaration, model profile, framework default.
- Unknown model-declared protocol identifiers must fall through to existing model-profile/default inference.
- Do not add production dependencies.
- Update tests, changelog, bilingual Engine docs, and bilingual README news.

---

### Task 1: Lock the direct-Engine regression and precedence

**Files:**
- Modify: `tests/test_model_protocols.py`

**Interfaces:**
- Consumes: `build_model_for_preset(...)`, `Engine.resolve_protocol()`, `AgentModule.model_protocol`, parser `contract_id`, and model tool-schema delivery methods.
- Produces: Regression coverage for preset model attributes, metadata fallback, existing precedence, unknown-declaration fallback, and API `tools` delivery.

- [x] **Step 1: Add a failing direct-construction regression test**

Construct a Kimi preset model with `family_id="kimi"` and `model_name="k3"`, bind it to a minimal agent, and assert that `Engine(agent=agent).resolve_protocol()` returns `json_decision_v1` with source `model_qitos_protocol`.

- [x] **Step 2: Add behavior coverage for metadata and request delivery**

Add focused tests showing that metadata-only protocol declarations resolve with source `model_harness_metadata`, and that a real Engine run sends a non-empty OpenAI-compatible `tools` option for the K3 preset.

- [x] **Step 3: Add compatibility coverage**

Assert the unchanged higher-priority branches (Engine protocol, Agent protocol, parser inference) and verify an unknown model declaration falls through to the existing model-profile/default behavior.

- [x] **Step 4: Run the new tests and verify the expected RED result**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider tests/test_model_protocols.py -k 'preset_model_protocol or harness_metadata_protocol or protocol_precedence or unknown_model_declared_protocol'`

Expected: the preset/model-metadata tests fail because the current Engine reports `framework_default`; compatibility tests pass.

### Task 2: Implement the minimal Engine resolution fix

**Files:**
- Modify: `qitos/engine/engine.py:440-469`
- Test: `tests/test_model_protocols.py`

**Interfaces:**
- Consumes: `get_protocol(protocol)` and model harness attributes.
- Produces: `Engine.resolve_protocol()` returning a validated model-declared protocol with source `model_qitos_protocol` or `model_harness_metadata`.

- [x] **Step 1: Insert validated model candidates after parser inference**

Read `llm.qitos_protocol` first and `qitos_harness_metadata["protocol"]` second. For each candidate, call `get_protocol`; return only a recognized protocol and otherwise continue to the existing model-name branch.

- [x] **Step 2: Run the focused regression suite and verify GREEN**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider tests/test_model_protocols.py`

Expected: all tests in the file pass.

- [x] **Step 3: Run adjacent Engine and native-tool-call suites**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider tests/test_engine_core_flow.py tests/test_native_tool_calling_runtime.py tests/test_model_runtime_text_tool_calls.py`

Expected: all collected tests pass.

### Task 3: Document the behavior and verify repository quality

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `README.zh.md`
- Modify: `docs/concepts/engine.mdx`
- Modify: `docs/zh/concepts/engine.mdx`

**Interfaces:**
- Consumes: the final protocol precedence and resolution-source names.
- Produces: user-facing release notes and bilingual direct-Engine protocol guidance.

- [x] **Step 1: Update user-facing documentation**

Document that direct Engine construction honors preset model protocol declarations after explicit Engine/Agent/parser configuration and before model-name inference. Add concise Unreleased and README news entries.

- [x] **Step 2: Run stable-surface static checks**

Run: `flake8 qitos/core qitos/engine qitos/models qitos/trace`

Run: `mypy qitos/core qitos/engine qitos/models qitos/trace`

Expected: both commands exit successfully.

- [x] **Step 3: Run the full available test suite**

Run: `PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider`

Expected: no regressions beyond the already-recorded baseline collection failures caused by absent optional/submodule packages. If those packages remain absent, report the exact errors and use all independently collectable core suites as the verification boundary.

- [x] **Step 4: Review the final diff**

Confirm the production change is limited to protocol resolution, the tests exercise consumer-visible behavior, documentation is bilingual, and no unrelated files or existing user work changed.

## Verification notes

- Initial regression RED: 3 failed and 2 passed; the failures matched the missing model-declaration branches and API tools delivery.
- Reviewer-boundary RED: malformed metadata raised before a valid `qitos_protocol`; the new regression failed for that exact reason.
- Focused protocol suite: 20 passed.
- Engine/protocol/native-tool regression set: 156 passed and 3 skipped.
- Changed-file `flake8` and `git diff --check`: passed.
- Repository-wide `flake8` and `mypy` were executed but remain red on pre-existing stable-surface debt (46 lint findings and 157 type errors); none points to the new resolution code or tests.
- Full `pytest` remains blocked during collection by 10 absent optional/submodule packages. After excluding those collection blockers, 1551 tests passed, 52 skipped, and 156 unrelated environment/component tests failed.
