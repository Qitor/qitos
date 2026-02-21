# QitOS Full Project Documentation

## 1. Product Goal
QitOS is a modular agent framework for research and fast workflow prototyping.

Primary goals:
- Build new agent ideas quickly.
- Keep execution behavior inspectable and reproducible.
- Compose policies/tools/memory/search/critics without rewriting kernel internals.

---

## 2. Canonical Architecture
QitOS is organized around one kernel model:

- `AgentModule`: user-defined agent interface.
- `Decision`: strict decision contract.
- `ToolRegistry` + `ToolSet`: unified tool execution model.
- `Runtime` and `FSMEngine`: canonical orchestration layers.
- `TraceWriter` + schema validator: reproducible run artifacts.
- `ReplaySession` + Inspector payloads: stepwise debugging.

Core principle:
- strategy logic in policy/agent methods,
- orchestration logic in runtime/engine,
- capability logic in tools/toolsets,
- observability in trace + inspector.

---

## 3. Repository Layout

- `qitos/core`: core contracts (`Decision`, `Policy`, parser/search/critic interfaces, tools, state).
- `qitos/runtime`: policy-first runtime orchestrator.
- `qitos/engine`: state-machine engine for `AgentModule` runs.
- `qitos/memory`: canonical memory adapter contracts + baseline implementations.
- `qitos/trace`: trace models, writer, schema validator.
- `qitos/debug`: replay and inspector helpers.
- `qitos/presets`: composable preset registry and baseline presets.
- `qitos/release`: release hardening checks and report generation.
- `templates`: reference agents (ReAct, PlanAct, Voyager, SWE).
- `benchmarks`: smoke benchmark runners for templates.
- `docs`: project architecture and operational docs.

---

## 4. Core Interfaces

### 4.1 `Decision`
Path: `qitos/core/decision.py`

Decision modes:
- `act`: execute actions.
- `final`: finish run.
- `wait`: continue without action.
- `branch`: branch/search decision.

Validation guarantees:
- `act` requires actions.
- `final` requires final answer.
- `branch` requires candidate decisions.
- `meta` must be a dict.

### 4.2 `AgentModule`
Path: `qitos/core/agent_module.py`

Required methods:
- `init_state(task, **kwargs)`
- `observe(state, env_view)`
- `decide(state, observation)`
- `reduce(state, observation, decision, action_results)`

Convenience:
- `agent.run(...)` for direct execution.
- `agent.build_engine(...)` for explicit engine composition.

### 4.3 `Policy`
Path: `qitos/core/policy.py`

Policy contract:
- `prepare(state, context)`
- `propose(state, obs) -> Decision`
- `update(state, obs, decision, results) -> state`
- `finalize(state)`

This supports policy-first experiments via `Runtime`.

### 4.4 `ToolRegistry` and `ToolSet`
Paths:
- `qitos/core/tool_registry.py`
- `qitos/core/toolset.py`

Supported registration modes:
- plain function tools (`register`).
- grouped tool packs (`register_toolset`).
- decorated methods (`include`).

ToolSet lifecycle:
- `setup(context)` before run execution.
- `teardown(context)` after run completion/failure.

### 4.5 Parsers, Search, Critics
Paths:
- `qitos/core/parser.py`
- `qitos/core/search.py`
- `qitos/core/critic.py`

These are plug-in interfaces to support:
- model output parsing variations,
- tree-style search strategies,
- verifier-guided runtime control.

### 4.6 Memory Adapter
Paths:
- `qitos/memory/adapter.py`
- `qitos/memory/adapters.py`

Canonical memory API:
- `append(record)`
- `retrieve(query)`
- `summarize(max_items)`
- `evict()`

Baseline implementations:
- `WindowMemory`
- `SummaryMemory`
- `VectorMemory`

---

## 5. Execution Layers

### 5.1 `Runtime` (policy-first)
Path: `qitos/runtime/runtime.py`

Responsibilities:
- observation build
- decision normalize/validate
- branch selection (selector or search adapter)
- action execution
- state update
- critic evaluation
- stop criteria evaluation
- tool lifecycle events
- trace emission

