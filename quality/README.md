# Static quality ratchet

Task 08A keeps the existing zero-error stable-surface gates and adds one
repository-wide no-regression gate for the shipped `qitos` package.

## Install and run

Use the exact interpreter and tools recorded in `toolchain.json`:

```bash
python --version  # Python 3.12.7
python -m pip install -r requirements/quality.txt
python scripts/static_quality.py check
```

CI runs the same entrypoint. A tool or Python version mismatch is reported as a
toolchain/rule-upgrade event, separately from a new source finding.

The stable zero-debt commands remain independent and blocking:

```bash
flake8 qitos/core qitos/engine qitos/models qitos/trace
mypy qitos/core qitos/engine qitos/models qitos/trace
```

## Baseline format

`static_baseline.json` is machine-readable and records every flake8/mypy
finding. Each entry contains:

- tool, rule, path, message, and original line/column evidence;
- enclosing symbol plus a normalized source-line hash as the stable location;
- an identity derived from rule, path, stable location, message, and occurrence;
- correctness, contract, hygiene, or vendored/generated classification;
- a semantic lane owner and, for correctness findings, a correctness kind;
- an optional reviewed exception.

flake8 uses the committed repository `.flake8` configuration. The tool version
pin and committed config together define the rule set; bypassing that config is
a rules upgrade, not newly introduced source debt.

Line numbers are not matching keys. Moving unchanged code therefore does not
create false debt, while changing the diagnostic or anchored source does.
Unparseable diagnostics fail the command.

The only vendored surface currently identified is
`qitos/benchmark/tau_bench/port`. It is still diagnosed. Its entries are marked
`vendored/generated`, retain their underlying semantic class, and point to Lane
D / Task 10B for provenance pinning, isolation, and removal from the core
distribution.

## Shrink or extend the baseline

When findings are fixed, shrink the baseline:

```bash
python scripts/static_quality.py update
python scripts/static_quality.py check
```

`check` treats a stale baseline as a failure, so a fix cannot leave an inflated
allowance behind.

New baseline entries are rejected unless every new finding is covered by one
itemized exception JSON file:

```json
{
  "schema_version": 1,
  "maintainer": "@maintainer",
  "reason": "Why this debt must land before its semantic fix",
  "expires_on": "2026-09-30",
  "finding_ids": ["sha256-finding-id"]
}
```

Apply it explicitly:

```bash
python scripts/static_quality.py update --exception path/to/exception.json
```

The expiry must be in the future. Expired exceptions fail CI. On pull requests,
CI also compares the committed baseline with the base commit and rejects added
entries that do not carry a valid exception. The initial W1 baseline is the
only bootstrap and is identified by its source commit.

`correctness_handoffs.md` is generated with the baseline. It assigns
correctness-class debt to Lanes B, C, and D; Lane A does not silently recast
runtime correctness findings as hygiene.

## Integration qualification and CI trust

The A1-I qualification rebased the ratchet onto integration source
`8441bef2f2024fd6c2ec01784708512222382471` and retained the original W1
diagnostic baseline unchanged: 399 total findings, 377 active and 22
vendored/generated. Python 3.12.7 and every version in `toolchain.json` matched
the pinned environment.

`tests/test_static_quality_ratchet.py` now exercises the transition contract
without editing real `qitos` files, reading real Git history, or racing the
wall clock. It covers new and stale findings, base-ref growth, valid and
expired itemized exceptions, non-W1 bootstrap rejection, diagnostic parse
failures, source-debt versus rules-upgrade reporting, and explicit baseline
shrink/growth updates.

Task 08E repository-side workflow roles and commands are recorded in
`docs/internal/ci-job-ownership.md`. `tests/test_workflow_contracts.py` rejects
the invalid GitHub changed-file expression, masked commands, automatic reruns,
missing pytest/docs paths, bilingual documentation drift, and accidental
collapse of the stable and full-package gates. The table describes repository
intent only; it does not infer GitHub branch-protection settings.
