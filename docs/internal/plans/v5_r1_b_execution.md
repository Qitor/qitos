# V5 R1 Lane B execution record

## Source and ownership

- Sole source baseline: `4dfb570fb7eef504c1e6d247c21a1984251b80e4`.
- Branch: `codex/v5-r1-b-memory-context`.
- Worktree: `WhitzardOS-v5-r1-b`, sibling of the primary checkout.
- Fetch of `origin master` succeeded. Baseline exists and is an ancestor of
  `origin/master`; initial HEAD and merge-base equal the baseline, with a clean
  initial worktree. The primary checkout and its uncommitted V5 documents were
  preserved; no pull, stash, reset, cherry-pick, push or worktree deletion.
- Production API source: `1710b2723238648e3d7394b262f06e97290cd093`.

## Scope adjustment and evidence

The initial task requested evidence before changing a materially conflicting
interface. Inspection found that RequestView selected/omitted exchanges before
`_model_runtime._execute_request_view` invoked the compactor. RequestView had no
policy argument, so changing only the concrete compactor could not enforce
explicit-policy-only omission. The user instructed continued execution after
reviewing the minimal proposal.

The authorized model-request wiring change passes the existing policy into
RequestView and removes the post-selection receipt callback/rebuild. The real
consumer also exposed removal of `_step_id` before ExchangeLog conversion,
merging all history into one current exchange. Preserve that identity until
canonical conversion; the existing codec continues to construct wire messages.
No provider/codec, config loader/builder/extensions, Session/checkpoint/WorkGraph,
artifact store, permission, MCP, benchmark, CI or packaging metadata changed.

Required artifacts are now probed in the allowed `_context_runtime.py` before
request construction. The S2 vertical fixture previously used a fictitious
required artifact digest and no resolver. Its test fixture now writes a real
artifact and rebinds its resolver in the restored process; all twenty recovery
rounds and their existing assertions are retained. No runtime ownership or
checkpoint implementation was changed to accommodate the fixture.

## Delivered behavior

- `qitos.kit.memory.adapter.MemorySourceAdapter(memory, *, namespace, query=None,
  required=False, priority=0)` implements MemorySource. It borrows the memory,
  snapshots query/content, uses user-level data placement, and never closes,
  resets or deletes the underlying resource. Namespace is a logical factory
  binding, not authorization to open arbitrary directories.
- `MemoryRecord.record_id` gives equal independent records distinct identities.
  Memdir persists identity and reads disk afresh, without merging stale cache
  copies. Content changes alter contribution revision/digest; edits/deletions
  affect both retrieve and summarize. Host paths are not inserted into recalled
  content or contribution metadata/IDs. Historical text files use a hashed
  namespace-relative identity fallback; moving such a legacy file changes that
  fallback identity.
- Memdir defaults to restoring an existing root, with typed
  `MemoryResourceError` on absence. `create=True` explicitly initializes a new
  resource, including through `memdir_memory(...)`. Cache reset/eviction does
  not delete persistent records. Text is the durable reference; arbitrary
  Python/JSON content or metadata is not a lossless serialization promise.
- MarkdownFileMemory uses the same adapter for its current instance. Fresh
  instances do not reload existing logs; no eval or guessed metadata recovery.
- `qitos.kit.context.compaction.ClosedExchangeWindowCompactor()` authorizes
  deterministic oldest-first omission of eligible closed exchanges without a
  summary. RequestView remains the sole selector; ContextBudget remains the
  sole recent-window/budget owner. Default omission is rejected without an
  explicit policy; historical receipts alone are not authorization.
- Tool call/results stay atomic and completion order is unchanged. Open batches,
  unanswered input (even with a reused exchange ID and zero recent window),
  pending steering and required context/artifacts stay protected. Opaque
  continuation state conservatively protects complete history because no
  smaller dependency closure is declared. Oversized protected input fails typed.
- Compaction receipts identify omitted exchanges, declared loss and the digest
  of the selected exchange projection. ExchangeLog persistence bytes remain
  unchanged. Recall runs on every request, so an unchanged revision reappears
  after omission/restore instead of being permanently suppressed.

## User configuration and installed consumer

YAML uses existing fields:

```yaml
memory:
  sources: [project_memory]
compaction:
  provider: closed_window
```

The application binds `project_memory` to a factory returning the adapter over
its restored Memdir resource, and `closed_window` to the concrete compactor in
`build_agent_composition(..., extensions={...})`. No independent registry,
framework façade, root/aggregate export or Engine constructor option was added.
The existing Python `dataclasses.replace` config path supplies the budget policy
and explicit `context.allow_codec_loss=True`; the YAML loader does not accept
those two context service keys. Neither adapter enables blanket loss internally.

