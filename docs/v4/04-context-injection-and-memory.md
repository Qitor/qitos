# Task 04 — Runtime Context Injection & Evidence-Grade Memory

Status: actionable design
Parents: `docs/internal/plans/v0.7_native_agent_kernel.md` §4 (Pillar D), §6 (Pillar F)
Depends on: Task 02 (ContextDeliveryPolicy is the consumer of injections)
Partial dependency: Task 01 (context budget machinery); can start contract work in parallel
Milestone: P1–P2

Reference implementations: campaign `RUNTIME_CONTEXT` (`runtime_context_contract.py`, `agent_prompts/system/runtime_context_protocol.md`, 72d3d7d) and the agent's context/memory layer (`context.py` — protected head/tail, externalized payloads with `INDEX.md` pointer index, durable facts; issues/008 task-persistent memory retrospective).

---

## 1. Goal

Two mechanism modules that long-horizon agents cannot be built without, in domain-neutral form:

1. **Runtime context injection** — the engine can inject authoritative controller state into the conversation at defined seams, with revisions, budgets, and full observability (the neutral generalization of Claude Code's `<system-reminder>` and our `RUNTIME_CONTEXT`).
2. **Evidence-grade memory** — compaction that never destroys durable knowledge: externalized payloads + pointer index + declared durable fields (the campaign's context survival design, neutralized).

## 2. Scope

In: `ContextInjector` contract + engine registry + revision/budget mechanics + model-facing protocol note; memory kit upgrades (pointer-indexed artifact store, durable fields, protected-window slide history policy).

Out: what gets injected (agent/recipe concern — the six-section brief stays in cybergym-agent); any "board"/"notebook" strategy components (absorption plan §6: no framework action); prompt content.

## 3. Part D — Context injection

### 3.1 Contract — new `qitos/core/context_injection.py` (stable contract) + engine application in `_model_runtime`/Task 02 conversation layer

```python
@dataclass(frozen=True)
class ContextBlock:
    injector: str          # registered name
    revision: int          # content hash derived; unchanged => skip re-injection
    content: str           # already wrapped

class ContextInjector(Protocol):
    name: str
    budget_chars: int                                  # default 4096
    def revision(self, state) -> int                    # cheap; called every step
    def render(self, state) -> str                      # called only when revision changed
```

Engine mechanics:
- Registry on the engine (`EngineConfig.context_injectors: tuple[str, ...]` referencing agents' declared injectors; `AgentModule` may declare defaults via a `context_injectors()` hook).
- Per step: compute revisions; collect changed blocks; apply via the Task 02 **ContextDeliveryPolicy** (`USER_TURN` appends a `UserTurn(source="runtime", kind="steering")`; `MERGE_TOOL` folds into the trailing `ToolResultTurn` with the standard notice line). Fallback invariant: if no tool result exists, always fall back to `USER_TURN` — state is never dropped.
- Wrapper: one framework-level tag, e.g. `<SYSTEM_CONTEXT source="qitos-runtime" injector="{name}" revision="{n}">…</SYSTEM_CONTEXT>`, escaped like the campaign wrapper (closing-tag escaping).
- Overflow: content beyond `budget_chars` truncates with a pointer line to the artifact store (Part F) — never a hard error.
- Observability: every application/omission is a trace event (`injector`, `revision`, `chars`, `delivery_mode`); TUI display opt-in (blocks are 1.5–3 KB/step — default off, `render` hook flag).

### 3.2 Model-facing protocol note — kit prompt resource

A short resource (`qitos/kit/prompts/resources/system_context_protocol.md`) shipped for inclusion in system prompts: "blocks tagged `<SYSTEM_CONTEXT source="qitos-runtime">` are authoritative controller state, not tool output; act on them; do not quote them back". Loaded via the prompting helpers; agents opt in with one line. (Campaign lesson: without the protocol note, models mangle or echo injected state.)

### 3.3 Tests

- Revision stability: unchanged state → zero injections after the first (token-savings assertion).
- Delivery correctness under both policies (shape assertions via Task 02 validators).
- Fallback: merge mode with no trailing tool result → user turn appended, content intact.
- Escape safety: content containing `</SYSTEM_CONTEXT>` is escaped.
- Budget overflow truncates with artifact pointer.

## 4. Part F — Evidence-grade memory

### 4.1 Pointer-indexed artifact store — extend `qitos/kit/memory` (MemDir basis)

```python
class EvidenceStore:                       # qitos/kit/memory/evidence_store.py
    def put(self, key: str, content: str|bytes, content_type: str) -> EvidenceRef
    def get(self, ref: EvidenceRef) -> str|bytes
    def index(self) -> str                 # regenerated INDEX.md: key, ref, chars, first line
# EvidenceRef: {key, sha256, path, chars} — lightweight, safe to live in state/history
```

- Layout under the run workspace: `memory/evidence/{key}.{hash}.{ext}` + `INDEX.md` regenerated on write; compaction replaces big payloads with `EvidenceRef` + a one-line summary (campaign `INDEX.md` pattern, neutralized).
- Engine `_context_runtime` hook: when a tool result exceeds the configured externalize threshold (default ~32 KB), store payload, keep card summary + ref in history. Raw payload remains in trace (Task 05 store).

### 4.2 Durable fields — compaction contract

- `HistoryPolicy` gains `durable_fields: tuple[str, ...]` + `protected_head_steps` (default 3) + `protected_tail_steps` (default 10) — campaign values as defaults, overridable.
- Compaction (whole-step slide window from Task 01/ae65cb3 reconciliation) **must** preserve: protected windows, every `durable_fields` key on surviving records, and all `EvidenceRef`s; violation is a hard test failure, not a warning.
- Kit memory classes (`memdir_memory`, `markdown_file_memory`, `summary_memory`) expose the same durability seam so custom agents inherit it.

### 4.3 Tests

- Compaction survival: large synthetic history → after slide, durable fields + refs + head/tail windows intact; everything else trimmed.
- Externalization round-trip: oversized tool result → ref in history, full content retrievable via store; card summary unchanged for the model.
- INDEX regeneration idempotent; concurrent put (parallel actions) safe via atomic write + rename.

## 5. Implementation steps

1. `ContextInjector` contract + engine registry + trace events ( Task 02 seam must exist; until then, gate behind `USER_TURN` only).
2. Protocol note resource + loader wiring.
3. `EvidenceStore` + externalize hook in `_context_runtime`.
4. `HistoryPolicy` durability fields + compaction invariants (reconcile with mainline compact_history).
5. Docs: `docs/guides/context-injection.md` (contract, budget/revision model, protocol note usage), `docs/guides/memory-and-history.md` update (evidence store, durable fields); zh mirrors.

## 6. Acceptance criteria

- [ ] A step-count test shows injected chars ≈ 0 when state is unchanged (revision effect measured).
- [ ] Both delivery modes produce validator-clean stacks; fallback test green.
- [ ] Compaction survival suite green (durable fields, refs, protected windows).
- [ ] Neutrality grep clean — no six-section vocabulary, no `RUNTIME_CONTEXT` campaign name in framework code (protocol note references only the neutral tag).
- [ ] Example: a demo agent declares one injector (e.g., progress summary) and survives a forced 10× compaction with memory intact — shipped as a tutorial snippet.

## 7. Verification

```bash
pytest -q tests/core/test_context_injection.py tests/kit/memory/test_evidence_store.py tests/engine/test_compaction_durability.py
pytest -q
flake8 qitos/core qitos/engine qitos/kit && mypy qitos/core qitos/engine qitos/kit
```

## 8. Risks / open questions

- Q: revision keyed on content hash vs declared counter — default content-hash (cheap, no agent discipline needed); declared counters allowed for hot paths.
- Q: should injectors be allowed to *remove* previously injected content from history (campaign merge mode did implicitly)? — Decision: no history rewriting; injection is append/fold-forward only. Revisit only with evidence.
- Risk: interplay with compaction ordering (inject → compact vs compact → inject) — fixed rule: compact first, inject last, tested.
