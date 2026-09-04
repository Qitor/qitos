# Task 16 — S4 four-lane implementation instructions

Status: historical dispatch instructions; four candidates reviewed, G5 repair required
Updated: 2026-09-04
Promoted S3/G4 runtime baseline: `f07b38647cf3b18a5235581224a1153b88fac397`
S4 implementation ancestry: `c4e621d05960a4e2f06cb4864f6a8cb8275ac067`
Depends on: Task 15 and the promoted Tasks 12–14 implementation
Feeds: G5 public-framework convergence

---

Do not redispatch these implementation lanes. Their exact source heads,
independent review findings, and the next single G5 repair/convergence task are
recorded in the [S4 audit](../internal/plans/s4_g5_convergence_audit.md).
The seven reproduced framework defects must be repaired before normal G5
qualification/default switching. The instructions below remain the original
scope and ownership record, not evidence that their acceptance gates passed.

## 1. Decision and rationale

S4 uses four capability lanes, not four engineering-support lanes. Static
quality, documentation, fixtures, receipts, privacy, packaging, and evidence
remain mandatory in every lane, but none of them receives a permanent lane of
its own. The four lanes correspond to the extension points an Agent framework
user actually needs:

1. author and control an Agent;
2. transact with models and manage context;
3. execute tools and child work safely;
4. observe, evaluate, export, and install the result.

This decomposition improves QitOS as a development framework rather than as a
single built-in Agent. Prompts, domain strategy, task decomposition policy,
tool selection, and success criteria remain user code. QitOS owns the reusable
runtime mechanisms, stable extension boundaries, safe defaults, truthful
failures, and conformance suites.

The wave does not create a second execution architecture. Every public path
must converge on the existing:

```text
AgentConfig / Python composition
             |
             v
      AgentModule + Engine
             |
             v
          Session
       /      |      \
 ToolRuntime  WorkGraph  CheckpointStore
       \      |      /
        RuntimeEvent
             |
         Trajectory
             |
            qita
```

## 2. Baseline preflight before dispatch

The promoted S3/G4 runtime baseline is `f07b386...`. Task 15 was added by the
read-only planning successor `c4e621d...`; therefore all four implementation
branches use `c4e621d05960a4e2f06cb4864f6a8cb8275ac067` as their exact ancestry.
Do not branch from the earlier runtime SHA and do not silently substitute a
later documentation commit.

This Task 16 file and the corrected Task 15 status live in a later planning-only
commit, so they cannot be self-contained in their own fixed ancestor. Before
creating a lane worktree, read Task 16 from the verified formal branch with
`git show origin/feat/campaign-absorption:docs/v4/16-s4-parallel-wave-instructions.md`
or use the complete instruction copied by the maintainer. The Task 16 baseline
statement supersedes the older Task 15 header visible at `c4e621d...`; it does
not change any runtime bytes.

Before sending any lane instruction, the integration owner must:

```bash
qitos_repo="$(git rev-parse --show-toplevel)"
cd "$qitos_repo"
git status --short
git fetch origin --prune
git push origin feat/campaign-absorption:feat/campaign-absorption
git ls-remote origin refs/heads/feat/campaign-absorption
```

Dispatch is authorized only when all of these are true:

- the primary checkout is clean;
- local `c4e621d...` is an ancestor of the pushed branch;
- `origin/feat/campaign-absorption` resolves to `c4e621d...` or a reviewed
  documentation-only successor that preserves `c4e621d...` as the exact
  implementation ancestry;
- local/tracking divergence is `0/0`;
- no lane worktree or branch already exists under the names below.

If the remote still resolves to `f07b386...`, stop with
`blocked_dispatch_baseline_not_pushed`. An Agent must never guess the missing
baseline or work in the primary checkout.

## 3. Shared execution contract for all four Agents

Every lane instruction below is self-contained, but these rules apply to all
four.

### 3.1 Worktrees and branches

| Lane | Agent assignment | Branch | Worktree |
| --- | --- | --- | --- |
| A | public authoring/runtime API Agent | `codex/v4-s4-a-public-authoring` | sibling `WhitzardOS-s4-a` |
| B | model/context Agent | `codex/v4-s4-b-model-context` | sibling `WhitzardOS-s4-b` |
| C | safe execution Agent | `codex/v4-s4-c-safe-execution` | sibling `WhitzardOS-s4-c` |
| D | trajectory/release Agent | `codex/v4-s4-d-trajectory-release` | sibling `WhitzardOS-s4-d` |

Each Agent must fetch the formal branch, verify that `c4e621d...` is reachable,
create its own branch/worktree directly from that SHA, and record the exact
merge base. It must not cherry-pick another S4 lane unless a later integration
instruction explicitly authorizes that operation.

### 3.2 Shared architectural rules

- Preserve one `AgentModule + Engine + Session` kernel.
- Do not introduce public `V1`, `V2`, `Legacy`, `Next`, or parallel Agent,
  Session, Runtime, ToolResult, ArtifactRef, WorkGraph, Sandbox, or Trajectory
  families. Historical wire identifiers may remain private reader details.
- Reuse before creating. New protocols must correspond to a real third-party
  replacement point and include executable conformance tests.
- Do not place product prompts, benchmark policy, coding strategy, manager
  strategy, or domain-specific behavior in `qitos/`.
