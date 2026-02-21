# Kernel Invariants

These constraints are non-negotiable for the framework.

1. Single orchestrator path
- All execution must go through canonical `Engine` semantics.

2. Decision validation at engine boundary
- Every `Decision` returned by policy or parser is validated before execution.

3. Tool invocation through registry only
- Tools are executed only via `ToolRegistry`.

4. Trace-first execution
- Runs must emit schema-valid trace artifacts and stop reason.

5. Strategy/engine separation
- `AgentModule` defines strategy; `Engine` controls orchestration.

6. Stable public naming
- Public APIs must use canonical names (`AgentModule`, `Decision`, `Engine`, `ToolRegistry`, `ToolSet`).
