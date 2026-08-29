# Lane B conversation and context plan

Status: B1-R accepted; canonical C-P3 consumer requalification green
Work package: B1-R Phase 1 / Task 02A contract integrity
Integration baseline: `8441bef2f2024fd6c2ec01784708512222382471`
B1 source HEAD: `69a961f6f50656dff308db7a2f3e400439ef20d0`
Branch: `codex/v4-lane-b-exchange-integrity`

## Scope and sequencing

This package establishes only the persistent `ExchangeLog` layer and its
`HistoryMessage` compatibility boundary. It does not switch Engine history,
provider payload builders, request views, checkpoints, presets, or tracing.

1. Isolate every mutable value at append/load boundaries and return isolated
   snapshots from log/query APIs.
2. Persist each terminal result immediately, recover completed slots after a
   process-like reload, and preserve actual completion order as durable fact.
3. Derive declaration-ordered result views without rewriting persisted items;
   release queued steering exactly once only when the batch closes.
4. Replace the overbroad safe/public name with a versioned
   continuation-redacted diagnostic view and document that it is not a privacy
   filter.
5. Migrate the semantic fixture envelope to v3 with a strict ExchangeLog v2
   reader and typed rejection of malformed or unknown data and prior schemas;
   describe its execution/persistence tests only as consumer simulations.
6. Run the contract, architecture/public-surface, full-suite, static, and diff
   checks. This branch does not include or claim the Lane A ratchet.
7. Align on the exact accepted C contract before D receipt qualification.

## API decision record B1-ADR-001

Decision: introduce one module-level contract at `qitos.core.conversation`
without exporting it from `qitos.core.__init__` or the root package.

The persistent model has four explicit item types:

- user content;
- assistant output containing an ordered sequence of content blocks, reasoning
  references, and tool calls;
- tool results correlated by provider-scoped call identity;
- human steering, queued while a batch is open and committed after closure.

Tool calls retain raw arguments, optional parsed arguments, parse status, batch
identity, and provider scope. Opaque native continuation attachments are kept
as typed provider-owned payloads and are never projected into assistant text.
The lossless persistence form retains those payloads. A separately versioned
continuation-redacted diagnostic projection hides only opaque continuation
payloads; metadata, arguments, results, and provenance remain unchanged, so it
is explicitly neither a privacy-safe nor a public export.

`ExchangeLog` accepts out-of-order execution completion through
`ToolBatchBuilder`. Each terminal result is appended immediately in real
completion order and is therefore present in a partial-batch persistence
snapshot. Reload reconstructs the open batch and completed slots; only missing
slots may run or receive synthetic closure. Declaration-ordered results are an
explicit derived query for request/provider-facing consumers and never rewrite
durable facts. Every declared slot closes exactly once. An open batch rejects
the next normal model transaction, while steering is queued and released
exactly once after closure, including after recovery.

External immutability uses ownership-boundary defensive copies rather than a
new recursive immutable framework. Append, constructor/load, queued steering,
result recording, query snapshots, and serialization all isolate nested lists,
dictionaries, content metadata, parsed arguments, provenance details, and
opaque attachment values. The tradeoff is O(payload size) copying on writes and
reads in exchange for familiar dataclass/list/dict ergonomics and an explicit,
small contract surface. If profiling later shows this is material, a dedicated
persistent data structure can replace the boundary implementation without
changing the ownership semantics.

`ToolResult` is the sole outcome contract. `ToolResultItem` contains only item,
exchange, call, batch, synthetic-closure, and closure-reason facts plus the
canonical result; it has no second content/status/error/provenance envelope.
ExchangeLog persistence, model, and trace-safe projections call
`ToolResult.to_persistence_dict()`, `to_model_dict()`, and
`to_trace_safe_dict()` directly, while strict reads call
`ToolResult.from_canonical_dict()`. Permissive handling remains confined to the
named `HistoryMessage` legacy adapter.

`HistoryMessage` remains unchanged. Adapters preserve compatible fields,
synthesize stable exchange/item/batch identities and explicit parse status,
and raise `UnsafeHistoryConversionError` when the legacy shape cannot safely
represent ordered reasoning or assistant interleaving. Provider-specific
placement is never written into durable history.

### Compatibility matrix

| Direction | Preserved | Synthesized | Potential loss | Typed rejection |
|---|---|---|---|---|
| `HistoryMessage -> ExchangeLog` | role, step metadata, content blocks, tool call/result IDs, names, raw args, metadata, native items as opaque attachment | log/exchange/item/batch IDs, provider scope when absent, parse status | legacy assistant interleaving was never recorded, so content is placed before declared calls and marked in metadata | unsupported role, orphan/duplicate result, duplicate call ID, incomplete batch, unsafe native item |
| `ExchangeLog -> HistoryMessage` | user/tool content, compatible assistant content and calls, IDs, metadata, opaque native items | steering compatibility marker and step IDs when absent | reasoning references and content/call interleaving have no legacy representation | strict adapter rejects any such loss; callers must remain on `ExchangeLog` |

Adapter removal condition: remove the compatibility path only after Engine and
checkpoint migration, all supported provider codecs consume request views, v1
history/checkpoint fixtures resume through the migration reader, and one full
deprecation window has elapsed.

