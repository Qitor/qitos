# S1 Lane C effects and work-graph contract plan

Status: in progress; C-owned contracts may be frozen, cross-lane qualification waits for reviewed Lane A/B producers
Updated: 2026-08-30
Owner: Lane C — Stable Effects, Recovery and Multi-Agent Work Graph
Source: `c1efb0f4adde3e673bf181af5b1760c19a451ae2`

## Objective

Evolve the sole canonical `ToolResult` with durable attempt/effect/retry and
reconciliation facts, and define one generation-checked `WorkGraph` contract
for multi-agent ownership. This package freezes contracts, fixtures, adapters,
and evidence only. It does not implement child scheduling, distributed work,
hard thread cancellation, or process-independent multi-agent execution.

## Scope and stop conditions

- Preserve `ToolResult` as the only tool/action/child-work outcome.
- Keep `ActionResult` as compatibility input only.
- Define `WorkGraph` records in the contract layer; do not add another Engine,
  scheduler, result envelope, checkpoint/session store, or root export.
- Treat timeout, accepted cancellation, worker termination, external-effect
  certainty, reconciliation, late results, and stale ownership as distinct.
- Persist identifiers, immutable data, and opaque resolver/context references;
  never persist threads, futures, clients, credentials, closures, or stacks.
- Stop cross-lane qualification at `waiting_on_lane_a` until the reviewed Lane
  A identity/snapshot producer is consumed. Lane B context transfer remains an
  opaque reference in this package.

## File leases

Lease owner: Lane C
File(s): `qitos/core/tool_result.py`
Semantic purpose: canonical attempt/effect/retry/reconciliation vocabulary
Expected start/end package: S1 Lane C producer
Other lanes blocked or adapter supplied: existing v1 reader/writer remains; B/D consume versioned fixtures

Lease owner: Lane C
File(s): new `qitos/core/work_graph.py`
Semantic purpose: one durable ownership graph contract and strict serializer
Expected start/end package: S1 Lane C producer
Other lanes blocked or adapter supplied: no root export; A identity and B context references stay opaque

Lease owner: Lane C
File(s): `docs/architecture/tool-outcome-and-runtime-ownership.md`, new Lane C ADR/evidence docs
Semantic purpose: effect vocabulary, exact-source census, safe boundaries, API decision, handoff evidence
Expected start/end package: S1 Lane C producer
Other lanes blocked or adapter supplied: shared release/progress files remain untouched

## Work plan

1. [complete] Census exact runtime sources and existing tests for tools,
   concurrency, lifecycle resources, recovery, and multi-agent paths.
2. [complete] Freeze beginner/advanced multi-agent API, operation distinctions,
   default ownership/budget rules, sync/async symmetry, and public-surface
   budget in an ADR.
3. [complete] Extend `ToolResult` in place with strict JSON-owned attempt,
   effect, retry, reconciliation, uncertainty, late-result, stale-owner, and
   partial-batch facts while preserving current v1 compatibility.
4. [complete] Add strict `WorkGraph` records, generation compare-and-set rules,
   snapshot component, typed failures, and compatibility adapters/retirement
   ledger without runtime scheduling behavior.
5. [complete] Add stable fixtures under `tests/fixtures/tool_results/` and
   `tests/fixtures/work_graph/` plus strict read/write, isolation, generation,
   duplicate-completion, redaction, and golden API-shape tests.
6. [complete] Publish Lane C evidence: vocabulary, retry/reconciliation rules,
   quiescence matrix, fixture manifest/digests, producer identity, A/B/D
   consumer instructions, unsupported claims, and known gaps.
7. [complete] Run all required targeted/static/full validation, review the diff,
   make coherent commits, and report the final clean HEAD.

## Cross-lane status

- Lane A owns session identity, snapshot envelope, head generation, and resolver
  reference types. Current status: producer not yet consumed; qualification
  disposition is `waiting_on_lane_a`.
- Lane B owns ExchangeLog, RequestView, and context/continuation transfer
  schemas. Lane C stores only an opaque `context_transfer_ref`.
- Lane D consumes exact fixture bytes and producer evidence; it must not infer
  lineage or trust an unbound success flag.

## Verification ledger

Validation completed without masked exits or rerun-only success:

- targeted contract/runtime matrix: 419 passed, 4 skipped;
- static-quality ratchet: 399 baseline findings (377 active, 22 vendored);
- stable flake8: clean;
- stable mypy: 78 source files clean;
- full suite: 1897 passed, 50 skipped;
- final diff/status checks are recorded in the producer evidence.
