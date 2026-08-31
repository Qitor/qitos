# S3-R and G4 convergence evidence

Status: deterministic and repository candidate qualified; live-model
qualification blocked by configuration; not promoted
Updated: 2026-09-01
Fixed baseline: `851f7902f15da670e72f4c04d7453cf37201aee7`
Candidate branch: `codex/v4-s3-g4-convergence`

## Disposition

The A -> B -> C -> D replay and deterministic G4 process-loss gate qualify a
local candidate. The user supplied no explicit provider, model, credential
source, budget, network permission, or tool policy. Therefore
`live_model_qualification=blocked_configuration`, and promotion, push,
default-branch readiness, release claims, and worktree cleanup are prohibited.

Candidate Trajectory remains unfrozen and off by default. Frozen trace-v1
remains qita's default reader. The candidate does not claim distributed
scheduling, hard cancellation, or exactly-once external effects.

## Baseline and source identity

Before replay, local integration HEAD, its tracking ref, and the remote branch
were all verified at the fixed baseline with divergence `0/0`. The primary and
four producer worktrees were clean. The producer source heads were:

| Lane | Source branch | Verified source head |
|---|---|---|
| A | `codex/v4-s3-a-session-fork` | `9442647767bc9a7c45ed3bf07bc4f289412544ed` |
| B | `codex/v4-s3-b-transfer-authority` | `5efa1db19ae541234c562c4ba99e928d2381fc62` |
| C | `codex/v4-s3-c-durable-work-runtime` | `12edf48aa5dd2ed7c3c830baf9031116474bcc52` |
| D | `codex/v4-s3-d-graph-observability` | `ca620cdc8e9ad86bb196bdba482ebfde237784c3` |

## Strict replay and repair ledger

| Stage | Source | Integrated result | Evidence |
|---|---|---|---|
| A1 | `ae62ba1ea5fef7a472609dcb11d23a5f21733410` | `bc91a6e` | 48 focused passes |
| A2 | `feba1bf6d2312b82c7f03ce0b3c1f07e50712938` | `6635a0a` | 15 focused passes |
| A3 | `a94d4598bfdc9cafb2df30048e534533dca27e47` | `1e2de5d` | 15 focused passes |
| A4 | `ea8076c9d78742b25e2516fa610afac1ba9cfc2a` | `9ab7799` | 16 focused passes |
| A5 | `9442647767bc9a7c45ed3bf07bc4f289412544ed` | `1025f121d6de7fd3cff9e71558de44df3d36134a` | 28 fork/checkpoint/process passes |
| B1 | `b229e0b80a55a1add64fdb88fbe5b632f8d15ad8` | `a31284f` | 38 focused passes |
| B2 | `5efa1db19ae541234c562c4ba99e928d2381fc62` | `04caa1f` | 38 focused passes |
| B repair | stale manifest digest | `8bbfd6580e03f77f51777e696d78ee783bc09f75` | 216 passes plus committed-byte verifier |
| C1 | `72c9372412d6791f107de63b7f02d13dd549f94c` | `ceb103f` | 16 focused passes |
| C2 | `9c39b3fdfcaff4dd33fc73a55a464927d1f58bca` | `ab82928` | 65 integrated passes |
| C3 | `12edf48aa5dd2ed7c3c830baf9031116474bcc52` | `ef415f8` | stale waiting evidence rejected as expected |
| C runtime repair | real A/B consumption | `66a0e535d28c89f05bb4577eb343142289c8b412` | 107 passes plus focused lint/type |
| C join repair | typed all-successful failure | `b4e4d8542d29dcbd07d7b063bbcd2b5e4761c545` | 30 focused passes |
| C evidence | exact integrated manifest | `336ede9db49d0d1ff20fe7668017bdae7712fccd` | 88 passes plus 369-finding ratchet |
| C state repair | declaration-before-preparation | `291108655ba602c7aebcaad4419d89c1386c2edc` | separate dispatchable commit; pre/post handoff ownership tests |
| C final evidence | refreshed integrated manifest | `733e45b765a0fd66ad674bf664cd3af4022c4284` | binds final runtime and process-crash bytes |
| C admission repair | uncommitted admission rollback | `9815726bbf5500772d54ccb62503c2f469117105` | restores last durable dispatchable fact |
| C final binding | final crash-state manifest | `e9b6fe68d5549ca8d798ad5c112224b358144bfb` | exact final runtime/test/plan/evidence bytes |
| D1 | `1c5e2ae6c49eb0eba2ec4afa3d793d74c9179333` | `012a2978e75d9490c0fa3e15c30dee6ad355c55f` | 7 focused passes |
| D2 | `99137d0fed6177e7575f3171c0f349e054d3a390` | `d42a5eef3e264baf48a443f1a691cd1f1edb48a4` | 3 focused passes |
| D3 | `882eec1ad4f1b27b23e19c6a3223b47c5e8b0426` | `1788e7c242b68ec8fb2646258db02d9b46a75aed` | 2 consumer passes |
| D4 | `ca620cdc8e9ad86bb196bdba482ebfde237784c3` | `ca9c03a824dec30169fd25ded0f7c5a86700a300` | 12 focused passes |
| D repair | exact source/replay separation | `7f3a809a0eeefd90883aa87654da7e1aa5a2d6ef` | 47 passes; D qualifier ready |
| G4 | deterministic process loss | `163cda22a9d8518eaf016d5d2cca6dccc9be2112` | 20 independent database rounds |

