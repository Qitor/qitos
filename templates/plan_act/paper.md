# Plan-and-Act Template Notes

## Source idea
Plan-and-Act first produces a multi-step plan, then executes each step while updating progress.

## Mapping in QitOS
- `observe`: include plan status and last observation.
- `decide`: if no plan, generate plan; else execute current step via tools.
- `reduce`: update plan cursor and completion state.

## Scope in this template
This template provides a deterministic arithmetic multi-step baseline to validate planning-state transitions.
