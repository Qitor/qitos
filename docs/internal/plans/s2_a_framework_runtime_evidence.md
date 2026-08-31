# S2 Lane A framework runtime evidence

Status: qualified
Baseline: `446a347d1ac73636476ca2515a01da601b567c68`
Read-only ledger successor: `47cd4dc5e1ed1b2b0d244bfc90fac031ec55be32`
Producer commit: `bc725e8b77576a7a0b5c165a5066c83c4d9965c8`
Evidence commit: recorded in the final handoff because a commit cannot contain
its own content hash
Branch: `codex/v4-s2-a-framework-runtime`
Worktree: `/Users/morinop/Desktop/WhitzardOS-s2-a`

## Outcome

Lane A now provides one explicit runtime composition boundary, a small durable
Session facade over the canonical Engine loop, and an atomic checkpoint-backed
Session head protocol. Memory, SQLite, and a test-owned third-party
implementation pass the same public conformance semantics. A bounded offline
subprocess test proves restoration through a new Engine, new agent object, new
run identity, and a reopened SQLite connection without repeating the committed
effect.

This is Lane A completion evidence, not a claim that the combined S2 vertical
slice or S2 wave is closed.

## Public beginner API

```python
session = Engine(agent).session(task)
result = session.run()

pause_request = session.pause()  # cooperative while running
session = Engine.restore(pause_request.session_id, resolvers=resolvers)
result = session.run(steering="new constraint")
```

`Session.run()` delegates to `Engine.run()`. The facade has no execution loop,
state copy, permanent worker, or global registry. A lifecycle policy can also
request pause deterministically at an Engine safe boundary.

The Session type is exported from `qitos.engine`; it is intentionally absent
from the root `qitos` exports. The persisted head/CAS/receipt types are absent
from the beginner path.

## Advanced composition API

Import path: `qitos.engine.runtime`.

| API | Contract |
| --- | --- |
| `RuntimeComposition` | Process-local composition of checkpoint store, resolver registry, durability, ActionExecutor policy, context/model binding, lifecycle policy, snapshot components, and event sink. |
| `RuntimeCompositionConfig` | Strict JSON-safe projection containing only capability names, logical resolver references, component schemas, and policy metadata. |
| `RuntimeSnapshotComponent` | Owner supplies one `SnapshotComponentCodec`, `capture(context)`, and `restore(value, context)`. |
| `LifecyclePolicy` | `supports_pause`, `should_pause(context)`, and `pause_safety(context)`. |
| `ContextModelRuntime` | B-owned `capability_id` plus `bind(engine)` seam; the canonical model loop remains in Engine. |
| `RuntimeEventSink` | `emit(event)` subscription for Engine runtime events and explicit `SessionLifecycleEvent` head facts. |

`Engine.__init__` grew by exactly one parameter, `runtime`; the exact-base
parameter count was 33 including `self`, and the producer count is 34. Existing
constructor inputs remain compatibility adapters into the same composition.

## Session runtime protocol

Import path: `qitos.engine.session_runtime`.

- create: `Engine.session(task, session_id=None)`;
- run: `Session.run(steering=None)`;
- inspect: `Session.inspect()`;
- request pause: `Session.pause()` / `request_pause()`;
- restore: `Engine.restore(session_id, resolvers=..., runtime=...)`;
- typed lifecycle: `Session.lifecycle`;
- capability discovery: `Session.capabilities()`;
- current head: `Session.current_head`;
- explicit safe commit: `Session.commit_snapshot()`.

The lifecycle commit event carries distinct session, run, snapshot, and
checkpoint IDs plus generation, lifecycle, durability, and timestamp. Restore
validates envelope/component integrity and resolves every declared live
dependency before transferring ownership with CAS. The restored attempt gets a
new `RunIdentity`.

## Persistence protocol

Import path: `qitos.checkpoint` (definitions in
`qitos.checkpoint.session`). `CheckpointStore` exposes optional-by-default
Session methods so historical third-party stores remain constructible and
report typed unsupported capability:

```text
session_capabilities()
commit_session_snapshot(SessionSnapshotCommit) -> SessionCommitReceipt
get_session_head(session_id) -> SessionHeadRecord | None
get_session_snapshot(snapshot_id) -> SessionSnapshotRecord | None
list_session_lineage(session_id, limit=None) -> immutable records
```

The commit CAS includes expected generation, expected checkpoint, and expected
owner. Restore may explicitly replace the owner only after validating all three
facts. Successful receipts always state `durable=True`; conflicts and failures
are typed and never fabricate `paused`.

SQLite persists snapshot bytes once in canonical `checkpoints.state_data`.
`session_heads` is the small mutable pointer, and `session_snapshot_index` maps
the distinct snapshot identity to its checkpoint. One `BEGIN IMMEDIATE`
transaction inserts the immutable checkpoint/index and advances the head.
Memory performs the same operation under one lock. Every public return is deep
isolated.

## Reference and third-party implementations

- `InMemoryCheckpointStore`: atomic process-local reference implementation;
- `SqliteCheckpointStore`: durable cross-process reference implementation;
- `ThirdPartyCheckpointStore` in `tests/test_s2_runtime_conformance.py`: public
  protocol implementation with no SQLite schema or reference-store private
  attribute access.

The conformance suite compares commit, receipt, head, snapshot, lineage, CAS,
and mutation-isolation semantics across these implementations.

## Compatibility

- `Engine.init_session()` / `step()` remain unchanged.
- `Engine.resume_from_checkpoint()` / `resume()` remain available for the old
  run-checkpoint flow.
- `CheckpointManager` remains deprecated and unextended.
- `RunState` remains importable and serializable, but Session runtime never
  writes it as a durable truth.
