# Engineering quality program

Status: active planning umbrella
Updated: 2026-08-29
Source audit: [`docs/engineering-quality-audit.md`](../../engineering-quality-audit.md)
Execution specs: [`docs/v4/08`](../../v4/08-quality-gates-and-packaging.md),
[`docs/v4/09`](../../v4/09-runtime-lifecycle-and-error-semantics.md), and
[`docs/v4/10`](../../v4/10-consolidation-and-surface-reduction.md)
Dispatch playbook:
[`docs/v4/11`](../../v4/11-four-lane-execution-playbook.md)

## Objective

Turn the engineering-quality audit into reviewable work without creating a
parallel architecture program. Tasks 02–05 continue to own conversation, tool,
context/artifact, and trajectory contracts. Tasks 08–10 own the gates,
cross-cutting lifecycle semantics, and eventual removal of superseded surfaces.

## Program sequence

1. **Task 08A/08E:** establish the full-surface no-regression ratchet and repair
   misleading CI signals before large new diffs.
2. **Task 08C/08D:** make optional installs and critical runtime paths testable.
3. **Task 09A:** approve the lifecycle ownership matrix and vocabulary.
4. **Task 09B–09F:** land semantic changes with the owning Tasks 02, 03, and 05;
   keep checkpoint durability and conformance harnesses in Task 09.
5. **Task 10A:** collect external/public usage evidence while the contracts land.
6. **Task 10B–10F:** consolidate only after a tested canonical replacement and
   migration window exist.

## Coordination rules

- One coding agent owns one work package and its tests/docs per review branch.
- Cross-task files have one declared semantic owner before implementation.
- Static baseline files may only shrink unless a maintainer approves an
  itemized, expiring exception.
- No deletion is authorized by this umbrella plan alone; Task 10 decision gates
  and repository release policy still apply.
- Update the audit opportunity table or task evidence section after every
  merged package.

## Four-lane ownership

The implementation program runs through four semantic owners:

1. Lane A — quality gates, CI, packaging, and test infrastructure;
2. Lane B — conversation, provider codecs, request views, context, artifacts,
   and history;
3. Lane C — tool outcomes, coding tools, execution, lifecycle, timeout,
   durability, and MCP;
4. Lane D — trace/tracing/qita, hook completeness, benchmark migration, and the
   shared removal ledger.

Task 09 and Task 10 are split across these owners. The full file-lease, fixture-
handoff, merge-wave, and stop-gate rules are in the dispatch playbook.

## Current integration decision

The first repair wave produced A1/A2, B1-R Phase 1, C1-R, and D1-R. It closed
most first-wave findings, but the integration-owner re-review found one broken
workflow import, incomplete JSON/aliasing/projection boundaries in ToolResult,
the intentionally deferred B/C result convergence, and a self-attested receipt
trust boundary. Exact probes, source identities, and dispositions are maintained
in [`docs/progress.md`](../../progress.md).

The required order is now:

1. A2-R makes workflow-owned Python executable under repository tests, then A
   is integrated and the pinned ratchet is run;
2. C1-R2 closes recursive JSON validation, nested ownership isolation, and
   complete safe-projection/loss semantics on the accepted A HEAD;
3. B1-R Phase 2 rebases onto accepted C, removes the temporary result
   representation, and makes its versioned external reader strictly typed;
4. D1-R2 consumes producer-owned, digest-bound B/C receipts and proves manifest
   schema/validator parity while preserving all honest blockers;
5. combined G1 qualification runs before any 02B/03B/05A behavior wave.

Lane work may continue in isolated branches, but no completion report closes a
gate until its fixing commits and integrated verification are recorded in the
progress ledger.

## Completion

This umbrella plan closes when Tasks 08 and 09 meet their acceptance criteria,
Task 10 has either completed or explicitly scheduled each accepted deprecation,
and a re-audit shows no unowned P0 engineering-quality item.
