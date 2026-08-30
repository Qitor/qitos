# G2 stable-contract convergence plan

Status: complete and repository-qualified; runtime/Trajectory work not started
Updated: 2026-08-30
Owner: one G2 integration owner
S1 source ancestry baseline: `c1efb0f4adde3e673bf181af5b1760c19a451ae2`
Plan carrier: `907cf038b3a6af469a27ff6f1b2d48a0c7d3d7c7`
Target branch: `codex/v4-g2-contract-convergence`
Target worktree: `/Users/morinop/Desktop/WhitzardOS-g2`

## Closure record

The fixed dispatch `096e08244a0274720a58f07ed9f45ca0a7eece59` was used
directly. All 22 source commits were applied in the required A -> C -> B -> D
order without textual conflicts. The original source commits remain provenance;
the integrated commits are new cherry-pick identities.

G2 closes the eight semantic blockers at the contract layer:

- A producer `58864253a169d1bac5749ad2b2de5de6872c0da2` owns the typed
  identity vocabulary, extensible snapshot envelope/registry, component
  integrity rules, and canonical `ArtifactRef` foundation;
- C producer `bd7fca95e9ba9acfbbd9e8d0655a14ece066bcb6` consumes A
  identities directly, publishes the current ToolResult writer plus isolated
  historical reader, and owns typed effects/WorkGraph components;
- B producer `3cc29bea2bd311a2343862fd0b4f32636524bbb6` owns the sole
  conversation component, RequestView projections, typed continuation, and
  provider-declared capabilities without provider-name inference;
- D receipt integration `fcb0784` independently binds all 17 S1 requirement
  IDs to exact A/B/C producer commits, repository-relative paths, current and
  committed bytes, SHA-256 digests, qualification authority, typed identities,
  and explicit producer lineage.

The contract receipt gate reports all 19 requirements qualified (the two G1
foundations plus 17 G2 items) and no receipt blocker. This is deliberately not a
runtime or Trajectory claim: Engine pause/resume/fork, SessionStore/head CAS,
clean-process restore, persistent child scheduling, trajectory writer/store,
qita migration, publication, compression, deduplication, and performance remain
typed blocked or out of scope.

The beginner interface budget is frozen in
`docs/architecture/public-interface-budget.md`: 127 measured module-level
exports are classified, with no new root export and no new Engine parameter.

## Final qualification

The final G2 tree passed these gates on 2026-08-30 using the repository's
complete Python 3.12.7 quality environment:

| Gate | Result |
|---|---|
| static quality ratchet | 399 findings baselined: 377 active, 22 vendored/generated; no growth |
| stable flake8 | exit 0, no findings |
| stable mypy | success on 84 source files |
| architecture / public surface / no-local-path | 4 / 4 / 2 passed |
| session/checkpoint/Engine | 84 passed |
| conversation/RequestView/codec | 58 passed |
| ToolResult/WorkGraph | 74 passed |
| D readiness and receipt adversarial | 60 passed |
| trace/qita compatibility | 97 passed |
| convergence and interface budget | 12 passed |
| explicit migration/malformed/privacy/portability probes | 8 passed |
| full suite | 2010 passed, 50 conditionally skipped |
| diff check | clean |

Readiness without receipts exits 0 with zero qualified contracts and 19 receipt
findings. Dry-run with the exact receipt set exits 0 with 19 qualified contracts
and zero receipt findings. Normal execution with the same receipts exits 2 with
`schema_not_ready`. All modes report no measurements or claims.

The host's default Homebrew Python 3.13.3 lacks flake8 package metadata, so an
initial ratchet invocation failed before analysis. Selecting the existing
repository quality environment (`/opt/anaconda3/bin`, Python 3.12.7) made the
required `python scripts/static_quality.py check` invocation executable; the
gate then passed without any source or baseline relaxation.

## Objective

Converge the four independently produced S1 contract packages into one stable
architecture before any S2 pause/restore or persistent multi-agent behavior is
implemented. This is a semantic integration task, not a fifth feature lane.
It preserves one public concept for each role: `Session`, `SessionSnapshot`,
`ExchangeLog`, `RequestView`, `ToolResult`, `WorkGraph`, and `Trajectory`.

Public classes, modules, and product language must not introduce parallel
`V1`, `V2`, `Legacy`, `Next`, or equivalent architectures. Serialized records
may carry an internal `schema_version`; one current writer and isolated
historical readers/migrations are required when bytes evolve.

## Fixed source candidates

