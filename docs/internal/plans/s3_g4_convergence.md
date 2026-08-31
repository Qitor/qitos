# S3 G4 convergence plan

Status: deterministic and repository candidate qualified; live profiles
configured; budget approval and execution pending; not promoted
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

- [x] Replay A's five commits and run focused validation after each replay.
- [x] Replay B's two commits, recompute every producer digest, repair its
  manifest/evidence, and add executable manifest binding verification.
- [x] Replay C's three commits and replace independent placeholders with real A
  fork/lineage and B transfer/authority consumption.
- [x] Repair operation identity, reconstructable descriptors, queued recovery,
  crash-window state transitions, ownership, joins, cancellation, and direct /
  model-callable parity.
- [x] Replay D's four commits and refresh exact-source bindings and executable
  readiness over the integrated bytes.
- [x] Add and run the bounded SQLite subprocess G4 scenario for at least twenty
  independent rounds.
- [x] Run consumers, coding-agent acceptance, qita/privacy/readiness, interface
  budgets, static/lint/type, full pytest, package, diff, and secret gates.
- [x] Update shared documentation and publish exact qualification evidence.
- [x] Register the three supplied provider/model routes using endpoint-specific
  credential references; never persist credential values.
- [ ] Accept a bounded request/token/time budget, run the common capability
  preflight plus trajectory and disposable-agent scenarios, and publish only
  sanitized executable receipts.

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
| C state repair | declaration-before-preparation crash convergence | `291108655ba602c7aebcaad4419d89c1386c2edc` | added declared -> prepared -> dispatchable state and reusable fork recovery; verified handoff pre/post commit ownership | 18 focused passes; 20 graph rounds plus 20 preparation-crash rounds |
| C final evidence | refreshed exact integrated manifest | `733e45b765a0fd66ad674bf664cd3af4022c4284` | rebound changed runtime/tests and new process scenario | C and D executable manifest gates passed |
| C admission repair | failed queue/reject receipt persistence | `9815726bbf5500772d54ccb62503c2f469117105` | rollback to last durable dispatchable fact | 16 focused work-runtime passes |
| C final binding | crash-state producer manifest | `e9b6fe68d5549ca8d798ad5c112224b358144bfb` | rebound final runtime, tests, plan, and evidence | C and D executable manifest gates passed |
| D | `1c5e2ae6c49eb0eba2ec4afa3d793d74c9179333` | `012a2978e75d9490c0fa3e15c30dee6ad355c55f` | none | 7 passed: work-graph reader |
| D | `99137d0fed6177e7575f3171c0f349e054d3a390` | `d42a5eef3e264baf48a443f1a691cd1f1edb48a4` | none | 3 passed: exact-source readiness |
| D | `882eec1ad4f1b27b23e19c6a3223b47c5e8b0426` | `1788e7c242b68ec8fb2646258db02d9b46a75aed` | none | 2 passed: independent consumers |
| D | `ca620cdc8e9ad86bb196bdba482ebfde237784c3` | `ca9c03a824dec30169fd25ded0f7c5a86700a300` | none | 12 passed: final blocked evidence |
| D repair | integrated exact-source qualification | `7f3a809a0eeefd90883aa87654da7e1aa5a2d6ef` | bound source heads separately from replay/repair bytes; completed public-shape example | 47 passed; qualifier `s3_lane_d_qualified` |
| G4 | deterministic clean-process convergence | `163cda22a9d8518eaf016d5d2cca6dccc9be2112` | added bounded abrupt-exit create/restore fixture | 20 independent database rounds passed |

## Gate policy

Promotion and push are prohibited unless deterministic G4, the required live
matrix, the complete quality/package gates, worktree cleanliness, baseline
stability, and remote stability all pass. Three routes are now registered in
`s3_g4_live_model_matrix.md`, but their credentials remain external and the
bounded execution budget has not been accepted. This branch therefore remains
a clean candidate; no source worktree is removed.
