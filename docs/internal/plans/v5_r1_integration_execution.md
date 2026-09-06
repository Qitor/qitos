# V5 R1 integration execution

Status: historical completed integration. Offline framework qualification passed; local master acceptance completed at `d17a6ab4f6b09b0dd8a9c8896f859d26de17f3ec`. Live was not run; this integration task did not push or release. Current status and the additional Python 3.10 repair/push authorization are in the [remote synchronization record](v5_r1_remote_sync.md).

## Historical authorization and preservation

The current integration instruction supersedes older planning restrictions on
local preservation, qualified fast-forward promotion and non-forced retirement.
Remote synchronization remains unauthorized. Source baseline:
`4dfb570fb7eef504c1e6d247c21a1984251b80e4`.

Main started clean in the index at `60809b3be388d22ea40ea41b4aaa1f5540c76fda`,
with exactly the 23 allowed modified/untracked files. Preservation branch
`codex/v5-r1-planning-preserved`, commit
`318adc4be92222dd8cf0ef9035c80561feb5ccfc`, retains every file byte as verified
against [pre-stage digests](v5_r1_integration_evidence/planning-digests.json).
Main returned to clean master. Integration was created directly from the fixed
baseline. Planning replay: `ee95805` (not part of the 27 producer commits).

## Replay and conflict decisions

All four branches match their reviewed heads, clean working trees, exact common
baseline, counts 6/4/11/6, and no merges. All 27 commits replayed C → B → D → A,
without squash/skip/source edits. Full identities and conflicts are recorded in
[the mapping](v5_r1_integration_evidence/replay.json).

Planning replay conflicts: README.md and README.zh.md. Preserve baseline's new
self-contained tutorial entry AND the planning roadmap entry; no old full-file
replacement. B final docs, D final docs and A final docs each conflict in
README.md, README.zh.md and CHANGELOG.md: independent capability bullets and
migration facts from both sides are retained in their original sections.

Runtime and generated-document shared files merged textually. Semantic review
and combined behavior gates remain required: B step/exchange identity and
pre-selection policy; A completion order and dispatch/usage/refund; B/D API sync
features; all EN/zh source bindings will be regenerated on repaired source.

## Initial execution sequence (completed)

1. Reproduce and repair C1/C2, M1/M2, DX1, retaining source regressions.
2. Same-wheel original and combined installed consumers, success/failure variants.
3. Docs/migration/compatibility and complete pinned-toolchain qualification.
4. Qualified local FF, main revalidation, exact dispatch identity, safe retirement.

Historical review failures remain in the original review and probe files.

## R1-DX1 repair

The new YAML regressions failed 4 cases before repair (12 validation negatives
already passed); 67 YAML/config/security/extension tests pass after repair.
Only SDK-free tests ran. Named policy uses existing resolve_extensions factories;
loss requires a real boolean. B's context-only dataclasses.replace is removed.
Roundtrip exposed an existing serializer issue: unsafe_host emitted sandbox-only
neutral defaults rejected by its own loader. Serialization now emits type and
workspace only for that backend; admission and Env execution constraints are
unchanged. Config roundtrip and digest equality are asserted without a workaround.
At this intermediate point, installed consumers and source bindings were pending; completed results appear below.

## R1-M1/M2 repair

The initial 31 real-adapter regressions failed before repair. Stream chunks now
carry the existing reasoning_fields representation into ModelResponse, decoded
ReasoningBlock and RequestView. OpenAI-compatible selects the same Chat/Responses
codec as the built-in OpenAI adapter. Chat field replay requires explicit capability
support, matching provider/API scope and supported source field; generic providers
remain loss-explicit. No visible answer is synthesized from reasoning.

Cleanup attempts every owned resource, reports numeric cleanup_failures only,
retains typed primary category/stage/sent/partial/usage and preserves callback
exception identity/cancellation. Normal cleanup failure is typed. ProviderFailure
keeps only allowlisted non-negative integer usage counters, never raw SDK extras.
Expanded tests include borrowed Responses helper clients, cancellation during
iteration/cleanup, explicit sync/async close and no-reasoning behavior. A focused
144-test adapter/codec sweep passed before the last cancellation-only additions;
complete tests and installed two-tool-round verification were then pending; both completed below.

## R1-C1/C2 repair

Seven of eight initial review/public-path tests failed before repair. Reconciliation
and snapshot resolver selection now match descriptor work/session, explicit context
receipt linkage, actual transfer work and committed owner generation. Terminal refs
include the executing Session/run/attempt. Historical descriptors without enough
transfer linkage remain unreconciled instead of guessing ID conventions. CAS still
fences stale source runs; no source terminal callback was restored.

