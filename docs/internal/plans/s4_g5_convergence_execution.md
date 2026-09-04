# S4 G5 convergence execution

Status: in progress; not qualified; no promotion authorized until all gates pass.

## Source lock

Baseline: `306e689ab19665678b6de644045d374c5ec05102`.
Common ancestor: `c4e621d05960a4e2f06cb4864f6a8cb8275ac067`.
Primary branch: `feat/campaign-absorption`; clean and exact at task entry.
Integration branch: `codex/v4-s4-g5-convergence`, created from baseline.
Four source worktrees were independently clean with exact branch/HEAD and
merge-base before replay. The C manifest SHA-256 is
`80f3db9514791738f699932e17a2dfab80c6190d1083d388493fa2bc523d6a49`.

| Lane | Fixed HEAD | Count |
| --- | --- | ---: |
| A | `f670e551f0bd5d88501182c2d24a5037fa0aebb9` | 5 |
| B | `c834ce76b939e86b33019719d5b212b1c7a38bdd` | 7 |
| C | `a1958fe620f9a80017d80aca702711991b80c8e6` | 10 |
| D | `18278bd42ea91284f76f2d4523f82d316cc20a75` | 7 |

## Execution sequence

1. Replay 29 commits A → B → C → D; resolve overlap semantically and recount interfaces.
2. Commit reproducible failing audit regressions, then fix C1/C2, A1/A2, B1, D1/D2/D3.
3. Complete composition, sandbox, artifact, Session/work, and Trajectory bindings.
4. Requalify historical/current facts and two independently installed consumers.
5. Qualify real Docker serially, full suite, quality, packaging matrix, measurements.
6. Freeze schema, switch writer and reader in distinct commits only after prerequisites.
7. Verify candidate, fast-forward local primary, repeat required primary gates.
8. Retain all worktrees/refs and record retirement inventory. No remote writes.

## Toolchain

Verified Python 3.12.7 at the requested interpreter; metadata: flake8 7.0.0,
mypy 1.19.1, pyflakes 3.2.0, pycodestyle 2.11.1, mccabe 0.7.0.
Additional installed tools: pytest 9.0.3, build 1.3.0, twine 6.2.0.
No shared environment was modified.

## Replay mapping (source → replay)

