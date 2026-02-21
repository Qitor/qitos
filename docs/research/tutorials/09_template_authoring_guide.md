# 09 Template Authoring Guide

## Template Contract

A reusable template should include:

1. `agent.py`
2. `config.yaml`
3. `paper.md` (design intent + claims)
4. minimal runnable example or benchmark hook

See existing structure under `/Users/morinop/coding/yoga_framework/templates`.

## Authoring Rules

- Keep agent policy deterministic by default for tests.
- Put domain capabilities in ToolSet(s), not in policy code.
- Expose knobs in config (budget, retrieval top-k, critic toggles).
- Emit traces by default in evaluation scripts.

## Template Quality Checklist

- Can a new user run it in <10 minutes?
- Can they replace tools without rewriting core policy?
- Can they compare two runs with traces only?
- Is there at least one regression test for core behavior?

## Good First Templates to Copy

- `/Users/morinop/coding/yoga_framework/templates/react`
- `/Users/morinop/coding/yoga_framework/templates/plan_act`
- `/Users/morinop/coding/yoga_framework/templates/voyager`
- `/Users/morinop/coding/yoga_framework/templates/swe_agent`
