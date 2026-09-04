# S4 candidate audit and G5 repair/convergence plan

Status: reviewed candidates; G5 repair required; no integration or promotion
Updated: 2026-09-04
Reviewed integration HEAD: `d78c385e91c37f8522d7696d4867f6c6c3fb50d3`
Common lane ancestry: `c4e621d05960a4e2f06cb4864f6a8cb8275ac067`
Remote runtime baseline: `f07b38647cf3b18a5235581224a1153b88fac397`

## 1. Decision

The four lanes delivered useful framework mechanisms, not merely documents:
Session-first authoring, provider/context extension contracts, Env-only ACI and
private Docker staging, and a durable Trajectory candidate with qita/evaluation/
distribution consumers. The direction remains correct for a research-first
Agent-development framework.

They are not yet merge-ready. Independent probes reproduced seven framework
defects, including a host-write boundary escape, a false process-termination
receipt, a false durable-write receipt, silent trajectory truncation, and a
readiness false positive. These are not explained by Docker contention, model
quality, or Agent-author policy. Source review also found unresolved public
persistence/inspection semantics and required cross-lane wiring.

The next task should be one bounded G5 repair-and-convergence task, not another
four-lane feature wave. It may replay these exact candidates into an isolated
integration worktree and repair the enumerated defects there. It must not
freeze defaults, promote, publish, or retire source worktrees until the final
integrated tree passes the required gates.

## 2. Verified source identities

All five current worktrees were clean before and after the read-only audit.
Every lane's merge-base is exactly `c4e621d...`. No combined source tree was
created during this audit.

| Lane | Exact source HEAD | Commits after baseline | Disposition |
| --- | --- | ---: | --- |
| A | `f670e551f0bd5d88501182c2d24a5037fa0aebb9` | 5 | public-path producer; fork and persistence/inspection repair required |
| B | `c834ce76b939e86b33019719d5b212b1c7a38bdd` | 7 | offline producer; post-dispatch failure accounting repair required |
| C | `a1958fe620f9a80017d80aca702711991b80c8e6` | 10 | execution producer; host-export and process-lifecycle repair required |
| D | `18278bd42ea91284f76f2d4523f82d316cc20a75` | 7 | unfrozen candidate; journal/read/readiness repair required |

The pasted C report does not exactly match the repository for either the full
HEAD or manifest digest. The authoritative values are:

- HEAD: `a1958fe620f9a80017d80aca702711991b80c8e6`;
- `tests/fixtures/s4/lane_c/producer_manifest.json` SHA-256:
  `80f3db9514791738f699932e17a2dfab80c6190d1083d388493fa2bc523d6a49`.

Other manifest byte identities independently computed:

- A `producer-manifest.json`:
  `369c9d51ecfbab6a5024a5983d70baa8d0deaf56587bafae8bb7e4a23d9cf97f`;
- B `producer-manifest.json`:
  `a137229d89e4732743053403d37da16fcdeee9d3f26541bac003a323391473af`;
- D `producer-manifest.json`:
  `4622142eeecf1ac610abca43268b22d06148d67cecd00000c98d4d42dc91784d`.

`git ls-remote` and the tracking ref both resolve the formal feature branch to
`f07b386...`. Before the audit documentation commit, the primary checkout was
two documentation commits ahead, with no remote-only commits. No push occurred.

## 3. What is genuinely improved

- **A:** `AgentComposition` is a context manager over the existing runtime;
  declarative execution uses Session; explicit ephemeral execution, CLI
  inspection/resume/fork, and wheel-safe scaffolding exist.
- **B:** provider capabilities, modern exchange semantics, structural adapter
  conformance, bounded context/transfer, and artifact/memory contracts are
  concrete implementations. No live-model success is needed to accept their
  offline mechanisms.
- **C:** ten Env-only ACI tools, typed sandbox policy and private staging,
  durable-only multi-agent adapters, and MCP lifecycle consolidation are useful
  changes. Their security and termination claims require the repairs below.
- **D:** a journal store, reader-based inspection, evaluator/export extensions,
  storage measurements, and installed-wheel consumers exist. Keeping schema and
  default switches unqualified is correct.

These are candidate capabilities. None is represented as newly integrated into
the primary checkout by this audit.

## 4. Independently reproduced framework defects

