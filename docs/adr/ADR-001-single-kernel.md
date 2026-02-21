# ADR-001: Single-Kernel Architecture

## Status
Accepted

## Context
The project needs high research velocity and stable reproducibility. Multiple execution paths and versioned API families increase maintenance cost and reduce predictability.

## Decision
Adopt one kernel architecture for first public release:

- `AgentModule`
- `Decision`
- `Policy`
- `Runtime`
- `ToolRegistry` / `ToolSet`
- `Trace`

No parallel runtime architecture is part of public product scope.

## Consequences

### Positive
- Clear mental model for users.
- Lower maintenance burden.
- Better reproducibility and debugging consistency.

### Negative
- New features must be designed as plugins/extensions, not alternative kernels.

## Enforcement
- CI checks for trace schema and canonical API usage in templates/tests.
- Docs and examples must reference canonical names only.
