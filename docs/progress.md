# v4 integration progress

Status: active integration ledger
Updated: 2026-09-04
Integration branch: `feat/campaign-absorption`
Independently reviewed runtime baseline: `5ef8ab657f6452ae48c931beea79106e2cca34c6`
S1 dispatch baseline: `c1efb0f4adde3e673bf181af5b1760c19a451ae2`
G2 candidate: `cab8fd246d2485784a13558e668eadb3ffa4d42f`
G2-R2 repair branch: `codex/v4-g2-r2-promotion` through `49fa15b5b0499e3f2a1bb4ea86b2af7a143f3e5c`
Promoted G2 contract code head: `c0f19cd8f19a223fc84844f8a6a0ae4a5d0145aa`
Historical S2 dispatch baseline:
`446a347d1ac73636476ca2515a01da601b567c68`
Promoted S2 runtime head:
`3af0ee3b2c3b5b5575e4e07cc31ff7f652327ba7`
S3 plan freeze: `52e050d9bc1ee0d4c6dcc78c90a5497c25722648`
S3 convergence source: `851f7902f15da670e72f4c04d7453cf37201aee7`
Current gate: **S3/G4 CLOSED; S4 CANDIDATES REVIEWED, FRAMEWORK REPAIRS REQUIRED;
G5 NOT STARTED; LIVE AGENT CAPABILITY REMAINS INFORMATIONAL**
Source plan: [`docs/v4/11-four-lane-execution-playbook.md`](v4/11-four-lane-execution-playbook.md)
Next architecture: [`Task 15 public framework graduation`](v4/15-public-framework-graduation.md),
building on [`Task 12 durable sessions`](v4/12-session-runtime-and-persistence.md),
[`Task 13 durable multi-agent work`](v4/13-durable-multi-agent-work-graph.md),
and [`Task 14 sandboxed agent execution`](v4/14-sandboxed-agent-execution.md)

## S4 candidate audit and G5 repair decision (2026-09-04)

All four lane heads and clean worktrees were independently checked against the
common `c4e621d05960a4e2f06cb4864f6a8cb8275ac067` ancestry:

- A: `f670e551f0bd5d88501182c2d24a5037fa0aebb9` (5 commits);
- B: `c834ce76b939e86b33019719d5b212b1c7a38bdd` (7 commits);
- C: `a1958fe620f9a80017d80aca702711991b80c8e6` (10 commits);
- D: `18278bd42ea91284f76f2d4523f82d316cc20a75` (7 commits).

The repository C HEAD and manifest digest differ from the pasted report; use
the source identities and full hashes in the
[independent audit and G5 plan](internal/plans/s4_g5_convergence_audit.md).

The implementations materially improve authoring, model/context extension,
Env-only ACI/sandboxing, and Trajectory/qita/distribution, but are not yet
merge-ready. Seven independent probes reproduced: implicit sandbox export
writing outside the host workspace and into protected paths; false process
reaping with a live descendant; CLI fork advancing the source Session into
restoring; post-dispatch continuation failure reporting request-not-sent;
short journal writes falsely acknowledged as persisted; truncated run reads
claiming no loss; and forged A/B/C readiness accepted from unrelated files and
nonexistent test nodes. These are framework-owned defects, not model or
Agent-author failures and not explained by Docker contention.

The reviewer also ran 198 focused tests across the four exact heads, all
passing. C's old S3 evidence gate independently fails on historical/current
hash mismatch (1 failed, 1 passed); its static ratchet independently exits 1
because nine resolved allowances still need a shrink-only integration update.
No full suite, real Docker stress, live model, package matrix, or merged tree was
qualified by this audit. Producer-reported Docker failures remain open platform
evidence; they are not converted to skips or passes.
The primary checkout's documentation-only update separately passed 23
architecture/public-surface/workflow/example/path-safety tests and diff checks.

Next is one bounded G5 repair/convergence task: replay A -> B -> C -> D, repair
the audited invariants, connect real config/context/artifact/sandbox/Session
services, reconcile historical evidence and interface budgets, qualify serial
Docker and installed-wheel consumers, then consider Trajectory freeze/default
switch and baseline promotion. No additional feature wave is authorized by
this plan. Four source worktrees remain registered and unchanged; cleanup waits
for a qualified promoted/pushed baseline. `DEFAULT_BRANCH_READY=false` and
`RELEASE_READY=false` remain unchanged.

## S4 four-lane implementation planning (2026-09-03)

Historical dispatch record; superseded by the candidate audit above. The lanes
used the locally available exact baseline without changing their ancestry.

The independent post-closure audit and Task 15 planning commit
`c4e621d05960a4e2f06cb4864f6a8cb8275ac067` is now the fixed S4 implementation
ancestry. The already promoted `f07b386...` remains the S3/G4 runtime baseline;
the successor adds planning truth only. S4 dispatch must wait until the formal
remote branch contains `c4e621d...` and local/tracking/remote identities are
verified. No implementation worktree has been created and no S4 code has been
merged.

[Task 16](v4/16-s4-parallel-wave-instructions.md) defines four non-overlapping,
capability-oriented lanes:

- A owns the public authoring path, Session-by-default composition, config,
  CLI, scaffolding, lifecycle ownership, and public-surface budget;
- B owns the canonical model transaction, modern message/reasoning/tool rounds,
  context/memory/compaction/artifacts, provider conformance, and optional
  bounded live capability evidence;
- C owns Env-only native ACI, ToolRuntime, task-exclusive Docker sandboxing,
  lifecycle/effects, MCP parity, and durable multi-agent execution adapters;
- D owns the single Trajectory candidate, crash-safe store/reader/exporter,
  read-only qita, evaluation, privacy, measurements, extras, and clean-wheel
  consumer qualification.

Quality, documentation, privacy, receipts, and packaging are mandatory gates in
every lane rather than a fifth engineering-only line. A publishes the beginner
API shape; B and C publish independent producers; D prepares strict readiness
but must remain `waiting_on_a_b_c` until G5 consumes exact same-wave bytes. The
planned integration order is A -> B -> C -> D, followed by one G5 repair and
qualification pass. Only G5 may freeze/switch Trajectory defaults, update shared
documentation, promote a baseline, push, or retire the new clean worktrees.

`DEFAULT_BRANCH_READY=false` and `RELEASE_READY=false` remain unchanged.

## G4-R5 framework conformance (2026-09-02)

R5 starts from existing convergence head `0bda057a...` over fixed baseline
`851f7902...`; it does not replay A/B/C/D or create another convergence branch.
The promotion definition now follows the
[framework responsibility boundary](architecture/framework-responsibility-boundary.md):
QitOS guarantees runtime correctness, but not task success for every
Agent/model.

The candidate binds and clears the reusable Engine cache for each Session,
retains direct-fork history only through explicit snapshot lineage, rebases
fan-out/delegate children to the child task plus accepted context-transfer
selection, and persists one effective request budget from descriptor through
restore and pre-dispatch admission. Canonical ToolResult/environment facts stay
separate from bounded, redacted model projections with loss receipts. Provider
encode, request projection, transport/status, and decode stages now retain a
closed safe failure code and accurate request-sent fact.

The required committed-bytes repository, deterministic 100-round isolation,
40-round process-loss, Docker, privacy, packaging, wheel, and exact-source gates
remain the authority for promotion. One GLM smoke of at most three requests is
reported separately as `LIVE_AGENT_CAPABILITY_MATRIX=informational`; a typed
provider/model outcome does not block promotion unless it exposes a framework
invariant failure. Historical live receipts remain immutable.

Code qualification head `901e972ddbaafd2f4e99d95e664ed377ffb254c9`
passes `2436 passed, 50 skipped`, the 367-finding zero-growth static ratchet,
stable lint/type, packaging/twine, wheel config/Session smoke, architecture,
public-interface, privacy/path, Docker cleanup, 100-round Session isolation,
and 40-round multi-agent process-loss gates. Informational GLM round
`s3-g4-l3-a1146482fb3295ff` issued two real requests against a limit of three;
durable and outer counters both report 2, the RequestView is Session-isolated,
native tools are expressible, and Trajectory/qita/cleanup/privacy all pass.
The model returned typed `malformed_structured_response`, so the Session
correctly ended `failed`; this is an informational model outcome with
`framework_invariant_failure=false`. DSV and Qwen were not re-requested in R5.
The main worktree fast-forwarded from `851f7902f15da670e72f4c04d7453cf37201aee7`
to qualification/evidence head `1915c299ad8cd74314369b6635df63e96099796f`.
The post-promotion focused 418-test gate, four dedicated conformance tests,
full `2436 passed, 50 skipped` suite, static/lint/type, build/twine,
privacy/path/diff, and Docker-zero checks all passed. The first non-force push
was verified at that SHA with local/tracking/remote divergence 0/0.

All five clean S3 worktrees were then removed non-forcibly in A/B/C/D/G4
order and pruned: registered worktrees changed from 6 to 1 and 3,384,888 KiB
(3.23 GiB) was released. Local branch-ref count stayed 33, including all five
S3 lane/convergence refs. The docs-only commit containing this closure record
is the unique S4 dispatch baseline once its second non-force push is verified;
there is no earlier candidate baseline. `S3_STATUS=closed`, `G4_STATUS=closed`,
`S4_READY=true`, while `DEFAULT_BRANCH_READY=false` and `RELEASE_READY=false`.

## Independent post-closure audit and S4 disposition (2026-09-02)

The primary checkout was independently verified clean on
`feat/campaign-absorption` at
`f07b38647cf3b18a5235581224a1153b88fac397`. Its tracking ref and
`git ls-remote` result match with divergence `0/0`; only the primary worktree is
registered, while all five S3 lane/convergence branch refs remain reachable.
The code qualification head `901e972...` and promoted evidence head
`1915c299...` are ancestors of the final baseline. The committed live runner's
SHA-256 is `c673ad3a62276c1a4f6fd7288250a877681b8753374f140d5115a5c6687e5034`,
matching the redacted R5 receipt.

