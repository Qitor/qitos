# Changelog

This project keeps a human-curated changelog so users and contributors can see how QitOS evolves over time.

Format:
- `Added`: new features and capabilities
- `Changed`: behavior changes, refactors, and structural improvements
- `Fixed`: bug fixes
- `Deprecated`: old paths or APIs that will be removed later
- `Removed`: deleted features
- `Breaking`: upgrade notes for incompatible changes

How to update:
- Add high-signal entries under `Unreleased` while work is in progress
- Move `Unreleased` notes into a dated or versioned section when publishing a release
- Prefer user-facing changes, upgrade notes, and important engineering changes over low-level edit logs

## Unreleased

### Added

- Added the G4-L3 stable `qitos.agent` configuration path, a structural sandbox backend contract with inspect-backed Docker and explicit `unsafe_host` adapters, configured Trajectory/EventSink wiring, and deterministic single-/multi-process workflow qualification through the existing AgentModule, Engine, Session, WorkGraph, and qita surfaces.
- Added one strict `qitos.agent/v1` launch configuration and composition root for `ModelFactory`, toolsets, Env, Session/checkpoint, budgets, the existing `AgentModule`, and the existing `Engine`, exposed through `qit run --config` and the same Python API. Added typed credential references with hardened local-file, deterministic fake, and explicit environment-compatibility resolvers; canonical/source/policy digests remain secret-free.
- Added an executable G4-L2 Docker qualification harness and bounded multi-config live runner. Actual Docker inspect and in-container probes now verify identity, non-root/network/rootfs/capability/resource/tmpfs/mount policy, Env-only read/grep/write/test routes, repository integrity, targeted cleanup, and absence after cleanup. The live runner consumes only canonical configs, binds source/config/runner/evidence digests, records attempted requests, provider usage and latency, and keeps private evidence outside Git.
- Added the Task 14 sandbox architecture and primary-source research disposition. It promotes the research harness's task-exclusive, network-denied, non-root, narrowly mounted, pre-attested, fail-closed Docker boundary into a domain-neutral `SandboxSpec`/backend/Env plan, while adding private workspace staging, typed resources and egress, Session/WorkGraph ownership, redacted receipts, stronger local and managed adapters, and real escape/cleanup conformance gates. Existing `DockerEnv` remains native execution support and is not described as a qualified untrusted-code sandbox.
- Added the S3 durable multi-agent convergence candidate: real Session fork and owner fencing, strict ContextTransfer plans/receipts, reconstructable JSON-only WorkDescriptors, bounded scheduler admission/recovery, distinct handoff/delegate/spawn/fan-out/join semantics, direct/tool adapter parity, read-only qita graph/timeline inspection, two unrelated consumers, and a compact public-shape coding-agent example.
- Added deterministic G4 clean-process qualification with twenty independent SQLite graph create/crash/restore rounds plus twenty declaration/preparation-crash rounds. It proves declarations precede child preparation, committed forks are reused, completed work is not replayed, eligible queued work retains its operation identity, missing running work becomes `outcome_unknown`, joins reject duplicate/late outcomes, and ownership/cancellation/detachment/least-privilege facts survive restart.
- Added the executable S3 durable multi-agent wave at definition commit `52e050d9bc1ee0d4c6dcc78c90a5497c25722648`: four independent Session-fork, context/authority-transfer, durable-scheduler, and work-graph-observability lanes; exact producer commit/path/digest handoffs; A -> B -> C -> D -> G4 convergence; a frozen 41/27/24/28/22/101/34 interface budget; and a nineteen-item clean-process acceptance gate. This is a dispatch contract only—no fork runtime, scheduler, Trajectory default, qita mutation path, schema, fixture, or public API changed.
- Added the S2 G3 single-agent runtime vertical: the existing `AgentModule + Engine` kernel now owns one durable Session head, captures/restores the canonical ExchangeLog and partial tool batch, pauses only after executor quiescence, resumes eligible missing slots before the next model request, consumes queued steering once, restores provider continuation through resolver references, and publishes exact runtime facts through one EventSink seam. A deterministic offline SQLite parent/child test passes 20 independent rounds with zero duplicate committed effects.
- Added the qualified G2-R2 stable-contract promotion candidate: one typed runtime-identity vocabulary, an explicit extensible snapshot-component registry with B/C owner codecs, one canonical content-addressed `ArtifactRef`, typed WorkGraph/effect components, provider-declared capabilities, recursive diagnostic redaction, and an executable four-tier interface budget. These are contract and migration surfaces only; no session runtime, persistent scheduler, provider-default switch, Trajectory writer/store, qita migration, or release behavior is added.
- Added the v4 durable-session and native multi-agent architecture: Task 12 defines distinct session/run/work/checkpoint identities, one checkpoint-v2-backed snapshot truth, safe pause, fresh-process resume, fork, resolver references, and honest effect recovery; Task 13 defines a generation-checked durable work graph for handoff, delegate, fan-out, spawn, fork, steering, join, cancellation, budget/capability boundaries, and qita lineage.
- Added deterministic full-ratchet transition tests and a repository-intent CI ownership matrix covering required-candidate, advisory, stale, and release-only jobs without inferring external branch-protection state.
- Added C1-R ToolResult contract hardening: strict `qitos.tool_result/v1` persistence/parser entrypoints, an explicit flattened legacy adapter, versioned allowlisted model and ToolResult-only trace-safe views, typed non-JSON/contradictory-state failures, fail-closed repository-schema validation after interceptor/permission rewrites, and Lane B/D hardening fixtures. This does not change coding-tool behavior, checkpoint durability, MCP transport, trace v1, or qita.
- Added a continuously maintained v4 integration ledger (`docs/progress.md`) that distinguishes lane completion from integrated qualification and records exact source identities, review findings, contract blockers, merge order, and evidence gates.
- Added a pinned repository-wide flake8/mypy no-regression ratchet with a machine-readable classified baseline, stable source anchors, shrink-only updates, expiring maintainer exceptions for growth, semantic-lane correctness handoffs, and a dedicated CI job while preserving the stable-surface zero-error gates.
- Added the canonical `qitos.tool_result/v1` outcome contract by evolving `ToolResult` in place: lossless action/tool identity and terminal status, explicit model projection, stable failure/recovery fields, validated continuation, completeness/omissions, timing/attempts, effects/filesystem changes, artifact-reference slots, normalized request metadata, provenance, and honest continuing-worker timeout receipts. `ActionResult` and legacy dict/`model_summary` values now adapt into that contract, with versioned Lane B/D fixtures and an explicit runtime lifecycle ownership matrix.
- Added a non-bypassable structural tool-call gate for JSON object shape, required fields, declared primitive/container types, and closed-object schemas at both executor and standalone registry boundaries. Tool-discovered semantic problems remain typed post-dispatch outcomes; permission/security decisions remain hard gates.
- Added the module-level `qitos.core.conversation` ExchangeLog v2 contract (not yet a root export): ordered multimodal user/assistant/steering items, provider-scoped call identities, immediate partial-result persistence in real completion order, declaration-ordered derived queries, recovery-safe synthetic closure and queued steering, strict typed reads, and direct canonical ToolResult persistence/model/trace projections. The v3 producer fixture directly consumes Lane C evidence; Engine/provider/checkpoint main paths and Task 02B remain pending.
- Added the Lane D D1 exact-source data-plane census and public-surface/removal ledger, two privacy-gated representative trajectory source manifests, explicit Lane B/C fixture requests, and a schema-neutral trajectory-store benchmark readiness script. D1-R now enforces a strict manifest/publication schema, non-echoing portability diagnostics, exact per-contract qualification receipts, and D01–D16 source-symbol checks. It reports typed `TRAJECTORY_SCHEMA_NOT_READY` with zero measurements or claims; both fixtures and 05A remain unqualified, trajectory v2 remains unfrozen, and trace v1/qita behavior is unchanged.
- Added neutral per-client `default_headers` support to OpenAI and OpenAI-compatible synchronous/asynchronous transports, plus `DockerEnv(container_env=...)` and correct absolute container-path handling.
- Added an explicit, opt-in model-layer retry policy: `Model(retry=RetryPolicy(...))` and `build_model_for_preset(..., retry=...)` re-use the `qitos.core.tool.RetryPolicy` shape (max attempts, exponential backoff with cap and jitter, retryable-exception filter) around chat-completions and raw provider dispatch. Default stays `None` — no silent retries; engine recovery remains the safety net.
- Campaign absorption wave 1 (engine correctness, decontaminated): `ContextConfig.tool_call_loop_detection_enabled` (default on) so long-running agents can opt out of repeated-call blocking; runtime exception reporting — recovered exceptions now surface on stderr, as a `RECOVER` trace event, in `QITOS_ERROR_LOG`/`QITOS_TRACE_DIR/step_error.log`, and as `EngineResult` `last_error`; the `json_decision_multi_v1` protocol registration and preset-level `recommended_request_kwargs` plumbing (no preset flips its default yet — that decision is deferred to the conversation-kernel task).
- Added an explicit repository architecture harness: a recovered-architecture audit, a module boundary matrix with a target dependency graph and the enumerated list of current violations, a task-oriented change guide, and a P0/P1/P2 architecture-debt inventory under `docs/architecture/`.
- Added mechanical architecture guardrails (`tests/test_architecture_boundaries.py`): module-level dependency rules enforced as a ratchet with a shrinking legacy-violation allowlist, detection of new module-level import cycles, pinned exit plans for remaining legacy cycles, harness-document coverage checks, and link validation for `AGENTS.md`/`ARCHITECTURE.md`/architecture docs.
- Added layered agent working agreements: rewrote the root `AGENTS.md` as a compact map (architecture map, dependency rules, where-changes-belong navigation, verification commands) and added local `AGENTS.md` files for `qitos/`, `qitos/core/`, `qitos/engine/`, and `qitos/kit/` covering owns/does-not-own, allowed and forbidden dependencies, invariants, and common mistakes.
- Added the initial v4 kernel execution decomposition under `docs/v4/`: five dependency-ordered subtask designs covering a trustworthy campaign-absorption baseline, model I/O transactions, in-place coding-tool consolidation, explicit context/artifact/history contracts, and a lossless trajectory-v2 migration.
- Added the v4 goal-and-metric definition (`docs/v4/00-goal-metric.md`): five independent gates for same-agent mechanism removal and non-inferiority, a second consumer, provider conformance, replay/storage correctness, and repository quality.
- Added an evidence-backed engineering-quality audit and three coding-agent-ready v4 tasks: whole-package quality gates/packaging/test trust (Task 08), runtime lifecycle/error/durability semantics (Task 09), and post-contract consolidation/public-surface reduction (Task 10).
- Added the v4 four-lane execution playbook: complete coding-agent instructions for Quality & Release Trust, Conversation/Providers/Context, Tools/Execution/Runtime Safety, and Trajectory/Observability/Convergence, including file leases, versioned fixture handoffs, four merge waves, and evidence-based integration gates.
- Added the first coding-agent task batch (`docs/v4/06-batch-1-instructions.md`): four self-contained briefs — restore a green CI baseline (stale out-of-tree test removal), break the harness↔models cycle, remove the kit→benchmark edge, and land campaign engine-correctness commits (Batch E of the absorption plan) on a new integration branch.
- Added the second coding-agent task batch (`docs/v4/07-batch-2-instructions.md`): Batch M (reasoning-field preservation, description precedence, kwargs hygiene, decision-context normalization, explicit opt-in retry policy), Batch X (four-level concurrency adjudication, model-summary projection, state receipts, deterministic context budgets, slide-window knobs), Batch Y grafts (neutralized sticky routing, DockerEnv env mapping, TUI fix), and the carried-over test-isolation brief.
- Added the internal CyberGym campaign absorption plan (`docs/internal/plans/cybergym_campaign_absorption.md`), scoped to domain-neutral mechanisms only: branch-topology-driven merge sequencing for engine/model/tool/observability hardening, a primitive sufficiency audit keeping all campaign strategies out-of-tree, decontamination checklist, and milestones toward a fully domain-neutral package.
- Added the v0.7 native agent kernel design (`docs/internal/plans/v0.7_native_agent_kernel.md`) covering six first-class capabilities distilled from the campaign: a canonical conversation/message-stack orchestration layer with per-provider reasoning-preservation and context-delivery policies, native parallel tool calls, a domain-neutral ACI toolset, runtime context injection, a space-efficient content-addressed trajectory data plane with OpenAI/ShareGPT exporters, and curated generic kit modules.
- Added opt-in OpenAI Responses API support for synchronous, asynchronous, and typed streaming calls, including structured output-item preservation, `call_id` tool-result correlation, stateless tool-round replay, and privacy-safe trace summaries. Chat Completions remains the default.
- Added `AgentSpec.tool_name` so delegate workers can expose task-oriented model-facing tool names while keeping the registry agent name stable.

