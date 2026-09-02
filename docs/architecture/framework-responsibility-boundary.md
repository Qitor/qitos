# Framework, Agent, and provider responsibility boundary

Status: G4-R5 conformance contract
Updated: 2026-09-02

QitOS guarantees runtime correctness. QitOS does not guarantee task success for
every Agent/model. Release qualification therefore separates deterministic
`FRAMEWORK_CONFORMANCE` from the informational
`LIVE_AGENT_CAPABILITY_MATRIX`.

## QitOS framework guarantees

The framework owns mechanisms and their truthful receipts:

- independent Sessions isolate state, conversation, continuation, steering,
  partial batches, tool-use satisfaction, request views, and budgets;
- direct forks retain explicit snapshot lineage while future writes remain
  independent; delegate, fan-out, and handoff receive only a declared
  `ContextTransferPlan` projection and receipt;
- the effective child budget is the intersection of parent remaining budget,
  transfer grant, child declaration, runtime ceiling, and provider/config
  ceiling, and provider admission is enforced before dispatch;
- snapshots preserve identity, generation, owner, terminal failure, request
  accounting, and restart-safe continuation;
- canonical persistence is distinct from bounded model projection. Tool and
  environment views are allowlisted, redacted, bounded, and carry selection or
  loss receipts; required context fails closed;
- provider encode, request projection, transport, status normalization, and
  response decode failures retain a closed, non-echoing stage code and an
  accurate `provider_request_sent` fact;
- tools execute according to declared parallelism, timeout, cleanup, and
  sandbox policy. A Docker claim must be backed by inspection and cleanup
  evidence; `unsafe_host` is never described as isolation;
- Trajectory and qita report what actually happened. Failure, budget
  exhaustion, duplicate/late results, and missing required transfer never
  masquerade as success.

These are deterministic framework conformance requirements. A violation blocks
promotion even if it was first observed during a live run.

## Agent developer responsibilities

The Agent developer owns policy: prompts and system instructions, strategy,
toolset selection, context contributors and compaction, budget size,
retry/fallback policy, provider/model selection, child decomposition,
join/reducer semantics, custom-tool output design, and final task correctness.
QitOS provides bounded policy hooks and truthful failure receipts; it does not
infer which domain material is important or claim that lossy compaction is
semantically lossless.

## Provider and external-service responsibilities

The provider owns endpoint availability, rate limits, actual model capability,
output stability, server-side context/request limits, and intermittent external
transport behavior. Correctly classified authentication, rate-limit, timeout,
connection, rejection, server, malformed-response, or native-tool capability
outcomes describe that profile; they are not automatically framework defects.

The distinction is strict in both directions. A model that does not follow a
prompt is not proof of a Session defect. Session cross-talk, a request-budget
overrun, secret disclosure, sandbox fallback, false accounting, false success,
or incorrect recovery is not excused as provider behavior.

## Qualification split

`FRAMEWORK_CONFORMANCE` is required and deterministic. It covers repository
tests, Session/fork/transfer isolation, durable request admission, persistence,
bounded projection, provider failure semantics, sandbox truth, deterministic
single- and multi-agent flows, privacy, qita/Trajectory, and packaging.

`LIVE_AGENT_CAPABILITY_MATRIX` is informational. It records real dispatch,
request count, native-tool expression, latency, provider availability, model
behavior, and task completion within a fixed user budget. A profile may report
`passed`, `model_request_budget_exhausted`, `provider_unavailable`, or another
typed failure without blocking promotion, unless the observation exposes a
required framework invariant violation.

## Explicit non-guarantees

QitOS does not claim a distributed scheduler, external exactly-once effects,
Python-thread hard cancellation, automatic understanding or lossless summary of
arbitrary domain content, or that every Agent/model completes its task. Unknown
external effects are not automatically retried.
