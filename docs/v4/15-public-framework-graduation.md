# Task 15 — public framework graduation

Status: S4 four-lane implementation planned; dispatch awaits remote baseline verification
Updated: 2026-09-03
Promoted S3/G4 runtime baseline: `f07b38647cf3b18a5235581224a1153b88fac397`
Fixed S4 implementation ancestry: `c4e621d05960a4e2f06cb4864f6a8cb8275ac067`
Depends on: Tasks 02–05 and 08–14; S3/G4 framework conformance
Milestone: G5 default-safe framework and release-candidate review
Risk: critical — public API coherence, safe defaults, migration truth, and
third-party usability

---

## 1. Goal

S4 turns the mechanisms already proved in S1–S3 into one coherent framework for
building long-running coding, research, and tool-using agents. A user should be
able to build systems in the class of Codex, Claude Code, OpenCode, or OpenClaw
without copying QitOS internals or accepting unsafe host execution by accident.

This is a framework-graduation wave, not another runtime rewrite. The existing
`AgentModule + Engine + Session + CheckpointStore + WorkGraph` execution truth
remains authoritative.

The two golden paths are:

```bash
qit run --config agent.yaml
```

and a small programmatic path that composes the same configuration, opens a
Session, and owns cleanup. The exact convenience spelling must be selected by
the Lane A API review; it must delegate to the existing composition and Session
rather than create another Agent, runner, store, or execution loop.

## 2. Why S4 is required

S3/G4 proves the hard runtime properties:

- isolated and durable Sessions;
- safe pause, fresh-process restore, fork, steering, and ownership fencing;
- explicit context/authority transfer;
- durable delegate, spawn, fan-out, handoff, and join semantics;
- bounded parallel tools, typed effects, and honest unknown outcomes;
- a structural sandbox contract with an inspect-backed Docker reference;
- typed provider stages and durable request admission;
- candidate Trajectory storage and read-only qita graph/timeline inspection.

The public product surface does not yet present those properties as one path.
The current quickstart still teaches environment variables, direct
`AgentModule.run()`, host-workspace-oriented coding helpers, and the frozen
trace board. The declarative path currently calls `Engine.run()` rather than
making durable Session ownership the normal path. Session control, WorkGraph,
sandbox receipts, candidate Trajectory, qita, packaging extras, and tutorials
therefore remain individually useful but collectively difficult to discover
and compose.

## 3. Responsibility boundary

QitOS owns reusable mechanism and truthful receipts:

- lifecycle, persistence, isolation, budgets, failure taxonomy, cleanup, and
  concurrency;
- provider-neutral request/response/tool-call representation;
- explicit context selection and loss;
- sandbox enforcement and evidence;
- durable ownership/work graph semantics;
- complete canonical facts plus bounded model/public projections;
- stable extension protocols and conformance suites.

Agent authors own prompts, policy, domain strategy, tool selection, context and
compaction choices, requested budgets, provider/model selection, reducers,
human-interaction design, and task accuracy. Providers own availability,
rate-limits, output quality, and server behavior. A typed model failure is not a
framework failure unless it exposes a QitOS invariant violation.

## 4. Non-negotiable architecture

1. One execution kernel: no second Engine, Session store, work scheduler,
   provider transaction, ToolResult, ArtifactRef, or Trajectory truth.
2. One public architecture: do not add public `V1`, `V2`, `Legacy`, `Next`, or
   similarly suffixed Agent, Session, Runtime, Trajectory, Tool, or config APIs.
   Historical wire readers may retain private schema identifiers.
3. Reuse the current `qitos.agent` configuration and credential-reference
   boundary. Environment lookup remains an explicit deployment compatibility
   adapter, never the beginner path.
4. Executable coding/research tools fail closed without an attested sandbox.
   `unsafe_host` remains an explicit opt-out and cannot claim isolation.
5. qita is a client of persisted runtime facts. It never owns mutation
   semantics or infers lineage from names, paths, or message text.
6. Domain strategies and showcase products remain out-of-tree. Only
   domain-neutral mechanisms, adapters, recipes, and teaching examples belong
   here.
7. Public-surface growth requires itemized review. Prefer contracting the
   34-parameter Engine constructor and hiding extension records from beginners.

## 5. S4 capability target

At G5, a framework user can:

- create or load an Agent with a model, tools, context policy, budgets, and an
  optional sandbox without importing persistence internals;
- run it through a durable Session and inspect, pause, restore, steer, and fork
  it through the same semantics in Python and the CLI;
- use native sequential or parallel tool calls with canonical outcomes,
  artifacts, effects, timeouts, and bounded model-visible output;
- delegate, spawn, fan out, hand off, and join child work through one durable
  WorkGraph API;
- replace providers, tools, context contributors, checkpoint stores, event
  sinks, evaluators, and sandbox backends through documented protocols and
  executable conformance kits;
- inspect the same Session and WorkGraph through qita, replay/export a stable
  Trajectory, and understand every declared loss or uncertainty;
