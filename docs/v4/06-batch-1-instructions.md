# Batch 1 — Coding-Agent Task Instructions (first wave)

Status: archived historical brief — do not dispatch

Task 01 was closed on 2026-08-29. The authoritative capability ledger and
verification gates are in `docs/v4/01-baseline-absorption.md`; Tasks 02–05 were
redesigned after implementation review. This file is retained only to explain
the original commit-by-commit rollout.

How to use: each brief below is self-contained and can be pasted to a coding agent as one assignment. Recommended dispatch: Brief A first (it restores a trustworthy CI signal); after A merges, B, C, D are independent and can run in parallel. Each brief lands as its own small PR series. Repository-wide rules the agent must read first: root `AGENTS.md`, `docs/architecture/change-guide.md`, and the subpackage `AGENTS.md` relevant to the touched code.

Verified baseline for this batch (2026-08-27, commit `4c4acdd`): `pytest -q` = **136 failed, 1630 passed, 10 collection errors**; `tests/test_architecture_boundaries.py` = 4/4 green.

---

## Brief A — Restore a green CI baseline (test hygiene)

**Context.** On `main`, 136 test failures and 10 collection errors are stale references to out-of-tree packages that do not exist in this repository. The framework's domain-neutrality policy (AGENTS.md) means these packages (zoo agents, the vendored CyberGym agent) live outside `qitos/`; their tests must not remain here failing forever. Verified classification:

| Missing module | Failing tests |
|---|---|
| `qitos_zoo.qitos_auditor` | `test_auditor_completeness.py` (27), `test_auditor_knowledge.py` (13), `test_qitos_auditor_package.py` (7), `test_auditor_multi_agent.py` (collection) |
| `qitos_zoo.qitos_coder` | `test_qitos_zoo_package.py` (23), `test_coder_terminal_mode.py` (4), `test_coder_compact_history.py` (4), `test_claude_code_streaming.py` (7), `test_harness_presets.py` (collection), `test_examples_smoke.py` (collection), `test_qita_cli.py` partial (verify) |
| `pentagi` | `test_pentagi_function_tool_migration.py` (27), `test_pentagi_handoff_targets.py` (5) |
| `qitos.benchmark.cybergym.agent` | 6 collection errors + `test_cybergym_context_retention.py` (6), `test_benchmark_cybergym_recipe.py` (3), `test_cybergym_task_spec.py` / `test_cybergym_parallel_tools_prompt.py` / `test_cybergym_evidence_selector.py` / `test_cybergym_context_snip.py` / `test_cybergym_candidate_failure_records.py` / `test_cybergym_agent_poc_profile.py` / `test_cyber_critic_migration.py` (collection) |
| genuine stale-test bugs | `test_model_providers.py` (2: `monkeypatch.setattr("qitos.models.openai.time", ...)` assumes `qitos.models.openai` is a package — it is a module), `test_advanced_tools_and_executor.py` (2: verify same class of issue before fixing) |

**Task.**
1. Re-verify the classification yourself (do not trust the table blindly): run `pytest -q --continue-on-collection-errors`, group failures by root cause.
2. For tests of out-of-tree packages: delete the test files. Rule: a test file whose primary subject is an out-of-tree module goes entirely; if a file mixes real in-tree coverage with out-of-tree imports, split it and keep the in-tree part.
3. Fix the genuine stale-test bugs in place (e.g., patch the imported `time` module object instead of the dotted path).
4. Do not change any `qitos/` source in this brief. Do not touch `setup.py`/`qitos_zoo/` dangling refs (separate debt item).
5. CHANGELOG: one `Removed` entry listing the removed test groups and why.

**Acceptance.** `pytest -q` exits 0 (0 failed, 0 errors, 0 collection errors). The pass-count delta is explained in the PR description. `pytest tests/test_architecture_boundaries.py -q` stays green.

---

## Brief B — Break the `harness ↔ models` module-level cycle + clean root self-imports

**Context.** `docs/architecture/architecture-debt.md` ranks this as a P0 structural cycle: `qitos/harness/_adapters.py` and `qitos/models/profile_registry.py` import each other at module level and only survive via partial-initialization tolerance. Any future edit to either `__init__` can turn this into a hard `ImportError`. Additionally, ~12 sites import the root `qitos` package from inside subpackages (audit finding), creating latent cycles.

**Task.**
1. Read `docs/architecture/module-boundaries.md` (target dependency graph) and the specific D-items in `architecture-debt.md` covering this cycle; follow the exit plan written there (preset data下沉 / adapter 外移 as specified).
2. Make the dependency one-directional per the target graph. Moves must be pure import/structure changes — no behavior changes, no renames beyond what the debt doc specifies.
3. Clean the root-package self-imports: subpackage modules must import their siblings directly (`qitos.core.x`), never via the root `__init__`.
4. Shrink the ratchet allowlist in `tests/test_architecture_boundaries.py` to reflect the fixed edges (the allowlist is the progress dashboard — every fixed edge removes an entry).
5. Do not introduce new function-level (lazy) imports as a workaround; the boundary test and reviewer will reject them.

**Acceptance.** Boundary tests green with a strictly smaller allowlist. `python -c "import qitos"`, `python -c "import qitos.engine"`, `python -c "import qitos.harness"`, `python -c "import qitos.models"` all succeed from fresh interpreters, in any order. No new lazy imports (diff-reviewed). Full `pytest -q` green (after Brief A).

**Verification.** `pytest tests/test_architecture_boundaries.py -q && pytest -q && flake8 qitos/harness qitos/models && mypy qitos/harness qitos/models`.

---

## Brief C — Remove the `kit → benchmark` edge (kit domain-neutrality)