| Lane | Branch | Reviewed HEAD | Producer facts |
|---|---|---|---|
| A | `codex/v4-s1-a-session-contracts` | `cb79532d45b114826ee4313a60bf42ebc5abca06` | identity producer `63d5cfbea4e0a0941b038833f0152c391d9b63bd`; snapshot contracts `aeb58379d2a266f5f8ba36688530f9ac27da07d1` |
| C | `codex/v4-s1-c-work-graph-contracts` | `61c85ab774705610a2edf039417a8480afbeee16` | effect/work fixtures `c4b4943e9281e86a122bf1e59d8a5e4960eb397c` |
| B | `codex/v4-s1-b-request-view` | `939edd0164a7f1929818f3e79bea02f2635a9d7d` | request fixtures `86b6f41ed68b4775a6e974c05200a6a76748d742`; local evidence `774642eb21b4cb0b5f417d2ff6fbb9f2e488087a` |
| D | `codex/v4-s1-d-lineage-intake` | `44a09e3cbfaa29978584a05fbafbdd5c37cd7f2f` | readiness inventory/evidence at reviewed HEAD |

Every worktree was clean at review. All four heads descend from the S1 source
ancestry baseline. The source commits are candidates, not accepted integration
facts.

The G2 worktree must start from the exact `feat/campaign-absorption` dispatch
SHA supplied by the integration owner. That SHA must contain the plan carrier
above and may differ from the S1 source ancestry baseline because the audit and
dispatch documentation landed after the four candidates branched. Do not start
the G2 worktree directly from `c1efb0f...`.

## Pre-convergence independent audit evidence

An isolated A -> C -> B -> D merge completed without textual conflicts. The
merged tree passed 173 focused contract/readiness/boundary tests, the full suite
(`1999 passed, 50 skipped`), the 399-finding static ratchet, stable flake8,
stable mypy on 81 files, and `git diff --check`.

Green branch and merged-tree tests do not close the semantic blockers below.
Independent probes demonstrated that:

- C accepts arbitrary work/session/agent strings instead of Lane A typed
  identities;
- B's component schema cannot be used directly as A's outer component version,
  and no reviewed adapter resolves the outer/inner schema boundary;
- B's `ArtifactRef.to_dict()` is rejected by C's strict ToolResult artifact
  validator;
- the current C ToolResult writer is rejected by the pre-S1 strict reader while
  retaining the same serialized schema identity;
- `ProviderFailure.to_dict()` preserves a secret/host-path-bearing message and
  details;
- WorkGraph missing-identity diagnostics echo an untrusted host path;
- D still reports all 17 S1 requirements as
  `producer_version_unestablished`, qualifying only the two G1 foundations.

## Historical blocking repairs (closed by the closure record above)

### G2-I1 — one identity vocabulary

Lane A owns runtime identity types. C must use the accepted `SessionIdentity`,
`WorkItemIdentity`, `AttemptIdentity`, and `AgentIdentity` at its in-memory
boundaries and preserve their kinds in serialized records. B continuation and
artifact resolver references must compose with A's resolver contract. Raw
strings may remain only at explicit compatibility or wire-codec boundaries.

No consumer may copy identity enums or validate only “non-empty string”.

### G2-S1 — one snapshot composition model

Freeze one outer `SnapshotComponent` contract and one owner codec per component.
Resolve the current duplicate ownership of ExchangeLog, queued steering, and
provider continuation: these facts must have one B-owned component, not both a
conversation component and separate competing A slots. Resolve C's tool/effect
and work-graph components the same way.

The envelope's component schema identifier and each owner's inner payload
schema must have an explicit relationship. A must not hard-code every future
owner version into a closed map without a codec/registry boundary. Add real
A-reading-B and A-reading-C tests; prior simulations do not qualify.

### G2-A1 — one ArtifactRef

Create or select one core `ArtifactRef` contract owned semantically by the
context/artifact lane and consumed directly by RequestView, ToolResult,
snapshots, and future trajectory records. It must include content identity,
resolver reference, media/size, sensitivity, provenance, required/optional
behavior, and safe model projection without artifact bytes or host paths.

Remove the current B typed-object versus C restricted-dict mismatch. Do not
introduce a second result or artifact envelope.

### G2-T1 — honest ToolResult schema evolution

C added recovery/effect fields to the current writer while retaining the old
serialized schema identity. A pre-S1 strict reader rejects the new bytes with
`unknown_canonical_field: attempt_id`. Preserve the stable `ToolResult` class,
but make serialized evolution honest: one current schema/writer, an isolated
reader/migration for previously committed bytes, explicit compatibility tests,
and no public `ToolResultV2` type.

Requalify ExchangeLog and D receipts after the serialized bytes are final.

### G2-P1 — provider-neutral capability ownership

The generic codec contract must not infer reasoning and continuation support by
hard-coding `transport == "openai"` and `api_mode == "responses"`. Provider
adapters declare capabilities through one protocol; the generic layer validates
them. Defaults remain simple for users, but provider-specific knowledge stays
beside the provider.

### G2-R1 — safe diagnostic boundary