Source review confirmed that each Session binds and clears reusable Engine
state, child work is rebased from explicit transfer facts, model-request
admission advances the durable counter before transport, large canonical tool
and environment facts use bounded loss-explicit model projections, and provider
encode/projection/transport/decode failures retain typed non-echoing stages.
An independent 153-test matrix over configuration/provider transport, model
projection, provider adapters, ToolResult, live-qualification decisions, and
durable WorkGraph runtime passed in 10.90 seconds on Python 3.12.7. After the
documentation corrections, 24 architecture/workflow/path/public-interface
tests passed, the static ratchet passed with 367 existing findings (345 active,
22 vendored/generated), the full suite passed with `2436 passed, 50 skipped`,
and `git diff --check` remained clean.

The R5 live GLM outcome remains correctly classified as informational:
`malformed_structured_response` ended the Session as failed after two exactly
accounted requests, while isolation, budget, Trajectory/qita readability,
sandbox cleanup, and privacy invariants remained true. QitOS is responsible for
that truthful behavior, not for forcing every model to complete an Agent's
task.

The audit found documentation-state drift rather than a runtime blocker: the
playbook, Tasks 12–14, S3 wave, and L3 evidence headings still described
historical blocked candidates after the final promotion. Their current status
is corrected while the immutable failure sections remain provenance. The next
work is now defined by
[`Task 15`](v4/15-public-framework-graduation.md). S4 must converge the current
mechanisms into one default-safe authoring path, complete sandbox and extension
qualification, freeze and roll out Trajectory/qita, and close packaging/docs
gaps. No S4 implementation lane has started. `DEFAULT_BRANCH_READY=false` and
`RELEASE_READY=false` remain unchanged.

## G4-L3 stable config/sandbox/live closure (2026-09-01)

G4-L3 continues in the existing `codex/v4-s3-g4-convergence` worktree from
starting candidate `904df84f...`, whose merge base with the fixed integration
baseline is exactly `851f790...`. It does not replay A/B/C/D or open a second
convergence branch.

The candidate now canonicalizes public configuration as `qitos.agent` (with
`qitos.agent/v1` reader-only compatibility), keeps normalized configuration
deeply immutable, and binds a deterministic secret/path-free digest through
launch, Session restore, and Trajectory provenance. Resolved protocol owns the
parser/codec/tool-choice route. Tool-use policy is explicit and typed.

Coding launches now use a structural sandbox protocol with an inspect-backed,
fail-closed Docker reference and explicit unisolated `unsafe_host` opt-out.
Configured Trajectory sinks receive actual Engine/Session/WorkGraph records and
are read by the existing Trajectory reader/qita path. A formal configured
single-agent Docker pause/fresh-process-restore workflow and the existing
40-round multi-agent process-loss workflow pass. The full suite reports `2393
passed, 50 skipped`; static quality, stable lint/type, package/twine, interface,
architecture, privacy, permission, and diff gates also pass. The committed
runner preflight passed all 16 nodes. Fresh live round
`s3-g4-l3-71564b10447bf692` then stopped in GLM before provider dispatch:
codec projection rejected a nested immutable `mappingproxy` as non-JSON, so the
Session did not reach pause. The exact request ledger is zero; DSV and Qwen were
not started. Docker attestation/cleanup and privacy passed. Promotion, push,
and cleanup are blocked, and the immutable L2 failure remains historical. See
[`s3_g4_l3_qualification_evidence.md`](internal/plans/s3_g4_l3_qualification_evidence.md).

R1 repairs subsequently established one bounded JSON transport materializer,
non-echoing root failures, terminal failed Sessions, recovered-boundary pause,
and parent-Session-scoped live fork identities. Committed head `0f1435c...`
passed a fresh `2415 passed, 50 skipped` full suite and every static, package,
sandbox, permission, privacy, cleanup, fake-transport, single-process, and
40-round multi-agent gate. Round `s3-g4-l3-739e066ca1e8172a` proved the GLM
single-agent edit/test/pause/clean-process-restore/final/Trajectory/qita route,
then its first multi-agent child ended with `provider_transport_failure`. The
GLM ledger was exactly 12/12, so the second child, DSV, and Qwen were not
started. No same-source rerun, promotion, push, or worktree removal is
authorized; all branch refs and immutable receipts are retained.

## 0. S3 deterministic convergence candidate (2026-09-01)

### G4-L2 canonical launch checkpoint

The sole declarative authority is now strict `qitos.agent/v1`, consumed by both
`qit run --config` and the Python composition API. Credential values live behind
typed resolvers and never enter canonical config, Session snapshots, public
receipts, or Git. All nine model-bearing official templates use logical
references; the three orchestration-only templates remain intentionally
unchanged. The previous Markdown/env-driven live runner is no longer execution
truth.

The authoritative pre-live run passed all sixteen gates with zero provider
requests. Those gates include strict/security/resolver tests, native single and
parallel tool continuation, twenty-round deterministic Session continuity,
fresh-process single and multi-agent restore, a real uniquely labelled Docker
inspect/probe/cleanup round, and a fake-provider Agent workflow through the same
Env tool surface. Private launch sources and credentials remain outside Git;
committed evidence contains only logical identities and digests.

The three-provider preflight subsequently completed with real typed outcomes:
DSV4 and GLM passed single/parallel native tools and continuation; Qwen reported
`capability_loss`. The required Agent workflows did not pass. DSV4 exposed a
created-Session restore defect and later `unrecoverable_error`; GLM restored a
single Session and two distinct children but did not route a real tool, while a
native-protocol projection stopped at `budget_steps` with the disposable tests
still failing. Observed requests were 9/13/4 respectively, so GLM exceeded its
12-request cap. `G4_LIVE=workflow_failure`; no further live request, promotion,
push, or worktree cleanup is authorized.

### Historical G4-L credential blocker (superseded by G4-L2)

This section preserves the earlier G4-L attempt as provenance; it is not the
current launch architecture or gate state. The exact live budget was accepted and the bounded qualification runner was
added at `e3a4b86ad10496f1e6ee98b4cfb92fffafd58c59`. It parses the three
registered profiles from the internal matrix, requires explicit profile plus
`--live`, uses zero automatic retries, counts only provider-native
`tool_calls`, and cannot send a request without both external private evidence
storage and a passing redacted sandbox attestation.

All three allowed credential references were absent. The authoritative command
exited 2 with three `configuration_blocked:credential_missing` outcomes, zero
requests, zero input/output/reported tokens, zero latency, and zero retries.
The credential gate preceded sandbox provisioning, so attestation, cleanup,
single-agent coding, multi-agent/process restore, and live Trajectory collection
did not run. This is not an unavailable skip and qualifies no model capability.

Consequently `S3_STATUS=blocked_live_qualification`,
`G4_LIVE=configuration_blocked`, `S4_READY=false`,
`FEATURE_BASELINE_PROMOTED=false`, and `DEFAULT_BRANCH_READY=false`.
Deterministic G4 remains a separately qualified candidate. No fast-forward
promotion, push, release, default-branch change, or S3 worktree retirement is
authorized. See the redacted
[`live summary`](internal/plans/s3_g4_live_qualification_summary.json) and
[`execution evidence`](internal/plans/s3_g4_live_qualification_evidence.md).

The convergence branch replayed the verified A/B/C/D source branches strictly
in that order from `851f7902f15da670e72f4c04d7453cf37201aee7`. It repaired B's
stale producer digest, replaced C's placeholder IDs and callable scheduler
payload with real A fork receipts, real B transfer receipts, and reconstructable
JSON-only work descriptors, then requalified D against both the immutable
source-lane heads and the committed replay/repair bytes actually executed.

The deterministic G4 test passed twenty independent SQLite graph process-loss
rounds plus twenty declaration/preparation-crash rounds.
Each round terminates the original process abruptly, restores through a fresh
Engine/runtime composition, retains completed work, dispatches only eligible
queued work with its original operation identity, marks missing running work
`outcome_unknown` without replay, closes a quorum join once, rejects duplicate
and late outcomes, preserves one handoff owner, and exposes graph/timeline facts
through read-only qita inspection. Two unrelated consumers and the compact
coding-agent public-shape example also pass.

This is a candidate, not a promoted baseline. Three provider/model profiles are
registered with endpoint-specific external credential references, but no secret
is repository state. The subsequent G4-L attempt accepted the budget and
stopped with three typed missing-credential outcomes before any request;
preflight, trajectory, and disposable-agent receipts therefore remain absent,
and `live_model_qualification=configuration_blocked`. No main-branch update,
push, release claim, or worktree cleanup is authorized.
Candidate Trajectory remains unfrozen and off by default; qita remains on frozen
trace-v1 compatibility; distributed scheduling, hard cancellation, and
exactly-once external effects
remain unsupported. Exact replay and gate evidence is recorded in
[`s3_g4_convergence_evidence.md`](internal/plans/s3_g4_convergence_evidence.md),
and the credential-free live profiles and execution gate are recorded in
[`s3_g4_live_model_matrix.md`](internal/plans/s3_g4_live_model_matrix.md).

The live runner's per-response output ceiling is planned at 10,240 tokens, with
separate request-count, total-usage, timeout, and stop-policy bounds. Live agent
work must not run in the primary checkout. Until Task 14 is implemented, it must
use an equivalent task-exclusive, network-denied, non-root, narrowly mounted,
pre-attested Docker harness with no host fallback.

The current `DockerEnv` is a useful native Docker execution backend, but it is
not a qualified untrusted-code sandbox. A reference-harness audit showed that
research/coding agents need task-exclusive provisioning, exact mount/user/
network/tmpfs/tool/socket attestation before the first model request, all tools
routed through Env, controller-held secrets/private authority, input/contamination
digests, and task-owned cleanup. Task 14 now makes this the framework's safe
default design and adds typed resource policy, private workspace staging,
Session/WorkGraph ownership, stronger local runtimes, independent adapters, and
executable escape/egress/resource/cleanup gates. The supporting comparison is
recorded in [`sandbox_runtime_research.md`](internal/plans/sandbox_runtime_research.md).

