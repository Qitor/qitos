# Issue #34 Cancellation State Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Propagate an observed immediate cancellation through the canonical state, result objects, END event, and trace manifest without changing unrelated Engine behavior.

**Architecture:** Keep `StateSchema.stop_reason` as the single source of truth. Add one typed stop reason, set it at the immediate-cancellation branch, and derive both event and manifest output from that state. Reuse qita's existing `stopped` terminal manifest status.

**Tech Stack:** Python 3, pytest, QitOS Engine and TraceWriter.

## Global Constraints

- Cover only `CancelMode.IMMEDIATE`; do not fold the separate `after_step` checkpoint defect into this patch.
- Do not add dependencies or a parallel cancellation/result abstraction.
- Preserve `AgentModule + Engine` and existing trace/result contracts.
- Use a deterministic hook-based regression with no sleeps.
- Do not commit changes unless explicitly requested by the user.

---

### Task 1: Lock the cancellation contract with a failing regression

**Files:**
- Modify: `tests/engine/test_cancellation.py`

**Interfaces:**
- Consumes: `Engine.run`, `CancelToken.request_cancel`, `TraceWriter`, `RuntimePhase.END`.
- Produces: a regression test covering state, task result, END event, and manifest consistency.

- [x] **Step 1: Write the failing test**

  Add a hook whose `on_after_step(ctx, engine)` method requests
  `engine._cancel_token.request_cancel("immediate")` once. Run a real Engine with a
  real `TraceWriter` under `tmp_path`, then assert literal expected values for all
  terminal outputs.

- [x] **Step 2: Run the test to verify RED**

  Run:

  ```bash
  PYTHONDONTWRITEBYTECODE=1 pytest -q -p no:cacheprovider tests/engine/test_cancellation.py::TestCancelInEngine::test_immediate_cancel_propagates_to_state_result_and_trace
  ```

  Expected: failure because `result.state.stop_reason` is `None` instead of
  `"cancelled_immediate"`.

### Task 2: Implement the minimal canonical-state fix

**Files:**
- Modify: `qitos/core/errors.py`
- Modify: `qitos/engine/engine.py`
- Test: `tests/engine/test_cancellation.py`

**Interfaces:**
- Produces: `StopReason.CANCELLED_IMMEDIATE = "cancelled_immediate"`.
- Preserves: existing `EngineResult`, `TaskResult`, `TraceWriter`, and qita APIs.

- [x] **Step 1: Add the typed stop reason**

  Add `CANCELLED_IMMEDIATE` to `StopReason` so `StateSchema.set_stop()` and the
  validation gate accept the value.

- [x] **Step 2: Apply the state transition before the END event**

  In the immediate-cancellation branch, call
  `state.set_stop(StopReason.CANCELLED_IMMEDIATE)` and emit
  `payload={"stop_reason": state.stop_reason}`.

- [x] **Step 3: Map cancellation to the existing stopped manifest status**

  Extend the Engine's trace finalization status selection so
  `cancelled_immediate` produces `status="stopped"`; retain `failed` only for
  `unrecoverable_error` and `completed` for all existing paths.

- [x] **Step 4: Verify GREEN and related cancellation behavior**

  Run the new test, then the complete cancellation test module.

### Task 3: Synchronize public documentation and project history

**Files:**
- Modify: `docs/reference/api.mdx`
- Modify: `docs/zh/reference/api.mdx`
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `README.zh.md`

**Interfaces:**
- Documents: the new public stop reason and consistent cancellation trace outcome.

- [x] **Step 1: Update English and Chinese API references**

  Add `cancelled_immediate` to the `StopReason` enum/table and explain that it is
  set after immediate cancellation is observed.

- [x] **Step 2: Update changelog and README news**

  Add concise user-facing Issue #34 entries describing synchronized State,
  EngineResult, END event, and manifest cancellation status.

### Task 4: Verify compatibility and review the diff

**Files:**
- Review all files modified by Tasks 1-3.

**Interfaces:**
- Confirms: cancellation correctness and absence of regressions in stable surfaces.

- [x] **Step 1: Run targeted and full tests**

  Run cancellation tests first, then `pytest -q`. If the full suite is blocked by
  unrelated environment or optional dependencies, report exact failures.

- [x] **Step 2: Run stable-surface static checks**

  Run:

  ```bash
  flake8 qitos/core qitos/engine qitos/models qitos/trace
  mypy qitos/core qitos/engine qitos/models qitos/trace
  ```

- [x] **Step 3: Review repository state and diff**

  Confirm only intended files changed, no debug artifacts were created, and all
  four terminal status outputs are consistent.

## Implementation Record

- TDD RED: the new regression failed because final State retained
  `stop_reason=None` after an END event reported `cancelled_immediate`.
- TDD GREEN: the new regression passed after the minimal state/status change;
  `tests/engine/test_cancellation.py` passed 15 tests.
- Related Engine/qita/trace regression set: 268 passed.
- Full `pytest -q` is blocked during collection by 10 missing migrated/optional
  packages. Excluding those collection blockers produced 1593 passed, 52 skipped,
  and 144 pre-existing environment/component failures unrelated to this patch.
- `flake8` and `mypy` are not installed in the current environment. Python
  `compileall` and `git diff --check` completed successfully as available static
  checks.