### Changed

- Recorded the fresh G4-L3 live round as a primary-profile failure with zero provider requests: nested immutable request options reached codec projection as a non-JSON `mappingproxy`, so GLM did not reach the required pause. DSV and Qwen were not started; offline gates, Docker attestation/cleanup, and privacy passed, while promotion, push, and worktree cleanup remain blocked.
- Made `qitos.agent/v1` reader-only compatibility; canonical writers and examples now emit `qitos.agent`. Config objects are deeply immutable, protocol resolution owns parser/codec selection, tool-use requirements are explicit request facts, and configuration digests bind launch, snapshots, restores, and trajectory provenance.
- Coding-capable declarative launches now default to a fail-closed Docker environment. Host execution must be named `unsafe_host`, emits an unisolated receipt, and rejects container-only safety claims. Provider credentials and requests remain host-side and are never injected into the tool container.
- Recorded the G4-L execution outcome as three `configuration_blocked:credential_missing` profiles with zero requests, tokens, latency, and retries. No model capability, sandbox, single-agent, multi-agent/restore, or live Trajectory scenario was qualified; S3 promotion, push, and worktree retirement remain blocked while deterministic G4 stays separately qualified.

- Requalified Lane D against immutable A/B/C source heads and the exact replayed or repaired producer bytes actually executed. Three external-credential live profiles are now registered locally and the per-response output ceiling is 10,240 tokens, but executable live capability/trajectory/agent receipts remain pending. The candidate Trajectory plane remains unfrozen and off and qita's default remains frozen trace compatibility; therefore no baseline promotion, push, release claim, or worktree cleanup is authorized.
- Closed S2 promotion truth and opened the S3 entry gate: the qualified durable single-agent/clean-process vertical was fast-forwarded, repeated in the primary checkout, pushed, and verified with local/tracking/remote identity at `3af0ee3b2c3b5b5575e4e07cc31ff7f652327ba7`; previous-wave worktrees were retired without force while refs remained. The old `446a347...` S2 and `47cd4dc...` G3 sources are historical only. S3 runtime is not implemented, Trajectory v2 is unfrozen, and qita's candidate reader remains non-default.
- Split S2 runtime qualification from Trajectory schema/publication qualification: exact committed A/B/C receipts qualify all twelve runtime facts, while the candidate schema remains unfrozen, its writer remains off by default, qita remains on the frozen trace-v1 compatibility plane, and publication/performance claims remain blocked. The current interface budget keeps 41 root exports and classifies 101 aggregate exports; the 34th `Engine.__init__` parameter (`runtime`) is a reviewed migration bridge, not a second permanent composition root.
- Closed G2-R2 documentation truth and authorized S2 dispatch: `c0f19cd...` remains the promoted contract code head, while `446a347d1ac73636476ca2515a01da601b567c68` is the fixed, independently qualified S2 dispatch baseline. All four S2 lanes must branch from that SHA; later ledger-only successors do not redefine it. The 11 remaining readiness blockers belong to S2 runtime/Trajectory work rather than G2 contract repair, and no S2 runtime behavior is included.
- Promoted the independently repaired G2 contract code head at `c0f19cd...` by fast-forward after matching the fixed dispatch SHA, repeated the complete gate matrix in the primary checkout, and retired 17 clean superseded worktrees without force while preserving all branch refs.
- Requalified Lane D readiness as 21 independent receipts: 17 G2 contract-bundle requirements, two explicitly historical G1 compatibility records, and two current ToolResult/ExchangeLog writer records. Each binds exact commit, current/committed bytes, paths, digests, authority, evidence role, source/replay lineage, and an independent consumer; runtime, writer/store, qita, publication, and measurement blockers remain separate.
- Made the G2 interface budget semantic rather than nominal: 124 deliberate module exports are distinct from three visible implementation-private diagnostic helpers, while the exact 41-name root export set and 33-parameter `Engine.__init__` remain unchanged. Fixture edits alone no longer authorize surface growth.
- Replayed the G2 candidate's real contract convergence direction onto the audit-bearing integration baseline: one current `ToolResult` writer plus a bounded historical reader, A-owned typed identities consumed by WorkGraph, one conversation snapshot owner, one `ArtifactRef`, and provider-declared capabilities without provider-name inference. G2-R2 repaired the receipt semantics; runtime and Trajectory readiness remain typed blocked as explicit S2 work after G2 closure.
- Independently reviewed the repository-green G2 candidate and kept it unpromoted: current implementation direction is sound and `2010 passed, 50 skipped`, the 399-finding ratchet, lint/type, focused contracts, and readiness modes pass, but mixed historical/current ToolResult fields, malformed ProviderCapabilities types, incomplete path/key/JWT redaction, historical receipts presented as current foundations, private names in `__all__`, divergent integration ancestry, and missing worktree retirement require one bounded G2-R2 before S2. The follow-up also retires roughly 10.13 GiB of clean superseded worktrees after the repaired baseline is promoted.
- Reviewed the four S1 producer candidates for stable sessions, provider-neutral requests, effect/work ownership, and trajectory lineage. A conflict-free isolated A → C → B → D tree passes 173 focused tests, `1999 passed, 50 skipped`, the 399-finding ratchet, and stable lint/type, but remains deliberately unmerged: typed identity consumption, snapshot-component ownership, one ArtifactRef, honest ToolResult schema migration, provider/WorkGraph diagnostic redaction, interface curation, and exact S1 receipts must converge in one G2 integration task before runtime work starts. Every future wave closure now also requires clean, non-forced retirement of its source and convergence worktrees after baseline promotion, while preserving branch and commit references.
- Independently re-audited the promoted G1-R4 baseline: four clean references, exact C fixture/evidence digests and D producer receipt, a fresh forced-secret scalar-role matrix, 168 combined tests, the 399-finding ratchet, stable lint/type, tool qualification, all readiness modes, and the `1872 passed, 50 skipped` full suite passed. The synchronized S1 plan now authorizes exactly four contract-first lanes from one final post-audit integration HEAD; no S1 branch or runtime behavior was created by the audit.
- Accepted the A → C → B → D G1 final convergence after an independent audit reopened R3 and G1-R4 closed C-P4: forced-secret integer, float, boolean, null, and nested scalar content is redacted under a private content role, trace-safe omitted counts retain their validated integer type under a separate role, canonical data remains lossless, B requalified without a runtime change, and D binds the exact new C producer while rejecting the R3 receipt. Python 3.12.7 ratchet, lint/type, targeted, readiness, adversarial, and `1872 passed, 50 skipped` full-suite gates pass. S1 may start only from the final R4 baseline; no Task 02B, 03B–E, 05A, 12/13 runtime, provider-default, trajectory-v2, qita, or packaging behavior was started.
- Remapped post-G1 four-lane execution from a permanent quality implementation lane to four capability lanes—Session/Persistence, Conversation/Context, Tools/Multi-Agent, and Trajectory/qita/DX—while retaining the repository ratchet, tests, packaging, and documentation parity as mandatory cross-lane integration gates. Trajectory v2 schema freeze now waits for durable session and work-graph lineage.
- Extended the v4 integration ledger with the convergence-wave code audit: exact A2/B2/C2/D2 identities, integration-owner reruns, executable boundary probes, newly discovered CI/JSON/aliasing/projection/receipt blockers, and the revised final-G1 repair order.
- Replaced the original commit-oriented v4 drafts with dependency-ordered coding-agent specifications: a closed capability-based baseline; model I/O, tool, context/artifact, and lossless trajectory contracts; plus quality gates, lifecycle/error semantics, and consolidation. The old batch briefs and internal campaign workstream plan are explicitly archived.
- Made `qitos.kit.toolset` security-research compatibility exports lazy so importing `qitos.kit` remains a safe default while explicit legacy imports continue to work.
- `qitos.kit` no longer depends on the deprecated `qitos.benchmark` layer (D6/V5): the CyBench evaluator, guided/unguided metrics, and the `submit_answer` tool moved from `qitos.kit.{evaluate,metric,tool}` into `qitos.recipes.benchmarks.cybench` — import them from the recipe module now. The `{benchmark, kit, recipes}` import cycle shrank to `{benchmark, recipes}`.
- Removed all 13 module-level root-package self-imports (D8/V6): subpackage modules under `kit`, `recipes`, and `demo` now import `qitos.core.*` / `qitos.engine.*` directly instead of going through the root `qitos` `__init__`; the corresponding legacy allowlist entries are gone from the boundary test.
- Broke the `harness <-> models` module-level import cycle (D5/V1): `OpenAICompatibleAdapter`, `adapter_for_kind`, `resolve_context_window`, and `build_model_for_preset` moved from `qitos/harness/_adapters.py` to `qitos/models/harness_adapter.py` and are re-exported from `qitos.models`. `qitos.harness` now depends only on `protocols` and keeps presets plus `build_harness_policy`; import `build_model_for_preset` from `qitos.models` (or `qitos.models.harness_adapter`) instead of `qitos.harness`. `HarnessPolicy.adapter` is now optional and `HarnessPolicy.adapter_kind` falls back to the family preset.
- Raised the optional OpenAI SDK floor to `openai>=1.66.0` and taught compact history to preserve active Responses function-call rounds atomically.
- Strengthened the CyberGym PoC agent's task bootstrap with lightweight structured task-spec extraction and more relevant repo evidence ranking.
- Clarified candidate provenance and lightweight failure taxonomy handling in the CyberGym agent without changing its single-agent runtime architecture.

