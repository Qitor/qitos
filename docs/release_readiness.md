# Release Readiness

## Goal

Ensure QitOS can be published as a reliable framework, not just a working repo.

## P0 must pass

1. Core contracts documented and frozen.
2. Examples runnable and aligned with docs.
3. Hook payload schema stable and tested.
4. Trace schema stable and tested.
5. Public API exports audited for leakage.

## P1 should pass

1. Tutorial docs complete for researchers and builders.
2. Comparison page reviewed for factual, non-hype language.
3. `qita` board/replay docs available with screenshots.
4. Regression taskset script available.

## Release checklist template

| Item | Owner | Status | Evidence |
|---|---|---|---|
| API freeze |  |  |  |
| Hook schema |  |  |  |
| Trace schema |  |  |  |
| Examples validated |  |  |  |
| Docs build success |  |  |  |

## Final go/no-go questions

1. Can a new user run a tutorial end-to-end in under 15 minutes?
2. Can a researcher reproduce one pattern and compare two variants in under 1 day?
3. Can failures be diagnosed from trace artifacts without rerunning blindly?

## Source Index

- [PRD.md](https://github.com/Qitor/qitos/blob/main/PRD.md)
- [plans.md](https://github.com/Qitor/qitos/blob/main/plans.md)
- [qitos/__init__.py](https://github.com/Qitor/qitos/blob/main/qitos/__init__.py)
- [qitos/engine/__init__.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/__init__.py)
- [tests/test_p0_freeze_guards.py](https://github.com/Qitor/qitos/blob/main/tests/test_p0_freeze_guards.py)
