# Researcher Docs & Tutorials

This track is designed for researchers who want to build new agent ideas quickly, compare behaviors, and debug runs rigorously.

## Who This Is For

- You want to prototype a new agent behavior with minimal boilerplate.
- You need reproducible traces for analysis and paper figures.
- You want a clean path from classic patterns (ReAct/PlanAct) to new policies (tree search, reflection, verifier-guided loops).

## Learning Path

1. [Quickstart: Build and run your first agent](./tutorials/01_quickstart.md)
2. [Core mental model (State, Decision, AgentModule, Engine)](./tutorials/02_core_mental_model.md)
3. [Tools and ToolSets (function tools, class toolsets, lifecycle)](./tutorials/03_tools_and_toolsets.md)
4. [From ReAct to PlanAct with minimal code diffs](./tutorials/04_react_to_planact.md)
5. [Add search-style behavior (branch decisions)](./tutorials/05_branching_and_search.md)
6. [Memory and reflection loops](./tutorials/06_memory_and_reflection.md)
7. [Trace, replay, and inspector workflow](./tutorials/07_trace_replay_inspector.md)
8. [Benchmark and regression workflow for research iteration](./tutorials/08_benchmarks_and_regression.md)
9. [Template authoring guide (publish reusable agents)](./tutorials/09_template_authoring_guide.md)
10. [FAQ for researcher workflows](./tutorials/10_faq.md)

## Design Principles of This Tutorial Series

- Start with `agent.run(...)`, then expose deeper controls only when needed.
- Every new capability maps to one extension point, not runtime rewrites.
- Every tutorial ends with a reproducibility/debugging checkpoint.

## Related Technical Specs

- `/Users/morinop/coding/yoga_framework/PRD.md`
- `/Users/morinop/coding/yoga_framework/docs/PROJECT_FULL_DOC.md`
- `/Users/morinop/coding/yoga_framework/docs/kernel_scope.md`
- `/Users/morinop/coding/yoga_framework/docs/kernel_invariants.md`
- `/Users/morinop/coding/yoga_framework/docs/agent_engine_governance.md`
- `/Users/morinop/coding/yoga_framework/docs/kit.md`
- `/Users/morinop/coding/yoga_framework/examples/README.md`
