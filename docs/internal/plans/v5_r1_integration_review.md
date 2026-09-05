# V5 R1 independent implementation review

Date: 2026-09-05. Status: **changes requested before integration qualification**.
This is a source review with offline diagnostics, not a merged-tree, live-model,
release or remote-promotion qualification.

## 1. Source identity

All four lane worktrees are clean and have the same exact merge-base:
`4dfb570fb7eef504c1e6d247c21a1984251b80e4`.

| Lane | Branch | Reviewed HEAD | Commits after baseline |
|---|---|---|---:|
| A | `codex/v5-r1-a-model-io` | `5c6c2c370c0465e5471024a6e4870a9feb8c2b2a` | 6 |
| B | `codex/v5-r1-b-memory-context` | `4b62f46712f1683338c0b7590ae1290c492cb542` | 4 |
| C | `codex/v5-r1-c-runtime-correctness` | `5b8a4363e59fd01286009741b26597f197de706b` | 6 |
| D | `codex/v5-r1-d-trajectory-efficiency` | `522ce90abf5a39fd5510fd254652a256ad283f4f` | 11 |

The current local master is still
`60809b3be388d22ea40ea41b4aaa1f5540c76fda`, with the pre-existing V5 planning
draft preserved. Tracking and `git ls-remote` both report master at the R1
baseline, five commits ahead of that local checkout. None of the four lane
deliveries is in remote master. The six registered worktrees comprise main,
docs-learning and the four R1 lanes; no worktree was removed.

Producer reports were read in full: A/B/C's `v5_r1_*_execution.md` and D's
`v5_r1_d_evidence/REPORT.md` under their respective `docs/internal/plans/`.
Those documents and installed-consumer results are producer evidence; the
independent reruns below are a distinct, smaller verification scope.

## 2. What was actually delivered

| Lane | Useful capability present in the candidate | Qualification boundary |
|---|---|---|
| A | Real built-in provider adapters have typed stream terminal/usage/dispatch handling and owned cleanup; history rereads preserve tool completion order. | Twelve offline adapter cases do not prove live provider parity. Reasoning and cleanup counterexamples remain below. |
| B | Memdir-backed memory contributions, stable record identities and cross-process recall; explicit deterministic omission of old eligible closed exchanges, with loss receipts and unchanged raw ExchangeLog. | YAML cannot yet express both required context options; Markdown replay and model summaries remain future work. |
| C | Same-Session handoff admission is persisted before dispatch; source callbacks no longer write a superseded head. Read/Edit delegate actual file semantics; Observation has one mapping/attribute authority. | Destination reconciliation needs work/transfer scoping; known dispatch rejection needs honest recovery facts. |
| D | Incremental derived-index maintenance, reader-local snapshot cursors, bounded iteration and atomic streaming canonical export; qita consumes the reader boundary. | Full historical byte hashing and writer retention remain O(N). This is not suffix-only I/O or universally bounded legacy APIs. |

These are functional framework improvements, not merely additional contracts or
test infrastructure. They preserve the single AgentModule + Engine execution
kernel and the existing canonical Session/WorkGraph/Trajectory mechanisms.

## 3. Confirmed residual findings

### R1-M1 — P1: Chat streaming silently loses supplied reasoning

Owner: A / integration model-I/O repair.
Source: `qitos/models/_stream.py::ChatStream.feed/finish`,
`qitos/models/openai.py::OpenAICompatibleModel.stream`.

The actual adapter, with only its SDK transport replaced, receives a
`delta.reasoning_content`, ordinary answer text, and a valid stop. Its aggregated
response contains `text=answer`, `finish_reason=stop`, `native_items=null`.
No reasoning representation survives this path. The non-stream decoder already
recognizes reasoning fields; this is a residual streaming contract gap, not a
claim that A introduced every aspect of it.

Required repair: preserve supported reasoning in the existing canonical response
and next-request path, separate from visible answer text. If a selected codec
cannot preserve it, report/reject the loss explicitly under the existing policy.
Test sync and async Chat adapters, multiple fragments, tool rounds and history
rereads. Do not invent content for providers that do not return reasoning.

### R1-M2 — P1: cleanup failure overrides typed stream failure

Owner: A / integration model-I/O repair.
Source: `qitos/models/_stream.py::close_owned/aclose_owned` and provider `finally`
blocks, including `qitos/models/openai.py::OpenAICompatibleModel.stream`.

For premature EOF followed by a stream `close()` raising a synthetic private
marker, the public `qitos_stream_transport` raises raw `RuntimeError`, not
`ProviderFailure`, and its string exposes the marker. The owned client still
closes; the defect is exception precedence and diagnostic safety, not proof that
all cleanup leaks resources. A higher Engine wrapper may normalize again; this
probe establishes the direct adapter boundary and lost original failure facts.

