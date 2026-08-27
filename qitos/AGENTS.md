# qitos/ AGENTS.md

Rules for the `qitos` package as a whole. Deeper rules: `core/AGENTS.md`, `engine/AGENTS.md`, `kit/AGENTS.md`. Full boundary matrix: `docs/architecture/module-boundaries.md`.

## Purpose

The framework package: kernel contracts (`core`), execution runtime (`engine`), implementations (`kit`), observability (`trace`/`tracing`/`qita`/`render`), model access (`models`/`harness`), research layers (`recipes`, deprecated `benchmark`), and edge tooling (`cli.py`, `demo`, `config`, `experiment`, `leaderboard`, `hf`).

## Owns / Does Not Own

- Owns agent-execution vocabulary only (see the domain-neutrality test in root `AGENTS.md`).
- Does NOT own: product agents, benchmark datasets, domain strategies, campaign scripts — those belong to `qitos-zoo`, external assets, or user code.

## Non-obvious facts (things local code reading won't tell you)

1. **Two observability generations coexist.** `qitos/trace/` (v1: flat `TraceEvent`/`TraceStep` → `runs/{run_id}/manifest+events+steps.jsonl`) is the production path and a **frozen compatibility contract** — qita, benchmark runners, evaluate, and hf push/pull all consume it. `qitos/tracing/` (v2: spans + processors incl. W&B/MLflow) is built but not wired by default and must not replace v1 artifacts until `docs/v4/05` (trajectory data plane) lands. `render/ClaudeStyleHook(output_jsonl=...)` is a third artifact path — don't add a fourth.
2. **`qitos/harness/` is not a test harness.** It holds `FamilyPreset` model-family defaults consulted by engine, models registries, and `qit bench --preset`. Treat it as kernel infrastructure (rename to `model_presets` is planned debt D7).
3. **`qitos/benchmark/` is deprecated mid-migration.** New/updated benchmark work goes to `qitos/recipes/benchmarks/`. The two packages currently import each other (module-level, 5 files each) — never add a new edge in either direction; port code to shrink the tangle.
4. **Root-level leaves.** `protocols.py` (I/O protocol registry) and `prompting.py` (prompt builder) are stdlib-only modules deliberately outside `core` because engine/kit/harness share them; do not move them into a subpackage casually, and do not add imports of qitos modules to them (the lazy `protocols.py -> kit.parser` import is legacy debt V7).
5. **Import-cycle landmines.** `harness <-> models` is a live module-level cycle held together by Python partial-init tolerance; `subpackages -> root qitos -> engine -> (lazy) kit` is a latent cycle. Consequence: **never promote a function-level (lazy) import of `kit`/`mcp`/`cache` inside `engine/` to module level**, and never import `from qitos import ...` inside the package — import `qitos.core.x` / `qitos.engine.x` directly.
6. **Deprecated but still imported**: `qitos/debug` (qita's fork feature uses it), `qitos/cache` (engine auto-wrap + experiment), checkpoint v1 `CheckpointManager` (experiment). Don't build new features on them.
7. `evaluate/` and `metric/` are thin contract packages; their implementations live in `kit/evaluate/` and `kit/metric/`.

## Allowed / Forbidden Dependencies

Enforced by `tests/test_architecture_boundaries.py`. Summary: dependencies point downward `edge -> recipes -> kit -> engine -> core`; nothing imports `cli`/`qita`/`demo`/`experiment`/`leaderboard`/`hf`/`debug`/`cache`; no new module-level cycle; no root self-import. When you remove a legacy violation, delete its allowlist entry in the same change.

## Invariants

- Root `qitos/__init__.py` exports kernel contracts only (guarded by `tests/test_public_surface.py`); no product or security symbols.
- `run_id`/`step_id`/`phase` semantics flow unchanged from engine events into v1 trace artifacts.
- `qit` and `qita` console entrypoints (`setup.py`) must keep working: `qit --version`, `qit demo minimal`, `qita board --logdir runs`.

## Testing

`pytest -q` covers the package; targeted suites listed in root `AGENTS.md`. After dependency-relevant edits run `pytest tests/test_architecture_boundaries.py tests/test_public_surface.py -q`.
