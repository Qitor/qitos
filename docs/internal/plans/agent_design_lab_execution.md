# Agent Design Lab execution ledger

Status: qualification in progress. The user authorized remote push after closeout;
package release and deployment remain unauthorized.
Source baseline: `f1545414913d2e0668d0eccdcd82fe91c3b28d01`.

## Contract

Six independently installable teaching projects use the canonical AgentModule,
Engine, Session, model runtime, tools and Trajectory. Strategies stay in the
projects; necessary framework defects and missing reusable mechanisms are fixed
here, with permanent regression tests. A scripted provider is mechanism evidence
only. Live completion requires real Qwen requests and independent task checks.
Private endpoints, credentials and raw evidence remain outside the repository.

## Implementation and consumer matrix

| Work | Consumers | Required evidence | State |
| --- | --- | --- | --- |
| Custom composition factory | ReAct, PlanAct | invalid bindings, cleanup, persistence, installed usage | pending |
| Durable tool/skill library | Hermes, Voyager | reopen, version, isolation, retrieval, full-body loading | pending |
| Feedback and planning | ReAct, PlanAct | same tasks, actual replanning, recorded model requests | pending |
| Extensible coding | Pi-like, Claude-Code-like | native Env tools, independent extension, child review | pending |
| Memory and skill learning | Hermes, Voyager | cross-session recall, validated executable reuse | pending |
| Independent packaging | all six | Python 3.10 and 3.12 outside checkout | pending |
| Research qualification | all six | three tasks x three repetitions plus ablations | pending |
| Public teaching material | all six | complete EN/zh source, references, limitations, sync | pending |

## Confirmed gaps before changes

1. `build_agent_composition` unconditionally constructs ConfiguredAgent; custom
   AgentModule authors cannot reuse the same resource-owning composition root.
2. The existing BaseToolLibrary has only an in-memory implementation. Cross-
   process skill reuse needs a conforming durable implementation, not duplicate
   course stores.
3. Existing Voyager arithmetic examples save observations as reflection text;
   they do not qualify executable skill accumulation or automatic curriculum.
4. The old SkillInjector truncates instructions at 1,200 characters. This cannot
   represent selective loading of an entire required skill.
5. Existing PlanAct examples call a planner directly and treat individual tool
   success as step completion. New courses must use tracked model phases and
   independent verification rather than copy these assumptions.

## Source ideas

- ReAct: https://react-lm.github.io/
- Plan-and-Act: https://arxiv.org/html/2503.09572v3 (runtime teaching adaptation;
  planner training and paper benchmark scores are not reproduced).
- Voyager: https://voyager.minedojo.org/ (Docker code/data adaptation).
- Claude Code: https://code.claude.com/docs/en/how-claude-code-works (public design
  documentation, not a reproduction of proprietary implementation).
- Hermes: https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/
- Pi: https://github.com/earendil-works/pi/tree/main/packages/coding-agent

## Verification log

### Foundation implementation checkpoint (not whole-lab qualification)

- Factory rejection/cleanup/custom-state recovery: 10 tests passed after the
  original unsupported-keyword failures. Stable model/registry/parser/protocol
  ownership is checked; a factory may populate an initially empty registry.
- SQLite library: 5 tests passed, including two procedural/program consumers,
  subprocess reopen, namespace separation, revision CAS and invalid JSON.
- Full-body skill selection and Memdir forgetting: 2 failing counterexamples
  fixed. Deletion is namespace-local, not secure erasure or a multi-file transaction.
- Artifact authority: reproduced privileged developer placement and changed
  references to user-level data. Targeted combined gate: 24 passed.
- Initial full suite: 3747 passed, 52 skipped, 1 failed in 370.20 seconds. The
  failure is the expected exact-source API documentation binding after changing
  builder.py; it must be rebound to an actual implementation commit, not bypassed.
- Pinned mypy in an isolated Python 3.12 environment: 98 source files passed.
  The system environment's NumPy stubs were incompatible with the source target;
  no source errors were ignored to work around that environment issue.
- Six installed project factory consumers passed on Python 3.12. These verify
  factory construction, PlanAct state changes and Hermes durable/full-body
  mechanisms; they are NOT the six complete design qualification matrix.

### Live exploratory results (all raw evidence remains private)

- ReAct R17: final plus independent numeric/source checks passed; 5 actual file
  reads, 1 calculation command and 1 report submission.
- PlanAct R17: final plus numeric/source checks passed; 6 actual revise_plan
  calls, 5 file reads, 2 calculation commands and 1 report submission.
- Pi and Voyager initial programs passed controller tests but the following
  request received provider HTTP 400 after artifact context was introduced.
  Minimal explicit probes confirmed rejection of extra system/developer roles.
  This motivated the artifact-authority fix, not removal of artifacts.
- Subsequent attempts failed before any tool execution with
  provider_connection_failed; the exception chain was APIConnectionError →
  ConnectError (SSL). TLS verification was NOT disabled, credentials were NOT
  printed, and another provider was NOT silently selected. Live qualification of
  the fix and the required 3×3×6 matrix remain open.

### Still required before claiming completion