### Fixed

- Fixed declarative launches that accepted a protocol while always selecting a ReAct text parser, retained ineffective trajectory settings, allowed malformed native responses to appear successful, or leaked a prepared sandbox when later composition failed. Cleanup failure, capability loss, parser mismatch, policy violation, digest mismatch, and lossy projection now remain typed failures.
- Fixed G4-L2 workflow qualification to run a newly created single Session to a safe pause before clean-process restore, continue with a proven tool-capable profile when another profile reports typed capability loss, preserve sanitized typed restore-worker failures without copying child stderr, and project one decrementing profile request budget across fresh worker processes. Live evidence remains blocked: no required coding workflow completed and one provider exceeded its request budget during diagnosis.
- Removed the tracing-local `ArtifactRef` implementation and made trajectory/store/reader/exporter/sink surfaces use `qitos.core.artifact.ArtifactRef`; repository AST and identity gates now reject any second framework implementation. Session-head CAS also rejects stale/superseded terminal writers, and recovery refuses committed-effect or outcome-unknown replay.
- Repaired the five independently audited G2-R2 contract gaps: historical `qitos.tool_result/v1` bytes now reject every current-only or unknown field; ProviderCapabilities constructor/adapter/reader paths enforce closed vocabularies and exact booleans/budgets with typed errors; ProviderFailure, WorkGraph, ToolResult projections, readiness, and ArtifactRef reject or redact arbitrary host paths and common credential/token/JWT/PEM forms without echo; current and historical writer evidence is distinct; and internal diagnostic helpers are absent from `__all__`.
- Closed D-R1 by deriving contract readiness only from reviewed receipts bound to exact B/C producer commits, committed fixture and producer-evidence paths and hashes, and an approved authority. Forged digest/path/commit/version/authority fields are typed blockers; each receipt clears only its own contract, while trajectory v2, publication, measurements, and claims remain blocked.
- Closed the G1 ToolResult JSON-admission, nested-ownership, C-P3 key-projection, and C-P4 forced-secret scalar gaps: tool calls reject recursive non-JSON values and non-finite numbers before interceptors, permissions, or execution; canonical/legacy construction and serialization detach nested caller-owned values; sensitive model/trace mapping keys use deterministic collision-safe placeholders; and role-aware projection redacts every forced-secret JSON scalar while preserving validated omitted counts. Aggregate/per-field loss facts remain conserved.
- Fixed the contribution tool-schema gate so workflow and repository tests execute one checked-in qualification entrypoint over real constructible class tools and the actual `ToolRegistry`, with a controlled malformed-spec failure instead of a broken inline `ToolSpec` import.
- Repaired contribution CI trust: removed unsupported `pull_request.changed_files` array predicates, unused changed-count logic, masked pytest commands, and missing zoo test paths; retained the zoo workflow as an explicitly stale advisory inventory pending external required-check evidence.
- Closed the campaign-absorption quality baseline: the stable core/engine/models/trace surface is flake8- and mypy-clean; the private Engine protocol matches its runtime helpers; cancellation checkpoints use the correct arguments; synchronous Engine MCP lifecycle and tool discovery resolve their async operations; and Action objects render correctly in the TUI.
- Multi-action steps no longer abort sibling actions when one is blocked: gate- and loop-blocked actions are collected pre-flight, executable siblings still run, and results merge back by original action index with `call_{step}_{i}` native tool-call ids; the terminal UI renders parallel actions/observations with per-index dedup and preserves recovery cards on failed observations instead of hiding them behind the error title.
- Tool history keeps string recovery cards verbatim instead of wrapping them in an opaque JSON error envelope, keeping provider history and the TUI aligned on the same actionable text.
- Concurrent benchmark recipe runs can no longer execute the same job twice: `execute_example_jobs` tracks in-flight job keys under a lock.
- Fixed immediate cancellation finalization so the END event, canonical State, `TaskResult`/`EngineResult`, and trace manifest all report `cancelled_immediate`; cancelled manifests now use the existing terminal `stopped` status instead of `completed`.
- Fixed native text fallback so malformed structured action output enters parser recovery instead of being misreported as a successful final answer, while ordinary natural-language conclusions still use `native_text_final`.
- Fixed message-window trimming so native tool results whose declaring assistant call has been evicted are removed before provider dispatch, while complete tool chains and existing interrupted-call recovery remain unchanged.
- Fixed direct `Engine(agent=...)` construction so models created with `build_model_for_preset(...)` retain their declared protocol and native API tool-schema delivery, including provider aliases such as Kimi K3 that cannot be inferred from the model name alone.
- Fixed empty model responses with neither usable text nor tool calls being misclassified as parser `wait` decisions. The Engine now records them as `model_error`, retries once through bounded recovery, and stops with `unrecoverable_error` if the empty response repeats while preserving response diagnostics in traces.
- Fixed native response text extraction so OpenAI-compatible messages with null content no longer become repr-string final answers.
- Fixed OpenAI-compatible forced tool-call requests so conflicting thinking options are disabled, and repaired JSON/tool-call parsing for bare control characters inside string values.
- Fixed JSON-like object extraction so apostrophes in surrounding natural-language text no longer hide valid JSON payloads.
- Fixed `DelegateTool` context delivery so the optional tool-call `context` object is passed into the child agent via `Engine.run(..., context=...)`.
- Fixed OpenAI-compatible tool schema generation for postponed or string annotations so CyberGym tools no longer emit invalid JSON Schema types.
- Fixed CyberGym batch trace/result/render redaction so API keys and auth token markers are scrubbed before persisted artifacts are written.
- Fixed CyberGym PoC generation runs so benchmark-local Bash commands can run without interactive command review while the default coding toolset review guard remains intact.
- Fixed tool registration with name overrides so CyberGym uppercase aliases do not mutate source tool specs shared with ordinary coding toolsets.

