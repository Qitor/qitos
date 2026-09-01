# v4 framework round — decisions, metrics, and delivery contract

Status: active acceptance anchor
Updated: 2026-08-31
Scope: Tasks 01–05 and 08–14

---

## 1. North star

QitOS is a research-first agent framework: one domain-neutral
`AgentModule + Engine` kernel that makes agent execution mechanisms reusable in
the same way that a tensor/runtime framework makes learning mechanisms reusable.

The CyberGym/Cyborg campaign is evidence, not product scope. We absorb mechanisms
that can be described only with agent-execution vocabulary: state, observation,
decision, action, tool, model, context, memory, artifact, trace, budget, hook,
protocol, and experiment. Campaign strategy, vulnerability vocabulary, benchmark
heuristics, and task-specific renderers remain out of tree.

## 2. What success means

G4-L2 adds an admission condition shared by these gates: a complete launch must
come from the strict, digest-bound `qitos.agent/v1` configuration and resolve
credentials only at composition. A sixteen-gate offline round now proves the
parser, resolvers, native-tool continuation, Session/process restore, real
Docker qualification, privacy, and reachable success state before any live
provider request. This evidence is necessary for S3 promotion but does not
complete the broader Task 14 threat model.

The old “10% agent” target mixed code size and task performance and could be gamed
by weakening the reference agent. v4 uses seven independent gates instead.

### Gate A — mechanism removal on the same agent

For each completed task, audit the out-of-tree campaign agent before and after
adoption. Record the framework glue removed by category and its LOC. Compare the
same agent, prompts, task subset, model, and runtime settings. Performance must
remain within a predeclared non-inferiority band.

Categories tracked by v4:

- provider message/reasoning assembly;
- parallel tool-batch bookkeeping;
- tool validation, recovery, projection, pagination, and output budgets;
- control-context injection and transaction-safe compaction;
- artifact externalization and trajectory plumbing.

### Gate B — a second independent consumer

Every new core contract must be exercised by the campaign agent and at least one
unrelated agent, example, or protocol fixture. A single consumer is insufficient
evidence for promotion into `qitos.core`.

### Gate C — model protocol conformance

Offline fixtures cover OpenAI Chat Completions, OpenAI Responses, Anthropic, and
Gemini/GLM-compatible paths. Opt-in `e2e` tests cover live endpoints when keys are
available. Conformance includes multimodal content, ordered tool calls/results,
reasoning continuation, steering boundaries, and explicit loss reports.

### Gate D — replay and storage correctness

The canonical QitOS format must round-trip losslessly. Exporters to external
training formats declare their version and any information they drop. Storage
size targets come from a committed benchmark against representative runs; v4
does not pre-commit to an arbitrary compression ratio.

### Gate E — framework quality

Each merge keeps the full test suite, architecture boundaries, stable-surface
flake8, and stable-surface mypy green. New public APIs include compatibility and
migration tests. Task 08 adds a repository-wide no-regression ratchet so the
stable-surface gate cannot be mistaken for whole-package coverage. No task is
complete while its status document disagrees with the code.

### Gate F — durable session continuity

A representative run must pause at a declared safe boundary, terminate its
process, restore through a fresh Engine/composition root, and continue with the
same state, exchanges, completed tool slots, queued steering, context/artifact
references, budgets, and trace lineage. A committed effect is not repeated;
uncertain effects remain typed `outcome_unknown` rather than being retried or
reported as exactly once without backend proof.

### Gate G — durable multi-agent composition

Two unrelated multi-agent methods must use the same handoff, delegate, fan-out,
spawn, fork, and join primitives. A partial child graph survives process restart,
ownership remains single-writer, and qita can navigate parent/child/transfer
lineage without decoding run-name conventions. Role strategy and product-specific
coordination remain out of tree.

## 3. Demonstration metric

A compact coding-agent example remains a developer-experience smoke test. Target:
roughly 50–100 lines excluding prompts and configuration, using the public
coding-toolset and session APIs and no private Engine helpers. It demonstrates
start, pause, fresh-process resume, one delegated child, and qita inspection. It
is not a substitute for the seven gates above and has no standalone pass-rate
target.

## 4. Architecture decisions fixed for this round

1. Conversation state has three layers: persistent `ExchangeLog`, ephemeral
   `RequestView`, and provider-owned codecs/continuation state.
2. Parallel actions use the existing `Decision.actions` and ActionExecutor path;
   v4 validates and completes it rather than introducing a second scheduler.
3. ACI upgrades the existing `qitos.kit.tool` and `qitos.kit.toolset` hierarchy.
   There is no `qitos.kit.aci` parallel package.
4. Human steering, control context, semantic memory, and artifact storage are
   distinct concepts with distinct lifetimes.
5. QitOS owns a lossless canonical trajectory format. OpenAI, Hermes, ShareGPT,
   and ms-swift shapes are versioned exporters, never the storage schema.
6. `qitos/trace` v1 stays readable throughout v4. Migration is dual-read or
   dual-write until parity is demonstrated.
7. Session, run, work item, checkpoint, exchange, tool call, and agent identities
   are distinct. A resumed execution advances a session/work item with a new run.
