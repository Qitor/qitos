# G4-L3-R5 framework conformance and promotion plan

Status: active
Updated: 2026-09-02
Fixed baseline: `851f7902f15da670e72f4c04d7453cf37201aee7`
Candidate branch: `codex/v4-s3-g4-convergence`
Starting candidate: `0bda057a308983d6eaa2fb0465df0ea7911109cb`

## Responsibility boundary

QitOS guarantees runtime correctness: isolated Session state, explicit fork and
context-transfer semantics, exact durable budget admission, bounded model
projection, typed provider-stage failures, safe sandbox execution, persistence,
and truthful trajectory facts. Agent authors own prompts, strategies, toolsets,
context and compaction policy, declared budgets, provider selection, reducers,
and task accuracy. Providers own service availability, rate limits, model
capability and output stability, and server-side request constraints. A typed
external failure is informational capability evidence unless it exposes a QitOS
invariant failure.

QitOS does not guarantee task success for every Agent or model.

## Exact-source census

```text
Engine
  -> Session._create -> generation-0 snapshot
  -> Session.run -> restore/bind -> Engine.run -> commit/unbind
  -> Session.fork -> explicit source snapshot clone
  -> Session._prepare_work_descriptor -> durable child + transfer receipt
  -> ContextTransferPlan/execute_context_transfer
  -> ConversationSnapshotComponent/ExchangeLog
  -> RequestView/context selection
  -> ProviderCodec encode/projection
  -> provider request admission -> transport -> decode
  -> ToolResult canonical persistence -> bounded model projection
  -> snapshot/head/CAS restore
```

The current defect is exact-source deterministic. `Session._create()` captures
Engine conversation/runtime globals left by the preceding Session. Direct fork
correctly clones an immutable source snapshot, but fan-out/delegate currently
reuse that clone without rebasing the child from the explicit transfer receipt.
Child budget allocations are durable work-graph metadata but are not connected
to provider dispatch admission. Provider execution also catches encode,
projection, transport, and decode inside one broad transport-normalization
boundary.

## File lease

Lease owner: G4-L3-R5 convergence owner

Files: `qitos/engine/engine.py`, `qitos/engine/session_runtime.py`,
`qitos/engine/_snapshot_components.py`, `qitos/engine/_model_runtime.py`,
`qitos/models/provider.py`, `qitos/core/tool_result.py`, and directly related
tests/docs.

Semantic purpose: isolate durable Session runtime state; distinguish direct fork
from child transfer; enforce durable request budgets at dispatch; bound model
projection; classify provider stages.

Expected package: R5 framework conformance through final promotion.

Other lanes: no parallel lane is active; no adapter is required.

## Work packages

1. Add explicit Session runtime bind/reset/unbind behavior and independent
   generation-0 capture. Preserve direct fork inheritance.
2. Rebase delegate/fan-out children from authorized transfer receipts and make
   the child task the sole active task.
3. Extend the existing RuntimeBudget and snapshot component with one durable
   model-request counter. Intersect parent remaining, transfer, declaration,
   runtime, and configured/provider ceilings; admit immediately before transport.
4. Keep canonical ToolResult persistence complete while bounding the model view,
   recording projection loss, and proving 10MB inputs stay bounded.
5. Split provider encode, request projection, connection/HTTP transport, and
   response decode failures into the closed safe taxonomy.
6. Add deterministic conformance tests and the required responsibility document;
   run the fixed-Python full validation on committed bytes.
7. Run at most one three-request GLM informational smoke. If it exposes no new
   framework invariant failure, fast-forward, revalidate, push without force,
   retire clean worktrees, publish the final docs-only S4 baseline, and push it.

No public root export, reviewed aggregate export, Engine constructor parameter,
parallel Engine/SessionStore/ExchangeLog, or versioned Agent/Session type is
authorized.