### Removed

- Removed test suites whose subject lives out of tree, restoring a green `pytest -q` baseline (0 failed / 0 collection errors): `qitos_zoo.qitos_auditor` (completeness, knowledge, package, multi-agent), `qitos_zoo.qitos_coder`/zoo package structure (package, terminal mode, zoo eval configs), `qitos_zoo.qitos_cyber.pentagi` (function-tool migration, handoff targets, critic migration), and the vendored `qitos.benchmark.cybergym.agent` tests (context retention, task spec, parallel-tools prompt, evidence selector, context snip, candidate failure records, agent PoC profile). Mixed files were split with their in-tree coverage kept (streaming/hooks, compact history, harness presets, examples smoke, cybergym recipe; the in-tree `CodingToolSet` review tests now live in `tests/test_coding_toolset_review.py`). Also pruned stale tests for behavior no longer present in the source: the OpenAI-compatible retry/120s-timeout pair and the executor `candidate_ready_for_submit` guard tests.

## v0.6.0 (2026-05-28)

### Added

- **WebBrowserEnv**: Playwright-backed web browser environment (`qitos.kit.env.web`) with `MockBrowserProvider` and `PlaywrightBrowserProvider`, extending desktop GUI actions with `navigate`, `go_back`, `go_forward`, `switch_tab`, `close_tab`. Optional dep: `pip install qitos[web]`
- **qita Screenshot Strip**: Interactive horizontal thumbnail strip at the top of run detail pages, showing one thumbnail per step with screenshot. Click thumbnail to scroll to step card. Grounding failure and critic retry indicators.
- **qita Action Overlay**: Click/action markers on screenshots with coordinate labels. Red markers for grounding failures, green for success. Navigate actions shown with URL badge.
- **qita Observation Pack Viewer**: Expandable per-step panel showing DOM, accessibility tree, OCR spans, UI candidates, and grounding metadata. Toggle with "observation pack" button.
- **qita Branch Comparison**: `/compare-branches/{run_id}/{step_id}` route for side-by-side branch candidate comparison with grounding failure banner.
- **MultimodalCapabilityProfile**: Model-aware observation adaptation in `qitos.models.profile_registry`. Vision models receive screenshots; text-only models receive DOM + OCR fallback.
- **AgentSpec.model_override / tools_override**: Override the sub-agent's model and tool registry for delegation.
- **AgentSpec.__post_init__ validation**: Empty name raises ValueError.
- **AgentRegistry.get_handoff_tools()**: Returns `HandoffTool` instances for Decision-mode handoff.
- **DelegateTool nested delegation fix**: `_build_sub_engine()` now passes `agent_registry` enabling depth-2+ delegation.
- **DelegateEventInterceptor**: First-class `DELEGATE_START`/`DELEGATE_END` events in `EngineResult.events` when `agent_registry` is provided.
- **Sub-trace writer depth-aware run_id**: `f"{parent_run_id}__delegate_{agent_name}_depth{depth}"` prevents collisions.
- **ReviewerAgent** in delegate example demonstrating multi-delegation with `ContextStrategy.SUMMARY`.
- **v0.7 handoff scope document**: Documents what is in v0.6 vs v0.7 scope for handoff/Decision mode.

