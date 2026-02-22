# Practical Computer-Use Agent Walkthrough (JSON Decisions, Web-to-Report)

## What this agent is

`examples/real/computer_use_agent.py` is a web research “computer-use” agent:

- fetch a page
- extract readable text
- write a report file
- finish with a concrete deliverable

It uses a strict **JSON decision protocol** (`JsonDecisionParser`) to reduce tool-call ambiguity.

## Core design choices

1. **Decision protocol is JSON**, not free-form ReAct text.
2. **Workflow is expressed as preferences in system prompt**, not hard-coded branching logic.
3. **State stores a bounded scratchpad** so the model can maintain continuity.
4. **Deliverable is a file**, so termination is tied to an artifact.

## Method-by-method design

### `ComputerUseState`: minimal fields for stable behavior

- `target_url`: the external resource
- `report_file`: the output artifact name
- `scratchpad`: bounded trajectory

### `__init__`: tool surface is explicit

This agent registers:

- `HTTPGet` and `HTMLExtractText` (web evidence pipeline)
- `WriteFile` and `ReadFile` (deliverable pipeline)
- `RunCommand` (optional verification/debug)

### `build_system_prompt`: JSON schema is the real safety rail

Why:

- The most common failure mode in “computer-use” is the model drifting into unparseable tool calls.

This prompt:

- defines the exact JSON schema for act/final/wait
- enforces exactly one action in act mode
- forbids markdown/code fences

### `prepare`: make the current objective explicit

It provides:

- task + URL + report filename
- step counter
- recent trajectory lines

Design principle:

- avoid repeating huge page HTML in prompt; keep evidence flow via tools.

### `reduce`: treat tool outputs as observations, not truth claims

This reducer:

- logs thought/action/observation into scratchpad
- does not “interpret” results as solved; the model must decide when to finalize

## Common upgrades

1. Add a citation format:
   - force the report to cite extracted evidence snippets
2. Add a “done” check:
   - stop only when `report.md` exists and has > N chars
3. Add memory:
   - attach `WindowMemory` or `MarkdownFileMemory` in Engine kwargs

## Source Index

- [examples/real/computer_use_agent.py](https://github.com/Qitor/qitos/blob/main/examples/real/computer_use_agent.py)
- [qitos/kit/parser/json_parser.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/parser/json_parser.py)
- [qitos/kit/tool/web.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/tool/web.py)
- [qitos/kit/tool/file.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/tool/file.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
