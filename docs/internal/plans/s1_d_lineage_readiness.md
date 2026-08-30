# S1 Lane D lineage and readiness plan

Status: complete; runtime/readiness remains intentionally typed blocked
Updated: 2026-08-30
Owner: Lane D / stable trajectory lineage, readiness, and developer experience
Source branch: `feat/campaign-absorption`
Source commit: `c1efb0f4adde3e673bf181af5b1760c19a451ae2`
Branch: `codex/v4-s1-d-lineage-intake`
Worktree: isolated S1-D worktree (host-local path intentionally omitted)

G2 integration update: the exact A/B/C producer bundles now populate all 17 S1
requirements, and the stable receipt set qualifies each requirement
independently. This completes contract intake only. Normal readiness remains
typed blocked because runtime consumers and the Trajectory writer/store/qita
migration do not exist.

## Objective

Define one future `Trajectory` architecture and a strict, producer-owned S1
readiness/evidence contract for session, conversation, recovery, and work-graph
lineage. This package is an intake and qualification gate only. It does not add
a trajectory writer/store, change qita runtime, freeze a trajectory schema, or
make storage, compression, deduplication, publication, or performance claims.

## Baseline and constraints

- The integration source was clean and matched the exact requested commit and
  subject before this worktree was created.
- Current trace artifacts remain a frozen compatibility input. Current tracing
  spans and renderer JSONL are derived planes, not competing products.
- Runtime producer lanes own facts and schemas. Lane D records requirements and
  validates exact committed evidence; it never infers lineage from identifiers,
  paths, or naming conventions.
- `tests/fixtures/trajectories/` and `tests/fixtures/readiness/` are the stable
  fixture roots. Historical producer fixture paths remain compatibility inputs.
- `README.md`, `README.zh.md`, `CHANGELOG.md`, and `docs/progress.md` are explicit
  integration-owner leases and are not modified in this package.

## File lease

Lease owner: Lane D / S1-D lineage intake

Files:

- `docs/internal/plans/s1_d_lineage_readiness.md`
- Lane D evidence/ADR documents under `docs/internal/plans/`
- `scripts/benchmark_trajectory_store.py`
- `tests/test_benchmark_trajectory_store.py`
- `tests/test_lane_d_evidence_links.py`
- new Lane D tests under `tests/`
- `tests/fixtures/readiness/`
- `tests/fixtures/trajectories/README.md`

Semantic purpose: exact-source census, one-Trajectory target decision, strict
cross-lane receipt/readiness validation, privacy/portability evidence, and
future qita developer experience. No runtime writer, reader migration, CLI
behavior, public export, or producer-owned schema is implemented.

Expected package: S1 Lane D lineage intake only.

Other lanes: A/B/C remain semantic owners. Their absent or unaccepted facts are
reported as typed blockers. Receipt refresh after producer acceptance is a
separate mechanical commit owned by the integration sequence.

## Work plan

1. Complete the exact-source census through runtime events, trace/tracing,
   renderer, checkpoint/replay/fork, qita/export, evaluation, provider,
   ExchangeLog, ToolResult, artifacts, compaction, and multi-agent paths.
2. Publish the single `Trajectory` target ADR, lineage field proposal,
   canonical/derived/compatibility disposition, removal prerequisites, and
   beginner/advanced qita flows.
3. Replace the G1-only requirement list with a stable S1 A/B/C contract
   inventory carrying owner, authority, schema state, exact evidence bindings,
   blockers, and remediation.
4. Harden receipt validation for unsupported/unestablished schemas,
   identity/lineage conflicts, inferred edges, exact committed/current bytes,
   approved authority, and one-blocker-only clearing.
5. Add stable readiness scenario fixtures and machine/CI/maintainer/developer
   output with low-cardinality codes and no rejected value echo.
6. Run the requested targeted, static, full-suite, CLI-mode, portability, and
   diff checks; record exact results and final source identity.

## Stop gates and unsupported claims

- No canonical trajectory writer or store exists in this package.
- The proposed record fields and payload `schema_version` are not frozen.
- No producer commit, fixture digest, evidence digest, or version is invented;
  G2 bindings are resolved only after the semantic-owner commits exist.
- Existing G1 B/C receipts and all 17 G2 receipts qualify contract bytes only;
  they do not establish runtime or Trajectory readiness.
- No benchmark measurement, publication, compression, deduplication,
  performance, or qita migration claim is permitted.
- No current trace/qita compatibility behavior is removed or changed.

## Progress

- [x] Exact source identity and clean isolated worktree verified.
- [x] Required architecture, wave, Task 05/12/13, prior Lane D, fixture, and
      readiness sources read.
- [x] Extended exact-source census and disposition published.
- [x] Single Trajectory ADR and qita/DX proposal published.
- [x] S1 A/B/C readiness inventory and strict validator implemented.
- [x] Scenario fixtures and privacy/portability tests implemented.
- [x] Targeted and full validation complete.
- [x] Diff, commits, clean status, and exact final HEAD recorded in the handoff.
