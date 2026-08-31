# v4 four-lane execution playbook

Status: active dispatch specification
Updated: 2026-08-31
Nature: orchestration document, not a fifth architecture or a new public API
Source tasks: Tasks 02–05 and 08–13
Baseline: Task 01 complete; exact current integration status lives in
[`docs/progress.md`](../progress.md)

Current dispatch state: **S2 CLOSED; S3 entry gate satisfied; S3 runtime not
started.** The durable single-agent vertical and clean-process restore were
qualified, promoted, repeated in the primary checkout, pushed, and verified at
fixed pre-S3-closure source `3af0ee3b2c3b5b5575e4e07cc31ff7f652327ba7`;
the previous-wave worktrees were retired without force and their branch refs
remain. The historical S2 lane baseline `446a347...` and G3 integration source
`47cd4dc...` remain provenance only. The four S3 lanes must branch from the one
complete remote SHA published by this S3 dispatch closure, never from either
historical source. Trajectory v2 remains unfrozen, its candidate reader is not
the qita default, and no durable multi-agent scheduler exists yet.

---

## 1. Purpose

This document turns the active v4 tasks into four durable engineering lanes
that can be assigned to four coding agents or teams. It answers four practical
questions that the individual task designs intentionally do not:

1. which lane owns each semantic decision and file family;
2. which work can proceed concurrently and which must wait for a contract;
3. what exact artifact crosses a lane boundary;
4. what a coding agent must verify before handing work back.

The lanes are delivery boundaries, not new runtime layers. They must implement
the canonical contracts already described in Tasks 02–05 and 08–13. They may
not create `V2`, `Next`, parallel tool hierarchies, alternate trace formats, or
generic utility packages to avoid coordination.

Baseline validation note: while preparing this playbook, one full-suite run
failed `test_durability_manager_flush_full_queue_logs_warning`; two immediate
targeted reruns and the next full-suite run passed. The background worker can
drain a slot before `flush()` attempts its sentinel, so the test's mandatory-
warning assertion is race-sensitive. Lane A must record this as a test-trust
reproducer and Lane C must resolve it with Task 09D durability semantics. Do not
hide it with rerun-only CI or weaken the assertion without defining the intended
flush contract.

## 2. The four lanes

The program has two lane maps separated by G1. This avoids rewriting the
historical completion evidence while moving future capacity from audit work to
researcher-visible runtime capabilities.

### 2.1 G1 repair ownership (historical)

| Lane | Mission | Canonical tasks | Primary code ownership |
|---|---|---|---|
| A — Quality & Release Trust | Make every later change mechanically trustworthy and installable | Task 08; Task 10 admission evidence | CI, static ratchet, packaging, test infrastructure |
| B — Conversation, Providers & Context | Build the model I/O transaction kernel and context/artifact/history semantics | Tasks 02 and 04; Task 09B | conversation contracts, model codecs, request views, context/history/artifacts |
| C — Tools, Execution & Runtime Safety | Unify action outcomes, harden coding tools, and own resource/timeout/durability semantics | Task 03; Task 09A/C/D/F; Task 10C | tool/action runtime, toolsets, env/process/MCP, checkpoint durability, functional API |
| D — Trajectory, Observability & Convergence | Establish one lossless data plane and remove superseded architecture after proof | Task 05; Task 09E; Task 10A/B/E | trace/tracing/qita/render, benchmark migration, decision ledger |

Task 10 is not handed wholesale to Lane D. Cleanup follows semantic ownership:

- token/JSON/provider cleanup belongs to Lane B;
- result/Observation/process/retry/functional/MCP cleanup belongs to Lane C;
- JSONL/trace/qita/benchmark cleanup belongs to Lane D;
- Lane A owns packaging and gate cleanup;
- Lane D maintains the shared removal ledger and release order.

Sections 5–8 preserve the complete instructions used by the G1 branches. They
remain historical except where the integration ledger assigns a bounded repair
to the same semantic owner.

### 2.2 Post-G1 capability ownership

After the integration owner records G1 reclosure, new branches use this mapping:

| Lane | Mission | Canonical tasks | Primary code ownership |
|---|---|---|---|
| A — Session Runtime & Persistence | Make execution pauseable, process-independent, recoverable, and forkable | Task 12; Task 09A/C/D/F integration | Engine session lifecycle, checkpoint v2 session head/snapshot, restore/resolver integration |
| B — Conversation, Context & Continuation | Complete model transactions, steering, provider continuation, context, memory, and artifacts | Tasks 02 and 04; Task 09B | ExchangeLog/RequestView/codecs, context/history/memory/artifact contracts |
| C — Tools & Durable Multi-Agent | Harden ACI/tool outcomes and build handoff/delegate/fan-out/spawn on one work graph | Tasks 03 and 13; Task 09C integration | tool/action runtime, effects, work graph, local worker/join adapters |
| D — Trajectory, qita & Developer Experience | Make session/work lineage inspectable, replayable, compact, and easy to use | Task 05; Task 09E; owned Task 10 cleanup | trace/tracing/qita/render, exporters, examples and migration evidence |

Quality/release trust is a cross-lane gate after G1. The integration owner runs
the pinned ratchet, stable lint/type checks, architecture/public-surface tests,
full suite, packaging matrix where relevant, and documentation parity for every
accepted package. Quality findings return to the semantic lane that owns the
code; they do not recreate a permanent fifth implementation lane.

## 3. Global delivery waves

Four lanes do not mean four uncontrolled long-lived branches. Work is delivered
in small packages through one closure wave and four capability waves.

| Wave | Lane A | Lane B | Lane C | Lane D | Exit gate |
|---|---|---|---|---|---|
| G1-R — closed | retained trusted ratchet/CI evidence | canonical consumer green | C-P3 and C-P4 closed | exact scalar-safe C receipt refreshed | G1 passed; scalar-safe baseline promoted |
| S1 — contracts | 12A identity/lifecycle/snapshot ADR | 02B RequestView + 04A/04B contract handoffs | 03 recovery fields + 13A graph ADR | session/work lineage schema proposal only | G2: identities, ownership, snapshots, effects, and resolver contracts reviewed |
| S2 — single-agent vertical slice | 12B/C/D session head, safe pause, clean-process restore | 02C/D + context/artifact snapshot components | 03B/C effects and partial-batch recovery | observe the slice; no v2 freeze | G3: start -> parallel tools -> pause -> process exit -> restore -> finish, no duplicate committed effect |
| S3 — durable multi-agent | Session fork and ownership producer | context/continuation/authority transfer producer | one durable WorkGraph scheduler for handoff, delegate, spawn, fan-out/join | exact work-graph facts, read-only graph/timeline/DX | G4: partial child graph and ownership transfer survive process restart |
| S4 — DX and convergence | 12E compatibility/CLI | 02E/04C/D rollout | 03D/E + 13E adapters | 05 schema freeze/store/export/qita rollout | G5: public example, two independent consumers, release and migration gates green |

