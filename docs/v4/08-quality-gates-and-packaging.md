# Task 08 — quality gates, packaging, and test trust

Status: in progress — 08A implemented on Lane A; 08B–08E remain open
Depends on: Task 01
Unblocks: Task 09 and safe large-scale work in Tasks 02–05
Risk: medium — CI policy and contributor workflow

---

## 1. Goal

Make a green QitOS build mean what contributors think it means: no newly
introduced static defects anywhere in the shipped package, advertised optional
features install correctly, and tests execute critical routes rather than only
asserting that symbols or strings exist.

This task uses a ratchet. It does not require hundreds of pre-existing findings
to be repaired in one review.

## 2. Baseline contract

Record the exact commands, tool versions, Python version, exclusions, and
machine-readable findings at the start of 08A. Separate findings into:

- **correctness class:** undefined names, invalid overrides, unreachable imports,
  impossible branches, unbound resources;
- **contract class:** public typing errors, protocol violations, dependency
  declarations inconsistent with imports;
- **hygiene class:** unused imports, formatting, line length, and similar local
  debt;
- **intentionally excluded:** generated/vendored code with an owner and removal
  plan.

New findings in any non-vendored `qitos/` file fail CI immediately. Existing
findings live in a committed baseline keyed by rule, path, and stable location;
the baseline cannot grow without a reviewed exception and expiry.

## 3. Work packages

### 08A — static baseline and no-regression ratchet

1. Write `docs/internal/plans/task08_quality_gates.md` with the selected ratchet
   implementation and baseline format.
2. Pin or record diagnostic versions so local and CI results agree.
3. Generate full-surface flake8 and mypy reports. Do not hide packages using
   broad `ignore_errors = true` after their findings have been baselined.
4. Make new findings blocking. Preserve the existing stable-surface zero-error
   jobs until the full ratchet is demonstrably stricter.
5. Fix correctness-class findings in small, behavior-focused commits. The known
   `qita` undefined route variable requires a route test before its fix.

Decision gate: stop for review if the selected ratchet depends on unstable line
numbers or silently drops diagnostics that cannot be parsed.

### 08B — package-by-package baseline retirement

Retire findings in ownership order, not alphabetical order:

1. `qitos.kit.parser`, `qitos.render`, and public kit contracts;
2. active recipes and `qita`;
3. checkpoint, MCP, evaluate/metric, experiment, and functional API;
4. deprecated benchmark code only where it remains shipped during Task 10B;
5. generated/vendored code through upstream pinning or isolation, not manual
   mass reformatting.

Each PR must reduce the baseline and add a regression test for every
correctness-class fix. A refactor PR may not include unrelated hygiene cleanup.

### 08C — packaging and optional-capability matrix

1. Inventory every non-stdlib import and map it to base install, an extra,
   build/dev only, or a deliberately unsupported integration.
2. Resolve known gaps: MCP HTTP, local embeddings, APScheduler, PDF/notebook
   helpers, pgvector drivers, and the incomplete `all` extra.
3. Add fresh-environment smoke jobs for the base package and each supported
   extra. Importing the base package must not activate optional integrations.
4. Missing optional dependencies must fail at feature construction with the
   exact extra name; they must not silently create an inert feature.
5. After install parity is proven, move project metadata to PEP 621
   `[project]`/`[project.optional-dependencies]` and keep one source of truth.

Decision gate: a feature with no maintainer/consumer or conflicting drivers is
handed to Task 10 for admission/deprecation; do not add dependencies merely to
make dead code import.

### 08D — high-value test architecture

Add tests in this order:

1. qita HTTP route execution: board/run endpoints, fork POST, malformed input,
   traversal rejection, SSE connection/cleanup, and shutdown;
2. provider failure conformance: transport/auth/rate-limit/malformed response,
   sync and streaming;
3. method recipe override conformance against `AgentModule`;
4. optional-feature construction under present/missing dependencies;
5. resource ownership fixtures that record surviving threads, subprocesses,
   clients, and schedulers.

Move flat tests into subsystem directories only when their owning module is
already being edited. Preserve test IDs or document the move so CI filters and
contributor workflows do not silently stop selecting them.

### 08E — CI and contributor workflow repair

1. Replace unsupported changed-file expressions in `contribution-test.yml`.
2. Remove unused variables and `|| true` from jobs intended to protect a merge.
3. Delete or relocate the stale in-repo zoo workflow; out-of-tree projects own
   their own integration checks.
4. Make required checks explicit and non-overlapping: full tests, stable zero-
   debt lint/type, repository ratchet, package build, dependency audit.
5. Add a lightweight workflow/config test that detects missing test paths,
   invalid path predicates, and commands masked by unconditional success.

## 4. Required artifacts

- machine-readable static baseline and human-readable generation instructions;
- optional feature/extra matrix in the packaging reference;
- isolated install smoke script or test harness;
- CI ownership table (job, surface, blocking status, expected runtime);
- updated contribution guide if commands or required checks change;
- evidence updates in this task document after each package lands.

