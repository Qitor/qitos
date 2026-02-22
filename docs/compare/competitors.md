# QitOS vs LangChain, Langflow, Dify

## Scope of this comparison

This page compares framework design trade-offs for agent development, not vendor quality.

## High-level comparison

| Dimension | QitOS | LangChain | Langflow | Dify |
|---|---|---|---|---|
| Primary orientation | Agent runtime kernel | General LLM framework | Visual flow orchestration | LLM app platform |
| Mainline architecture | Single (`AgentModule + Engine`) | Multiple stacks/components | Node/flow-first | App/pipeline-first |
| Runtime phase visibility | High | Medium | Medium-low | Medium-low |
| Research reproducibility posture | High | Medium | Low-medium | Medium (product logs first) |
| Low-code friendliness | Low | Medium | High | High |
| Best fit | Agent research + advanced builders | Broad ecosystem integration | Rapid visual prototyping | Team-facing productization |

## Practical differences

## QitOS advantages

1. Lower conceptual branching in core API.
2. Better phase-level debugging for agent behavior.
3. Easier controlled comparisons between strategy variants.
4. Explicit env capability mapping reduces hidden backend coupling.

## LangChain advantages

1. Large ecosystem and integration coverage.
2. Rich set of abstractions for varied app architectures.

## Langflow advantages

1. Faster visual assembly for flow-style prototypes.
2. Better for users who prefer drag-and-drop over code-first iteration.

## Dify advantages

1. Strong app-level workflows and deployment ergonomics.
2. Better fit for product teams prioritizing operational UI workflows.

## How to decide

Choose QitOS when:

1. You need to publish/compare agent methods rigorously.
2. You need one explicit runtime contract for many agent variants.
3. You want a smaller, more predictable core architecture.

Choose alternatives when:

1. Your priority is low-code product assembly speed.
2. You need a broader built-in integration marketplace immediately.

## Source Index

- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [qitos/core/env.py](https://github.com/Qitor/qitos/blob/main/qitos/core/env.py)
- [qitos/trace/schema.py](https://github.com/Qitor/qitos/blob/main/qitos/trace/schema.py)
- [examples/patterns/react.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/react.py)
