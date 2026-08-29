# Lane A quality and release trust plan

Status: complete — A1/A2 integration candidate; G1 remains open
Updated: 2026-08-29
Work package: Lane A / A1-I + A2 — static ratchet qualification and CI trust repair
Integration baseline: `8441bef2f2024fd6c2ec01784708512222382471`
A1 source: `ab25edf9c6457ee40054aaaab4596d7bed30cbe5`

## A1-I / A2 qualification scope

This round rebases the completed A1 package onto the reviewed integration
source, qualifies the pinned ratchet with deterministic transition tests, and
repairs Task 08E workflow predicates and result masking. It does not change
runtime behavior, public APIs, packaging metadata/extras, architecture
allowlists, or the integration-owned `docs/progress.md` ledger.

Source and target identity:

- integration branch/source: `feat/campaign-absorption` at
  `8441bef2f2024fd6c2ec01784708512222382471`;
- A1 source commits, in order: `00b23ef`, `67a7487`, `208860a`, `ab25edf`;
- qualification worktree: `/Users/morinop/Desktop/WhitzardOS-lane-a2`;
- qualification branch: `codex/v4-lane-a-ci-trust`;
- cherry-pick conflict scope: only `README.md`, `README.zh.md`, and
  `CHANGELOG.md`, resolved manually while preserving both the integration
  progress-ledger entry and A1 evidence.

Current leases:

- `scripts/static_quality.py`, `tests/test_static_quality_ratchet.py`: Lane A
  owns deterministic ratchet-transition qualification;
- `.github/workflows/*.yml`, `tests/test_workflow_contracts.py`: Lane A owns
  Task 08E predicate, masking, missing-path, and job-role contracts;
- `quality/README.md`, `docs/v4/08-quality-gates-and-packaging.md`, this plan,
  and the CI ownership evidence: Lane A owns qualification documentation;
- `README.md`, `README.zh.md`, and `CHANGELOG.md`: minimal synchronized closeout
  only; `docs/progress.md` remains read-only and integration-owner managed.

Qualification is complete only if Python 3.12.7, the pinned toolchain, the
full ratchet, stable zero-debt gates, targeted suites, and the full suite all
pass. That outcome may be called an A1/A2 integration candidate, never a claim
that the cross-lane G1 gate is closed.

## Outcome

Establish one reproducible full-`qitos` flake8/mypy diagnostic baseline and a
no-regression gate before the other v4 lanes expand the change surface. This
package changes quality infrastructure only. It does not change Agent, Model,
Tool, Checkpoint, Trace, qita, benchmark/recipe, public API, or packaging/extra
runtime semantics.

## Source identity

- Worktree: `/Users/morinop/Desktop/WhitzardOS-lane-a`
- Branch: `codex/v4-lane-a-quality-ratchet`
- Starting HEAD: `fb75cd5902fedf50d5e67dd617e62cd981c3128f`
- Starting status: clean

## Shared-file leases

Lease owner: Lane A / A1
File(s): `pyproject.toml`, `.pre-commit-config.yaml`
Semantic purpose: static-analysis configuration and pinned quality entrypoint
Expected start/end package: A1 only
Other lanes blocked or adapter supplied: no runtime owner is blocked; the
ratchet command and baseline are the handoff.

Lease owner: Lane A / A1
File(s): `.github/workflows/ci.yml`
Semantic purpose: keep stable zero-debt checks and add the full-package ratchet
plus an explicit architecture-boundary job
Expected start/end package: A1 only
Other lanes blocked or adapter supplied: B/C/D consume the same local command;
no other workflow is rewritten in A1.

Lease owner: Lane A / A1
File(s): `README.md`, `README.zh.md`, `CHANGELOG.md`
Semantic purpose: contributor-visible Task 08A status and local command
Expected start/end package: A1 documentation closeout
Other lanes blocked or adapter supplied: short additive entries only.

Lease owner: Lane A / A1
File(s): `docs/v4/08-quality-gates-and-packaging.md`
Semantic purpose: A1 evidence and acceptance status
Expected start/end package: A1 documentation closeout
Other lanes blocked or adapter supplied: later Task 08 packages retain their
unchecked status.

## Ratchet design

1. Pin the diagnostic interpreter, flake8, mypy, and flake8 plugin versions in
   a machine-readable toolchain file and an installable requirements file.
2. Run pinned flake8 over `qitos` with the committed `.flake8` policy and mypy
   over `qitos` with a dedicated config that contains no package exclude and no
   per-package `ignore_errors` override.
3. Store each finding with tool, rule, path, original line/column, normalized
   message, enclosing symbol, source-line hash, and a stable identity derived
   from rule + path + symbol + source anchor + message + occurrence.
4. Classify every finding as correctness, contract, hygiene, or
   vendored/generated. Vendored entries retain their underlying semantic class,
   provenance, owner, and exit plan.
5. `check` fails on every new finding, a stale baseline that should shrink, an
   expired exception, malformed diagnostics, or a toolchain mismatch. A
   toolchain mismatch is reported separately as a rule-upgrade event.
