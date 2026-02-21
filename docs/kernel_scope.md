# Kernel Scope

QitOS ships one kernel architecture:

- `AgentModule`: user-facing agent interface (`init_state/observe/decide/reduce/run`).
- `Decision`: validated decision schema consumed by engine.
- `Engine`: canonical orchestrator loop and lifecycle owner.
- `ToolRegistry`: single tool execution registry for functions and ToolSets.
- `Trace`: mandatory run artifacts (`manifest.json`, `events.jsonl`, `steps.jsonl`).

## Responsibility Boundaries

- Agent design logic belongs to `AgentModule` methods.
- Scheduling, stop criteria, recovery, and execution ordering belong to `Engine`.
- Tool registration/invocation/lifecycle belongs to `ToolRegistry`.
- Reproducibility and inspection data belong to `Trace`.

## Out of Scope for Kernel

- Alternative engine semantics.
- Template-specific execution loops.
- Hidden side-channel tool execution.
