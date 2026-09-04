# Post-G5 functional E2E dispatch plan

Status: planned_not_run. No model requests or private credential reads in the
documentation task or master CI stabilization. Historical G5 qualification remains bound to
`717b4cf1b23f2ed252cd03234ffd8605038d9567`.
Dispatch identity: the final remote-verified master CI successor SHA, recorded in
the master CI stabilization receipt. This supersedes the earlier docs-only dispatch. **Do not dispatch until that identity exists and local,
tracking and ls-remote agree.** Do not use a moving branch as an execution pin.

## Setup and evidence contract

Begin in a new directory using public Installation, Quickstart and Configuration.
Install the pinned wheel/source and generate `my_agent` with qit new. Preserve
its source digest, sanitized canonical agent.yaml, Python/wheel/extra versions,
Docker image digest and runtime facts. Use a newly approved model profile and
explicit CredentialRef/resolver; secrets stay outside the checkout, 0600 file
and 0700 directory. Do not reuse credentials from chat or historical logs.

One run per scenario/profile. Default overall ceiling: 80 model requests,
160,000 total measured tokens, 2,048 output tokens per response, 30 minutes,
64 external tool calls, two concurrent tools/children. Each scenario also has
its lower ceiling below. Stop when either ceiling is reached. No automatic
provider fallback, SDK retry, or resubmission after an unknown effect.
Model capability declarations must include the selected transport, native tool
expression, parallel calls when needed, reasoning and continuation behavior.

Evidence records dispatch SHA, Session/Run/WorkItem/Attempt IDs, input digests,
request_sent, admitted/used budgets, tool declarations/completions, effect/loss
receipts, stop reason, artifact digest and cleanup. A separate read-only checker
reopens SQLite and default_reader in a fresh process and verifies assertions.
Raw provider payloads and private journal remain private; public evidence is a
reviewed redacted projection with declared loss and byte digests.

## Scenarios

### 1. A developer creates their first Agent

- Goal: follow docs without repository test helpers; install, scaffold, configure,
  register one pure arithmetic tool and run a Session.
- Config/dependencies: base + openai extra, explicit model/endpoint/ref; no Docker
  for the trusted pure-function variant. Fixture: an empty new project and two
  fixed integers. Run the generated install/test commands, then the real-provider
  composition path with that tool.
- Visible result: a final sum, Session ID and readable journal. Independent
  assertions: the sum is correct, tool result is 42, request accounting matches
  transport facts and the installed qitos origin is site-packages.
- Limits: 6 calls, 12k total tokens, 120 seconds, 3 tool calls.
- Cleanup: close composition; preserve project plus private receipts. Classify
  installation/config errors separately from missing tool use or wrong answers.

### 2. Multi-turn native model/tool exchange and codec loss (first priority)

- Goal: a real model reads a fixture, calls a tool, incorporates its result and
  completes the next turn through the same codec/continuation contract.
- Config/dependencies: native-tool profile with declared reasoning/continuation,
  openai extra and Docker for file operations. Fixture: `numbers.json` containing
  [20,22] and a tool returning a bounded typed result.
- Operations: run two or more turns; capture post-tool encode and dispatch facts.
  Reproduce the G5 informational outcome where a native tool executed but the
  following request was rejected by codec loss policy. First use default loss
  rejection; do not pre-plan allow_codec_loss=true or a text fallback.
- Visible result: verified answer, or precise typed capability failure with the
  tool effect retained. Independent assertions: completed tool is not repeated,
  post-dispatch failures preserve sent=true and budgets, rejected pre-dispatch
  requests are not counted as sent, original continuation and loss are traceable.
- Limits: 8 calls, 16k tokens, 180 seconds, 6 tools.
- Cleanup: close only owned resources; preserve the failed exchange for review.
  Separate unrepresentable provider semantics, invalid provider declarations,
  framework accounting/retention bugs and Agent prompt failures.

### 3. Sequential and parallel tools

- Goal: read two independent files, then combine their values after both complete.
- Config/dependencies: native batch-capable model, max_concurrency=2, Docker.
  Fixtures: left.txt/right.txt, a deterministic slow/fast pure tool pair with
  bounded deadlines and distinct outputs.
- Operations: first request serial calls, then one declared batch. Inspect actual
  completion events and declaration-ordered reductions; compare final sums.
- Visible result: same verified sum with explicit batch facts. Independent
  assertions: exactly one terminal result per call ID, actual completion ordering
  retained, reduction does not pair outputs by completion position.
- Limits: 8 calls, 16k tokens, 180 seconds, 8 tools.
- Cleanup: wait for owned work to finish, close sandbox. Unknown or timed-out
  workers remain unknown; model failing to emit a batch is capability evidence.

### 4. Pause, exit, restore and steer

- Goal: pause after a completed tool, exit the process and continue with human input.
- Config/dependencies: SQLite, matching resolver registry and image, lifecycle
  policy at a safe boundary. Fixture: two-stage file task with no unresolved approval.
