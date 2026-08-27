# qitos/kit/ AGENTS.md

Implementation layer. Root rules apply; this file adds kit-specific constraints.

## Purpose

Curated, swappable implementations over the kernel: tools (`tool/`), toolset presets (`toolset/`), parsers (`parser/`), prompts (`prompts/`), memory (`memory/`), history (`history/`), planning (`planning/`), critics (`critic/`), envs (`env/`), permissions (`permission/`), interceptors (`interceptor/`), embeddings/vectorstores/search, multi-agent patterns (`patterns/`), REPL (`repl/`), skills (`skill/`), evaluate/metric implementations.

## Owns / Does Not Own

- Owns: concrete behavior. Contracts live in `qitos.core` (+ `qitos.evaluate`/`qitos.metric`); runtime mechanics in `qitos.engine`.
- Does NOT own: benchmark specifics (the three `cybench.py` files here are debt D6, migration target `recipes.benchmarks`), agent-execution semantics, trace artifact format.

## Public Surface

Three import layers (README contract): `qitos.kit` (curated top), `qitos.kit.toolset` (scenario presets like `coding_tools`), `qitos.kit.tool.<domain>` (atomic). `kit/__init__.py` keeps top-level py files to `__init__.py` only (guarded by `tests/test_architecture_layout.py`); implementation bodies live in subpackages (`tool/internal/` for the big coding suite).

## Allowed / Forbidden Dependencies

- Allowed: `qitos.core`, `qitos.engine`, `qitos.models`, `qitos.protocols`, `qitos.prompting`, `qitos.evaluate`, `qitos.metric`, `qitos.trace` (tools that observe runs: delegate/fanout).
- Forbidden: `qitos.benchmark` (current `kit/evaluate/cybench.py:9` import is debt V5 — port to recipes), `qitos.recipes`, periphery, and **`from qitos import ...`** root self-import (two files remain, debt V6 — import `qitos.core.x` directly).

## Invariants

- Tools implement `execute(args, runtime_context)`; `run()` is compat routing only (`qitos/core/tool.py` owns the contract).
- Toolsets compose through `ToolRegistry`; list-first composition (`include_toolset([...])`) is the canonical authoring path.
- Security-sensitive tools live ONLY under `tool/experimental/security_research/`, opt-in, never in `kit/__init__`, `qitos.__init__`, demos, or quickstart (guarded by `tests/test_experimental_boundary.py`, `tests/test_public_surface.py`). Deprecated top-level shims (`tool/network_toolset.py`, `web_test_toolset.py`, `security_audit.py`) must keep their `DeprecationWarning`.
- Env implementations consume env ops / capability contracts; no direct host-filesystem assumptions beyond what the env contract grants.
- Kit stays domain-neutral: if a module's vocabulary is benchmark- or product-specific it belongs in `qitos.recipes` or the zoo.

## Extension Points

New tool domain → `tool/<domain>/` + toolset builder in `toolset/`; new parser → `parser/` + protocol registration in `qitos.protocols`; new memory/history/critic/env → implement the `qitos.core` contract here; interceptor → `core/interceptor.py` contract.

## Testing

`tests/kit/` (+ `tests/kit/tool/`, `tests/kit/interceptor/`), `tests/test_tool_registry_and_toolset.py`, `tests/test_predefined_atomic_tools.py`, `tests/test_memory_and_parser_and_critic.py`, `tests/test_env_contract.py`, `tests/test_permission_pipeline.py`. Tool-contract changes also require `tests/core/test_coding_function_tool_migration.py` (all tools are `FunctionTool`, destructive ops need approval).

## Common Mistakes

- Re-implementing an abstraction that exists (check `qitos/kit/parser/parser_utils.py` for JSON salvage, `qitos/core/_json_repair.py` for control-char repair, `qitos/kit/critic/` before adding critics — `self_reflection.py` vs `react_self_reflection.py` near-duplicate is the cautionary tale).
- Importing `qitos.benchmark` or `qitos.recipes` from kit.
- Skipping toolset registration (tool exists but isn't composable through `ToolRegistry`).
- Moving experimental security tools into default exports or shims without warnings.