### G5-C1 — P0: implicit sandbox export can write outside the source workspace

Source: C `qitos/kit/env/docker_env.py::DockerEnv.close` and
`_export_private_workspace` (around lines 510 and 779).

Cleanup automatically copies container output back into the host source tree.
Export excludes `.git` and exported symlinks, but does not reject symlinks in
destination ancestors and does not preserve the staging exclusions for `.ssh`,
`.env`, credential files, or other protected destinations.

A temporary-directory probe substituted only the Docker copy transport. The
source contained `link -> outside`, and the synthetic container export contained
`link/escaped.txt` and `.ssh/authorized_keys`. Observed:

```text
WROTE_OUTSIDE_SOURCE True
WROTE_PROTECTED_DIRECTORY True
```

No real container or user file was touched. The defect is in the actual
controller-side export algorithm, not in the synthetic transport.

Required repair:

1. Cleanup must not implicitly publish untrusted outputs into the user's source
   tree. Preserve outputs in a task-owned artifact/staging area.
2. If source publication is supported, make it an explicit operation with
   authority, selected paths, a diff/receipt, input-digest/conflict checks, and
   a failure-safe commit policy.
3. Deny protected paths, destination-ancestor symlinks, traversal, hard-link/
   special-file tricks, and races using descriptor-relative/no-follow semantics
   where supported; fail closed elsewhere.
4. Test partial publication, changed source files, concurrent source changes,
   fork siblings, failed/cancelled runs, and cleanup without publication.

This is a promotion blocker regardless of Docker performance.

### G5-C2 — P1: process termination reports reaped while descendants survive

Source: C `DockerProcessControlCapability.start/poll/terminate`, around lines
291–354 of `qitos/kit/env/docker_env.py`.

Termination signals the recorded shell PID and then writes a synthetic exit
code file. Poll trusts that file as terminal. It neither proves descendant
termination nor waits for a true process-group completion acknowledgement.

A local shell-control probe ran the exact command scripts with only their
task-private path and command transport substituted. Observed:

```text
TERMINATION owned_process_reaped
WORKER_STILL_RUNNING False
CHILD_STILL_ALIVE True
```

The probe's owned process group was explicitly cleaned up. This is shell
lifecycle evidence, not a claim that real Docker qualification was run.

Required repair: own a process group or backend task identity, signal and wait
for all owned execution, validate real completion, and keep unresolved workers
unknown. A controller-written `.rc` file is not completion evidence. Cleanup
errors must not be swallowed and then erased from ownership tracking.

### G5-A1 — P1: CLI fork mutates and strands the source Session

Source: A `qitos/cli.py::_session_main`, around lines 254–285.

CLI captures the old snapshot, then calls `composition.restore(source_id)` before
forking. Restore advances source ownership/head even though the requested
operation is only fork. A SQLite/fake-model probe observed:

```text
before: source lifecycle=paused, generation=4
qit session fork: exit=0
after: source lifecycle=restoring, generation=5
SOURCE_HEAD_UNCHANGED False
```

Capturing the old snapshot fixes which child snapshot is selected; it does not
preserve source identity/head. The existing CLI test asserts child creation but
does not assert source invariance.

Required repair: fork an immutable source through the canonical fork/store
operation without claiming source ownership. Test paused, waiting-input,
terminal, historical snapshot, persistence failure, concurrent source owner,
and repeated-operation paths. Source head and owner must remain unchanged.

### G5-B1 — P1: continuation failure loses post-dispatch accounting

Source: B `qitos/models/provider.py::execute_provider_request`, around line 668.

When transport succeeds and decode returns continuation state but no capture
resolver exists, the executor raises a default `ProviderFailure`. Its default
stage is transport and its request-sent flag is false.

Using B's independent adapter/request fixture, counting transport calls, and
removing only its continuation resolver produced:

```text
TRANSPORT_CALLS 1
ERROR_CODE continuation_capture_unavailable
STAGE transport
REQUEST_SENT False
```

Required repair: retain `provider_request_sent=true` for every post-dispatch
failure, use the correct decode/continuation stage, and normalize validation,
capture, attachment construction, and assistant-item finalization failures.
Add counter-conservation tests across admission, cancellation, transport,
decode, capture, and result publication; no duplicate request on recovery.