### Changed

- `DelegateTool._build_sub_engine()`: now passes `agent_registry`, applies `model_override`/`tools_override` from `AgentSpec`.
- `DelegateTool._build_sub_trace_writer()`: includes `current_depth` in sub-run-id for uniqueness.
- `qita renderActionOverlay()`: now shows grounding failure banners inline.
- Engine auto-registers `DelegateEventInterceptor` when `agent_registry` is provided.

## v0.5.0 (2026-05-27)

### Added

- Added `CORE_BOUNDARY.md`, a core governance audit, a dependency audit, and a staged `qitos-zoo` migration manifest for product-grade agents.
- Added regression tests for public API and examples governance.
- Added `FamilyPreset.override()` for programmatic preset customization and `recommended_models`, `recommended_protocol`, `recommended_parser` advisory fields.
- Added `MaxTokensCriteria` stop criterion so engines can halt when accumulated output tokens exceed a budget.
- Added `CriticTrace` and `HandoffTrace` export APIs for programmatic access to critic decisions and multi-agent handoff data.
- Added `EngineConfig` export API for inspecting engine configuration outside the engine runtime.
- Added `ToolPermissionSpec` for declarative tool permission policies.
- Added `WandbTraceProcessor` for W&B experiment tracking integration (`pip install qitos[wandb]`).
- Added `MlflowTraceProcessor` for MLflow experiment tracking integration (`pip install qitos[mlflow]`).
- Added qita cost panel showing token usage and cost metrics in the run overview.
- Added `qit --version` and `qita --version` CLI flags.
- Added `qit new --template <name>` CLI for scaffolding new agent projects from built-in cookiecutter templates.
- Added `qit list-templates` CLI for listing built-in scaffold and method templates.
- Added 5 method template recipe implementations:
  - `qitos.recipes.self_refine` — Self-Refine pattern (generate → critique → refine)
  - `qitos.recipes.reflexion` — Reflexion pattern (act → reflect → retry with memory)
  - `qitos.recipes.lats` — LATS pattern (Monte Carlo tree search with UCB1 scoring and reflection)
  - `qitos.recipes.moa` — MoA pattern (parallel proposals + aggregation layers)
  - `qitos.recipes.magentic_one` — Magentic-One pattern (orchestrator + specialist workers with stall detection)
