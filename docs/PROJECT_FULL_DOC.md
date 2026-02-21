# QitOS Full Project Documentation

## 1. Product Goal
QitOS is a research-oriented agent framework with one canonical execution path:
- `AgentModule + Engine`

Core goals:
- make new agent ideas fast to implement;
- keep decisions and state transitions inspectable;
- keep runs reproducible with trace artifacts.

## 2. Canonical Architecture
- `AgentModule`: user strategy surface (`init_state`, `observe`, `decide`, `reduce`).
- `Decision`: strict decision contract (`act`, `wait`, `final`, `branch`).
- `Engine`: orchestrates runtime phases, tool execution, recovery, stop checks, critics, search, and tracing.
- `ToolRegistry` / `ToolSet`: register tools and manage lifecycle.
- `TraceWriter`: writes `manifest.json`, `events.jsonl`, `steps.jsonl`.

## 3. Repository Layout
- `qitos/core`: core contracts and data models.
- `qitos/engine`: canonical runtime engine and extensions.
- `qitos/kit`: reusable concrete modules (`memory`, `parser`, `planning`, `tool`, `prompts`, `critic`, `state`).
- `qitos/models`: model provider interfaces and implementations.
- `qitos/trace`: trace schemas and writer.
- `qitos/debug`: replay and inspector helpers.
- `templates`: reference agent templates.
- `examples`: runnable examples with model config loading.
- `tests`: architecture and runtime regression tests.

## 4. Agent + Engine Flow
1. `Engine` initializes state via `AgentModule.init_state`.
2. `Engine` builds `env_view` (budget, metadata, memory context).
3. `AgentModule.observe` returns structured observation.
4. `AgentModule.decide` returns a `Decision` or `None`.
5. If `None`, `Engine` calls LLM with:
   - `AgentModule.build_system_prompt(state)`
   - history from `memory.retrieve_messages(state, observation)`
   - current user message from `AgentModule.prepare(state, observation)`
6. `Engine` executes actions for `Decision.act`.
7. `AgentModule.reduce` updates state.
8. stop criteria, critics, recovery, trace emission run inside `Engine`.

## 5. Extension Points
- Parser: pass `engine_kwargs={"parser": ...}` or set `agent.model_parser`.
- Search: pass `engine_kwargs={"search": ...}` for branch decisions.
- Critic: pass `engine_kwargs={"critics": [...]}`.
- Memory: pass `engine_kwargs={"memory": ...}`.
- Stop criteria: pass `engine_kwargs={"stop_criteria": [...]}`.
- Render hooks: pass `engine_kwargs={"render_hooks": [...]}`.

## 6. Trace and Debug
- Trace fields are validated by `TraceSchemaValidator`.
- Replay and inspector helpers are in `qitos.debug`.
- Standard debugging payload includes decision rationale, tool I/O, critic output, and state diff.

## 7. Design Constraints
- one engine only;
- no parallel orchestration abstraction;
- templates/examples must run through `agent.run(...)` or `Engine`.

## 8. References
- `/Users/morinop/coding/yoga_framework/PRD.md`
- `/Users/morinop/coding/yoga_framework/docs/kernel_scope.md`
- `/Users/morinop/coding/yoga_framework/docs/kernel_invariants.md`
- `/Users/morinop/coding/yoga_framework/docs/agent_engine_governance.md`
- `/Users/morinop/coding/yoga_framework/docs/kit.md`