S1 branches start only from the exact final G1 accepted head reported by the
integration owner. G1 is now reclosed, but each lane still receives only its S1
contract package. Task 05 census, privacy qualification, and benchmark readiness
may continue; trajectory v2 freeze remains blocked through S3 contract handoff.

### 3.1 Gate G1 — trustworthy change surface

Required before large implementation PRs:

- Task 08A no-regression ratchet is active in CI;
- stable-surface flake8/mypy remain zero-debt;
- Lane B's exchange invariants and Lane C's outcome/lifecycle vocabulary have
  approved ADRs;
- Lane D's census identifies readers/writers and current public consumers;
- the integration owner has recorded high-conflict file leases.

Planning, fixtures, and failing regression tests may be prepared before G1.
Behavior implementation must not bypass G1 merely because another lane is slow.

### 3.2 Gate G2 — canonical contracts and ownership

Required before Task 04 and Task 05 integration:

- `ExchangeLog`/`RequestView` contracts and compatibility adapters pass;
- one lossless action outcome closes every declared tool slot;
- provider failures are typed and cannot become assistant text;
- thread timeout is explicitly non-cancelling and late results cannot commit;
- checkpoint callers can distinguish accepted, persisted, failed, and dropped;
- session/run/work-item/checkpoint identities and the immutable snapshot contract
  are reviewed;
- handoff/delegate/fan-out/spawn/fork semantics and single-owner generation rules
  are reviewed;
- no second scheduler, message stack, result envelope, checkpoint store, or
  lifecycle truth exists.

### 3.3 Gate G3 — single-agent process-independent continuity

Required before default flips or compatibility deletion:

- Task 04 artifacts are content-addressed and retrieval-tested;
- compaction preserves complete exchanges and parallel tool batches;
- a fresh process reconstructs the session from checkpoint v2 and resolver
  references without live objects from the original process;
- completed parallel slots, queued steering, budgets, context/artifacts, and
  trace cursor survive restore without duplicate committed effects;
- stale owners/late workers cannot advance the head;
- hook/trace/durability/effect uncertainty is visible in receipts.

G3 receipt (2026-08-31): the SQLite/offline-provider vertical passes twenty
independent clean parent/child process rounds with Event barriers, one
committed effect, one deterministic running barrier, and one eligible missing
slot. Exact-source receipts qualify all twelve S2 runtime facts. This gate does
not authorize a Trajectory schema freeze/default writer, qita migration, G4/S3
multi-agent scheduling, authoring sugar, or an external exactly-once claim.
Promotion receipt: G3 was subsequently fast-forwarded, revalidated in the
primary checkout, pushed with local/tracking/remote identity, and its temporary
worktree was retired. Statements elsewhere that these operational steps remain
pending are historical pre-promotion evidence.

### 3.4 Gate G4 — durable multi-agent continuity

Required before freezing trajectory v2 or rolling out graph-aware defaults:

- handoff commits one ownership transfer and cannot leave two active owners;
- delegate/spawn children have durable identity, budgets, capabilities,
  checkpoints, outcomes, and parent lineage;
- a partial fan-out/join restores without recreating completed children;
- parent cancellation, detachment, timeout, late-result, and unknown-outcome
  semantics are typed and tested;
- qita can navigate the graph without parsing run-name conventions.

The executable nineteen-item subprocess/process-loss matrix, producer manifests,
interface budget, and exact A -> B -> C -> D freeze order are fixed in
[`s3_durable_multi_agent_wave.md`](../internal/plans/s3_durable_multi_agent_wave.md).
Before all nineteen items pass, S3, durable multi-agent readiness, Trajectory
schema freeze, production distributed scheduling, and release readiness remain
unsupported claims.

### 3.5 Gate G5 — release convergence

Required before declaring v4 complete:

- base install and every supported extra pass clean-environment smoke tests;
- package build/twine checks pass with equivalent wheel contents;
- deprecated imports have documented replacements and removal versions;
- architecture allowlists and static baselines strictly shrink;
- v1 trace remains readable; no lossy exporter claims exact round-trip;
- trajectory v2 consumes Task 12/13 lineage and receipts rather than copying or
  inferring them;
- the public reference flow demonstrates pause/restart, fork, one child-work
  operation, and qita inspection without private Engine helpers;
- README, CHANGELOG, user docs, examples, and EN/zh counterparts match code.

## 4. Shared operating contract for every lane

Every coding agent receives the lane-specific instruction below plus this
shared contract.

### 4.1 Read before editing

1. root `AGENTS.md` and the nested `AGENTS.md` for every touched package;
2. `ARCHITECTURE.md`;
3. `docs/architecture/module-boundaries.md` and `change-guide.md`;
4. the lane's source Task documents listed below;
5. the active internal plan for the lane;
6. `git status --short` and the current diff, preserving all existing work.

Historical `docs/v4/06-*` and `07-*` files are forensic records and must not be
used as implementation instructions.

### 4.2 Branch and review unit

- Default branch name: `codex/v4-lane-<a|b|c|d>-<work-package>` unless the
  maintainer supplies another branch.
- One work package or one independently reviewable semantic change per PR.
- Do not combine mass formatting, file moves, behavior changes, and deprecation
  in one PR.
- A failing regression test may land with its fix in the same PR, but the commit
  or PR description must show the test failed before the fix.
- Do not amend, reset, discard, or reformat another lane's changes.

### 4.3 File-lease protocol

The following files are high-conflict integration points:

- `qitos/core/__init__.py` and root public exports;
- `qitos/engine/engine.py`, `_protocol.py`, and `async_engine.py`;
- `qitos/engine/run_state.py`, `interrupt.py`, and `_handoff_runtime.py`;
- `qitos/core/conversation.py`, `tool_result.py`, and `agent_spec.py`;
- `qitos/checkpoint/__init__.py` and `store.py`;
- `qitos/trace/schema.py` and `writer.py`;
- `qitos/qita/_cli_app.py`;
- `setup.py`, `pyproject.toml`, README, CHANGELOG, and architecture docs.

Before editing one, the agent must record in its plan:

