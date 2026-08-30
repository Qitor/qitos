# S1 Lane A producer evidence

Status: contract producer complete; repository qualification in progress
Source: `c1efb0f4adde3e673bf181af5b1760c19a451ae2`
Branch: `codex/v4-s1-a-session-contracts`

## Outcome

Lane A produced the sole S1 identity vocabulary, lifecycle vocabulary,
`SessionSnapshot` envelope, resolver-reference contract, head-generation/CAS
rules, pause/persistence receipt semantics, typed failures, strict fixtures, and
the beginner/advanced API ADR. It did not implement Engine pause, process
restore, runtime fork, or atomic store behavior.

## Producer identities

| Artifact | Exact commit | SHA-256 |
|---|---|---|
| identity producer | `63d5cfbea4e0a0941b038833f0152c391d9b63bd` | identity fixture below |
| snapshot producer | `aeb58379d2a266f5f8ba36688530f9ac27da07d1` | fixture manifest below |
| `identity-vocabulary.json` | identity producer | `83dfe69231d6c4786a30a4a6a0682aef222dca26c5273c41cad4618cc2a3b48f` |
| `semantic-fixtures.json` | snapshot producer | `5ad16d94f9bf98d76567c8a09775515285c4cbd27d91c210d9b7d3c0b1d10299` |
| `restore-candidate.json` | snapshot producer | `ab56a922fbe7ebfba85bf5f3a802f37f8aaa5a5c73bc51895aa0dd97a9651c06` |
| `forked-session.json` | snapshot producer | `1cd011001cee67602dffad5827bac80f174e9db6e7220bf0a25af9b0ffa6c7d5` |
| `fixture-manifest.json` | evidence package | `2e950e2320007716a137d3ee4e35b01ccb771c53b30c6e167e7c5de6f023a4b1` |
| `qualification-evidence.json` | evidence package | `af6d8237e263d3090c1b689bbf2948c39f1dd095b7e078d154f514b35aa2e712` |

## B/C/D consumer instructions

All consumers must:

1. consume commit `63d5cfbea4e0a0941b038833f0152c391d9b63bd`
   (or the final Lane A head containing it);
2. import identity types, `IdentityKind`, `IdentityRelation`, lifecycle,
   `ComponentSlot`, resolver, and snapshot types directly from
   `qitos.core.session`;
3. verify `tests/fixtures/session/fixture-manifest.json` against SHA-256
   `2e950e2320007716a137d3ee4e35b01ccb771c53b30c6e167e7c5de6f023a4b1`;
4. use `SessionSnapshot.from_json/from_dict` for strict reading;
5. preserve the component slot envelope while owning only the component payload
   schema assigned to that lane;
6. run:

   ```bash
   /opt/anaconda3/bin/python3.12 -m pytest -q \
     tests/core/test_session_identity.py \
     tests/core/test_session_contract.py
   ```

Lane B owns `exchange_context`, `partial_parallel_batch`, `queued_steering`, and
`provider_continuation` payload schemas. Lane C owns `tool_effects` and
`work_graph`. Lane D is a reader of identity, lineage, receipt, and completeness
facts. None may copy the identity enum, infer lineage from string names, or add
a parallel snapshot/session truth.

The B-like and C-like independent consumer simulations in
`tests/core/test_session_contract.py` prove slot isolation only. They are not
real cross-lane qualification; the integration owner must consume exact B/C/D
producer commits before G2.

## Contract evidence

- identity types are distinct, framework-generated, JSON-safe, strict, and
  relationship-validated;
- `pause_requested`, `pausing`, and `paused` are distinct lifecycle states;
- safe pause requires recorded partial slots, quiesced framework workers, and no
  unresolved effect;
- immutable snapshots deep-own nested values, reject non-JSON/non-finite/live
  objects, reject obvious host paths/credentials, and verify deterministic
  SHA-256 integrity;
- required components, duplicate slots/references, unknown fields, wrong types,
  envelope schema, and component schema fail closed;
- resolver references cover model, tool registry, environment, artifact store,
  secret, checkpoint store, and provider continuation without persisting the
  live resource;
- head advancement distinguishes stale generation from superseded ownership;
- accepted, persisted, rejected, failed, and conflict receipts are not
  interchangeable; only persisted may report paused and advance generation;
- all thirteen required error codes have stable safe serialization.

## Compatibility and removal evidence

The exact-source census and retirement ledger are in
`docs/internal/plans/s1_a_session_contracts.md`. The public ADR is
`docs/architecture/session-runtime-contract.md`. No compatibility runtime was
changed in 12A. Later packages must isolate historical checkpoint/RunState
readers and use one current writer.

## Unsupported claims

Lane A does **not** claim:

- Engine pause/resume behavior is implemented;
- a new process can yet reconstruct and run a session;
- checkpoint stores perform atomic session-head CAS;
- durability queue acceptance is persistence;
- runtime fork or qita fork convergence is complete;
- ToolResult effects execute exactly once;
- B/C payload schemas are cross-lane qualified;
- trajectory schema is frozen;
- provider defaults, root exports, CLI, examples, or shared release documents
  changed.

## Known gaps and next gates

- Task 12B: add idempotent atomic session-head persistence to current stores;
- Task 12C: integrate safe pause and same-process resume;
- Task 12D: prove clean-process restore with resolvers;
- Task 12E: runtime fork, qita/CLI adapters, and compatibility rollout;
- Lane B: publish real ExchangeLog/context/steering/continuation components;
- Lane C: publish effect/quiescence/work-graph components;
- Lane D: consume exact producer evidence without freezing trajectory schema.

## Integration-owner release text suggestion

For the shared README/changelog/progress lease: “Defined the canonical durable
session identity, lifecycle, immutable snapshot envelope, resolver-reference,
generation/CAS, receipt, and compatibility contracts with strict portable
fixtures. Runtime pause, fresh-process restore, and fork behavior remain planned
for later Task 12 packages.”

## Validation evidence

- Session contracts + checkpoint + Engine targeted matrix:
  `285 passed in 3.31s`.
- Architecture boundaries + root public surface + no-local-path policy:
  `10 passed in 1.15s`.
- Full-package static ratchet: passed with 399 baselined findings
  (377 active, 22 vendored/generated), no baseline growth.
- Stable flake8 over `qitos/core qitos/engine qitos/models qitos/trace`: passed
  with no findings.
- Stable mypy over the same surfaces: success on 78 source files.
- Full Python 3.12 suite: `1920 passed, 50 skipped in 24.88s`.
- `git diff --check`: passed.
- No validation used a rerun, masked exit, alternate interpreter, live model,
  push, deployment, or baseline update.
