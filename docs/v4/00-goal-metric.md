# Task 00 — Goal Definition & Acceptance Metric for the v4 Framework Round

Status: agreed direction (this document is the acceptance anchor for Tasks 01–05)
Position: sibling of `docs/internal/plans/cybergym_campaign_absorption.md` (v2) and `docs/internal/plans/v0.7_native_agent_kernel.md`

---

## 1. The goal, stated precisely

North star: with the new qitos, the Cyborg campaign agent (`cybergym_agent`, out-of-tree) can be rebuilt with drastically less code — excluding prompts.

The literal reading ("reimplement cybergym_agent in 10% of its code") is **not achievable for the full agent** and must not be pursued as written: hitting it by LOC pressure would push domain strategy into the framework, violating the domain-neutrality invariant (AGENTS.md, absorption plan §1). The goal is therefore defined as two measurable acceptance metrics below.

## 2. Baseline measurement (2026-08-27, `cybergym_agent` out-of-tree copy)

Python LOC, excluding tests and prompts: **50,872** total.

| Subsystem | LOC | Classification under v4 |
|---|---|---|
| `analysis/` (tree-sitter static analysis service) | 17,364 | domain — unchanged |
| `tools/` | 11,067 | ~4,000 mechanism lines absorbed by Task 03; ~6,500 domain tools stay (submit/note/static), shrinking via framework card/render contracts |
| `runtime/` (reducers, policy, history, tracing) | 7,719 | ~2,000 absorbed by Tasks 02/04/05 (messages, response normalization, history, context, tracing, token meter); reducers/policy are strategy and stay |
| `scripts/` (ops tooling) | 5,205 | not agent implementation — excluded from the "agent proper" denominator |
| `preflight/` (task bootstrap, harness discovery) | 3,683 | domain — small reuse of framework tools |
| `benchmark/` (adapter, runner, environment) | 1,922 | shrinks to ~700 via entry-point seam (Task 01 / absorption WS8) |
| `domain/` + `knowledge/` (state models, plans, ontology) | 2,176 | domain — unchanged |
| `agent.py`, `cli.py`, `__main__.py` | 1,007 | shrinks to ~400 via AgentModule hooks + prompt resources |
| `offline_eval/` | 621 | mostly replaced by Task 05 export/qita tooling |

Derived figures: eliminable mechanism code ≈ **10,000–11,000 LOC**; faithful reimplementation floor ≈ **38,000–40,000 LOC (75–80% of the full repo)**; "agent proper" denominator (excluding `analysis/` + `scripts/`) = **28,300 LOC**, floor ≈ **55–60%**.

## 3. Acceptance metrics

### Metric A — Mechanism-zero (hard gate, per merged task)

**The agent repository contains zero lines that exist because the framework lacked a feature.** Operationally, after Tasks 01–05 land, none of the following may appear in the out-of-tree agent:

- `validate_input` no-op bypasses (replaced by Task 03 soft-validation contract);
- hand-rolled card envelopes, truncation/pagination/budget logic (Task 03 budgets + next_action);
- hand-rolled message assembly, decision-response normalization, reasoning handling (Task 02);
- hand-rolled history/compaction/context survival management (Task 04);
- hand-rolled tracing/telemetry plumbing (Task 05 canonical store);
- tool concurrency whitelists or token metering reimplementations (Task 01 adjudication + budgets).

Check: a dated audit note in the agent repo listing the removed categories with before/after LOC, reviewed alongside the corresponding v4 task's acceptance list.

### Metric B — The 10% reference agent (demonstration, shipped as an example)

A **reference reimplementation** of a CyberGym-class agent built purely on new qitos: `coding_toolset()` + a domain submit tool + a minimal state machine + prompts. Target: **≤ 2,800 LOC (≤10% of the 28,300 "agent proper" baseline)**, shipped under `examples/` (framework repo) or the agent monorepo with a CI-run smoke.

Performance anchor (prevents the number from being gamed by gutting capability): on an agreed fixed task subset, the reference agent must reach **≥50% of the full agent's pass rate** — the exact subset and full-agent score are recorded in this file when Metric B work starts (baseline first, then build).

### Non-goals (guardrails)

- No domain vocabulary, strategy code, or benchmark-specific logic enters `qitos/` to improve either metric (neutrality grep in absorption plan §9 stays a merge gate).
- The full campaign agent's strategy core (analysis, reducers, domain tools) is expected to remain large; shrinking it is research work, not framework work.

## 4. Anchoring

- Tasks 01–05 each close part of Metric A; their acceptance lists are the decomposition of §3A.
- Metric B becomes executable after Tasks 02+03 land; schedule it as the capstone of this round (P2/P3).
- Progress reporting uses two numbers only: "mechanism LOC removed from the agent repo" and "reference agent LOC / pass-rate anchor". Do not report raw framework LOC growth.