## Invariants and fixture handoff

Schema: `qitos.exchange_log.v2`
Fixture envelope: `qitos.conversation.fixture.v3`

The fixture manifest covers multimodal input, single and parallel calls,
out-of-order completion, both malformed and semantically invalid arguments,
duplicate IDs, incomplete/interrupted batches, queued steering, opaque
continuation, unsupported reasoning replay, genuine `Error:` assistant text,
and serialization round-trip. Every case declares its invariant, expected
typed error, consumer simulation, and losslessness. The deterministic recovery
test serializes a one-of-N completion, reloads it, executes only the missing
slot, and verifies completion-order persistence plus declaration-order query.

Execution-side qualification covers declared calls, partial persistence,
recovery, and declaration-ordered query. Persistence qualification uses the
exact committed Lane C fixture, strict v2 parsing, and canonical C serializers.
Producer-owned qualification evidence is published beside the v3 fixture for
Lane D to bind to the exact B fixing commit.

## G1 B/C convergence evidence

- [x] B-C1: remove the temporary result enum and duplicated result envelope;
  conversation owns only correlation, ordering, closure, and steering facts.
- [x] B-V1: strict v2 parsing rejects unknown fields at every declared layer,
  wrong shapes/types, non-JSON values, non-finite numbers, prior envelopes, and
  malformed canonical results with `ConversationValidationError`.
- [x] Round-trip the exact Lane C `contract_hardening.json` canonical source.
- [x] Verify persistence/model/trace views are byte-for-byte the corresponding
  public ToolResult serializer outputs.
- [x] Publish `tests/fixtures/conversation/v3/qualification-evidence.json`.

Integrated targeted evidence: 29 conversation tests and 71 combined
conversation/ToolResult/projection tests passed; stable mypy succeeded on 77
source files and stable flake8 was clean. Full combined G1 qualification remains
open until Lane D is integrated.

## G1-R3 canonical consumer requalification

ExchangeLog required no runtime change. Its `to_model_dict()` and
`to_trace_safe_dict()` continue to call C's public serializers directly, so the
collision-safe key encoding, recursive value behavior, omitted budget, and loss
facts are inherited byte-for-byte. The new consumer probe also confirms that
persistence retains the original sensitive keys and strict round-trip behavior.
The 108-test combined ToolResult/structural/projection/conversation command
passed, including typed malformed reads, partial completion, completion order,
recovery, and one-time steering. The B producer fixture/evidence bytes did not
change, so D correctly retains B's `2e46fc8...` receipt.

## File leases

Lease owner: Lane B / B1
File(s): `CHANGELOG.md`, `README.md`, `README.zh.md`,
`docs/v4/02-conversation-kernel.md`
Semantic purpose: document the new module-level ExchangeLog contract, evidence,
compatibility boundary, and non-integration status.
Expected start/end package: B1/B1-R Phase 1 documentation sync only.
Other lanes blocked or adapter supplied: no code consumer is blocked; Lane C/D
receive versioned fixtures. No root export or shared runtime file is modified.

No lease is requested for `qitos/core/__init__.py`, root exports,
`qitos/engine/*`, `qitos/models/*`, `qitos/checkpoint/*`, or trace/qita files.

## B1-R Phase 1 completion evidence

- `pytest -q tests/core/test_conversation.py`: 26 passed;
- `pytest -q tests/test_architecture_boundaries.py`: 4 passed;
- `pytest -q tests/test_public_surface.py`: 4 passed;
- `pytest -q`: 1,720 passed, 50 skipped;
- `flake8 qitos/core qitos/engine qitos/models qitos/trace`: clean;
- `mypy qitos/core qitos/engine qitos/models qitos/trace`: success, 77 source
  files (one existing unchecked-body note in `qitos/core/state.py`);
- `git diff --check`: clean;
- architecture allowlist delta: zero;
- public/root export delta: zero;
- forbidden Engine/provider/RequestView/checkpoint/trace/qita/runtime delta: zero;
- `docs/progress.md` delta: zero;
- Lane A ratchet: not present and not claimed;
- C1-R alignment: historical Phase 1 gate, now closed by the G1 section above.

## Original B1 evidence (historical)

- `pytest -q tests/core/test_conversation.py`: 20 passed;
- `pytest -q tests/test_architecture_boundaries.py`: 4 passed;
- `pytest -q tests/test_public_surface.py`: 4 passed;
- `pytest -q`: 1,714 passed, 50 skipped;
- `flake8 qitos/core qitos/engine qitos/models qitos/trace`: clean;
- `mypy qitos/core qitos/engine qitos/models qitos/trace`: success, 77 source
  files (one existing unchecked-body note in `qitos/core/state.py`);
- `git diff --check`: clean;
- architecture allowlist delta: zero;
- public-surface delta: zero;
- Engine/provider/checkpoint/trace runtime delta: zero;
- Lane A ratchet/rebase: pending. At verification time the integration branch
  and all four lane branches still pointed to the W1 baseline; Lane A's ratchet
  files were uncommitted in its isolated worktree. This branch must rebase onto
  the future integration commit containing A1 and run the published ratchet
  before merge-readiness can be claimed.
