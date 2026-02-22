# QitOS Agent Engineering Playbook

This document is the operating contract for any AI coding agent that contributes to QitOS.

## 0. Ultimate Goal

QitOS is being built to become the next-generation agent framework for:

- researchers who need fast, rigorous iteration over new agent ideas,
- super-developers who want full control over detailed agentic scaffolding design,
- teams that want to harness the maximal capability of modern models.

The target quality bar is not “good enough” or “MVP”.
The package must aim to be competitive with world-class open-source Python frameworks such as PyTorch and vLLM in:

- architecture clarity,
- modularity and extensibility,
- performance-minded design,
- developer ergonomics,
- documentation and ecosystem readiness.

Every major design decision should be evaluated against this standard:
Does it move QitOS toward world-class open-source framework quality?

## 1. Product Mission

QitOS is a research-first and builder-friendly agentic framework.
The core goal is:

- make new agent design easy to implement,
- make experiments reproducible,
- keep architecture minimal but extensible.

## 2. Non-Negotiable Architecture Invariants

1. Single mainline only:
- `AgentModule + Engine`
- lifecycle is explicit: `observe -> decide -> act -> reduce -> check_stop`

2. No parallel architecture lines:
- no Runtime-vs-Engine split
- no Policy-vs-Agent dual mainline
- no legacy branches

3. Naming discipline:
- do not introduce names like `V1`, `V2`, `Next`, `Legacy`
- avoid duplicated concepts with new aliases

4. Contracts over hidden behavior:
- core interfaces must stay simple and stable
- behavior differences belong in kit implementations, not core branching

## 3. Package Boundaries

Use these boundaries strictly:

- `qitos.core`: minimal abstract contracts and fundamental data types
- `qitos.engine`: execution kernel mechanics (loop, hooks, validation, recovery, stop, action execution)
- `qitos.kit`: concrete reusable implementations (tool, memory, parser, planning, critic, env helpers, prompts, state helpers)
- `qitos.benchmark`: adapters that convert external benchmarks into `Task`
- `examples`: practical runnable agents and benchmark runners
- `docs`: educational docs for researchers and builders

Rule:
- if code is concrete/replaceable, prefer `qitos.kit`.
- if code is a stable framework contract, keep it in `qitos.core`.

## 4. Interface Design Rules

1. `AgentModule`:
- should be easy to subclass for new research ideas.
- default path should be LLM-friendly and low-boilerplate.

2. `Engine`:
- should orchestrate lifecycle and model/tool/memory wiring.
- must expose hook points for each important phase.

3. `Task`:
- canonical problem package (objective, inputs, resources, constraints, budget, env_spec, metadata).

4. `Env`:
- provides capabilities/ops for execution context.
- tools/actions should consume env ops, not assume host filesystem/process directly.

5. Tools:
- should support both function-style and class-based definitions.
- should remain composable through `ToolRegistry`.

## 5. Observability and Reproducibility Requirements

Every major feature must preserve:

- standardized trace schema
- meaningful hook payloads (`run_id`, `step_id`, `phase`, etc.)
- replayability via `qita`
- clear stop reason and error category

Do not ship changes that reduce trace clarity.

## 6. Benchmark Integration Standard

All benchmark integrations must follow:

1. Benchmark rows -> canonical `Task`
2. Keep raw source fields in metadata when useful
3. Avoid benchmark-specific hacks in core
4. Put benchmark adapters in `qitos.benchmark`
5. Provide at least one runnable example in `examples`

## 7. Example Quality Bar

Examples are product surface, not toy snippets.

Each new example should:

- run end-to-end with real model/tool path
- reflect realistic workload
- be readable and easy to modify
- highlight one clear design pattern

If an example needs credentials:
- use env vars
- never commit secrets

## 8. Docs Quality Bar

Docs must serve two audiences:

- Researchers: principles, extension points, paper reproduction.
- Builders: quick start, integration patterns, operations.

Requirements:

- bilingual quality parity when both languages exist
- each concept page links to concrete source files
- tutorial steps are constructive (build-up), not only command dumps

## 9. Change Safety Checklist (Before Merge)

For every non-trivial change:

1. Run targeted tests for modified areas.
2. Run at least one representative example.
3. Ensure API exports remain coherent.
4. Ensure docs are updated when contracts change.
5. Validate no duplicate abstractions were introduced.

## 10. Anti-Patterns (Do Not Do)

- Reintroducing old architecture tracks for compatibility theater.
- Moving core complexity into hidden magic.
- Adding one-off wrappers that duplicate existing abstractions.
- Expanding API surface without clear composability gain.
- Sacrificing readability for framework cleverness.

## 11. Preferred Decision Heuristic

When uncertain, choose the option that:

1. keeps `AgentModule + Engine` simpler,
2. improves researcher iteration speed,
3. improves traceability/debuggability,
4. preserves modular extension through `qitos.kit`,
5. avoids architecture forks.

---

If a proposal violates this document, revise design before coding.
