# Practical EPUB Reader Walkthrough (Tree-of-Thought Over Evidence)

## What this agent is

`examples/real/epub_reader_agent.py` is a practical Tree-of-Thought-like reader:

- it treats reading as evidence gathering
- it branches between multiple candidate next actions
- it finishes only when evidence is sufficient to answer the question

It uses:

- `EpubToolSet` (chapter listing/search/reading)
- `Decision.branch(...)` for candidate actions
- optional `DynamicTreeSearch` for selection

## Core design choices

1. **Evidence is the central state**, not “thought text”.
2. **Branching is explicit** via `Decision.branch(...)`.
3. **Bootstrapping is deterministic** (list chapters / keyword probe).
4. **Prompt output is structured JSON** to generate candidates reliably.

## Method-by-method design

### `EpubToTState`: evidence-first state

Key fields:

- `evidence`: bounded snippets from tools
- `thoughts`: bounded rationales for interpretability
- `chapter_count`: derived capability info (helps reduce random actions)

### `decide`: bootstrap, then expand candidates

Step 0:

- return a `Decision.branch(...)` with two deterministic candidates:
  - list chapters
  - search for question keywords

Later steps:

- ask the model for 2-4 candidate “thoughts” as JSON
- convert each candidate into `Decision.act(Action(...), meta={"score": ...})`
- return `Decision.branch(candidates=...)`

### `reduce`: transform tool output into reusable evidence

The reducer:

- extracts chapter catalog hints, search snippets, and chapter text fragments
- keeps evidence bounded (`[-20:]`) to avoid growth

Design principle:

- “progress” in reading is evidence quality, not step count.

## How to extend it into a stronger reader

1. Add a verifier:
   - score candidates by whether they increase evidence diversity (not just relevance)
2. Add a tree recorder:
   - store parent/child edges for each decision id to visualize search
3. Add citation formatting:
   - require final answer to include evidence ids/snippets

## Source Index

- [examples/real/epub_reader_agent.py](https://github.com/Qitor/qitos/blob/main/examples/real/epub_reader_agent.py)
- [qitos/kit/tool/epub.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/tool/epub.py)
- [qitos/kit/planning/dynamic_tree_search.py](https://github.com/Qitor/qitos/blob/main/qitos/kit/planning/dynamic_tree_search.py)
- [qitos/core/decision.py](https://github.com/Qitor/qitos/blob/main/qitos/core/decision.py)
- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
