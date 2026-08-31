# G2-R2 independent repair, promotion, and worktree retirement

Status: planned; blocks G2 promotion and every S2 runtime lane
Updated: 2026-08-31
Owner: one integration owner
Integration branch: `feat/campaign-absorption`
Integration base before this audit record:
`3ab69c91b8c5b7759208a3449def341658bd5fd1`
Reviewed G2 candidate:
`cab8fd246d2485784a13558e668eadb3ffa4d42f`

## Objective

Preserve the useful G2 contract convergence while closing the independent
review findings, replaying it onto the integration branch that contains the
worktree-retirement policy, promoting one verified baseline, and removing
superseded worktrees without deleting their branch or commit references.

This is one bounded repair/integration task. It does not implement session
runtime, provider dispatch, a child scheduler, Trajectory, or qita behavior.

## Source and promotion topology

The G2 candidate started at
`096e08244a0274720a58f07ed9f45ca0a7eece59`. The integration branch later
advanced to `3ab69c91...`, so `cab8fd2...` cannot fast-forward the current
integration branch. An isolated replay of the 29 commits in
`096e082..cab8fd2` onto `3ab69c91...` applied the first 28 commits and stopped
only on the final documentation commit. The expected conflicts are:

- `CHANGELOG.md`;
- `README.md`;
- `README.zh.md`;
- `docs/v4/11-four-lane-execution-playbook.md`.

The G2-R2 worktree must start from the exact later
`feat/campaign-absorption` dispatch SHA supplied after this audit record is
committed. It must contain `3ab69c91...` and this plan. Apply the candidate
commits in source order; resolve shared documents line by line, retaining both
the G2 implementation evidence and the independent finding/promotion/cleanup
truth. Do not merge or copy the candidate's premature `G2 CLOSED` wording.

## Independent validation already passed

On the clean G2 candidate:

- full suite: `2010 passed, 50 skipped`;
- focused contract/boundary suite: `226 passed`;
- static ratchet: 399 findings, 377 active and 22 vendored/generated;
- stable flake8: zero findings;
- stable mypy: 84 source files, zero errors;
- readiness without receipts: exit 0, 0 qualified, 19 receipt findings,
  30 blockers;
- readiness with exact receipts: exit 0 in dry-run and exit 2 in normal mode,
  19 qualified, zero receipt findings, 11 non-contract blockers;
- every readiness mode remains `schema_not_ready` with empty measurements and
  claims.

These green gates validate the candidate's broad direction. They do not cover
the blockers below.

## Required repairs

### R2-T — strict historical ToolResult grammar

`ToolResultCompatibilityReader` currently validates a historical
`qitos.tool_result/v1` payload against the current field set. A payload labelled
historical can therefore inject current-only `attempt_id`, `owner_generation`,
effect, uncertainty, retry, and batch-closure fields and be accepted.

Required:

- define the exact historical field grammar from committed historical bytes;
- reject every current-only field under the historical schema identifier;
- keep one current `ToolResult` and one current writer;
- keep historical conversion inside the bounded compatibility reader;
- add adversarial mixed-schema fixtures and typed failure assertions;
- do not introduce a public `ToolResultV2` or parallel result hierarchy.

### R2-P — strict ProviderCapabilities decoding

`ProviderCapabilities.from_dict()` currently accepts values such as string
feature sequences, string/integer/list booleans, and negative input budgets; a
different malformed value can escape as raw `TypeError`.

Required:

- require finite, explicit field types at constructor, adapter declaration, and
  persisted-reader boundaries;
- require string sequences rather than treating a string/dict as an iterable;
- require real booleans for every capability flag;
- require `max_input_units` to be `None` or a positive non-boolean integer;
- reject empty/duplicate/unknown capability values according to one documented
  vocabulary policy;
- normalize all malformed declarations and records to typed codec failures;
- retain provider-owned declarations and no provider-name heuristic.

### R2-R — complete diagnostic and ArtifactRef safety

The shared diagnostic helper does not currently recognize `/etc`, `/usr`,
`/Library`, standalone OpenAI/AWS-style keys, or JWT-like values.
`ProviderFailure.category` is not sanitized, nested safe-named fields can carry
those values, and `ArtifactRef` accepts a resolver such as
`resolver:/etc/passwd` plus a secret-like model summary.

Required:

- cover arbitrary absolute POSIX and Windows paths, file/home paths, local
  endpoints, authorization values, common key/token/JWT/PEM shapes, and nested
  secret-bearing values;
- apply the safe boundary to every externally supplied ProviderFailure text
  field, including category;
- validate all logical ArtifactRef strings and its model projection;
- retain stable error code, retryability, status, bounded remediation, and
  correlation digests without echoing rejected input;
