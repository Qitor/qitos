# G2-R2 independent repair, promotion, and worktree retirement

Status: complete — G2 CLOSED; S2 dispatch authorized
Updated: 2026-08-31
Owner: one integration owner
Integration branch: `feat/campaign-absorption`
Integration dispatch baseline:
`8e17b1f6471a89a52aacec74a55f41386d44559a`
Reviewed G2 candidate:
`cab8fd246d2485784a13558e668eadb3ffa4d42f`

Repair qualification through:
`49fa15b5b0499e3f2a1bb4ea86b2af7a143f3e5c`

## Repair execution record

The candidate range was replayed in exact source order onto dispatch baseline
`8e17b1f6471a89a52aacec74a55f41386d44559a`; replay HEAD is
`a68b281c2b79cf26252801bf06c6a6f2a9fb5d3a`. Repair commits are:

- R2-T `3f2bde6` — strict historical ToolResult grammar;
- R2-P `0efa496` — strict ProviderCapabilities decoding;
- R2-R `0dad384` — diagnostic, ProviderFailure, ArtifactRef, WorkGraph, model,
  trace, receipt, and readiness safety;
- R2-U `abfd89d` — semantic public-interface budget;
- current writer evidence `00e9981` — ToolResult and nested ExchangeLog;
- R2-D `49fa15b` — 21 independently bound producer receipts.

Repair-tree gates passed: 291 focused tests; `2104 passed, 50 skipped` full
suite; 399-finding ratchet (377 active, 22 vendored/generated); stable flake8;
stable mypy on 84 files; readiness 0/21 without receipts and 21/21 with exact
receipts; exact normal mode exit 2; every mode `schema_not_ready` with empty
measurements/claims; and clean `git diff --check`.

Promotion was a guarded fast-forward from exact integration dispatch
`8e17b1f...` to `c0f19cd8f19a223fc84844f8a6a0ae4a5d0145aa`.
The primary checkout repeated the focused, ratchet, flake8, mypy, full-suite,
readiness, and diff gates successfully. Worktree retirement reduced 18
registered worktrees to one and reclaimed `11,287,672 KiB` (10.765 GiB) using
only non-forced `git worktree remove` calls plus prune; all 17 branch refs remain
reachable. `c0f19cd...` is the promoted contract code head. The independently
qualified, pushed, and remotely verified S2 dispatch baseline is
`446a347d1ac73636476ca2515a01da601b567c68`.

## Final closure receipt

Local `feat/campaign-absorption`, its tracking ref, and the read-only remote ref
were all verified at `446a347d1ac73636476ca2515a01da601b567c68` with divergence
`0/0`. The final-head focused, full-suite, static, lint/type, readiness, and
clean-tree gates passed. Git registered one primary worktree after retirement;
17 superseded worktrees were removed without force and all 17 branch refs were
retained. These facts close G2.

The sole S2 dispatch baseline remains
`446a347d1ac73636476ca2515a01da601b567c68`. Documentation-only ledger
successors record the completed remote state but do not redefine that baseline
or its ancestry. S2 implementation was not started by G2-R2.

### Candidate-to-replay commit map

