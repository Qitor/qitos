# Task 03 — Native ACI Toolset: `qitos.kit.aci`

Status: actionable design
Parents: `docs/internal/plans/v0.7_native_agent_kernel.md` §3 (Pillar C)
Depends on: Task 01 (model_summary projection, concurrency adjudication, description-precedence contract); benefits from Task 02 (parallel-action turns) but can start in parallel
Unblocks: the 50-line DX example (shared with Task 02)
Milestone: P2

Primary reference: the battle-tested tool layer of the out-of-tree Cyborg campaign agent (`cybergym_agent/tools/` — `filesystem, navigation, shell, submit, note, switch, todo, workspace, search_service, names, registry` modules, `rendering/`, `docs/x2.md`, `ARCH.md`; git lineage on the campaign line, latest synced shape at campaign commit `a02e96c` and successors). Those tools were iterated against real traces (x2.md measures e.g. GREP median 38 calls on timeout tasks vs 12 on solved) and encode the ACI lessons this task ports, decontaminated.

---

## 1. Goal

Ship a domain-neutral, production-grade toolset that makes a Claude-Code-class coding agent a ~50-line program on qitos, and codify the **ACI engineering rules** the campaign proved (output budgets with explicit truncation, error-as-card recovery, pagination affordances, read-before-write concurrency control) as framework contracts + kit implementations.

## 2. Scope

In:
1. Three small **framework contracts** the toolset needs (soft validation, card envelope, summary-render dispatcher).
2. Kit tools: `read`, `grep`, `glob`, `bash`, `write`, `edit`, `todo_create/update/get/list`, `hexview`, `structprobe`.
3. Workspace layer on Env ops (container/host adapters).
4. `coding_toolset()` factory + description style guide + golden-output tests.

Out (stay in cybergym-agent / zoo, patterns noted only): `submit_poc` (deliverable-submit pattern), `NOTE` (evidence notebook), `SWITCH` (stage intent), `gdb_debug`, `STATIC_*` six-pack, GREP's harness/production-source role ordering (becomes a pluggable scorer).

## 3. Framework contracts (land in qitos core/engine, small)

### 3.1 Soft validation — errors as recoverable results

Campaign evidence (code comments in every Cyborg tool): framework pre-validation is all-or-nothing and *discards structured recovery information* — agents then loop on opaque `Error: error`. The Cyborg tools deliberately no-op `validate_input` and emit recovery cards from `execute()`.

Contract change:
- `ToolSpec` gains `validation_mode: Literal["strict", "soft"] = "strict"`.
- Engine-level gating stays **hard** always: permission checks, schema *shape* (missing required key, wrong JSON type), security invariants.
- In `soft` mode, semantic parameter problems (bad path, unknown id, out-of-range values) are returned by the tool as **successful executions carrying a structured error result**, so the recovery card survives into model history.

```python
# qitos/kit/aci/cards.py
def error_card(tool: str, status: str, code: str, message: str,
               next_action: Optional[ToolCallSpec] = None,
               available: Optional[dict[str, list[str]]] = None) -> ToolResult
```

### 3.2 Card envelope — common result scaffolding

Every kit.aci tool result carries (verified pattern from Cyborg payloads):

```python
@dataclass
class CardEnvelope:                    # merged into the result dict by a helper
    schema_version: int = 1
    normalized_request: dict           # what the tool actually did (replay parity)
    completeness: dict                 # {complete: bool, truncated: bool, omitted_chars?: int}
    timing: dict                       # {duration_ms: float}
    effects: dict                      # {filesystem: {created: n, modified: n, deleted: n}}
    next_action: Optional[dict]        # {tool, args} — copy-pasteable continuation call
```

### 3.3 Summary-render dispatcher (kit side, rides on Task 01 `model_summary`)

```python
# qitos/kit/aci/rendering.py
_RENDERERS: dict[str, Callable[[dict], str]]
def register_renderer(tool_name: str) -> Callable          # decorator
def render_tool_output(tool_name: str, payload: dict) -> str   # fallback: generic error card
```

Structured dict is the canonical truth (trace/replay); the rendered Markdown card is `model_summary` (model/TUI). Rule from the campaign: **even error-status results go through the tool's own renderer** — generic error rendering discards stderr/recovery hints and caused opaque loops.

## 4. Tool specifications

All numbers below are the campaign's tuned values; they become **module constants + toolset-level overrides** (`coding_toolset(budgets=...)`), not hardcoded magic.

