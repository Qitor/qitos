# Tree-of-Thought Example Walkthrough (Branch + Search Selection)

## What this agent is

`examples/patterns/tot.py` implements a Tree-of-Thought-style loop:

- the model proposes multiple candidate next actions (“thoughts”)
- the agent converts them into `Decision.branch(candidates=[...])`
- the Engine selects a candidate (via `Search` or a default selector)

This is the minimal QitOS pattern that demonstrates **branching semantics**.

## Core idea

ToT is not “one prompt”. It is a **search policy**:

1. expand candidates (multiple thoughts)
2. score them
3. prune
4. select one to execute

In QitOS terms:

- candidate generation lives in `AgentModule.decide(...)`
- candidate selection lives in `Engine` via `Search` (if provided)

## Method-by-method design

### State: evidence accumulation matters more than scratchpad

Design principle:

- In ToT, you are searching for evidence, not just “taking actions”.

What the example does:

- stores `evidence` snippets from EPUB operations
- uses evidence as the context for the next thought expansion

### `decide`: return `Decision.branch(...)`

Design principle:

- Branching must be explicit and typed, otherwise you cannot plug search.

What the example does:

- step 0 bootstraps with a deterministic action (`epub.list_chapters`)
- later steps call LLM to propose a JSON structure:
  - list of thoughts, each has `idea`, `score`, and tool action
- converts each thought into `Decision.act(...)` and returns `Decision.branch(...)`

### Engine wiring: attach a `Search` implementation

The example passes:

```python
engine_kwargs = {"search": DynamicTreeSearch(top_k=2), ...}
```

Design principle:

- Search policy should be swappable without rewriting the agent.

What `DynamicTreeSearch` does (conceptually):

- keeps top-K candidates
- uses per-candidate scores (from decision meta) to choose one

### `reduce`: evidence is the invariant

Design principle:

- ToT “progress” is evidence quality, not cursor increments.

What the example does:

- extracts `hits[].snippet` or `content` from EPUB tool results
- appends snippets to evidence, keeping it bounded

## How to evolve this into a real research ToT

1. Separate expand vs score:
   - let model propose candidates, but have a verifier score them
2. Add backtracking:
   - if pruning removes everything, call `Search.backtrack(state)`
3. Track a tree explicitly:
   - store nodes/edges in state and expose them in trace

## Source Index

- [examples/patterns/tot.py](https://github.com/Qitor/qitos/blob/main/examples/patterns/tot.py)
- [qitos/core/decision.py](https://github.com/Qitor/qitos/blob/main/qitos/core/decision.py)
- [qitos/engine/search.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/search.py)
- [qitos/kit/planning/dynamic_tree_search.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/planning/dynamic_tree_search.py)
