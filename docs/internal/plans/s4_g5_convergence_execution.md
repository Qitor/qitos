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

### Durable sandbox/work integration repair

Registered the C sandbox component on durable Docker compositions. Its required
owner stores a bounded workspace ArtifactRef, cold-restores into a new attested
allocation, validates source/fork lineage and generation, and binds exact Docker
Session/run/work/attempt labels. New snapshots require the owner; the older
optional component remains readable. RuntimeSnapshotContext carries the existing
Session, immutable source snapshot and ownership facts to extension owners; no
Engine constructor parameter or second persistence store was added.

Outputs are bounded to 4 MiB of file bodies / 4096 entries (8 MiB encoded
workspace artifact). Native process/memory restore, nested host publication, and
resuming an unresolved background process remain unsupported. Source publication
is separate from cleanup. Retention/cleanup failure is now typed and emitted; it
cannot be reduced to a warning-only successful run. Original warning assertions
remain, with typed failure assertions added.

The real restored-sandbox test passed (5.32 s); three serial Docker continuity,
sibling isolation/identity-label, old-owner fencing and missing-artifact tests
passed (13.53 s). The original missing-workspace regression is closed by this
code; installed fresh-process qualification remains pending.

A real LocalWorkScheduler child test first failed: a completed child Session had
zero WorkGraph completions and its join remained open (1 failed, 0.37 s). Session
now verifies actual child checkpoint identity/lineage/owner and records canonical
ToolResult completion before accepting join dependencies. Scheduler callback
failure no longer invokes a second terminal callback as a synthetic worker
failure. Handoff snapshots preserve the transferred agent identity/reference,
while the previous facade remains fenced.

Final adjacent iteration on f23136e plus this fixing diff: 300 passed (19.75 s)
across engine/checkpoint, audit, sandbox continuity, cleanup, public budget and
architecture gates. A prior adjacent run had 299 passed / one cleanup-test-double
failure, repaired with partial-resource-safe cleanup lookup. The real child/fork
subset passed 41 tests (7.42 s). Flake8 changed modules passed; mypy stable plus
changed composition/sandbox modules passed, 107 files. Full-tree, installed-wheel
consumers, all Docker adversarial cases, readiness and default switches are still
required; these focused results are not substituted for those gates.

### Explicit shared journal composition before default switching

The installed-consumer preparation exposed a missing composition path: `.journal`
outputs were interpreted as directories and qita could only parse JSON. A new
read-only inspection regression failed on cbf9b4b plus the test (1 failed, 0.19 s;
`/tmp/qitos-g5-journal-reader-red.log`). Explicit `.journal` configuration now
selects the existing JournalTrajectoryStore; its read-only mode acquires a shared
existing lock and performs no tail recovery, index rewrite or file creation.
qita uses the same frame validator in this mode. Defaults remain unchanged.
The new constructor flag is necessary for inspection without mutation, introduces
no root export, and does not change Engine's interface budget.

After repair, tracing/qita/composition/interface-budget tests: 134 passed, 79.93 s
(`/tmp/qitos-g5-explicit-journal.log`); mypy on the three changed modules passed.
A whole trajectory is still materialized and scanned in memory: read-only does
not imply bounded memory. Installed consumer and default qualification remain
pending.

### Installed coding attempt 1: failure-path integration repairs

Intermediate wheel from a13f650 code installed in a fresh external venv (no
editable install / PYTHONPATH). Consumer attempt failed: its native-tool-required
child returned only text; the resulting failed child exposed a missing canonical
error_kind/error_code in Session completion collection. An independent real-child
regression reproduced the latter (1 failed / 1 passed, 5.48 s). The consumer now
uses a real native tool before finalizing; the framework records failed child
completion with execution error facts.

Three process-tool regressions also failed: live/unknown worker results violated
ToolResult invariants and were replaced by generic semantic errors. Bounded poll
now reports timed_out with process_still_running/process_outcome_unknown; an
unconfirmed terminate reports cancelled with a still-running flag. Both carry
explicit effect uncertainty and non-retryable worker facts. No hard cancellation
is claimed. Explicit publication rollback uncertainty also preserves its effect
reference. After repair: 46 passed, 1.45 s (work runtime, real child failure,
process tool truth, publication); prior 3-failure intermediate output retained.
Installed consumers have NOT passed yet.

### User-authorized supplemental live provider validation

The user explicitly authorized real model calls after the original offline-only
boundary. Live checks are now allowed as bounded informational capability evidence;
they do not replace deterministic framework gates. No private credentials file
is read, and supplied secrets are never committed or written to qualification
artifacts. Endpoint and key values are intentionally absent from this record.

