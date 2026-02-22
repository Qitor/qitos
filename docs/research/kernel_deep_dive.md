# Kernel Deep Dive

## Goal

Build a precise mental model of how QitOS executes one run, where data flows, and where extension points belong.

## 1) The canonical execution chain

At runtime, one call to `Engine.run(task)` goes through these stages:

1. initialize state (`agent.init_state`)
2. preflight checks (task validity + env capability)
3. per-step loop:
- `observe`
- `decide` (agent custom decision or Engine-driven LLM+parser path)
- `act` (ActionExecutor -> ToolRegistry -> Env ops)
- `reduce`
- `critic` (optional)
- `check_stop`
4. finalize trace + task result

This sequence is intentionally explicit to make agent behavior comparable and debuggable.

## 2) Lifecycle phases (semantic contract)

This section is intentionally **semantic**, not just “what code calls what”.
If you implement new agents, parsers, critics, or env backends, you should align with these meanings.

### Phase: `INIT`

Purpose:

- Start a new run with a stable `run_id`.
- Reset runtime components (`Memory.reset`, recovery policy reset).
- Hydrate trace metadata and emit run-level identity.
- Perform preflight validation (Task validity + Env capability match).

Inputs:

- `task` (string or `Task`)
- agent config (`AgentModule.__init__` + state kwargs)

Outputs:

- initial `StateSchema` from `agent.init_state(...)`

Invariants:

- `state.task` is set.
- tool registry and env are ready before the first `OBSERVE`.

Observability:

- emits `RuntimePhase.INIT` event
- triggers hooks: `on_run_start(...)`

### Phase: `OBSERVE`

Purpose:

- Produce the step-local observation that the policy will act on.

Inputs:

- `state` (single source of truth)
- `env_view` (budget, metadata, env info, and *memory context view*)

Outputs:

- `observation` (agent-defined type)

Guidelines:

- observation should be **bounded** (truncate histories)
- observation is not “everything in state”

Side-effects:

- Engine appends observation to memory as a record (if memory enabled).

Observability:

- emits `RuntimePhase.OBSERVE` events (`start`, `observation_ready`)
- triggers hooks: `on_before_observe`, `on_after_observe`

### Phase: `DECIDE`

Purpose:

- Convert observation into a normalized `Decision` (act/final/wait/branch).

Inputs:

- `state`
- `observation`

Outputs:

- `Decision[Action]` attached to `StepRecord.decision`

Two decision paths:

1. Agent-native decision path:
   - `AgentModule.decide(...) -> Decision`
   - Use this for deterministic or tool-free logic.
2. Engine model decision path:
   - `AgentModule.decide(...) -> None`
   - Engine performs:
     - `prepared = agent.prepare(state, observation)` (string)
     - `system = agent.build_system_prompt(state)` (optional string)
     - `history = memory.retrieve_messages(state, observation, query={})` (if memory provided)
     - `raw_output = agent.llm(messages)`
     - `Decision = parser.parse(raw_output, context={...})`

Important nuance:

- `AgentModule.build_memory_query(...)` currently affects the **`env_view["memory"]` context** shown to the agent,
  but Engine’s model-history retrieval uses `retrieve_messages(..., query={})`.
  Treat `env_view["memory"]` as a *debuggable memory view*, not necessarily the full model context.

Branching:

- If `Decision.mode == "branch"`, Engine selects a candidate:
  - via `Search` (if provided), otherwise via `BranchSelector`

Observability:

- emits `RuntimePhase.DECIDE` events (`start`, `model_input`, `model_output`, `decision_ready`)
- emits error phases on failure: `DECIDE_ERROR`, then `RECOVER`
- triggers hooks: `on_before_decide`, `on_after_decide`

### Phase: `ACT`

Purpose:

- Execute tool actions when `Decision.mode == "act"`.

Inputs:

- `Decision.actions` (normalized `Action(name, args)`)
- `Env` (optional, but required if tools need ops groups)

Outputs:

- `action_results: list[Any]` attached to `StepRecord.action_results`

Execution path:

- `ActionExecutor.execute(...)`
- `ToolRegistry.call(tool_name, args, runtime_context={env, ops, state, ...})`
- Env ops groups are resolved and injected for tools that request them (advanced)

Observability:

- emits `RuntimePhase.ACT` events (`start`, `skipped`, `action_results`)
- emits error phases on failure: `ACT_ERROR`, then `RECOVER`
- triggers hooks: `on_before_act`, `on_after_act`

### Phase: `REDUCE`

Purpose:

- Update state using observation + decision + action results.

Inputs:

- previous `state`
- `observation`
- `Decision`
- `action_results`

Outputs:

- updated state (mutated in place or returned as a new object)
- `state_diff` stored into `StepRecord.state_diff`

Guidelines:

