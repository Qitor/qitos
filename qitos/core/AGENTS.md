# qitos/core/ AGENTS.md

Contract layer of the framework. Root rules apply; this file adds core-specific constraints.

## Purpose

Define the stable agent-execution vocabulary every other package builds on: `AgentModule`, `StateSchema` (+ field reducers/channels), `Decision`, `Action`, `BaseTool`/`FunctionTool`/`ToolRegistry`, `Task`/`TaskBudget`/`TaskResult`, `Memory`, `History`, `Env` + capability ABCs, `Observation`/`ToolResult`/`ModelResponse`, errors/`StopReason`, `AgentSpec`/`AgentRegistry`, `SharedMemory`, multimodal types, `RunSpec`/`ExperimentSpec`.

## Owns / Does Not Own

- Owns: abstract contracts, canonical data types, schema/serialization helpers for state and tools.
- Does NOT own: runtime mechanics (engine), concrete implementations (kit), provider knowledge (models), parsing strategies for specific vendors (kit/parser + protocols), benchmark semantics.

## Public Surface

Prefer importing from `qitos.core.<module>` (or the root `qitos` package for the ~40 kernel symbols). Internal helpers (`_json_repair`, private registries) are not contract.

## Allowed / Forbidden Dependencies

- Allowed: `qitos.protocols`, `qitos.prompting` (both stdlib-only leaves).
- Forbidden: engine, kit, models, harness, benchmark, recipes, trace, tracing, render, periphery — **at module level absolutely; lazily only inside the existing `AgentModule.run()` convenience path and `AgentSpec` tool factories** (`agent_module.py`, `agent_spec.py`). Those lazy imports (engine/kit/trace/render/harness) are recorded debt D2 — do not add more and do not copy the pattern elsewhere.
- `core` has no third-party dependencies. Keep it that way (the lazy `openai` import in `errors.py` is debt D16, not a precedent).

## Invariants

- Zero third-party imports at module level; stdlib + typing only.
- Data types are serializable and schema-versioned (`StateSchema` + `StateMigrationRegistry`, `core/state.py`); state has exactly one canonical representation per agent.
- Tool contract: `execute(args, runtime_context)` is canonical; `run(...)` only routes to it for compat.
- `Decision.mode` vocabulary (`act`/`final`/`wait`/`handoff`/`branch`) is closed — engine validates against a whitelist.
- Breaking changes to exported types require a root `AGENTS.md`-level decision (public contract, guarded by `tests/test_public_surface.py`, `tests/core/`).

## Extension Points

New contracts belong here only if they are implementation-neutral and needed by ≥2 packages; otherwise put the ABC where its implementations live and keep core out of it.

## Testing

`tests/core/` (decorators, registry, reducers, schema generation, retry policy, shared memory, tool migration guards). If you touch `AgentModule`/`Decision`/`Action`/tool contracts also run `tests/test_engine_core_flow.py`, `tests/test_engine_protocol.py`, `tests/engine/`.

## Common Mistakes

- Adding a lazy import of engine/kit to "make the convenience API nicer" — grows debt D2.
- Putting provider- or benchmark-specific types here (fails the domain-neutrality test).
- Duplicating an existing abstraction (check `tool.py`, `observation.py`, `spec.py` before inventing parallel dataclasses).
