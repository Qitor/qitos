# Task 05 — Trajectory Data Plane & Observability Generalization

Status: actionable design
Parents: `docs/internal/plans/v0.7_native_agent_kernel.md` §5 (Pillar E); absorption plan WS5
Depends on: Task 01 (canonical trace commit 4b8c8a0 base, error reporting); Task 02 (canonical turns are the export unit)
Milestone: P1–P2

Reference implementation: `origin/codex/x3-tool-contract` commit 4b8c8a0 (`qitos/trace/canonical.py`, `qitos/trace/export.py`, `TraceStorageConfig`) and the qita workbench commit 85a8099 (`qita/_cli_app.py` step_interactions/insights + `tests/test_qita_cli.py`).

---

## 1. Goal

One **canonical, space-efficient trajectory store** that is the single source of truth for replay, debugging (qita), and training-data production (SFT/distill), with exporters aligned to the formats the ecosystem actually consumes. Plus the observability generalization that decontaminates the campaign's qita/TUI work.

Why it matters: the research loop is *run agents → collect trajectories → analyze/train*. A framework in the PyTorch position must treat trajectory storage as its DataLoader-equivalent: canonical, deduplicated, compressed, exportable.

## 2. Scope

In: canonical store hardening (compression, dedup ratios, index); exporters (OpenAI messages, ShareGPT, ms-swift); redaction everywhere; qita reads the store; workbench plugin-signals extraction; declared render sections (generic replacement for campaign's constraint-board TUI blocks); truncation-default rollback.

Out: analysis/leaderboarding (existing modules untouched); any domain-specific signal logic (moves to cybergym-agent as a plugin); otel/Letta exporters (noted as extensions).

## 3. Canonical store (base: 4b8c8a0, extended)

Layout per run:

```
runs/<run_id>/
  manifest.jsonl        # append-only turn records (references by hash)
  blobs/<sha256>        # content-addressed payloads (messages, tool schemas, raw outputs), zstd-compressed
  index.sqlite          # optional query index (built lazily)
  meta.json             # run_id, git sha, config snapshot pointer, schema, stats
```

Mechanics (keep from campaign commit, then extend):
- `TRAJECTORY_SCHEMA = "qitos.trajectory.v1"`: append-only; every message/tool-schema stored once, referenced by hash; turn records reference hashes + roles + timings. With Task 02, the canonical turn model is the record unit (assistant turns with N tool calls + batched results stay atomic).
- **Add zstd** compression for blobs (`compression: "zstd"` in meta; stdlib-adjacent via `zstandard`, already a candidate dep — justify in pyproject).
- **Add stats**: dedup ratio, compressed bytes, per-step model-visible chars vs stored chars (the budget/telemetry numbers researchers actually want).
- TraceWriter `TraceStorageConfig`: `capture_debug_artifacts` stays opt-in; `flush_every` stays; add `compression`, `index` toggles.
- `safe_projection` redaction (keys/bearers/hosts/tokens) runs on **every export path** — no exporter may bypass it (test-enforced).

Acceptance target: ≥10× smaller than naive per-step JSON dumps on a real campaign run (dedup + zstd), measured by a scripted benchmark committed under `scripts/`.

## 4. Exporters — `qitos/trace/export.py`

| Exporter | Shape | Consumer |
|---|---|---|
| `openai_record(run)` | native OpenAI messages + tools schema, transaction manifest | universal analysis/replay; OpenAI-ecosystem tooling |
| `sharegpt_record(run)` | ShareGPT JSONL (`conversations` with `from`/`value`, tool calls embedded) | Hermes/Axolotl-style SFT pipelines |
| `swift_record(run)` | ms-swift roles + loss-mask flags | ms-swift training |

Rules:
- Export from the canonical store only (never from live objects) — replay parity by construction.
- Round-trip tests per exporter: `store → export → reimport → identical turns`.
- Loss-masking policy (swift) is explicit and tested: mask tool results/system unless configured otherwise.
- Multi-action turns export faithfully (N calls + N results in one assistant block — the native shape trainers expect).

## 5. qita workbench generalization (decontaminate 85a8099)

- Land the workbench mechanics: `step_interactions` causal pairing (action↔result by `action_id`/order, environment results separated, unmatched evidence bucket), `_build_step_summaries/_build_tool_stats/_build_phase_stats`, insights flag priority, inspector tabs, themes, Focus Navigator, mobile CSS; port `tests/test_qita_cli.py`.
- **Extract domain signals into a plugin seam**:

```python
# qitos/qita/signals.py
class SignalsPlugin(Protocol):
    benchmark: str                       # registration key
    def signals(self, state_diff: dict) -> dict        # neutral: typed key/values
    def focus(self, run: CanonicalRun) -> FocusView | None
# registration: entry_points(group="qitos.qita.signals") or explicit registry
```

  The campaign's `_cybergym_signals`/`_build_cybergym_focus` move to cybergym-agent under this interface; the built-in flag set keeps only neutral flags (parser_error, tool_or_event_error, critic_stop, model_error, unrecoverable_error…).
- qita `board`/`replay`/`export` read the canonical store directly; replay becomes a deterministic manifest rebuild.

## 6. Declared render sections (replace campaign TUI blocks)

- The campaign hardcoded Constraint Board / Task Memory / Sink Candidates rendering + `_tui_*` metadata plumbing into `_model_runtime._state_stats` and `render/_hooks_impl.py`. Replace with:

```python
# agent side (any AgentModule):
def render_sections(self, state) -> Iterable[RenderSection]   # {title, lines, hints: {token: color}}
# framework side: renders blindly, no vocabulary knowledge
```

- `RenderSection` lines are plain text; optional `hints` map substrings to semantic colors (the campaign's FIRST BLOCKER/refuted/confirmed coloring generalized).
- TUI hook renders declared sections; per-task log file via TeeConsole stays (d2ee976). Phase badges: user-declared phase strings with a default color wheel (replaces the five hardcoded campaign phases).
- AC: constraint-board-identical output reproducible from cybergym-agent with zero CyberGym terms in qitos source.

## 7. Truncation-default rollback

Revert debug-era inflation to configured defaults with explicit knobs (absorption plan §9): `parser_raw_preview` 50000→500 (knob `QITOS_PARSER_PREVIEW`), renderer body caps 50000→2000/20000 tiered, `cli_render` 200000→20000, hooks `max_preview_chars` 50000→800. Deep-debug profiles set knobs via config, not source edits.

## 8. Implementation steps

1. Land 4b8c8a0 base (from Task 01 batch or direct if not already) + zstd + stats + `scripts/benchmark_store_size.py`.
2. Exporters + round-trip/redaction suites.
3. qita store-backed reads + workbench mechanics port + signals plugin seam (neutral flags only).
4. Declared render sections + TeeConsole retention + phase color wheel; port multi-action render from Task 01 picks.
5. Truncation rollback sweep + knob docs.
6. Docs: `docs/guides/observability.mdx` major update (canonical store, exporters with format examples, signals plugins, declared sections); `docs/zh` mirrors; CHANGELOG wave 2/3.

## 9. Acceptance criteria

- [ ] Size benchmark: ≥10× vs naive dumps on the reference run; report committed.
- [ ] Round-trip tests green for all three exporters; redaction suite green and enforced (exporter bypass attempt fails a test).
- [ ] qita works end-to-end from the store: board, replay (deterministic rebuild), export.
- [ ] `grep -rniE 'cybergym|_cybergym_signals|sink|constraint.?board' qitos/qita qitos/render qitos/engine` → zero hits; signals logic lives behind the plugin seam.
- [ ] Truncation defaults restored; every former debug inflation is a documented knob.
- [ ] A campaign-format run replays identically before/after generalization (fixture from the x3 branch).

## 10. Verification

```bash
pytest -q tests/trace/test_canonical.py tests/trace/test_export.py tests/test_qita_cli.py tests/render/test_declared_sections.py
python scripts/benchmark_store_size.py --run <reference-run>
pytest -q
flake8 qitos/trace qitos/qita qitos/render && mypy qitos/trace qitos/qita qitos/render
```

## 11. Risks / open questions

- Q: zstd dependency — `zstandard` is a compiled dep; if unacceptable, ship optional extra (`qitos[trajectory]`) with gzip fallback and keep the format field honest.
- Q: ShareGPT tool-call encoding is not formally standardized — document the exact convention we emit (assistant `tool_calls` JSON in `value`, tool role records) and version it in the exporter, not the store.
- Risk: signals plugin seam could become a domain backdoor — the neutrality grep gate (absorption §9) covers qita/render; keep plugin interface typed and vocabulary-free.