Complete and independently verify Claude child review/return/restore, Voyager
curriculum and code reuse/composition, Hermes cross-process recall/history,
PlanAct+memory+extension composition, 3.10 installation, real Docker mechanism
tests, full live/ablation matrix, bilingual complete-source courses, API/source
bindings, documentation rendering, final quality gates and exact-source evidence.
The draft project files are not a substitute for those receipts.

### Child resource restoration counterexample and repair

The independent Docker reviewer exposed a framework defect: rebasing a forked
child's Agent/conversation state captured a new external resource before restoring
the fork's pinned resource snapshot. The child therefore inspected pristine input
instead of the parent's verified source. Registered components now restore before
child capture; failure prevents dispatch and parent resources are restored in the
existing finally boundary. No Docker import or second execution path was added.

The two permanent external-component cases fail without the repair and pass with
it (preserved content; failed restore causes zero dispatch). Kernel/session/fork
regression: 335 passed. The independently installed, actual-Docker Claude reviewer
now passes read/check/structured-final/spawn/join. The scripted provider needed
distinct call IDs across parent/child; reused IDs were correctly rejected, not
relaxed in the framework. This is deterministic mechanism evidence, not live results.

Python 3.10 installed PlanAct + Memdir + separately installed Pi extension also
passes 12 requests, 10 plan revisions and actual closed-window compaction. The
notebook remains after composition cleanup. Live connectivity recovered on a new
ReAct probe; the full matrix and ablations are running in private storage.

### Live-driven encoded scalar and recovery repair

The initial full matrix exposed a reproducible false positive: JSON tool arguments
containing Python `as f:\n` matched a Windows drive-path pattern. Complete encoded
JSON is now decoded only for inspection (original bytes are preserved). Inspection
also closes the prior encoded real-path bypass, with bounded depth/node handling
and non-echoing failures. Counterexamples: 8 failed / 9 passed before the repair;
the combined core/factory gate passed 494 tests afterward.

SessionContractError was separately classified as recoverable merely because it
occurred during ACT, allowing another decision with an unclosed batch. Such errors
now terminate the current loop with typed state failure; explicit reconstruction
remains distinct from automatic retry. Four classification counterexamples failed
before the fix; engine tests also check zero additional decisions after rejection.

The old experimental group remains private and is not discarded. Its controller
was paused while its last active child finished normally, then stopped before
dispatching more old-source cases. The final unappended child's exit code is not
invented; its actual failure log and an intervention receipt remain. A new wheel
and independently identified matrix must qualify the corrected implementation.

### Same-owner continuation repair

The Docker review consumer exposed another existing contract inconsistency:
RUN accepted PAUSED but skipped its required RESTORING transition. After fixing
that transition, a retained historical pause receipt also suppressed terminal
persistence. The permanent same-owner counterexample now verifies one tool effect,
unchanged owner, advanced head and COMPLETED lifecycle. Session/work-runtime gate:
33 passed. Installed real-Docker Pi and full Claude parent/child/join/parent-final
consumers passed. Explicit Engine.restore still creates and fences a new owner.

### Full-suite isolation regression and correction

The first expanded full run recorded 3894 passed, 52 skipped and 3 failed. One
existing independent child RequestView test caught parent conversation restored
after the filtered transfer. Resource restoration now precedes cache clearing
and authorized projection; both external-resource and conversation-isolation
tests must pass together. The two other failures were the tutorial import gate
mistaking separately installed `qitos_lab_pi` for the `qitos` package. Package
matching is now exact (`qitos` or `qitos.*`); external project imports are verified
by the separate installed consumers, not silently imported from the checkout.
The old application matrix is stopped at a case boundary before qualifying child
reviews; its observations remain private. The corrected installed wheel is used
for final application consumers and live trials. Research trials have no child
transfer and retain their original installed-source identity.

### Live-driven history and native preflight closure

The next full suite passed 3899 tests with 52 conditional skips. Subsequent real
Hermes execution exposed a course KeyError: its task descriptors have an objective,
not a required `id`. History now labels the declared objective (or explicit ID);
a permanent test executes the history tool on the packaged task, and the installed
consumer also publishes/reopens an episode. Its original failing result is retained.

Repeated failed calls exposed an independent framework issue: loop-detector blocks
returned before recording canonical tool terminals. Preflight blocks now close
their matching conversation slots, and warnings are appended only after results.
A native Session counterexample on the prior action runtime fails with an open
batch; the corrected runtime reaches final with exactly one terminal per blocked
call. No repeated tool is actually executed after the policy block.

Final live qualification is a new source-bound group, not a best-of retry. For
bounded completion it uses explicit per-task launch guards of 24 steps/requests
and 600 seconds; output remains 10,240 and no total request/cost quota is imposed.
The public project defaults remain 80/80/3600 and are configurable. Up to four
independent project/repetition groups may run concurrently; each group's learning,
recall and controls stay ordered. All old 80-step observations remain separate.

The bounded Docker Claude consumer initially exhausted its parent's remainder
because the application declared a fixed 30-request child allocation. Its review
policy now declares at most one third of the configured request ceiling, capped
at 30; the framework still intersects all authorities. The same 24-request Docker
counterexample now completes parent, independent child and final continuation.
This is application budget policy, not a framework refund or accounting bypass.
