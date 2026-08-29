# Engineering quality program

Status: active planning umbrella
Updated: 2026-08-29
Source audit: [`docs/engineering-quality-audit.md`](../../engineering-quality-audit.md)
Execution specs: [`docs/v4/08`](../../v4/08-quality-gates-and-packaging.md),
[`docs/v4/09`](../../v4/09-runtime-lifecycle-and-error-semantics.md), and
[`docs/v4/10`](../../v4/10-consolidation-and-surface-reduction.md)
Dispatch playbook:
[`docs/v4/11`](../../v4/11-four-lane-execution-playbook.md)
Runtime expansion: [`docs/v4/12`](../../v4/12-session-runtime-and-persistence.md)
and [`docs/v4/13`](../../v4/13-durable-multi-agent-work-graph.md)

## Objective

Turn the engineering-quality audit into reviewable work without creating a
parallel architecture program. Tasks 02–05 continue to own conversation, tool,
context/artifact, and trajectory contracts. Tasks 08–10 own the gates,
cross-cutting lifecycle semantics, and eventual removal of superseded surfaces.
Tasks 12–13 now define the next capability phase: a process-independent durable
session and one durable multi-agent work graph. Quality remains their admission
gate rather than becoming their architecture.

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
7. **Task 12A–12D:** define identity/snapshot contracts, converge checkpoint v2,
   and prove the single-agent clean-process vertical slice.
8. **Task 13A–13D:** add ownership transfer and durable child/join recovery only
   after Task 12 can restore one work item.
9. **Tasks 12E/13E/05:** expose public/qita workflows and freeze trajectory v2
   only after session/work-graph lineage is available.

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

This mapping is retained through the current G1 repair. After G1 reclosure, quality and
release trust become integration-owner gates and the four capability lanes are:

1. Lane A — Task 12 session runtime and checkpoint persistence;
2. Lane B — Tasks 02/04 conversation, continuation, context, memory, artifacts;
3. Lane C — Tasks 03/13 tools, effects, handoff, delegate, spawn, fan-out/join;
4. Lane D — Task 05 trajectory, qita, replay, export, and developer experience.

## Current integration decision

The A -> C -> B -> D convergence candidate now contains A2-R, C1-R2, B1-R
Phase 2, D1-R2, and their fixing commits. Independent reruns confirm the pinned
ratchet, stable lint/type gates, tool-schema qualification, targeted consumers,
full suite, and honest trajectory readiness behavior. Provenance is recorded as
ordered source-to-integrated cherry-pick mappings rather than claiming the
original SHAs are ancestors.

An adversarial post-convergence audit reopened G1 on one C-owned issue: sensitive
mapping keys and trace-safe omitted keys can bypass redaction and loss
accounting. The required order is now:

1. C1-R3 closes key/omitted projection and loss semantics with nested regression
   probes;
2. B reruns its delegated canonical consumer; D refreshes exact receipts only if
   C producer evidence changes;
3. the integration owner reruns the combined G1 gates and records the new exact
   accepted baseline;
4. only then may the contract-only S1 wave begin: 12A, 02B, Task 03 recovery
   handoff plus 13A, and Task 05 lineage intake.

The conditional package specification lives in
[`s1_contract_wave.md`](s1_contract_wave.md). Behavior starts only after these
fixtures converge. The next end-to-end target remains deliberately user-facing:
start -> parallel tools -> pause -> process exit -> fresh-process restore ->
steer -> finish, with no duplicate committed effect. Durable multi-agent recovery
follows that single-agent proof.

Lane work may continue in isolated branches, but no completion report closes a
gate until its fixing commits and integrated verification are recorded in the
progress ledger.

## Completion

This umbrella plan closes when Tasks 08 and 09 meet their acceptance criteria,
Task 10 has either completed or explicitly scheduled each accepted deprecation,
Tasks 12–13 pass their clean-process continuity gates, and a re-audit shows no
unowned P0 engineering-quality item.