- Credentials enter only through `CredentialRef` plus an explicit resolver.
  Do not read ambient credentials, commit private config, echo a secret, or
  place credentials in tool sandboxes, snapshots, trajectories, child context,
  process arguments, or logs.
- Executable model-selected tools must fail closed without the required
  sandbox. `unsafe_host` stays an explicit lower-assurance compatibility mode.
- Canonical persistence remains complete; model, diagnostic, public, and
  export projections are bounded and declare loss.
- qita is read-only. It may inspect durable facts but never owns Session or
  WorkGraph mutation.
- A typed provider/model failure is not a framework defect unless a QitOS
  invariant is violated. Live completion rate is informational.
- Do not push, deploy, publish a package, change the GitHub default branch,
  access server 149, delete another worktree, or delete a branch/tag/ref.

### 3.3 File leases

The following shared files are frozen in all four lane worktrees and belong to
the G5 integration owner:

- `README.md`, `README.zh.md`, and `CHANGELOG.md`;
- `docs/progress.md` and existing `docs/v4/00-*.md` through
  `docs/v4/16-*.md`;
- shared docs navigation/configuration files;
- global quality baseline and global public-surface allowlists, unless a lane
  cannot pass without a shrink-only mechanical update and records it for G5.

To satisfy documentation-sync requirements without creating merge conflicts,
each Agent writes one lane-owned plan/evidence file under
`docs/internal/plans/` and includes patch-ready English/Chinese README,
changelog, progress, and public-doc wording in its handoff. G5 applies the
shared edits once after convergence.

The most conflict-prone implementation seams are also leased explicitly:

| Surface | Sole lane owner during parallel work |
| --- | --- |
| `qitos/config/**`, `qitos/cli.py`, `qitos/core/session.py`, `qitos/engine/engine.py`, `qitos/engine/session_runtime.py`, `qitos/engine/runtime.py` | A |
| conversation/request/context/history/memory/multimodal/model-response/artifact contracts, `qitos/prompting.py`, `qitos/models/**`, `qitos/engine/_model_runtime.py`, `qitos/engine/_context_runtime.py`, model streaming | B |
| action/tool/ToolResult/Env/WorkGraph/agent-spec/interceptor contracts, `qitos/engine/_action_runtime.py`, `_env_runtime.py`, `_handoff_runtime.py`, `action_executor.py`, `tool_runtime.py`, `work_runtime.py`, `qitos/kit/env|tool|toolset/**`, `qitos/mcp/**` | C |
| `qitos/tracing/**`, bounded `qitos/trace/**` readers, `qitos/qita/**`, evaluation/metric/export/benchmark and packaging surfaces | D |

`qitos/core/__init__.py`, `qitos/engine/__init__.py`, root exports,
`qitos/engine/events.py`, and `qitos/engine/_snapshot_components.py` are G5 seam
files. A/B/C/D publish required imports, event payloads, and snapshot components
as fixtures or patch-ready handoffs rather than editing those seam files in
parallel. If an existing test makes a seam edit unavoidable, stop and report an
exact lease conflict instead of creating an overlapping change.

### 3.4 Quality and evidence

Use the repository-pinned Python 3.12.7 toolchain, not whichever `python`
happens to be first on the shell path. Every lane must run:

```bash
/opt/anaconda3/bin/python scripts/static_quality.py check
/opt/anaconda3/bin/flake8 qitos/core qitos/engine qitos/models qitos/trace
/opt/anaconda3/bin/mypy qitos/core qitos/engine qitos/models qitos/trace
/opt/anaconda3/bin/python -m pytest -q
git diff --check
```

Also run the lane-specific gates listed below. New tests must be deterministic:
no sleep-based ordering, hidden retry, rerun-only success, masked exit, network
dependency in the required suite, or unavailable-platform skip presented as a
pass.

Every producer bundle must bind:

- the exact source commit and merge base;
- committed fixture, manifest, evidence, and test-node paths;
- SHA-256 digests of committed bytes;
- public/extension/private classification;
- supported and unsupported semantics;
- independent consumer instructions for the other lanes and G5;
- current writer versus historical-reader authority;
- public-surface and dependency-boundary deltas.

## 4. Dependency and convergence model

All four Agents start concurrently, but the work has explicit dependency
direction:

```text
A public composition/API shape -----------+
                                           |
B model/context producer -----------------+--> G5 convergence --> D default switch
                                           |
C tool/sandbox/work producer -------------+
                                           |
D candidate schema/readiness preparation -+
```

Lane A publishes the beginner-path fixture and config extension slots early.
Lanes B and C do not edit A-owned config/CLI files; they publish exact config
requirements and consumer fixtures. Lane D may implement and test the candidate
data plane in isolation, but it must finish with `waiting_on_a_b_c` rather than
freeze the schema or switch qita's default reader without exact same-wave
producer consumption.

The planned G5 replay order is A -> B -> C -> D. G5 then repairs cross-lane
bindings, regenerates D receipts from committed integrated bytes, runs both
golden-path consumers, switches defaults only after every gate passes,
fast-forwards the integration branch, pushes non-forcibly when authorized, and
removes the four clean lane worktrees plus its convergence worktree without
force. Branch and commit refs remain.

