# 06 Memory and Reflection

## Memory Options

Canonical adapters live in `/Users/morinop/coding/yoga_framework/qitos/kit/memory`:
- `WindowMemory`
- `SummaryMemory`
- `VectorMemory`
 - `MarkdownFileMemory`

In current layout, concrete memory implementations are in:
- `/Users/morinop/coding/yoga_framework/qitos/kit/memory`

Use memory to store reusable records from observation/decision/action results.

## Reflection Pattern (Voyager-style)

1. Execute action.
2. Reflect on outcome in `reduce`.
3. Store reflection artifact in memory or skill library.
4. Retrieve relevant artifacts in next `observe`.

Reference:
- `/Users/morinop/coding/yoga_framework/templates/voyager/agent.py`

## Practical Guidance

- Keep reflection concise and structured (task, action, outcome, reuse condition).
- Store retrieval tags for domain/tool/task-type.
- Avoid unbounded growth: summarize/evict periodically.

## Experiment Ideas

- No memory vs episodic memory vs skill memory.
- Reflection every step vs reflection-on-failure only.
- Different retrieval top-k on success rate and token cost.
