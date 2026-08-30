# S1 Lane C producer evidence

Status: C-owned producer complete; cross-lane qualification `waiting_on_lane_a`
Source branch: `feat/campaign-absorption`
Source commit: `c1efb0f4adde3e673bf181af5b1760c19a451ae2`
Producer branch: `codex/v4-s1-c-work-graph-contracts`
Producer commit: `c4b4943e9281e86a122bf1e59d8a5e4960eb397c`
Worktree: sibling `WhitzardOS-s1-c`

## Outcome

Lane C froze effect/recovery semantics on the sole canonical `ToolResult` and
added one contract-only `WorkGraph` with generation-checked ownership,
operations, child completion, late-result rejection, budget/capability grants,
and a snapshot component. It did not add runtime scheduling behavior.

The accepted vocabulary, beginner/advanced API decision, public-surface budget,
retry/reconciliation rules, operation semantics, ownership rules,
compatibility retirement ledger, and fixture manifest are in
`docs/architecture/stable-effects-and-work-graph.md`. The exact-source runtime
census and executable safe-boundary matrix are in
`docs/internal/evidence/s1_c_runtime_census.md`.

## Producer commits

1. `2d2e7bb` — runtime ownership/effect census and active plan;
2. `a213f1d` — beginner/advanced API and WorkGraph ADR;
3. `e5e1415` — canonical ToolResult effect/recovery fields;
4. `e0ea424` — canonical WorkGraph records and strict reader/writer;
5. `c4b4943` — recovery/work-graph fixtures and executable tests.

The following evidence-only commit appends this report and does not change the
producer fixture bytes.

## Exact digests

SHA-256 at producer commit `c4b4943e9281e86a122bf1e59d8a5e4960eb397c`:

| Artifact | SHA-256 |
|---|---|
| `qitos/core/tool_result.py` | `8aacffc25cae292aa1c43c491504f49393a557cd3ff2e0dc97d65a55f1e971ad` |
| `qitos/core/work_graph.py` | `a22ec558647af6868ee7942657fd09fb29cc01ba16e62242b47da5520f71070b` |
| `tests/fixtures/tool_results/recovery_outcomes.json` | `10e28d5c997c74420c27940f6e0897296bfabbd177119d1e24886775b4ae88e5` |
| `tests/fixtures/work_graph/contracts.json` | `a02b9a11b8094da636b3b663072215896922995ae4359f459132d318319ed366` |
| `docs/architecture/stable-effects-and-work-graph.md` | `08be875ff4a1c99689979b2e8b6032e5628adb2e999ae441ace4f4a34c82ae2e` |
| `docs/internal/evidence/s1_c_runtime_census.md` | `6459f8ea6323049505ef82e1a834e3339f69f0e557bb3b6d62a153240435a267` |

## Fixture manifest

ToolResult fixtures cover successful tool, semantic failure, execution
failure, timeout/stopped, timeout/continuing, accepted cancellation with unknown
worker, committed effect, unknown effect, retryable and non-retryable outcomes,
reconciliation, partial batch, late result, and stale owner.

WorkGraph fixtures/tests cover handoff transfer, delegate, spawn, fan-out,
partial join, cancel request, cancelled late result, detach, monotonic owner
transfer/restore, stale-owner rejection, duplicate completion, budget
exhaustion, missing capability, and restore with unresolved child.

Strict tests cover canonical round-trip, unknown version/field, non-JSON data,
caller ownership isolation, stale generation, duplicate/late completion,
secret/path redaction, snapshot component, and explicit API operation shape.

## Lane A consumer request

Lane A owns session identity, snapshot envelope, head generation, and resolver
references. To qualify the provisional C snapshot component:

1. consume `qitos.work_graph.snapshot_component/v1` inside the reviewed Lane A
   envelope without copying its fields into a second type;
2. store `graph_ref` and unresolved work identities as one C-owned component;
3. advance Lane A head/owner generation before restored workers may commit;
4. exercise missing graph resolver, unsupported component version, stale owner,
   partial batch, and unresolved child failures;
5. bind the exact producer commit and fixture digests above.

Until that producer exists and is reviewed, status remains
`waiting_on_lane_a`; G2 qualification is not claimed.

## Lane B consumer instructions

Lane B continues to consume `ToolResult.to_persistence_dict()`, strict
`from_canonical_dict()`, and the safe projections. It owns ExchangeLog,
RequestView, steering, continuation, and context-transfer data. WorkGraph stores
only `context_transfer_ref`; Lane B must not copy owner generation or invent a
child result. Queued steering may apply once only after C's boundary declares
the model/tool/child state safe.

## Lane D consumer instructions

Lane D should bind the exact producer commit and both fixture digests before
clearing C-owned readiness blockers. It may ingest explicit session/work/item/
attempt/owner generation, operation, join, late-result, and uncertainty facts.
It must not infer graph edges from `run_id`, freeze trajectory v2, or treat an
unbound `qualified=true` flag as evidence.

## Integration/Lane D auxiliary request

Existing `AgentTool.AgentResult`, nested Engine results, aggregate fan-out dicts,
and `HandoffResult` are compatibility surfaces, not additional canonical
outcomes. Their future adapters must produce/reference canonical `ToolResult`
and WorkGraph records. Removal waits for consumer inventory and later behavior
packages.

## Validation evidence

All commands ran from the Lane C worktree on Python 3.12 without masked exits or
rerun-only success:

- combined targeted matrix: `419 passed, 4 skipped in 13.25s`;
- static quality ratchet: passed with `399 findings baselined (377 active, 22
  vendored/generated)`;
- stable flake8 over `qitos/core qitos/engine qitos/models qitos/trace`: exit 0,
  no output;
- stable mypy over the same packages: `Success: no issues found in 78 source
  files`;
- full suite: `1897 passed, 50 skipped in 23.95s`;
- `git diff --check`: passed before commits and is repeated after evidence.

The targeted matrix covered ToolResult, structural validation, retry,
ActionExecutor/ToolRegistry, parallel/recovery/timeout/cancellation, checkpoint
and durability, MCP, handoff/delegate/fan-out, architecture boundaries, public
surface, and no-local-path checks. The four targeted skips and fifty full-suite
skips are existing conditional tests and are not counted as proof of live
model/MCP/HTTP behavior.

## Unsupported claims

- persistent child scheduling or cross-process multi-agent execution;
- hard cancellation of Python threads;
- exactly-once external effects;
- runtime replacement of nested Engine, HandoffTool, DelegateTool, FanOutTool,
  AgentTool, qitos.func, checkpoint durability, MCP, or trace processors;
- Lane A session envelope or Lane B context-transfer qualification;
- trajectory v2/qita changes, live model/MCP/HTTP tests, deployment, or push.

## Known gaps

- Lane A's reviewed identity/snapshot producer is not yet consumed;
- Lane B's reviewed context-transfer component is represented only by an opaque
  reference;
- ActionExecutor does not yet populate every new recovery field mechanically;
- current retry behavior still predates reconciliation enforcement;
- current partial parallel, nested child, durability, MCP, and stream runtimes
  do not yet write these frozen contracts;
- compatibility `AgentResult` and live handoff/delegate/fan-out paths remain.