| Source candidate commit | Replay commit |
|---|---|
| `99390d16662a3f7e62ca866654a518c898f0619a` | `0f60a11df92a21cd5b5dc0f4271638a99e559786` |
| `5dfc90617aaf0ebeac286b3633882583174668a3` | `6dd9b4fceb7565c4f7ddf280e16c3e9b2fd837d6` |
| `b58dddafd82654158afca7ec20545100bdd54636` | `36bb7c5d6f5425b229a9e0e06899857c551fda07` |
| `7c58233253afd6fd714a4920d67bd7862403acf5` | `ef65be8c596d6bff2634a2388a249b85f786257e` |
| `632e353b4658070e5fdbc75d95f695313bade43b` | `5d67627c030811be812cdab54dc6a9064a83b88e` |
| `a8db8ba5c94ffca3fdd6cd1abf2c67dba304144e` | `528e7fa22ff48f1f4855ed6b033caf0aec195fcd` |
| `b8bda14c09a7dc9f2279d0b4ee4c3e3f36c3b3fa` | `680f3b9df843145f7aab20a60dd74ae19387c65d` |
| `551fc3bf117ec7c3d34c2ceacd188e009cf79baa` | `34896be8807826866767ab57ad67ac838355d52f` |
| `7c769d0c23c53b867922e2b173e9ab261e3ba0b4` | `b7fd46b17a36f1e2f9fc461cc53219039596bebe` |
| `090008c04ee84b0e53af3ee976db1592356df443` | `6c2f2810c49b7ef78f45b484e5595f3eb54935ab` |
| `c02ddeaf45725e6a6f519ffdd217447b72858a56` | `4462aad165b6e0e2016cebbec334148f1cc27e8d` |
| `fb46b381c0b55283121d509da493aebe739b6711` | `5e7127fa7113e12e54cae7fa337391e1f9fcdf4c` |
| `2cb5d6b14fb5f6189f70486681b5fb9987a8eb65` | `dd1c390be8acd1594f553287b79b279e7c34b39d` |
| `12cc08f27c5b70696c1519bfd05dd24f7f542624` | `d6257abdd745da8362db96ab29a27f03bc3f9f93` |
| `3ab128048e85e9e05d32cd1a34e829ae28f29004` | `120150675d333116e0aec65f31ff0eb215dd1097` |
| `7c72484e8fce64f4c4b48f762b9e8d85020c7806` | `83d63b9ca5b61c4c956dd319e524c9c5aa3b2e53` |
| `368f879146a1ce41dddb97bd12f8d3b460f62257` | `dde334df7cadab512d0edaec215582b5c637c49b` |
| `45fb68879086c38df58e0b5f4258168b30adfb28` | `e44622b752d18de83ea9b2416a7db8188ac3c479` |
| `d090afe4dbc24df0fae22ffdbedfc84f04487d50` | `ee91224acc80a35be4981b4bee03fa99ddc5b739` |
| `dcc6c758799daca96a66fe3100792d52ee5fb3ad` | `68e1ffd6597b9fbc9a5bf2b7f397a329d4f7236f` |
| `cda9a8475736ae4746e259946d1873edf634ebdb` | `2b48b983b9b6afa7c0272e8e4f88aac5aa547584` |
| `f764147aa18ef79b9404cb54862d0e8b4e4fa08b` | `c06438bcca1d19a61422c6cb00794289037721ba` |
| `58864253a169d1bac5749ad2b2de5de6872c0da2` | `d90b6a99caa4b4c1d2f25807ac777085905d3ebd` |
| `bd7fca95e9ba9acfbbd9e8d0655a14ece066bcb6` | `39ae60a5664a26dfde5c3a444135a9c7f53c8c60` |
| `3cc29bea2bd311a2343862fd0b4f32636524bbb6` | `9241dd3ef379dafc8df299370bde3930241ffb03` |
| `ced9d3304e988504b155505c723b3a88d03ec6e9` | `f4e7b1cbac6705168d11312b34f6ed3982d32c82` |
| `fcb07843ce196a5d20d4bfceb6b668f9bdf70d94` | `6a005dd47afff64ea517c4f931a8c4917d631f35` |
| `2c3e634cb2ac709a9fd5c7e6cded51a78195c91c` | `1dee3ab957f0934de6d4cc5d5600edaebac7d37e` |
| `cab8fd246d2485784a13558e668eadb3ffa4d42f` | `a68b281c2b79cf26252801bf06c6a6f2a9fb5d3a` |

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
advanced to `8e17b1f...`, so `cab8fd2...` cannot fast-forward the current
integration branch. The authoritative replay of the 29 commits in
`096e082..cab8fd2` onto `8e17b1f...` applied the first 28 commits and stopped
only on the final documentation commit. The resolved conflicts were:

- `CHANGELOG.md`;
- `README.md`;
- `README.zh.md`;
- `docs/internal/plans/g2_contract_convergence.md`;
- `docs/internal/plans/s1_d_lineage_readiness.md`;
- `docs/progress.md`;
- `docs/v4/11-four-lane-execution-playbook.md`;
- `docs/v4/12-session-runtime-and-persistence.md`;
- `docs/v4/13-durable-multi-agent-work-graph.md`.

The G2-R2 worktree started from exact `feat/campaign-absorption` dispatch SHA
`8e17b1f...`, which contains this plan. The candidate commits were applied in
source order; shared documents were resolved line by line, retaining both
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
6. record the final closure-commit SHA as the sole S2 dispatch baseline;
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

- [x] All five R2 repair groups have fixing commits and regression tests.
- [x] Candidate commits are replayed onto the latest audit-bearing integration
      baseline with shared documents resolved honestly.
- [x] Current and historical producer receipts describe different facts.
- [x] G2 checklist and status agree with actual code and integration topology.
- [x] Integration branch fast-forwards to the independently qualified HEAD.
- [x] Promoted-tree gates pass.
- [x] Superseded worktrees are removed without force; branches/refs remain.
- [x] Exact local/tracking/remote SHA equality and `0/0` divergence are recorded.
- [x] One exact S2 baseline is recorded and S2 remains otherwise untouched.

## Explicit non-goals

No Session façade/runtime, durable head CAS, pause/resume/fork behavior,
fresh-process restore, persistent child scheduler, provider-default switch,
Trajectory writer/store, qita runtime, packaging release, live model, or remote
deployment belongs in G2-R2.