6. Baseline updates can remove findings without approval. Additions require an
   itemized exception naming the finding IDs, maintainer, reason, and future
   expiry date. CI compares baseline changes to the previous committed baseline
   when that baseline exists.
7. Local and CI entrypoint: `python scripts/static_quality.py check`.

Decision-gate result: the selected identity does not depend on line numbers.
Line and column are evidence only; matching uses the source anchor and enclosing
symbol. Unparseable diagnostics are fatal rather than silently discarded.

## Initial evidence

Candidate pinned environment observed locally:

- Python 3.12.7
- flake8 7.0.0
- pyflakes 3.2.0
- pycodestyle 2.11.1
- mccabe 0.7.0
- mypy 1.19.1

Unratcheted full-package diagnostic at the W1 source baseline:

- flake8: 204 findings;
- mypy: 195 errors when the old broad excludes/ignores are bypassed;
- total: 399 findings before classification and vendored attribution.

The earlier audit's 48-error mypy number used the narrower historical
configuration. The committed baseline records both the expanded scope and the
new pinned toolchain so future maintainers can distinguish newly introduced
debt from a deliberate rule/scope upgrade.

## Test-trust finding

`tests/test_bounded_queues.py::test_durability_manager_flush_full_queue_logs_warning`
is tracked as a race-sensitive test-trust finding. Lane A will measure repeated
targeted executions without automatic reruns. Lane C / Task 09D owns the
checkpoint durability contract and semantic fix. A1 will not edit durability
runtime code or delete/weaken the warning assertion.

## Verification plan

Required commands:

```bash
pytest -q
pytest -q tests/test_architecture_boundaries.py
pytest -q tests/test_public_surface.py
flake8 qitos/core qitos/engine qitos/models qitos/trace
mypy qitos/core qitos/engine qitos/models qitos/trace
python scripts/static_quality.py check
git diff --check
```

Controlled proof:

1. add one temporary undefined name to an active non-vendored `qitos` file;
2. show `python scripts/static_quality.py check` fails and names the new F821;
3. remove only that temporary line;
4. show the same command returns green;
5. verify the temporary finding is absent from the diff and baseline.

## Delivery sequence

1. Baseline format, parser, classifier, generator, and unit tests.
2. No-regression comparison and controlled failure proof.
3. CI integration with stable zero-debt and architecture jobs kept distinct.
4. Evidence, test-trust handoff, contributor docs, README/CHANGELOG, and final
   validation.

## Out of scope and handoffs

- Lane B: provider/parser/context correctness and invalid `prepare` overrides.
- Lane C: tool/outcome/env/MCP/checkpoint/functional correctness, invalid
  `reduce` overrides, and the durability test race under Task 09D.
- Lane D: qita/render/trace/benchmark correctness and vendored Tau exit work.
- Lane A will not fix these semantic findings in A1; the generated handoff list
  assigns every correctness entry to its semantic owner.

## Implementation evidence

Artifacts:

- `quality/static_baseline.json`: 399 machine-readable findings;
- `quality/correctness_handoffs.md`: 36 semantic correctness findings assigned
  to Lanes B/C/D, including one vendored correctness finding;
- `quality/toolchain.json`, `quality/mypy.ini`, and
  `requirements/quality.txt`: reproducible diagnostic environment;
- `scripts/static_quality.py`: bootstrap, strict check, shrink-only update, and
  expiring exception enforcement;
- `tests/test_static_quality_ratchet.py`: 9 parser, classification, identity,
  exception, and toolchain contract tests;
- `.github/workflows/ci.yml`: separate full-package ratchet and architecture-
  boundary jobs while stable lint/type and pytest jobs remain distinct.

Baseline counts:

| Dimension | Count |
|---|---:|
| Total | 399 |
| flake8 | 204 |
| mypy | 195 |
| Active non-vendored | 377 |
| Vendored/generated | 22 |
| Correctness semantic class | 36 |
| Contract semantic class | 163 |
| Hygiene semantic class | 200 |

Top-level categories contain 35 correctness, 143 contract, 199 hygiene, and 22
vendored/generated entries. The difference from semantic counts is deliberate:
vendored/generated entries retain an underlying semantic category, including
one correctness finding, instead of being mislabeled as hygiene.

Controlled proof:

- temporary probe: `qitos/_quality_ratchet_probe.py` with unused `os` import;
- failing result: exit 1, exactly one new `flake8:F401` reported;
- recovery: probe deleted, baseline unchanged, exit 0 with 399 findings matched;
- final source/baseline search: probe absent.

Test-trust investigation:

- 50 independent targeted pytest processes;
- 50 passed, 0 failed;
- no rerun plugin or failure-masking command;
- historical race remains open because the worker can drain the queue before
  `flush()` attempts its sentinel;
- owner: Lane C / Task 09D; no checkpoint runtime/assertion change in A1.

Verification completed before documentation closeout:

