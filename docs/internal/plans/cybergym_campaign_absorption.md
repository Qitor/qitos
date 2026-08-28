# CyberGym Campaign Absorption Plan — archived source inventory

Status: superseded on 2026-08-29; do not dispatch this document.
Authoritative execution set: `docs/v4/00-goal-metric.md` through
`docs/v4/05-trajectory-data-plane.md`. Task 01 is closed there; Tasks 02–05
replace the workstreams and acceptance criteria below.

This file remains only as the branch/commit inventory and historical reasoning
used to derive the v4 plans. Its old sequencing, statuses, metrics, and target
paths are not current instructions.

Former companion design: `v0.7_native_agent_kernel.md`.
Author: framework team
Sources: campaign branches `origin/qitos_cybergym`, `core` (Cyborg checkout), `origin/core`, `origin/codex/x3-tool-contract`, `origin/feat/runtime-context-in-tool`; Cyborg monorepo artifacts under `/Users/morinop/Desktop/cyborg/` (`Cyborg/cybergym_agent/`, `audit/cybergym-agent/`, `Cyborg/experiments/cybergym/`).

---

## 1. Position and non-negotiable doctrine

qitos's goal is unchanged: the researcher's agent R&D framework, in the position PyTorch holds for deep learning. That analogy dictates the layering:

| Layer | PyTorch analogue | qitos home | Campaign content destination |
|---|---|---|---|
| Mechanism substrate | `torch` (core, nn, optim, utils.data) | `qitos` core/engine/models/trace/harness + domain-neutral kit | WS1–WS5 of this plan |
| Reference methods | torchvision models | `qitos.recipes` method templates (ReAct/LATS/…) | nothing from this campaign — single-campaign strategies are not reference methods |
| Research strategies, domain packs | user code / ecosystem packages | out-of-tree: cybergym-agent, future `qitos_zoo` | all campaign methodologies (§6 audit) |
| Experiment composition | user training scripts | monorepo `experiments/` (already extracted) | already out |

**Domain-neutrality test — the inclusion gate for every framework change:** a change is framework material only if it is expressible using agent-execution vocabulary alone (state, observation, decision, action, tool, model, trace, budget, experiment, hook, protocol). If a proposal needs *submit, PoC, sink, vulnerability, oracle, constraint board, knowledge pack, harness, sanitizer* — it is strategy or domain content and stays out of `qitos/`.

Corollaries:

1. The framework absorbs the campaign's **engineering** lessons (correctness, contract preservation, data plane, observability mechanics), never its **strategy** lessons.
2. Where campaign strategies hacked around missing primitives, we fix the primitive (§6), never port the strategy.
3. Existing benchmark adapters inside the package (gaia/tau/cybench/cybergym/osworld, deprecated) are legacy surface: the direction is out-of-tree packages discovered via the `qitos.benchmark.runners` entry-point seam (P3 RFC, community-visible).

## 2. Branch topology (as of 2026-08-27)

```
e82ef2f  merge-base: "cybergym optimization v1 - first stable version"
├── WhitzardOS main:        e82ef2f + 14 commits (Responses API, compact history, fixes #33–#36)  ← ABSORB TARGET
├── origin/qitos_cybergym:  base + campaign commits + vendor syncs v14–v19nb, sticky routing, container_env   (37 ahead of old main)
│     └── diverged sibling; 10 commits not in local core
├── core (Cyborg checkout): base + 32 commits incl. d2eb969 "extract cybergym-agent",
│     f7fe812/549bba4 experiments-layer move-out
│     └── origin/core = core + 10 hardening commits (427ce9c…05a1c82)
│           └── origin/codex/x3-tool-contract = origin/core + 4 (181ba65, 7fd1fee, 75e3c53, 4b8c8a0 canonical trace export)  ← MOST ADVANCED FRAMEWORK LINE
└── origin/feat/runtime-context-in-tool: merge_tool observation delivery (72d3d7d), branched mid-campaign
```