WorkGraph's existing strict state reader now accepts dispatch_not_started with
closed admission, outcome_unknown=false and a safe dispatch reason reference.
Queue rejection, closed scheduler and pre-worker resolver failure are distinct
from possibly dispatched outcomes. Same operation retry returns the persisted fact;
restore the destination Session, then run it to continue without another dispatch.
Changing the payload is still a typed identity conflict. A source write after a
concurrent destination claim fails normal owner CAS and cannot rewrite its terminal.
Local resolver failures (including non-callable return) are normalized before worker
creation, with capacity released. Forty-one focused work/runtime/race tests passed;
the 20-process interleaving gate and installed combination were then pending; both completed below.

## Combined-consumer discovered repair

The installed consumer first failed because RequestView inherited the model's
128k default instead of the declared fixture budget; YAML now explicitly sets the
model context window to 100000. With real overflow, it then exposed a runtime
regression: after durable restore, the second step rebuilt canonical conversation
from compatibility History, losing old raw items/reasoning and changing identity.
Canonical ExchangeLog now remains authoritative; only the current user input is
appended once, keyed by run/step/content. Assistant/tool facts share that user's
exchange identity, allowing whole eligible exchanges to compact. No second log or
execution loop was introduced. The installed regression asserts original items
byte-for-byte unchanged after restore and nine reasoning-bearing tool rounds.

Development wheel 4 passed the public combination in 7.29 seconds: ten requests,
nine tool batches, forced fast-before-slow completion via Event/terminal hook,
multiple actual compactions, required memory/artifact/recent-window preservation,
continuation/missing-artifact/open-batch rejection, same-Agent independent Session,
page/iterator/export/reimport equality and owned thread/resource release. A separate
namespace made a real ordinary no-loss request. Missing loss permission prevented
the second SDK request (`provider_capability_loss`). The failure variant truncated
the second tool batch and failed both closes: zero incomplete-batch tool effects,
two earlier results retained, no final, two consumed requests, sent/usage/partial
counts and two cleanup failures retained. Recovery did not redispatch it.

Only SDK I/O is scripted. The first five calls stream; the destination restored in
a clean process uses the adapter's nonstream path (stream callbacks are not durable
configuration). Provider tool results preserve identity/output association; the
codec may transmit completion order, which is distinct from declaration order.
These are development checks, not the final source/wheel qualification receipt.

## First complete qualification failure and tutorial repair

The first final-wheel full suite at 72a5925 completed with 3713 passed, 51 skipped
and two failed installed tutorial executions (multi-agent page and learning-order
run). It was not a Docker failure. SQLite inspection showed the spawned child
failed before a request with max_model_requests=0. The tutorial omitted delegate
and spawn allocations, allowing the first child to reserve all remaining parent
requests. Both now declare two requests, as the existing fan-out already did. No
timeout, sample count, assertion or budget enforcement was weakened; no implicit
refund was introduced. EN/zh complete source is regenerated. The earlier 86-test
precommit group passed, so this wider run supplied necessary combination evidence.

Directed lint also found formatting in the three new regression files. Formatting
is normalized with AST equality checked; their executable behavior is unchanged.
A new full suite will qualify the final tutorial tree using the same runtime wheel.

The first tutorial edit incorrectly passed budget to the convenience delegate/spawn
methods, whose signatures do not accept it. The second full run exposed that TypeError;
it is retained as failed evidence. The corrected tutorial uses the existing public
submit_work operation payload for explicit child allocations. No new API is added.

## Final qualification and compatibility

Source/test/example execution HEAD: `55c356f9d0f6b0df431ac1427f2373dfd5e540fa`. Packaged runtime last changed at
`72a5925d107099f6e32bd18344dae5212a5c4786`; all 510 qitos Python files in the final
wheel match the accepted source bytes. The final wheel/sdist were built at
`13b10d229c28479120781fb8dd1a89004e8c672f`; the following consumer typing commit
changes no packaged runtime. [Environment and digests](v5_r1_integration_evidence/environment-final.json).

- Full source suite: **3715 passed, 51 skipped in 352.53s (0:05:52)**, [raw receipt](v5_r1_integration_evidence/final-full-suite-3.txt).
- 50 existing live model E2E opt-ins skipped; one existing explicit Docker docs gate skipped. Every skip is listed in the raw log. No added skips or relaxed limits. Ordinary suite Docker tests ran serially; no new sandbox/Env safety semantics were introduced.
- All A/B/C/D original installed consumers pass, including C serial/concurrent handoff. [Four consumers](v5_r1_integration_evidence/original-installed-2.txt), [C handoff](v5_r1_integration_evidence/c-handoff-installed-final.txt).
- Combined success, truncated-stream plus dual-close failure, namespace and no-loss cases pass. Standalone assertions are `examples/v5/r1_integration/consumer.py`; each phase is a separate outside-repository process. No live model, source PYTHONPATH, private Engine fields or tests helpers are used.
- Original C bounded Event/barrier matrix: 20 rounds × 6 cases, every process passed, no sleep sorting or rerun-only qualification. [Per-round facts](v5_r1_integration_evidence/handoff20.json).
- Static quality: 356 findings (334 active + 22 vendored/generated), allowance delta 0. Flake8 and mypy pinned gates pass; new helpers also pass directed lint and mypy with check-untyped-defs. Public/architecture/path and G2/S2 interface budgets pass. Root exports/Engine constructor defaults do not grow.
- API and tutorial generators preserve both B/D features; regenerated composition/context/trajectory/work-graph EN/zh bindings pass. 166 MDX pages compile; navigation, bilingual parity and local links pass. Actual browser checks covered 28 page/viewports at 1440×1000 and 390×844; no horizontal overflow or browser errors, only local preview Socket.io warnings. Final budget payload rendering was rechecked.
- Clean build artifacts each pass twine. Earlier build/test/development failures remain evidence and are not counted as qualification. No external model, 149, remote mutation or release occurred.