Preparation found an SDK accounting gap: OpenAI client construction inherited
the SDK retry default. The regression failed (1 failed, 0.25 s) because
max_retries was unset. Shared sync/async client options now set max_retries=0,
so an SDK cannot silently repeat an admitted request. Provider compatibility
and conformance checks passed after the fix (see /tmp/qitos-g5-sdk-retry-fixed.log).

### Readiness identity binding refinement

Readiness validates approved writer symbols in committed source. Code, producer
facts and qualification results have separate commit bindings to avoid
self-referencing digests. Typed Session/run/work/attempt identities and the
installed consumer's actual execution result must match the producer facts.
The source table's nonexistent ToolRuntime writer was corrected to the existing
ReferenceEffectPolicy. Existing readiness/audit checks passed: 21 passed, 2.09 s.
Qualification pins remain empty; no producer is claimed qualified. Additional
negative binding cases and actual current consumer facts remain required.

### Live attempts 1–2 and restored policy repair

Two bounded live attempts against the user-authorized model each sent one request,
received a native tool call and executed the survey tool once (814 provider tokens
each). Both stopped before a second dispatch with CodecCapabilityError /
provider_capability_loss: the generic Chat Completions codec cannot replay the
returned reasoning under the default loss-rejecting policy. No SDK retry or
persisted/diagnostic secret was detected. These are failed capability attempts,
not framework qualification passes. Sanitized receipts remain under
/tmp/qitos-g5-live-result{,-02}.json.

The public config now wires the existing allow_codec_loss extension, false by
default. The regression initially failed at config admission. Corrected native
protocol fixtures verify two dispatched requests, real tool execution, canonical
reasoning retention in the persisted conversation, and explicit projection loss
in Trajectory. Earlier test setup mistakenly used a text protocol and disabled
trajectory; those intermediate failures are retained, not counted as regressions.

Installed coding attempt 3 separately revealed that fresh restore discarded
approval, parallel/failure and context settings. A public restore regression
failed (1 failed, 0.80 s). Existing execution settings are now captured in the
Engine progress component and validated/restored via the same Engine constructor.
No constructor parameter or public versioned API was added. Thirty-nine adjacent
Session/fork/context tests passed (2.94 s); changed-module flake8 and mypy passed.
Required approval-interrupt closure remains a separate pending investigation.

### Installed consumer steering publication and readiness adversarial checks

Coding attempt 4 reached final publication/artifact retrieval/child join; research
attempt 1 reached real handoff, fresh-process continuation and typed worker timeout.
Both then failed because no independently classified steering record existed in
Trajectory. The focused regression reproduced zero records (1 failed, 2.97 s).
After each successful snapshot commit, Session now compares its persisted
steering receipts with the previous immutable head and emits changed dispositions
through RuntimeEvent. This covers submission and queued-to-applied transitions
without repeating an unchanged applied receipt on every snapshot.

Twenty-six steering/Session/vocabulary/readiness tests passed (3.51 s); mypy on
the two changed runtime modules passed. The readiness validator additionally has
15 positive/negative unit cases, including README/schema/writer/test-node spoofs,
stale digests, unknown/duplicate requirements, historical writers, missing or
uncollected execution, unpassed consumers and invalid/mismatched identities.
These synthetic validator fixtures are not qualification evidence.

Live attempt 3 on 75b58da code, with explicit projection loss, failed at connection
after one admitted request (provider_connection_failed, no tool executed, no
provider token usage reported). A subsequent credential-free TCP/TLS probe failed
with SSLEOFError. The request remains consumed and was not automatically resent.
Three total live requests have been admitted so far; only the first two have
reported usage (814 tokens each). This environment failure is informational and
does not replace any required offline gate.

### Installed consumer tool-status admission

Coding attempt 5 on 7cf8bf6 failed its strengthened per-tool assertion. The old
qualification image lacks both rg and the python command used by run_test;
an owned sandbox probe confirmed python3 and pytest 7.2.1 only. A dedicated
Dockerfile adds ripgrep and python-is-python3 and restores USER node. Build 1
failed because the inherited non-root user cannot install packages; build 2
succeeded as image sha256:e3c403f9d6b7b0b93c1cda6bcb329cea11c60d9c0b70b4ac249e8ff049bcde53.
Logs: /tmp/qitos-g5-image-build{,-02}.log. The consumer now checks both canonical
ToolResult and the documented trace-safe projection schema, retaining all eleven
required tool-status assertions. Neither previous final text nor publication
alone constitutes a passed tool consumer.

### First passing installed consumers and in-loop durable work repair

