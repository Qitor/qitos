# Task 04 — control context, artifacts, and transaction-safe history

Status: design approved; implementation waits for Tasks 02A–02B and 03A
Depends on: Task 02 request views; Task 03 tool outcomes
Unblocks: Task 12 complete snapshots, Task 13 context transfer, and Task 05
Risk: high — context survival and model-visible behavior

---

## 1. Goal

Give long-running agents a precise way to add changing control information,
externalize large results, and compact history without losing tool transactions
or durable references. Do not collapse these mechanisms into a generic “memory”
bucket.

## 2. Four distinct concepts

| Concept | Lifetime | Owner |
|---|---|---|
| Human steering | User intent inserted while running | Engine interrupt/turn boundary |
| `ContextBlock` | Transient control information for one or more request views | Engine + injected provider |
| Semantic memory | Agent-owned recall across steps/runs | existing core/kit memory contracts |
| `ArtifactRef` | Addressable large/raw content | artifact store service |

Tool execution's existing `runtime_context` remains a separate concept and name.
Task 12 snapshots references and policy/digests for these concepts, not live
provider/store objects. Task 13 transfers an explicit selection of immutable
references between work items and records the omissions; it does not mutate the
source history to manufacture child context.

## 3. `ContextBlock` contract

A context provider is passed explicitly to Engine/Agent construction. There is no
name-based global registry.

Minimum block fields:

- stable key and source;
- content blocks, not only text;
- optional revision plus a framework-computed digest;
- priority and token/character budget;
- requested placement and persistence horizon;
- sensitivity/redaction classification.

The provider returns raw content. The framework owns wrapping, escaping,
deduplication, budgeting, placement reports, and telemetry.

Revision equality alone never suppresses a block. A block may be omitted only
when the current `RequestView` or provider continuation demonstrably contains the
same digest. Compaction or stateless requests therefore reinsert required blocks.

Placement is capability driven—system/developer/user/after-tool projection—not a
mutation of the persistent exchange log. Human steering is never encoded as a
runtime context block.

## 4. Artifact store

The artifact store is a content-addressed service shared by tool results and
trajectories. Promote an abstract contract to core only once those two consumers
exist; the filesystem implementation belongs in kit or trace, not core.

Required behavior:

- SHA-256 identity and deduplication;
- media type, byte length, encoding, sensitivity, and provenance metadata;
- atomic write and integrity verification on read;
- explicit retention/cleanup ownership;
- `ArtifactRef` serialization with no host path leakage;
- private raw storage separated from redacted/public export views;
- a model-visible summary and retrievable next action before payload
  externalization.

“Evidence” may be a domain interpretation of an artifact; it is not the generic
store name.

## 5. Transaction-safe history policy

Compaction operates on complete exchanges, never arbitrary message counts.

It must preserve:

- system/cache anchors selected by policy;
- open tool batches in full;
- the configured recent exchange window;
- human steering not yet consumed;
- required context digests;
- every surviving `ArtifactRef` and continuation anchor;
- explicit synthetic results used to close interrupted batches.

Durable agent state remains in `StateSchema` or semantic memory. Do not add vague
“durable fields” to arbitrary history messages.

Summary compaction records its input exchange IDs, output digest, model/policy,
and declared losses. Retrieval of an externalized artifact is a normal tool or
store operation, not hidden prompt expansion.

## 6. Work packages

### 04A — context provider and request-view integration

- Define block/provider contracts and placement reports.
- Add explicit provider injection and a compatibility adapter for
  `AgentModule.prepare()` where appropriate.
- Implement digest visibility, stable wrappers, and budget rules.
- Test stateless requests, compaction reinsertion, and queued steering.

### 04B — artifact contract and filesystem store

- Define `ArtifactRef`, atomic storage, integrity checks, and retention policy.
- Integrate Task 03 tool outcomes as the first consumer.
- Add sensitive/raw versus export-redacted tests.

### 04C — exchange compaction

- Refactor CompactHistory selection onto Task 02 exchanges.
- Preserve full parallel batches and native continuation anchors.
- Record deterministic compaction reports and loss declarations.

### 04D — externalization and memory integration

- Externalize oversized canonical tool results only when a usable projection and
  retrieval path exist.
- Integrate existing Memdir/Markdown memory rather than replacing all memory
  classes.
- Demonstrate one run-scoped and one cross-run memory consumer.
- Supply resolver references, retention facts, and versioned snapshot/transfer
  receipts to Tasks 12 and 13.

## 7. Acceptance criteria

- [ ] Identical visible digests are not duplicated in one request, but required
  blocks reappear after compaction or on stateless transport.
- [ ] Human steering appears once at the next completed exchange boundary.
- [ ] Provider placement never rewrites persistent exchange history.
- [ ] Open/parallel tool batches remain structurally valid through compaction.
- [ ] Artifact reads verify content identity; refs contain no host paths.
- [ ] Raw sensitive data is not emitted by public exporters or telemetry.
- [ ] Oversized tool results retain model-visible completeness and retrieval
  guidance.
- [ ] Existing memory APIs continue to work through documented adapters.
- [ ] A fresh-process Task 12 restore resolves context/artifact/memory references
      without persisting live stores, secrets, or host paths.
- [ ] A Task 13 handoff/delegate fixture reports selected and omitted context,
      preserving the source ExchangeLog unchanged.

## 8. Verification

```bash
pytest -q tests/engine/test_context_blocks.py tests/engine/test_request_view.py
pytest -q tests/core/test_artifact_ref.py tests/kit/test_artifact_store.py
pytest -q tests/test_compact_history.py tests/engine/test_exchange_compaction.py
pytest -q
flake8 qitos/core qitos/engine qitos/kit qitos/trace
mypy qitos/core qitos/engine qitos/kit qitos/trace
```

## 9. Stop-and-escalate decisions

Stop for review before:

- making context providers global or discoverable by string name;
- rewriting persistent exchanges to satisfy one provider;
- storing raw secrets without an explicit at-rest policy;
- externalizing content without a retrieval path;
- replacing semantic-memory implementations as part of compaction work;
- choosing protected-window defaults from campaign constants without a benchmark;
- serializing live context providers, memory objects, artifact stores, or secrets
  into a session or work-graph snapshot.
