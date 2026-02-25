# ReAct Example Walkthrough (Text Protocol)

## What this agent is

`examples/patterns/react.py` is a minimal but practical ReAct agent:

- one tool call per step
- text output protocol (`Thought:` / `Action:` / `Final Answer:`)
- Engine does the model call when `decide(...) -> None`

## Core idea

ReAct is “think-act-reduce” in a loop. In QitOS terms:

- `prepare` selects the minimal context for this step
- `decide` delegates to Engine’s model path
- `reduce` writes the trajectory back into state (for future steps and for trace)

## Method-by-method design

### `__init__`: tools + parser are part of the contract

Design principle:

- The agent’s tool surface must be explicit and enumerable.

What the example does:

- registers `EditorToolSet` (file edit ops) and `RunCommand` (verification)
- attaches `ReActTextParser` so Engine can parse LLM output into `Decision`

### `init_state`: keep state small and bounded

Design principle:

- State is the single source of truth, but should stay bounded.

What the example does:

- stores `scratchpad` for the last N steps
- sets `max_steps` for reproducibility

### `prepare`: give the model only what it needs

Design principle:

- Observation is “policy input”, not a dump of state.

What the example does:

- returns task + recent scratchpad only
- truncates to avoid unbounded prompt growth

### `build_system_prompt`: enforce the output protocol

Design principle:

- Parser correctness depends on prompt correctness.

What the example does:

- includes tool schema
- enforces “exactly one tool call per step”
- specifies ReAct output format

### `prepare`: convert observation into user text

Design principle:

- `prepare` is where you control prompt shape without building chat messages.

What the example does:

- adds step counter
- includes recent trajectory lines

### `decide`: `None` means Engine owns the LLM call

Design principle:

- Returning `None` keeps the LLM wiring stable across agents.

What the example does:

- returns `None` always
- Engine constructs messages and calls `llm(messages)` then `parser.parse(...)`

### `reduce`: create a durable trajectory

Design principle:

- If you cannot reconstruct what happened from state + trace, the agent is not research-grade.

What the example does:

- appends `Thought/Action/Observation` lines to `scratchpad`
- truncates `scratchpad` to remain bounded

## What to modify to create “a new agent”

1. Change the output protocol:
   - swap parser (e.g. JSON/XML)
   - update system prompt to match
2. Change “what the agent can do”:
   - register a different toolset
3. Change the policy:
   - keep `decide -> None` and change prompt/prepare, or
   - implement custom deterministic `decide`

## Source Index

- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [qitos/kit/parser/react_parser.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/parser/react_parser.py)
- [qitos/core/tool_registry.py](https://github.com/Qitor/qitos/blob/main/qitos/core/tool_registry.py)