---

## 5. Instruction for Agent A — public authoring, Session, CLI, and config

Copy this entire section to the Agent assigned Lane A.

### 5.1 Mission

You own S4 Lane A: make the already-qualified QitOS runtime simple to compose
and control without creating another runner or hiding lifecycle truth. The
normal declarative and programmatic paths must create and use the existing
`Session`; explicit ephemeral execution may remain only as a clearly named
compatibility mode.

### 5.2 Fixed source and setup

- Integration repository: the current primary `WhitzardOS` checkout
- Exact implementation ancestry:
  `c4e621d05960a4e2f06cb4864f6a8cb8275ac067`
- Branch: `codex/v4-s4-a-public-authoring`
- Worktree: sibling `WhitzardOS-s4-a`

Fetch and verify the formal remote branch. Refuse to start if the exact SHA is
not reachable, the destination exists, the branch exists unexpectedly, or the
source checkout is dirty. Create the worktree directly from the exact SHA.

### 5.3 Required reading

- root `AGENTS.md`, `qitos/AGENTS.md`, `qitos/core/AGENTS.md`, and
  `qitos/engine/AGENTS.md`;
- `ARCHITECTURE.md` and the architecture boundary/change-guide documents;
- Tasks 11–16, especially Tasks 12 and 15;
- `docs/architecture/framework-responsibility-boundary.md`;
- `qitos/config/`, `qitos/cli.py`, `qitos/engine/engine.py`,
  `qitos/engine/session_runtime.py`, `qitos/checkpoint/`;
- current quickstart, configuration reference, templates, generated projects,
  examples, public-surface tests, and package entry points.

### 5.4 Writable lease

Primary ownership:

- `qitos/config/**`;
- `qitos/cli.py`;
- `qitos/core/session.py`, `qitos/engine/engine.py`,
  `qitos/engine/session_runtime.py`, and `qitos/engine/runtime.py`;
- scaffold/template and beginner config/example files that do not contain
  provider, tool, or sandbox implementations;
- Lane-A-specific tests and fixtures;
- `docs/internal/plans/s4_a_public_authoring.md`.

Do not modify Lane B provider/context implementation, Lane C Env/tool/sandbox
implementation, or Lane D tracing/qita implementation. Express their settings
through stable extension slots and record unresolved producer dependencies.

### 5.5 Required work

1. **Exact-source census.** Trace every current public way to run, resume, fork,
   steer, inspect, and close an Agent: direct `AgentModule.run`, direct Engine,
   `AgentComposition`, `run_agent_config`, `qit run`, old checkpoint helpers,
   qita, demos, templates, and docs. Classify each as canonical, advanced,
   compatibility, deprecated, or internal. Do not remove a surface without
   consumer and migration evidence.

2. **One resource-owning composition path.** Evolve the current
   `AgentComposition`/builder in place so it has deterministic context-manager
   ownership, creates the existing Session, exposes lifecycle-safe inspect/run/
   pause/restore/steer/fork operations, and closes event sinks, sandbox,
   checkpoint stores, model transports, MCP clients, and other owned resources
   exactly once. Do not introduce `App`, `Runner`, or a second Session facade
   unless the public-surface review proves the existing name cannot serve.

3. **Session is the default truth.** Route `run_agent_config()` and `qit run
   --config` through Session and the checkpoint head protocol. A stateless
   launch, if retained, must be explicitly named, must not emit durable claims,
   and must have a migration notice. Session configuration must not default to
   silently disabled merely because that is the historical value.

4. **Stable control UX.** Provide coherent Python and thin CLI operations for
   create/run, inspect, safe pause, clean-process restore/resume, steering, and
   fork. Reuse existing Session typed errors and capabilities. Do not simulate
   live cross-process control if no control transport exists: report a typed
   unsupported capability and document the boundary. qita remains read-only.

5. **Configuration as composition, not object serialization.** Keep one
   canonical `qitos.agent` schema and reader-only historical spellings. Add
   typed/selectable slots for B context/model services, C sandbox/tool runtime,
   and D trajectory/evaluator services without importing their concrete
   implementations into core contracts. Persist logical references and policy
   digests, never clients, callables, credentials, absolute private paths, or
   live handles.

6. **Public API budget.** Prefer module-level advanced imports and a small
   beginner path. Measure root exports, aggregate exports, CLI command families,
   and `Engine.__init__` parameters before and after. Contract redundant Engine
   construction behind `RuntimeComposition` when compatibility can be preserved
   with explicit warnings. Do not grow the root surface merely to expose every
   receipt type.

7. **Generated beginner project.** Make `qit new` produce one installable,
   testable, domain-neutral project whose default config uses CredentialRef,
   durable local Session storage, an attested sandbox requirement, Trajectory,
   and a deterministic fake provider for offline tests. The generated code must
   not use internal imports, environment credentials, HostEnv, direct
   `AgentModule.run()`, or version-suffixed framework types.

8. **Golden-path equivalence.** Add executable fixtures proving that declarative
   CLI and programmatic composition reach the same Engine, Session, checkpoint
   head, config digest, tool/runtime extension slots, event sink, and cleanup
   semantics. Do not claim B/C/D functionality that has not yet been consumed;
   fixtures may use strict third-party-style stubs at those documented seams.