- treat `reduce` as “pure state transition” (avoid doing I/O here)
- always record enough breadcrumbs for debugging (scratchpad, plan cursor, etc.)

Observability:

- emits `RuntimePhase.REDUCE` events (`start`, `state_reduced`)
- triggers hooks: `on_before_reduce`, `on_after_reduce`

### Phase: `CRITIC` (optional)

Purpose:

- Evaluate the step outcome and optionally request retry/stop.

Inputs:

- updated state
- step decision + results

Outputs:

- `"continue" | "retry" | "stop"`

Observability:

- emits `RuntimePhase.CRITIC` events (`start`, `outputs_ready`)
- triggers hooks: `on_before_critic`, `on_after_critic`

### Phase: `CHECK_STOP`

Purpose:

- Decide whether to stop the run, and set standardized stop reason.

Stop sources (in priority order):

1. `Decision.mode == "final"` => `StopReason.FINAL` with `final_answer`
2. `AgentModule.should_stop(state)` => `StopReason.AGENT_CONDITION` (if not already set)
3. `Env.is_terminal(...)` => `StopReason.ENV_TERMINAL`
4. stop criteria (default: FinalResultCriteria) and budgets:
   - `StopReason.BUDGET_STEPS`, `StopReason.BUDGET_TIME`, `StopReason.BUDGET_TOKENS`, etc.

Observability:

- emits `RuntimePhase.CHECK_STOP` events (`start`, `continue`, `stop`)
- triggers hooks: `on_before_check_stop`, `on_after_check_stop`

### Phase: `END`

Purpose:

- Finalize trace artifacts (manifest + summaries) and return `EngineResult`.

Observability:

- emits `RuntimePhase.END` event (with `stop_reason`)
- triggers hooks: `on_run_end(...)`

### Error & recovery phases

When an exception occurs in the step loop, Engine:

1. emits `DECIDE_ERROR` or `ACT_ERROR` depending on where it failed
2. emits `RECOVER`
3. calls `RecoveryPolicy.handle(...)` to decide `continue_run` vs stop

If recovery stops the run, `StopReason.UNRECOVERABLE_ERROR` is used.

## 2) What each core module owns

### `AgentModule`

Owns policy semantics:

- what to observe
- how to decide
- how state changes after action results
- optional stop semantics

### `Engine`

Owns orchestration semantics:

- loop ordering
- budget constraints
- hook dispatch
- event/trace write
- recovery behavior

### `Decision` and `Action`

Own normalized runtime intent:

- whether to act/final/wait
- which tool actions and with what args

### `Env`

Owns backend capabilities:

- provides ops groups (`file`, `process`, ...)
- can be host/docker/repo/etc.

### `Memory`

Owns context retrieval contract:

- retrieve context/messages for model input
- record runtime memory entries

## 3) Two decision paths (important)

### Path A: agent-native decision

`AgentModule.decide(...)` returns `Decision` directly.

Use this when:

- deterministic strategy
- hand-written heuristics
- non-LLM policies

### Path B: Engine model decision

`AgentModule.decide(...)` returns `None`.

Then Engine will:

1. call `agent.prepare(...)`
2. build messages (system prompt + memory + user)
3. call `agent.llm(messages)`
4. parse output into `Decision`

Use this when:

- your policy is LLM-driven
- you need parser-governed output protocols

## 4) Hook/Event contract in practice

Hook contexts and runtime events carry canonical metadata so tools can rely on it:

- `run_id`
- `step_id`
- `phase`
- `ts`
- plus phase payloads

This lets render, debugging tools, and future dashboard backends consume one stable stream.

## 5) Why this design scales for research

1. You can swap parser/memory/critic/env independently.
2. You can compare methods under one fixed runtime semantics.
3. You can replay and inspect failures phase-by-phase.
4. You can publish reproducible traces with model/tool/task fingerprints.

## 6) Common architectural mistakes

1. putting orchestration logic inside Agent methods
2. mixing tool backend assumptions into parser/prompt logic
3. storing critical runtime facts outside `StateSchema`
4. changing multiple strategy axes in one experiment branch

## Source Index

- [qitos/engine/engine.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/engine.py)
- [qitos/core/agent_module.py](https://github.com/Qitor/qitos/blob/main/qitos/core/agent_module.py)
- [qitos/core/state.py](https://github.com/Qitor/qitos/blob/main/qitos/core/state.py)
- [qitos/core/decision.py](https://github.com/Qitor/qitos/blob/main/qitos/core/decision.py)
- [qitos/core/action.py](https://github.com/Qitor/qitos/blob/main/qitos/core/action.py)
- [qitos/core/env.py](https://github.com/Qitor/qitos/blob/main/qitos/core/env.py)
- [qitos/core/memory.py](https://github.com/Qitor/qitos/blob/main/qitos/core/memory.py)
- [qitos/engine/hooks.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/hooks.py)