### G5-D1 — P1: short journal writes return false persisted receipts

Source: D `qitos/tracing/journal_store.py::_append_frame/append_batch`, around
lines 225 and 290.

The unbuffered file write return value is ignored. A controlled short-write
transport wrote half of one frame and returned the real written byte count.
The real append method reported:

```text
status=persisted, accepted_count=1, persisted_count=1
subsequent query after partial-tail recovery: 0 records
```

Required repair: a write-all loop or equivalent checked primitive, durable
acknowledgement only after complete framing and fsync, and explicit failure/
uncertainty when an I/O error occurs after bytes may have reached disk. Test
short/zero writes, partial-frame failure, complete-frame-before-fsync failure,
missing delimiter, recovery, repeated append, and exact readback. The current
I/O test throws before writing any bytes and is insufficient.

### G5-D2 — P1: bounded reads silently become lossy complete trajectories

Source: D `JournalTrajectoryStore._query_unlocked/_trajectory/read_run`, around
lines 327–352.

With three records and `max_query_records=2`, `read_run` returns two records and:

```text
LossReport(policy_id='qitos.loss/none', entries=())
```

The same boundary affects session reads, replay, inspection, and exporters.
Required repair: explicit page/cursor/has-more metadata, or a typed limit
failure, or complete iteration for whole-run APIs. Exact export must consume
all pages. No partial result may claim loss-free completeness. Also measure the
full-journal reload on every append/query; result count bounds alone do not
bound memory or scanning work.

### G5-D3 — P1: exact-source readiness accepts unrelated files and fake tests

Source: D `qitos/tracing/s4_readiness.py::_validate_binding`.

The validator checks a file digest and that the test file exists, but only
requires non-empty schema/writer strings, accepts a self-asserted conflict flag,
and does not resolve the test symbol or validate semantic producer authority.

A probe bound every A/B/C requirement to the committed `README.md`, supplied
`schema='not-a-schema'`, `current_writer='nonexistent.writer'`, and
`tests/test_no_local_paths.py::test_does_not_exist`. Observed:

```text
status=ready_for_g5_review
qualified_lanes=[A, B, C]
finding_codes=[]
```

Required repair: an integration-owned expected producer/requirement registry;
strict schema/current-writer checks; source/replay/current-byte separation;
duplicate/unknown rejection; resolvable test-node identity plus executable
consumer results. Parse identities and reject conflicts rather than accepting
`no_identity_conflict=true`. Metadata cannot authorize itself.

## 5. Additional source-reviewed requirements

### G5-A2 — public durability and read-only inspection must be truthful

A `SessionConfig` defaults to `mode='durable'` but `store='memory'`.
`run_agent_config` labels this `durable_session`, although a new process cannot
recover an in-memory store. The generated SQLite config is useful but does not
fix the general default. Keep Memory as an explicit process-local/testing
capability, or require/select a persistent store for the durable CLI path.

`qit session inspect/capabilities` currently builds the full AgentComposition
before reading a head. That may resolve model credentials and provision Docker
for a read-only operation. It also reports the supplied config's digest rather
than independently retrieving the persisted source digest. Inspection should
need only the read-capable store/resolver; unavailable providers or Docker must
not prevent inspection of a persisted failure.

These are source-review findings, not additional executed CLI/Docker probes.

### G5-I1 — accepted config slots are not implemented services

A currently transports memory/compaction/lifecycle/failure settings as metadata.
B publishes provider/context/artifact service requirements; C publishes a
sandbox component/allocation; D publishes a journal/readiness consumer. G5 must
instantiate and execute these services through the same public paths, rather
than accepting arbitrary settings that have no effect.

Required binding includes:

- context contributor, MemorySource, selector, compactor, ArtifactResolver and
  continuation resolver;
- spec-driven parallel admission and the ten Env-only tools;
- sandbox snapshot registration, restore attestation, child allocation,
  handoff generation fencing and terminal cleanup;
- a resolvable storage implementation for C's `tool-result-output` ArtifactRef,
  not only a digest/reference without a body retrieval path;
- required event sink/journal selection and one qita reader path;
- source/output publication as a separate permission-controlled operation.

### G5-E1 — evidence, leases and quality need integrated repair

Two file-overlap groups are present:

- A/B: `tests/fixtures/public_surface/g2-interface-budget.json` and
  `tests/test_g2_interface_budget.py`;
- A/C: `tests/test_sandbox_backend_contract.py` and
  `tests/test_yaml_config.py`.

A/B changed frozen global interface-budget evidence. G5 must review actual
exports and merge the semantic budgets, not take either entire file or simply
accept a raised expected count.

B rewrote the historical context-transfer manifest's producer commit/hashes to
S4 while retaining its S3 producer and dispatch labels. C's unchanged S3
manifest test compares historical hashes to changed current source and fails.
Preserve historical bytes and verify them against their historical commits;
publish separate current S4 qualification. Do not rewrite history to green CI.

C's static ratchet independently fails only because nine resolved findings
remain in the frozen allowance baseline. A shrink-only integrated update is
appropriate after the final source tree is stable. No new allowance or blanket
exception is justified.

The C report's 99 skips versus other lanes' 50 requires exact skipped-node and
reason reconciliation in the final environment. Do not sum per-lane test counts
or use sequential reruns of individual nodes as a green integrated full suite.

## 6. Independent validation performed

The reviewer ran these source-specific, offline suites on the exact clean lane
heads:

| Lane | Suite | Result |
| --- | --- | --- |
| A | public authoring, G2 interface budget, no-local-path, public surface | 23 passed |
| B | S4 provider conformance, S4 fixture tests, S4 context extensions | 23 passed |
| C | S4 Lane C, MCP, delegate/fan-out/handoff adapters | 131 passed |
| D | S4 journal/readiness/publication/qita/distribution contracts | 21 passed |

Total: **198 passed**, plus the seven independent boundary probes above that
demonstrated missing invariants despite those green suites.

Additional executed negative gates:

- C `tests/test_s3_lane_c_evidence.py`: **1 failed, 1 passed**, reproduced
  historical/current hash mismatch;
- C `scripts/static_quality.py check`: exit **1**, nine stale allowances for
  resolved findings, no newly introduced findings reported by that invocation.

The audit did not rerun full suites, Docker stress, real models, the 20-profile
package matrix, or a merged candidate. Per-lane full-suite and packaging counts
remain producer-reported evidence. Docker resource contention is a plausible
reported environmental contributor, not an independent explanation for every
failure. No unrelated container or process was stopped.

The documentation-only update in the primary checkout additionally passed
23 tests across no-local-path/secret, architecture, public-surface, workflow,
and example-policy gates, plus `git diff --check`. These are separate from the
198 lane-specific tests and do not qualify a combined runtime tree.

## 7. Next task: one G5 repair-and-convergence worktree

### Phase 0 — source lock and bounded execution environment

Start from the reviewed integration branch, retaining the audit/Task 15/16
planning commits. Lock all four exact source heads above and the 29-commit
replay inventory. Use one new G5 worktree; retain the four source worktrees.
Record the actual Python/toolchain and reserve serial execution for Docker
qualification. Do not clean up or interrupt unrelated Docker workloads.

### Phase 1 — replay A -> B -> C -> D

Replay all 29 commits in source order and retain source-to-replay mapping.
Resolve the two overlap groups semantically. Do not use whole-file ours/theirs,
merge commits, force-reset, or rewriting of source branches. Before claiming
qualification, run the seven probes against the replayed tree to preserve a
red baseline.

### Phase 2 — repair framework invariants

Repair G5-C1/C2, A1/A2, B1, D1/D2/D3 in the same integration worktree. Add
deterministic regression tests at the correct owning boundary. Keep the scope
limited: no new product Agent, no distributed scheduler, no daemon-control
project, no strong-isolation vendor expansion, and no new parallel API family.

### Phase 3 — complete the public vertical

Implement G5-I1 so config and Python composition execute the same real services.
Prove create/run/inspect/pause/resume-with-steering/fork, durable child work,
least-authority sandbox allocation, typed cancellation/unknown, artifact
retrieval, and complete Trajectory reading. Use one coding/tool consumer and
one unrelated research/tool consumer. They must consume an installed wheel and
public/extension APIs, not private test harness objects.

### Phase 4 — one honest qualification run

