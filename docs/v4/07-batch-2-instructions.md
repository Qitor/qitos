# Batch 2 — Coding-Agent Task Instructions (Batch M / X / Y)

Follows `docs/v4/06-batch-1-instructions.md` (all landed on main as of `adf179f`: green baseline 1652 passed, harness↔models decycled, kit→benchmark edge removed, Batch E engine fixes absorbed).

Dispatch order: **Brief M first**; after M merges, **Brief X and Brief Y in parallel** (both touch `qitos/models/openai.py` or `_model_runtime.py` regions M may have changed; landing M first avoids conflicts). Brief E′ (test isolation, carried over) can run anytime.

Branch naming: `feat/campaign-absorption` continues (commit on top of main). Read `docs/v4/01-baseline-absorption.md` §2 Batch M/X/Y tables before starting; every pick must keep the neutrality gate (`git diff main | grep "^+" | grep -icE cybergym` = 0).

---

## Brief M — Batch M: model/provider layer (x3 line)

Commits (in order), with landing notes:

1. **75e3c53** — `ModelResponse.reasoning_fields: Dict[str,str]` + `reasoning_source`; verbatim provider-channel preservation (`reasoning_content`, `reasoning`, …); summary-dict output; render/TUI display of reasoning. Supersedes the older `reasoning_content`-only extraction (5452e23) and includes the dedupe-when-equal-to-raw behavior (71bb4e1). Before porting: check whether current main's `_model_runtime`/render already carry partial reasoning handling (main evolved separately) and reconcile — final state must be the 75e3c53 shape. Principle from the source: *field names are provider protocol data, not agent protocol text* — preserve verbatim, never reformat.
2. **181ba65** — authored-description-beats-docstring in `BaseTool`/`FunctionTool`/`build_tool_spec` + `tests/core/test_tool_description_contract.py`. Port code + test as-is.
3. **6379f25** — docstring `:param`/Google-style parsing into per-parameter schema descriptions. Port + **add the missing edge test** for `_strip_param_docs` continuation lines (non-`:` continuation lines must be stripped from the top-level description, not retained).
4. **7fd1fee** — (a) `ToolHookContext.step_id` = `_active_state.current_step` on the native tool-call path (was placeholder 0); (b) `_relocate_chat_template_kwargs` moves SDK-unknown kwargs (`do_sample`, etc.) into `extra_body` instead of failing the whole request. Port both; keep `chat_template_kwargs` behavior.
5. **05a1c82** — `_normalize_decision_context_packet()`: exactly-one current DECISION_CONTEXT invariant, pre-rebuild sidecar dump on rejection. Location note: message assembly internals live in `_model_runtime`; do not reintroduce provider JSON building outside the existing assembly point (Task 02 will formalize).
6. **New (decision item, not a pick): explicit request-retry policy.** Context: Brief A (batch 1) found a `_call_with_retries` loop (`time.sleep`) that existed only in a dead checkpoint commit and never on mainline; tests asserting it were removed. Decision: do NOT restore a hidden loop. Instead add an explicit, opt-in retry policy at the model layer: reuse the existing `RetryPolicy` shape from `qitos/core/tool.py` if it fits (reuse before create); expose `retry=` on Model construction / `build_model_for_preset`; default = no silent retries (engine recovery remains the safety net); retryable-exception predicate + max attempts + backoff; tests with a fake transient error. CHANGELOG `Added` + docs note.

Acceptance (docs/v4/01 §5 model subset): reasoning fields round-trip verbatim through history/TUI (dict and object response shapes tested); description-precedence contract test green; `_strip_param_docs` edge test green; hook step numbers non-zero on native path; unknown-kwargs request no longer degrades (test with `do_sample`); decision-context packet invariant test; retry policy opt-in with default-off test. `pytest -q` green; `flake8 qitos/models qitos/core && mypy qitos/models qitos/core` at main parity.

---

## Brief X — Batch X: executor & context mechanics (x3 line) — after M

Commits (in order), with landing notes:

1. **3f34a04** — four-level concurrency adjudication: policy `parallel_tool_names` → `needs_approval` veto → explicit `ToolSpec.concurrency_safe` authoritative → `read_only` heuristic fallback; missing parallel slots return `[TOOL_RESULT_MISSING]` recovery card; unknown tool names rejected with error listing available tools. **Delete the `_CONCURRENCY_SAFE_TOOLS` hardcoded list entirely** (Batch E already excluded its campaign additions; now remove the mechanism). Also **remove the pre-existing `submit_poc` special-case** in `_action_runtime._model_visible_tool_output` (confirmed on main, ~2 hits) — it is superseded by item 2's generic projection. This commit also resolves the semantics gap found in batch 1 (read-only but not concurrency-safe was inexpressible). Adjudication matrix unit test required.
2. **a3597a9** — `model_summary` projection: tools may return an LLM-facing summary projected across native tool history, budget trimming (`_tool_output_for_budget`), TUI, and trace while the structured dict stays canonical. Port code + design doc (`docs/internal/plans/model-summary-tool-projection.md`) + `tests/test_model_summary_projection.py`. This is the generic replacement for every per-tool visible-output special-case.
3. **e9bde23** — `StopReason.INFRASTRUCTURE_INVALID` + optional `agent.commit_action_results(state, actions, results, step_id)` pre-history hook. Small; port with a test.
4. **1e9d9b4** — `resolve_request_budget()` deterministic long-context recovery: hard_input_budget / soft_input_target / `apply_effective_output_limit` / `emergency_output_limit` / `min_output_reserve_tokens`; occupancy telemetry into states. Port + budget-resolution tests.
5. **ae65cb3** — whole-step slide-window trimming coordinated between assembled packets and durable history + tool-schema per-param rendering in protocols. **Decontaminate**: replace the 150k/130k literals with `ContextConfig` knobs with provider-neutral defaults; reconcile with mainline `compact_history.py` (main has its own Responses-era changes — mainline behavior wins where they overlap, knobs express the campaign policy).

Acceptance: no tool-name literals in engine (`grep -rnE "submit_poc|_CONCURRENCY_SAFE_TOOLS" qitos/engine/` = 0); adjudication matrix + model-summary + receipts-hook + budget tests green; slide-window knobs documented in `ContextConfig`; `pytest -q` green; flake8/mypy engine at parity.

---

## Brief Y — Batch Y grafts (qitos_cybergym-only) — after M, parallel with X

1. **5e013e9 + d16e775** — sticky routing headers. Generalize: neutral per-model or per-preset `extra_headers`/routing config on the OpenAI-compatible provider; **no `x-inspire-inference-key` literal anywhere in qitos**; env-var driven, default off. Test with a fake transport asserting header presence.
2. **ecd817d** — `DockerEnv(container_env: dict[str,str] | None)` + runner passes an env mapping into the container. Keep only the neutral mechanism (env mapping passthrough); runner-side CYBERGYM_* names are NOT ported.
3. **e37540f** — TUI task_id display / action rendering fix. Port as-is.

Acceptance: `grep -rniE "cybergym|inspire-inference" qitos/` = 0; docker env mapping test (existing docker tests extended); `pytest -q` green.

---

## Brief E′ — test isolation (carried over from batch 1, unchanged)

`tests/test_examples_smoke.py::test_swe_security_and_skill_examples_smoke` fails standalone (`budget_steps`) but passes after `test_minimal_example_smoke_runs` — shared-state leak between example agents. Locate via bisection; fix with explicit fixture-level init/cleanup (not ordering/xfail); no `qitos/` source changes (if the leak is framework-level global state, report as architecture-debt candidate). AC: standalone pass + full suite green.

---

## After this batch

Batch 1+2 complete Task 01 (`docs/v4/01`). Next: Task 02 conversation kernel contracts (`qitos/core/conversation.py` — turn model, validators, policies, compilers; brief will be prepared from `docs/v4/02`), which Batch M's reasoning fields and 05a1c82 seam directly feed.
