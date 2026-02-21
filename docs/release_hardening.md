# Release Hardening

Release hardening checks are implemented in `qitos.release.checks`.

Checks:

- Architecture consistency (canonical export names, no versioned API tokens)
- Template contract compliance
- Trace schema smoke validation
- Benchmark smoke validation

Programmatic usage:

```python
from qitos.release import run_release_checks, write_release_readiness_report

report = run_release_checks()
write_release_readiness_report("reports/release_readiness.md")
```
