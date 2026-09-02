# Change Guide — where a change belongs

Task-oriented navigation for coding agents. Pattern: locate the owning module, extend through its extension point, avoid the listed traps, run the listed tests.
Boundary rules behind this table: [module-boundaries.md](module-boundaries.md). Deep dives: [architecture-audit.md](architecture-audit.md).

## Tools

**Add a tool**
→ Inspect `qitos/core/tool.py` (contract) and a sibling in `qitos/kit/tool/<domain>/`.
→ Implement `execute(args, runtime_context)`; register via `qitos.core.function_tool_decorator.function_tool` or subclass `BaseTool`.
→ Compose into a registry through `qitos/kit/toolset/<scenario>.py`; expose new presets via `qitos.kit.toolset`.
→ Avoid: overriding `run()` (compat path); constructing tools inside engine; security-sensitive tools outside `kit/tool/experimental/security_research` (guarded by `tests/test_experimental_boundary.py`).
→ Tests: `tests/core/`, `tests/kit/tool/`, `tests/test_tool_registry_and_toolset.py`, `tests/test_predefined_atomic_tools.py`.

**Add a toolset preset**
→ `qitos/kit/toolset/` builder + export from `qitos.kit.toolset`; update `qitos/kit/__init__.py` lazy exports only if user-facing.
→ Tests: `tests/test_examples_smoke.py`.

**Add MCP server support / bridge behavior**
→ `qitos/mcp/` (server ABC, transports, `schema_convert`, `bridge.mcp_server_to_function_tools`).
→ Engine wiring already exists (`Engine._connect_mcp_servers`); do not add new engine imports of mcp.
→ Tests: `tests/mcp/`.

## Models and protocols

**Add a model provider**
→ Subclass `Model`/`AsyncModel` in `qitos/models/<provider>.py`, register with `@ModelFactory.register`.
→ Provider-specific request shaping stays in `qitos/models/` (see `_openai_responses.py` for the pattern). Never let provider names/types reach `qitos.core` or `qitos.engine` (current exception: `core/errors.py` openai classification, debt D16).
→ Tests: `tests/test_model_providers.py`, `tests/test_openai_responses.py`, `tests/test_engine_protocol.py`.

**Add/change a model family preset**
→ `qitos/harness/_presets.py` (`FamilyPreset`). Presets feed `models/profile_registry.py`, `models/context_registry.py`, engine defaults, and `qit bench --preset`.
→ Avoid editing `cli.py` preset lists (they must source from harness; debt D13).
→ Tests: `tests/test_harness_presets.py`, `tests/test_domestic_model_harness.py`, `tests/test_model_context_registry.py`.

**Add a parser / output protocol**
→ Protocol definition + renderer: `qitos/protocols.py` (`_protocol_table`). Text parsers: `qitos/kit/parser/` (shared salvage in `parser_utils.py`, low-level repair in `core/_json_repair.py`).
→ Native tool-call handling is engine-side (`engine/_model_runtime.py`); prefer protocol-level changes over new engine branches.
→ Tests: `tests/test_model_protocols.py`, `tests/test_engine_protocol.py`, `tests/test_memory_and_parser_and_critic.py`.

## Agent and kernel

**Add/change declarative Agent launch configuration**
→ Evolve the single `qitos.config.AgentConfig` and strict `qitos.agent`
loader in place; compose through `build_agent_composition`. Keep `qit run` a
thin dispatch and reuse `ModelFactory`, `ToolRegistry`, `Env`,
`RuntimeComposition`, checkpoint stores, `AgentModule`, and `Engine`.
→ Credentials are `CredentialRef` values. Resolver implementations belong in
`qitos/config/credentials.py`; providers must never open credential stores.
Canonical and diagnostic views must remain secret-free, deterministic, and
digest-bound. Environment resolution is compatibility-only and missing values
fail closed.
→ Avoid: parallel `V2`/`Legacy` config types, YAML in core, provider-specific
launch runners, runtime client objects in config, or Engine reverse-dependencies
on the loader.
→ Tests: `tests/test_yaml_config.py`, `tests/test_agent_credentials.py`,
`tests/test_config_security.py`, `tests/test_s3_live_qualification.py`, and CLI
governance tests.

**Change agent lifecycle / execution semantics**
→ `qitos/engine/engine.py` `Engine.run()` loop + the `_*.py` runtime mixins; stop logic in `engine/stop_criteria.py` + `_control_runtime.py`.
→ Read `qitos/engine/AGENTS.md` first — lazy-import conventions and mixin protocol are load-bearing.
→ Avoid: adding new kit/benchmark imports (even lazy); changing hook payload shapes without updating `_trace_runtime` and docs.
→ Tests: `tests/test_engine_core_flow.py`, `tests/engine/`, `tests/test_stop_criteria.py`, `tests/test_runtime_recovery.py`.

**Change context construction / prompts**
→ Framework sections: `qitos/prompting.py`; assembly: `core/agent_module.py` `build_prompt_spec`; history policies: `core/history.py` + `kit/history/` (compaction in `kit/history/compact_history.py`, engine entry `_control_runtime.py`).
→ Note: v0.7 conversation kernel (`docs/v4/02`) will replace ad-hoc assembly — align new work with that design.
→ Tests: `tests/test_kit_planning_prompts_state.py`, `tests/test_compact_history.py`, `tests/test_engine_protocol.py`.

