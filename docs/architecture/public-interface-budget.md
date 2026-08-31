# G2 public-interface budget

Status: G2 evidence preserved; S2/current budget frozen for S3 dispatch
Updated: 2026-08-31

G2 adds persistence and migration contracts without expanding the root `qitos`
API or `Engine.__init__`. The executable source of truth is
`tests/fixtures/public_surface/g2-interface-budget.json`; the test
`tests/test_g2_interface_budget.py` distinguishes deliberate module exports
from implementation-private symbols and requires every deliberate `__all__`
name in the eight convergence modules to have exactly one supported
classification.

## Budget

| Surface | Intended audience | Rule |
|---|---|---|
| beginner-facing | ordinary agent authors | Only direct concepts such as `SessionSnapshot`, `RequestView`, `ArtifactRef`, `ToolResult`, and `WorkGraph`; no schema/CAS/receipt bookkeeping |
| extension-facing | provider, persistence, and orchestration implementers | Typed identities, registries, codecs, capability declarations, and structured failures |
| persistence-internal | current writers and compatibility readers | Schema constants, component envelopes, receipts, integrity records, and migration readers; never part of the beginner path |
| internal-private | implementation helpers | No supported import promise |

The reviewed module budget is 124 deliberate exports plus three visible but
unsupported implementation-private diagnostic symbols. Those three helpers
are deliberately absent from `qitos.core.diagnostics.__all__`. The deliberate
count includes the canonical `ArtifactRef` re-exported by `request_view`; that
re-export is the same class, not a second artifact contract. The root package
remains at the reviewed 41 exports and `Engine.__init__` at the reviewed 33
parameters, so G2 growth at both surfaces is zero.

## Beginner path

The existing `AgentModule + Engine` path remains authoritative. G2 introduces
no root export and no Engine argument for pause, resume, fork, session stores,
snapshot registries, or trajectory stores. Future user-facing session verbs are
budgeted as `run`, `pause`, `restore`, `fork`, `steer`, `inspect`, `handoff`,
`delegate`, `fan_out`, and `join`, but G2 implements only their prerequisite
contracts.

Ordinary examples must not require users to construct snapshot component
envelopes, codec reports, generation compare-and-set records, or qualification
receipts. Those remain extension or persistence concerns.

## Enforcement

The public-surface test fails when:

- a convergence module adds or removes an `__all__` entry without updating the
  reviewed classification and the separately pinned growth policy;
- one name is placed in more than one category;
- an internal-private name appears in `__all__` or no longer exists;
- the exact reviewed root export set or `Engine.__init__` parameter set changes.

Editing the JSON fixture alone does not authorize growth: the test pins the
reviewed counts, root names, Engine parameters, and
`architecture-review-required` authority independently. Any intentional
expansion therefore needs architecture review plus coordinated policy, test,
and documentation changes.

This is a visibility budget, not a deletion target. Extension contracts remain
available where required for independent implementations, while the beginner
surface stays small.

## S2/current review

The G2 fixture above remains immutable historical evidence. S2 has a separate
executable budget at
`tests/fixtures/public_surface/s2-current-interface-budget.json`, enforced by
`tests/test_s2_interface_budget.py`.

| Surface | S2/current result |
|---|---:|
| root `qitos.__all__` | 41 |
| `qitos.engine.__all__` | 27 |
| `qitos.checkpoint.__all__` | 24 |
| `qitos.models.__all__` | 28 |
| `qitos.tracing.__all__` | 22 |
| reviewed aggregate exports | 101 |
| `Engine.__init__` parameters including `self` | 34 |

The added `runtime` parameter is architecture-approved as a migration
composition entry for checkpoint, lifecycle, event-sink, snapshot-component,
and tool-policy ownership. Existing checkpoint/action/context constructor
arguments remain compatibility adapters into that same composition; they are
not a second mutable runtime truth. Follow-up work must move repeated groups
behind the composition/config path and then deprecate redundant constructor
spelling before considering any further Engine-parameter growth.

Candidate Trajectory records, stores, readers, exporters, and adapters remain
available only from their explicit unfrozen modules and are absent from
`qitos.tracing.__all__`. Checkpoint CAS records, provider implementation
records, and runtime component internals likewise require explicit module
imports. The ordinary path remains `Engine(agent).session(task)` plus the small
Session façade; it does not expose envelopes, registries, CAS records,
durability receipts, codec reports, or Trajectory records.

## S3 freeze

The measured S2/current counts above are the S3 dispatch ceiling, not a target
for growth. S3 keeps root exports at 41, the four reviewed aggregates at
27/24/28/22 (101 total), and `Engine.__init__` at 34 parameters including
`self`. Root growth requires item-by-item G4 public-surface review; the Engine
constructor gains no parameters.

Proposed multi-agent authoring stays on the existing Session facade (`fork`,
`handoff`, `delegate`, `spawn`, `fan_out`, and `join`) and behind replaceable
module-level protocols. Model-callable tools adapt to the same runtime rather
than defining a second surface. Advanced records remain module-level imports by
default, and public `V1`, `V2`, `Legacy`, `Next`, or parallel Agent/Session/
Runtime type tracks are forbidden. The full review contract is in
[`s3_durable_multi_agent_wave.md`](../internal/plans/s3_durable_multi_agent_wave.md).