- `pytest -q`: 1,703 passed, 50 skipped;
- architecture boundaries: 4 passed;
- public surface: 4 passed;
- stable flake8: clean;
- stable mypy: 76 source files, no issues;
- ratchet after controlled recovery: passed, 399 matched;
- ratchet unit tests: 9 passed;
- `git diff --check`: passed for tracked changes; final staged-tree check is
  still required after adding generated artifacts.

Known remaining Task 08 work: package-by-package debt retirement (08B), optional
install matrix (08C), high-value route/provider/resource tests (08D), and the
complete contribution/zoo workflow repair (08E). Existing masked commands in
those legacy workflows were not copied into the new blocking jobs and are not
claimed fixed by A1.

## Commits

1. `00b23ef` — static toolchain, baseline format, generator/ratchet, handoffs,
   and unit tests;
2. `67a7487` — distinct full-package ratchet and architecture-boundary CI jobs;
3. `208860a` — Task 08A evidence, contributor docs, README/README.zh, and
   changelog.

Final review confirmed that no runtime file, public API, packaging/extra
declaration, historical `docs/v4/06-*`/`07-*` record, or other lane worktree was
modified. The controlled probe is absent. The final branch status is clean
after the evidence-closeout commit.

## A1-I / A2 qualification closeout

The four A1 source commits were applied to integration baseline `8441bef` in
their declared order. README.md, README.zh.md, and CHANGELOG.md were the only
conflicts; they were merged item by item to preserve both the integration
progress-ledger link and A1 quality evidence. No runtime or baseline conflict
occurred, and integration-owned `docs/progress.md` was not edited.

Ratchet qualification:

- transition tests increased from 9 to 20 and use temporary files, a fixed
  date, monkeypatches, and synthetic base refs;
- new/stale findings, controlled growth, legal and expired exceptions, W1
  bootstrap identity, source-debt/rules-upgrade separation, malformed
  diagnostics, and explicit update behavior are mechanically covered;
- the real controlled F401 probe exited 1 with rule/path/symbol evidence, then
  deletion without baseline mutation restored exit 0;
- the baseline remains 399 total, 377 active, and 22 vendored/generated, with
  the same SHA-256 `05ae4fb966c1f69ccbb59dc4bd6d859fff1d7ba02fc0c8df56a655849acab6f5`.

CI trust repair:

- invalid changed-file predicates and unused changed-count logic were removed;
- intended commands no longer use `|| true`, stderr suppression, unconditional
  `continue-on-error`, or automatic reruns;
- contribution jobs are explicitly advisory and run within supported
  workflow-level path scope;
- the stale zoo workflow is retained, explicitly named stale/advisory, and
  reduced to a deterministic migration inventory because external required-
  check settings were not available;
- six workflow/config contract tests guard predicates, masking/reruns,
  referenced pytest/docs paths, bilingual documentation parity, the
  stable/full-package split, and job inventory;
- `docs/internal/ci-job-ownership.md` is the repository-intent ownership table,
  not a claim about GitHub branch protection.

Final qualification evidence:

- Python 3.12.7; flake8 7.0.0; pyflakes 3.2.0; pycodestyle 2.11.1;
  mccabe 0.7.0; mypy 1.19.1;
- pinned full-package ratchet: passed, 399 matched;
- stable flake8: clean; stable mypy: 76 files, no issues;
- ratchet tests: 20 passed; workflow contracts: 6 passed;
- architecture boundaries: 4 passed; public surface: 4 passed;
- full suite: 1,720 passed and 50 skipped after its local-path policy caught and
  Lane A removed a host-specific path from public evidence;
- durability race investigation: 50 independent processes passed, 0 failed,
  with no automatic retry. The test-trust finding remains assigned to Lane C /
  Task 09D and no checkpoint behavior/assertion was changed.

Known gaps: branch-protection/ruleset configuration was not inspected, so no
workflow is claimed actually required by GitHub and the stale zoo workflow was
not deleted. Task 08B baseline retirement, 08C packaging/extras, and 08D
behavioral route/provider/resource coverage remain open. This lane is an
A1/A2 integration candidate only; it does not claim the program-wide G1 gate is
closed.

## G1 integration-owner A-CI1 closure

All seven reviewed Lane A commits were integrated in their supplied order on
`codex/v4-g1-convergence`. The integration owner replaced the workflow's broken
inline `ToolSpec` import with `scripts/qualify_tool_schemas.py`, a normal
repository entrypoint used unchanged by the workflow and executable tests.

The entrypoint imported 61 real `qitos.kit.tool` modules, inventoried 74 public
class-tool definitions, qualified 62 constructible class tools, and registered
all 62 through `ToolRegistry`; 12 constructor-dependent definitions were
reported rather than instantiated with fake dependencies. A controlled invalid
spec ran through the same entrypoint, exited 1, and reported
`invalid_tool_name`. Integrated Phase A evidence is 20 ratchet tests, 8 workflow
tests, 4 architecture tests, 4 public-surface tests, and the pinned Python
3.12.7 ratchet with all 399 baseline findings matched. This closes A-CI1 only;
combined G1 remains an integration-owner decision after C/B/D qualification.
