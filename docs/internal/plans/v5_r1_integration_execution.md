# V5 R1 integration execution

Status: in progress; qualification and promotion pending. Live not run; no push or release.

## Authorization and preservation

The 2026-09-05 integration instruction supersedes older planning restrictions on
local preservation, qualified fast-forward promotion and non-forced retirement.
Remote synchronization remains unauthorized. Source baseline:
`4dfb570fb7eef504c1e6d247c21a1984251b80e4`.

Main started clean in the index at `60809b3be388d22ea40ea41b4aaa1f5540c76fda`,
with exactly the 23 allowed modified/untracked files. Preservation branch
`codex/v5-r1-planning-preserved`, commit
`318adc4be92222dd8cf0ef9035c80561feb5ccfc`, retains every file byte as verified
against [pre-stage digests](v5_r1_integration_evidence/planning-digests.json).
Main returned to clean master. Integration was created directly from the fixed
baseline. Planning replay: `ee95805` (not part of the 27 producer commits).

## Replay and conflict decisions

All four branches match their reviewed heads, clean working trees, exact common
baseline, counts 6/4/11/6, and no merges. All 27 commits replayed C → B → D → A,
without squash/skip/source edits. Full identities and conflicts are recorded in
[the mapping](v5_r1_integration_evidence/replay.json).

Planning replay conflicts: README.md and README.zh.md. Preserve baseline's new
self-contained tutorial entry AND the planning roadmap entry; no old full-file
replacement. B final docs, D final docs and A final docs each conflict in
README.md, README.zh.md and CHANGELOG.md: independent capability bullets and
migration facts from both sides are retained in their original sections.

Runtime and generated-document shared files merged textually. Semantic review
and combined behavior gates remain required: B step/exchange identity and
pre-selection policy; A completion order and dispatch/usage/refund; B/D API sync
features; all EN/zh source bindings will be regenerated on repaired source.

## Remaining execution

1. Reproduce and repair C1/C2, M1/M2, DX1, retaining source regressions.
2. Same-wheel original and combined installed consumers, success/failure variants.
3. Docs/migration/compatibility and complete pinned-toolchain qualification.
4. Qualified local FF, main revalidation, exact dispatch identity, safe retirement.

Historical review failures remain in the original review and probe files.

## R1-DX1 repair

The new YAML regressions failed 4 cases before repair (12 validation negatives
already passed); 67 YAML/config/security/extension tests pass after repair.
Only SDK-free tests ran. Named policy uses existing resolve_extensions factories;
loss requires a real boolean. B's context-only dataclasses.replace is removed.
Roundtrip exposed an existing serializer issue: unsafe_host emitted sandbox-only
neutral defaults rejected by its own loader. Serialization now emits type and
workspace only for that backend; admission and Env execution constraints are
unchanged. Config roundtrip and digest equality are asserted without a workaround.
Installed consumers and final source bindings remain pending.

## R1-M1/M2 repair

The initial 31 real-adapter regressions failed before repair. Stream chunks now
carry the existing reasoning_fields representation into ModelResponse, decoded
ReasoningBlock and RequestView. OpenAI-compatible selects the same Chat/Responses
codec as the built-in OpenAI adapter. Chat field replay requires explicit capability
support, matching provider/API scope and supported source field; generic providers
remain loss-explicit. No visible answer is synthesized from reasoning.

Cleanup attempts every owned resource, reports numeric cleanup_failures only,
retains typed primary category/stage/sent/partial/usage and preserves callback
exception identity/cancellation. Normal cleanup failure is typed. ProviderFailure
keeps only allowlisted non-negative integer usage counters, never raw SDK extras.
Expanded tests include borrowed Responses helper clients, cancellation during
iteration/cleanup, explicit sync/async close and no-reasoning behavior. A focused
144-test adapter/codec sweep passed before the last cancellation-only additions;
final complete tests and installed two-tool-round verification remain pending.
