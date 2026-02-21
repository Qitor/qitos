# SWE-Agent Mini Template Notes

## Core loop
1. Inspect target file.
2. Apply focused patch.
3. Run validation command.
4. Submit result when tests pass.

## Mapping in QitOS v2
- `decide` drives fixed phases: `view -> edit -> test -> submit`.
- `reduce` stores observations and advances phase state.
- Uses editor and shell tools to emulate code-repair workflow.

## Scope
Minimal deterministic patch scenario for local regression tests.
