# Task 01 — Baseline Absorption: land campaign mechanism commits on main

Status: actionable design, ready to execute
Parents: `docs/internal/plans/cybergym_campaign_absorption.md` (v2), `docs/internal/plans/v0.7_native_agent_kernel.md`
Depends on: nothing (this is the prerequisite task)
Unblocks: Task 02 (conversation kernel), Task 03 (ACI toolset), Task 04 (context/memory), Task 05 (trajectory plane)
Milestone: P0 (see absorption plan §11)

---

## 1. Goal

Replay every **domain-neutral mechanism commit** from the CyberGym campaign branches onto current `main`, decontaminated, with tests — so Tasks 02–05 build on a hardened base instead of re-deriving fixes.

What this task is NOT: no new design, no methodology promotion, no strategy code. Pure landing + cleanup of already-proven fixes.

## 2. Source commits and batches

Base topology (verified 2026-08-27): merge-base `e82ef2f`; most complete framework line = `origin/codex/x3-tool-contract` (= local Cyborg `core` + 10 hardening + 4 final commits); unique extras on `origin/qitos_cybergym`; delivery-mode commit on `origin/feat/runtime-context-in-tool`.

Land in four ordered batches:

### Batch E — engine correctness (from `core`/x3 line)

| Commit | Change | Landing notes |
|---|---|---|
| 7388fb7 | multi-action blocking isolation in `_action_runtime.py`; result merge by original index; `call_{step}_{i}` ids; multi-action render | keep render changes that ride along; skip GLM preset default flip to `json_decision_multi_v1` (defer to Task 02 decision, release-note there) |
| 427ce9c | in-flight dedup in `recipes/benchmarks/_shared.py::execute_example_jobs` | as-is |
| 147468f → d9596e4 → 39f423f | `_report_runtime_exception()` in `engine.py`: stderr + file log + RECOVER trace event + `EngineResult.last_error` | **decontaminate**: replace `CYBERGYM_TASK_TRACE_DIR` probe with `QITOS_TRACE_DIR` (or EngineConfig field); drop stray `traceback.print_exc()` scaffolding from 147468f |
| 0370917 | `ContextConfig.tool_call_loop_detection_enabled` + `loop_max_repeats` (default on) | as-is |
| 2a2397e | recovery-card passthrough in `_serialize_for_tool_message` | as-is + its regression test |

### Batch M — model/provider layer (x3 line)

| Commit | Change | Landing notes |
|---|---|---|
| 75e3c53 | `ModelResponse.reasoning_fields: Dict[str,str]` + `reasoning_source`; supersedes 5452e23 `reasoning_content`; includes 71bb4e1 thinking dedupe | port as one squashed unit; Task 02 builds the policy layer on top |
| 181ba65 | authored-description-beats-docstring in `BaseTool`/`FunctionTool`/`build_tool_spec` + `tests/core/test_tool_description_contract.py` | as-is |
| 6379f25 | `:param`/Google-style docstring parsing into per-param schema descriptions | audit `_strip_param_docs` continuation-line edge; add the missing test |
| 7fd1fee | `ToolHookContext.step_id` = current step on native path; `_relocate_chat_template_kwargs` moves unknown SDK kwargs (`do_sample`…) into `extra_body` | as-is |
| 05a1c82 | `_normalize_decision_context_packet()` + pre-rebuild sidecar dump | as-is |

### Batch X — executor & context mechanics (x3 line)

| Commit | Change | Landing notes |
|---|---|---|
| 3f34a04 | four-level concurrency adjudication; `[TOOL_RESULT_MISSING]` cards; unknown-tool rejection listing available tools | **must remove** the CyberGym `_CONCURRENCY_SAFE_TOOLS` literal list — empty default + policy/flags only |
| a3597a9 | `model_summary` projection across history/budget/TUI/trace + design doc + `tests/test_model_summary_projection.py` | port code + `docs/internal/plans/model-summary-tool-projection.md`; Task 03's card renderers build on it |
| e9bde23 | `StopReason.INFRASTRUCTURE_INVALID`; optional `agent.commit_action_results(...)` pre-history hook | as-is |
| 1e9d9b4 | `resolve_request_budget()` hard/soft/emergency budgets + occupancy telemetry | as-is |
| ae65cb3 | whole-step slide-window trimming + tool-schema param rendering in protocols | **decontaminate**: replace 150k/130k literals with `ContextConfig` knobs, provider-neutral defaults; merge against mainline `compact_history.py` changes |
| 84d56b2 | DockerEnv absolute-path passthrough in `_inner_path` | as-is; note behavior change in release notes |