- Run all new regressions and existing S2/S3 recovery/isolation/budget gates.
- Run the full pinned suite once on the final tree; retain every failure and
  the exact skipped-node inventory. After a fixing commit, rerun all relevant
  gates rather than hiding failures behind rerun plugins.
- Run real Docker create/stage/attest/execute/restore/child/cancel/export-policy/
  cleanup and required adversaries serially on an adequate host. If a platform
  cannot enforce a requirement, reject that capability and constrain the claim;
  do not treat a fake or unavailable skip as platform qualification.
- Shrink only the actually resolved static baseline, reconcile public budgets,
  retain historical evidence, and publish current exact-source consumers.
- Build wheel/sdist, run twine and clean-venv extras/consumer qualification.
- Keep live-model capability informational. Missing credentials, provider
  availability, and task success do not block a correct framework; privacy,
  request accounting, isolation, and persistence invariant failures do.

### Phase 5 — data-plane graduation and baseline decision

Only after Phase 4 and real A/B/C consumers pass may G5 freeze the single
Trajectory contract, enable the canonical writer for both public paths, switch
qita's default reader, and rerun complete/lossy/historical parity. A switch
failure keeps the candidate unpromoted; it does not authorize a second writer.

Update shared English/Chinese docs, README, changelog, progress, API references,
and migration truth once. Review the exact committed tree and repeat the
required checks in the primary checkout after an authorized fast-forward.

Push, package publication, default-branch changes, and cleanup remain separate
authority gates. When baseline promotion and an authorized non-force push are
verified, retire only the completed clean, idle S4/G5 worktrees using non-force
removal, retain all branch/commit refs, and record released space.

## 8. Current final status

```text
S3_G4_STATUS=closed
S4_STATUS=candidates_reviewed_repairs_required
G5_STATUS=not_started
INTEGRATED_S4=false
TRAJECTORY_SCHEMA_FROZEN=false
DEFAULT_BRANCH_READY=false
RELEASE_READY=false
```

This review changed planning/documentation only. It did not fix candidate
runtime code, create a convergence worktree, merge, push, deploy, call a model,
publish a package, delete a worktree, or delete a ref.

## G5 repair references appended 2026-09-04

The audit above is preserved as the original observed failure record. Repairs
and fresh regression evidence now exist in the isolated G5 branch; these
references close the corresponding reproduced defect on fixing candidates,
not the still-pending final G5 promotion gate. Follow-up integration, staging,
approval and selector failures remain in the execution ledger.

| Item | Primary fixing commit | Regression/qualification |
|---|---|---|
| G5-C1 | `5a6d048cff82ca050cb1fb8e2353942cb67c9e80` | `tests/test_g5_publication.py; tests/test_g5_input_staging.py; tests/test_g5_docker_owned.py` |
| G5-C2 | `e30975a9325c105062e94a4fa4dda03aa295a0f2` | `tests/test_g5_docker_owned.py; tests/test_g5_process_tool_status.py` |
| G5-A1/A2 | `ee351384fc101cc5f646b421343f4e52c090616a` | `tests/test_g5_audit_regressions.py; tests/test_g5_session_public.py; tests/test_g5_pending_approval.py` |
| G5-B1 | `b9b9479bd001f437c483f1ac21bcb642ead3f495` | `tests/test_g5_audit_regressions.py; tests/models/test_g5_transport_retry_budget.py` |
| G5-D1/D2 | `bd66a30abb01ab95b5d558b9b906ceb55aca3612` | `tests/tracing/test_g5_journal_durability.py; tests/qita/test_g5_default_reader.py` |
| G5-D3 | `c4b088ce9612a802e4c327d761b639cb17651240` | `tests/tracing/test_g5_readiness_bindings.py; scripts/qualify_g5_composition.py` |

C's reported 99 skips was a transcription error. Its original completed command
exec-16da826f-892e-46e8-9404-dab8ba6cf610 in the Lane C task recorded
`6 failed, 2446 passed, 50 skipped in 826.94s`. The original stdout, aggregate
and formatted output agree; their digest and exact summary are preserved in
tests/fixtures/s4/g5/lane-c-skip-reconciliation.json. There are no evidenced
additional 49 skip nodes to explain. The erroneous historical report is not
rewritten, and its six failures remain failures. Current 50 skips are live E2E
credential opt-ins; required offline/Docker probes must not skip.
