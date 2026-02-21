# Release Hardening

QitOS currently uses repository tests and architecture checks as release hardening gates.

Checks:

- Architecture consistency (single kernel, expected package layout)
- Template contract compliance
- Trace schema smoke validation
- Example smoke runs
- Test suite pass (`pytest`)

Recommended commands:

```bash
pytest -q
python examples/dynamic_tree_planning_agent.py --task "compute 20 + 22 then * 2"
```
