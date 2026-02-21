# ReAct Template Notes

## Source idea
ReAct combines reasoning traces with tool actions in an interleaved loop:
1. Think about next step.
2. Call tool if needed.
3. Observe tool result.
4. Repeat until final answer.

## Mapping in QitOS v2
- `observe`: expose task + current scratchpad.
- `decide`: return `Decision.act(...)` for tool calls, or `Decision.final(...)`.
- `reduce`: append observation/action result to state scratchpad.

## Scope in this template
This template focuses on a deterministic arithmetic ReAct baseline so behavior is fully reproducible.