```text
Lease owner:
File(s):
Semantic purpose:
Expected start/end package:
Other lanes blocked or adapter supplied:
```

A lease is not permission to absorb another lane's semantics. If two lanes need
the same file, the semantic owner lands the contract first; the other lane then
integrates against it in a separate PR.

### 4.4 Required PR evidence

Every handoff reports:

```text
Work package:
Contracts added/changed:
Compatibility behavior:
Files owned and shared files touched:
Tests added (what failure they reproduce):
Commands run and exact results:
Static-baseline delta:
Architecture allowlist delta:
Docs/README/CHANGELOG updated:
Open decision gates or risks:
Next lane artifact and location:
```

“Tests pass” without commands/counts is not evidence. A package is not complete
while its task status or acceptance checklist disagrees with the code.

Test paths named in Tasks 02–05 that do not exist at the Task 01 baseline are
required deliverables, not proof that a baseline test already exists. Until the
new file lands, run the closest existing subsystem tests and report both the
current path and the planned path explicitly.

### 4.5 Cross-lane handoff artifact

Cross-lane communication is by a versioned fixture/contract, not by prose alone.

G1 repair handoffs:

| Producer | Consumer | Required handoff |
|---|---|---|
| Lane A | B/C/D | ratchet command, baseline file, tool versions, clean-CI proof |
| Lane B | C | ordered call/result exchange fixture and model-facing projection boundary |
| Lane C | B | serialized canonical outcome fixture, artifact-ref field contract, timeout receipt |
| Lane B | D | exchange/request/codec/compaction fixtures and schema version |
| Lane C | D | action outcome/durability/hook-facing receipt fixtures |
| Lane D | A | v1/v2 install/test matrix and release-required jobs |
| Lane D | B/C | removal ledger naming canonical replacement and earliest removal version |

Post-G1 capability handoffs:

| Producer | Consumer | Required handoff |
|---|---|---|
| Lane A | B/C/D | identity/schema version, snapshot envelope, resolver protocol, lifecycle/durability receipts, clean-process fixture |
| Lane B | A | ExchangeLog/steering/continuation snapshot component with exact version and migration receipt |
| Lane B | C | immutable context/state/artifact transfer fixture and declared losses |
| Lane C | A | canonical effect/attempt/child outcome and quiescence receipts |
| Lane C | D | work graph, ownership transfer, join, cancellation, and outcome-unknown fixtures |
| Lane A | D | pause/resume/fork/restore lineage fixtures and trace completeness fields |
| Lane D | A/B/C | reader/export compatibility report, qita navigation evidence, and release migration matrix |

The integration owner—not a producer lane—attaches pinned ratchet/full-suite and
documentation evidence to every accepted package.

Any incompatible fixture change stops consumers until migration adapters and
updated fixtures are reviewed.

## 5. Lane A instruction — Quality & Release Trust

### 5.1 Mission

Make the repository's green signal trustworthy before the other lanes multiply
the change surface. This lane owns diagnostics, CI behavior, optional dependency
declarations, clean-install verification, and reusable test infrastructure. It
does not own runtime semantics exposed by those checks.

### 5.2 Required source documents

- `docs/v4/08-quality-gates-and-packaging.md` in full;
- `docs/engineering-quality-audit.md`, especially EQ1, EQ12, and EQ17;
- `docs/internal/plans/engineering_quality_program.md`;
- `.github/workflows/*.yml`, `.pre-commit-config.yaml`, `pyproject.toml`, and
  `setup.py`.

### 5.3 Owned scope

Primary ownership:

- `.github/workflows/` and required-check definitions;
- flake8/mypy ratchet configuration and committed diagnostic baseline;
- `pyproject.toml`, `setup.py`, extras metadata, and build smoke harness;
- generic test infrastructure and clean-environment scripts;
- CI/config validation tests;
- contributor-facing quality commands and packaging references.

This lane may add a failing subsystem integration test—such as the qita POST
route reproducer—but the semantic owner fixes the runtime code unless the fix is
strictly mechanical and explicitly leased.

Forbidden without owner handoff:

- changing provider, action, checkpoint, trace, or qita semantics;
- silencing a finding with a broader exclude/ignore;
- installing every optional dependency in the base package;
- moving/deleting public modules under the label “lint cleanup”.

### 5.4 Work packages

#### A1 — Task 08A: static no-regression ratchet

1. Create/update `docs/internal/plans/lane_a_quality_release.md`.
2. Record Python, flake8, mypy, and plugin versions.
3. Generate machine-readable full-package findings categorized as correctness,
   contract, hygiene, and vendored/generated.
4. Preserve current stable zero-error jobs.
5. Make every new active non-vendored finding fail CI.
6. Fix correctness findings only through small reproducer-first PRs assigned to
   the semantic lane.

Deliverable to all lanes: one documented local/CI ratchet command and immutable
baseline format.

#### A2 — Task 08E: CI repair

1. Replace invalid changed-file predicates.
2. Remove unused `CHANGED` logic and `|| true` from intended required checks.
3. remove/relocate stale in-repo zoo checks after confirming repository required
   check settings;
4. add workflow/config tests for missing paths, invalid predicates, and masked
   commands;
5. publish the blocking/non-blocking job ownership table.

#### A3 — Task 08C: dependency and packaging matrix

1. Map every non-stdlib import to base, a named extra, dev/build, or unsupported.
2. Resolve MCP HTTP, embeddings, cron, PDF/notebook, pgvector, browser, and `all`
   extra inconsistencies with Lanes C/D.
3. Add isolated base/extra install-import smoke jobs.
4. Require feature-specific errors naming the correct extra.
5. Migrate to PEP 621 only after wheel contents, entry points, package data, and
   extras compare equal.

#### A4 — Task 08D and 08B: test trust and baseline retirement

1. Reproduce and classify the known durability full-queue test race, then hand
   the semantic fix to Lane C; do not paper it over with automatic reruns.
2. Add route/provider/resource conformance tests requested by semantic lanes.
3. Retire findings package by package; the baseline may only shrink.
4. Move flat tests only when their production owner is already being changed.
5. Protect test selection against path moves and stale filters.
6. Publish before/after diagnostic counts for every package.

### 5.5 Acceptance criteria

- new flake8/mypy findings anywhere in active QitOS code fail CI;
- stable-surface zero-debt checks remain green;
- every supported extra installs and imports in isolation;
- no required job is masked by unconditional success;
- qita route and provider failure tests execute behavior, not symbol presence;
- packaging metadata has one source of truth and wheel parity proof;
- all other lanes can run the same ratchet locally.

