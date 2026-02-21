# 02 Core Mental Model

## The Four Core Objects

1. `StateSchema`
   - Persistent run state.
   - Where your plan, memory references, and intermediate results live.

2. `Decision`
   - Output of each step.
   - Modes: `act`, `wait`, `final`, `branch`.

3. `AgentModule`
   - Your research logic surface:
   - `init_state` -> `observe` -> `decide` -> `reduce`.

4. `Engine`
   - Orchestration loop.
   - Handles execution, stopping, recovery, and trace integration.

## Where To Put New Ideas

- New prompting strategy: usually `decide`.
- New state structure: `StateSchema` subclass fields.
- New execution semantics for actions: custom `action_executor` in `build_engine(...)`.
- New stop behavior: `should_stop` or engine stop criteria (when using `Engine`).

## Rule of Thumb

If your new agent idea changes “how to think”, update `decide`.
If it changes “what to remember”, update state fields and `reduce`.
If it changes “how to run”, configure `Engine` kits instead of rewriting agent logic.

## Validation Checklist

- Every `decide` path returns a valid `Decision`.
- `reduce` is deterministic for same input tuple.
- State has explicit fields for anything used by the next step.
