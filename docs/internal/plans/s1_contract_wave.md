# S1 contract wave plan

Status: blocked pending G1-R4 forced-secret scalar closure
Updated: 2026-08-29
Owner: v4 integration owner
Source gates: [`docs/progress.md`](../../progress.md) and
[`docs/v4/11-four-lane-execution-playbook.md`](../../v4/11-four-lane-execution-playbook.md)

## Objective

Freeze the minimum versioned contracts needed for QitOS to support durable,
process-independent sessions and a native multi-agent work graph without
starting runtime behavior prematurely. S1 is an architecture/fixture wave, not
an authorization to add a second Engine, SessionStore, result envelope, trace
schema, provider default, or distributed scheduler.

## Dispatch gate

Do not create S1 implementation branches from
`587f34b76245e71fe3362a51dbad40895d7c43c5` or the pre-repair
`acb491bd822baf6ca429e81639aadbde72a626f0`. G1-R3 has now established the
later accepted baseline reported by the integration owner, containing:

- the C-P3 sensitive-key and omitted-key projection repair;
- B's canonical consumer requalification;
- refreshed D producer receipts when fixture/evidence bytes changed;
- the pinned 399-finding ratchet, stable flake8/mypy, adversarial projection
  probes, targeted cross-lane suites, full suite, both readiness modes, and
  `git diff --check` passing on the combined tree;
- a clean three-worktree fast-forward and explicit **G1 CLOSED** decision in
  `docs/progress.md` and the final integration report.

The R3 authorization is superseded by C-P4 review. No S1 branch may be created
until the integration owner reports the new scalar-safe R4 baseline SHA after
all gates and three fast-forwards. That later authorization will remain limited
to each lane's first contract package.

## Shared contracts

All four packages use these rules:

1. persistent records contain identifiers, data, and resolver references, never
   live clients, locks, futures, threads, credentials, or Python stacks;
2. session, run, work item, checkpoint, exchange, tool call, agent, and attempt
   identities remain distinct and versioned;
3. checkpoint v2 is the only durable session truth; `RunState` receives an
   adapter/retirement decision rather than becoming a competing store;
4. one canonical `ToolResult` represents local tool and child-work outcomes;
5. every snapshot component states ownership, version, required/optional fields,
   migration behavior, redaction boundary, and missing-reference failure;
6. `handoff`, `delegate`, `fan_out`, `spawn`, `fork`, `steer`, and `join` retain
   distinct ownership semantics;
7. no behavior package starts until the relevant producer fixtures are reviewed
   and consumed by a second lane.

## Lane A — 12A session identity and snapshot contract

Owner: Engine session lifecycle and checkpoint-v2 composition.

Deliver:

- exact census of `init_session`, `RunState`, checkpoint v1/v2,
  interrupt/resume, trace/run IDs, qita fork, task/state construction, and
  resolver boundaries;
- ADR defining session/head generation, lifecycle states, safe boundaries,
  immutable snapshot identity, optimistic head commit, pause, restore, and fork;
- versioned snapshot fixtures covering running, safely paused, partial parallel
  batch, failed persistence, superseded owner, clean restore, and isolated fork;
- component slots for B's ExchangeLog/context and C's effect/quiescence facts;
- typed failures for missing resolver, unsupported component version,
  generation conflict, unsafe pause, corrupt snapshot, and unavailable secret;
- compatibility decision for `RunState`, checkpoint v1, and current resume APIs.

Do not implement Engine behavior, add root exports, serialize live objects, or
create another session/checkpoint store in 12A.

Handoff: publish the exact identity vocabulary and snapshot envelope that B/C/D
fixtures must consume.

## Lane B — 02B RequestView and continuation contract

Owner: persistent conversation facts and provider-facing request construction.

Deliver:

- versioned `RequestView` and `CodecReport` fixtures derived from ExchangeLog;
- explicit provider/transport/API-mode capability inputs and loss reporting;
- queued steering semantics: accepted while work is unsafe, applied exactly once
  at the next declared boundary, and durably represented across restore;
- snapshot component for ExchangeLog, opaque continuation references, context
  selection, compaction facts, and ArtifactRef references;