- Added 12 method template directories under `templates/` with `paper.md`, `config.yaml`, `agent.py`, and `__init__.py`:
  - react, plan_act, swe_agent, voyager, debate, manager_worker, planner_executor, self_refine, reflexion, lats, moa, magentic_one
- Added eval config YAML files for LATS, MoA, and Magentic-One under `qitos/recipes/benchmarks/eval_configs/`.
- Added bilingual method-templates guide covering all 12 templates with quickstart code, parameters, and state fields.
- Added LATS, MoA, and Magentic-One terms to bilingual glossary.
- Added `cookiecutter` optional extra (`pip install qitos[cookiecutter]`).

### Changed

- Tightened QitOS public/default surfaces around kernel-first contracts and moved product-grade agent positioning toward `qitos-zoo`.
- Updated examples policy so canonical examples are teaching-first and product-like agents are marked for migration.
- Refreshed README.md with v0.5.0 content: 12 method templates table, `qit --version` in quickstart, Beta status, optional extras, and method-templates guide link.

### Fixed

- Restored engine final/wait lifecycle behavior so reduce, parser feedback, hooks, checkpoints, and memory records are preserved.
- Fixed `_TEMPLATES_DIR` path resolution in `qit new` so template directories at repo root are found correctly.

## v0.4.0 (2026-05-13)

### Added