### 5.6 Verification

```bash
pytest -q
pytest -q tests/test_architecture_boundaries.py
flake8 qitos/core qitos/engine qitos/models qitos/trace
mypy qitos/core qitos/engine qitos/models qitos/trace
# Then run the Task 08 full-package ratchet command.
python -m build
python -m twine check dist/*
```

### 5.7 Stop and escalate

Stop before broadening an exclusion, changing runtime behavior to satisfy a
checker, adding a heavy base dependency, removing a configured required check,
or migrating package metadata without wheel equivalence.

### 5.8 Completion handoff

Hand all lanes the ratchet command/baseline and Lane D the release job matrix.
For the historical G1 program, this quality lane remains the integration signal
owner through closure. After G1, that responsibility moves to the integration
owner as a cross-lane gate; post-G1 Lane A is Task 12.

## 6. Lane B instruction — Conversation, Providers & Context

### 6.1 Mission

Create one provider-neutral persistent conversation transaction, derive one
ephemeral request view per model call, preserve provider-native continuation,
then build explicit control context, artifact, and transaction-safe history
semantics on that foundation.

### 6.2 Required source documents

- `docs/v4/02-conversation-kernel.md` and
  `04-context-injection-and-memory.md` in full;
- Task 09B in `09-runtime-lifecycle-and-error-semantics.md`;
- engineering audit EQ4, EQ7, EQ9, EQ10, EQ15, and EQ16;
- `qitos/core/AGENTS.md` and `qitos/engine/AGENTS.md`.

### 6.3 Owned scope

Primary ownership:

- the new core conversation/exchange contracts and compatibility adapters;
- `qitos/models/` provider codecs and model failure mapping;
- `qitos/engine/_model_runtime.py`, request-view/context integration, and model
  portion of the composition root;
- `qitos/prompting.py`, `qitos/protocols.py`, and parser integration where the
  protocol contract requires it;
- `qitos/kit/history`, `kit/context`, relevant memory adapters;
- Task 04 artifact contract/filesystem implementation;
- checkpoint exchange serialization/version adapters, excluding durability.

Explicit split inside `qitos/checkpoint/`:

- Lane B owns exchange schema/version serialization in `store.py`,
  `checkpoint.py`, or `versioning.py` only through a recorded lease;
- Lane C owns `durability.py`, queue/flush semantics, and durability receipts;
- shared `__init__.py` changes land after both contracts and require a lease.

Forbidden without handoff:

- changing `ActionExecutor` scheduling/timeout or tool result semantics;
- writing trace-v2 or qita readers;
- encoding provider placement by mutating persistent history;
- adding a global context/provider registry;
- creating a giant cross-provider compiler module.

### 6.4 Work packages

#### B1 — Task 02A: exchange contracts and invariants

1. Write `docs/internal/plans/lane_b_conversation_context.md` and the API ADR.
2. Define ordered exchange items, multimodal content, raw/parsed call arguments,
   provider-scoped IDs, steering, opaque continuation, and batch closure.
3. Add `HistoryMessage` adapters; do not switch Engine yet.
4. Test duplicates, incomplete/interrupted batches, synthetic closure,
   serialization, and two independent consumers.
5. Produce the ordered exchange fixture for Lanes C/D.

#### B2 — Task 02B: request view and construction policy

1. Implement ephemeral request selection and deterministic budget reports.
2. Add queued steering only at completed exchange boundaries.
3. Define provider capabilities by transport/API mode.
4. Establish the model/conversation portion of one typed Engine construction
   specification; keep Engine the façade.
5. Do not overload exported `EngineConfig` snapshot with runtime services.

#### B3 — Task 02C + Task 09B: provider codecs and typed failures

1. Migrate OpenAI Chat, OpenAI Responses, Anthropic, then Gemini/GLM/local.
2. Decode successful responses into ordered exchange items.
3. Preserve signed/encrypted/native continuation opaquely.
4. Replace error strings with typed model failures carrying redacted metadata.
5. Make sync/stream failure categories equivalent and keep genuine `"Error:"`
   model text valid.
6. Reuse the OpenAI-compatible path for LM Studio/vLLM; retain native Ollama.

#### B4 — Task 02D/E: Engine/checkpoint migration and rollout

1. Switch `_model_runtime` to exchange/request/codec owners.
2. Version checkpoint conversation payloads with v1 adapters.
3. Emit request/codec reports for Lane D without raw secrets.
4. Enable defaults only after the provider conformance matrix passes.
5. Delete superseded assembly only after compatibility tests.

#### B5 — Task 04A–D: context, artifacts, and history

1. Add explicitly injected `ContextBlock` providers and placement reports.
2. Implement SHA-256 artifacts with atomic write, integrity verification,
   sensitivity, retention ownership, and no host-path leakage.
3. Consume Lane C's canonical tool outcome/artifact-ref fields.
4. Refactor compaction onto complete exchanges and preserve open batches,
   steering, continuation anchors, and artifact refs.
5. Externalize only when a model-facing projection and retrieval path exist.
6. Integrate existing memory APIs through adapters; do not replace them.
7. Deliver exchange/artifact/compaction fixtures and schema versions to Lane D.

#### B6 — owned Task 10 convergence

After G3 only:

- remove superseded token estimators and JSON-repair/provider helpers;
- move concrete SharedMemory stores/managers to kit after consumer inventory;
- remove old model/history assembly after migration evidence.

### 6.5 Acceptance criteria

- parallel-tool exchanges round-trip losslessly with ordered correlation;
- provider-native continuation survives or a typed unsupported-policy error is
  raised;
- provider failure cannot become assistant text;
- request views never rewrite persistent exchanges;
- steering appears exactly once at the next safe boundary;
- context digests reappear after compaction/stateless requests when required;
- artifacts verify identity and public refs contain no host path;
- compaction preserves complete exchanges and declares every loss;
- v1 history/checkpoint fixtures resume through adapters.

### 6.6 Verification

```bash
pytest -q tests/core/test_conversation.py
pytest -q tests/engine/test_request_view.py tests/engine/test_model_runtime_conversation.py
pytest -q tests/models/test_conversation_codecs.py
pytest -q tests/checkpoint
pytest -q tests/engine/test_context_blocks.py tests/test_compact_history.py
pytest -q tests/core/test_artifact_ref.py tests/kit/test_artifact_store.py
pytest -q
flake8 qitos/core qitos/engine qitos/models qitos/trace
mypy qitos/core qitos/engine qitos/models qitos/trace
# Also run Lane A's full-package ratchet.
```

