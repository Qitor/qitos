# S3 Lane B — context, continuation, and authority transfer

Status: in progress
Updated: 2026-08-31
Owner: S3 Lane B
Dispatch source: `851f7902f15da670e72f4c04d7453cf37201aee7`

## Outcome

Publish one strict, provider-neutral child-input transfer contract that Lane C
can persist before dispatch and Lane D can inspect without receiving secrets,
host identities, or provider payloads. This lane does not schedule work, mutate
Session heads, or define product roles.

## Exact-source census

| Concern | Exact source at dispatch | Decision |
|---|---|---|
| canonical conversation | `qitos/core/conversation.py` — `ExchangeLog` | select immutable exchange groups; never rewrite the source |
| request/context selection | `qitos/core/request_view.py` — `RequestView`, `SelectionReport`, `CompactionReceipt` | preserve ordered selection facts and compaction loss |
| continuation | `qitos/core/request_view.py` — `ContinuationRef`; `qitos/core/session.py` — `ContinuationIdentity` | validate provider/model/API/expiry and codec support; never persist payload/token |
| artifacts | `qitos/core/artifact.py` — `ArtifactRef` | transfer only canonical refs; enforce sensitivity authorization and required resolution |
| authority | `qitos/core/work_graph.py` — `BudgetAllocation`, `CapabilityAllocation` | reuse exact allocation types; validate intersection and reject escalation |
| identities/head | `qitos/core/session.py` — typed identities, `SessionHead`, `SessionSnapshot` | reference source session/run/work/snapshot/head digest without copying a Session truth |
| provider capability | `qitos/models/codec.py` — `ProviderCapabilities` | core records only neutral destination capability facts; models supplies the declaration |
| state | `qitos/core/state.py` — `StateSchema`/migration registry | no blind copy; inject a typed projector resolver at execution and persist only its ref/digest |
| safe diagnostics | `qitos/core/diagnostics.py` | reuse path/secret/local-endpoint detection and bounded redaction semantics |

No current type combines these transfer facts without duplicating one of the
contracts above. The minimum new module-level candidates are therefore
`ContextTransferPlan` and `ContextTransferReceipt`, plus implementation-neutral
projector/policy protocols and strict execution/read helpers.

## Contract shape

`ContextTransferPlan` is immutable and integrity protected. It records operation
identity/kind; typed source session/run/work/snapshot identities and head digest;
destination agent/spec resolver reference and request target; context selection;
state schemas/projector ref and digest; continuation requirement; exact existing
budget/capability allocation requests; canonical artifact refs; required
components; approved-loss codes; and destination constraints.

`ContextTransferReceipt` records the plan/operation/source/destination identities,
selected/transformed/omitted/loss facts, projected child state, continuation
disposition, canonical artifact refs, granted/rejected authority, reconstruction
requirements, policy/provenance digests, terminal disposition, typed failure,
and integrity digest. Its canonical, model, and diagnostic projections are
separate allowlists.

## File lease

Lane B owns:

- `qitos/core/context_transfer.py` (new)
- `tests/core/test_context_transfer.py` (new)
- `tests/fixtures/context_transfer/` (new)
- this plan

G4 retains the shared lease for `README.md`, `CHANGELOG.md`, progress,
architecture/public-surface documents, aggregate `__init__` modules, and final
convergence receipts. Lane B will not edit those files. Engine, Session runtime,
WorkGraph scheduler behavior, and provider transports are outside this lease.

## Implementation steps

1. [completed] Add strict plan/receipt codecs, deterministic digests, defensive
   JSON ownership boundaries, and safe projections.
2. [completed] Add exchange-safe selection, continuation validation, typed state
   projection, artifact authorization, and five-way least-privilege authority.
3. [completed] Add exhaustive offline contract and independent-implementation tests.
4. [in progress] Publish versioned fixture/evidence and an exact-source consumer
   handoff, then run focused/full/static/public-surface gates.

## Risks and controls

- Frozen dataclasses can still contain mutable dict/list members: store all
  nested payloads as canonical JSON and reconstruct defensive copies on access.
- Hashing unsafe input is not sanitization: reject secret/path/endpoint/live
  values before computing integrity digests.
- Custom selection can split tool batches: selection operates on whole ordered
  exchanges and validates the resulting `ExchangeLog`.
- Provider continuation may look compatible by family only: require exact
  provider, model, API mode, expiry, and destination codec capability.
- Projectors are process-local code: persist resolver identity/capability/digest,
  never the callable; fail closed on missing or mismatched resolver.
- Least privilege can be accidentally implemented as a union: compute the
  intersection of all five authorities and reject requested escalation.
- Model/diagnostic views can leak canonical private fields: use explicit
  allowlists and never recursively echo rejected data.

## Lane C consumer handoff

Lane C must import the real module-level plan/receipt types and strict readers,
persist the plan before child dispatch, persist the terminal receipt before join
publication, and enforce only the granted `BudgetAllocation` and
`CapabilityAllocation`. It must not copy enums/shapes or infer identities. The
final fixture manifest will name the producer commit, schema IDs, byte digests,
test node IDs, and supported/unsupported cases.

## Lane D consumer handoff

Lane D must consume `ContextTransferReceipt.to_diagnostic_dict()` (or its strict
round-tripped equivalent) for read-only graph/timeline facts. It must not render
the canonical child state, resolver keys, opaque continuation, rejected values,
or host/provider payloads. Model-visible inspection uses only
`to_model_dict()`.