9. **Migration truth.** Provide warnings and migration examples for every
   changed default or deprecated convenience path. Preserve reader compatibility
   without keeping two public architectures indefinitely. Record exact
   retirement gates.

10. **Producer bundle.** Publish committed fixtures and an independent consumer
    test that B, C, D, and G5 can use without private Engine access. Include
    extension-slot requirements, the final beginner spelling, cleanup ownership,
    interface-budget deltas, and patch-ready shared documentation text.

### 5.6 Required tests

- config strictness, secret/path safety, digest stability, and compatibility
  readers;
- CLI help/golden output plus every supported Session control operation;
- context-manager success, construction failure, partial setup failure,
  exception, repeated close, and cleanup failure;
- Memory and SQLite Session create/run/pause/restore/steer/fork;
- fresh-process restore with resolver-only reconstruction;
- CLI/programmatic equivalence and fake-provider generated-project smoke;
- architecture, root/aggregate surface budgets, no-local-path, package entry
  point, full suite, static ratchet, lint/type, and diff checks.

Build wheel/sdist and run the generated offline project from a fresh virtual
environment if packaging surfaces used by the scaffold change.

### 5.7 Forbidden claims and edits

Do not claim live daemon control, distributed scheduling, provider parity,
production sandbox qualification, Trajectory freeze/default, or S4 completion.
Do not push or alter the frozen shared files. Finish as an exact Lane A
producer, not as G5.

### 5.8 Final report

Report: outcome; source/merge-base; worktree/branch; census; selected beginner
and advanced APIs; Session/default behavior; CLI matrix; composition ownership;
config extension slots; compatibility/retirement; public-surface delta;
fixtures/digests/consumer tests; A-to-B/C/D handoffs; validation; unsupported
claims; gaps; commits; clean HEAD.

---

## 6. Instruction for Agent B — model transactions, context, and providers

Copy this entire section to the Agent assigned Lane B.

### 6.1 Mission

You own S4 Lane B: make model calls, messages, context, memory, reasoning,
continuation, and provider replacement a coherent extension plane for framework
users. Preserve one ExchangeLog/RequestView transaction truth and one provider
adapter/codec boundary; do not build a second chat history or provider loop.

### 6.2 Fixed source and setup

- Exact implementation ancestry:
  `c4e621d05960a4e2f06cb4864f6a8cb8275ac067`
- Branch: `codex/v4-s4-b-model-context`
- Worktree: sibling `WhitzardOS-s4-b`

Apply the same remote verification and safe worktree rules as Section 3.

### 6.3 Required reading

- root and package AGENTS files plus Tasks 02, 04, 09, 12, 13, 15, and 16;
- `qitos/core/conversation.py`, `request_view.py`, `context.py`,
  `context_transfer.py`, `artifact.py`, and prompting contracts;
- `qitos/models/codec.py`, `provider.py`, all shipped provider adapters, model
  base/factory, harness adapter, streaming, and continuation code;
- Engine model-request, context-service, compaction, steering, and snapshot
  paths; current provider and conversation fixtures/tests;
- configuration and credential-reference contracts, read-only only.

### 6.4 Writable lease

Primary ownership:

- conversation/request/context/memory/artifact/continuation contracts under
  `qitos/core/` where they already live;
- `qitos/prompting.py`, provider-neutral model protocols, and `qitos/models/**`;
- context/memory/compaction implementations in `qitos/kit/` that do not overlap
  tool or Env ownership;
- `qitos/engine/_model_runtime.py`, `qitos/engine/_context_runtime.py`, and
  model-streaming modules; Session/public composition wiring remains an exact
  G5 handoff rather than a parallel edit;
- Lane-B fixtures/tests and
  `docs/internal/plans/s4_b_model_context.md`.

Do not edit `qitos/config/**`, `qitos/cli.py`, sandbox/tool implementations,
Trajectory/qita, or frozen shared documents. Publish exact config requirements
for A/G5 rather than editing A's files.

### 6.5 Required work

1. **Transaction census.** Map all writers/readers for system/user/assistant/
   steering messages, tool declarations/results, native parallel calls,
   multimodal items, reasoning, continuation, streaming, usage, retry,
   compaction, memory, artifacts, and provider failure. Identify duplicate
   histories, direct provider calls, inferred capabilities, lossy projections,
   and raw error/string repair paths.

2. **One model transaction.** Make ExchangeLog -> RequestView -> ProviderCodec
   -> provider transport -> decoded response -> ExchangeLog the only canonical
   request path. Persist each terminal parallel tool result immediately in real
   completion order; declaration order remains a derived view. Steering may be
   inserted only at declared safe boundaries and must reconcile exactly once
   after recovery.

3. **Modern message semantics.** Prove sequences of assistant tool calls and
   tool results across multiple turns, intervening user steering, native
   parallel calls, out-of-order completions, multimodal content, opaque
   reasoning/continuation, stateless replay, truncation, retry, cancellation,
   and clean-process resume. Preserve provider-native opaque reasoning only as a
   scoped resolver reference when raw persistence is unsafe or unsupported.

4. **Provider capability grammar.** Capabilities are declared and strictly
   validated, never guessed from provider/model names. Cover chat completions,
   responses-style APIs, reasoning, multimodal input, parallel calls,
   streaming, usage, tool choice, continuation, and context budgets. Unsupported
   features must reject or explicitly degrade with `CodecReport` loss; no silent
   fallback.