- typed provider failure boundary proving failures cannot become assistant text;
- independent reader test consuming Lane A's snapshot envelope.

Do not add a conversation-owned session store, switch provider defaults, call
live models, or persist clients/secrets/raw host paths.

Handoff: publish immutable conversation/context components and selected/omitted/
loss facts for A, C, and D.

## Lane C — recovery/effect contract and 13A work-graph ADR

Owner: canonical outcome recovery, quiescence, and multi-agent ownership.

Deliver:

- complete attempt/effect/idempotency/reconciliation vocabulary on canonical
  ToolResult, including `outcome_unknown` and `worker_still_running`;
- safe-boundary matrix for model calls, threads, subprocesses, HTTP/MCP clients,
  background checkpoint work, and partial parallel tool batches;
- census of current handoff/delegate/fan-out paths and nested Engine behavior;
- 13A ADR and versioned fixtures for work item, ownership generation, parent/
  child edge, transfer, delegation, spawn, fan-out, join, cancellation,
  detachment, late result, and budget/capability allocation;
- independent consumer test using Lane A identities and B context-transfer facts.

Do not implement child scheduling, nested-engine replacement, hard thread
cancellation, distributed execution, or role/strategy policy in S1.

Handoff: publish effect/quiescence and work-graph fixtures for A recovery and D
lineage intake.

## Lane D — session/work lineage intake

Owner: evidence/readiness and future trace/qita consumption, not runtime truth.

Deliver:

- extend the reader/writer census for session, head generation, checkpoint,
  work item, ownership transfer, child/join, pause/restore, and uncertainty;
- readiness contract IDs for every A/B/C producer fixture and exact receipt
  rules consistent with the G1 producer-owned evidence model;
- proposed trajectory lineage fields and loss declarations, clearly marked
  unfrozen;
- fixtures proving missing, unknown, stale, conflicting, and qualified producer
  receipts clear only their owned blocker;
- dual-read/qita implications and compatibility risks without adding writers.

Do not freeze trajectory v2, materialize private fixtures, claim compression or
performance gains, infer graph edges from naming conventions, or change qita.

Handoff: publish the G2 readiness matrix and unresolved lineage blockers.

## Leases and merge order

High-conflict files are integration-owner leases:

- `qitos/core/tool_result.py` — Lane C;
- `qitos/core/conversation.py` — Lane B;
- checkpoint/session contract files — Lane A;
- trajectory manifest/readiness files — Lane D;
- `README.md`, `README.zh.md`, `CHANGELOG.md`, `docs/progress.md`, and shared v4
  status sections — integration owner.

Preferred acceptance order:

1. Lane A identity vocabulary and snapshot envelope;
2. Lane C effect/ownership vocabulary against A identities;
3. Lane B RequestView/snapshot component against accepted A/C contracts;
4. Lane D exact producer intake against accepted A/B/C fixtures;
5. integration-owner G2 contract qualification.

Agents may work concurrently after A publishes a reviewed draft, but consumers
must rebase on accepted producer commits; copied enums or fixture shapes do not
count as a handoff.

## G2 exit criteria

- [ ] One reviewed identity matrix distinguishes every runtime and persistence
      identity.
- [ ] One immutable snapshot envelope has versioned A/B/C components and typed
      compatibility behavior.
- [ ] Safe pause and restore preconditions are explicit for every owned
      resource class.
- [ ] Partial parallel results, steering, effects, and uncertain outcomes have
      durable representations without claiming exactly-once execution.
- [ ] Work ownership, transfer, children, joins, cancellation, and stale-owner
      rejection are versioned and unambiguous.
- [ ] D consumes exact producer-owned fixtures and keeps trajectory v2 unfrozen.
- [ ] Two independent consumers exercise each cross-lane contract.
- [ ] Ratchet, lint/type, architecture/public surface, targeted suites, full
      suite, docs parity, privacy/local-path checks, and diff checks pass.
- [ ] `docs/progress.md` records exact accepted commits and authorizes S2.

## Stop conditions

Stop and return to the semantic owner if a package requires a second canonical
store/result/trace, a root API decision, serialization of a live object or
credential, a provider-default change, an unverifiable exactly-once claim, or a
behavior change outside its S1 contract scope.
