# 10 FAQ

## Should I start with `agent.run(...)` or explicit `Engine` wiring?

Start with `agent.run(...)` for idea validation. Move to explicit `Engine` wiring when you need custom critics, search adapters, or trace plumbing.

## How do I move from PlanAct to tree-style reasoning?

Keep your state/tool layer unchanged. Change `decide` to output `Decision.branch(...)` candidates and plug in selection/search logic.

## Do I need to rewrite the engine for a new agent paper idea?

No. Most ideas should be implemented in state, `decide`/`reduce`, parser, critic, or search adapter.

## Can tools be plain Python functions?

Yes. `ToolRegistry.register(function)` is first-class.

## Can tools be class-based and environment-configured?

Yes. Use a ToolSet class with `setup`, `teardown`, and `tools()`.

## How do I debug a failure quickly?

Write traces, replay the run, inspect state diffs and decision rationale, then classify failure category before changing prompts/agent logic.

## What is the minimum to publish a reproducible template?

- one deterministic baseline config
- one benchmark script
- trace artifacts for baseline runs
- clear paper/design note (`paper.md`)