5. **One provider-author extension kit.** Publish a standalone structural
   conformance kit for a third-party adapter/codec. It must test request encode,
   safe projection, transport boundary, streaming assembly, response decode,
   native calls/results, capability loss, reasoning preservation, usage,
   continuation, cancellation/timeout, and non-echoing typed failures. The fake
   provider must live outside provider internals and pass without private
   Engine access.

6. **Context as an explicit service.** Make context contributors, memory,
   selection, compaction, artifact references, and budgets replaceable through
   stable protocols. Selection is deterministic and produces a receipt. Required
   artifacts fail typed; raw bodies are not copied into every message or child
   snapshot. Compaction never rewrites canonical history and declares every
   omission/transformation.

7. **Transfer authority.** Context transfer to fork/delegate/spawn/handoff must
   be the intersection of parent authority, child need, provider capability,
   sandbox authority, and budget. Provider credentials, raw continuation state,
   host paths, and unselected history never follow a child implicitly.

8. **Failure and budget truth.** Preserve encode, projection, admission,
   transport/connection, timeout, authentication, rate-limit, provider
   rejection/server, cancellation, stream, and decode stages with stable safe
   codes. Durable request admission happens before transport and survives
   restore. No hidden retry; retry and usage are explicit facts.

9. **Configuration handoff.** Define the exact secret-free config shapes and
   registries needed to select providers, codecs, context contributors, memory,
   compaction, and artifacts. Do not implement them in A-owned files. Provide a
   consumer fixture and patch-ready schema/example text for A/G5.

10. **Producer bundle.** Publish provider matrix fixtures, a third-party adapter,
    conformance runner, transaction/recovery fixtures, and exact A/C/D handoff.
    D must be able to derive canonical provider/request/context/loss/usage facts
    without parsing provider names or diagnostic strings.

### 6.6 Informational live matrix

Required qualification is offline. After all deterministic gates pass, a live
matrix may run only if an explicit local AgentConfig and credential resolver are
available outside Git. Do not scan ambient environment variables. The profiles
may use any of the three maintainer-approved private endpoints, but their URL,
credential values, and private receipts must remain outside committed files.

For each selected profile:

- use `max_tokens: 10240` unless the provider declares a smaller hard limit;
- set explicit per-request and total request/token/time ceilings;
- use zero hidden retry and record every request admission;
- run one conversational and one native-tool/parallel scenario when supported;
- retain only redacted capability facts and digests in repository evidence;
- classify provider/model task failure as informational unless it violates a
  framework invariant.

Missing credentials, network, provider support, or model capability is typed
`blocked_configuration`/`unsupported_capability`, not a required-gate failure.

### 6.7 Required tests

- full semantic message matrix and partial-batch crash/recovery;
- each shipped provider mode plus independent adapter conformance;
- streaming, reasoning, multimodal, continuation, steering, usage, timeout,
  cancellation, and loss behavior;
- context/memory/compaction/artifact determinism, budgets, transfer authority,
  serialization isolation, secret/path safety, and 10 MB bounded-adversary
  projection;
- checkpoint/Session/WorkGraph consumer tests without editing their contracts;
- architecture/public-surface/static/lint/type/full-suite/diff gates.

### 6.8 Forbidden claims and edits

Do not switch public config/CLI defaults, implement an Agent strategy, commit a
credential or private live receipt, claim every model can operate every tool,
or claim S4 completion. Do not create provider-specific canonical message
classes or a second memory/history truth.

### 6.9 Final report

Report: outcome; source; census; transaction path; message matrix; provider
capability matrix; extension kit; context/memory/compaction/artifact semantics;
transfer/budget/failure behavior; config handoff; live matrix and request counts
if run; fixtures/digests; A/C/D consumers; interface delta; validation;
unsupported claims; gaps; commits; clean HEAD.

---

## 7. Instruction for Agent C — safe tool, sandbox, MCP, and work execution

Copy this entire section to the Agent assigned Lane C.

### 7.1 Mission

You own S4 Lane C: deliver the safe, replaceable execution substrate required
by coding and research Agents. Consolidate tools, ACI, Env, sandbox, MCP, and
durable WorkGraph adapters around the existing ToolRuntime and Session
operations. Do not create a product Agent or another scheduler.

### 7.2 Fixed source and setup

- Exact implementation ancestry:
  `c4e621d05960a4e2f06cb4864f6a8cb8275ac067`
- Branch: `codex/v4-s4-c-safe-execution`
- Worktree: sibling `WhitzardOS-s4-c`

Apply the same remote verification and safe worktree rules as Section 3.

### 7.3 Required reading

- root/package/core/engine/kit AGENTS files and Tasks 03, 09, 12–16;
- `docs/architecture/framework-responsibility-boundary.md`;
- `qitos/core/tool*.py`, Env/permission/artifact/effect/runtime contracts;
- `qitos/engine/action_executor.py`, `tool_runtime.py`, `_env_runtime.py`,
  Session and durable work runtime/adapters;
- `qitos/kit/env/**`, `qitos/kit/tool/**`, `qitos/kit/toolset/**`, and
  `qitos/mcp/**`;
