# AgentModule + Engine Governance

## Objective
Keep one public execution mainline for all framework usage:
- `AgentModule + Engine`

## Scope
Applies to:
- core API exports
- templates
- benchmarks
- examples
- docs
- release checks

## Mandatory Rules
1. User strategy must live in `AgentModule` subclasses.
2. Orchestration must be performed by `Engine` (directly or via `agent.run`).
3. New features must be added as Engine plugins/kits, not alternate runtimes.
4. No public API should present a second execution abstraction.

## Template Enforcement
Each template must:
- provide `agent.py`, `config.yaml`, `paper.md`, `__init__.py`
- define at least one `AgentModule` subclass
- avoid `Policy` as execution entry
- run via `Engine` or `agent.run`

## Example Enforcement
Each example must:
- use real model integration through `qitos.models`
- use env-based credentials/config
- avoid hard-coded API keys
- produce reproducible run behavior (bounded `max_steps`)

## Migration Discipline
Any PR touching core orchestration must include:
- trace compatibility verification
- release checks passing
- docs updated to reflect Agent+Engine-only story
