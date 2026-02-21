# Kit Design

`qitos.kit` is not a thin alias layer for skills.
It provides reusable agent-construction blocks used directly in `AgentModule` code.

## What Kits Should Contain

1. Agent building blocks
- message construction
- llm-to-decision adaptation
- plan cursor operations
- state reduce helpers

2. Reusable infra blocks
- parser constructors
- memory constructors
- search adapters
- critics
- toolkit packs

## What Kits Should Not Contain

- alternate execution loops
- second orchestrator abstractions
- standalone policy mainline

## Current High-Value Modules

- `qitos.kit.planning`
  - `ToolAwareMessageBuilder`
  - `LLMDecisionBlock`

- `qitos.kit.planning`
  - `parse_numbered_plan`
  - `PlanCursor`

- `qitos.kit.planning`
  - `append_log`
  - `set_final`
  - `set_if_empty`

These are intended to reduce repetitive code in `decide` and `reduce` implementations.
