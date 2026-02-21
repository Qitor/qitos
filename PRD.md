# QitOS PRD (Public Release)

## 1. Product Intent
QitOS is a single-kernel agent framework for research and fast iteration.

Primary promise:
- Implement new agent ideas quickly.
- Keep behavior inspectable and reproducible.
- Compare runs and strategies with stable contracts.

## 2. Single Kernel Rule
The only execution mainline is:
- `AgentModule + Engine + Trace`

There is no parallel runtime model and no alternative execution abstraction in public API.

## 3. User Goals
1. New user can run an agent with `agent.run(...)` quickly.
2. Research user can swap parser/search/critic/memory without rewriting kernel.
3. Template author can publish reproducible benchmarks and traces.

## 4. Core Interfaces

### 4.1 AgentModule
User strategy surface:
- `init_state(task, **kwargs)`
- `observe(state, env_view)`
- `decide(state, observation)`
- `reduce(state, observation, decision, action_results)`

Optional hooks:
- `build_system_prompt`
- `prepare`
- `build_memory_query`
- `should_stop`

### 4.2 Engine
Orchestration owner:
- phase loop
- action execution
- recovery policy
- stop criteria
- branch decision selection
- critic evaluation
- toolset lifecycle
- trace writing

### 4.3 Decision
Canonical decision modes:
- `act`
- `wait`
- `final`
- `branch`

### 4.4 Tooling
- `ToolRegistry` for function and ToolSet registration.
- `ToolSet` with optional `setup/teardown/tools`.

## 5. Extension Model
Extensions must attach to AgentModule+Engine pipeline:
- parser plugins
- search adapters
- critics
- stop criteria
- memory adapters
- toolkits/skills

No extension may introduce a second orchestrator.

## 6. Repository Structure
- `qitos/core`: contracts and types
- `qitos/engine`: canonical engine
- `qitos/kit`: reusable concrete kits
- `qitos/models`: LLM provider interfaces
- `qitos/trace`: trace artifacts + schema
- `qitos/debug`: replay/inspect
- `templates`: reference agents
- `examples`: runnable LLM-integrated agents
- `tests`: regression and architecture tests
- `docs`: architecture and researcher tutorials

## 7. Template Contract (Mandatory)
Each template must include:
- `agent.py`
- `config.yaml`
- `paper.md`
- `__init__.py`

And must satisfy:
- `agent.py` subclasses `AgentModule`
- runs through `Engine`/`agent.run(...)`

## 8. Trace and Reproducibility
Required artifacts per run:
- `manifest.json`
- `events.jsonl`
- `steps.jsonl`

Minimum reproducibility fields:
- model id
- prompt hash
- tool versions
- seed
- run config hash

## 9. Quality Gates
Quality checks must include:
- template contract checks
- architecture consistency checks (single kernel)
- trace schema validation smoke
- test suite pass

## 10. Release Readiness
Release is ready only if:
1. Docs/templates/examples all present `AgentModule + Engine` as the only mainline.
2. Core templates run on the same Engine.
3. Trace artifacts validate in smoke runs.
4. A failed run is diagnosable through replay + inspector payloads.