**Add a critic / stop criterion / hook**
→ Critics: implement engine critic contract, examples in `kit/critic/`. Stop criteria: `engine/stop_criteria.py`. Hooks: `engine/hooks.py` `EngineHook`.
→ Tests: `tests/engine/test_critic_decorator.py`, `tests/test_critic_patch_lifecycle.py`, `tests/test_stop_criteria.py`, `tests/test_engine_hooks.py`.

**Add memory**
→ Contract `core/memory.py`; implementations `kit/memory/`; cross-agent blackboard `core/shared_memory.py`. Do not add a second state representation.
→ Tests: `tests/test_memory_and_parser_and_critic.py`, `tests/core/test_shared_memory_formal.py`.

**Add/change an environment**
→ Capabilities `core/env.py`; implementations `kit/env/` (host/repo/docker/tmux/desktop); engine constructs by `EnvSpec.type` in `engine/_env_runtime.py` — new env types must be registered there (accepted coupling until D3 is resolved).
→ Tests: `tests/test_env_contract.py`, `tests/test_env_host_and_engine_interpretation.py`, `tests/test_task_and_engine_env.py`.

**Multi-agent / handoff**
→ `core/agent_spec.py` (`AgentSpec`/`AgentRegistry`), `engine/_handoff_runtime.py`, tools `kit/tool/{delegate,fanout,handoff_tool}.py`; scope guard: `docs/internal/plans/v0.7_handoff_scope.md`.
→ Durable ownership, child work, spawn/join, and process recovery follow `docs/v4/13-durable-multi-agent-work-graph.md`; do not extend the in-process helpers as a second protocol.
→ Tests: `tests/test_handoff.py`, `tests/engine/test_handoff_context.py`, `tests/test_delegate_tool.py`, `tests/test_fanout_tool.py`.

## Observability

**Change trace/trajectory output**
→ v1 artifacts (frozen contract): `qitos/trace/writer.py` + `schema.py`. Consumers: qita, benchmark runners, `evaluate/base.py load_run_artifacts`, `hf/`.
→ v2 spans: `qitos/tracing/` (processors console/JSON/W&B/MLflow). Do not point qita at `.traces/` until the data-plane task (v4/05) lands.
→ Tests: `tests/tracing/`, `tests/test_engine_result_traces.py`, `tests/test_qita_cli.py`.

**Change qita (board/replay/export)**
→ `qitos/qita/_cli_app.py` (single module; split opportunistically). Reads only v1 artifacts. `fork` uses `qitos/debug` (deprecated — do not extend that dependency).
→ Tests: `tests/test_qita_cli.py`.

**Change checkpointing / interrupts**
→ `qitos/checkpoint/` (v2 stores; v1 `checkpoint.py` is deprecated), engine side `engine/engine.py` (`_save_checkpoint_if_needed`, `resume_from_checkpoint`) + `engine/interrupt.py`.
→ Durable session identity, safe pause, fresh-process restore, and fork follow `docs/v4/12-session-runtime-and-persistence.md`; checkpoint v2 remains the single persistence mechanism.
→ Avoid: new v1 CheckpointManager usage (experiment still does — debt D10).
→ Tests: `tests/checkpoint/`, `tests/test_checkpoint.py`, `tests/engine/test_interrupt.py`, `tests/e2e/test_checkpoint_resume.py`.

## Benchmarks, recipes, experiments

**Add/fix a benchmark**
→ New home: `qitos/recipes/benchmarks/<name>.py` + `eval_configs/*.yaml`. Legacy `qitos/benchmark/<name>/` is deprecated — port rather than extend.
→ Contracts: `benchmark/base.py` adapter + `core/spec.py` `BenchmarkRunResult`. Scorers implement `metric` contract (`qitos/metric` + `kit/metric/`), evaluators the `evaluate` contract.
→ Never put benchmark vocabulary into core/engine/kit (neutrality test in root `AGENTS.md`).
→ Tests: `tests/test_benchmark_*.py`, `tests/test_cybench_evaluate_metric.py`, `tests/test_evaluate_metric.py`, e2e under `tests/e2e/`.

**Add a method recipe / template**
→ Canonical implementation: `qitos/recipes/<method>/`. Teaching template: `templates/<method>/` (agent.py + config.yaml + paper.md). Keep both in sync; recipes is the source of truth.
→ Tests: `tests/test_reflexion.py`, `tests/test_lats.py`, `tests/test_moa.py`, `tests/test_self_refine.py`, `tests/test_magentic_one.py`, `tests/test_examples_policy.py`.

**Change experiment runner / sweeps**
→ `qitos/experiment/` + `qitos/config/` (YAML). Uses cache/checkpoint — check deprecation notes (D10).
→ Tests: `tests/test_experiment.py`.

**Change CLI**
→ `qitos/cli.py` (`qit`) — thin dispatch only; implementation stays in the owning package; benchmark lists and presets must not be inlined (D13).
→ Tests: `tests/test_cli_governance.py`, `tests/test_qit_demo_cli.py`, `tests/test_cli_new.py`.

## Repository-level

**Examples / docs / templates policy** → root `AGENTS.md` and `ARCHITECTURE.md` (examples are product surface; docs EN/zh aligned; changelog+README news updated with every meaningful change).
**Packaging** → `setup.py` (+ `docs/internal/plans/dependency_audit.md`); run `python -m build` + `twine check`.
**Architecture changes** → update `docs/architecture/*` and the allowlist in `tests/test_architecture_boundaries.py` in the same change.