Use actual evolved paths if tests are split, but preserve every invariant.

### 6.7 Stop and escalate

Stop before changing public HistoryMessage semantics, exposing encrypted/native
reasoning in public serialization, flipping a preset default, mutating history
for provider placement, adding one-provider fields to core, storing raw secrets
without policy, or externalizing content without retrieval.

### 6.8 Completion handoff

Lane C receives ordered exchange/projection fixtures at B1. Lane D receives
versioned exchange, outcome-reference, artifact, codec, and compaction fixtures
after B5. Lane B remains the semantic owner for future schema questions until
Task 05 default rollout is complete.

## 7. Lane C instruction — Tools, Execution & Runtime Safety

### 7.1 Mission

Define one lossless action/tool outcome, make the existing coding toolset
reliable, and establish honest timeout, cancellation, retry, durability, and
resource ownership across runtime integrations.

### 7.2 Required source documents

- `docs/v4/03-aci-toolset.md` in full;
- Task 09A/C/D/F in `09-runtime-lifecycle-and-error-semantics.md`;
- relevant Task 10C/D/F sections;
- engineering audit EQ3, EQ5, EQ8, EQ11, EQ13, EQ18;
- `qitos/core/AGENTS.md`, `engine/AGENTS.md`, and `kit/AGENTS.md`.

### 7.3 Owned scope

Primary ownership:

- `qitos/core/action.py`, `tool_result.py`, tool schema/registry contracts;
- `qitos/engine/_action_runtime.py`, `action_executor.py`, cancellation and
  action-related Engine integration;
- `qitos/kit/tool/`, `toolset/`, `permission/`, and relevant env/process code;
- `qitos/mcp/` QitOS bridge and lifecycle;
- `qitos/checkpoint/durability.py` and durability lifecycle tests;
- `qitos.func` disposition and executor lifecycle;
- Cron/PgVector optional-surface decision with Lane A packaging evidence.

Forbidden without handoff:

- changing provider codecs, exchange/request-view or history semantics;
- creating `qitos.kit.aci` or a second tool/result hierarchy;
- weakening schema, permission, or security gates;
- claiming thread timeout cancels work;
- changing trace schema or qita rendering contracts directly.

### 7.4 Work packages

#### C1 — Task 09A + Task 03A decisions

1. Write `docs/internal/plans/lane_c_tool_runtime.md`.
2. Inventory threads, pools, subprocesses, clients, schedulers, MCP sessions,
   streams, checkpoint workers, trace processors, and env resources.
3. Record creator, owner/borrower, close path, deadline, idempotency, and failure.
4. Define one lossless action outcome by evolving existing `ToolResult` and
   adapting `ActionResult`; do not add an envelope.
5. Define structural validation versus typed semantic tool failure.
6. Deliver serialized outcome, artifact-ref slot, timeout, and durability receipt
   fixtures to Lanes B/D.

#### C2 — Task 03B: read/search foundations

1. Reproduce known Read offset, Grep field, alias error/message, and path-policy
   defects with failing tests.
2. Extract owned workspace/path, pagination, budget, and backend-attestation
   services near the tool package—not into generic utils.
3. Refactor Read/Grep/Glob; retain explicit completeness, omissions, and
   continuation.
4. Keep host/container access behind Env capabilities.

#### C3 — Task 03C + Task 09C: mutation/execution and timeout

1. Reproduce Bash timeout and Edit replace-all defects.
2. Refactor Bash/Write/Edit using existing permission and read-before-write
   enforcement.
3. Report structured effects and optimistic-staleness conflicts.
4. Separate awaiting an awaitable, sync-to-async invocation, and deadline.
5. Mark thread timeout non-cancelling and prohibit late commit to closed steps.
6. Prevent retry overlap with a still-running attempt unless an explicit safe
   contract permits it.

#### C4 — Task 09D: checkpoint durability

1. Choose explicit ASYNC overflow policy with compatibility review.
2. Make accepted/queued/persisted/failed/dropped observable without falsely
   implying persistence.
3. retain worker errors and report incomplete flush/shutdown;
4. test full queue, slow/failing store, repeated shutdown, EXIT mode, and process
   exit assumptions;
5. replace the race-sensitive mandatory-warning test with deterministic contract
   tests for the chosen overflow/flush outcome; preserve a regression that fails
   against the old false-success behavior;
6. integrate with Lane B checkpoint serialization without editing its schema
   under an unrecorded lease.

#### C5 — Task 03D/E + Task 09F: presets and integrations

1. Make `coding_tools()` the canonical composition path and deprecate aliases.
2. Add optional task/binary tools only after measured first-wave stability.
3. Add lifecycle conformance for MCP, model clients (with Lane B), Docker/host
   env, cron, functional executors, and trace processors (with Lane D).
4. Run the version-pinned official MCP SDK parity spike; adopt/defer/reject with
   evidence before changing transports.
5. Demonstrate the compact coding-agent example on a non-campaign repository.

#### C6 — owned Task 10 convergence

After G3 only:

- complete-and-teach or deprecate `qitos.func`; remove inert knobs either way;
- admit, experimentalize, move, or remove Cron/PgVector/MCP optional surfaces;
- replace dual-state `Observation` with one typed representation and a tested
  compatibility projection, consuming Lane B's request/context adapters;
- remove duplicate result/process/retry mechanics after canonical owners land;
- remove compatibility aliases only after the announced window.

### 7.5 Acceptance criteria

- one canonical result retains status, identity, timing, effects, omissions,
  recovery, next action, model projection, and artifact refs;
- all declared parallel calls close exactly once in declaration order;
- partial search never becomes false no-match;
- Bash honors the configured deadline and reports continuing work honestly;
- late timed-out results cannot mutate closed state;
- read-before-write and stale-version enforcement are single-source;
- durability states and incomplete shutdown are observable;
- framework-owned resources close idempotently; borrowed resources remain open;
- no hard-coded safe-tool list, global registry, or campaign default lands.

### 7.6 Verification

```bash
pytest -q tests/core/test_tool_result.py tests/engine/test_tool_result_projection.py
pytest -q tests/kit/tool tests/test_predefined_atomic_tools.py
pytest -q tests/test_permission_pipeline.py tests/engine/test_concurrent_execution.py
pytest -q tests/checkpoint tests/mcp
pytest -q -k "timeout or cancel or retry or lifecycle or shutdown or durability"
pytest -q
flake8 qitos/core qitos/engine qitos/models qitos/trace
mypy qitos/core qitos/engine qitos/models qitos/trace
# Also run Lane A's full-package ratchet.
```