### 5.2 `FSMEngine` (agent-module-first)
Path: `qitos/engine/fsm_engine.py`

Responsibilities:
- explicit phase machine for AgentModule runs
- validation gates
- recovery policy handling
- budget enforcement
- memory append hooks
- trace event/step writing

---

## 6. Trace and Reproducibility

Primary artifacts per run:
- `manifest.json`
- `events.jsonl`
- `steps.jsonl`

Trace schema validation path:
- `qitos/trace/schema.py`
- enforced on finalize by `TraceWriter` (strict mode default)

Manifest includes reproducibility fields:
- `model_id`
- `prompt_hash`
- `tool_versions`
- `seed`
- `run_config_hash`

Step-level observability includes:
- decision payload
- actions
- action results
- `tool_invocations`
- `critic_outputs`
- state diff

---

## 7. Debugging and Inspection

Replay API:
- `ReplaySession` (`qitos/debug/replay.py`)

Inspector API:
- `build_inspector_payload(...)`
- `compare_steps(...)`
- schema defined in `docs/inspector_schema.md`

Inspector payload guarantees:
- decision rationale
- tool invocations + provenance
- action outputs
- critic outputs
- state diff
- stop reason
- remediation hint (when derivable)

---

## 8. Preset Ecosystem

Path: `qitos/presets`

Preset families:
- policies
- parsers
- memories
- search
- critics
- toolkits

Registry entrypoint:
- `build_registry()`

Composition matrix:
- `docs/presets.md`

---

## 9. Templates and Benchmarks

Templates:
- `templates/react`
- `templates/plan_act`
- `templates/voyager`
- `templates/swe_agent`

Benchmarks:
- `benchmarks/react_eval.py`
- `benchmarks/plan_act_eval.py`
- `benchmarks/voyager_eval.py`
- `benchmarks/swe_mini_eval.py`

SWE/Voyager benchmarks can emit trace artifacts for reproducibility checks.

---

## 10. Release Hardening

Release check module:
- `qitos/release/checks.py`

Checks include:
- architecture consistency
- template contract compliance
- trace schema smoke
- benchmark smoke

Readiness report output:
- `reports/release_readiness.md`

Operational doc:
- `docs/release_hardening.md`

---

## 11. Current Canonical Public API (Top-Level)

From `qitos`:
- Core: `AgentModule`, `Decision`, `Policy`, parser/search/critic interfaces.
- Tooling: `ToolRegistry`, `tool`, `ToolSet`.
- Runtime/Engine: `Runtime`, `FSMEngine`, budgets and criteria.
- Memory: `MemoryAdapter`, `MemoryRecord`, baseline memories.
- Trace/Debug: `TraceWriter`, `TraceSchemaValidator`, replay/inspector helpers.
- Presets/Release: preset registry builder and release checks.

---

## 12. Minimal Usage Patterns

### 12.1 Quick agent run
1. Implement `AgentModule` methods.
2. Register tools into `ToolRegistry`.
3. Call `agent.run(task, ...)`.

### 12.2 Policy-first runtime experiment
1. Implement `Policy`.
2. Compose `Runtime(policy=..., toolkit=..., parser/search/critics/criteria as needed)`.
3. Execute `runtime.run(state)`.

### 12.3 ToolSet-based domain extension
1. Implement a class with `name/version/setup/teardown/tools`.
2. Register via `ToolRegistry.register_toolset(...)`.
3. Call tools by namespaced action names.

---

## 13. What Was Removed
The project has removed the obsolete legacy stack and obsolete docs to keep one coherent release path.

Removed categories:
- old documentation branches not aligned with current kernel.
- deprecated execution path modules and legacy CLI path modules.
- obsolete tests for removed legacy execution stack.

---

## 14. Maintenance Guidance

For future additions:
- add new capabilities via contracts, not alternate kernels.
- keep trace schema backward-safe and explicitly validated.
- keep presets pure/composable (no hidden global state).
- add benchmark + replay coverage for new template families.