## 0.1 S2 promotion closure and S3 entry (2026-08-31)

S2 is closed. The G3 candidate was fast-forwarded into
`feat/campaign-absorption`, its required primary-checkout gates were repeated,
and the branch was pushed. Local HEAD, tracking ref, and `ls-remote` were all
verified at `3af0ee3b2c3b5b5575e4e07cc31ff7f652327ba7` with `0/0`
divergence. The integration checkout was clean, every previous-wave non-primary
worktree was retired without force, and the retained branch/commit refs remain
reachable.

The durable single-agent vertical and clean-process restore are qualified. The
S3 entry gate is therefore satisfied, but S3 runtime implementation has not
started: Session fork, context/authority transfer, a durable multi-agent
scheduler, child recovery/join execution, and work-graph qita inspection remain
open. Trajectory v2 is still unfrozen, its candidate writer remains off, and the
candidate trajectory reader is not qita's default. The executable S3 contract
is [`s3_durable_multi_agent_wave.md`](internal/plans/s3_durable_multi_agent_wave.md).

### S2 G3 runtime vertical convergence (pre-promotion evidence)

The fixed integration source was
`47cd4dc5e1ed1b2b0d244bfc90fac031ec55be32`. G3 replayed the nine lane commits
strictly A -> C -> B -> D, then closed the vertical blockers without adding a
second Engine loop, executor, SessionStore, provider transaction path,
ArtifactRef, or trajectory truth.

- one checkpoint-backed Session head now captures the Engine-owned conversation
  and tool-batch components and advances every terminal slot by owner/generation
  CAS before reporting persistence;
- pause reaches the existing executor's condition/event quiescence barrier and
  cannot persist `PAUSED` while a framework worker can still advance the owner;
- fresh-process recovery closes the original batch before reduce/model, skips
  committed/terminal slots, refuses unknown outcomes, and runs only eligible
  missing work with original identities;
- the tracing-local ArtifactRef was removed; the repository has one canonical
  framework class in `qitos/core/artifact.py`;
- Engine and Session facts bridge into the one extension-facing EventSink;
  qita inspection stays read-only on the frozen trace compatibility default;
- the current interface budget remains 41 root exports and 101 classified
  aggregate exports. The 34th Engine parameter (`runtime`, including `self` in
  the count) is a reviewed migration entry with a contraction route.

The deterministic SQLite E2E ran twenty independent parent/child process rounds
using Event barriers and an offline provider. Every round restored reasoning and
continuation, applied steering once, retained the artifact/budget/trajectory
cursor facts, rejected the old owner, executed only the missing eligible slot,
and kept the committed-effect counter at one.

Exact-source A/B/C receipts bound to producer commit
`42d6821e4ceee7a09d3dda9011e687a8cb64f5ba` qualify all twelve runtime facts:
`s2_runtime_ready=true`. This does not qualify the candidate Trajectory schema
or publication (`false`), enable its writer, migrate qita, implement the S3
persistent child scheduler, add agent-authoring sugar, or establish external-
world exactly-once effects. At the time this pre-promotion evidence was written,
promotion, primary-checkout reruns, push, and worktree retirement were
conditional on the final gate matrix; the promotion closure above records their
subsequent completion.

## 1. Purpose and maintenance rule

This file is the integration owner's continuously growing record for the v4
program. Lane plans and completion reports remain evidence, but they do not
change integration status by themselves.

Maintain it with these rules:

- record the exact source commit for every reviewed package;
- distinguish agent-reported validation from integration-owner reruns;
- do not mark a package integrated until its commits are present in the
  integration branch and the integrated gates pass;
- keep review findings until a fixing commit and regression test close them;
- append dated validation/integration entries rather than replacing historical
  evidence;
- update the current dashboard and next merge sequence after every accepted
  package.

## 2. Current decision

**G2 CLOSED; S2 CLOSED; S3 ENTRY GATE SATISFIED.** The historical fixed lane dispatch
baseline remains `446a347d1ac73636476ca2515a01da601b567c68`. The integration
source for G3 was `47cd4dc5e1ed1b2b0d244bfc90fac031ec55be32`; all A/C/B/D
producer commits were replayed in the required order before convergence.

The [`S2 runtime wave`](internal/plans/s2_runtime_wave.md) now has an executable
single-agent Session vertical, exact-source runtime receipts, and fully passed
branch and primary-checkout qualification matrices. Promotion, push verification,
and worktree retirement are complete at `3af0ee3...`. There is no persistent
child scheduler, provider-default flip, default Trajectory writer/store or
candidate reader, qita migration, authoring sugar, or external exactly-once
claim. S3 lanes must use the complete remote SHA from the S3 dispatch closure,
not the historical S2 baseline or G3 source.

### G2-R2 repair qualification (pre-promotion)

The 29 candidate commits were replayed in source order onto fixed dispatch
baseline `8e17b1f6471a89a52aacec74a55f41386d44559a`. The first 28 applied
directly; the final documentation commit was resolved across nine shared
documents while retaining the later audit, worktree-retirement policy, real
candidate capabilities, and the fact that S2 has not started. Replay HEAD was
`a68b281c2b79cf26252801bf06c6a6f2a9fb5d3a`.

Independent repair commits are:

- `3f2bde6` — exact historical ToolResult grammar and mixed-schema rejection;
- `0efa496` — typed ProviderCapabilities constructor/reader/adapter validation;
- `0dad384` — shared non-echoing diagnostics, ProviderFailure, ArtifactRef,
  ToolResult/readiness, and WorkGraph safety;
- `abfd89d` — semantic interface budget: 124 deliberate module exports, three
  implementation-private helpers, and zero root/Engine growth;
- `00e9981` — committed current ToolResult and nested ExchangeLog writer bytes
  with independent consumers;
- `49fa15b` — 21 distinct historical/current/bundle receipts with exact
  source/replay lineage and independent consumer bindings.

Repair-tree qualification used Python 3.12.7, flake8 7.0.0, mypy 1.19.1,
pyflakes 3.2.0, pycodestyle 2.11.1, and mccabe 0.7.0. The 291-test focused
contract/architecture/public/no-local-path gate passed; the 399-finding ratchet
remained exactly 377 active plus 22 vendored/generated; stable flake8 passed;
stable mypy passed on 84 files; and the complete suite passed `2104 passed, 50
skipped`. Readiness without receipts exited 0 at 0/21 with 21 receipt findings;
exact-receipt dry-run exited 0 at 21/21 with zero receipt findings; normal
exact-receipt execution exited 2. All three remained `schema_not_ready`, and
the exact modes retained 11 non-contract blockers with empty measurements and
claims. `git diff --check` passed and the repair tree was clean.

### Promotion and worktree-retirement receipt

The primary branch was still clean at exact dispatch SHA `8e17b1f...` before a
`--ff-only` promotion to `c0f19cd...`. The primary checkout then repeated the
291 focused tests, 399-finding ratchet, stable flake8/mypy, `2104 passed, 50
skipped` full suite, all three readiness modes, and `git diff --check` with the
same results as the repair tree.

Before retirement, Git registered 18 worktrees: the primary checkout plus 17
explicit retirement targets. Every target was clean, unlocked, idle, and on a
retained local branch ref. Their measured total was `11,287,672 KiB` (10.765
GiB). Removal used only `git worktree remove <exact-target>` without
`--force`, followed by `git worktree prune`.

| Retired worktree | Retained branch | Recorded HEAD |
|---|---|---|
| G1 convergence | `codex/v4-g1-convergence` | `c1efb0f4adde3e673bf181af5b1760c19a451ae2` |
| G1 final | `codex/v4-g1-final-baseline` | `c1efb0f4adde3e673bf181af5b1760c19a451ae2` |
| G1-R4 | `codex/v4-g1-r4-secret-scalars` | `c1efb0f4adde3e673bf181af5b1760c19a451ae2` |
| G2 candidate | `codex/v4-g2-contract-convergence` | `cab8fd246d2485784a13558e668eadb3ffa4d42f` |
| Lane A | `codex/v4-lane-a-quality-ratchet` | `ab25edf9c6457ee40054aaaab4596d7bed30cbe5` |
| Lane A2 | `codex/v4-lane-a-ci-trust` | `ec43f09c1d6926a146b2c3f80a4b351861c5ea87` |
| Lane B | `codex/v4-lane-b-exchange-contract` | `69a961f6f50656dff308db7a2f3e400439ef20d0` |
| Lane B2 | `codex/v4-lane-b-exchange-integrity` | `5b0e8d54ab9dc95746b9e30fb2ce97a6165f0390` |
| Lane C | `codex/v4-lane-c-outcome-lifecycle` | `1a36349b425e8c39d87b89e71ad4dcabd23d9e30` |
| Lane C2 | `codex/v4-lane-c-contract-hardening` | `86ad165cef56262d0d5b58e095a1452f8201bc79` |
| Lane D | `codex/v4-lane-d-data-census` | `ad03cb0b63c62e2067a222d654f3879ba7c01bb5` |
| Lane D2 | `codex/v4-lane-d-evidence-gates` | `d80f4cc7e7c1532c33ea0cf057435447bf9261e7` |
| S1-A | `codex/v4-s1-a-session-contracts` | `cb79532d45b114826ee4313a60bf42ebc5abca06` |
| S1-B | `codex/v4-s1-b-request-view` | `939edd0164a7f1929818f3e79bea02f2635a9d7d` |
| S1-C | `codex/v4-s1-c-work-graph-contracts` | `61c85ab774705610a2edf039417a8480afbeee16` |
| S1-D | `codex/v4-s1-d-lineage-intake` | `44a09e3cbfaa29978584a05fbafbdd5c37cd7f2f` |
| G2-R2 | `codex/v4-g2-r2-promotion` | `c0f19cd8f19a223fc84844f8a6a0ae4a5d0145aa` |