Sequencing implication: absorb from `origin/codex/x3-tool-contract` first; graft the few unique items still only on `qitos_cybergym` (sticky inference-key routing 5e013e9/d16e775; DockerEnv `container_env` ecd817d; TUI task_id/action fix e37540f). The remaining qitos_cybergym-only commits are vendored-agent syncs whose content lives in the separate cybergym-agent package — discard.

Conflict zone during replay onto current main: `qitos/models/openai.py` (main added Responses API `_openai_responses.py` + kwargs relocation; campaign line rewrote chat-completions paths), `qitos/kit/history/compact_history.py` (main has its own changes; x3's ae65cb3 adds deterministic slide-window), `qita/_cli_app.py`.

## 3. Mechanism invariants validated by the campaign

1. **Domain neutrality is architectural, not cosmetic** (§1). The campaign's own endgame — extracting the agent and the experiments layer out of the package — is the pattern to preserve.
2. **The engine must never silently swallow failures** — recovery-suppressed exceptions need surfaced diagnostics (`last_error`, file logs, trace events).
3. **Model-visible contracts are sacred**: authored tool descriptions, schema parameter descriptions, tool-summary projection, message shapes (no trailing user turn after tool results where the provider dislikes it) decide real-world success more than any algorithm.
4. **Graded termination signals are a mechanism need**; `TaskCriterionResult` + critic stop already model them — verify sufficiency, do not add new vocabulary.
5. **Reproducibility = config snapshot + git commit + traces on disk**; fleet-grade durable ledgers matter once runs cross host boundaries (guide material, not framework code).

## 4. Workstreams — mechanism absorption

### WS0 — Baseline reconciliation (prerequisite)

- Integration branch off current `WhitzardOS main`; replay order: (1) x3 framework commits per WS below; (2) `72d3d7d` merge_tool rebased onto the hardened `_model_runtime`; (3) qitos_cybergym-only picks (sticky routing, container_env, e37540f).
- Resolve openai.py against Responses-API main; keep both chat-completions fixes and the responses path.
- AC: `pytest -q` green; no file under `qitos/benchmark/cybergym/` reintroduced; CHANGELOG batched per wave.

### WS1 — Engine correctness fixes (cherry-pick directly)

| Item | Source | AC |
|---|---|---|
| Multi-action blocking isolation (blocked action no longer cancels siblings; result ordering/tool_call_id stable) | 7388fb7 (`engine/_action_runtime.py`) | unit test: gate-blocked first action does not cancel second |
| Concurrent duplicate-job prevention in shared benchmark execution | 427ce9c (`recipes/benchmarks/_shared.py`) | in-flight set rejects repeated job_key |
| Runtime error reporting: stderr + file log + trace event + `EngineResult.last_error` | 147468f/d9596e4/39f423f | `tests/test_engine_error_reporting.py` passes; no `CYBERGYM_*` env names — generic trace-dir probe |
| Tool loop detection opt-out with default-on guardrails | 0370917 (`ContextConfig.tool_call_loop_detection_enabled`, `loop_max_repeats`) | knob documented; warn-level repeats recorded as events |
| Recovery-card passthrough (stop double-wrapping string cards into `{"error":...}`) | 2a2397e (`_serialize_for_tool_message`) | regression test keeps card text intact |

### WS2 — Model/provider layer

- Native reasoning-field preservation end-to-end: `ModelResponse.reasoning_fields/reasoning_source` (75e3c53, superseding the earlier `reasoning_content` extraction 5452e23); dedupe when reasoning equals raw output (71bb4e1). AC: provider dict/object shapes tested; TUI/thinking rendering dedupes.
- Authored-vs-docstring description precedence (181ba65, `tests/core/test_tool_description_contract.py`) plus docstring `:param`/Google-style parsing (6379f25, audit `_strip_param_docs` continuation edge).
- Provider kwargs hygiene: relocate unknown SDK kwargs (`chat_template_kwargs`, `do_sample`) into `extra_body` instead of silent TypeError degradation (7fd1fee).
- Sticky routing headers for multi-endpoint serving (5e013e9/d16e775): generalize behind a provider-transport config knob, neutral naming.
- **Observation-delivery policy** (mechanism): fold the `<RUNTIME_CONTEXT>` wrapper and merge_tool delivery (72d3d7d) into one documented `EngineConfig` field (`user` | `merge_tool`), replacing the `CYBERGYM_OBSERVATION_DELIVERY` env gate. AC: conversation never ends on a trailing user turn under merge_tool; fallback appends a user turn (state never lost); protocol doc updated. Passes the neutrality test: it is about message-shape mechanics, not content.

### WS3 — Tool interface & concurrency governance

- Four-level concurrency adjudication replacing hardcoded tool whitelists: policy `parallel_tool_names` → needs_approval veto → explicit `concurrency_safe` flag → read_only heuristic; missing slots return `[TOOL_RESULT_MISSING]` card; unknown tool names rejected with an error listing available tools (3f34a04). **Remove** the CyberGym tool-name list from `action_executor.py`. AC: whitelist gone; adjudication matrix unit-tested.
- `model_summary` projection: tools may provide an LLM-facing summary projected across native history, budget trimming, TUI, and trace while canonical structured data is retained (a3597a9 + design doc `docs/internal/plans/model-summary-tool-projection.md`).
- State receipts hook: optional `agent.commit_action_results(state, actions, results, step_id)` pre-history commit + `StopReason.INFRASTRUCTURE_INVALID` (e9bde23).
- Tool-hook step numbers on the native tool-call path (7fd1fee a-side: `ToolHookContext.step_id` = current step, not 0).

### WS4 — Context, memory, and prompt mechanics

- Deterministic long-context recovery: `resolve_request_budget()` (hard_input_budget/soft_input_target/emergency_output_limit/min_output_reserve), occupancy telemetry, recovered-request budget recomputation (1e9d9b4).
- Deterministic slide-window trimming by whole step units (ae65cb3) reconciled with mainline compact_history; expose high-water/target/reserve knobs in `ContextConfig` with provider-neutral defaults (drop 150k/130k literals).
- **Pointer-indexed external artifact store + durable fields surviving compaction** — the neutral storage mechanism the campaign's evidence memory hacked together by hand. Implement as extension of `qitos.kit.memory` + `engine/_context_runtime`. This is mechanism: "externalize large payloads, keep lightweight pointers, preserve declared durable fields" contains no domain vocabulary.
- Prompt resource loading utility (importlib.resources + cached `{{var}}` substitution), low priority: neutral convenience on top of existing `PromptSpec/PromptBuilder`; gate on a second consumer.

### WS5 — Observability mechanics & data plane

- **Canonical trajectory store** (`qitos/trace/canonical.py`, 4b8c8a0): `TRAJECTORY_SCHEMA="qitos.trajectory.v1"`, append-only, content-addressed dedup, `safe_projection` redaction; training/audit projections (`export.openai_record()`, `swift_record()`) as optional adapters (the agent-research equivalent of a data loader — this is the substrate for SFT/distill/eval datasets). AC: round-trip replay/export tests; redaction suite tested; docs/guides/observability updated.
- qita diagnostic workbench (85a8099): step_interactions causal view, insights flags, inspector tabs, themes. **Extract cybergym-specific derivations into a registered signals-plugin interface** (`_cybergym_signals` et al. move out).
- Rendering mechanics: multi-action banners + per-index observations (7388fb7), per-task TUI log files via TeeConsole (d2ee976), run-start task banner (707979f), user-declared phase badges. Replace hardcoded Constraint Board/Task Memory/Sink Candidates renderers and the `_tui_*` plumbing in `_state_stats` with a **generic declared-render-section mechanism**: agents register named sections + optional color hints; the framework renders blindly. AC: constraint-board-style output achievable with zero CyberGym terms in qitos source.
- Preview/truncation limits: revert debug-era inflation (parser_raw_preview 50000, renderer 50000, cli_render 200000) to configured defaults with explicit deep-debug knobs (c01587e scope review).

## 5. (folded into §6)

## 6. Primitive sufficiency audit — replaces v1 "methodology promotion"

The framework question for every campaign strategy is exactly one: *which primitive did it need, does qitos already provide it, and is a minimal neutral extension justified?* The strategies themselves stay out-of-tree (cybergym-agent / future zoo).

| # | Campaign strategy (stays OUT of qitos) | Primitive it needed | qitos today | Framework action |
|---|---|---|---|---|
| 1 | Six-section observation brief + revision slots + validation/budget | Sectioned observation assembly + revision counters + validation seam | `Observation` is a bare dict; `StateValidationGate` is state-side only | **Candidate primitive (small)**: declarable observation sections with revisions + validation hook. Land only after a second, non-security consumer sketch exists |
| 2 | Feedback taxonomy → required-action arbitration | Critic verdicts + action gating + structured injection into next prompt | `Critic` + `_apply_critic_patches`, `InterceptorChain`, validation gate exist | None: add a composition test + guide showing the pattern |
| 3 | Graded verdict / partial-hit continuation | Graded termination signals | `TaskCriterionResult`, `critic_stop`, stop-criteria chain | Verify sufficiency; docs only |
| 4 | Constraint board / chain gates / candidate pool | Typed state fields + channel reducers + declared render views | `channel.py` reducers + `field_reducers` exist; render views arrive via WS5 declared-sections | None beyond WS5 |
| 5 | Pre-submission consistency guards | Interceptor chain + block/warn signals | `InterceptorChain` + `ToolValidationResult` | None; example lives in zoo/agent docs |
| 6 | Submit queue / fingerprint dedup / idempotency | — (pure strategy) | interceptors + tool policy suffice | None |
| 7 | Knowledge packs + evidence registry | Skill loading mechanism | `qitos.kit.skill` exists | None; packs stay in cybergym-agent |
| 8 | Recipe IR + audited rewriter | — (pure strategy) | — | None |
| 9 | Phase checkpoints / budgets / force-progress | Planning + budgets | `kit/planning/phase_engine`, `TaskBudget`, stagnation criteria | Verify sufficiency; optional neutral extensions only in kit/planning |
| 10 | Harness modeling / sanity gates / frontier probe | — (strategy-shaped) | — | None |
| 11 | Sanitizer/crash parsing | Verdict normalization | `TaskCriterionResult` | None (domain) |
| 12 | Compaction + externalized evidence + durable facts | Pointer-indexed artifact store | partial | **WS4 mechanism** (in scope, neutral storage) |
| 13 | Prompt resource tree combination | Prompt assembly + resource loader | `PromptSpec/PromptBuilder` | Optional small loader utility (WS4, gated) |
| 14 | Per-tool result processors | Tool hooks / interceptors | `ToolHook` + interceptors | Optional registry convenience in kit/tool, gated on second consumer |
| 15 | Benchmark adapter registration | Entry-point discovery | added by d2eb969 | WS8 verify on main |
| 16 | RUNTIME_CONTEXT protocol | Observation-delivery policy | was env-gated hack | **WS2 mechanism** (in scope) |

Net effect versus v1: framework scope shrinks sharply — ten of sixteen strategies require **no framework action at all**; the framework's obligation is that its primitives (critics, interceptors, gates, channels, budgets, stop criteria) compose cleanly enough that researchers can build such strategies themselves.

## 7. Out-of-tree strategy track

- cybergym-agent remains the living strategy package, discovered via the entry-point seam.
- Propose `qitos_zoo` (directory already reserved, empty) as the sister package for research strategies that prove reusable **across at least two independent campaigns**. Gate: a strategy enters zoo only after independent reuse — never directly into qitos.
- One mechanism tutorial (guide) demonstrating how a feedback-arbitration-style pattern composes from critics + interceptors + validation gates, written with zero domain vocabulary — this is how the campaign's strategic lessons transfer to researchers without polluting the framework.

## 8. Experiment-layer guidance & hygiene

- Mainline the entry-point runner discovery (d2eb969) if not already on main; keep all benchmark adapters out-of-tree going forward.
- Document the validated experiment pattern as a guide: YAML configs with `${VAR}` interpolation, regenerable spec tables, JSONL results + meta.json snapshots (git sha), resume semantics; reference fleet durable-ledger lessons (per-task atomic records, leases/heartbeats, attempt caps). Target: `docs/guides/scaling-experiment-runs.mdx`.
- Review the workspace symlink loosening (85a8099) as a permission-policy change: keep only behind an explicit escape-hatch flag; deny-by-default otherwise.
- P3 RFC (separate decision): migrate in-package benchmark adapters (deprecated `qitos/benchmark/*`, `recipes/benchmarks/*`) to out-of-tree packages on the entry-point seam, making the package fully domain-neutral. Community-visible; needs its own migration plan.

## 9. Decontamination checklist (must pass before absorption is called done)

- [ ] No `CYBERGYM_*` env var names anywhere in `qitos/`
- [ ] Neutrality grep clean: `grep -rniE 'cybergym|\bpoc\b|sink_|vuln|sanitizer|oracle|gdb' qitos/` returns only whitelisted legacy hits (deprecated benchmark shims pending §8 P3)
- [ ] No agent tool-name literals in engine/render/qita sources
- [ ] Preview/truncation limits back to sane configured defaults
- [ ] cybergym-branded functions extracted from qita CLI into plugin registrations
- [ ] `docs/zh/benchmarks/cybergym.mdx` no longer references deleted scripts/vendored layout
- [ ] Temp diag scaffolding replaced by the formal error reporter
- [ ] GLM preset default switch to multi-action protocol verified intentional and release-noted

## 10. Documentation & announcement sync

- CHANGELOG: one curated wave per milestone (note GLM protocol default change, concurrency-safety policy change, workspace-permission flag as Breaking where applicable).
- docs/: concepts/engine (delivery modes, receipts hook), guides/observability (canonical trajectories, qita workbench), new scaling-experiments guide, strategy-composition tutorial (§7); zh mirrors for user-facing pieces.
- README news: milestone-level announcements (e.g., "campaign-hardened engine + trajectory v1 data plane"), not per-commit.

## 11. Milestones

- **P0 (days)**: WS0 branch setup; WS1 fixes; WS3 first three items; §9 initial sweep. One reviewed PR series; changelog wave 1.
- **P1 (≈1–2 wks)**: WS2 complete (delivery-mode promotion to EngineConfig); WS4 context/memory mechanisms; WS5 canonical trace + rendering generalization; changelog/docs wave 2.
- **P2**: §6 audit executed (composition tests, guides, the one gated observation-sections primitive if a second consumer is shown); §7 zoo RFC.
- **P3**: §8 benchmark out-of-tree RFC + guides; §9 final sign-off; README news; version bump (v0.7.x series target); campaign retrospective for docs/blog.

## 12. Verification matrix

- `pytest -q` after every wave; targeted suites: `tests/test_engine_error_reporting.py`, `tests/test_model_summary_projection.py`, `tests/core/test_tool_description_contract.py`, `tests/test_qita_cli.py` (ported), plus new tests per WS.
- Static: `flake8 qitos/core qitos/engine qitos/models qitos/trace && mypy qitos/core qitos/engine qitos/models qitos/trace`.
- Packaging when touching exports/entry-points: `python -m build && python -m twine check dist/*`.
- Smoke: one GAIA/CyBench recipe run via `qit bench run` (no benchmark-path regressions); optional cybergym-agent smoke against the separated package to validate the entry-point seam.
- Neutrality: §9 grep gate runs in CI or pre-commit once clean.

## 13. Risks

1. openai.py three-way conflict (main Responses API vs campaign chat path) — land WS2 with responses-path tests in CI from day one.
2. User-visible behavior changes (GLM preset multi-action default, concurrency-safety policy, workspace flag, truncation defaults) — Breaking/release notes required.
3. **Over-inclusion** — the historical failure mode this plan corrects; mitigation: the §1 neutrality test is a merge gate, enforced by the §9 grep.
4. **Under-absorption** — strategies that genuinely needed a primitive get it via the §6 audit table; the table is the tracking instrument.
5. Losing forensic history — tag campaign branch tips (`archive/cybergym-campaign-x3` etc.) before any cleanup.
