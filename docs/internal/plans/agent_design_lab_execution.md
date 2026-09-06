# Agent Design Lab execution ledger

Status: in progress; not qualified. No push, release or deployment authorized.
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