After prune, Git registers only the primary worktree, all 17 recorded branch
refs resolve, and the retired worktree disk total is zero. The remaining
primary checkout measured `701,380 KiB`. The promoted contract code head is
`c0f19cd...`; the independently qualified and remotely verified S2 dispatch
baseline is `446a347d1ac73636476ca2515a01da601b567c68`.

### Documentation truth closure verification

The fixed dispatch baseline and its documentation-only successor were
independently checked with `2104 passed, 50 skipped`, the 399-finding ratchet
(377 active and 22 vendored/generated), clean stable flake8, and clean stable
mypy over 84 files. Readiness remained honest: 0/21 without receipts, 21/21
with exact receipts, and exact normal mode exited 2 with 11 S2/runtime/
Trajectory blockers and no measurements or claims. Before the ledger-only
successor worktree was created, local and remote divergence was `0/0`, Git
registered one primary worktree, and all 17 retired-worktree branch refs
resolved.

### Historical pre-G2/S1 audit context

The following paragraphs and lane table preserve the pre-G2 audit decision.
They are historical evidence, not the current integration or dispatch state.

The A -> C -> B -> D convergence tree and the bounded G1-R3/R4 repairs are
integrated at `5ef8ab657f6452ae48c931beea79106e2cca34c6`. C-P3 collision-safe key
projection and C-P4 role-aware scalar projection are both closed. Secret-bearing
content redacts every JSON scalar leaf, trace-safe omitted data preserves only
validated counts, canonical persistence remains lossless, B delegates directly
to C, and D binds the exact current C producer artifacts.

The integration owner independently re-audited the promoted R4 tree on
2026-08-30. The scalar role matrix, committed digests, receipt identity, 168
combined tests, `1872 passed, 50 skipped` full suite, 399-finding ratchet,
stable flake8/mypy, tool qualification, architecture/public-surface checks, and
all three readiness modes passed. No new G1 blocker was reproduced.

Gate G1 remains **closed**. Four S1 contract candidates have now been delivered
from the reviewed dispatch baseline. Their branches are individually green and
an isolated A -> C -> B -> D merge is textually clean, but they are not a single
qualified architecture yet. No S1 code is present on the integration branch and
no pause/restore, provider-dispatch, persistent work-graph, trajectory-writer,
or qita behavior exists.

The independent S1 review passed 173 focused tests and the combined full suite
(`1999 passed, 50 skipped`), the 399-finding ratchet, stable flake8/mypy on 81
files, and diff checks. It also reproduced cross-lane blockers that branch-local
tests cannot see: C does not yet use A's typed identities; A/B/C snapshot
component ownership and schema adaptation are unresolved; B and C disagree on
`ArtifactRef`; C changed ToolResult writer bytes under the old schema identity;
provider and WorkGraph diagnostics can echo secret/host-path-bearing input; D
still reports all 17 S1 producers as unestablished; and the module-level
`__all__` surface is much larger than the claimed beginner API budget.

The next authorized work is one integration-owned G2 convergence task in
[`docs/internal/plans/g2_contract_convergence.md`](internal/plans/g2_contract_convergence.md),
not four independent repair branches. Its fixed semantic order is A -> C -> B
-> D. The S1 source ancestry baseline remains `c1efb0f...`, while the G2
worktree must start from the later integration-owner dispatch SHA that contains
this audit and plan; the task instruction supplies that exact SHA.

The convergence report's provenance wording is also corrected: all 26 reviewed
source commits were applied by ordered cherry-pick, but the original source SHAs
are not ancestors of the convergence HEAD. Eighteen integrated commits are
patch-id equivalent; eight documentation/evidence commits were conflict-resolved
and therefore have new, non-equivalent patch identities. The resulting code and
evidence are present, but source identity was not literally preserved.

The v4 architecture now explicitly includes Codex-like durable sessions,
process-independent pause/resume/fork, and a native durable multi-agent work
graph. This is a planning decision, not an implementation claim and not a reason
to bypass G1. Existing `init_session`, `RunState`, checkpoint v2,
interrupt/resume, handoff, delegate, and fan-out paths are recorded as useful but
fragmented primitives. The next capability phase converges them into one
checkpoint-backed session truth and one generation-checked work graph.

| Lane | Integrated fixing HEAD | Package | Integration disposition | Next package |
|---|---|---|---|---|
| A | `cb79532d45b114826ee4313a60bf42ebc5abca06` | Session identity/snapshot candidate | Source reviewed; individual gates green; not integrated | First G2 producer; repair component envelope |
| C | `61c85ab774705610a2edf039417a8480afbeee16` | Effects/WorkGraph candidate | Source reviewed; `waiting_on_lane_a`; not integrated | Consume typed identities; repair ToolResult evolution |
| B | `939edd0164a7f1929818f3e79bea02f2635a9d7d` | Request/codec/context candidate | Source reviewed; `waiting_on_lane_a`; not integrated | Converge ArtifactRef, snapshot and capability boundary |
| D | `44a09e3cbfaa29978584a05fbafbdd5c37cd7f2f` | Lineage/readiness candidate | Source reviewed; 17 S1 requirements remain unestablished | Integrate last and bind exact producers |

## 3. Source and validation evidence

All four branches have merge-base
`fb75cd5902fedf50d5e67dd617e62cd981c3128f`, the W1 integration baseline.
Their worktrees were clean when reviewed.

| Lane | Worktree | Agent-reported full suite | Integration-owner targeted rerun |
|---|---|---:|---:|
| A | `WhitzardOS-lane-a` (local sibling) | 1,703 passed, 50 skipped | 17 passed |
| B | `WhitzardOS-lane-b` (local sibling) | 1,714 passed, 50 skipped | 28 passed |
| C | `WhitzardOS-lane-c` (local sibling) | 1,714 passed, 50 skipped | 28 passed |
| D | `WhitzardOS-lane-d` (local sibling) | 1,696 passed, 50 skipped | 107 passed |

The targeted reruns covered each new contract/scaffold plus architecture and
public-surface gates. `git diff --check` passed for every lane diff. The current
integration-owner shell uses Python 3.13.3 and does not have the pinned flake8
distribution, so it could not independently rerun Lane A's Python 3.12.7
ratchet. This is an environment limitation, not a replacement for the reported
ratchet result; the pinned command remains an integration gate.

The convergence-wave review used the shared integration baseline
`8441bef2f2024fd6c2ec01784708512222382471`. All four worktrees were clean and
their reported HEADs matched the commits reviewed.

| Lane | Worktree | Agent-reported full suite | Integration-owner targeted rerun |
|---|---|---:|---:|
| A | `WhitzardOS-lane-a2` | 1,720 passed, 50 skipped | 34 passed; separate executable import probe failed |
| B | `WhitzardOS-lane-b2` | 1,720 passed, 50 skipped | 34 passed |
| C | `WhitzardOS-lane-c2` | 1,756 passed, 50 skipped | 277 passed; separate boundary probes failed |
| D | `WhitzardOS-lane-d2` | 1,720 passed, 50 skipped | 34 passed |

The reruns covered ratchet/workflow contracts, ExchangeLog, ToolResult and
structural validation, Engine action execution, trajectory readiness,
exact-source evidence, architecture boundaries, and public surface. Diff checks
passed for all four reviewed ranges. Pairwise merge-tree simulation found
content conflicts in `CHANGELOG.md`, `README.md`, and `README.zh.md` for every
lane pair; no other textual conflict was reported. These documentation conflicts
must be hand-merged, but they are secondary to the semantic blockers below.

## 4. Historical review findings

This section preserves the blockers as they were discovered in the first and
convergence-wave branch reviews. Their old “open” wording is audit history, not
the current dashboard. The fixing commits and the new C-P3 disposition are
authoritative in Sections 2, 5–7, and the append-only entries below.

### 4.1 Lane A — quality ratchet

What is sound:

- the full-package diagnostic is separate from the zero-debt stable-surface
  checks;
- finding identity does not depend on line number alone;
- stale allowances, new findings, malformed diagnostics, expired exceptions,
  and toolchain drift have explicit failure paths;
- CI does not mask the new jobs with `|| true` or automatic reruns;
- no runtime, public API, or packaging semantics changed.

Open follow-up `A-Q1` (non-blocking for initial integration):

- `tests/test_static_quality_ratchet.py` tests parsers, identity,
  classification, exception fields, and toolchain mismatch, but the committed
  unit suite does not directly exercise `check()` for new findings, stale
  allowances, base-ref growth, and bootstrap/base-ref failure. The manual F401
  probe is good evidence; A2 should turn the critical ratchet transitions into
  deterministic tests.

Disposition: integrate A1 first, resolve the three shared documentation files,
install the pinned toolchain, and run `python scripts/static_quality.py check`
against the integrated tree before publishing the new baseline as active.

### 4.2 Lane B — conversation contract

What is sound:

- ordered assistant parts retain content, reasoning references, and tool calls;
- raw versus parsed arguments and provider-scoped call identity are explicit;
- out-of-order completion is correlated by call ID and projected in declaration
  order;
- mid-batch steering is queued and opaque continuation is not converted into
  assistant reasoning text;
- the module is not root-exported and does not prematurely modify Engine or
  provider behavior.

Gate blocker `B-C1` — duplicate result semantics:

- `qitos/core/conversation.py::ToolResultStatus` uses `succeeded`, `failed`,
  `permission_blocked`, `timed_out`, `cancelled`, and `missing_worker`;
- `qitos/core/tool_result.py::ToolResult` on Lane C uses `success`, `error`,
  `skipped`, `timed_out`, and `cancelled`, plus `error_kind` and `error_code`;
- `ToolResultItem` stores a second content/status/provenance result envelope
  rather than carrying or adapting the canonical outcome.

Task 02 and Task 03 cannot both call these representations canonical. Lane C
owns the execution outcome. Lane B must consume that outcome and keep only
conversation-specific call/batch/closure identity.