- test message, category, provider, API mode, error code, nested details,
  ArtifactRef, exception text, receipt, readiness, model, and trace projections;
- use conservative redaction rather than attempting to enumerate only known
  home-directory roots.

### R2-D — honest current and historical receipts

The reported 19/19 count includes two G1 foundation receipts. The item named
`lane_c.canonical_tool_result_fixture_version` still binds
`qitos.tool_result/v1` at `9a0c5ed...`, even though the current writer is the
new schema. The ExchangeLog foundation likewise represents historical bytes.

Required:

- label retained G1 receipts as historical compatibility evidence, not current
  canonical-writer evidence;
- publish current ToolResult and current ExchangeLog producer fixtures after
  R1-T/R1-R are committed;
- bind exact producer commit, path, digest, committed/current bytes, authority,
  lineage, and independent consumer tests;
- adjust the requirement count if honest semantics require separate historical
  and current receipts; do not preserve 19 merely to preserve a reported
  number;
- keep runtime, writer/store, qita, publication, and measurement blockers
  independent from contract qualification.

### R2-U — make the interface budget semantically enforceable

The G2 budget classifies three diagnostic helpers as `internal-private` while
the module explicitly publishes them through `__all__`. In Python those two
claims conflict.

Required:

- remove internal-private names from `__all__`, or reclassify them honestly as
  supported extension APIs;
- make the executable budget distinguish deliberate exports from private
  module symbols;
- retain zero root-export and zero Engine-parameter growth;
- keep persistence constants, migrations, receipts, and registries outside the
  beginner path;
- record a reviewed growth policy rather than treating fixture edits as
  automatic authorization for API expansion.

## Promotion and documentation rules

After repairs:

1. run the full gate matrix on the G2-R2 branch;
2. update `docs/progress.md` with exact fixing/evidence commits;
3. mark every current G2 checklist item explicitly, leaving runtime items open;
4. fast-forward `feat/campaign-absorption` only if its expected old HEAD still
   matches the G2-R2 dispatch baseline;
5. rerun the critical gates on the promoted integration checkout;
6. record the final promoted SHA as the sole S2 baseline;
7. only then execute worktree retirement.

Do not call a lane-local branch the integration branch and do not mark G2
closed while promotion or cleanup remains incomplete.

## Worktree-retirement scope

The audit found 16 clean non-primary worktrees consuming approximately
10.13 GiB. After promotion, re-check clean/idle/registered/ref-preserved status
and remove only explicit paths with `git worktree remove <path>` without
`--force`, followed by `git worktree prune`.

The retirement allowlist covers completed G1, earlier A/B/C/D repair lanes,
S1 A/B/C/D, the G2 candidate, and finally the G2-R2 worktree. Preserve every
branch and commit ref. Never remove `/Users/morinop/Desktop/WhitzardOS`, never
use recursive filesystem deletion, and report dirty, locked, active, or
unrecorded paths as cleanup blockers.

Measure registered worktree count and disk usage before and after cleanup and
publish the receipt in `docs/progress.md`.

## Verification

- historical/current ToolResult grammar and mixed-schema adversaries;
- ProviderCapabilities malformed constructor/declaration/reader matrix;
- provider/WorkGraph/ArtifactRef diagnostic and secret/path adversaries;
- current and historical ExchangeLog/ToolResult receipt validation;
- cross-line identity, snapshot, artifact, effect, and readiness tests;
- architecture, public surface, no-local-path, and documentation parity;
- Python 3.12 quality ratchet, stable flake8, stable mypy;
- full `pytest -q` without rerun or masked exit;
- all three readiness modes;
- `git diff --check`, promoted integration rerun, final clean status;
- post-promotion `git worktree list` and disk-use receipt.

## Exit criteria

- [ ] All five R2 repair groups have fixing commits and regression tests.
- [ ] Candidate commits are replayed onto the latest audit-bearing integration
      baseline with shared documents resolved honestly.
- [ ] Current and historical producer receipts describe different facts.
- [ ] G2 checklist and status agree with actual code and integration topology.
- [ ] Integration branch fast-forwards to the independently qualified HEAD.
- [ ] Promoted-tree gates pass.
- [ ] Superseded worktrees are removed without force; branches/refs remain.
- [ ] One exact S2 baseline is recorded and S2 remains otherwise untouched.

## Explicit non-goals

No Session façade/runtime, durable head CAS, pause/resume/fork behavior,
fresh-process restore, persistent child scheduler, provider-default switch,
Trajectory writer/store, qita runtime, packaging release, live model, or remote
deployment belongs in G2-R2.