Redact or structurally exclude credentials, headers, bearer tokens, local
endpoints, file URIs, home paths, and host paths from provider and WorkGraph
diagnostics. `redacted_details` is a claim that must be enforced, not a field
name. Add adversarial string/scalar/nested-key tests and prove model, trace,
receipt, exception, and readiness projections are safe.

### G2-U1 — honest interface budget

Zero root exports does not by itself prove a simple interface. The four new
contract modules currently declare 96 names through `__all__` across roughly
4,500 lines. Classify every name as beginner-facing, extension-facing,
persistence-internal, or private. Keep the future beginner façade limited to
session/run/pause/restore/fork, steering/context inspection, explicit
delegate/fan-out/join/handoff, and qita navigation. Internal codecs, schema
constants, CAS records, receipts, and graph bookkeeping must not become the
ordinary-user API.

This gate does not authorize root exports or runtime façades in S1; it freezes
their budget and prevents accidental public sprawl before S2.

### G2-D1 — exact producer qualification

After A/C/B repairs are committed, publish producer-owned fixtures and evidence
whose exact commits contain the reviewed bytes. D then binds all 17 S1 contract
requirements to the accepted producers. One receipt clears one blocker. G2 may
be contract-ready while trajectory runtime remains `schema_not_ready`; no
writer, store, qita migration, publication, compression, or performance claim
is authorized.

## Integration sequence

1. Verify the supplied G2 dispatch SHA contains the plan carrier, then verify
   all four reviewed heads, their ancestry from `c1efb0f...`, commit chains,
   and clean statuses; create the target worktree from the supplied dispatch
   SHA.
2. Integrate A in source order and review the identity/snapshot producer.
3. Repair G2-S1 envelope extensibility and freeze the component-owner rules.
4. Integrate C in source order; close G2-I1 and G2-T1 against accepted A.
5. Integrate B in source order; close G2-A1, G2-P1, and the A/B snapshot
   consumer with no provider-default change.
6. Close G2-R1 and G2-U1 on the combined A/C/B tree.
7. Commit final A/C/B fixtures/evidence and resolve exact producer SHAs/digests.
8. Integrate D; replace unestablished S1 requirements with exact accepted
   producer bindings and run receipt adversaries.
9. Run combined qualification, synchronize shared release documents, and only
   then promote one G2 baseline.

The semantic order is fixed A -> C -> B -> D. Conflict-free git merges do not
authorize changing it.

## File leases

- `qitos/core/session.py` and session fixture envelope: A semantics, G2 owner
  performs integration repairs;
- `qitos/core/tool_result.py` and `qitos/core/work_graph.py`: C semantics;
- `qitos/core/conversation.py`, `qitos/core/request_view.py`, artifact contract,
  and `qitos/models/codec.py`: B semantics;
- readiness script, requirements, receipts, and trajectory intake: D semantics;
- `README.md`, `README.zh.md`, `CHANGELOG.md`, `docs/progress.md`, playbook, and
  shared status sections: G2 integration owner only.

Unexpected semantic changes return to the owning contract. Do not resolve them
by copying a producer type into a consumer module.

## Validation

Required before promotion:

- exact A/B/C producer and D receipt digest checks;
- cross-lane identity, snapshot, ArtifactRef, ToolResult migration, provider
  capability, and diagnostic-safety adversarial tests;
- session, checkpoint, Engine, conversation, provider codec, ToolResult,
  WorkGraph, readiness, trace, and qita targeted suites;
- architecture boundaries, root public surface, no-local-path, docs parity;
- controlled historical ToolResult read and current-writer proof;
- dry-run without receipts, dry-run with exact receipts, and normal typed-blocked
  readiness behavior;
- fixed Python 3.12 static ratchet;
- stable flake8 and mypy;
- full `pytest -q` without rerun or masked exit;
- `git diff --check` and final clean status.

## G2 exit criteria

- [ ] A/C/B use one typed identity vocabulary.
- [ ] One extensible snapshot envelope consumes real B/C components.
- [ ] One ArtifactRef is shared by request, result, snapshot, and lineage facts.
- [ ] ToolResult has one current writer and tested historical migration reader.
- [ ] Generic capability logic contains no provider-name heuristic.
- [ ] Provider/WorkGraph diagnostics pass adversarial privacy tests.
- [ ] Public/extension/internal surfaces have a reviewed interface budget.
- [ ] D binds all 17 S1 requirements to exact accepted producers.
- [ ] S1 contracts are qualified while runtime/trajectory claims remain honest.
- [ ] Combined quality gates pass and one clean G2 baseline is promoted.

## Explicit non-goals

This plan does not implement Engine pause/resume/fork, session-head store CAS,
fresh-process restore, child scheduling, cross-process multi-agent execution,
hard thread cancellation, provider dispatch migration, a trajectory writer or
store, qita runtime changes, or public root exports. Those start only after G2.