Required repair: attempt cleanup of every owned resource, preserve the primary
failure and request-sent/partial/usage facts, and expose secondary cleanup facts
through a bounded safe contract. With no primary failure, return an explicit
safe cleanup failure rather than silently swallowing it. Cover response and
client close failures together, normal completion, cancellation and async close.
Do not change the documented handling of consumer callback exceptions by accident.

### R1-C1 — P1: reconciliation attributes another work item's completion

Owner: C / integration runtime repair.
Source: `qitos/engine/session_runtime.py::Session._reconcile_handoff`.

The method checks target Agent identity but does not bind each transfer to the
current work item/session and relevant ownership generation. A canonical
WorkGraph with two different work items and sessions handed to the same Agent
passes strict serialization. Reconciling only the current Session as completed
changes both operation receipts to completed with the same terminal reference.

This is a production-method unit counterexample, not a claim that this reviewer
ran a public multi-process cross-work E2E. The repair must add that public-path
regression: same Agent is not the same work, run, attempt or ownership transfer.
Bind reconciliation to explicit identities/generations and preserve unrelated,
stale and superseded receipts. Do not restore source-owned terminal CAS writes.

### R1-C2 — P2: known dispatch rejection remains admitted/unknown

Owner: C / integration runtime repair.
Source: `qitos/engine/work_runtime.py::_dispatch_handoff`, `submit`, `recover`.

With a structural scheduler that rejects before creating any worker using
`queue_capacity_exceeded`, public `DurableWorkRuntime.submit` persists three
snapshots and leaves the receipt `transfer_admitted`, `admission_state=admitted`,
`outcome_unknown=true`. Repeating the same operation returns that receipt;
scheduler dispatch count remains one. The public caller receives a typed error,
but persisted facts do not distinguish known non-dispatch from uncertain work.

Required repair: distinguish provably not-dispatched admission/resolution failure
from a possibly running destination, persist a safe rejection/queue/recovery
fact, and document/test an actionable retry or destination-recovery path. Do not
solve this by replaying uncertain work or letting a superseded source write the
new owner's head. Scheduler acknowledgements are not destination task success;
diagnostic failure receipts and business terminal facts must remain separate.

### R1-DX1 — P2: ordinary YAML cannot select the new budget/loss options

Owner: integration config owner, consuming B's existing extension contracts.
Source: `qitos/config/loader.py::_parse_context`;
`examples/v5/r1_b_memory_context/consumer.py`.

Adding `context.budget_policy` or `context.allow_codec_loss` to B's actual example
and passing its bytes through `load_agent_config` produces
`UnknownConfigFieldError`. B honestly documents its `dataclasses.replace`
workaround. The installed Python consumer is valid; an all-YAML path is not yet
complete. This is an integration/DX gap, not a failed claim of Memdir persistence.

Required repair: accept the existing options through strict canonical config,
resolve the named budget extension at composition, and retain explicit loss
opt-in. Unknown factories, invalid types and missing authorization must fail
before model dispatch. Remove the workaround from the beginner example and
test YAML -> composition -> actual budgeted request/compaction.

## 4. Reproducible review evidence

[Offline counterexample runner](v5_r1_review_probes.py) imports from the selected
lane checkout and checks its exact HEAD. Invoke it with the pinned interpreter
from A, B or C's working directory, passing `A`, `B` or `C`. The script itself
resides in the main documentation draft, not in the historical source commits.
It uses synthetic data and no live key/network. Exit zero means the diagnostic
ran, **not** that the exposed behavior is qualified.

Observed outputs from the final checked runner:

| Finding | Result |
|---|---|
| R1-M1 | answer/stop; native_items=null |
| R1-M2 | RuntimeError; typed_provider_failure=false; synthetic_marker_exposed=true; client_closed=1 |
| R1-C1 | current_state=completed; unrelated_state=completed; same_terminal_reference=true |
| R1-C2 | queue_capacity_exceeded; transfer_admitted; admitted; unknown=true; retry does not dispatch |
| R1-DX1 | UnknownConfigFieldError for each of the two context keys |

Independent tests used Python 3.12.7, each in its exact lane checkout:

| Lane | Test files below `tests/` | Result |
|---|---|---:|
| A | models/test_r1_stream_lifecycle.py, models/test_r1_provider_matrix.py, engine/test_r1_stream_worker_lifecycle.py, test_config_provider_transport.py | 65 passed, 5.73 s |
| B | test_v5_memory_adapters.py, core/test_v5_exchange_compaction.py, core/test_request_view.py, test_g5_composition_extensions.py | 53 passed, 11.12 s |
| C | core/test_v5_observation_consistency.py, engine/test_v5_handoff_owner_race.py, test_v5_coding_actual_files.py | 45 passed, 4.02 s |
| D | tracing/test_v5_bounded_reader.py, tracing/test_v5_journal_work_budget.py, tracing/test_v5_streaming_export.py | 35 passed, 30.34 s |