**Context.** Three kit files (audit: `kit/evaluate/cybench.py` and two siblings) import the deprecated `qitos.benchmark` package upward. This edge merges two known cycles into a three-node SCC `{benchmark, kit, recipes}` and violates the layering rule (kit is L2, benchmark is L3/deprecated). Benchmark-specific content must live in `recipes.benchmarks`, per AGENTS.md package boundaries.

**Task.**
1. Identify all kit files importing `qitos.benchmark` (grep `from qitos.benchmark|import qitos.benchmark` under `qitos/kit/`).
2. Relocate the benchmark-specific implementations to `qitos/recipes/benchmarks/`, following the existing recipes module pattern and naming.
3. Preserve the public CLI surface: `qit bench --benchmark cybench` behavior unchanged (check `tests/test_cli_governance.py` and existing bench tests; relocate tests together with the code).
4. Update the ratchet allowlist: the kit→benchmark edge entry is removed; re-run the cycle check — the SCC should shrink.
5. CHANGELOG entry (`Changed`): kit no longer depends on the deprecated benchmark layer.

**Acceptance.** `grep -rn "qitos.benchmark" qitos/kit/` returns nothing. Boundary tests green with the edge removed from the allowlist. Cybench tests pass from their new location; CLI governance tests pass.

**Verification.** `pytest tests/test_architecture_boundaries.py -q && pytest -q -k "cybench or bench" && flake8 qitos/kit qitos/recipes && mypy qitos/kit qitos/recipes`.

---

## Brief D — Campaign absorption, Batch E: engine correctness commits (start of `docs/v4/01`)

**Context.** `docs/v4/01-baseline-absorption.md` §2 Batch E lists five proven engine fixes from the campaign branches (remote refs already configured in this repo). This brief lands them, decontaminated, on a new integration branch. It requires Brief A merged first (a green baseline to verify against). Read `docs/v4/01-baseline-absorption.md` in full before starting; also `qitos/engine/AGENTS.md`.

**Task.**
1. Forensic safety: `git fetch origin`, then create local archive tags — `archive/cybergym-core` → `549bba4`, `archive/cybergym-x3` → `4b8c8a0` (origin/codex/x3-tool-contract tip), `archive/cybergym-queue` → `c6e8fc0` (origin/qitos_cybergym tip). Do **not** push; list the push command for the maintainer in the PR.
2. Create `feat/campaign-absorption` off `main`.
3. Cherry-pick, in this order, resolving per the notes:
   - `7388fb7` — multi-action blocking isolation (`engine/_action_runtime.py`, result merge by original index, `call_{step}_{i}` ids, multi-action render). **Exclude the GLM preset default-protocol flip hunk** (`harness/_presets.py`) — that decision belongs to Task 02; drop that hunk and note it in the commit message.
   - `427ce9c` — in-flight job dedup in `recipes/benchmarks/_shared.py` (only the `_shared.py` hunk; other riding-along changes in that commit are out of scope — leave them).
   - `39f423f` — runtime error reporting (`_report_runtime_exception`: stderr + file log + RECOVER trace event + `EngineResult.last_error`). This is the final state of a 3-commit evolution (`147468f`→`d9596e4`→`39f423f`); if it does not apply cleanly, recreate the final behavior from the combined diff rather than picking the intermediates (which contain `traceback.print_exc()` scaffolding that must NOT land).
   - `0370917` — `ContextConfig.tool_call_loop_detection_enabled` + `loop_max_repeats` (default on).
   - `2a2397e` — recovery-card passthrough in `_serialize_for_tool_message` + its regression test.
4. Decontaminate during resolution: `CYBERGYM_TASK_TRACE_DIR` → `QITOS_TRACE_DIR` (generic trace-dir probe); zero occurrences of `CYBERGYM`/`cybergym` in the resulting diff; port `tests/test_engine_error_reporting.py` with the renamed env var.
5. Add the missing regression test: a gate-blocked first action must not cancel its sibling actions in a multi-action step (per `docs/v4/01` §5).
6. CHANGELOG wave-1 entries under `Unreleased` (Fixed/Added; include the DockerEnv-style behavior notes only where behavior actually changed in this batch).

**Acceptance (from `docs/v4/01` §5, Batch E subset).**
- [ ] `git log main..feat/campaign-absorption` shows exactly the five picks (decontaminated equivalents acceptable, each explaining deviations).
- [ ] `grep -rniE 'cybergym' qitos/ tests/` → zero hits in newly added/changed lines.
- [ ] Multi-action isolation regression test green; error-reporting test green with `QITOS_TRACE_DIR`; loop-detection knob test green; recovery-card passthrough test green.
- [ ] `pytest -q` fully green; `flake8 qitos/engine && mypy qitos/engine` clean.

**Out of scope (do not pull in):** merge_tool/`72d3d7d` (Task 02), GLM preset protocol default (Task 02), model_summary/`a3597a9` and concurrency adjudication/`3f34a04` (Batch X, next wave), anything touching `qita/_cli_app.py` (Task 05), any vendored-agent content.

---

## Dispatch summary

| Brief | Prereq | Touches | Risk |
|---|---|---|---|
| A | none | `tests/` only | very low |
| B | A merged | `qitos/harness`, `qitos/models`, root imports, boundary-test allowlist | low (pure import moves) |
| C | A merged | `qitos/kit`, `qitos/recipes`, relocated tests | low |
| D | A merged | `qitos/engine`, `recipes/benchmarks/_shared.py`, new branch + tags | medium (cherry-pick resolution) |

Next wave after this batch: Batch M + Batch X from `docs/v4/01` (model layer and executor mechanics), then Task 02 conversation-kernel contracts.
