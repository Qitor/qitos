# S2 G3 runtime vertical convergence evidence

Status: S2 runtime closed, promoted, pushed, and cleaned up; Trajectory
schema/publication remains blocked

Updated: 2026-08-31

## Integration identity and replay

The clean integration source, local tracking ref, and remote ref were all
`47cd4dc5e1ed1b2b0d244bfc90fac031ec55be32` with `0/0` divergence. The G3
worktree was created directly from that SHA. Replay order and identities:

| Lane | Source | Replay |
|---|---|---|
| A | `bc725e8b77576a7a0b5c165a5066c83c4d9965c8` | `110238aa6b4ea52ed3f01bd81ae768dd8bd04cc7` |
| A | `a075ea6e1e18064a79866a6f4cadecdb7536c746` | `f56d59c6d0897433b125d5b700dfd1fee8d21360` |
| C | `769422d4d6b5dfd0552fbe98a34def1885786848` | `2b61cd8fb601246d8758d409b084837a34c07436` |
| C | `c63917ab48aff65b3e5df615ea947ab183653d97` | `e6e450deb56c228a1f28a13e1b1b4b5340b2e662` |
| C | `6a8ff24ede400a549e1f3dafa593a23e61b845f3` | `ab255b333585cbf827127bbc800609f32363c478` |
| B | `60e8d94edb9a5f00434095a3489e1e1100185bea` | `25af41fa65886ff2fdf7e82094749e67681be4cc` |
| B | `0c7bde6ddb5ff2a61116793274ec706666d91e0f` | `cabb9e543c40d1ab783e6f6ddd85c27dad5a933a` |
| D | `f8f63b2e6dd29fd98135c644b2964c0814551749` | `f569db44a51fd6015156bc7b5b33168ea192c5df` |
| D | `c034988a628881b55630f6a149c6b40a9a619070` | `7308f1cfe2149ae601e485d8eab936e7309abe79` |

The only replay conflict was `quality/static_baseline.json`. It was resolved by
regenerating from the joint tree, not by selecting A or D wholesale.

## Pre-fix joint baseline

- full suite: `2242 passed, 50 skipped`;
- combined S2 contract group: `219 passed`;
- static quality: `376 total / 354 active / 22 vendored-generated`;
- stable flake8: clean;
- stable mypy: clean on 90 source files;
- architecture/public/no-local-path: `10 passed`;
- root exports: 41.

## Convergence receipts

- canonical ArtifactRef: only `qitos/core/artifact.py::ArtifactRef` remains;
- conversation: the Lane B codec is captured/restored by the private
  Engine-owned component in `qitos/engine/_snapshot_components.py`;
- tool batch: terminal slots become Session components and advance the one head
  by owner/generation CAS before persistence publication;
- pause: ActionExecutor receives the request and the condition/event barrier
  must report migratable before a synchronous `PAUSED` head is committed;
- recovery: the original decision/batch is restored before model I/O, terminal
  or committed slots are skipped, unknown outcomes are refused, and only safe
  missing slots execute;
- observability: one public EventSink seam receives explicit Session and Engine
  facts; candidate Trajectory writers remain opt-in and qita default remains
  trace-v1 compatibility;
- API: root remains 41; the S2/current aggregate budget classifies 101 exports;
  Engine has 34 parameters including `self`, with `runtime` approved as a
  migration bridge and a documented contraction route.

## Exact-source runtime qualification

Producer commit:
`42d6821e4ceee7a09d3dda9011e687a8cb64f5ba`.

The receipt set binds the committed integrated fixture and three committed
qualification documents by SHA-256. `scripts/qualify_s2_lane_d.py --json`
returns:

- status `s2_runtime_ready`;
- `s2_runtime_ready=true`;
- qualified lanes A, B, C;
- all twelve required scenarios;
- zero findings;
- `trajectory_schema/publication_ready=false`;
- `qita_store_reader_default=false`;
- no measurements or claims.

## Controlled failures

| Required proof | Executable evidence |
|---|---|
| stale generation cannot commit | `tests/checkpoint/test_session_head.py` |
| superseded owner / late parent cannot advance restored head | `tests/test_s2_g3_convergence.py` and the subprocess child |
| committed effect is not replayed | `test_recovery_does_not_replay_committed_effect` plus the 20-round counter |
| outcome unknown is not retried | `test_recovery_refuses_outcome_unknown_automatic_retry` |
| missing continuation fails typed; explicit replay records loss | `test_unresolved_continuation_rejects_or_records_explicit_stateless_loss` |
| running worker cannot persist pause | `tests/test_tool_lifecycle_conformance.py` and G3 control sink |
| required/optional sink failures | `tests/test_event_sink_conformance.py` |
| malformed component schema | `tests/core/test_session_contract.py` |
| duplicate ArtifactRef implementation | `test_framework_has_one_artifact_ref_implementation` |
| candidate Trajectory aggregate export | `test_candidate_trajectory_is_not_an_aggregate_public_export` |
| unclassified aggregate export | `test_every_s2_aggregate_export_is_classified_once` |

## Authoritative subprocess proof

`tests/e2e/test_s2_g3_runtime_vertical.py` runs twenty independent rounds. Each
round starts a parent Python process with SQLite, an offline provider returning
reasoning/continuation/three parallel calls, a committed-effect counter, and a
deterministic Event barrier. The persisted head contains two terminal slots and
one eligible missing slot; the parent exits. A clean child resolves resources,
rejects the old owner CAS, restores continuation/steering/artifact/budget/cursor
facts, executes only the missing slot, reduces the original decision once, and
completes. Every final counter is `1/1/1`; duplicate committed effects are zero.

## Final validation ledger

The qualified branch matrix completed with:

- full suite: `2252 passed, 50 skipped`;
- requested combined S2 suites: `221 passed`;
- authoritative 20-round parent/child E2E: `1 passed`;
- static update: `removed 0, added 0, total 376`;
- static check: `376 total / 354 active / 22 vendored-generated`;
- stable flake8: clean;
- stable mypy: clean on 91 source files;
- architecture/public/no-local-path: `10 passed`;
- privacy/credential/host-path adversaries: `40 passed`;
- S2 interface gates: `4 passed`, with 41 root exports, 101 classified
  aggregate exports, and 34 Engine parameters including `self`;
- exact-source D qualification: all 12 scenarios, zero findings,
  `s2_runtime_ready=true`;
- independent schema/publication proof: `1 passed` and
  `trajectory_schema/publication_ready=false`;
- package build: sdist and wheel built; twine accepted both;
- `git diff --check`: clean.

### Promotion receipt

Historical pre-promotion note (superseded): primary-checkout rerun, remote
verification, and worktree-retirement receipts were expected to belong to the
final integration report after they occurred.

Those operational steps are now completed: `feat/campaign-absorption` was
fast-forwarded, the required primary-checkout gates passed, and the branch was
pushed normally. Local HEAD, tracking ref, and remote ref were verified at
`3af0ee3b2c3b5b5575e4e07cc31ff7f652327ba7` with `0/0` divergence. The G3
worktree was clean and retired without force while its branch/commit refs were
preserved; only the primary worktree remained before S3 dispatch closure began.
No live model, provider key, deployment, or remote-runner access is part of this
evidence.

## Explicitly unsupported

- Trajectory schema freeze, publication readiness, default writer, or qita
  migration;
- compression/index/dedup or performance gains;
- persistent child scheduler or S3 multi-agent continuity;
- beginner agent-authoring constructor sugar;
- exactly-once external effects without backend proof.