| Lane | Source SHA | Replay SHA |
| --- | --- | --- |
| A | `315f33f8476a9de5a9afbaaea8cede9c0624f63e` | `1938ea21acec891bc5b46c3c84cfd515fa317b5c` |
| A | `c3989afb5995d88d022ea9774398fb5b1396111c` | `aaeff0a0ce2f0d8f970ba1bb64741e460621efd5` |
| A | `bdaa8be1e49722c2cf647ee6f784493132ed29d8` | `442b7fa8ad9ef7c73768f8aa056f59cbb0aa8aa8` |
| A | `65718ee782065e7dccc3b3d0a5e7ea9a318b5411` | `839e6456d1acde999b0b680c47dce3cd1e219a18` |
| A | `f670e551f0bd5d88501182c2d24a5037fa0aebb9` | `96f504b0f018584bf46eb065ba1029f98cce8b70` |
| B | `5930b38d2c12532d9183ac8a375669fccd71c6d5` | `7e86a1157a0c3dd0689b3484c31b05dd48879c22` |
| B | `4a22cc5082f1fc63a500ba4c82cc53090016ccc3` | `b4ebab112c368d53fe00b708d5cce9852aecc8fb` |
| B | `e6ed17f7047a6dcbbc384cb8c46478090ac2f99d` | `23a165e7b0ade33152d74c8b3380efd0e3695e87` |
| B | `f77cbf6d80eec8622b613e4406f58702d2ac3828` | `0f2c000770c92358263092a74c41d79a0e1eb6d2` |
| B | `ba58a6b3169b5f68d3e4e220394078904d99de27` | `4aaa1389bad46814fcf055c3f731de87a6308da5` |
| B | `e83fca34dfa362a336fa5b2ff9d1cd659dbe5e8d` | `2f4ebc0cc4c609c163a6b67d44c8edb7c12e2e05` |
| B | `c834ce76b939e86b33019719d5b212b1c7a38bdd` | `d278c44dd414690ccd5eee988bcc5c601c090e84` |
| C | `bb154a1136104c6bec0d48be3a4860dae5bb5684` | `dd3084843f31a143c62a44ab685172c8a94e3de0` |
| C | `b24b3a66449feff8a2c6d2faa6a1a73b1e105441` | `7f839becd36c4c49161fb69a1d9b217ffbcf993f` |
| C | `6429d394ddb52ed6ec807b52edc42d62e90b5b31` | `ad53cbf59bc0a635e79d34be3643abc333977ceb` |
| C | `c194ad7e063f8c4c3f0b9f349670ba84027317bc` | `b1323c29a8285768fab1a9db3df0c6f93f46f191` |
| C | `7ba11147445277788135aa748c52454e7002bb59` | `b0bab586a2e085933029253b2d913d59bfab7346` |
| C | `7225a955f534fe0cf64c258369e78ca876df15cf` | `96895e8f54028fe7d2d8210a39766a184bbdc522` |
| C | `2ae2c23ebb5e651240e579d035fa10abdad3356a` | `5ecc1f494648c64b4da32b17476984f0b3dced0c` |
| C | `4f0d728462573bb4e0f91f3ed5516fa259d7e413` | `909f6ee1ff4e24ed80a071927941de6286b86901` |
| C | `3b46dfb43391da302afe0ab1bd2ca7a61df60dad` | `a39a917c10fd551ea63ce19f0317dee859f27199` |
| C | `a1958fe620f9a80017d80aca702711991b80c8e6` | `6b08da3188317810a4fb17b2aaa5553d062c84c7` |
| D | `d722d039d658a6251d93889cb1bb80f519fab3f6` | `b380af7712155a14fd7eec3ce28c9911bd3c2602` |
| D | `6b8982f7220e00cf282879823de06f7823b91207` | `29a571a9fe36595d5cd3e658cb2272517218a3c4` |
| D | `4798f39995f7cbd69684585dbfa17d2b80eeca16` | `3df69e760b8a13360b263c4f4d63ca0d56fb6381` |
| D | `0c4d7c39fb8293efd45dd3872c17786064e7be5a` | `37895d29a1a202baf2e9534b1423ec5ef7ac2e56` |
| D | `4f17c7c902b9fe6e749f8af52380fab8831f05cd` | `942bbbb9d7914c6f443a072aec13f8c38329532a` |
| D | `65df1ddd03108721e105d21b8415b5f8b959a0d6` | `ebf4f057f9de987c2fc65b158e8b831921415231` |
| D | `18278bd42ea91284f76f2d4523f82d316cc20a75` | `6c764522fccbab8a499aab6994d5a8bd82b7913f` |

## Conflict resolutions

A/B conflicted only on deliberate export totals in the interface budget JSON
and test. Imported each classified module and checked exact `__all__` membership:
artifact 6, session 44, request_view 25, tool_result 15, work_graph 22,
snapshot_composition 1, codec 14, config.errors 27, sandbox 10, diagnostics 0.
Total 164; internal-private 3; root exports 41; Engine signature unchanged.
No whole-file conflict selection or new interface was used.

A/C automatic merges retain the union of source test function names in
`tests/test_sandbox_backend_contract.py` and `tests/test_yaml_config.py`.

## Validation and repairs

No G5 repair or qualification has yet passed. Historical audit failures remain
unchanged in the audit document. No live provider calls or private credential
reads are authorized. Docker qualification must use only task-owned labels.

### Replay baseline validation

Code source `6c76452` (full replay identity in the table), then documentation
commit `0f6a659`; unchanged replay code. Overlap/interface suites: 39 passed.
`python -m pytest -q tests/test_g5_audit_regressions.py --tb=short` executed
against that code with added regression tests: **9 failed**, all seven audit
probes plus two A2 checks. C1's initial test harness omitted required image;
that setup failure is not defect evidence. Corrected rerun reached the real
ancestor-symlink write and all nine assertions failed in the intended boundary.
The C2 probe explicitly killed its own surviving child in `finally`.

Regression nodes: `tests/test_g5_audit_regressions.py::test_g5_*`.
Raw logs retained in the task's temporary evidence directory; committed red
summary records the source and assertions without treating historical audit
text as a fresh run. Fixing commits and passing evidence follow below.

### G5-B1 transaction repair

