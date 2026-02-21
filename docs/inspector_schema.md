# Inspector Schema

Inspector payloads are derived from canonical trace step records.

Required fields per inspector step:

- `step_id`
- `rationale`
- `decision_mode`
- `actions`
- `tool_invocations`
- `action_results`
- `critic_outputs`
- `state_diff`
- `stop_reason`
- `remediation_hint`

Design rules:

- Inspector output must be reconstructable from `manifest.json` + `steps.jsonl`.
- No template-specific inspector payload shape.
- Step comparison uses the same canonical fields.
- Tool lifecycle status is derived from trace events (`toolset_setup_*`, `toolset_teardown_*`).
