# 05 Branching and Search-Style Agents

## When To Use `Decision.branch`

Use `Decision.branch(...)` when your policy generates multiple candidate actions/plans and needs selection logic (tree-of-thought style exploration).

## Pattern

1. In `decide`, create candidate `Decision` objects.
2. Return one `Decision.branch(candidates=[...])`.
3. Let runtime/search adapter or selector choose one candidate.
4. Continue execution with selected candidate.

## Candidate Quality Signals

Put scoring info in `Decision.meta`, for example:
- heuristic score
- uncertainty
- verifier hints
- expected token/tool cost

## Minimal Research Loop

- Start with greedy select.
- Add pruning criteria.
- Add critic/verifier feedback to candidate scoring.
- Compare trace metrics (quality, cost, depth, retries).

## Reference Tests

- `/Users/morinop/coding/yoga_framework/tests/test_kernel_stop_recovery_search_critic.py`
- `/Users/morinop/coding/yoga_framework/tests/test_v3_nextgen_core.py`