The post-dispatch decode/capture/attachment/assistant/response boundary now
normalizes all failures with sent=true; failure normalizer exceptions cannot
escape transport accounting. Red probe: `1a1cb30` test commit against replay
code. The expanded nine-stage matrix and original probe pass (10 tests).
A preliminary edit had an indentation error and an expanded test mistakenly
called a nonexistent exception decoder; both were corrected before acceptance.
JSON failure facts round-trip; full persisted Session recovery qualification
remains pending. No new export or Engine constructor argument.

### G5-D1/D2 journal repair

Write-all now checks short/zero writes; only newline-complete frames are committed.
`StoreIOError` preserves observed bytes and durability uncertainty after any
attempted write, including exceptions that may follow an unreported write.
Fsync precedes persisted receipts. Exact duplicate retry verifies content and
fsyncs the existing frame; conflicting or partial duplicate batches reject.

Unbounded query requests beyond the configured page size raise
`query_requires_pagination`; explicit `limit` plus `after_sequence` is the
existing paging contract. Whole run/Session/replay APIs consume all pages under
one store lock; qita discovery uses full replay. No query cap was removed.
A 64 MiB frame limit now bounds individual frame input, not total store memory.
Current implementation reloads/scans all journal records per operation and
materializes whole trajectories. Memory/scaling qualification is pending.

Original D1/D2 probes passed after repair. Journal suites: 14 passed in 8.28 s,
including 10,003 records, page boundary/order, qita inspection and exact export/
reimport. Initial retry comparison incorrectly compared fresh recorded_at;
failed run retained (4 failed, 10 passed), then corrected to compare all producer
content while excluding only store-assigned sequence/time/digest. This is not
yet the final complete-tree gate or readiness/default qualification.

### G5-A1/A2 Session repair

`AgentComposition.fork` binds a source facade without restore and calls the one
existing `Session.fork`/atomic checkpoint fork. Source ownership is never claimed.
Repeated operation IDs retain the existing typed `duplicate_fork_operation`
contract; no second child is created. Added tests cover paused/completed source,
historical snapshot under a newer source owner, and persistence failure.

Declarative defaults use SQLite. A YAML launch derives runtime.data_root from
the explicitly supplied project config location; a Python launch derives it
from an explicit project workspace or requires data_root/path. Store preflight
runs before model construction. Memory stays explicit and reports
process_local_session/cross_process=false. Read-only SQLite mode performs no
schema creation or write PRAGMA. CLI inspect/capabilities opens that mode only,
reads the persisted config digest, and does not construct model, credential
resolver, tools, or sandbox. CLI live pause/steer remain typed unsupported.

Public additions: AgentComposition.fork (necessary immutable-source entrypoint),
RuntimeConfig.data_root (explicit durable storage location), and read_only option
on the existing SQLite store. No root exports or Engine constructor growth.

The Session/config/fork/checkpoint suite passed 72 tests after correcting memory
preflight and expected process-local reporting. Extra public-path tests and
seven audit probes are recorded separately. Initial failures remain in the
local execution logs; static CLI findings F841/F401 are pre-existing, not
new allowances. Session durability across fresh processes and all lifecycle
variants still require the final combined qualification.

### G5-C1/C2 initial safety repair

Cleanup no longer calls the implicit workspace exporter; the former private
export hook typed-rejects rather than retaining the unsafe copy algorithm.
Explicit permission/effect-controlled publication and retained output/artifact
integration remain pending, so C1 as a whole is not yet qualified.

Docker process control now launches one bounded-output backend supervisor and
requests cancellation through a request marker. Only the supervisor emits real
completion after parent exit, group absence, pipe drainage and (on Linux)
adopted descendant absence. The controller never writes an exit code. Unknown
completion retains ownership and close raises a typed cleanup failure.

The original local parent-exit/child-survival probe now passes. One required
real Docker test passed in 2.25 s on the preinstalled qualification image:
private stage/read, non-root/read-only/cap-drop/NNP/network-none, no mounts,
0.5 CPU/256 MiB/32 pids, owned process group termination, repeated termination,
source-byte invariance and exact label-scoped container absence. This is one
bounded scenario, not the complete required Docker matrix. No foreign container
was stopped or removed. Python thread/remote request hard cancellation is not
claimed; escaped process groups require containment/unknown semantics.

### G5-D3 readiness authority repair (qualification pins pending)