Gate blocker `B-I1` — append-only integrity is not enforced:

- frozen dataclasses contain mutable lists and dictionaries;
- `ExchangeLog.items` returns the internal item objects inside a tuple;
- a caller can append to `UserItem.content` or mutate `metadata`, changing a
  previously committed fact without an `append()` call. A reviewer probe
  changed a one-block committed item into two blocks through the returned
  object and the serialized log reflected the mutation.

Gate blocker `B-P1` — the safe projection name overclaims privacy:

- `OpaqueContinuationAttachment.to_safe_dict()` redacts only
  `opaque_payload`;
- ordinary item metadata, tool arguments, result content, and provenance
  details pass through unchanged;
- a reviewer probe placed `{"token": "secret"}` in item metadata and
  `ExchangeLog.to_safe_dict()` returned it unchanged.

This method may be a continuation-redacted diagnostic view, but it is not a
general public/privacy-safe projection until it applies a versioned policy and
returns a loss report.

Gate blocker `B-R1` — partial parallel completion has no durable form:

- `ToolBatchBuilder.record_result()` keeps results only in its private
  `_results` mapping until every slot closes;
- after one of two calls completed, `results_for_batch()` returned zero and
  persistence contained only the assistant declaration;
- a crash/checkpoint between completions therefore loses already completed
  slot facts. Task 02D must not discover this only after Engine migration.

Follow-up `B-T1`: the two claimed independent consumers are two test functions
in `tests/core/test_conversation.py` that simulate Lane C and Lane D. They are
useful fixture tests, but Gate B still requires actual execution and
trajectory/request consumers after cross-lane integration.

Disposition: do not integrate B1 as the accepted canonical contract. Land a
B1-R package that isolates internal state from caller mutation, names or
implements projections honestly, defines crash-safe partial-batch persistence,
and consumes Lane C's reviewed result serialization.

### 4.3 Lane C — tool outcome and lifecycle contract

What is sound:

- the existing `ToolResult` is evolved instead of adding a new top-level
  package;
- `ActionResult` has a named compatibility adapter;
- timeout/cancellation/skip states and `worker_still_running` survive the
  adapter;
- the structural argument gate executes before tool code in the executor and
  standalone registry path;
- the ownership matrix correctly rejects a fake universal lifecycle interface;
- the durability race reproducer explains a real scheduling window without
  changing durability behavior.

Gate blocker `C-P1` — model projection is not a strict safe view:

- `_ActionRuntime._model_visible_tool_result_dict()` and the matching Env path
  replace `output` with `model_output`, but retain `metadata`,
  `normalized_request`, `provenance`, `artifact_refs`, and other canonical
  fields;
- those fields may contain host paths, raw request material, or implementation
  details and are serialized into native tool history;
- the contract text calls `model_output` redacted/bounded, but changing one
  field does not make the enclosing result safe for model delivery.

Add an allowlisted model-view serializer with explicit size/redaction rules;
never reuse the persistence dictionary as the model message.

Gate blocker `C-S1` — the versioned result is not mechanically closed:

- `ToolResult.to_dict()` flattens arbitrary dictionary output keys into the
  top-level canonical payload;
- `ToolResult.from_value()` accepts an explicit
  `qitos.tool_result/v999` payload when its status happens to be known;
- canonical list fields silently drop non-mapping entries;
- contradictory states such as `status="success"` with an execution error are
  accepted.

Keep legacy adaptation permissive at a named compatibility boundary, but make
the `qitos.tool_result/v1` serializer/parser strict and lossless.

Gate blocker `C-V1` — malformed schemas can pass the hard gate:

- an unknown JSON Schema type currently matches every value;
- a string-valued `required` field is silently treated as no requirements;
- reviewer probes returned valid for both cases.

The validator must either support a documented subset or reject an unsupported
or malformed schema with `schema_contract_violation`; it must never interpret
an unknown constraint as permission.

Follow-up `C-D1`: the Lane D handoff calls for a versioned trace-safe redaction
contract. C1 provides prose requirements, not a policy implementation and
fixture that can gate arbitrary keys, values, paths, free-form strings, and
artifacts. D must continue to report this dependency as open.

Disposition: do not integrate C1 until C1-R separates strict canonical,
compatibility, persistence, and model projections and closes validator
fail-open behavior with regression tests.

### 4.4 Lane D — data-plane census and readiness scaffold

What is sound:

- the census distinguishes runtime truth, trace-v1 compatibility truth,
  derived tracing/render planes, and checkpoint durability;
- no v2 writer/store or compression result is fabricated;
- the campaign fixture remains hashes/structure only because license and
  sanitization are not qualified;
- SQLite is not selected as canonical storage;
- the removal ledger does not treat repository grep as proof of external
  disuse.

Gate blocker `D-G1` — the readiness checker is a shallow inventory, not a
publication gate:

- `_load_manifests()` checks only that JSON is an object;
- readiness checks source class and status but not manifest version, unique
  fixture ID, license decision, sanitization receipt, hash shape, portability,
  coverage, or unexpected fields;
- the result always reports B/C contracts as unversioned and has no input
  mechanism for verified contract receipts.

Keep `TRAJECTORY_SCHEMA_NOT_READY`, but validate the source-manifest schema and
make every required contract/sanitization gate machine-checkable before 05A can
freeze a schema.

Gate blocker `D-P1` — readiness output can publish a host path:

- `build_readiness_result()` emits `fixture_root.as_posix()`;
- invoking the documented script with an absolute fixture path returned the
  full host-local worktree path even though the same plan requires public
  fixtures and receipts to reject host-local paths.

Report a logical fixture identifier or repository-relative path in portable
evidence.

Correction `D-E1`: census row D15 names
`qitos/core/action.py::{ActionResult,ToolResult}`. `ToolResult` lives in
`qitos/core/tool_result.py`; the exact-source record must be corrected before
the census is integrated.

Dependency status: B has supplied ExchangeLog fixtures and C has supplied
ToolResult/receipt fixtures, but they do not yet form one compatible,
privacy-qualified contract. RequestView, CodecReport, ArtifactRef, compaction,
durability behavior, hook failure fields, and executable redaction remain open.
Trajectory 05A schema freeze is therefore still blocked.

Disposition: preserve the census and source manifests, harden the readiness
validator and portable evidence, correct D15, then rebase onto the accepted B/C
contracts. Do not start a v2 schema merely because fixture filenames now
exist.

### 4.5 Convergence-wave re-review

The earlier findings remain historical evidence. This section records which
ones the repair branches actually closed and which new boundary probes prevent
integration.

#### Lane A — ratchet improved; executable CI still broken

Closed from the first review:

- `A-Q1`: twenty deterministic tests now exercise new/stale findings,
  base-reference growth, exceptions, expiry, bootstrap, rules upgrades, and
  explicit update behavior;
- the required/advisory/stale ownership table and workflow path repairs are
  documented without claiming knowledge of GitHub branch protection.

New blocker `A-CI1`:

- `.github/workflows/contribution-test.yml` imports `ToolSpec` from
  `qitos.core.tool_schema`;
- the class is defined and exported from `qitos.core.tool`, and the workflow's
  exact import raises `ImportError`;
- `tests/test_workflow_contracts.py` parses YAML and checks paths/tokens, but
  does not execute or import-check embedded Python, so all 34 targeted tests
  pass while the job itself fails before validating any schema.

Disposition: keep A first in merge order, but require A2-R to move non-trivial
inline code into a repository script or otherwise execute it in tests. Correct
the import and prove that the schema check discovers real registered/class tool
specs rather than merely walking modules without assertions.

#### Lane C — strict parser improved; the safe boundary is incomplete

Closed from the first review:

- the canonical parser now rejects unknown versions/fields, malformed lists,
  contradictory terminal states, and non-JSON canonical values;
- legacy flattening is explicit, model fields are allowlisted, and unsupported
  schema keywords/types fail closed;
- argument validation is repeated after permission/interceptor rewriting.

New blocker `C-J1` — runtime arguments are not required to be JSON values:

- `validate_tool_arguments({"x": float("nan")}, {"type": "object"})` returns
  valid;
- an arbitrary `object()` under an open object schema also returns valid;
- a declared `number` accepts `NaN`, despite the gate being described as a JSON
  structural boundary.

New blocker `C-I1` — canonical result ownership is aliased:

- construction and `from_canonical_dict()` retain nested caller-owned values;
- `to_persistence_dict()` returns nested output/metadata references rather than
  an isolated JSON tree;
- mutating either the source payload or serialized result changed the existing
  `ToolResult` in reviewer probes.

New blocker `C-P2` — allowlisted projections still leak and under-report loss:

- `tool_name`, `action_id`, and `error_code` are emitted without identifier
  validation or redaction; token-like values and host paths survive unchanged;
- error and recovery-hint strings are redacted, but `to_trace_safe_dict()`
  reports loss counters only from `model_output`, producing zero redactions for
  redacted error/hint content;
- the trace-safe receipt therefore cannot yet qualify Lane D's full redaction
  dependency.

Disposition: C1-R2 must deep-isolate canonical inputs/outputs, reject every
non-finite/non-JSON runtime argument recursively, validate or redact all
model-visible identifiers, and aggregate loss facts across every projected
field.

#### Lane B — Phase 1 integrity is sound; C convergence remains deliberately open

Closed from the first review:

- `B-I1`: append, read, restore, and serialization boundaries now use isolated
  snapshots for nested values;
- `B-P1`: the old safe-name overclaim is replaced by an explicitly
  continuation-only redacted diagnostic projection;
- `B-R1`: each terminal result is appended immediately in completion order,
  partial logs round-trip, missing slots resume, and queued steering commits
  once after final closure.

Still-open blocker `B-C1`:

- `ToolResultStatus` and `ToolResultItem` remain explicitly temporary and still
  encode a second status/content/provenance result representation;
