# CI job ownership and evidence

Status: repository-intent inventory for Lane A / Task 08E
Updated: 2026-08-29

This table records the role expressed by repository configuration. It is not
evidence of GitHub branch-protection settings: those settings are external and
were not inspected in this lane. A maintainer must compare the intended
required rows below with the repository ruleset before renaming, disabling, or
deleting any configured check.

| Workflow / job | Surface | Repository role | Evidence command | Expected CI runtime |
|---|---|---|---|---:|
| `ci.yml` / `tests` | supported Python matrix and full pytest suite | required candidate | `pytest -q` | 3–8 min |
| `ci.yml` / `coverage` | 80% floor for core, engine, and trace | required candidate | coverage pytest invocation in workflow | 2–5 min |
| `ci.yml` / `package` | wheel/sdist build and metadata validity | required candidate | `python -m build`; `python -m twine check dist/*` | 1–3 min |
| `ci.yml` / `lint-stable` | stable zero-debt lint surface | required candidate | `flake8 qitos/core qitos/engine qitos/models qitos/trace` | <1 min |
| `ci.yml` / `type-stable` | stable zero-debt type surface | required candidate | `mypy qitos/core qitos/engine qitos/models qitos/trace` | 1–2 min |
| `ci.yml` / `static-ratchet` | full active `qitos` no-regression baseline | required candidate | `python scripts/static_quality.py check` | 1–3 min |
| `ci.yml` / `architecture-boundaries` | dependency boundary allowlist | required candidate | `pytest -q tests/test_architecture_boundaries.py` | <1 min |
| `ci.yml` / `audit` | installed dependency vulnerabilities | required candidate | `pip-audit --progress-spinner off` | 1–3 min |
| `docs.yml` / `validate` | documentation navigation and bilingual parity | required candidate | embedded deterministic validators | <1 min |
| `contribution-test.yml` / all jobs | path-scoped tool/parser/critic diagnostics | advisory | always run when the workflow-level contribution paths match | 1–4 min |
| `zoo-test.yml` / `stale-zoo-inventory` | migration-document inventory only; no framework/product runtime coverage | stale advisory; disable/move candidate after ruleset evidence | deterministic staging-manifest inventory | <1 min |
| `pypi.yml` / `build` | release artifact construction | release-only required predecessor | build and twine check | 1–3 min |
| `pypi.yml` / `publish` | trusted publication after release build | release-only privileged action | PyPI trusted-publish action | 1–3 min |

## Trust rules

- The stable lint/type commands and full-package ratchet are separate blocking
  candidates with different debt contracts; neither substitutes for the other.
- Main pytest, architecture boundaries, package construction, dependency audit,
  and the static gates expose separate failure causes even where the full suite
  provides some overlapping execution.
- Advisory jobs still fail visibly when their commands fail. They do not use
  `continue-on-error`, `|| true`, or automatic reruns to manufacture success.
- `contribution-test.yml` uses supported workflow-level path filters and runs
  every focused job within that scope. It does not treat the numeric
  `pull_request.changed_files` field as an iterable.
- `zoo-test.yml` is retained because branch-protection usage is unknown. It is
  explicitly named stale/advisory and no longer runs missing or out-of-tree
  product tests. Runtime coverage belongs in the qitos-zoo repository.
- `tests/test_workflow_contracts.py` blocks invalid changed-file expressions,
  masked/rerun commands, missing pytest/docs paths, bilingual documentation
  drift, loss of the distinct stable and ratchet commands, and undocumented
  workflow files.