Coding attempt 6 and research attempt 2 passed their installed-wheel checks
using framework code 7cf8bf6 and c02f1b7 consumer scripts, outside the repository
with PYTHONPATH unset. Coding read 305 records; research read 125. Public exports
round-tripped every record and explicitly declared privacy-projection loss.
Logs: /tmp/qitos-g5-installed-coding-06.log and
/tmp/qitos-g5-installed-research-02.log. They are intermediate qualifications;
the final tree, final wheel and default selectors still require rerunning.
The 797-test core/engine/checkpoint/provider/audit combination passed in 13.41 s
on c02f1b7. No full-tree success is implied.

Three additional model-adapter regressions reproduced an actual lifecycle
failure: spawn/delegate/fan-out called public fork while the source was RUNNING.
The first fixture attempt had invalid AgentSpec arguments; corrected execution
failed all three assertions in 0.36 s. The fix records a quiescent pre-action
snapshot and passes that identity into the sole private fork implementation.
Public fork keeps its lifecycle checks; arbitrary running heads cannot fork.
The fixed three cases passed in 0.44 s, and 50 adjacent work/fork/Session tests
passed in 5.84 s. A separate native-model composition test also executes the
adapter and verifies a real independent child head. Changed-module flake8/mypy
passed. Logs: /tmp/qitos-g5-model-work-{red-02,fix-01,adjacent-02}.log and
/tmp/qitos-g5-native-work-01.log.

### Complete intermediate tree and MCP artifact repair

Full pytest on clean 5ddb78e47a61d3d86a13e5ea30b368f2b671cfe8 passed:
2628 passed, 50 skipped, 433.60 seconds. The complete skipped-node inventory,
JUnit digest, wheel/sdist digests and 19 extra-profile results are committed in
tests/fixtures/s4/g5/validation-5ddb78e.json. All skips require live E2E variables;
required offline/Docker cases did not skip. Live requests are separately bounded
and informational. Historical C's additional 49 skips remain unsubstantiated:
its report contains no node inventory; repository sources contain only 13 async
test functions, so an absent async plugin is not an established explanation.
The original C report remains unchanged; its original pytest/JUnit was requested.

The earlier full-02 attempt ran on c02f1b7 plus the work repair diff and was
interrupted after detecting a native fake-model assertion mismatch. It is not a
complete verification. Full-03 is the separate clean-commit result above.

Stable flake8/mypy passed. The ratchet found three new sandbox component type
findings and the nine original C stale findings. Explicit backend type/receipt
checks repair the new findings. Full MCP static scope also exposed two existing
unused imports, now removed; final shrink-only update must account for those two
additional resolved findings, without exceptions.

An additional MCP probe reproduced missing artifact bytes and false success
without a resolver. The draft permission assertion expected not_started rather
than the existing rejected disposition; it was corrected without changing policy.
The bridge now keeps runtime_context local, persists and verifies large responses
through the composed artifact resolver, and returns a typed post-dispatch failure
if retention fails. It preserves reconciliation requirements. Tests: 87 passed
in 1.86 s (tests/mcp plus S4 C safe execution). Full MCP and sandbox component
flake8/mypy passed. Logs: /tmp/qitos-g5-mcp-{red,fixed-01,static-01}.log.

The 19 non-base packaging profiles all installed and imported the explicit
5ddb78e wheel in independent fresh environments. Base/current installed-consumer
and final-wheel qualifications remain pending. A three-repetition measurement
on the intermediate real consumer exports ran with 305 coding and 125 research
records; this preliminary result does not establish bounded memory or final-tree
performance. Canonical append/query currently reload full journals.

### G5-C2 completion-channel adversary (after 8f17ba6)

A real owned Docker probe stopped its supervisor, rewrote the writable state
file as terminal and reproduced false completion: 1 failed in 1.66 s
(`/tmp/qitos-g5-forged-completion-red.log`). The repair uses an owned Docker
exec completion channel, isolated controller imports and protected Linux
supervisor state. Its focused regression passed in 1.34 s.
The supervisor-kill/import-shadow probe passed in 10.74 s: unknown remained
unknown, ownership and cleanup failure survived repeated close, and source
bytes remained unchanged after owned-container removal.
Combined platform attempt 02 selected an incorrect filename and collected no
tests; attempt 03 uses the actual sandbox Session module. These are distinct
from the earlier seven passing real Docker cases in 20.02 s.
Changed controller/composition/adapter flake8 and mypy passed (six files).
Combined real Docker attempt 03 passed all eight cases in 29.11 s; log:
`/tmp/qitos-g5-owned-channel-docker-03.log`. No other-task containers were used.

### Configured budget/compaction and real work completion