| Finding | Fixing commit | Permanent regression and after behavior |
|---|---|---|
| R1-M1 | `3a3970315996bca7275896137d5856bd93437e48` + `72a5925d107099f6e32bd18344dae5212a5c4786` | `tests/models/test_v5_r1_stream_repairs.py` and combined installed consumer: distinct reasoning fragments retained once, tool-history reread, capability preservation or explicit loss, no invented answer. |
| R1-M2 | `3a3970315996bca7275896137d5856bd93437e48` + `72a5925d107099f6e32bd18344dae5212a5c4786` | Same model regressions plus installed truncated batch: all owned closes attempted, borrowed resource retained, primary typed sent/usage/partial facts with safe numeric cleanup failures. |
| R1-C1 | `a99752376e31cf14963eb0a75f9b4817bb7a5753` | `tests/engine/test_v5_r1_handoff_repairs.py`: two legal same-Agent works, SQLite destination recovery, parent/child, generations and fences; original C Event/barrier matrix passes 20/20 processes. |
| R1-C2 | `a99752376e31cf14963eb0a75f9b4817bb7a5753` | Same runtime regressions: confirmed no-worker rejection survives restore as dispatch_not_started; destination restore+run is executable, changed payload conflicts, unknown never automatically dispatches again. |
| R1-DX1 | `5e34cf7ae948a91ae2aac02e87bea03b45a9832a` | `tests/test_v5_r1_yaml_context.py`: strict policy name/boolean, factory failure before request, roundtrip/digest, installed no-loss rejection and ordinary lossless success. |


Compatibility is explicit: Memdir initialization requires create=True and otherwise
restores; Read/Edit direct callers receive ToolResult, must check status then read
output, and are not universally string-compatible. Observation's single authority,
atomic validation, snapshots, dict/dataclass and historical checkpoint contracts
remain. WorkGraph adds a strictly recognized dispatch_not_started state; old readers
reject it and must upgrade. Historical handoff descriptors lacking explicit linkage
remain unresolved rather than guessing another work's terminal. No new canonical
config, Engine, SessionStore or outcome is introduced.

Performance is not remeasured. D's [source-bound report](v5_r1_d_evidence/REPORT.md)
measured runtime df9316415db7ec76f1e5d70a11ceabfd47744169 against the fixed baseline:
100k warm append median 0.1717→0.0868 s, while hashing all ~205 MB historical bytes.
Writer retention/open checkpoints remain O(N); reader cold-open validates all history;
whole iteration and some smaller streaming exports are slower. 100k streaming export
Python peak 1,435,215 bytes and traced-process RSS 62,160,896 bytes are distinct
measurements, not a universal bound or new integration measurement.

## Historical local acceptance and retirement contract (executed)

Local acceptance subsequently completed at `d17a6ab4f6b09b0dd8a9c8896f859d26de17f3ec`; the integration and four lane worktrees were retired with refs preserved. The following paragraph retains the original acceptance procedure.

All implementation changes and documentation closure are committed before local
acceptance. The user authorizes master fast-forward only after the candidate and
remote ancestry checks, then main static/public/repair/combined revalidation. Exact
old/new master, final dispatch SHA, main revalidation and actual disk retirement are
reported in the task final receipt, without a self-referential evidence commit.
The preservation, integration and four source refs remain local and are not deleted.
Producer tasks are completed/inactive; pre-retirement heads/status match the fixed
source mapping. Cache/venv/build data are reproducible. Any non-cache artifacts are
preserved outside Git before non-forced removal; unexpected data retains its tree.
No unrelated docs-learning tree is a retirement target.

R1 closes only its framework integration scope. Future owners remain V5-01 for full
original-Agent live migration, V5-02 for summary quality/Markdown durable reader and
history retirement, V5-03 for func/SharedMemory/MCP/hooks/optional dependencies,
V5-04 for Artifact GC/external training formats/campaign/suffix-only I/O, V5-05 for
interactive controls/new sandbox/daemon, and packaging for PEP 621. Async Session
full parity remains a separate runtime task. No documentation-only closing wave is
needed. LIVE_MODEL_QUALIFICATION=not_run; REMOTE_SYNC=not_performed;
PUSH_PERFORMED=no; RELEASE_PERFORMED=no.