- current Docker qualification harness, CyberGym-derived generic ACI lessons,
  sandbox fixtures, WorkGraph recovery tests, and MCP lifecycle tests.

### 7.4 Writable lease

Primary ownership:

- `qitos/kit/env/**`, `qitos/kit/tool/**`, and `qitos/kit/toolset/**`;
- existing tool/runtime/permission/effect contracts and execution code needed
  for canonical behavior;
- `qitos/engine/_action_runtime.py`, `qitos/engine/_env_runtime.py`,
  `qitos/engine/_handoff_runtime.py`, `qitos/engine/action_executor.py`,
  `qitos/engine/tool_runtime.py`, and `qitos/engine/work_runtime.py`;
- `qitos/mcp/**` and MCP-specific lifecycle integration;
- durable WorkGraph tool adapters, but not the Session public API owned by A;
- Lane-C tests/fixtures and
  `docs/internal/plans/s4_c_safe_execution.md`.

Do not edit `qitos/config/**`, `qitos/cli.py`, provider/context implementation,
Trajectory/qita, or frozen shared documents. Publish sandbox/config and Session
snapshot-binding requirements to A/G5 rather than editing A's lease.

### 7.5 Required work

1. **Execution census.** Map every file, command, terminal, edit, test, process,
   HTTP, MCP, environment, background, delegate, spawn, fan-out, handoff, and
   join path. Prove whether it enters the canonical ToolRuntime, permission
   pipeline, Env, effect policy, terminal callback, lifecycle owner, and
   durable WorkGraph. Record and remove semantic alternatives only with
   migration evidence.

2. **Small native ACI.** Stabilize a domain-neutral set of read, grep/search,
   list, write/edit, command/test, and bounded process operations. All paths use
   Env capabilities; none calls the host filesystem or subprocess as a hidden
   fallback. Support native parallel tool calls, real completion order,
   declaration-order queries, bounded output, ArtifactRef spill, structured
   errors, and explicit loss. Keep tool schemas compact and provider-neutral.

3. **Typed sandbox policy.** Evolve the existing single SandboxBackend contract
   in place. Replace free-form security arguments with a typed policy/spec,
   capability discovery, identity, generation/lease, attestation, resource/
   egress facts, and cleanup receipt. Compatibility adapters may read old
   settings but cannot advertise unproven guarantees.

4. **Task-exclusive Docker reference.** Stage a private copy/worktree volume
   rather than directly granting the Agent a writable host repository bind.
   Enforce and inspect: digest-pinned/recorded image identity, non-root,
   read-only root, explicit writable workspace/result mounts, no credential or
   controller-private mounts, network-off by default, no Docker socket, dropped
   capabilities, no-new-privileges, bounded pids/CPU/memory/tmp/output/time,
   input/workspace digests, unique ownership labels, and deterministic scoped
   cleanup. Missing Docker or an unavailable platform is typed blocked, never
   passed or silently downgraded.

5. **Boundary adversaries.** Test traversal, symlink/TOCTOU, Git metadata,
   unexpected mount, socket/device/namespace access, local/private endpoint,
   DNS/egress policy, secret environment/arguments/output, fork bomb, resource
   exhaustion, oversized output, cross-session contamination, stale lease,
   late worker, repeated destroy, controller loss, and leaked-resource
   detection. Never use global Docker prune.

6. **Session/WorkGraph binding.** Persist logical sandbox identity, policy/image
   digest, capability set, owner generation, lease, workspace/input digest,
   quiescence, and cleanup status as a canonical snapshot/event component.
   Restore must re-resolve and attest; fork/delegate/spawn/fan-out allocate new
   least-authority sandboxes; handoff fences the previous owner; join/cancel
   preserves unknown and late-result truth. No child receives parent filesystem,
   network, artifact, or credential authority implicitly.

7. **Direct/tool parity.** Direct Session methods and model-callable handoff,
   delegate, spawn, fan-out, and join tools must produce the same durable
   descriptor/operation receipts and call the existing scheduler. Remove or
   retire nested-Engine/thread-pool semantic alternatives; do not duplicate
   WorkGraph mutations in tools.

8. **Lifecycle/effect truth.** Keep sync, async, thread, subprocess, HTTP, MCP,
   Env, and background ownership explicit. Python threads do not gain fake hard
   cancellation; remote timeout is not remote cancellation; committed effects
   are not replayed; unknown effects require reconciliation. Flush waits for
   actual durability acknowledgement.

9. **MCP consolidation.** Put MCP-discovered tools behind the same registry,
   argument validation, permission, ToolResult, cancellation, lifecycle,
   artifact, and sandbox policy as local tools. Decide and document SDK
   parity/migration without exposing a second public tool runtime.

10. **Replaceability.** Publish one external-package-style backend adapter and
    one tool/runtime adapter that pass public conformance without Engine/store
    private access. A fake qualifies protocol semantics only. Docker is the
    required real isolation reference; gVisor, microVM, and managed backends are
    optional capability-specific follow-ups and must not be falsely claimed.

11. **Producer bundle.** Publish executable A/B/D handoff fixtures: sandbox
    snapshot component, ACI outcomes, lifecycle/effect matrix, WorkGraph
    operations, MCP parity, attestation/cleanup, privacy projections, and exact
    config requirements.

