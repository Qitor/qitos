# S3 G4 convergence plan

Status: in progress
Updated: 2026-09-01
Owner: G4 integration owner
Fixed source: `851f7902f15da670e72f4c04d7453cf37201aee7`
Branch: `codex/v4-s3-g4-convergence`

## Objective

Replay the four S3 producer lanes in the fixed A -> B -> C -> D order, repair
exact-source evidence and cross-lane runtime semantics, and qualify the
deterministic G4 process-loss gate without changing trace-v1/qita defaults or
claiming unsupported distributed/exactly-once behavior.

## Fixed identities

| Lane | Branch | Verified head |
|---|---|---|
| A | `codex/v4-s3-a-session-fork` | `9442647767bc9a7c45ed3bf07bc4f289412544ed` |
| B | `codex/v4-s3-b-transfer-authority` | `5efa1db19ae541234c562c4ba99e928d2381fc62` |
| C | `codex/v4-s3-c-durable-work-runtime` | `12edf48aa5dd2ed7c3c830baf9031116474bcc52` |
| D | `codex/v4-s3-d-graph-observability` | `ca620cdc8e9ad86bb196bdba482ebfde237784c3` |

The integration repository, tracking ref, and remote ref were all verified at
the fixed source with divergence `0/0`. The main and four source worktrees were
clean before this convergence worktree was created.

## Execution sequence

- [ ] Replay A's five commits and run focused validation after each replay.
- [ ] Replay B's two commits, recompute every producer digest, repair its
  manifest/evidence, and add executable manifest binding verification.
- [ ] Replay C's three commits and replace independent placeholders with real A
  fork/lineage and B transfer/authority consumption.
- [ ] Repair operation identity, reconstructable descriptors, queued recovery,
  crash-window state transitions, ownership, joins, cancellation, and direct /
  model-callable parity.
- [ ] Replay D's four commits and refresh exact-source bindings and executable
  readiness over the integrated bytes.
- [ ] Add and run the bounded SQLite subprocess G4 scenario for at least twenty
  independent rounds.
- [ ] Run consumers, coding-agent acceptance, qita/privacy/readiness, interface
  budgets, static/lint/type, full pytest, package, diff, and secret gates.
- [ ] Update shared documentation and publish exact qualification evidence.
- [ ] Record live-model qualification as blocked configuration unless an
  explicit provider/model/credential/budget/network/tool matrix is supplied.

## Replay ledger

Each row is completed immediately after replay and focused validation.

| Lane | Source SHA | Replay SHA | Conflict / resolution | Focused validation |
|---|---|---|---|---|

## Gate policy

Promotion and push are prohibited unless deterministic G4, the required live
matrix, the complete quality/package gates, worktree cleanliness, baseline
stability, and remote stability all pass. With no explicit live matrix this
branch remains a clean candidate; no source worktree is removed.