- `session_snapshot_from_checkpoint()` is the bounded compatibility reader. It
  accepts a canonical Session envelope behind an old checkpoint address and
  returns typed `incompatible_checkpoint` for state-only checkpoints.
- While a Session owns Engine execution, the old state-only checkpoint writer
  is disabled, preventing two persistence truths.

## Fixture binding

Manifest:
`tests/fixtures/s2/lane_a/fixture-manifest.json`

| Fixture | SHA-256 | Producer |
| --- | --- | --- |
| `checkpoint-session-commit.json` | `e28bcc9c95fb5c300a24b6c8201edb76530ac192396595df3dcd750139fe45e4` | `bc725e8b77576a7a0b5c165a5066c83c4d9965c8` |
| `interface-budget.json` | `7e25df1c0198e25db4ab70ed280351b64fc66982462f8a5e44863099cf873a14` | same |
| `runtime-composition-config.json` | `7eef33bbd17b5087b76590d9d5797e902fbb8b246e89abc80458e5e0ebc1cfad` | same |
| `unsupported-capability-matrix.json` | `c43204cb4665353d821e6aa2eceb2a2b0526d7c5f3aee5019647dbfba95f55ef` | same |

The conformance suite recalculates every digest and decodes the fixtures only
through public protocol types.

## B/C/D handoffs

### Lane B model/context component

Provide one `RuntimeSnapshotComponent` with an owner-specific codec. Capture
the exact ExchangeLog/request head, codec report, selected context,
continuation reference, and queued-steering record. Restore it through the
same component before `Session.run()`. Live providers and credentials remain
resolver references. If Lane B supplies a context/model binding, implement
`ContextModelRuntime.bind(engine)`; do not add a second model loop.

Lane A currently applies `run(steering=...)` once in the resumed Engine process,
but persistence across another crash before B's next safe snapshot remains a B
producer claim, not an A claim.

### Lane C executor/quiescence component

Provide one `RuntimeSnapshotComponent` for declared and completed tool slots,
completion order, effect/idempotency receipts, open workers, cancellation and
timeout facts, and `outcome_unknown`. Supply a `LifecyclePolicy.pause_safety()`
result derived from those facts. A commits `paused` only after
`PauseSafety.require_migratable()` succeeds and never interprets C's payload.

The A subprocess fixture proves a completed effect is not repeated from a
fully recorded step boundary. Partial parallel slot closure and worker
quiescence remain C claims.

### Lane D lifecycle subscription

Pass a `RuntimeEventSink`. It receives canonical `RuntimeEvent` instances plus
`SessionLifecycleEvent` with exact session/run/snapshot/checkpoint/generation
facts. D must bind lineage from these fields and must not derive it from trace
directory names. The frozen v1 trace writer and qita are not modified here.

## Unsupported capability matrix

The canonical machine-readable matrix is
`tests/fixtures/s2/lane_a/unsupported-capability-matrix.json`.

- cooperative pause when the lifecycle policy declares no support;
- durable Session operation on a store without atomic Session commit;
- Session durability with async/exit policy;
- restoration of a state-only legacy checkpoint;
- run/pause/restore on invalid or terminal lifecycle;
- Session fork and durable multi-agent scheduling;
- Python-thread hard cancellation.

## Validation

All required gates passed in the exact worktree:

| Command | Result |
| --- | --- |
| `pytest -q tests/checkpoint` | `9 passed` |
| `pytest -q tests/core/test_session_contract.py tests/core/test_session_identity.py tests/engine/test_run_state.py tests/engine/test_interrupt.py` | `69 passed` |
| `pytest -q tests/engine/test_session_runtime.py` | `6 passed` |
| `pytest -q tests/e2e/test_session_core_process_restore.py` | `1 passed` |
| `pytest -q tests/test_s2_runtime_conformance.py` | `10 passed` after final manifest/composition additions |
| `pytest -q tests/test_architecture_boundaries.py tests/test_public_surface.py tests/test_no_local_paths.py` | `10 passed` |
| `/opt/anaconda3/bin/python scripts/static_quality.py check` | passed; pinned Python 3.12.7 toolchain, 394 findings baselined (372 active, 22 vendored/generated) |
| `flake8 qitos/core qitos/engine qitos/models qitos/trace` | passed, zero output |
| `mypy qitos/core qitos/engine qitos/models qitos/trace` | `Success: no issues found in 86 source files` |
| `pytest -q` | `2128 passed, 50 skipped` |

The default shell `python` is 3.13.3 and correctly failed the pinned-toolchain
preflight. The required static ratchet was therefore run with the repository's
available pinned Python 3.12.7 interpreter. The ratchet update removed five
pre-existing unused-import findings from the A-owned checkpoint files, added
zero findings, and reduced the baseline to 394 before the passing check.

`git diff --check` and the final clean-status audit are performed immediately
before the evidence commit and reported in the final handoff.

## Known gaps and unsupported claims

- no fork runtime or persistent multi-agent scheduler (S3/Task 12E);
- no Lane C partial-parallel/quiescence/effect reconciliation producer;
- no Lane B persisted ExchangeLog/provider continuation/queued-steering
  producer;
- no default Trajectory writer or qita migration;
- no exactly-once claim for external effects lacking backend receipts;
- no migratable pause for a live non-quiesced worker;
- no async/exit durability claim for Session head commits;
- no public deprecation/removal of `RunState`, checkpoint v1, or old resume
  entry points;
- no claim that complete S2 is closed.

Shared README, CHANGELOG, progress, and `docs/v4` status updates remain leased
to the integration owner. Integration must add the user-facing documentation
entries after merging the four S2 lanes.