Total: **198 passed**, no skips in these groups. Producer full suites remain
source-specific reports: A 3487, B 3474, C 3461, D 3473 passed, each with 51
conditional skips. Do not sum those counts or represent them as a merged suite.
This reviewer did not rerun complete suites, installed consumers, the performance
matrix, real Docker, live models or remote CI at the candidate heads.

The main-checkout documentation update separately passed 18 tests in 18.42 s:
architecture boundaries, public surface, no-local-path, docs golden paths and
architecture layout. Public docs navigation/parity validation passed; 83 local
links across 11 planning/ledger documents resolved; the diagnostic runner parsed
and ran at all three pinned source heads. `git diff --check` passed. No MDX,
site layout or executable public tutorial was edited by this review, and no
browser-rendering or public-site promotion is claimed. Final lane status checks
again showed clean worktrees, unchanged HEADs and 6/4/6/11 source commit counts.

## 5. Integration and compatibility review

- A and B both change `_model_runtime.py`. B records an explicitly approved
  minimal lease adjustment. Preserve B's pre-selection compaction policy and
  step identities together with A's completion-order reconstruction and actual
  dispatch accounting. Textual merge success is not a semantic test.
- A/B pairwise `git merge-tree --trivial-merge` reports textual conflicts in
  CHANGELOG and the two READMEs, not `_model_runtime.py`. This is only a read-only
  pairwise diagnostic, not a four-way integration or qualification.
- Shared source-bound docs: API contracts A/B/D, tutorial contracts A/C/D,
  composition pages A/B, trajectory pages A/B/D, work-graph pages B/C;
  `sync_api_reference.py` changes in both B and D. Merge intended changes, then
  regenerate against the integrated code; do not pick one lane's whole file.
- Memdir now defaults to restoring an existing directory; initialization is
  explicit `create=True`. Keep that safer contract and audit beginner call sites.
- Read/Edit direct calls now return canonical ToolResult instead of a string.
  Keep one canonical result, but document the return-type migration and test
  actual public string-extraction/legacy consumer patterns. Do not silently call
  the change fully backward-compatible or create another canonical outcome type.
- Observation's dict/dataclass/checkpoint compatibility has targeted coverage.
  Its extension surface and owned snapshots need the combined installed consumer,
  not another architectural redesign.

## 6. Performance interpretation

D measurements are bound to `df9316415db7ec76f1e5d70a11ceabfd47744169`, not newly
measured by this review. At 100k records, reported warm append median decreases
from 0.1717 s to 0.0868 s and derived index writes from 200,000 to zero on that
operation. Historical byte hashing remains about 205 MB; writer RSS remains
roughly 658 MiB. Cold-open cost is not eliminated.

The streaming export reports approximately 1.44 MB peak Python allocation and
62 MiB process RSS on that dataset; this is not a universal memory ceiling or a
claim about all legacy readers. Reported full traversal operation time increases
from about 2.81 s to 6.96 s, while 100k export operation time changes from about
8.00 s to 7.71 s. Extra verification passes trade I/O/time for bounded memory.
These tradeoffs are acceptable within R1's corrected scope and must stay visible.

## 7. Decision and remaining roadmap

Proceed with **one bounded R1 integration/repair owner**, in the original order
**C -> B -> D -> A**, following [the integration plan](v5_r1_integration_plan.md).
Do not send the four lanes back to rebuild completed mechanisms. Convert the
five findings above to executable regressions, repair them on the combined
candidate, and qualify one installed cross-capability consumer.

The following are not R1 blockers and remain in their original V5 groups:

- Real-model autonomous success and original out-of-tree Agent migration/Gate A.
- Markdown durable replay, optional summary-model policy, long-session and
  cross-Agent memory strategy, complete history retirement.
- Functional retry/timeout, SharedMemory, tool preset/alias retirement,
  MCP/hooks/optional dependency consolidation and PEP 621 migration.
- Suffix-only I/O with an explicit integrity/trust model, Artifact GC, external
  training formats and authorized campaign publication.
- Durable approval/control channels, broader workspaces/sandbox backends,
  async Session parity and stronger isolation qualification.

Framework loss, false terminal facts and unsafe diagnostics are framework-owned.
Prompt quality, chosen memory content and task strategy remain Agent-author
choices; provider availability is separately reported. A live failure must not
hold an otherwise qualified framework repair hostage, and offline success must
not be advertised as autonomous task success.

No runtime patch, merge, commit, push, deployment, package publication or worktree
cleanup was performed by this review. Only planning/evidence documentation was
added or updated in the existing main-worktree draft.