An integration-owned closed registry now fixes producer/source/replay identities,
expected current artifact paths, schema, writers and controlled test nodes.
The validator rejects duplicate/unknown requirements, unrelated artifacts,
fake writers/schema, unresolved symbols, absent or mismatched execution pins,
and self-authorized current qualification. It never executes manifest code.
13 unique controlled nodes were actually collected with pytest (exit 0).
The original spoof probe plus readiness/audit suites passed 21 tests.

QUALIFICATION_PINS is intentionally empty until final committed installed
consumer execution produces content-bound current artifacts and identity facts.
Readiness remains waiting_on_a_b_c; this guard repair does not close current
producer qualification or authorize schema/default switches.

### Historical bundle repair

Restored the context-transfer producer manifest byte-for-byte from locked
baseline 306e689ab19665678b6de644045d374c5ec05102. Its original producer identity
b229e0b80a55a1add64fdb88fbe5b632f8d15ad8 is preserved; the baseline identifies
the subsequently assembled historical qualification bundle. Historical hash
and test-node assertions now read that bundle with git show, independently of
current source modifications. The S3 Lane C bundle uses the same verified
historical baseline. No old digest or failure history was rewritten.

At 5829f8b plus these historical-only edits,
`python -m pytest -q tests/core/test_context_transfer.py tests/test_s3_lane_c_evidence.py`
passed 42 tests (1.18 s). New S4/G5 current qualification remains separate and
pending; these historical assertions do not qualify today's runtime.

### Explicit publication and first composition wiring

Added opt-in SandboxPublicationTool through existing permission/effect execution.
Caller fixes selected top-level paths and staged input digest before registration.
Descriptor-relative, no-follow publication uses atomic file exchange on Darwin
and Linux; selected source conflicts and protected/special paths reject. Partial
failure rolls back only unchanged outputs, otherwise reports rollback uncertainty
and retains recovery files. Nested path publication is typed unsupported.
Cleanup remains separate. FileArtifactStore retains verified bounded content,
with logical ArtifactRefs and explicit missing/integrity failures.

Configured contributors/memory sources/selector/compactor/continuation/artifact
services now resolve explicit caller factories. Unknown effective extension and
tool policy options reject before provisioning; lifecycle and fail-closed policy
are connected. Parallel admission uses declarations rather than tool-name lists.
These are submodule extension methods, not new root exports or Engine parameters.

At c4c415e plus this working diff: publication/Docker/A/C suites passed 61 tests
(5.09 s); eight configuration regressions passed (0.33 s), including contributor
and memory sent through a real Engine request and selector invocation. Flake8
changed modules passed; mypy seven changed composition/kit modules passed.
The real Docker publication test passed (1.65 s): unmodified host before explicit
publication, committed effect, retrievable artifact, and no cleanup writeback.

A further synchronous-command parent-exit defect was found and fixed by reusing
the same backend supervisor (no additional executor). Serial owned Docker tests
and the original process regression passed four tests (4.83 s), including timeout
after shell exit with a living child, actual descendant completion, and byte
counts. These are intermediate gates; required sandbox restore/fork/fencing,
full consumer work runtime and final qualification remain pending.

### First full-tree gate and retained output follow-up

At f9dfc98: full pytest (live-model endpoint/key unset) completed in 396.32 s:
2592 passed, 50 skipped, 5 failed. All 50 skips are live-credential E2E nodes;
no G5 node skipped. Raw local logs: /tmp/qitos-g5-first-full.log and XML alongside.
Failures: S3 configured Docker recovery and Docker model route expected implicit
cleanup publication; B S4 fixture compared historical bytes to current source;
large-output projection fixture lacked its artifact resolver; cleanup fixture
lacked explicit durable root. Stable-surface flake8 and mypy (94 files) passed.
Ratchet found two new Optional resolver type errors plus nine stale C allowances.

Rebound historical B bytes to its original producer commit without changing any
historical hashes. Supplied explicit resolver/root in the affected contract tests.
The two publication adaptations first failed because Engine teardown had already
destroyed Env before caller publication. This exposed a real output-retention gap.
Added bounded content-addressed workspace retention before owned cleanup and
publication from retained artifacts after verified container absence. Six serial
Docker tests then passed in 14.58 s, preserving the original output assertions.

A new sandbox Session regression now demonstrates the remaining actual gap:
paused, unpublished code is retained, but fresh composition restore reads the
original input instead of the snapshot output (1 failed, 1.99 s). The earlier
invalid fork-operation test setup was corrected before recording that failure.
This is a red G5-I1 test, not a passing restore qualification.