- this was an intentional Phase 1 stop, so B cannot be merged as the canonical
  conversation result contract until it consumes the accepted C serializer,
  model view, status/error mapping, and artifact slot.

New blocker `B-V1`:

- malformed persisted values do not consistently fail with
  `ConversationValidationError`; for example a string-valued item `metadata`
  escapes as a built-in `ValueError` from `dict(...)`;
- Phase 2 must make the versioned external reader mechanically strict while
  keeping any permissive legacy conversion behind a named adapter.

`B-T1` also remains open: the current consumer simulations are useful, but
actual Engine/request and trajectory consumers arrive in later packages.

#### Lane D — strict default blocking is sound; receipts are not yet verified

Closed from the first review:

- `D-G1`: manifest fields, state consistency, publication evidence, identities,
  coverage, receipts, and blocker categories now have typed checks;
- `D-P1`: readiness output no longer emits fixture roots or rejected raw values;
- `D-E1`: D15 exact sources are corrected and D01-D16 symbols are AST-checked.

Remaining blocker `D-R1`:

- a caller can supply any syntactically valid 64-hex digest with
  `qualified=true` and remove the corresponding contract blocker;
- `qualification_authority` is optional, the digest is not resolved against a
  committed B/C artifact, and no producer-owned qualification proof is
  verified;
- this is safe while the default remains blocked and no receipts are supplied,
  but it is not yet a trustworthy cross-lane qualification mechanism.

Follow-up `D-S1`: the JSON Schema file and the stdlib typed validator are two
representations. Current tests compare a few constants but do not prove that
the documented schema and executable validator accept/reject the same fixture
corpus. Add parity fixtures or make one representation generated/authoritative.

Disposition: D1-R may be preserved as a strict blocked scaffold, but D1-R2 must
consume producer-owned receipts bound to exact fixture bytes/versions and a
reviewed authority before any contract becomes qualified.

## 5. Contract convergence and merge order

The historical A -> C -> B -> D order and the G1-R3/R4 repair sequence are
complete. The promoted runtime baseline and all four mirrored worktrees were
independently verified at `5ef8ab657f6452ae48c931beea79106e2cca34c6`.
Shared release documents remain integration-owner leases.

## 6. Historical G2-R2 dispatch decision (superseded)

This section records the next-work decision made before G2-R2 promotion. At that
historical point, the authorized work was the S2 four-lane wave from fixed
baseline `446a347d1ac73636476ca2515a01da601b567c68`. It is superseded by the S3
dispatch contract above.

The G2 candidate is complete but not promoted. Dispatch one G2-R2 owner using
[`g2_r2_promotion_audit.md`](internal/plans/g2_r2_promotion_audit.md). Do not
begin S2 behavior and do not create four parallel repair branches. After the
qualified G2-R2 baseline is promoted, wave closure requires clean, non-forced
retirement of all completed G1, repair-lane, S1, G2, and G2-R2 worktrees on the
explicit allowlist. Branch and commit refs remain; dirty, active, locked, or
unrecorded worktrees block cleanup rather than being forcibly removed. The
current 16 clean non-primary worktrees consume approximately 10.13 GiB.

### Accepted Lane C — C1-R4 / C-P3 and C-P4 projection closure

- recursively sanitizes or replaces mapping keys in model output and nested
  `next_action` arguments; raw host paths, token/header/secret-like text, and
  other sensitive identifiers must not survive as keys; the representation must
  be deterministic and collision-safe so two redacted keys cannot overwrite or
  silently discard values;
- makes trace-safe `omitted` data use an explicitly safe representation instead
  of copying canonical keys verbatim;
- counts key redactions and omitted-field projection losses in aggregate and
  per-field loss facts;
- adds nested probes for host paths and secrets in keys, including model output,
  next-action arguments, trace-safe omitted data, and ExchangeLog delegation;
- preserves canonical persistence bytes and strict readers;
- publishes updated C evidence/fixtures and hands the exact identity to D;
  coding tools, durability, MCP, and Task 13 behavior remain untouched.
- separates secret-bearing content from omitted-count projection so forced
  string/int/float/bool/null leaves are redacted without corrupting counts.

The bounded C repair, B consumer rerun, D receipt refresh, and integrated A
quality gate are complete. The S1 packages were specified in
[`docs/internal/plans/s1_contract_wave.md`](internal/plans/s1_contract_wave.md)
and were dispatched from the final accepted baseline. Their local producer
status does not supersede the G2 blockers above.

### Post-G1 capability remap (S1 candidates delivered; behavior not started)

After the integration owner closes G1, quality becomes a mandatory cross-lane
gate and the four implementation lanes change to:

| Lane | First package | Scope |
|---|---|---|
| A — Session Runtime & Persistence | Task 12A candidate delivered | identity, lifecycle, safe boundaries, one snapshot truth, resolver references |
| B — Conversation, Context & Continuation | Task 02B candidate delivered | RequestView, steering, provider capabilities, snapshot handoff |
| C — Tools & Durable Multi-Agent | recovery + Task 13A candidates delivered | effects/quiescence and work-graph ownership/join contracts |
| D — Trajectory, qita & DX | lineage intake candidate delivered | session/work graph reader census and readiness only; no schema freeze |

S2's required vertical slice is: start -> parallel tools -> pause -> process exit
-> restore through a fresh Engine/composition root -> apply steering once ->
finish, with no duplicate committed effect. Multi-agent behavior starts only
after this single-agent continuity proof. The Task 05 trajectory schema remains
blocked from freeze until Task 12/13 lineage is available.

## 7. Gate checklist

### G1 — trustworthy change surface

- [x] A1 changes are in the integration branch through ordered cherry-picks.
- [x] Pinned full-package ratchet passes on the integrated tree.
- [x] Stable flake8/mypy remain zero-debt.
- [x] B and C use one canonical tool outcome.
- [x] ExchangeLog persistence cannot be mutated through returned references.
- [x] Persistence and model/public projections have explicit privacy contracts.
- [x] D manifests reject malformed, unlicensed, unsanitized, or host-bound
      publication evidence.
- [x] Cross-lane fixtures have actual consumer tests, not labels alone.
- [x] Full suite, architecture boundaries, public surface, and diff checks pass.
- [x] Workflow-owned Python checks are executed by repository tests, not merely
      parsed as YAML strings.
- [x] Tool arguments reject every recursively non-JSON/non-finite value.
- [x] ToolResult canonical serialization has no caller-visible nested aliases.
- [x] Trace-safe loss facts cover every redacted or omitted projected field.
- [x] Model/trace-safe projections sanitize sensitive mapping keys at every
      nesting level, including trace-safe omitted data (`C-P3`).
- [x] Forced-secret content redacts every JSON scalar while omitted projection
      preserves validated non-negative integer counts (`C-P4`).
- [x] Cross-lane qualification receipts bind to reviewed producer artifacts.

### G2 prerequisites and runtime boundary

- [x] C uses A's typed session/work/attempt/agent identities at in-memory and
      serialized boundaries.
- [x] A's envelope has one owner codec per component and real B/C consumers;
      ExchangeLog, steering, and continuation do not have competing slots.
- [x] RequestView, ToolResult, snapshots, and lineage share one ArtifactRef.
- [x] ToolResult has one current writer plus an explicit historical migration
      reader; old and new strict readers do not share a false schema identity.
- [x] Generic provider capability logic contains no provider-name heuristic.
- [x] Provider, WorkGraph, ArtifactRef, receipt, model, and trace diagnostics do
      not echo credentials, common key/token forms, or host paths.
- [x] The 124 deliberate module exports and three private helpers are
      constrained by a reviewed
      beginner/extension/internal interface budget.
- [x] D binds all 17 S1 requirements plus distinct historical/current writer
      evidence to exact accepted producer commits and
      keeps runtime/trajectory readiness independently blocked.
- [x] RequestView and CodecReport are versioned and transport/API-mode aware.
- [x] Provider failures remain typed and cannot become assistant text.
- [x] Contract fixtures preserve partial parallel completion for future
      checkpoint/recovery consumers.
- [x] Contract receipts state continuing-worker timeout and late/stale result
      semantics; persistent execution remains a runtime item below.
- [x] Persistence contracts distinguish accepted, persisted, failed, and
      dropped outcomes; no durable session runtime is claimed.
- [x] Hook/trace incompleteness is represented without recursive failure.
- [x] Session/run/work-item/checkpoint/exchange/tool-call/agent identities are
      distinct and versioned.
- [x] Checkpoint v2 is the only planned session persistence truth; `RunState`
      has an
      adapter/retirement decision and no parallel SessionStore exists.
- [ ] Runtime: a fresh process restores task, concrete state, ExchangeLog, partial tool
      batch, steering, context/artifacts, budgets, owner, and trace cursor.
- [ ] Runtime: generation checks must prevent stale owners and late workers
      from advancing a persisted newer session head.
- [ ] Handoff, delegate, fan-out, spawn, fork, and steering have distinct
      ownership semantics over one durable work graph.
- [ ] Task 05 schema freeze waits for explicit session/work/ownership lineage.

## 8. Append-only integration log

### 2026-08-29 — first-wave branch audit

- Confirmed all four lane branches descend from the W1 baseline and have clean
  worktrees.
- Reviewed their actual diffs rather than accepting completion summaries.
- Re-ran 17 Lane A, 28 Lane B, 28 Lane C, and 107 Lane D targeted tests.
- Confirmed pairwise textual conflicts are limited to README/README.zh and
  CHANGELOG; identified the independent semantic conflicts above.
- Kept all lane implementation commits out of the integration branch while
  review blockers remain open; only this integration-owned review ledger and
  its documentation pointers were committed.

### 2026-08-29 — convergence-wave branch audit

- Verified the exact A2/B2/C2/D2 worktrees, branches, clean status, common
  `8441bef2...` baseline, and reported final HEADs.
- Re-ran 34 Lane A, 34 Lane B, 277 Lane C, and 34 Lane D targeted tests; all
  selected suites passed after correcting one nonexistent path in the supplied
  C validation list to the repository's real test layout.
