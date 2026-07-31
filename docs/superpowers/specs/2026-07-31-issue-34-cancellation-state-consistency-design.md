# Issue #34 Cancellation State Consistency Design

## Problem

When the synchronous Engine observes an immediate cancellation request, it emits an
`END` event with `stop_reason="cancelled_immediate"` and exits the loop. It does not
apply the same reason to the canonical `StateSchema`. Final `TaskResult`,
`EngineResult`, and trace-manifest data are subsequently derived from the unchanged
state, so the same run is reported as both cancelled and normally completed.

## Scope

This change covers only an immediate cancellation after the Engine has observed the
cancel token. It does not attempt to interrupt an in-flight model request and does
not repair the separate `after_step` cancellation/checkpoint defect.

## Design

1. Add `StopReason.CANCELLED_IMMEDIATE` with the stable string value
   `"cancelled_immediate"` so cancellation can pass the existing state-validation
   contract.
2. In the immediate-cancellation branch, call
   `state.set_stop(StopReason.CANCELLED_IMMEDIATE)` before emitting the terminal
   event. Build the event payload from `state.stop_reason` rather than maintaining a
   second literal.
3. Finalize a cancelled trace manifest with `status="stopped"`. Qita already treats
   `stopped` as a terminal manifest status, while `completed` is treated as a normal
   completion. Preserve the exact cancellation mode in
   `manifest.summary.stop_reason`.

No new result fields or trace-writer APIs are needed. `TaskResult` and
`EngineResult` already consume the canonical state, and `TaskResult.success` already
evaluates unknown non-success reasons as false.

## Regression Test

Use a deterministic lifecycle hook to request immediate cancellation after the
first complete step. The regression must assert that:

- the END event reports `cancelled_immediate`;
- final state and task result report `cancelled_immediate`;
- task success is false and final result remains absent;
- trace manifest status is `stopped`;
- trace manifest summary reports `cancelled_immediate`.

The test must not use sleeps or timing races.

## Compatibility

Normal success, budget, validation, interrupt, and unrecoverable-error paths retain
their current state and manifest behavior. The new enum member is additive. Existing
consumers that inspect `state.stop_reason` gain a non-null terminal reason; consumers
that inspect manifest status see an already-supported terminal status.
