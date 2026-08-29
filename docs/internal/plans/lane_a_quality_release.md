# Lane A quality and release trust plan

Status: complete
Updated: 2026-08-29
Work package: Lane A / A1 — Task 08A repository-wide static quality ratchet
Source baseline: `fb75cd5902fedf50d5e67dd617e62cd981c3128f`

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
