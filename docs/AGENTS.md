# QitOS documentation maintenance

Root AGENTS.md safety, scope and architecture constraints remain authoritative.
This file never relaxes them and does not authorize plugins, deployments or models.

- Use AgentModule, Engine, Session, Run, Snapshot/Checkpoint, WorkItem/Attempt,
  ToolResult, ArtifactRef, Trajectory and historical trace consistently; see glossary.
- Pair EN and zh content in the same change: defaults, commands, dependencies,
  limits, examples and navigation order must agree. Avoid empty translation mirrors.
- One beginner path: install a source identity, qit new, canonical config,
  AgentComposition Session, inspect, restore/extend. Advanced AgentModule.run remains explicit.
- Bind runnable lessons in tutorial-contracts.json to complete standalone examples.
  Label illustrative code and signature references. Never silently skip a runnable
  block because it contains ellipsis. Do not execute arbitrary documentation shell.
- Separate current capabilities, compatibility, historical evidence and future plans.
  A source-bound historical test result is not evidence for a later commit.
- Fake providers prove mechanisms only. No host isolation claim, blanket provider
  compatibility, hard-thread-cancellation, automatic publication or lossless-redaction claim.
- Use task-local pinned documentation dependencies. Run docs/tests/link/MDX checks
  and inspect actual desktop/mobile pages before promotion. No deployment is implied.