- Operations: run first stage, save IDs, exit, use credential-free CLI inspect,
  start fresh process, restore and pass steering to Session.run.
- Visible result: paused then completed Session, steering shown by qita.
  Independent assertions: stable Session identity, new attempt/run where applicable,
  no duplicate completed effect, config digest and budgets preserved.
- Limits: 8 calls, 16k tokens, 240 seconds, 6 tools.
- Cleanup: no live CLI pause/steer workaround. Test unresolved approval separately
  as expected unsupported. Distinguish store/resolver failure from model behavior.

### 5. Independent fork

- Goal: compare a new approach while the parent remains unchanged.
- Config/dependencies: paused immutable SQLite snapshot with reconstructable
  resources. Fixture: parent has one verified intermediate result.
- Operations: record full source head, fork before restore claims ownership,
  execute child with different steering, reopen parent from a separate reader.
- Visible result: distinct child Session and explicit source lineage.
  Independent assertions: source head/generation/checkpoint/lifecycle unchanged
  by fork and child execution; child state and effects are independent.
- Limits: 8 calls, 16k tokens, 180 seconds, 6 tools.
- Cleanup: close both owned compositions; retain both journals. A source mutation
  is framework failure, even if the child solves its task.

### 6. Delegate, fan-out, join and handoff

- Goal: collect two child results, then transfer the same work to another Agent.
- Config/dependencies: durable WorkGraph and caller-supplied local resolver,
  explicit per-child request grants (2 each), matching agent capabilities and
  context transfer policy. Fixture: independent arithmetic/checking subtasks.
- Operations: delegate one child, spawn a supervised child, fan out two declared
  children, wait for durable outcomes and join. At a safe paused boundary, handoff
  the same WorkItem to a declared target; attempt execution by the former owner.
- Visible result: child IDs and closed joins; handoff target owns the original work.
  Independent assertions: four real child checkpoints, no completed child replay,
  source owner fenced after handoff, authority/budget intersections preserved.
- Limits: 20 calls including children, 40k tokens, 360 seconds, 16 tools.
- Cleanup: owned scheduler/children closed or explicitly unresolved. No distributed
  scheduler claim. Distinguish unavailable worker resolution from Agent strategy.

### 7. Sandbox, large artifact and explicit publication

- Goal: edit a fixture in isolation, inspect a large output, publish one approved file.
- Config/dependencies: Docker image with required commands, bounded CPU/memory/pids,
  network none, SQLite and artifact store. Fixture: a small program, its test and
  an output exceeding the model projection cap; only a top-level file is publishable.
- Operations: read/edit/test inside Env, retrieve full output by ArtifactRef,
  inspect retained output after cleanup without publication, then in a separate
  run register publication after restore for the exact file and input digest.
- Visible result: verified file/test and explicit publication receipt.
  Independent assertions: host input unchanged before publication, full artifact
  digest valid, unrelated/protected paths untouched, owned container absent.
- Limits: 12 calls, 24k tokens, 300 seconds, 16 tools; output fixture under 1 MiB.
- Cleanup: exact owned labels only; no global prune. Unsupported platform/file
  shape is a typed boundary, not a successful publication or a reason to bypass it.

### 8. Inspect, replay and export

- Goal: understand success and failure through public qita commands.
- Config/dependencies: base package and retained scenario data; no model or Docker.
  Fixture: one completed journal, one typed failure and one historical trace.
- Operations: qita inspect, board, replay and HTML export; use default_reader and
  CanonicalTrajectoryExporter for JSON projection/reimport. Stop local servers.
- Visible result: complete timelines, child lineage, effects, loss and stop reason.
  Independent assertions: all records read, export count matches projection,
  public output excludes private content, raw data unchanged; memory use is measured
  without claiming bounded streaming because the journal currently loads in full.
- Limits: 0 model calls/tokens/tools, 120 seconds.
- Cleanup: local browser/server only; retain selected redacted artifacts.

## Failure classification and dispatch decision

| Class | Evidence | Action |
|---|---|---|
| Framework bug | broken identity, accounting, authority, persistence, loss or cleanup invariant | block framework acceptance; minimal offline reproduction |
| Provider compatibility | valid profile cannot preserve requested tool/reasoning/continuation semantics | preserve codec report; review adapter/profile, no silent loss |
| Model did not complete | truthful execution within budget, wrong/missing answer/tool expression | capability result, not automatic framework failure |
| Agent strategy | unsuitable prompt, tool design, context priority or decomposition | revise out-of-tree strategy with a new scenario identity |
| Environment failure | daemon/image/network/storage unavailable | repair environment; preserve failed receipt and rerun deliberately |

Pass only a workflow whose independently checkable assertions succeed. A provider
ping, final text, native tool receipt alone, or a historical G5 result is insufficient.
Record expected typed unsupported cases separately from successful scenarios.