### 7.7 Stop and escalate

Stop before introducing a second result envelope/tool package, weakening
validation/permission, changing workspace escape policy, claiming hard thread
cancellation, changing `put()` return type without migration, closing borrowed
resources, adding process isolation to the base path, or replacing MCP without
the parity report.

### 7.8 Completion handoff

Lane B receives the result/artifact-ref contract before Task 04B. Lane D receives
outcome, durability, lifecycle, and hook-facing receipt fixtures before Task
05A readiness work. In the post-G1 map, Task 13/work-graph questions remain with
Lane C while session/checkpoint ownership moves to Lane A.

## 8. Lane D instruction — Trajectory, Observability & Convergence

### 8.1 Mission

Build one lossless and space-efficient trajectory source consumed by qita and
exporters, make observability failure visible, and coordinate the removal of
superseded architecture only after canonical replacements are proven.

### 8.2 Required source documents

- `docs/v4/05-trajectory-data-plane.md` in full;
- Task 09E and all of `10-consolidation-and-surface-reduction.md`;
- engineering audit EQ2, EQ6, EQ13, EQ16, EQ17, EQ18;
- `qitos/trace` v1 fixtures and qita/replay/export tests;
- architecture debt D1, D4, D10, D12, D18, D23–D31.

### 8.3 Owned scope

Primary ownership:

- `qitos/trace/`, `qitos/tracing/`, `qitos/qita/`, and `qitos/render/`;
- trajectory benchmarks, exporters, reader interfaces, and migration fixtures;
- hook/processor failure policy integration with Engine trace dispatch;
- Task 10 public-surface census/removal ledger;
- `qitos.benchmark` → `qitos.recipes.benchmarks` migration;
- qita/debug replay ownership and qita seam-based split;
- architecture-debt status and removal sequence.

Lane D does not own code merely because it appears in the removal ledger. It
assigns model/context cleanup to B, tool/lifecycle cleanup to C, and packaging
cleanup to A.

Forbidden without handoff:

- changing/deleting v1 on-disk format before parity and release review;
- adding a trace-only artifact store instead of Task 04's store;
- making SQLite/index state canonical;
- irreversible default redaction or exposing opaque provider reasoning;
- coupling core/engine to qita/render types;
- deleting public surfaces based only on repository grep.

### 8.4 Work packages

#### D1 — early census and inventory (historical W1)

1. Create/update `docs/internal/plans/lane_d_data_convergence.md`.
2. Execute Task 10A census of exports, commands, extras, registry entries,
   docs/examples, shims, known out-of-tree consumers, and deprecation state.
3. Inventory every event/artifact writer and reader across runtime, trace v1,
   tracing v2, renderer JSONL, qita, benchmark, evaluate, and hf.
4. Prepare representative campaign-derived and unrelated trajectory fixtures.
5. Prepare the storage-size benchmark without freezing v2 schema early.

#### D2 — Task 09E: observability failure semantics (historical W2)

1. Consume Lane C's lifecycle vocabulary.
2. Classify hooks/processors as critical or best effort.
3. Add visible failure counts/diagnostics and `fail_open`/`strict` policy without
   changing the compatible default silently.
4. Mark trace completeness and prevent recursive failure while reporting sink
   failure.
5. Hand required trace fields back to B/C; do not duplicate their receipts.

#### D3 — Task 05A/B: schema, store, and v1 bridge (superseded sequencing)

This historical package is no longer authorized to freeze v2 after only B/C.
Post-G1 it follows S3 and must also consume Task 12/13 lineage and receipts.

1. Freeze v2 schema using Lane B exchange/artifact, Lane C outcome/work-graph,
   and Lane A session/restore fixtures by reference/import.
2. Define privacy modes, integrity hashes, schema/writer versions, and
   correlation invariants.
3. Run the committed size benchmark before choosing compression/index features.
4. Implement atomic read/write and Task 04 ArtifactStore reuse.
5. Add v1 import and optional dual-write parity; keep v1 readers operational.

#### D4 — Task 05C/D/E: exporters, qita, rollout

1. Implement canonical exact exporter/re-import first.
2. Add OpenAI, then ms-swift/Hermes exporters with machine-readable loss reports.
3. Put a storage-reader interface behind qita board/replay/export.
4. Run qita behavior against v1 and v2 fixtures.
5. Add vocabulary-free diagnostic extension seams outside core.
6. Make v2 default only after parity, performance, privacy, migration docs, and
   release review.

#### D5 — Task 10B/E and shared convergence (historical W4)

1. Finish benchmark-to-recipes migration family by family with compatibility
   imports and an announced removal version.
2. Move/isolate large vendored ports with provenance/license/version metadata.
3. After Lane A route tests, split qita data/routing/render ownership without
   combining behavior changes and file moves.
4. Remove qita's deprecated debug dependency by assigning replay/fork to its
   canonical owner.
5. Coordinate evaluate/metric, leaderboard, hf, and other peripheral admission
   decisions using evidence.
6. Remove duplicate JSONL writers and compatibility planes only after G5.

### 8.5 Acceptance criteria

- v2 round-trip preserves every declared exchange, event, outcome, artifact,
  report, and correlation field;
- v1 fixtures remain readable by qita/replay;
- every external exporter is versioned and declares loss/privacy policy;
- raw/private and redacted/public views are separate and tested;
- missing/corrupt blobs and failed hooks yield typed visible diagnostics;
- size/compression claims come from both representative consumers;
- qita board/replay/export run against both storage versions;
- benchmark/recipes cycle is removed through a migration, not another copy;
- every removed surface has consumer evidence, replacement, warning release,
  removal release, and owning lane.

### 8.6 Verification

```bash
pytest -q tests/tracing tests/test_engine_result_traces.py
pytest -q tests/test_qita_cli.py
# After D3 creates them:
pytest -q tests/trace tests/qita
python scripts/benchmark_trajectory_store.py --fixture tests/fixtures/trajectories
pytest -q tests/test_public_surface.py tests/test_architecture_boundaries.py
pytest -q
flake8 qitos/core qitos/engine qitos/models qitos/trace
mypy qitos/core qitos/engine qitos/models qitos/trace
# Also run Lane A's full-package ratchet and release build matrix.
```

### 8.7 Stop and escalate

Stop before changing/deleting v1, default-destructing raw data, requiring zstd
without benchmark/fallback, claiming exact import for a lossy format, coupling
core to UI types, deleting public APIs without external evidence, or changing a
semantic owner's code instead of issuing a handoff request.