- install the required extras in a clean environment and run two unrelated
  reference agents without repository-private setup.

## 6. Four S4 lanes

All lanes start from the exact fixed implementation ancestry above in separate
branches and worktrees, after it is pushed and verified. Shared README,
CHANGELOG, progress, navigation, and default-switch edits are leased to the G5
integration owner. The complete copyable instructions, file leases, branch
names, dependency model, evidence rules, and G5 entry gate are in
[Task 16](16-s4-parallel-wave-instructions.md).

### Lane A — Authoring, Session, CLI, and configuration

Mission: make the existing runtime pleasant without creating a facade that
competes with it.

Owned surfaces:

- `qitos/config/`, the thin public Session composition entry, and `qitos/cli.py`;
- Session control commands and compatible Python ergonomics;
- `qit new` scaffold, quickstart fixtures, and public-interface budgets;
- Engine-constructor contraction and compatibility warnings.

Required outcomes:

1. Perform a symbol/call-path census of `AgentModule.run()`, direct `Engine`,
   `AgentComposition`, `run_agent_config()`, CLI run, resume, checkpoint, and
   qita mutation-like paths.
2. Select one beginner composition object that is a resource owner, supports a
   context manager, creates the existing Session, and exposes only run/control/
   inspect operations. Do not add a new execution abstraction merely for naming.
3. Route the canonical declarative launch through Session. Preserve a deliberate
   stateless/ephemeral mode only if it is explicitly named and tested.
4. Provide typed CLI/Python create, inspect, pause, restore, steer, and fork
   behavior. Mutations belong to `qit` or the Session API; qita remains read-only.
5. Contract redundant Engine construction arguments behind
   `RuntimeComposition`/configuration with a documented migration period.
6. Generate one default-safe project that uses credential references, an
   attested sandbox, a durable local store, Trajectory, and a testable fake
   provider path.

Lane A must publish executable beginner-path fixtures before another lane copies
its API spelling.

### Lane B — Model transaction, messages, context, memory, and providers

Mission: make provider-neutral model interaction complete and easy to extend.

Owned surfaces:

- conversation, RequestView, prompting, context, compaction, memory, artifacts,
  continuation, codecs, provider adapters, and credential-safe provider config;
- native reasoning/multimodal/tool-call request and response conformance;
- the informational live capability matrix.

Required outcomes:

1. Prove ordered assistant/tool rounds, native parallel calls, steering, opaque
   reasoning continuation, multimodal items, and stateless replay across every
   advertised provider mode.
2. Give provider authors one documented adapter protocol and a standalone
   conformance kit covering encode, projection, transport, decode, capability
   loss, streaming, usage, continuation, and non-echoing typed failures.
3. Make context contributors, memory, compaction, and artifact references
   selectable from the stable config without serializing live objects or raw
   secrets. Every loss remains explicit.
4. Remove duplicated token/JSON-repair policy only after consumers use the
   canonical boundary.
5. Keep credentials behind resolver references. Custom headers and endpoint
   options must be classified so secret-bearing values never enter snapshots,
   Trajectory, diagnostics, or child transfers.
6. Run bounded live profiles only as capability evidence. Use a per-response
   ceiling suitable for agents (normally 10,240 tokens), explicit request and
   total-usage caps, zero hidden retry, and immutable private receipts.

### Lane C — Tools, ACI, sandbox, MCP, and durable multi-agent adapters

Mission: provide the safe execution substrate expected by mature agent authors.

Owned surfaces:

- canonical tools/toolsets, ActionExecutor/ToolRuntime, Env, permissions,
  artifacts/effects, MCP lifecycle, sandbox backends, and WorkGraph adapters;
- coding ACI such as read, grep, list, edit/write, shell, test, and process
  control.

Required outcomes:

1. Make the native ACI small, predictable, parallel-capable, bounded, and
   entirely Env-routed. Canonical output remains complete while model output is
   compact and loss-explicit.
2. Graduate the Docker reference from a qualification harness to a documented,
   task-exclusive backend with private workspace staging, non-root execution,
   read-only root, explicit writable mounts, network policy, dropped
   capabilities, no-new-privileges, process/CPU/memory/time/tmp bounds, and
   deterministic cleanup.
3. Bind sandbox identity, policy digest, ownership, and cleanup through Session
   fork/restore and WorkGraph child dispatch. No child inherits credentials or
   filesystem authority merely because its parent has them.
4. Publish a backend conformance kit usable by a real independent adapter. A
   structural fake is useful unit evidence but does not qualify platform
   isolation claims.
5. Keep hard-cancel and exactly-once claims capability-specific. Unstopped
   workers and unknown external effects remain typed unknown.
6. Put existing handoff/delegate/spawn/fan-out/join tools on the same durable
   Session operations as direct API calls; do not retain nested-Engine or
   thread-pool semantic alternatives.
7. Decide the official MCP SDK parity/migration behind the QitOS tool bridge;
   do not expose a second tool lifecycle.