Replay conflicts were limited to Git's clean automatic merge of A additions in
C's runtime/session-runtime files; no semantic conflict was resolved by copying
producer contracts. B and C cross-lane defects were repaired on the convergence
branch and their committed evidence was refreshed before D qualification.

## Runtime qualification facts

- Every default durable operation gets a fresh identity; idempotent retry
  requires an explicit operation ID.
- The parent operation declaration is committed before child/transfer
  preparation; preparation is committed as `dispatchable` before dispatch.
  Recovery reuses an already committed fork receipt rather than creating a
  second child.
- Work descriptors are reconstructable JSON-only records and persist real
  Session fork and ContextTransfer receipts before scheduler dispatch.
- Queue admission is bounded and recoverable; eligible queued work retains its
  identity, while a missing running worker becomes `outcome_unknown` and is not
  automatically replayed.
- Handoff transfers one work item's owner and fences the superseded owner;
  delegate, spawn, fan-out, and join retain distinct graph semantics.
- `all`, `all_successful`, `first_success`, and quorum joins close
  deterministically; duplicate and late results cannot mutate a closed join.
- Cancellation propagation, request-and-wait, detachment, capabilities,
  budgets, and safe descriptor projection are explicit persisted facts.
- Direct Session calls and model-callable durable adapters use the same runtime
  protocol and descriptor shape.

## Deterministic G4 receipt

The test creates a parent Session, completed/queued/running children, a partial
fan-out, a direct spawn, a model-callable spawn, a quorum join, all three
cancellation policies, one detachment, and one handoff. It then terminates the
original process with `os._exit(0)`, composes a fresh store/resolver/runtime,
restores, recovers only the eligible queued operation, and checks closed-join
behavior and read-only qita graph/timeline inspection without ID or path
inference.

Twenty independent SQLite graph databases and twenty additional
declaration/preparation-crash databases passed. Every graph round had a unique Session
ID, one owner transfer, fan-out width two, two accepted join outcomes, one late
discarded outcome, join generation two, and secret-free descriptors. No sleeps,
live model, masked exit, or unavailable-test skip is used.

## Exact D producer bindings

| Contract | Immutable source head | Executed producer commit | Manifest digest |
|---|---|---|---|
| A fork/ownership | `9442647767bc9a7c45ed3bf07bc4f289412544ed` | `1025f121d6de7fd3cff9e71558de44df3d36134a` | `4a01a329ccfd7b114f35fbd84703f14cba623e31504cd9441c835e43f6506a56` |
| B context/authority | `5efa1db19ae541234c562c4ba99e928d2381fc62` | `8bbfd6580e03f77f51777e696d78ee783bc09f75` | `62db8bb77d0e4e20fc1871d3bfd12570bf311fb517a84895639c4cc709703bd6` |
| C durable runtime | `12edf48aa5dd2ed7c3c830baf9031116474bcc52` | `e9b6fe68d5549ca8d798ad5c112224b358144bfb` | `deb2e67658bd0d6645904714ae6d98a17c2dbce2fa8b31699cb6300a3203ce28` |

The D qualifier reports `s3_lane_d_qualified`, all three producers, 31
executable scenarios, no findings/blockers, `schema_frozen=false`,
`writer_default=frozen_trace_v1_unchanged`,
`qita_reader_default=frozen_trace_v1_compatibility`, and
`publication_ready=false`.

## Quality and packaging gates

- integrated focused matrix: 278 passed, including fork, ContextTransfer,
  WorkGraph atomicity, WorkRuntime, checkpoint conformance, S2/G4 clean-process,
  handoff/delegate/spawn/fan-out/join, tracing/qita/privacy/readiness,
  consumers, documentation, architecture, and interface budgets;
- deterministic G4: 20 graph process-loss rounds plus 20
  declaration/preparation-crash rounds passed;
- fixed Python 3.12.7 static ratchet: passed with 369 baselined findings (347
  active, 22 vendored/generated);
- stable flake8: clean; stable mypy: 93 source files, no issues;
- full fixed-environment suite: 2349 passed, 50 skipped;
- public/interface budgets: 41/27/24/28/22/101/34, no delta;
- coding-agent example: exactly 88 non-comment code lines and
  `qualified_public_shape` completion;
- package: `qitos-0.6.0.tar.gz` and `qitos-0.6.0-py3-none-any.whl` built;
  twine passed both artifacts;
- D exact-source qualifier: `s3_lane_d_qualified`, three producers, 31
  executable scenarios, zero blockers/findings; and
- no-local-path, documentation parity, diff, and secret gates: passed.

The first default-Python 3.13 package invocation could not import `build`, and
its full suite lacked `cookiecutter` for two CLI tests (2342 passed, 50 skipped,
2 environment failures). The complete package and full test commands were then
run from scratch—not failure-only reruns—under the repository's fixed Python
3.12.7 quality environment, where the dependencies are installed, with the
passing results above.

Promotion remains blocked independently by the missing live configuration even
though every deterministic, repository, and package gate passes.

## Live-model gate

Status: `blocked_configuration`.

Required but absent inputs are an explicit provider and model, credential
source, cost/token/time budget, network permission, and tool policy. The
integration owner did not inspect or infer credentials from the environment and
did not spend external budget. This typed block is not a test failure, but it is
a mandatory promotion blocker under the requested gate policy.
