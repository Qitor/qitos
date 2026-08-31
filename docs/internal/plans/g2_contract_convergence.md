# G2 stable-contract convergence plan

Status: candidate delivered; independent G2-R2 audit blocks promotion
Updated: 2026-08-31
Owner: one G2 integration owner
S1 source ancestry baseline: `c1efb0f4adde3e673bf181af5b1760c19a451ae2`
Plan carrier: `907cf038b3a6af469a27ff6f1b2d48a0c7d3d7c7`
Target branch: `codex/v4-g2-contract-convergence`
Target worktree: `/Users/morinop/Desktop/WhitzardOS-g2`

## Post-candidate disposition

Candidate `cab8fd246d2485784a13558e668eadb3ffa4d42f` preserves the intended
identity, snapshot, ArtifactRef, WorkGraph, capability-owner, and receipt
directions and passes its complete repository suite. It is not the integration
baseline: it branched before `3ab69c91...`, has not been promoted, and its S1/G2
worktrees remain registered.

Independent probes reopened strict historical ToolResult grammar, strict
ProviderCapabilities types, complete diagnostic/ArtifactRef secret and path
safety, honest current-versus-historical receipts, and private `__all__`
visibility. The authoritative closure plan is
[`g2_r2_promotion_audit.md`](g2_r2_promotion_audit.md). Do not start S2 from the
candidate HEAD.

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

## Independent audit evidence

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

## Blocking repairs

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
- [ ] Retired S1/G2 worktrees have a clean, non-forced post-promotion removal
      receipt; their branch and commit references remain recoverable.

## Post-promotion worktree retirement

Worktree removal is part of closing the wave, not an optional later cleanup.
Only after the qualified G2 HEAD has been promoted to the integration branch,
recorded in `docs/progress.md`, and independently verified may the integration
owner retire these explicit paths:

- `/Users/morinop/Desktop/WhitzardOS-s1-a`;
- `/Users/morinop/Desktop/WhitzardOS-s1-c`;
- `/Users/morinop/Desktop/WhitzardOS-s1-b`;
- `/Users/morinop/Desktop/WhitzardOS-s1-d`;
- `/Users/morinop/Desktop/WhitzardOS-g2` after promotion no longer depends on
  that checkout.

Before each removal, verify the path is a registered worktree, its status is
clean, no task is running in it, and every required commit/evidence identity is
recorded and reachable through a retained branch or the promoted baseline. Use
`git worktree remove <exact-path>` without `--force`, then `git worktree prune`
and verify both the filesystem path and worktree registry entry are gone.

Never use `rm -rf`, never remove the primary integration worktree, and do not
delete source branches or commit refs unless the maintainer separately asks for
branch deletion. Dirty, locked, missing-evidence, or active worktrees produce a
typed cleanup blocker rather than forced deletion.

## Explicit non-goals

This plan does not implement Engine pause/resume/fork, session-head store CAS,
fresh-process restore, child scheduling, cross-process multi-agent execution,
hard thread cancellation, provider dispatch migration, a trajectory writer or
store, qita runtime changes, or public root exports. Those start only after G2.