### Lane D — Trajectory, qita, evaluation, documentation, and distribution

Mission: make execution inspectable, research-ready, and publishable without
creating a product-specific control plane.

Owned surfaces:

- `qitos/tracing/`, compatibility readers in `qitos/trace/`, qita read paths,
  evaluation/metrics, exporters, storage benchmarks, and documentation drafts;
- packaging/extras evidence coordinated with the integration owner.

Required outcomes:

1. Freeze the single public Trajectory contract only after consuming exact
   A/B/C facts for Session lifecycle, provider transactions, tools/effects,
   sandbox receipts, context loss, and WorkGraph lineage.
2. Select and qualify the canonical writer/store/reader path with crash-safe
   append/commit behavior, integrity, bounded query/replay, artifact references,
   and measured storage results. Do not claim compression or performance
   without reproducible numbers.
3. Keep one bounded compatibility reader for historical traces, then switch
   qita's default to Trajectory. Do not expose version-suffixed public classes.
4. Provide read-only Session, graph, timeline, attempt, ownership, budget,
   sandbox, loss, and failure inspection plus documented export/replay behavior.
5. Define a stable evaluator view independent of the chosen store and prove a
   third-party evaluator and exporter through conformance tests.
6. Replace the public quickstart/tutorial path with the actual stable config,
   Session, sandbox, WorkGraph, and qita flow. English and Chinese navigation
   and examples must agree.
7. Complete the extras/install matrix and fresh-wheel smoke for the advertised
   providers, Docker path, qita, MCP, evaluation, and optional integrations.

## 7. Cross-lane handoffs

Every producer handoff contains:

- exact source commit and merge base;
- committed manifest and fixture paths plus SHA-256 digests;
- public/extension/private classification;
- executable independent consumer tests;
- compatibility and removal prerequisites;
- unsupported claims and typed blockers.

Consumers import producer types and read committed fixtures. Copied enums,
parallel DTOs, receipt-only simulations, or tests that reach through private
attributes do not qualify integration.

Recommended dependency order is A contract -> B and C producers -> D data-plane
consumer -> G5 integration. Parallel work is allowed, but default switches and
shared documentation wait for exact producer consumption.

## 8. G5 acceptance gate

G5 may promote an S4 baseline only when all of the following pass on committed
bytes and again in the primary checkout:

1. One generated coding agent and one unrelated research/tool agent install and
   run from a built wheel through the documented API/config, with no internal
   imports or repository-only files.
2. The declarative and programmatic golden paths reach the same Engine, Session,
   tool runtime, sandbox, provider transaction, checkpoint head, WorkGraph, and
   Trajectory facts.
3. Pause, clean-process restore, steering, fork, delegate, fan-out/join,
   cancellation request, and failure inspection pass deterministic process-loss
   tests without sleep ordering or rerun-only evidence.
4. Executable tools cannot start before required sandbox attestation. Escape,
   mount, egress, resource, credential, cross-session contamination, and cleanup
   adversaries pass for the claimed backend/platform.
5. Provider, tool, checkpoint, sandbox, event-sink, evaluator, and exporter
   third-party conformance suites pass without Engine/store private access.
6. Trajectory is frozen, its canonical writer is enabled for the golden path,
   qita reads it by default, historical traces remain readable, and all lossy
   exports declare loss.
7. Public API and CLI reference tests match actual signatures and help output;
   no beginner documentation requires environment credentials, direct host
   execution, schema-version suffixes, CAS/envelope construction, or deprecated
   APIs.
8. Full tests, static ratchet, stable lint/type, architecture boundaries,
   public-surface budget, privacy/path scan, package build, twine, clean-venv
   extras matrix, and `git diff --check` pass.
9. Live model runs are bounded, secret-safe informational evidence. They block
   only when they reveal a framework invariant failure.
10. Default-branch and release readiness are assessed separately. Passing G5
    does not silently publish a package or change the GitHub default branch.

## 9. Default-branch and release decision

`DEFAULT_BRANCH_READY` may become true after G5 plus a documentation and
migration audit, branch-protection review, and verified clean install from the
candidate branch. `RELEASE_READY` additionally requires version/changelog,
artifact provenance, supported-Python/platform, dependency/extras, security,
license, and publication checks.

Changing the GitHub default branch, publishing PyPI artifacts, deploying a
service, or deleting retained branch refs requires explicit maintainer
authorization. After a promoted baseline is pushed and verified, remove only
the completed wave's clean, idle worktrees with non-forced
`git worktree remove`, prune registrations, and retain branch/commit refs unless
separately authorized.

## 10. Explicit non-goals

S4 does not promise a hosted control plane, a distributed cluster scheduler,
hard cancellation of arbitrary Python threads, exactly-once behavior in the
external world, universal model task success, built-in product strategy, or a
non-Python core rewrite. Those may use the stable protocols later; they are not
prerequisites for a mature Python agent-development framework.
