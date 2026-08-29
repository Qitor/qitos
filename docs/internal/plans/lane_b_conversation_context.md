# Lane B conversation and context plan

Status: B1 implementation complete; Lane A/A1 integration rebase pending
Work package: B1 / Task 02A
Baseline: `fb75cd5902fedf50d5e67dd617e62cd981c3128f`
Branch: `codex/v4-lane-b-exchange-contract`

## Scope and sequencing

This package establishes only the persistent `ExchangeLog` layer and its
`HistoryMessage` compatibility boundary. It does not switch Engine history,
provider payload builders, request views, checkpoints, presets, or tracing.

1. Freeze the provider-neutral exchange vocabulary and validation errors.
2. Add versioned semantic fixtures before runtime integration.
3. Implement append-only exchange items, ordered tool-batch closure, queued
   steering, serialization, and compatibility adapters.
4. Prove the contract through two independent fixture consumers: a Lane C-like
   batch executor and a Lane D-like persistence/trajectory reader.
5. Run the B1 contract suite, architecture/public-surface checks, the full test
   suite, stable static checks, and `git diff --check`.
6. Rebase and rerun the Lane A ratchet only after A1 is present in integration;
   until then this branch is implementation-complete but not merge-ready.

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
Safe/public summaries redact their payload; the versioned persistence form is
the only lossless serialization form.

`ExchangeLog` accepts out-of-order execution completion through
`ToolBatchBuilder`, but commits tool-result items in assistant declaration
order. Every declared slot closes exactly once. Permission blocks, timeouts,
cancellation, and missing workers are terminal results; synthetic closure
requires explicit provenance. An open batch rejects the next normal model
transaction, while steering is queued and released exactly once after closure.

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

Schema: `qitos.exchange_log.v1`
Fixture envelope: `qitos.conversation.fixture.v1`

The fixture manifest covers multimodal input, single and parallel calls,
out-of-order completion, both malformed and semantically invalid arguments,
duplicate IDs, incomplete/interrupted batches, queued steering, opaque
continuation, unsupported reasoning replay, genuine `Error:` assistant text,
and serialization round-trip. Every case declares its invariant, expected
typed error, Lane C/D consumer, and losslessness.

Lane C handoff: declared calls plus ordered closure/result projection.
Lane D handoff: versioned persistence fixture plus redacted safe projection.

## File leases

Lease owner: Lane B / B1
File(s): `CHANGELOG.md`, `README.md`, `README.zh.md`,
`docs/v4/02-conversation-kernel.md`
Semantic purpose: document the new module-level ExchangeLog contract, evidence,
compatibility boundary, and non-integration status.
Expected start/end package: B1 documentation sync only.
Other lanes blocked or adapter supplied: no code consumer is blocked; Lane C/D
receive versioned fixtures. No root export or shared runtime file is modified.

No lease is requested for `qitos/core/__init__.py`, root exports,
`qitos/engine/*`, `qitos/models/*`, `qitos/checkpoint/*`, or trace/qita files.

## Completion evidence

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