`examples/v5/r1_b_memory_context` contains complete YAML, consumer and commands.
A wheel-installed independent Python 3.12.7 venv runs copied files outside the
repository with isolated `python -I` processes. Seed writes remembered-value=17
and exits. Run reconstructs composition and verifies:

- ten actual encoded requests in the main run, each with exactly one memory
  contribution; three actual budget compactions and the protected-two window;
- selected chunk visibility matches actual provider messages; internal step keys
  are absent from wire messages; final request identity survives serialization;
- a second configured composition makes an additional request against another
  bound namespace and cannot see remembered-value=17;
- memory remains available after borrowed composition/adapter lifecycle ends.

This is deterministic-provider mechanism evidence, not live model capability.
The example's 100,000-character budget accommodates ConfiguredAgent's repeated
recent-observation input; it is not a default or an automatic budget increase.

## Validation ledger

Implementation is frozen at the production source above. Final qualification
completed on 2026-09-05 with the documented API/reference changes present.

Final results:

- Pinned Python 3.12.7, flake8 7.0.0, mccabe 0.7.0, mypy 1.19.1,
  pycodestyle 2.11.1, pyflakes 3.2.0.
- `QUALITY_BASELINE_REF=4dfb570fb7eef504c1e6d247c21a1984251b80e4 python
  scripts/static_quality.py check`: 356 baselined findings (334 active,
  22 vendored/generated), no new findings and no allowance change.
- Stable-surface flake8 passed; stable-surface mypy passed for 94 source files.
- Engine/core regression sweep: 761 passed before the final unanswered-input
  guard; the final guard and associated selection suites: 83 passed.
- Required memory/history/S4/contributor/new regressions and installed consumer,
  together with architecture boundaries, public surface and no-local-path checks:
  73 passed after the production freeze.
- Twenty clean-process S2 vertical recovery rounds passed with real required
  artifact rebinding. Installed two-process configured consumer passed.
- `python -m pytest -q -rs`: **3474 passed, 51 skipped**, 295.32 seconds.
  Fifty existing live-provider E2E tests require endpoint/API-key credentials;
  one existing Docker documentation qualification is explicitly opt-in. No
  additional skip or rerun-only qualification was introduced.
- Serial `python -m build` followed by `python -m twine check dist/*` passed
  for both the wheel and source distribution.
- `python scripts/validate_docs.py`, API and tutorial synchronization checks
  (`--check`), and `git diff --check` passed after the final documentation edits.
- MDX 3.1.1: 166 public pages, zero failures. Mint 4.2.873 build validation and
  broken-link checks passed. Existing pinned tooling was reused without global
  upgrades after a separate task-local npm dependency download was cancelled.
- Playwright inspection: EN desktop and mobile guide, zh mobile guide, EN desktop
  and zh mobile context reference, plus the adapter parameter table. Viewports
  1440x1000 and 390x844; no document-level horizontal overflow, no browser errors.
  The sole console warning was the local preview Socket.io connection.

Earlier diagnostic runs are not final qualification: the first full run exposed
old implicit-omission fixtures and unsynchronized tutorials; a later run exposed
the fictitious required artifact and one concurrent-build filesystem collision.
An intermediate full run was interrupted when the final guard was added. Final
pytest and packaging run serially. A minimal temporary dependency environment
also produced unrelated third-party annotation differences; validation uses the
verified baselined environment, without expanding exceptions or changing skips.

## Documentation and API delta

EN/zh memory guide, context reference, complete runnable notes tutorial, README
and changelog describe verified behavior and the explicit-create/explicit-loss
migration. Context API bindings include the two concrete implementations and
supporting memory/request types. A per-group source reference keeps this lane's
API links pinned without changing other groups' source identities or reordering
the shared manifest. Browser QA found the common generator rendered union pipes
as literal entity text; its table escaping is corrected, with mechanically
synchronized EN/zh parameter tables. API type semantics are unchanged.

No static baseline, architecture allowlist, aggregate export, dependency metadata
or global V4/V5 progress document changed.

## Commits and remaining boundaries

- `20bfd50`: memory adapters, durable identity, explicit compaction and consumer.
- `a2f09fc`: restored artifact resolver and actual other-namespace request proof.
- `1710b27`: protect unanswered input when an exchange identity is reused.
- Final bilingual documentation/evidence commit contains this completed ledger.
  Its identity is reported in the delivery; production source remains pinned above.

Remaining by contract: Markdown durable reader, model-generated summaries,
complete legacy-history retirement, cross-Agent memory policy and original-Agent
migration experiments. Legacy CompactHistory remains supported. No real model,
publication, deployment or push was performed.
