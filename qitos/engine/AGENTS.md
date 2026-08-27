# qitos/engine/ AGENTS.md

Execution kernel. Root rules apply; this file adds engine-specific constraints.

## Purpose

Own the runtime: the `Engine` loop (`observe -> decide -> act -> reduce -> critic -> check_stop`), hook dispatch, stop criteria, recovery/compact, cancellation, interrupts/resume, checkpoints integration, handoffs, single-step/session APIs, `AsyncEngine`, and `ActionExecutor`.

## Owns

- `engine/engine.py` `Engine` (public orchestrator) + runtime mixins `_model_runtime` / `_action_runtime` / `_env_runtime` / `_control_runtime` / `_handoff_runtime` / `_trace_runtime` / `_control_runtime`, coordinated through `engine/_protocol.py` `_EngineProtocol`.
- `action_executor.py` (validation, permissions, concurrency, retry, approval, interceptors), `hooks.py` (`EngineHook`), `stop_criteria.py`, `recovery.py`, `cancellation.py`, `interrupt.py`, `states.py` (`RuntimeEvent`/`StepRecord`/`RunState`), `parser.py` (Parser protocol), `events.py` (`EngineEvent` stream), `async_engine.py`.

## Does Not Own

- Tool implementations, envs, parsers, prompts, model providers, trace storage format (owns only the event emission), benchmark/recipe semantics.

## Allowed / Forbidden Dependencies

- Allowed module-level: `qitos.core`, `qitos.protocols`, `qitos.models` (profile/base), `qitos.harness`, `qitos.checkpoint`, `qitos.trace`, `qitos.tracing`.
- Forbidden: `qitos.kit`, `qitos.mcp`, `qitos.cache`, `qitos.benchmark`, `qitos.recipes`, periphery. **The existing lazy (function-level) imports of kit/mcp/cache in `engine.py`, `_env_runtime.py`, `_control_runtime.py` are legacy debt D3/V3 — never promote them to module level (import cycle with kit) and never add new ones.**
- Protocol resolution chain order (explicit protocol > agent.model_protocol > parser inference > llm.qitos_protocol > harness metadata > model-profile default) is contract; change it only with tests.

## Invariants

- One canonical loop: all agent execution — including `final` decisions and multi-agent handoffs — passes through reduce/critic/check_stop phases; no side channels that skip lifecycle hooks.
- Every phase boundary dispatches hooks and emits `RuntimeEvent`s with `run_id`/`step_id`/`phase`; trace clarity and stop-reason auditability must not degrade (`_trace_runtime.dispatch_hook` currently swallows hook errors — D12; don't add new silent-failure paths).
- Cancellation, budget exhaustion, and recovery must always leave a consistent `EngineResult` with a valid `StopReason` (see `tests/engine/test_cancellation.py`).
- Checkpoint/resume round-trips `RunState` through `qitos.checkpoint` v2; schema changes to `states.py` need serialization-version handling (`tests/engine/test_run_state.py`).
- Engine constructor surface is public API; new options need docs + tests and preferably flow through `EngineConfig`.

## Extension Points

`EngineHook` (lifecycle + tool-level callbacks), stop criteria (register in `stop_criteria.py`), critics (engine critic contract, impls in `kit/critic`), `Parser` protocol, recovery handlers/`RecoveryPolicy`, `Env` capability checks, env type registration in `_env_runtime.py` (accepted coupling until D3).

## Testing

`tests/engine/` (concurrency, cancellation, interrupt, approval, critics, handoff context, run-state serialization, streaming) plus loop-level tests at `tests/test_engine_core_flow.py`, `test_engine_hooks.py`, `test_stop_criteria.py`, `test_runtime_recovery.py`, `test_engine_protocol.py`. Engine edits always run these.

## Common Mistakes

- Promoting a lazy kit/mcp import to module level → `ImportError` cycle at `import qitos`.
- Bypassing `ActionExecutor` to call tools directly from mixins.
- Adding provider-specific response handling here instead of `qitos/models` or a parser.
- Emitting events without run/step/phase context, breaking qita replay.