- Added `qitos.cache` package with `CacheBackend` ABC, `InMemoryCache` (LRU + TTL), `DiskCache` (file-per-key), and `CachedModel` wrapper that transparently caches any `Model` instance — zero Engine changes required.
- Added `qitos.config` package with `AgentConfig`, `ModelConfig`, `DatasetItem`, `load_agent_config()` for YAML-driven agent setup with `${ENV_VAR}` resolution, and `build_model()`, `build_run_spec()`, `build_tool_registry()` builders.
- Added `qitos.checkpoint` package with `CheckpointData` and `CheckpointManager` for run persistence and resume support. Engine auto-saves checkpoints at configurable intervals.
- Added `qitos.experiment` package with `ExperimentRunner`, `ExperimentResult`, `SweepSpec`, and `sweep_product()` for parameter-sweep experiments with concurrent execution, resume support, and result persistence.
- Added `EngineResult.run_id` field so callers can track run identity after engine execution completes.
- Added `qit experiment run --config <yaml>` CLI subcommand for experiment execution from YAML configs.
- Added `AsyncEngine` with `arun()` and `arun_stream()` methods for non-blocking agent execution inside `asyncio` event loops.
- Added `EngineEvent`, `EngineEventType`, and `EventStream` for structured real-time event streaming from engine runs.
- Added `AsyncOpenAICompatibleModel` and `AsyncOpenAIModel` with `_acall_api()` and `acall_raw()` using `openai.AsyncOpenAI`.
- Added SSE endpoint `/api/stream/{run_id}` to qita for streaming run events as Server-Sent Events.
- Added "live stream" button to qita run detail page for real-time event viewing.
- Added bilingual third-party benchmark integration guidance explaining the official `framework / benchmark / recipe` boundary, required family package structure, normalized result expectations, and qita/trace compatibility rules for future benchmark contributors.
- Added a new `qitos.benchmark.osworld` family with dataset adapter, runtime hook, evaluator bridge, scorer, and built-in runner entrypoints for the real OSWorld benchmark path.
- Added a new `qitos.recipes.desktop.osworld_starter` recipe layer so the canonical desktop baseline can be reused by examples, benchmark runners, and docs without depending on `examples/`.
- Added the first official `desktop` benchmark family as an OSWorld-compatible starter path, including committed starter tasks and built-in `qit bench` support.
- Added lightweight `ActionSpace` and `EnvironmentAdapter` multimodal abstractions so the desktop benchmark path is backed by stable framework types instead of example-local glue.
- Added a benchmark-grade upgrade for `examples/real/openai_cua_agent.py`, including planner/grounding/action-selector workflow guidance, a desktop grounding critic, and richer family-first harness integration.
- Added qita screenshot timelines, replay screenshot previews, basic action overlays, grounding visibility, and step-level visual summaries for desktop runs.
- Added bilingual v0.5 desktop benchmark docs, qita GUI-failure tutorials, and a short release note explaining the OSWorld-compatible starter positioning.
- Added a native tool-call decision lane for OpenAI-compatible family presets so Qwen-class endpoints can execute structured `tool_calls` before falling back to text parsers.
- Added bilingual Qwen best-practice docs explaining the native-lane-first harness strategy for `qwen-plus` and other OpenAI-compatible Qwen endpoints.
- Added the first v0.5 multimodal core slice with shared `ContentBlock` / `ObservationPack` abstractions, screenshot-first environment support, and an OpenAI-compatible visual input path for `chat.completions`.
- Added a minimal `ScreenshotEnv`, visual trace asset metadata, qita visual-asset inspection, and a new `examples/real/visual_inspect_agent.py` baseline for screenshot-driven agent workflows.
- Added an OSWorld-inspired desktop/computer-use substrate with `DesktopEnv`, mock and container-first desktop providers, provider-neutral GUI action tools, `ComputerUseToolSet`, and new desktop action protocols.
- Added `examples/real/openai_cua_agent.py` and `examples/real/desktop_env_smoke.py` as the first QitOS-native desktop/computer-use baselines.
- Added a run-scoped structured audit board memory for `examples/real/whitzard_agent.py`, giving the long-running security auditor durable target ranking, failed-search recall, focused-read tracking, and phase-aware convergence hints.

### Changed

- Migrated GAIA, Tau-Bench, and CyBench onto the same `qitos.benchmark.* + qitos.recipes.*` architecture as the desktop starter and OSWorld paths, leaving `examples/benchmarks/*.py` as thin wrappers instead of canonical implementations.
- Changed the canonical starter benchmark name from `desktop` to `desktop-starter` while keeping `desktop` as a compatibility alias.
- Split the desktop / OSWorld story into three explicit layers: framework (`DesktopEnv`, qita, multimodal contracts), benchmark (`qitos.benchmark.*`), and recipe (`qitos.recipes.*`).
- Moved the real implementation behind `examples/real/openai_cua_agent.py` into `qitos.recipes.desktop.osworld_starter`, leaving the example file as a thin wrapper.
- Changed `AgentModule.run()` so structured `Task.env_spec` environments are no longer accidentally overridden by an implicit `HostEnv` when `workspace` is set.
- Changed the desktop runtime to validate GUI actions against a formal action space before execution and to distinguish `executed`, `accepted`, `approval_required`, and failed validation outcomes.
- Changed the unified benchmark summary layer to aggregate desktop failure-tag distributions in addition to stop reasons.
- Upgraded the `qwen` family preset from generic JSON-first compatibility to native-tool-call-first behavior with text parser fallback.
- Preserved OpenAI-compatible raw responses inside the Engine runtime instead of flattening them to strings too early, while keeping direct text-oriented model calls available for existing authoring paths.
- Collapsed the canonical coding tool surface onto one traditional naming scheme, removed duplicated `*_v2` registry aliases, and standardized file-edit parameter names around `path` and `content`.
- Upgraded `examples/real/whitzard_agent.py` to the same preset-first family switching path as the flagship coding example, so long-running security audits can swap model families and harness policies without rewriting the agent.
- Tightened `examples/real/whitzard_agent.py` around a precision-first audit workflow with `CompactHistory`, deterministic target ranking, regex-recovery guidance, and stronger transitions from broad search to focused code reads.
- Upgraded the Engine and prompt/runtime chain so current-step screenshots can flow from task resources or environment observations into multimodal user messages without changing existing parser or tool-schema behavior.
- Extended the multimodal lane into a provider-neutral desktop action path, keeping image input on the OpenAI-compatible multimodal request shape while moving GUI action scaffolding into QitOS protocols and prompt helpers instead of a provider-specific computer-use API.