### 8.8 Completion handoff

Lane D publishes the canonical reader/writer/exporter matrix, removal ledger,
v1 compatibility evidence, storage benchmark, and release sequence. Lane A uses
that matrix for final required checks; B/C confirm their fixtures round-trip
before v2 becomes default.

## 9. Post-G1 capability-lane instructions

These instructions become active only after G1 reclosure is recorded in
`docs/progress.md`. Each lane starts with one work package and exact integration
baseline; no agent receives authorization for a whole Task at once.

### 9.1 Lane A — Session Runtime & Persistence

Mission: implement Task 12 on checkpoint v2 and the existing Engine loop.

First package: **12A identity/lifecycle/snapshot ADR**. It may edit plans,
versioned fixtures, and new contract-test scaffolds. It must census
`init_session`, `RunState`, checkpoint v1/v2, interrupt/resume, trace IDs, qita
fork, and resolver construction before proposing API names. No behavior or root
export changes land in 12A.

Later packages 12B–12E own atomic session-head generation, immutable snapshots,
safe pause, clean-process restore, fork, compatibility, and thin qita/CLI
adapters. They must consume B's ExchangeLog/context components and C's
effect/quiescence receipts. They may not create a parallel SessionStore, second
Engine, or serialize live runtime objects.

Acceptance focus: one fresh-process vertical slice; partial parallel completion;
exactly-once head commit; honest `outcome_unknown`; stale-owner/late-worker
rejection; resolver-only secrets/clients; isolated fork lineage.

### 9.2 Lane B — Conversation, Context & Continuation

Mission: finish Tasks 02/04 so every model/context fact required by a durable
session has one versioned component and migration path.

First package: **02B RequestView contract** after canonical B/C outcome
convergence. Produce RequestView/CodecReport fixtures, queued-steering semantics,
transport/API-mode capabilities, and the snapshot fields/reader that Lane A can
consume. Do not implement a conversation-owned session store.

Then deliver provider codecs/typed failures, context and ArtifactRef contracts,
compaction, and memory integration. For Lane C, provide immutable transfer
fixtures with selected/omitted/loss facts. Live providers, stores, secret values,
and host paths remain resolver-owned.

Acceptance focus: provider-neutral persistent facts; loss-explicit native
continuation; steering once at a safe boundary; fresh-process restoration;
non-destructive handoff/delegate context selection.

### 9.3 Lane C — Tools & Durable Multi-Agent

Mission: finish Task 03 and then implement Task 13 over Task 12 sessions.

First package: **03 recovery/effect contract handoff plus 13A ADR**. Complete
attempt/effect/idempotency/outcome-unknown/quiescence fields without introducing
a child-result wrapper. Census all existing handoff/delegate/fan-out nested
Engine and trace paths; freeze exact operation/ownership/join distinctions and
fixtures. No behavior changes land before Task 12A handoff is reviewed.

Then harden coding tools and implement generation-checked handoff, durable
delegate/spawn, fan-out/join recovery, capability/budget allocation, and adapters
for existing model-callable tools. The local executor is the reference; no
distributed service or role strategy enters the base framework.

Acceptance focus: one active owner; completed child/slot never recreated;
explicit parent cancellation/detachment/late-result behavior; direct API and
tools share semantics; no authority escalation.

### 9.4 Lane D — Trajectory, qita & Developer Experience

Mission: continue Task 05 readiness work, then make Task 12/13 continuity
observable and pleasant to use.

First package: **lineage proposal and fixture intake only**. Extend the D1
reader/writer census and readiness contract for distinct session/run/work-item/
checkpoint/agent IDs, pause/restore receipts, ownership transfer, child/join
state, and uncertainty. Do not freeze v2 or claim a benchmark while A/C producer
contracts are absent.

After S3, freeze v2 by consuming producer fixtures, add dual-read store/export
paths, qita session/work-graph timelines, and the compact public reference flow.
qita remains a client of runtime semantics and never infers graph edges from
run-ID suffixes.

Acceptance focus: exact lineage and declared losses; v1 compatibility; private
raw versus public redacted views; qita navigation/replay/fork/resume; measured
storage claims; EN/zh developer documentation.

## 10. Integration-owner instruction

One maintainer or planning agent acts as integration owner. It does not write a
fifth implementation. Its responsibilities are:

1. maintain the wave/gate dashboard below;
2. grant and close high-conflict file leases;
3. reject cross-lane semantic duplication;
4. sequence shared-file PRs and rebase consumers after owner contracts land;
5. run gate-level verification on the integrated branch;
6. update task evidence/status and record stop-gate decisions.

### 10.1 Current S3 dashboard template

| Lane | Current package | Branch/PR | Lease | Producer/consumer gate | Gate status |
|---|---|---|---|---|---|
| A | Session fork and ownership | created only from final S3 remote dispatch SHA | Session/checkpoint | publish exact commit/path/digest and C consumer contract | not started |
| B | context, continuation, and authority transfer | created only from final S3 remote dispatch SHA | request/context/codec | publish exact commit/path/digest and C consumer contract | not started |
| C | durable multi-agent scheduler | created only from final S3 remote dispatch SHA | WorkGraph/work runtime/tool adapters | consume real A/B types and fixtures; publish runtime facts to D | blocked on A/B producer freeze |
| D | work-graph observability and DX | created only from final S3 remote dispatch SHA | tracing/qita/evaluate/examples | consume real A/B/C facts; qualify two patterns and public example | blocked on A/B/C runtime facts |

### 10.1.1 Historical G2 contract-stage dashboard (superseded)

| Lane | Current package | Branch/PR | Lease | Tests | Handoff produced | Blocker/decision | Gate status |
|---|---|---|---|---|---|---|---|
| A | 12A session contracts | `d90b6a9` | session identity/snapshot | G2-R2 focused/full gates green | typed identities, extensible envelope, ArtifactRef foundation | runtime behavior absent | contract promoted; runtime not started |
| C | recovery/effects + 13A | `39ae60a` + `3f2bde6`/`0dad384` | outcome/work graph | strict grammar/privacy adversaries green | typed effects/work graph, distinct current/historical writer evidence | persistent scheduler absent | contracts promoted; runtime not started |
| B | 02B RequestView | `9241dd3` + `0efa496`/`0dad384` | conversation/context | capability/privacy adversaries green | sole conversation component, RequestView, declared capabilities | provider dispatch absent | contracts promoted; runtime not started |
| D | lineage intake | `49fa15b` | readiness/evidence | 0/21 absent; exact 21/21 | exact replay/current/historical producer bindings | runtime/Trajectory blockers retained | receipts promoted; Trajectory not ready |