## 5. Acceptance criteria

- [ ] A new flake8 or mypy finding in any active non-vendored `qitos/` package
  fails CI.
- [ ] Stable-surface zero-error gates remain green throughout migration.
- [ ] No broad mypy ignore remains without an itemized baseline and owner.
- [ ] Every correctness-class baseline item is fixed or has an explicit task and
  regression reproducer.
- [ ] Base install and every advertised extra pass fresh-environment smoke tests.
- [ ] Missing optional dependencies raise actionable feature-specific errors.
- [ ] qita fork POST and provider error paths execute in tests.
- [ ] No required CI command is masked by `|| true`.
- [ ] Zoo/product checks do not masquerade as in-repo framework coverage.
- [ ] `python -m build` and `python -m twine check dist/*` pass after metadata
  migration.

## 6. Verification

Exact commands may be wrapped by the ratchet tool, but the underlying evidence
must remain reproducible:

```bash
pytest -q
pytest -q tests/test_architecture_boundaries.py
flake8 qitos
mypy qitos
python -m build
python -m twine check dist/*
```

Fresh-install jobs must use clean virtual environments and must not inherit the
developer environment's optional packages.

## 7. Stop-and-escalate decisions

Stop for maintainer review before:

- making an existing diagnostic disappear through a broader exclusion;
- changing public behavior while fixing a static finding without a regression
  test and migration note;
- adding an optional dependency to the base install;
- declaring an inactive/deprecated package “fully typed” by excluding it;
- migrating packaging metadata without comparing wheel contents and entry
  points before and after;
- removing a workflow that is actually a required check in repository settings.

## 8. Coordination contract

Task 08 owns gates, packaging metadata, and test infrastructure. It does not own
the semantic fixes exposed by those gates:

- provider failures go to Task 02/09;
- action outcomes/timeouts go to Task 03/09;
- context/token behavior goes to Task 02/04;
- trace schema goes to Task 05;
- deletions and surface reduction go to Task 10.

## 9. Task 08A evidence — 2026-08-29

Source identity:

- W1 commit: `fb75cd5902fedf50d5e67dd617e62cd981c3128f`;
- branch: `codex/v4-lane-a-quality-ratchet`;
- local/CI entrypoint: `python scripts/static_quality.py check`.

Pinned diagnostic toolchain:

- Python 3.12.7;
- flake8 7.0.0, pyflakes 3.2.0, pycodestyle 2.11.1, mccabe 0.7.0;
- mypy 1.19.1 with Python 3.11 as its source-language target.

The committed baseline contains 399 findings: 204 flake8 and 195 mypy. It
contains 377 active findings and 22 vendored/generated findings. Semantic
classification is 36 correctness, 163 contract, and 200 hygiene findings; one
correctness finding belongs to the vendored Tau port and therefore has the
top-level `vendored/generated` classification while retaining its correctness
kind. `quality/correctness_handoffs.md` assigns all correctness findings to
Lanes B, C, or D. Lane A did not downgrade or fix runtime correctness debt.

The baseline identity uses rule, path, enclosing symbol, normalized source-line
hash, message, and occurrence. Line/column values remain evidence but are not
matching keys. Baseline checks fail on new findings and on stale allowances
after a finding is fixed. Additions require an itemized maintainer exception,
reason, and future expiry. A tool-version mismatch fails separately as a rules-
upgrade event.

Controlled failure proof:

1. a temporary active `qitos/_quality_ratchet_probe.py` with one unused import
   caused the ratchet to exit 1 and report exactly one new `flake8:F401`;
2. the probe was deleted without updating the baseline;
3. the same command then exited 0 with all 399 findings matched;
4. the probe is absent from the final diff and baseline.

Stable and test evidence:

- `flake8 qitos/core qitos/engine qitos/models qitos/trace`: clean;
- `mypy qitos/core qitos/engine qitos/models qitos/trace`: 76 source files,
  no issues;
- `pytest -q tests/test_architecture_boundaries.py`: 4 passed;
- `pytest -q tests/test_public_surface.py`: 4 passed;
- `pytest -q`: 1,703 passed, 50 skipped.

Test-trust investigation: 50 independent, targeted invocations of
`test_durability_manager_flush_full_queue_logs_warning` produced 50 passes and
zero failures without a rerun plugin. This does not retire the historical
failure: worker dequeue timing can still free a slot before `flush()` attempts
the sentinel. Lane C / Task 09D owns deterministic durability-contract tests
and the semantic resolution. Task 08A did not modify checkpoint runtime or the
warning assertion.

08A changes only the static baseline, ratchet tooling, pinned diagnostic
environment, the `ci.yml` ratchet/architecture jobs, and contributor evidence.
Optional installs, high-value route tests, baseline retirement, and the full
Task 08E workflow repair remain open.
