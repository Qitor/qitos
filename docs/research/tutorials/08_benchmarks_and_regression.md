# 08 Benchmarks and Regression

## Goal

Turn every agent idea into a reproducible experiment with a pass/fail gate.

## Built-in Entry Points

- `/Users/morinop/coding/yoga_framework/examples/react_agent.py`
- `/Users/morinop/coding/yoga_framework/examples/planact_agent.py`
- `/Users/morinop/coding/yoga_framework/examples/swe_agent.py`
- `/Users/morinop/coding/yoga_framework/examples/voyager_agent.py`

## Suggested Research Loop

1. Pick a baseline template.
2. Define a small benchmark taskset.
3. Run baseline and save traces.
4. Apply one policy change.
5. Re-run and compare:
   - success rate
   - step count
   - cost/tokens
   - error categories
   - stop reasons
6. Keep only changes that improve target metrics without severe regressions.

## Release Gate

Use release checks before sharing a template publicly:

```bash
pytest -q
python examples/dynamic_tree_planning_agent.py --task "compute 20 + 22 then * 2"
```

Reference:
- `/Users/morinop/coding/yoga_framework/docs/release_hardening.md`
