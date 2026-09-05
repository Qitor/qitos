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