### 10.2 Merge rule

Preferred order inside each gate:

1. contracts and fixtures;
2. compatibility adapters;
3. one implementation consumer;
4. second independent consumer;
5. Engine/integration switch;
6. docs/default change;
7. cleanup/deprecation only in a later PR.

If a consumer requires a contract change, return the change to the owning lane.
Do not patch the producer's private fields in the consumer PR.

### 10.3 Baseline promotion and worktree retirement

Every completed integration wave ends with a worktree-retirement receipt. After
the new baseline is promoted and recorded, the integration owner enumerates
only that wave's source and convergence worktrees, verifies each is registered,
clean, idle, and backed by retained refs, and removes it with
`git worktree remove <exact-path>` without `--force`. Run `git worktree prune`
and verify the paths and registry entries are gone. Preserve branches and commit
refs unless branch deletion is separately authorized.

Do not use recursive filesystem deletion, do not remove the primary integration
worktree, and do not treat a dirty, locked, active, or evidence-bearing
worktree as removable. Such a path blocks wave closure until reconciled.

## 11. Immediate dispatch order

The current instruction is the
[`S3 durable multi-agent wave`](../internal/plans/s3_durable_multi_agent_wave.md).
All four lanes receive the same complete remote SHA from the S3 dispatch
promotion receipt, use independent branches/worktrees, and freeze producers in
the order A -> B -> C -> D before G4 convergence. A owns Session fork/ownership,
B owns context/continuation/authority transfer, C consumes their real committed
types and fixtures to implement the durable scheduler, and D consumes real
A/B/C runtime facts for exact-source qualification and read-only DX. Copied
enums/fixtures or consumer simulations do not count as integration.

The following S2 dispatch instruction is **historical and superseded**. The
G2-R2 task defined by
[`docs/internal/plans/g2_r2_promotion_audit.md`](../internal/plans/g2_r2_promotion_audit.md)
has repaired the independently reproduced blockers, replayed the candidate,
promoted contract code through `c0f19cd...`, revalidated the primary tree, and
retired the explicit worktrees. Local, tracking, and remote refs were verified
at `446a347d1ac73636476ca2515a01da601b567c68` with `0/0` divergence. The
[`S2 runtime wave`](../internal/plans/s2_runtime_wave.md) is authorized to
create all four lanes from that exact fixed SHA.

The following R4/S1 dispatch history remains for provenance.

G1-R4 is the accepted repair endpoint. It closed C-P3 and C-P4, requalified B
without a runtime change, and bound D to C producer
`9a0c5ed5d6c1c959ff277d3888f54c927be3e183` through receipt refresh
`e41eb6ea68375b1064b30044e66ae58bcba67c67`. The independent integration-owner
audit confirmed four clean references at runtime baseline
`5ef8ab657f6452ae48c931beea79106e2cca34c6`, recomputed the committed digests,
passed a fresh scalar-role probe, and reran targeted, readiness, ratchet,
lint/type, tool-qualification, architecture/public-surface, and full-suite
gates. G1 is closed.

At that historical point, the maintainer could dispatch these four S1 packages
in parallel from the one final post-audit integration HEAD reported with the
dispatch:

1. **Lane A / 12A:** session identity, lifecycle, safe-boundary, snapshot, and
   resolver ADR plus versioned fixtures; no runtime behavior yet.
2. **Lane B / 02B:** RequestView/capability/steering contract and Task 12 snapshot
   handoff; no provider-default flip.
3. **Lane C / 03 recovery + 13A:** effect/quiescence fields and durable work-graph
   ADR/fixtures; no multi-agent behavior before Task 12A acceptance.
4. **Lane D / lineage intake:** extend readiness/census for Task 12/13 identities
   and receipts; no v2 freeze or performance claim.

These packages were deliberately contract-first and low-conflict. Their
versioned handoffs were later integrated and repaired by G2-R2. At that
historical point, S2 dispatch was authorized from
`446a347d1ac73636476ca2515a01da601b567c68`; that source is superseded for S3.

At that historical gate, concurrency did not transfer semantic ownership. Lane
A owned the identity vocabulary, and B/C/D could not qualify cross-lane
fixtures before consuming A's reviewed producer. That ownership rule remains;
the S2 acceptance order is A -> C -> B -> D as specified by the current S2
plan.

The detailed conditional S1 plan is
[`docs/internal/plans/s1_contract_wave.md`](../internal/plans/s1_contract_wave.md).

### G1-R4 scalar-safe acceptance

R3 remains recorded as accepted and subsequently reopened. R4 repaired the
forced-secret scalar leak in core commit
`89806df415f8a14da11db4427e4682f44e650c03`, requalified B without a runtime
change, accepted C producer
`9a0c5ed5d6c1c959ff277d3888f54c927be3e183`, and refreshed D in
`e41eb6ea68375b1064b30044e66ae58bcba67c67`. Content and omission-count roles
are deliberately distinct; canonical data is unchanged. Targeted, readiness,
ratchet, lint/type, and `1872 passed, 50 skipped` full-suite evidence closed G1.
This authorizes only contract-first S1 dispatch from the final R4 SHA; it does
not itself implement 02B, 03B-E, 05A, 12A, or 13A.

The 2026-08-30 independent audit found no new blocker and confirmed the promoted
runtime baseline. The dispatch source is the later post-audit integration HEAD
that contains the synchronized ledger and plans, not a lane-local R4 commit.

For direct dispatch, give each coding agent this entire playbook and state its
single lane/package (for example, `Lane A / 12A`). The agent must follow the
shared contract in Section 4 and only the ownership/instructions for its lane;
the other lane sections are dependency context, not authorization to edit them.

## 12. Program completion

The four-lane program is complete only when G5 passes and the source Tasks have
evidence-backed status updates. Finishing four branches, reducing raw LOC, or
making v2 the default is not by itself completion.

The final outcome must be one QitOS mainline with:

- one conversation/request model;
- one action/tool outcome;
- one explicit runtime lifecycle/error vocabulary;
- one context/artifact/history policy stack;
- one durable session identity/snapshot/restore path over checkpoint v2;
- one durable work graph for handoff, delegate, fan-out, spawn, fork, and join;
- one canonical trajectory source with compatible v1 reading;
- one trustworthy repository-wide quality signal;
- fewer public surfaces and compatibility paths than the starting point.
