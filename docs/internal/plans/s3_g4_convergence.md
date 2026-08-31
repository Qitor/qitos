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
| A | `ae62ba1ea5fef7a472609dcb11d23a5f21733410` | `bc91a6e` | none | 48 passed: fork + Session contract |
| A | `feba1bf6d2312b82c7f03ce0b3c1f07e50712938` | `6635a0a` | none | 15 passed: fork producer bundle |
| A | `a94d4598bfdc9cafb2df30048e534533dca27e47` | `1e2de5d` | none | 15 passed: fork producer bundle |
| A | `ea8076c9d78742b25e2516fa610afac1ba9cfc2a` | `9ab7799` | none | 16 passed: cross-process owner fencing |
| A | `9442647767bc9a7c45ed3bf07bc4f289412544ed` | `1025f12` | none | 28 passed: fork + checkpoint + clean-process restore |
| B | `b229e0b80a55a1add64fdb88fbe5b632f8d15ad8` | `a31284f` | none | 38 passed: ContextTransfer contract |
| B | `5efa1db19ae541234c562c4ba99e928d2381fc62` | `04caa1f` | none | 38 passed: ContextTransfer producer bundle |
| B repair | confirmed bad manifest digest | `8bbfd6580e03f77f51777e696d78ee783bc09f75` | corrected plan digest and refreshed all changed producer bytes; added commit/path/digest/test-node verifier | 216 passed; Python 3.12.7 static ratchet passed |
| C | `72c9372412d6791f107de63b7f02d13dd549f94c` | `ceb103f` | none | 16 passed: atomic WorkGraph mutations |
| C | `9c39b3fdfcaff4dd33fc73a55a464927d1f58bca` | `ab82928` | auto-merged A additions in `runtime.py` and `session_runtime.py`; no manual conflict | 65 passed: C runtime + A fork + B transfer |
| C | `12edf48aa5dd2ed7c3c830baf9031116474bcc52` | `ef415f8` | none; original waiting evidence intentionally failed its stale digest assertion | 10 passed, 1 expected exact-source evidence failure before repair |
| C repair | integrated A/B durable runtime | `66a0e535d28c89f05bb4577eb343142289c8b412` | replaced digest-derived IDs and callable scheduler contract; consumed real fork/transfer receipts | 107 passed; focused flake8/mypy passed |
| C join repair | all-successful typed terminal failure | `b4e4d8542d29dcbd07d7b063bbcd2b5e4761c545` | no conflict | 30 passed: WorkGraph/runtime/process restore |
| C evidence | integrated exact-source qualification | `336ede9db49d0d1ff20fe7668017bdae7712fccd` | refreshed manifest/digests/nodes and shrank ratchet baseline | 88 passed; Python 3.12.7 ratchet passed with 369 findings |

## Gate policy

Promotion and push are prohibited unless deterministic G4, the required live
matrix, the complete quality/package gates, worktree cleanliness, baseline
stability, and remote stability all pass. With no explicit live matrix this
branch remains a clean candidate; no source worktree is removed.
