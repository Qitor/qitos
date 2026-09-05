# v5 iteration planning

Status: completed planning deliverable; documentation-only, not implementation qualification.
Date: 2026-09-04.

## Source and scope

- Planning source: `f9e45f372ba4b8a5c89982add56a667908893b30`, branch `master`.
- Historical G5 runtime qualification: `717b4cf1b23f2ed252cd03234ffd8605038d9567`.
- The preceding read-only audit found residual provider-stream failure semantics,
  legacy ACI alias bugs, dual Observation state, inert functional policies,
  memory/compaction integration gaps, full-scan journal costs, missing training
  exporters, and incomplete optional integration/consolidation work.
- Concurrent master CI stabilization owns publication runtime/tests and its own
  plan. Preserve those changes; do not qualify them through this documentation.
- No model, credential lookup, deployment, push, release, branch switch or
  worktree deletion is part of this task.

## Deliverables

1. `docs/v5/README.md`: scope, audited starting facts, v4 migration map,
   responsibility boundary, priority, dependencies, file leases and acceptance.
2. Five actionable task documents: developer/provider loop; long-task context
   and memory; tools and consolidation; trajectory and research data; interactive
   Session and sandbox extensions.
3. Progress, v4 acceptance anchor, architecture-debt pointer, bilingual README
   and changelog updates, all explicitly describing plans rather than features.
4. Supersession notice and output-budget correction in the earlier functional
   E2E plan; no new live execution authorization.

## Plan

- [x] Read repository/documentation rules and verify current source and dirty scope.
- [x] Write the overview and five task groups with measurable acceptance.
- [x] Synchronize navigation and distinguish historical evidence from new plans.
- [x] Check task/dependency completeness, local links, privacy and scope.
- [x] Run focused documentation/repository gates and record exact results.

## Validation policy

Use local-link checks for repository Markdown plus the existing public docs
validator and focused privacy, architecture, public-surface and workflow tests.
No MDX, navigation, executable tutorial, runtime or package changes are intended.
No site promotion is performed; a future public-site promotion must still follow
`docs/AGENTS.md` rendering and installed-tutorial requirements. Do not report a
full-suite, Docker, live-provider or packaging rerun unless actually executed.

## Completed work

- Added `docs/v5/README.md` and five task documents. The overview maps original
  v4 packages, avoids reopening qualified G5 mechanisms, defines R1/R2/R3,
  explicit shared-file ownership and future baseline/worktree rules.
- Separated mechanism qualification from real Agent/migration evidence; optional
  stronger backends and later metadata work cannot block unrelated delivery.
- Updated bilingual README, changelog, progress, v4 acceptance anchor and debt
  pointer with planning-only statements. Earlier E2E scenarios are reused, with
  10,240 suggested output tokens and explicit per-profile/aggregate authority.
- Concurrent CI work evolved during drafting, including journal parsing and
  publication changes. v5 binds audit facts to the original source and requires
  consuming/rechecking committed successors rather than duplicating their fixes.
- This task changed no runtime, fixture, test, CI or quality-baseline file, and
  performed no Git promotion, commit, push, live call or resource cleanup.

## Validation results

- Repository Markdown check: five task groups, seven new planning files,
  30 local links; required task sections/fences and baseline-placeholder checks
  passed.
- Public navigation/bilingual/local-links validator: passed.
- `python -m pytest -q tests/test_no_local_paths.py
  tests/test_architecture_boundaries.py tests/test_public_surface.py
  tests/test_workflow_contracts.py`: **19 passed in 1.81 seconds**.
- First privacy pass caught two literal-pattern collisions in new prose/link
  names (not actual credentials/host paths). Renamed the context document and
  clarified network prose; final required checks passed without changing tests.
- `git diff --check`: passed.
- No full pytest, Docker, live model, packaging, browser/MDX or remote CI
  qualification is claimed for this repository-Markdown-only planning task.

Validation ran in the shared working tree with concurrent changes present;
these focused results are not qualification of the other task's runtime or of a
new committed release baseline. Implementation dispatch remains unissued.

## R1 follow-up review and executable instructions — 2026-09-05

The earlier sections are the 2026-09-04 planning record. Current follow-up:

- [Current-source review](v5_r1_review.md) verifies green remote master
  `4dfb570fb7eef504c1e6d247c21a1984251b80e4`, completed CI/tutorial fixes and
  current residual behavior; direct probes were rerun without network.
- [Common dispatch](v5_dispatch.md) plus four complete A/B/C/D instructions are
  prepared, not launched. Runtime source is pinned separately from the local
  uncommitted planning inputs; no baseline placeholder or dirty-tree reset.
- Refined R1: stream correctness; usable memory/window compaction; handoff race
  and public correctness; strict-integrity index/bounded read/export. Functional
  cleanup, full legacy history migration, GC/export formats and interactive
  controls remain separately scheduled, not silently marked complete.
- Updated V5 overview/tasks, progress and bilingual README/changelog as plans.
- Scope remains documentation-only. No implementation, commit, merge, push,
  remote setting, model credential access, Docker or worktree cleanup.

R1 verification completed:

- Runtime-oriented focused checks: 39 + 130 passed, with exact local/remote
  source equivalence stated in the review; five read-only diagnostic probes
  confirmed the remaining gaps without network requests.
- Pinned static ratchet against R1 baseline: passed; 356 findings unchanged
  (334 active, 22 vendored/generated). No baseline file was updated.
- All 13 V5 planning files: balanced code fences, 51 local links resolving,
  four distinct lane instructions with exact SHA/worktree commands, no baseline
  placeholder; passed.
- Public navigation/bilingual/local-link validation and `git diff --check`
  passed. Final privacy/architecture/public/workflow suite: **19 passed in
  1.80 seconds**. No tests, runtime, toolchain or quality allowances changed.

## Standalone dispatch refinement — 2026-09-05

User requested four clearer, individually transferable execution instructions.
Remote master remains `4dfb570fb7eef504c1e6d247c21a1984251b80e4` (ls-remote
rechecked); main worktree and its drafts remain untouched outside owned docs.

- A now specifies actual adapter/API-mode coverage, terminal/usage/cancellation
  oracles and an exact three-request / three-tool / final-11 installed fixture.
- B now specifies the module-level adapter/compactor target, real extensions
  mapping, existing budget/window owner, durable record identity/dedup, namespace
  and two-process consumer. ExtensionRegistry was a planning naming error, not
  an existing type; no new registry is requested.
- C now specifies pre-dispatch persistence and post-restore owner authority,
  six crash/duplicate outcomes, 20 forced-interleaving processes and concrete
  Observation/Read/Edit mutation assertions.
- D now specifies snapshot-bound cursors, append-versus-tail semantics, derived
  index watermarks, an isolated-reader workload/memory oracle, and no premature
  success publication for streamed exports.
- The final conversation instructions carry the full mandatory scope. Missing
  uncommitted local plans on another checkout is no longer a prerequisite failure.
- No new baseline commit, runtime changes, model calls, worktree creation or
  agent launch is included. This refinement is documentation-only.

Refinement validation: public navigation/parity/local links passed; 13 planning
files and 51 local links passed; privacy/architecture/public/workflow tests
**19 passed in 1.79 seconds**; `git diff --check` passed. No full suite or runtime
qualification was rerun for this wording/API-contract refinement.