- Executed reviewer probes that reproduced A-CI1, C-J1, C-I1, C-P2, B-V1, and
  D-R1 rather than inferring them from prose.
- Confirmed the original B integrity/privacy/persistence findings and original
  D strictness/portability/source findings are materially closed.
- Simulated every pairwise merge and recorded the three shared release-document
  conflicts; no lane commit was merged into integration while executable and
  semantic blockers remain.

### 2026-08-29 — durable session and multi-agent architecture expansion

- Inspected the existing Engine session/step API, `RunState`, checkpoint v2,
  interrupt/resume, handoff, delegate, fan-out, trace, and qita ownership paths.
- Recorded that they are fragmented primitives rather than a complete
  process-independent session protocol: checkpoint content and identity are
  incomplete for a fresh-process reconstruction, and child work is not durable.
- Added Task 12 for one checkpoint-backed session head/snapshot model, safe
  pause, clean-process restore, fork, resolver references, and honest effect
  recovery.
- Added Task 13 for distinct handoff/delegate/fan-out/spawn/fork/steer semantics,
  single-owner work items, durable children/joins, budget/capability boundaries,
  and qita graph lineage.
- Remapped post-G1 concurrency to four capability lanes while keeping the static
  ratchet, full tests, architecture/public surface, packaging, and docs parity as
  cross-lane acceptance gates.
- Made G1 closure an explicit prerequisite for implementation dispatch and made
  the clean-process single-agent vertical slice a prerequisite for multi-agent
  behavior and trajectory-v2 schema freeze.

### 2026-08-29 — G1 final convergence provisionally closed (superseded below)

- Created `codex/v4-g1-convergence` in the isolated `WhitzardOS-g1` worktree
  directly from fixed baseline
  `a02ce05e9a364eb484ef339fe5cbd623910cf525`.
- Integrated every supplied source commit in the fixed A → C → B → D order,
  using reviewed heads `ec43f09c1d6926a146b2c3f80a4b351861c5ea87`,
  `86ad165cef56262d0d5b58e095a1452f8201bc79`,
  `5b0e8d54ab9dc95746b9e30fb2ce97a6165f0390`, and
  `d80f4cc7e7c1532c33ea0cf057435447bf9261e7` as ordered cherry-pick sources.
  The resulting integrated commits have new SHAs; later audit records exact
  patch-equivalence and conflict-resolution facts.
- Closed A-CI1 in `f145cbe`: the workflow and tests execute one checked-in real
  tool-schema qualification entrypoint; 61 modules, 74 class definitions, and
  62 qualified/registered class tools passed, while the controlled invalid
  input exited 1 with `invalid_tool_name`.
- Closed C-J1 in `c509bd0` and C-I1/C-P2 in `ab1c501`: recursive JSON admission
  precedes interceptor/permission/tool execution, canonical and legacy result
  values are deeply ownership-isolated, and scalar model/trace-visible result
  values are bounded and redacted. A later adversarial audit reopened the
  stronger all-fields/loss claim as C-P3.
- Closed B-C1/B-V1 in `2e46fc8`: ExchangeLog v2 embeds the sole canonical
  ToolResult, delegates persistence/model/trace views to C, preserves completion
  and recovery semantics, strictly normalizes malformed reads to
  `ConversationValidationError`, and directly consumes C's committed fixture.
- Closed D-R1 in `30c1823`: qualification is derived from an approved authority,
  exact producer commit, committed fixture/evidence paths, current and committed
  SHA-256 bytes, and matching producer-owned evidence. The B/C receipts clear
  only their two contracts; all unimplemented dependencies remain typed blocked.
- Combined qualification passed: targeted suites 20/8/39/24/29/3/35/2/4/4/2;
  stable flake8 clean; stable mypy success on 77 files; full ratchet 399 findings
  (377 active, 22 vendored/generated); full suite 1863 passed, 50 skipped;
  architecture, public-surface, no-local-path, and `git diff --check` clean.
- The initial combined command contained one operator typo for a nonexistent
  `tests/core/test_schema.py` path after three passing suites. No code test
  failed or was rerun; execution resumed at the correct original
  `tests/core/test_tool_schema.py` command and the remaining matrix passed.
- Both trajectory readiness modes remain honestly blocked:
  `schema_not_ready`, zero publication-qualified fixtures, empty measurements
  and claims; dry-run exits 0 and normal execution exits 2. Trajectory v2 remains
  unfrozen.
- Provisional decision at this point in the audit trail: **G1 CLOSED** and S1
  capability-lane dispatch authorized. The independent entry immediately below
  supersedes this decision. This does
  not mark Task 02B, 03B–E, 04/05A, Task 12/13 runtime, provider defaults,
  trajectory v2, qita redesign, packaging migration, or deprecated-surface
  removal as implemented.

### 2026-08-29 — independent post-convergence audit reopens G1

- Verified the convergence worktree was clean at
  `587f34b76245e71fe3362a51dbad40895d7c43c5`, with the fixed baseline as its
  merge base and the documented A -> C -> B -> D integration history present.
- Corrected provenance: none of the 26 original source SHAs is an ancestor of
  the convergence HEAD because the work used cherry-picks. Patch-id comparison
  found 18 exact patch equivalents; eight shared documentation/evidence commits
  were manually conflict-resolved and therefore have new patch identities.
- Independently reran the fixed Python 3.12.7 toolchain: 179 targeted tests,
  tool-schema qualification (61 modules, 74 classes, 62 qualified/registered),
  the 399-finding ratchet, stable flake8, stable mypy on 77 files, and the full
  suite (`1863 passed, 50 skipped`) all passed.
- Independently verified trajectory readiness: normal execution exits 2,
  dry-run exits 0, both remain `schema_not_ready`, measurements/claims remain
  empty, default input qualifies no contracts, and the exact receipt input
  clears only the B ExchangeLog and C ToolResult contracts.
- Reproduced `C-P3`: sensitive host-path and token-like text in mapping keys
  survives `ToolResult.to_model_dict()` and `to_trace_safe_dict()`; nested
  `next_action` argument keys and trace-safe `omitted` keys also survive. The
  corresponding loss counters remain zero because `_redact_value()` processes
  mapping values but preserves keys, while trace-safe `omitted` is copied
  outside the shared projection path.
- Decision: the convergence tree remains a strong integration candidate, but
  **G1 is reopened and S1 is blocked**. Only the bounded C1-R3 repair, dependent
  B/D requalification, and combined gate rerun are authorized next.

### 2026-08-29 — G1-R3 final projection closure accepted

- Started the isolated final worktree directly from clean convergence source
  `acb491bd822baf6ca429e81639aadbde72a626f0`; the official integration source
  was independently clean at
  `a02ce05e9a364eb484ef339fe5cbd623910cf525`.
- Reproduced four pre-fix failures covering sensitive raw keys, omitted loss,
  zero-budget omitted bypass, and ExchangeLog inheritance, then closed C-P3 in
  core commit `94bfe80aae110f6ee7471478e6ab7eabdc13bba1`.
- Accepted C producer `d50f41fb3b8190a953f9f37f278bf0b197af286b`.
  The fixture SHA-256 is
  `a3eccdbf4d0c5da282c8118ea8308b901216415e4e26bd44bb9c2f3dde8e5775`;
  the evidence SHA-256 is
  `16ace4464b4c5325f63ed9a9092eef00701cc15f35d0f691a07f5043dc438a19`.
- Requalified B's direct canonical/model/trace delegation with no B runtime
  change. D receipt refresh
  `72d5d11bd924466aeff8282a5b0aa5ef8341de9e` binds the exact C artifacts and
  preserves B producer `2e46fc8e0228af42d6eaeaa6a665ffe5998c0bd5`.
- Passed 108 combined C/B tests, 55 readiness/evidence/boundary tests, seven
  dedicated adversarial nodes, and all three readiness cases. Dry-run with no
  receipts and dry-run with exact receipts exit 0; normal exact receipts exits
  2. Every case remains `schema_not_ready`, with trajectory v2 false, empty
  measurements/claims, and publication-qualified count zero; exact receipts
  qualify only B/C.
- Tool qualification passed with 61 imported modules, 74 class definitions,
  and 62 qualified/registered tools. Python 3.12.7 ran the 399-finding ratchet
  (377 active, 22 vendored/generated), stable flake8, stable mypy on 77 files,
  and the pre-documentation full suite (`1867 passed, 50 skipped`). One earlier
  combined shell invocation outlived its output-capture window, so its
  unobservable tail was discarded as evidence and each gate was rerun with an
  independently observable exit.
- Decision: **G1 CLOSED**. S1 contract packages are authorized only from the
  final accepted baseline reported by the integration owner. No S1 branch,
  Task 02B, 03B-E, 05A, 12A, 13A, trajectory-v2 freeze, qita redesign, provider
  default, packaging, push, deployment, or live-model work occurred.

### 2026-08-29 — G1-R4 forced-secret scalar closure accepted

- Independent review reopened the accepted R3 baseline after reproducing C-P4:
  `_redact_value(force_secret=True)` redacted strings but returned integer,
  float, boolean, and null leaves unchanged below a sensitive mapping key.
- Core fix `89806df415f8a14da11db4427e4682f44e650c03` introduced private projection
  roles. Secret-bearing content replaces every JSON scalar leaf and counts it
  exactly once; trace-safe omitted data redacts a sensitive key while retaining
  its validated non-negative integer count. Benign typed values and canonical
  persistence remain unchanged; no public version or root export changed.
- B remained a direct consumer of C's projection and required no runtime code
  change. New C producer `9a0c5ed5d6c1c959ff277d3888f54c927be3e183`
  publishes fixture SHA-256
  `b7f4dc6dfe8958bcd9c47617869a14bc8114629038d3428e6a623642fd2e5415`
  and evidence SHA-256
  `96b0e641ccca7e049a90658496a19964217aa7c359a29c6b6e6b345fb7cf99f5`.