### Batch Y — qitos_cybergym-only grafts

| Commit | Change | Landing notes |
|---|---|---|
| 5e013e9 + d16e775 | sticky inference-key routing headers in `models/openai.py` | generalize: neutral `extra_headers`/routing config on the model or preset; no `x-inspire-inference-key` literal in framework code |
| ecd817d | `DockerEnv(container_env=...)` + runner env passthrough | runner side keeps only the neutral mechanism (env mapping), not CYBERGYM_* names |
| e37540f | TUI task_id display / action rendering fix | as-is |

Explicitly deferred: `72d3d7d` (merge_tool) — redesigned as the delivery policy in Task 02, not landed as an env-gated hack. The qita workbench (85a8099) and canonical trace (4b8c8a0) land in Task 05. Everything vendored-agent related is discarded (lives in cybergym-agent package).

## 3. Procedure

1. **Archive tags first** (forensic safety): `git tag archive/cybergym-core core_tip; git tag archive/cybergym-x3 origin/codex/x3-tool-contract; git tag archive/cybergym-queue origin/qitos_cybergym` (push tags).
2. Branch `feat/campaign-absorption` off `main`.
3. Cherry-pick batch by batch; after each batch run the full verification block (§6) before continuing.
4. Conflict resolution policy:
   - `qitos/models/openai.py`: main's Responses API path (`_openai_responses.py`) wins structurally; campaign chat-completions fixes apply to the chat path only; both paths must keep working (CI matrix runs both).
   - `qitos/kit/history/compact_history.py`: mainline changes win; ae65cb3 slide-window reconciles on top as policy knobs.
   - `qita/_cli_app.py`: not touched in this task (Task 05).
5. Decontamination pass after Batch Y: grep gates in §6 must be clean.

## 4. Deliverables

- `feat/campaign-absorption` branch, green CI, reviewed PR series (one PR per batch, E/M/X/Y).
- Ported test files: `tests/test_engine_error_reporting.py`, `tests/test_model_summary_projection.py`, `tests/core/test_tool_description_contract.py` (+ new `_strip_param_docs` edge test, concurrency-adjudication matrix test, budget-resolution test).
- CHANGELOG wave 1 entries (incl. Breaking notes: DockerEnv abs-path, concurrency policy, `INFRASTRUCTURE_INVALID`).
- Updated `docs/concepts/engine.mdx` (error reporting, receipts hook, loop-detection knob) — minimal, no new concepts yet.

## 5. Acceptance criteria

- [ ] `git log main..feat/campaign-absorption` contains every commit listed in §2 or its decontaminated equivalent; none of the deferred items.
- [ ] `grep -rniE 'cybergym|CYBERGYM' qitos/` → zero hits.
- [ ] `grep -rn 'inspire-inference-key\|_CONCURRENCY_SAFE_TOOLS' qitos/` → zero hits.
- [ ] Multi-action isolation regression test green (blocked sibling does not cancel executed sibling).
- [ ] Concurrency adjudication has no hardcoded tool-name list; matrix test covers all four levels.
- [ ] Error-reporting test green with generic env var name.
- [ ] Both chat-completions and Responses paths pass provider tests.

## 6. Verification

```bash
pytest -q
flake8 qitos/core qitos/engine qitos/models qitos/trace
mypy qitos/core qitos/engine qitos/models qitos/trace
```

## 7. Risks

- openai.py three-way conflict is the hot spot; mitigation: per-hunk review with both-path tests from the first PR.
- Cherry-pick ordering inside batches matters (75e3c53 depends on 5452e23 lineage; error-reporting is a 3-commit evolution — take final state, not the intermediate prints).
