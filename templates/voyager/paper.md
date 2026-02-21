# Voyager-style Template Notes

## Core loop
1. Execute task with current policy.
2. Reflect on success/failure and derive reusable skill.
3. Insert/update skill into skill library.
4. Reuse skills in future episodes.

## Mapping in QitOS v2
- `reduce` emits reflection entries.
- reflection writes `SkillArtifact` into `InMemorySkillLibrary`.
- next episodes query skill library before deciding actions.

## Scope
Deterministic arithmetic environment for reproducible baseline while preserving reflection+skill-evolution structure.