- D receipt commit `e41eb6ea68375b1064b30044e66ae58bcba67c67`
  binds those exact committed bytes; a regression test proves the old R3 C
  receipt fails with `producer_source_commit_mismatch`. The B receipt is
  unchanged.
- Qualification passed: 112 combined C/B tests, 56 D/readiness/boundary tests,
  four dedicated C-P4 adversarial nodes, tool qualification (61 modules, 74
  classes, 62 qualified/registered), the 399-finding ratchet (377 active, 22
  vendored/generated), stable flake8, stable mypy on 77 files, and the full
  suite (`1872 passed, 50 skipped`). Readiness still qualifies only B/C; it
  remains `schema_not_ready`, trajectory v2 remains unfrozen, measurements and
  claims remain empty, and publication-qualified count remains zero.
- Decision: **G1 CLOSED** on the final scalar-safe R4 baseline. R3 remains in
  this ledger as an accepted-then-reopened audit event. S1 was not created or
  implemented and may start only from the exact final R4 baseline reported by
  the integration owner. Task 02B, 03B-E, 05A, 12A, and 13A remain unimplemented.

### 2026-08-30 — independent G1-R4 baseline audit confirms S1 dispatch

- Verified official integration, convergence, G1-final, and R4 worktrees were
  clean at the same runtime HEAD
  `5ef8ab657f6452ae48c931beea79106e2cca34c6`; merge-base and reachability
  checks showed no commit delta between the four references.
- Reviewed the R4 implementation rather than relying on its report. The private
  projection role distinguishes secret-bearing content from omission counts:
  forced-secret string, integer, float, boolean, and null leaves are redacted,
  while validated non-negative omitted counts remain integers. Benign values
  and canonical persistence bytes remain unchanged.
- Independently recomputed the C fixture and evidence digests as
  `b7f4dc6dfe8958bcd9c47617869a14bc8114629038d3428e6a623642fd2e5415`
  and `96b0e641ccca7e049a90658496a19964217aa7c359a29c6b6e6b345fb7cf99f5`;
  D's receipt binds those exact bytes and producer
  `9a0c5ed5d6c1c959ff277d3888f54c927be3e183`.
- A fresh adversarial scalar-role matrix passed. Independent repository gates
  passed: 168 combined contract/readiness/boundary tests, full suite
  `1872 passed, 50 skipped`, the 399-finding ratchet (377 active and 22
  vendored/generated), stable flake8, stable mypy on 77 files, and tool-schema
  qualification over 61 modules, 74 class definitions, and 62 registered tools.
- Re-ran all readiness modes. Dry-run without receipts exits 0 with 14 blockers;
  dry-run with exact receipts exits 0 with 12 blockers; normal exact-receipt
  execution exits 2 with the same 12 blockers. Only B/C contracts qualify;
  `trajectory_v2_ready` stays false, publication-qualified fixtures stay zero,
  and measurements/claims stay empty.
- One preliminary reviewer harness addressed the readiness object through an
  obsolete nested JSON path and was discarded as evidence. The corrected
  standalone harness used the actual top-level schema and exited 0; no product
  failure or rerun-only success was hidden.
- Decision: **G1-R4 independently accepted; G1 remains CLOSED.** Exactly four
  S1 contract lanes may be created from the final post-audit integration HEAD.
  This audit did not create those branches or implement session, provider,
  recovery, multi-agent, trajectory-v2, qita, or packaging behavior.

### 2026-08-30 — independent S1 candidate audit opens G2 convergence

- Verified all four S1 worktrees were clean, descended from dispatch baseline
  `c1efb0f4adde3e673bf181af5b1760c19a451ae2`, and matched reported heads A
  `cb79532d45b114826ee4313a60bf42ebc5abca06`, C
  `61c85ab774705610a2edf039417a8480afbeee16`, B
  `939edd0164a7f1929818f3e79bea02f2635a9d7d`, and D
  `44a09e3cbfaa29978584a05fbafbdd5c37cd7f2f`.
- Recomputed the reported A identity/manifest/evidence, B request/evidence, C
  recovery/work-graph, and D evidence/receipt-set digests. Committed producer
  bytes matched the reported A identity, B request, and C fixture digests; B's
  local evidence remains intentionally unqualified and was added after its
  fixture producer commit.
- Built an isolated A -> C -> B -> D tree. Git integration was conflict-free;
  173 focused contract/readiness/boundary tests and the full suite
  (`1999 passed, 50 skipped`) passed. The 399-finding ratchet, stable flake8,
  stable mypy on 81 files, and `git diff --check` also passed. The temporary
  audit worktree was removed after review.
- Cross-lane probes reproduced real semantic blockers despite the green suite:
  C accepts arbitrary work/session/agent strings instead of A identities; B's
  component has no reviewed A envelope adapter; B's ArtifactRef is rejected by
  C's strict ToolResult; the new C writer is rejected by the pre-S1 ToolResult
  reader under the unchanged schema identity; ProviderFailure and WorkGraph
  diagnostics can echo secret/host-path-bearing input.
- The combined modules declare 96 names through `__all__` across about 4,500
  lines. Root exports remain unchanged, but zero root delta is not evidence that
  the future user interface is simple; G2 must classify and constrain the
  beginner, extension, persistence-internal, and private surfaces.
- Readiness remains honest. Dry-run without receipts exits 0 with 30 blockers;
  dry-run with the two G1 receipts exits 0 with 28 blockers; normal execution
  exits 2. All 17 S1 requirements remain `producer_version_unestablished`, the
  trajectory schema remains unfrozen, and measurements/claims remain empty.
- Decision: the four branches are valuable S1 producer candidates but are **not
  merge-ready**. One G2 integration owner must converge A -> C -> B -> D using
  `docs/internal/plans/g2_contract_convergence.md`. S2 runtime work remains
  blocked.

### 2026-08-31 — independent G2 candidate audit opens G2-R2

- Verified clean G2 candidate
  `cab8fd246d2485784a13558e668eadb3ffa4d42f`, its 22 ordered S1
  cherry-picks and seven convergence commits. The primary integration branch
  remains clean at `3ab69c91b8c5b7759208a3449def341658bd5fd1`; the candidate
  branched from parent `096e082...`, so it is not a fast-forward successor and
  has not been promoted.
- Reviewed the actual identity, snapshot composition, ArtifactRef, ToolResult,
  WorkGraph, provider capability, diagnostic, readiness, and interface-budget
  code. Typed cross-line ownership and the single-contract direction are real;
  no session, scheduler, provider-default, Trajectory, or qita runtime was
  introduced.
- Independently passed 226 focused tests, full suite
  `2010 passed, 50 skipped`, the 399-finding ratchet, stable flake8, stable mypy
  on 84 files, and diff/readiness checks. Readiness results were 0/19 qualified
  without receipts and 19/19 with the checked-in set, while every mode remained
  `schema_not_ready` with no measurement or claim.
- Reproduced a mixed-schema failure: the historical ToolResult reader accepts
  current-only attempt, owner-generation, effect, and uncertainty fields under
  the historical schema identifier. The historical grammar therefore is not
  yet strict despite the current/historical class split.
- Reproduced malformed capability acceptance: persisted capabilities can carry
  string feature sequences, non-boolean flags, and a negative input budget; one
  malformed variant escapes as raw `TypeError` instead of a typed codec error.
- Reproduced diagnostic/privacy leaks for unenumerated absolute paths and common
  API-key/JWT-like values. ProviderFailure leaves category unsanitized and
  ArtifactRef accepts a secret-like model summary and embedded host path in a
  resolver reference.
- Found receipt and interface evidence mismatches: the item named canonical
  ToolResult foundation still binds G1 historical bytes, and diagnostic helpers
  classified as internal-private remain explicitly published through
  `__all__`.
- Replayed the candidate range onto the current integration baseline in a
  disposable worktree. The first 28 commits applied; the final documentation
  commit conflicted in CHANGELOG, both READMEs, and the four-lane playbook. The
  temporary worktree was cleanly aborted and removed.
- Inventoried 16 clean non-primary worktrees consuming approximately 10.13 GiB.
  None were removed before promotion. G2-R2 owns the verified, non-forced
  retirement receipt after the repaired baseline is promoted.
- Decision: candidate direction is accepted, but **G2 remains open**. Dispatch
  one G2-R2 repair/promotion owner. S2 is planned in
  `docs/internal/plans/s2_runtime_wave.md` but remains blocked.

## G5 isolated convergence — defaults repaired, final gates open (2026-09-04)

Exact A→B→C→D replay is complete (29 commits). Audit repairs, actual sandbox/
Session/work/context/artifact wiring and two independently installed consumers
have passed controlled qualification on 511013a. Schema freeze 50e99a2, initial
writer b5cd0df and reader 5648291 were separate commits. Failed combined attempt
05 exposed demo compatibility and shared implicit output; selector rollback
1055819 preserved data. Project-scoped writer 6977f7e and reader 75ae72d restore
defaults after focused repairs. Full attempt 03 had passed 2628/50 on an earlier
tree; attempt 04 failed one example, and attempt 05 was interrupted after known
failures. None is substituted for the final combined-tree gate.

C's original completed pytest output says 50 skips, not its later report's 99;
the exact output digest is now retained in G5 evidence. All source worktrees
and refs remain retained. Primary HEAD remains 306e689; no promotion or push.
See docs/internal/plans/s4_g5_convergence_execution.md for commands, failure
history, exact source/replay identities and current acceptance work.

G5 post-switch validation: committed source d01ea9e passed the complete suite
(2663 passed / 50 opt-in live skips), stable/config/reader checks, 356-finding
ratchet, all 20 wheel profiles and both fresh installed consumers with default
qita inspection. Current registry evidence is 5f36d4b, pinned by f977eb6.
Final evidence-inclusive candidate and primary post-FF validation remain
separate required gates; remote sync and release are not authorized.
