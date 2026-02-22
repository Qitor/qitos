# Practical Coding Agent Walkthrough (ReAct + Self-Reflection + memory.md)

## What this agent is

`examples/real/coding_agent.py` is a “realistic minimal” coding agent:

- ReAct-style tool execution (`ReActTextParser`)
- persistent local memory (`MarkdownFileMemory` writes `memory.md`)
- Engine-level critic (`ReActSelfReflectionCritic`) that can request retries

It is designed to be a tutorial for building a “shippable” agent:

- bounded state
- explicit verification
- reproducible traces

## Core design choices

1. **State contains trajectory**, not hidden global variables.
2. **Verification is a first-class tool call**, not narrative text.
3. **Self-reflection is a Critic**, not extra prompt tokens sprinkled randomly.
4. **Memory is owned by Engine**, not the agent (agent only chooses what to surface/consume).

## Method-by-method design

### `CodingState`: store only what you need to drive actions

Fields:

- `scratchpad`: trajectory breadcrumbs
- `target_file`: makes tool calls deterministic
- `test_command`: enforces a “proof of fix”
- `expected_snippet`: a minimal acceptance check

### `__init__`: tools and parser define the executable surface

What it wires:

- `EditorToolSet` (view/replace_lines/insert/etc.)
- `RunCommand` (verification)
- `ReActTextParser` for text-protocol decisions

### `build_memory_query`: control the *memory view* shown in `env_view`

This example returns:

```python
{"format": "records", "max_items": 12}
```

Design principle:

- the agent should not see unbounded memory; keep it bounded and inspectable.

Important nuance:

- this query shapes `env_view["memory"]` (the memory context view)

### `observe`: publish task, constraints, and memory view

What it exposes:

- file/test constraints
- bounded scratchpad
- `env_view["memory"]` so the agent can “see” a summary/records

### `build_system_prompt`: enforce one-action-per-step and verification discipline

This prompt is intentionally strict:

- one tool call per step
- inspect before editing
- run verification frequently
- stop only with “what changed + proof”

### `prepare`: inject just enough context for consistent steps

It composes:

- task + file + expected snippet + verification command
- step counters
- optional memory summary (if present)
- recent trajectory

Design principle:

- keep it short but *decision-sufficient*.

### `reduce`: treat tool outputs as evidence

The reducer:

- logs thought/action/observation into scratchpad
- sets `final_result` only after verification succeeded (`returncode == 0`)

Design principle:

- “done” should be a function of tool evidence, not model confidence.

## Engine wiring (why it matters)

This example passes into `Engine(...)`:

- `memory=MarkdownFileMemory(path=".../memory.md")`
- `critics=[ReActSelfReflectionCritic(max_retries=2)]`
- `env=HostEnv(workspace_root=...)`
- `trace_writer=...` (optional)

That’s the core “builder stack” in QitOS:

- Env provides execution backend
- Memory provides context persistence
- Critic adds controlled retries
- Trace makes it debuggable and comparable

## Source Index

- [examples/real/coding_agent.py](https://github.com/Qitor/qitos/blob/main/examples/real/coding_agent.py)
- [qitos/kit/memory/markdown_file_memory.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/memory/markdown_file_memory.py)
- [qitos/kit/critic/react_self_reflection.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/critic/react_self_reflection.py)
- [qitos/kit/parser/react_parser.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/parser/react_parser.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
