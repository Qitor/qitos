# Kernel Scope

QitOS ships one kernel architecture:

- `AgentModule`: user-facing agent interface (`init_state/observe/decide/reduce/run`).
- `Decision`: validated decision schema consumed by runtime.
- `Policy`: strategy interface (`prepare/propose/update/finalize`).
- `Runtime`: canonical orchestrator loop and lifecycle owner.
- `ToolRegistry`: single tool execution registry for functions and ToolSets.
- `Trace`: mandatory run artifacts (`manifest.json`, `events.jsonl`, `steps.jsonl`).

## Responsibility Boundaries

- Agent design logic belongs to `Policy` and `AgentModule` methods.
- Scheduling, stop criteria, recovery, and execution ordering belong to `Runtime`.
- Tool registration/invocation/lifecycle belongs to `ToolRegistry`.
- Reproducibility and inspection data belong to `Trace`.

## Out of Scope for Kernel

- Alternative runtime semantics.
- Template-specific execution loops.
- Hidden side-channel tool execution.
