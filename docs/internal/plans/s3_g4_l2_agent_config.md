# S3 G4-L2 canonical AgentConfig and live qualification plan

Status: implementation and all 16 offline gates passed; live qualification pending
Updated: 2026-09-01
Owner: G4 integration owner
Fixed integration source: `851f7902f15da670e72f4c04d7453cf37201aee7`
Candidate starting head: `bd0f93328ccb37b66e62855de8ad489916c47e1e`

## Objective

Make one strict declarative `AgentConfig` the launch authority for CLI and
Python execution, prove it with deterministic fake-provider and real Docker
qualification, then run the bounded three-provider live matrix and promote only
if every gate passes.

Architecture decision and pre-implementation census:
[s3_g4_l2_agent_config_adr.md](s3_g4_l2_agent_config_adr.md).

## Execution ledger

- [x] Fetch remote state and verify the integration repository, candidate
  worktree, branches, exact commits, merge base, cleanliness, and divergence.
- [x] Read all mandated architecture/runtime/session/sandbox/config/live
  qualification material and the two external reference implementations.
- [x] Record the exact-source census and accept the one-composition-root ADR.
- [x] Implement strict canonical schema, typed failures, deterministic
  secret-free serialization/digests, and explicit compatibility receipts.
- [x] Implement typed credential references and local-file, fake, and explicit
  environment-compatibility resolvers.
- [x] Extend the existing builder into the sole model/tool/environment/runtime/
  session/trace composition path and add thin `qit run --config` dispatch.
- [x] Migrate all nine model-bearing official YAML templates; record the three
  credential-free templates and remaining Python/docs migration backlog.
- [x] Replace the live runner's Markdown/environment/manual-attestation truth
  with multi-config loading, configured resolvers, executable sandbox receipts,
  real workflow results, and source/digest validation.
- [x] Add the hardened Docker qualification harness and prove the same `Env`
  owns every model-visible read/grep/edit/test operation without host fallback.
- [x] Run the sixteen offline gates, including fake-provider single/parallel/
  continuation and clean-process single/multi-agent restore paths.
- [x] Create private launch files with safe ownership/modes, validate local
  credential authority without disclosing values. The bounded live provider/
  workflow qualification remains pending.
- [ ] Update architecture/product docs, changelog, README, evidence, summary,
  and exact digests; run focused, full, static, package, diff, secret, source,
  and remote stability gates.
- [ ] If and only if every gate passes, fast-forward the integration branch,
  revalidate, push, verify exact remote identity, and remove the five completed
  source worktrees.

## Offline gate order

1. Strict parser and schema defaults.
2. Unknown-field and type rejection.
3. Canonical serialization/digest stability.
4. Credential non-disclosure and local-file security policy.
5. Explicit environment compatibility failure/warning receipts.
6. Fake resolver and fake provider preflight.
7. Fake single-step model execution.
8. Fake native tool execution through the configured `Env`.
9. Fake parallel tool execution.
10. Fake continuation behavior.
11. Clean-process single-agent session restore and credential re-resolution.
12. Clean-process multi-agent/work-graph restore and credential re-resolution.
13. Real hardened Docker creation and inspect attestation.
14. Real Docker tool/read-write-test/denial/repository-digest probes.
15. Source, config, policy, runner, evidence, and cleanup digest binding.
16. Fake provider plus sandbox reaches typed `G4_LIVE=passed`.

## Current boundary

Until the ledger is complete, the branch is an unpromoted candidate. Existing
trace-v1/qita behavior remains unchanged, no Task 14 completeness claim is
made, and no provider request or worktree cleanup is authorized.
