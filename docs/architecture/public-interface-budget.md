# G2 public-interface budget

Status: independently enforced for the G2 promotion candidate
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