### 4.1 `read` (ref: `tools/filesystem.py`, `rendering/filesystem.py`)

- Params: `path` (required), `start_line` (int, default 1, min 1), `line_count` (int, default 200, min 1, max 1000).
- Output: header `[READ] {path} · lines {a}–{b} of {total}`; body ` {n:>6}│ {text}`; footer `Shown: N lines`, `More below: N`, `Next: READ(path=..., start_line=b+1, line_count=...)`.
- Line truncation: 320 chars/line, keep ⅔ head + ⅓ tail, explicit `… <N chars omitted> …` marker (never silent).
- Card budget: 24,000 source chars (lines priced at len+16); on breach set `card_budget_reached` and point `next_action` at continuation.
- Error cards: `not_found` → next_action is a `glob` fallback call; `unsupported` (non-UTF-8) → next_action points to `hexview`; `empty`; `error(code, retry)`.
- Metadata: `read_only`, `concurrency_safe=True`, permission `filesystem_read`.

### 4.2 `grep` (ref: `tools/search_service.py` — the most-optimized tool)

- Params (15): `pattern`*, `path="."`, `syntax=literal|regex` (default **literal**), `case_sensitive` (default **true**), `whole_word=false`, `multiline=false`, `include=[]`, `exclude=[]`, `mode=content|files|count`, `context_before=1`, `context_after=1` (0–20), `max_matches=80` (1–1000), `max_matches_per_file=12` (1–100), `order=relevance|path`, `include_hidden=false`, `respect_ignore=true`.
- Backend: ripgrep detected once at startup (attested path); `rg --no-config --json --line-number --column --color never`, `--fixed-strings` for literal, pattern after `--` (dash-prefixed patterns safe).
- Output: `[GREP:{status}] pattern=… · path=…`; `N matches in M files · showing K`; policy lines (hidden/ignored/binary); grouped matches with `>` prefix on match lines, context lines unprefixed; count mode `- path — N`; files mode `- path`.
- **Semantic page limit**: card budget 48 source lines → `page_limit = 48 // (1 + before + after)` matches per card, explicitly reported (`Card page cap: N (requested M)`); continuation raises `max_matches = min(1000, max(2×old, shown+1))`. No offset/cursor pagination — deliberate (x2.md: re-executed searches can't promise stable cursors).
- **Status machine**: `complete` / `no_match` (only when scan completed with zero warnings) / `partial` (timeout, omissions, backend unavailable) / `invalid_query` / `error`. `partial` and backend-failure cards must state: no absence was inferred ("Do not interpret this as absence.").
- Result ordering: pluggable `FileRoleScorer` (kit default: neutral `path` order; the campaign's harness/production/test/vendor/doc scoring ships as a documented example, not a default).
- Error codes: `SEARCH_BACKEND_UNAVAILABLE`, `SEARCH_TIMEOUT`, `PATH_PERMISSION_DENIED`/`PATH_NOT_FOUND` (lstat-classified), `INVALID_REGEX` (retry card simplifies the pattern to literal).
- Metadata: `read_only`, `concurrency_safe=True`.

### 4.3 `glob` (ref: `tools/navigation.py`)

- Params: `pattern`*, `path`, `exclude=[]`, `kind=file|directory|any`, `include_hidden=false`, `respect_ignore=true`, `limit=200` (1–1000).
- Output: `[GLOB:{status}]`; `N matching paths · showing M`; `Complete enumeration: yes/no`; grouped by parent dir with human sizes; `N paths omitted from this page.`
- Recovery: empty + `respect_ignore=true` → one controlled second enumeration with `respect_ignore=false`; if hits exist, warn `policy_excluded_matches` (explains unexpected emptiness without weakening policy); no-match → next_action broadens pattern to `**/*{stem}*`; truncated → raise limit `min(1000, max(2×old, shown+1))`.
- Errors: `INVALID_GLOB_PATTERN` with dedicated messages for absolute path / `~` / `..` (description also forbids them); retry auto-splits absolute patterns into path + basename.
- Metadata: `read_only`, `concurrency_safe=True`.

### 4.4 `bash` (ref: `tools/shell.py`)

- Params: `command`*, `timeout` (int seconds, default 300, range 1–3600 — framework generalization of the campaign's fixed 300; Claude-Code parity), `additionalProperties: false`.
- **Non-zero exit is success evidence** — `execution_status=completed`; description states it ("A non-zero exit is normal shell evidence, not a tool rejection"); next_action on failure: "correct the invoked program failure and rerun".
- Output budget: 16,000 model-visible chars; stderr floor 4,000 / cap 12,000 allocated proportionally; overflow strategy **head 25% + tail 75%** with explicit `--- omitted {N:,} chars ---`; counts (`stdout_chars/omitted_chars/…`) and full `raw_stdout/raw_stderr` stay in the structured payload/trace only; `completeness.complete = omitted == 0`; strategy line in card.
- Command echo: truncate >1000 chars (700 head + 200 tail). `cwd` displayed as `.` (no host path leakage).
- Env-alias injection: neutral `inject_env: dict[str,str]` config on the toolset (campaign injected its PoC dir; framework ships none by default).
- Timeout card: next_action suggests narrower/bounded command.
- Metadata: permission `command`+`filesystem_write`, `concurrency_safe=False`.

### 4.5 `write` (ref: `tools/filesystem.py`)

- Params: `path`*, `content`* ("Complete UTF-8 target content. Use edit for a local change and bash for binary output.").
- **Optimistic concurrency**: read-snapshots (sha256, LRU 200 paths); overwriting an existing file requires a prior `read` (`READ_REQUIRED` card whose next_action is the read call); snapshot mismatch → `STALE_FILE_VERSION` with observed/current hashes.
- Guards: `CONTENT_TOO_LARGE` (2,000,000 chars — "generate large output with bash"), `SENSITIVE_PATH` (configurable list; defaults `.env`, `credentials.json`, `id_rsa`, `id_ed25519`, `*secret*`), `PATH_OUTSIDE_WORKSPACE`, `BINARY_TEXT_UNSUPPORTED`.
- Receipts: created → size/lines/content-hash; overwritten → hash before/after + unified diff (12,000-char cap, `diff_truncated` flag; full `raw_diff` in trace only).
- Metadata: `filesystem_write`, `concurrency_safe=False`.

### 4.6 `edit` (ref: `tools/filesystem.py` — most-polished tool)

- Params: `path`*, `old_string`*, `new_string`*, `replace_all=false`.
- Contract: `old_string` must match exactly once unless `replace_all`; **never fuzzy-apply**.
- Conflict cards: `EDIT_NO_MATCH` → top-3 candidate locations via `difflib.SequenceMatcher` line similarity ≥ 0.45 with `{line, similarity, preview(240)}`; `EDIT_AMBIGUOUS_MATCH` → `match_count` + first 12 `match_lines` + next_action `read(path, start_line=first-10, line_count=40)`; plus `READ_REQUIRED` / `STALE_FILE_VERSION` / `EDIT_EMPTY_OLD_STRING` / `EDIT_PATH_NOT_FOUND` ("use write to create one").
- Idempotency: `old == new` → `[EDIT:unchanged]` success, 0 replacements.
- Receipt: `[EDIT:applied]` replacements, affected line range, hash before/after, diff (12k cap).
- Metadata: `filesystem_write`, `concurrency_safe=False`.

### 4.7 `todo_create` / `todo_update` / `todo_get` / `todo_list` (ref: `tools/todo.py` — "Claude-Code-style, agent-owned")

- `todo_create`: `subject`* (1–160), `description` (≤600), `active_form` (≤200), `position` (≥1, default append), `links` `{plan_id?, candidate_id?, evidence_refs? (≤24)}`. Description guardrail: organize work only — not evidence, not a success claim.
- `todo_update`: `todo_id`* + any of status (`pending|in_progress|completed|deleted`) / subject / description / active_form / links / `blocked_by` (≤500) / position. Error card lists `available_todo_ids` (≤12) + `allowed_fields`/`allowed_statuses`.
- `todo_get` / `todo_list`: read-only, `concurrency_safe=True`; list filters by status, excludes deleted by default; board rendering with revision counter.
- All four: soft validation (per-field structured errors from execute; valid siblings still apply).

### 4.8 `hexview` / `structprobe` (ref: `tools/navigation.py`)

- `hexview`: `path`*, `offset=0`, `length=256` (max 4096), `width ∈ {8,16,32}`; hexdump block `{offset:08x}  hex  |ascii|`; previous/next calls driven by `has_more_before/after`; `OFFSET_PAST_EOF` → success + `empty` + fallback next_action to last readable window. (Domain disclaimer text dropped.)
- `structprobe`: `path`*, `offset`*, `formats`* (≤64 items; `u8…i64`, `bytes:N`, `cstring:N`, N ≤ 4096), `endian`; per-field `{format, offset, size, value, hex}`; out-of-bounds fields flagged. Note: the campaign's trap parameter (`blocking_question`) is **not** ported.
- Both `read_only`, `concurrency_safe=True`; opt-in via `coding_toolset(binary=True)`.

## 5. Workspace layer (ref: `tools/workspace.py`)

- All fs/exec through **Env ops** (`env.fs` / `env.cmd`) per AGENTS.md tooling rules — no direct host access. Adapters: container env (existing `DockerEnv`) and a `LocalWorkspaceEnv` (explicit opt-in, workspace-rooted).
- Path resolution: backslash normalization, `~` → home (probed in-env), relative → workspace root, absolute kept; **variable-expansion whitelist** (default empty; campaign allowed exactly one alias — that pattern, not the name).
- Runtime-private masking: configurable internal suffixes (default `.agent/`, trace files) invisible to tools and excluded from grep — prevents the agent reading its own telemetry as evidence (and multi-MB card blowups).
- Symlinks: workspace-internal symlinks resolve; escapes allowed only behind explicit `allow_symlink_escape=False` default flag (absorption plan WS8).

## 6. Cross-cutting rules (style guide → `docs/guides/aci-style.mdx`)

1. **Truncation triple**: explicit `completeness` + counts; visible omission marker; always a copy-pasteable `next_action` continuation. Never silent truncation.
2. **Error-as-card**: machine code + human message + recovery call; missing ids list available ones (≤12); every observation tool states what its negative result does **not** prove.
3. **Descriptions**: imperative, three-part — capability → cross-tool navigation ("use the 1-based start_line from grep output") → semantic guardrail; negative constraints inline ("do not use absolute path here"); embedded example calls.
4. **Naming**: UPPERCASE verbs for observation/edit tools, lowercase for interactive services, PascalCase for views; stable schemas forever (prompt-cache).
5. **Dual view**: structured dict is truth; `model_summary` card is the model/TUI face; raw payloads live in trace only.
6. **Idempotency fingerprints**: repeated expensive calls (campaign: gdb, static queries) short-circuit with `reused=true, information_gain=false` — kit provides the fingerprint helper; aci tools use it where relevant.

## 7. Implementation steps

1. Contracts: `validation_mode` in ToolSpec + executor gating split; `cards.py` envelope; `rendering.py` dispatcher. Tests: soft-mode keeps recovery cards; hard security gating unchanged.
2. Workspace layer on Env ops + LocalWorkspaceEnv + masking + symlink flag.
3. Tools in dependency order: `read`/`glob`/`grep` (search service + attestation + page limits) → `bash` → `write`/`edit` (snapshots, conflicts) → `todo_*` → `hexview`/`structprobe`.
4. Golden-output tests: exact card fixtures per tool (normal, truncated, each error card).
5. `coding_toolset(bash=True, net=False, binary=False, budgets=None)` factory + registry assembly.
6. DX example: 50-line coding agent (with Task 02) in `examples/` + tutorial doc; CI-run.
7. Docs: `docs/guides/aci-tools.mdx`, style guide, budget table; zh mirrors.

## 8. Acceptance criteria

- [ ] All tools pass golden tests; every truncation path emits marker + counts + next_action.
- [ ] Soft-validation contract test: semantic errors return structured recovery cards in model history; permission/schema-shape violations remain hard failures.
- [ ] Concurrency metadata wired: observation tools parallel-safe through Task 01 adjudication; write/edit/bash serialized.
- [ ] Neutrality grep: no `poc|sink|vuln|cybergym|harness` vocabulary in `qitos/kit/aci/` (role scorer example lives in docs with neutral naming).
- [ ] 50-line example runs a real multi-step coding task (fixture repo) in CI.
- [ ] Budget overrides honored end-to-end (tighten budgets → cards shrink, continuations still correct).

## 9. Verification

```bash
pytest -q tests/kit/aci/
pytest -q   # full suite incl. executor soft-validation matrix
flake8 qitos/kit/aci qitos/core && mypy qitos/kit/aci qitos/core
```

## 10. Risks / open questions

- Q: does `bash` need `run_in_background`-style async? — defer; engine's ActionExecutionPolicy + timeout covers the campaign's needs. Revisit with real usage.
- Q: search backend attestation — on host workspaces, rg discovery is best-effort with explicit `SEARCH_BACKEND_UNAVAILABLE` semantics (never infer absence); document loudly.
- Risk: golden fixtures overconstrain iteration — version the fixtures (`schema_version`) and treat format changes as release-noted.