### Fixed

- Fixed the desktop benchmark path so built-in runs now resolve to the desktop protocol/parser pair instead of inheriting the generic `react_text_v1` CLI defaults.
- Fixed a prompt-plumbing bug where agents overriding `build_system_prompt()` could silently drop API-level tool schemas, causing OpenAI-compatible models to guess tool argument names instead of receiving the real schema.
- Fixed qita step inspection so screenshot-backed runs can display visual assets and model-input modality summaries instead of hiding multimodal state inside raw JSON only.
- Fixed `examples/real/whitzard_agent.py` so family presets remain the protocol authority while inventory results now advance audit progress correctly and the agent no longer exposes `list_files` as an easy low-value fallback during long-running audits.

## 0.3.0 - 2026-04-08

### Added

- Added PR/push CI gates covering tests, packaging validation, stable-surface linting, and stable-surface type checking.
- Added dedicated maturity docs for architecture, development workflow, security reporting, community conduct, and environment configuration.
- Added an explicit `qitos.kit.tool.experimental.security_research` namespace for opt-in security research tool imports and registry builders.
- Added thin module boundaries for `qita` data/server/views and `render` terminal/themes façades to make future maintenance easier.
- Added a root-level changelog to document ongoing project evolution.
- Added a dedicated `requirements-dev.txt` entrypoint for full contributor installs from a local clone.
- Added stable `RunSpec`, `ExperimentSpec`, and `BenchmarkRunResult` public contracts to anchor reproducible-run metadata and normalized benchmark outputs.
- Added a first-pass unified `qit bench` CLI with `run`, `eval`, `replay`, and `export` subcommands.
- Added qita compare/diff views and export routes for summary-level run comparison.
- Added official-run and glossary docs, plus new reproducibility tutorials for benchmark runs and failed-run replay in both English and Chinese.
- Added a blog entry on why reproducible runs matter in QitOS.
- Added a first-class `qitos.harness` layer with `FamilyPreset`, `HarnessPolicy`, `ModelAdapter`, `ToolPolicy`, `ContextPolicy`, `build_harness_policy(...)`, and `build_model_for_preset(...)`.
- Added built-in gold presets for Qwen, Kimi, MiniMax, `gpt-oss`, and Gemma 4, plus bilingual docs for family presets, preset authoring, the model-family matrix, and same-example switching.
- Added `qit demo minimal`, a packaged minimal coding-agent demo that configures a real model, fixes a tiny workspace bug, and leaves behind a qita-ready trace.
- Added release notes for the first formal GitHub release package under `plans/releases/v0.3.0.md`.

### Changed

- Dropped Python 3.9 support and aligned CI, packaging metadata, README, and installation docs around Python 3.10+.
- Normalized the class-based tool contract around `execute(args, runtime_context)` while keeping `run(...)` as a compatibility path.
- Removed deprecated editor/codebase/file/shell compatibility shims in favor of the canonical `CodingToolSet` surface.
- Tightened default public exports from `qitos.kit` and `qitos.kit.tool` so experimental and higher-risk tool families are no longer part of the default surface.
- Preserved old security research import paths as short-term deprecation shims instead of keeping them as primary public entrypoints.
- Extracted shared coding-tool helper logic into internal utility modules to reduce coupling inside the canonical coding toolset.
- Slimmed `qita` and `render` entry modules so public behavior stays the same while implementation can evolve behind clearer boundaries.
- Reworked root installation guidance so `requirements.txt` is now a lightweight repo install path instead of a drifting copy of runtime and dev dependencies.
- Added coverage, dependency audit, and pre-commit tooling to the standard contributor workflow.
- Removed legacy root planning/audit scratch files, obsolete MkDocs configuration, and local phase-artifact directories so the repository surface matches the current Mintlify-based docs flow.
- Extended trace manifests with normalized run-spec, experiment-spec, benchmark, parser, and reproducibility metadata instead of keeping benchmark context in ad hoc side channels.
- Reworked benchmark example scripts so GAIA, Tau-Bench, and CyBench wrappers now emit the unified `BenchmarkRunResult` shape and route through the official v0.3 runner contract.
- Surfaced official-run and best-effort replay metadata inside qita board, run detail, and diff views.
- Updated benchmark, tracing, and CLI docs to position `qit bench` as the canonical benchmark path while keeping `examples/benchmarks` as thin wrappers.
- Refactored the flagship `examples/real/claude_code_agent.py` example into a preset-first showcase so the same agent can switch across supported model families without rewriting the agent implementation.
- Moved model-profile defaults onto preset-derived family data and extended context inference for the new v0.4 target families.
- Reworked README, quickstart, installation, CLI reference, and first-agent docs around the minimal coding-agent path so the public “minimal agent” story now matches the QitOS mindset: model config, workspace actions, verification, and qita inspection.
- Updated package metadata and contributor guidance so PyPI, docs, and release materials all describe QitOS as the torch-flavor framework for agent researchers.

### Fixed

- Fixed compatibility issues in direct `.run(...)` calls after the tool execution contract was normalized.
- Fixed the known undefined `target` reference in the exploit payload generation flow.
- Fixed stable-surface lint and mypy failures across `qitos/core`, `qitos/engine`, `qitos/models`, and `qitos/trace`.

### Deprecated

- Deprecated legacy security research import paths under `qitos.kit.tool.*_toolset` and `qitos.kit.tool.security_audit` in favor of explicit imports from `qitos.kit.tool.experimental.security_research`.

### Breaking

- Default root exports from `qitos.kit` and `qitos.kit.tool` no longer include advanced/security-audit convenience surfaces; import those explicitly from their module paths when needed.