### 7.6 Required tests

- class/function/async tools, native parallel completion, partial snapshots,
  timeout/cancel/late/duplicate/stale/missing-slot closure;
- permission/interceptor final revalidation and secret-safe failures;
- real Docker create/inspect/read-edit-test/denial/process-loss/cleanup on the
  supported host, including container-absence proof;
- adversarial filesystem, mount, egress, secret, resource, ownership, cleanup,
  and contamination matrix;
- Memory/SQLite Session pause/restore/fork and durable child operations with
  sandbox binding;
- MCP lifecycle/conformance and independent structural adapters;
- architecture/public/static/lint/type/full-suite/diff gates.

Do not turn an unavailable Docker/gVisor/microVM environment into a skip-based
pass. Record exact reproducible commands and the required host capabilities.

### 7.7 Forbidden claims and edits

Do not claim arbitrary Python hard cancellation, universal external exactly
once, Docker as a VM boundary, unrestricted safe egress, or S4 completion. Do
not implement secrets inside the sandbox, a cluster scheduler, benchmark policy,
or another Env/ToolResult/WorkGraph architecture.

### 7.8 Final report

Report: outcome; source; census; canonical execution path; ACI surface;
sandbox policy/identity/staging; Docker platform evidence; adversarial matrix;
Session/WorkGraph authority; lifecycle/effects; MCP; independent conformance;
fixtures/digests and A/B/D handoffs; interface delta; validation; typed blocked
platforms; unsupported claims; gaps; commits; clean HEAD.

---

## 8. Instruction for Agent D — Trajectory, qita, evaluation, and release DX

Copy this entire section to the Agent assigned Lane D.

### 8.1 Mission

You own S4 Lane D: make the framework's execution facts storable, inspectable,
evaluable, exportable, and installable. Prepare the single Trajectory plane and
qita migration, but do not freeze or switch defaults until G5 consumes exact
same-wave A/B/C producer bytes.

### 8.2 Fixed source and setup

- Exact implementation ancestry:
  `c4e621d05960a4e2f06cb4864f6a8cb8275ac067`
- Branch: `codex/v4-s4-d-trajectory-release`
- Worktree: sibling `WhitzardOS-s4-d`

Apply the same remote verification and safe worktree rules as Section 3.

### 8.3 Required reading

- root/package AGENTS files and Tasks 05, 08, 10–16;
- current RuntimeEvent, trace compatibility, tracing/Trajectory, sinks, stores,
  readers, exporters, renderers, qita, checkpoint/replay/fork, WorkGraph,
  evaluation, metrics, benchmark, HF/leaderboard, and artifact paths;
- package metadata/extras, CI/release workflows, docs navigation, quickstarts,
  examples, templates, and public-interface tests;
- exact S3/G4 producer receipts and current candidate-readiness scripts.

### 8.4 Writable lease

Primary ownership:

- `qitos/tracing/**` and bounded compatibility adapters in `qitos/trace/**`;
- qita read-only paths and commands;
- `qitos/evaluate/**`, `qitos/metric/**`, exporters, trajectory benchmarks, and
  related public conformance tests;
- packaging metadata/extras and fresh-install qualification scripts;
- lane-owned teaching examples/doc drafts that do not edit shared navigation;
- `docs/internal/plans/s4_d_trajectory_release.md`.

Do not edit config/CLI Session mutation, providers/context, tools/sandbox, or
frozen shared documents. qita may add/read inspection views but never mutate
Session or WorkGraph.

### 8.5 Required work

1. **Exact data-plane census.** Extend the writer/reader/public-surface/removal
   ledger across RuntimeEvent, Session, model transactions, reasoning,
   continuations, tools, effects, artifacts, sandbox, compaction, steering,
   checkpoints, budgets, WorkGraph, spans, renderers, trace compatibility,
   qita, evaluation, exporters, benchmarks, and packaging. Every canonical,
   derived, compatibility, or deprecated decision needs a consumer and
   retirement gate.

2. **Single Trajectory candidate.** Evolve the existing candidate in place; no
   public version-suffixed families. Define ordered records, identities,
   lineage, generations, operation/effect facts, privacy projections, loss,
   integrity, and schema evolution rules. Historical trace remains readable
   through one bounded compatibility reader, not as a second writer truth.

3. **Crash-safe store path.** Qualify the canonical writer/store/reader contract
   for append/commit atomicity, abrupt process loss, reopen, integrity, index
   rebuild, bounded query/replay, artifact references, concurrency, flush/close,
   corruption, disk/full I/O failure, and required versus optional sink
   backpressure. Memory and a durable local reference must share conformance;
   a third-party-style store must pass without private access.

4. **Reader and qita parity.** Make qita board/session/graph/timeline/item,
   replay, export, and live polling depend only on the reader boundary. Prove
   parity between candidate and historical inputs for shared semantics and show
   explicit unknown/loss for non-shared semantics. Keep qita's current default
   unchanged in this independent lane; publish an exact G5 switch procedure and
   rollback gate.

5. **Evaluation/export extension.** Freeze a store-independent evaluator view
   with version/provenance/loss facts and executable third-party evaluator
   conformance. Provide canonical exact re-import plus explicitly lossy public
   exports; no exporter may silently discard tool, reasoning, ownership,
   sandbox, or effect uncertainty.