8. Checkpoint v2 is the persistence mechanism: a mutable session-head index
   points to immutable snapshots. `RunState` is an adapter/view, not a second
   durable truth, and no parallel `SessionStore` is introduced.
9. Handoff, delegate, fan-out, spawn, fork, and steering have distinct ownership
   semantics but share one durable work graph and the existing Engine loop.
10. Pause is cooperative at declared safe boundaries. QitOS does not serialize
    Python stacks or claim hard thread cancellation/exactly-once external effects
    without backend evidence.

## 5. Delivery sequence

```text
Task 01 baseline ──→ Task 02 model I/O ──→ Task 04 context/artifacts ──→ Task 05 trajectories
        └─────────→ Task 03 tool outcomes ────────────────┘

        └─────────→ Task 08 quality gates ──→ Task 09 lifecycle/errors
                                      Tasks 02–05 + 08–09 ──→ Task 10 consolidation

Tasks 02–04 + 09 ──→ Task 12 durable sessions ──→ Task 13 multi-agent work graph
             Tasks 12–13 lineage ───────────────→ Task 05 schema freeze/qita
Tasks 03 + 09 + 12–13 ──→ Task 14 safe sandbox execution ──→ S4/G5 public DX
```

Task 02 and Task 03 may proceed independently after Task 01. Task 04 depends on
their contracts. Task 05 depends on the exchange and artifact schemas. Task 08
can start immediately; its first ratchet should land before large implementation
diffs. Task 09 coordinates semantic changes with Tasks 02, 03, and 05. Task 10
collects usage evidence early but removes or consolidates surfaces only after
their canonical replacements are proven. Task 12 starts with identity/snapshot
contracts after G1 and then proves a single-agent clean-process vertical slice.
Task 13 starts only after that vertical slice can durably recover one work item.
Task 14 reuses the Env/tool lifecycle plus Session and WorkGraph identities to
make command-running research/coding agents safe by default; it must not create
a vendor-specific Engine or tool API.
Task 05 may continue its census, fixture qualification, and benchmark scaffold,
but it does not freeze trajectory v2 until session/run/work-item/ownership
lineage from Tasks 12–13 is available.

Current gate truth: S2 is closed and promoted. The S3 convergence candidate now
contains Session fork, authority transfer, a durable multi-agent scheduler, and
graph-aware read-only qita consumption, and its deterministic G4 tests pass. It
is not yet promoted: registered live-model profiles still lack executable
capability/trajectory/agent receipts. Trajectory remains unfrozen and the
candidate reader is not the qita default. The executable S3 ownership and G4
matrix live in
[`s3_durable_multi_agent_wave.md`](../internal/plans/s3_durable_multi_agent_wave.md).
Task 14 is now a required S4/G5 architecture because current `DockerEnv` provides
Docker execution but not a qualified untrusted-code sandbox.

The authoritative multi-agent dispatch and merge sequence is
[`11-four-lane-execution-playbook.md`](11-four-lane-execution-playbook.md). It
organizes these source tasks into four ownership lanes and evidence gates; the
current S3 producer/consumer freeze is A -> B -> C -> D -> G4. It does not
replace the task-level contracts.

## 6. Coding-agent working contract

Each task below is an executable specification. A coding agent must:

1. read root and nested `AGENTS.md` files before editing;
2. create or update the matching implementation plan under
   `docs/internal/plans/` when the work spans multiple PRs;
3. deliver the listed work packages in order, one reviewable PR per package;
4. update the task document's evidence table after every merged package;
5. run the task-specific checks plus the repository verification gates;
6. stop at an explicit decision gate instead of inventing a new public API;
7. keep CHANGELOG, README, user docs, examples, and EN/zh pages synchronized.

## 7. Progress reporting

Report only evidence-backed numbers:

- mechanism LOC removed from the same out-of-tree agent;
- provider conformance cases passed;
- canonical replay invariants passed and exporter losses declared;
- measured storage bytes before/after;
- full tests, boundary tests, lint, and typing status.

Do not report framework LOC growth or cherry-picked commit ancestry as progress.

## 8. Four-lane dispatch rule

When more than one coding agent is active, assign work through the four-lane
playbook. The G1 repair wave keeps its historical A/B/C/D ownership. After G1,
the four capability lanes are:

- Lane A — session runtime, persistence, and sandbox identity/restore binding
  (Task 12 plus owned Task 09/14 work);
- Lane B — conversation, providers, context, memory, artifacts, and sandbox-safe
  credential/context transfer (Tasks 02/04/14);
- Lane C — tools, sandbox backends, and the durable multi-agent work graph
  (Tasks 03/13/14);
- Lane D — trajectory, qita, replay, sandbox receipts, and developer experience
  (Tasks 05/14).

Quality/release trust becomes a cross-lane merge gate run by the integration
owner, not a place to park all framework behavior. Task 10 cleanup returns to
the semantic owner of the replacement.

Cross-cutting Task 09 and Task 10 work returns to its semantic lane. No agent may
create a parallel abstraction merely to avoid a shared-file lease or contract
handoff.