The controlled budget-policy regression first failed configuration admission
(`/tmp/qitos-g5-context-budget-red.log`), then exposed missing independently
queryable compaction receipts (`...-fix-01.log`). Configuration now resolves
the existing budget protocol and the RuntimeEvent adapter emits its receipt
with model-projection loss. An initial 1024-unit fixture compacted both requests
(two real facts, not duplicate append); the corrected 4096-unit fixture admits
the first exchange and compacts the oversized restored exchange only. It checks
one receipt, explicit loss, and exact original 9000-character content retained
in the durable snapshot. No failed history was removed.
Real child execution/join now also covers delegate and fan-out, each with
successful and failed child heads. All 170 composition/audit/work/tracing tests
passed in 32.41 s (`/tmp/qitos-g5-composed-regressions-05.log`); changed static
checks passed. These tests ran on 8f17ba6 plus the recorded working changes,
including the process completion repair subsequently committed as e30975a.

### Approval interruption and persisted post-dispatch accounting

A new public Session probe reproduced approval interruption being treated as
recovery, followed by `IncompleteToolBatchError` and a failed Session (1 failed,
0.78 s; `/tmp/qitos-g5-pending-approval-red.log`). The repair records the
non-executed approval slot, completes its quiescence receipt, then stops the sole
Engine loop. Session follows pause-requested/pausing to waiting-input and keeps
its snapshot. The historical Engine test expecting recovery and a second model
request was corrected to assert one interrupted step, with that semantic reason.
Fix attempts 01/02 exposed lifecycle-transition and quiescence defects; attempt
03 exposed an invalid operation ID in the new fork fixture. All are preserved.
The corrected test verifies source-preserving fork and typed unsupported approval
resume (steering does not authorize effects). 329 Engine/Session/recovery/audit
tests passed in 16.09 s (`/tmp/qitos-g5-interrupt-engine-targets-01.log`), and
stable flake8/mypy passed on c961c09 plus this repair.

A separate post-dispatch continuation-capture failure test passed in 0.67 s:
exactly one request remained consumed in SQLite after closing/reopening the
composition; terminal restore did not resend it. The original stage, sent flag
and typed failure remained visible. Log: `/tmp/qitos-g5-budget-persistence-01.log`.

### Second installed consumer pair and bounded resource pressure

The 9f6856a wheel was rebuilt at the explicit path
`/tmp/qitos-g5-9f6856a-dist/qitos-0.6.0-py3-none-any.whl`
(sha256 decb7425cedb72ee0132dc7aeb063f7af8dd08bf5c9670194ec474124eed2e64);
sdist sha256 9e6a533feaa1c40ecfe302f0da6afaa497938ae1a809a5c4b2e66848e85c742e.
Both passed twine check. A regular reinstall into the external consumer env
ran coding attempt 07 successfully (307 records), including the authenticated
process channel, all ten ACI tools, explicit publication, real child join and
cleanup. Research attempt 04 passed (103 records), with a caller-owned structural
codec and durable continuation resolver, two continuation resolutions, two
compactions, preserved canonical reasoning, opaque-state isolation, handoff
fencing, timeout/late completion and exact public export/re-import.
Research attempt 03 checked the bounded transferred projection for complete
source text and failed; the corrected assertion verifies the unchanged original
immutable source snapshot through its persisted identity. Target omission is
separately represented by compaction/transfer facts, not canonical deletion.
These scripts are outside qitos; no Agent strategy or second runtime was added.
Logs: `/tmp/qitos-g5-installed-{coding-07,research-03,research-04}.log`.
The final-wheel fresh-environment pair remains required after default switches.

A newly owned container with .5 CPU, 256 MiB memory and 32 pids passed the
bounded pressure probe in 2.27 s. It verified cgroup values, non-root/NNP/zero
capabilities, no mounts or credential environment/socket, denied network routing,
pid-limit rejection and self-reaping children, bounded RLIMIT_AS memory pressure,
and label-scoped absence after cleanup. Memory pressure was intentionally
limited below the cgroup OOM boundary; it does not claim an OOM-kill experiment.
Log: `/tmp/qitos-g5-resource-docker-01.log`. All Docker runs were serial.

### Input-staging race extension to G5-C1

A temporary-directory attack replaced a checked source file with a symlink just
before the copying open. The 9a9cfe2 implementation imported outside-input
bytes and did not reject (`/tmp/qitos-g5-staging-race-red.log`: 1 failed,
0.34 s). The fix reuses publication's descriptor-root and protected-path policy
for bounded descriptor-relative input copying. Atomic no-follow open and inode
checks reject the race. Special-file, hard-link, size, protected-name and symlink
tests were added without using any real user directory as an attack target.
Thirty-eight adjacent offline tests passed in 0.40 s; 14 combined real Docker,
sandbox Session and staging regressions passed in 33.19 s
(`/tmp/qitos-g5-staging-docker-01.log`). Changed-module flake8/mypy passed.
The chunked digest preserves the existing input digest definition.