6. **Privacy and portability.** Separate raw/private, redacted/public, and safe
   diagnostic views. Test secrets, auth headers/cookies, provider raw payloads,
   artifact bodies, POSIX/Windows/UNC/file/home paths, local/private endpoints,
   cycles, deep/large containers, and non-echoing findings. Hashes prove byte
   identity, not sanitization or publication rights.

7. **Measured storage evidence.** Benchmark candidate versus current trace and
   naive JSON using representative long and unrelated Agent fixtures. Measure
   actual bytes, append/read/replay/query latency, artifact deduplication, and
   optional gzip/zstd/index choices with environment identity and repeated
   runs. Do not select SQLite/compression/index or claim gains without data.

8. **Distribution matrix.** Rationalize extras for advertised providers, qita,
   Docker, MCP, evaluation, and optional integrations. Build wheel and sdist,
   run twine, then use clean virtual environments to import advertised surfaces,
   run `qit --help`/`qita --help`, and execute two unrelated offline reference
   Agents from installed artifacts only. No repository-private import/path may
   be required.

9. **Same-wave readiness.** Build a strict, non-echoing readiness inventory for
   Lane A authoring/Session facts, Lane B provider/context facts, and Lane C
   tool/sandbox/work facts. It must validate exact commit/path/digest/schema/
   authority/test-node/current-writer identity and one blocker per missing or
   invalid requirement. Because those commits do not exist at branch start,
   independent Lane D must finish `waiting_on_a_b_c`, `schema_frozen=false`,
   `default_reader_switched=false`, and with no publication/performance claims.

10. **G5 handoff.** Supply deterministic commands that, after A/B/C replay,
    ingest exact producer receipts, regenerate candidate fixtures, run reader
    parity, freeze the schema, enable the canonical writer for both golden
    paths, switch qita's default, re-run benchmarks/install tests, and rollback
    if any invariant fails. Include patch-ready bilingual docs and release notes.

### 8.6 Required tests

- record/schema/integrity, sink/store/reader/exporter/evaluator conformance;
- abrupt-exit/reopen/corruption/backpressure/concurrency and exact re-import;
- qita historical/candidate parity, bounded live polling, graph/timeline facts,
  and typed unavailable source;
- privacy/path/secret/oversize/cycle/publication qualification;
- reproducible benchmark dry-run and real measurement modes with typed readiness;
- build, twine, clean-venv extras matrix, installed CLI/import, and two unrelated
  offline wheel consumers;
- architecture/public/static/lint/type/full-suite/diff gates.

### 8.7 Forbidden claims and edits

Do not freeze the schema, turn on the candidate writer by default, switch qita's
default, claim publication or performance benefits, or mark S4/G5 complete in
the isolated lane. Do not implement qita mutation, another Session store, or a
product dashboard/control plane.

### 8.8 Final report

Report: outcome/readiness; source; census; canonical/derived/compatibility
decisions; candidate schema; store/durability; reader/qita parity; evaluation/
export; privacy/publication; measurements; packaging/extras/clean-wheel
consumers; A/B/C inventory; exact G5 procedure; fixtures/digests; interface
delta; validation; unsupported claims; gaps; commits; clean HEAD.

---

## 9. G5 entry criteria after the four Agents finish

Do not launch convergence merely because all four branches are clean. G5 may
start only when:

- A publishes the exact public path, Session-default fixture, extension slots,
  cleanup ownership, and surface budget;
- B publishes a passing transaction/provider/context producer and independent
  provider conformance kit;
- C publishes passing ACI/ToolRuntime, real Docker attestation/cleanup, durable
  work binding, MCP, and sandbox conformance evidence;
- D publishes the unfrozen candidate/readiness consumer, qita parity,
  store/export/eval conformance, package matrix, and exact switch procedure;
- every branch starts at exact `c4e621d...`, is clean, contains committed
  evidence, and has no shared-file or foreign-lease edits;
- every required offline gate passes; optional live/platform limitations are
  typed and do not conceal framework invariant failures.

G5 is one separate integration task. It replays A -> B -> C -> D, repairs only
integration defects, consumes exact committed producers, freezes/switches the
data plane if qualified, updates shared documentation once, and re-runs the
complete gate in both the convergence and primary worktrees. Promotion,
non-force push, default-branch change, package publication, and worktree cleanup
remain distinct decisions.

## 10. Expected capability after G5, not after isolated lanes

If G5 passes, QitOS will provide a credible framework baseline for building
Codex/OpenCode/Claude-Code/OpenClaw-class systems:

- a concise declarative and Python authoring path over durable Sessions;
- pause, restore, steer, fork, and durable multi-agent work controls;
- modern provider-neutral message/tool/reasoning/context semantics;
- native bounded parallel ACI and replaceable tool/provider/context contracts;
- default-safe Docker-backed execution with truthful isolation receipts;
- a stable Trajectory/qita/evaluation/export plane;
- clean-wheel templates and two independent installed consumers.

It will still not be a hosted product, universal strategy library, distributed
cluster scheduler, arbitrary-thread hard canceller, or guarantee of task/model
success. Those boundaries are a sign of a mature framework, not missing honesty.
