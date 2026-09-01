# G4-L3 stable config, sandbox, and live-workflow evidence

Status: full offline gate passed; new live round pending
Updated: 2026-09-01
Fixed baseline: `851f7902f15da670e72f4c04d7453cf37201aee7`
Candidate branch: `codex/v4-s3-g4-convergence`
Starting candidate: `113af7088943c95e682601b8f40ad84bbc09dd1b`

## Evidence boundary

This is a new G4-L3 ledger. It does not edit, extend, or reinterpret the
G4-L2 live failure in `s3_g4_live_qualification_evidence.md`,
`s3_g4_live_qualification_summary.json`, or
`s3_g4_live_workflow_failure_receipt.json`. The new live runner must allocate a
fresh round ID. No result from the old request ledger counts toward L3.

No live provider request is authorized until every required offline repository,
package, configured-workflow, privacy, credential-permission, Docker
attestation, and cleanup gate passes on committed candidate bytes.

## Implemented closure

| Requirement | Candidate evidence |
|---|---|
| Stable config | canonical `qitos.agent`; isolated reader for `qitos.agent/v1`; deeply immutable normalized data; deterministic secret/path-free digest |
| Digest binding | launch receipt, runtime provenance, Session snapshot, restore comparison, and Trajectory records carry the config digest |
| Request parity | resolved protocol owns parser; RequestView, codec, provider projection, tool schema/choice, reasoning, continuation, and parser use one path |
| Tool policy | `auto`, `required_for_next_decision`, `required_before_final`, and `disabled`; premature final and missing native capability are typed failures |
| Sandbox truth | structural backend protocol; inspect-backed Docker reference; explicit `unsafe_host`; no Docker-to-host fallback; cleanup proof |
| Credentials | logical references only; local resolver requires file `0600` and directories with no group/world permissions; no container injection |
| Trajectory/qita | configured EventSink plus real runtime and durable WorkGraph facts; reader and qita consume the Trajectory store, not harness JSON |
| Offline workflow | canonical YAML -> configured AgentModule/Engine -> Docker -> native parallel tools -> edit/test -> safe pause -> fresh-process restore -> final -> Trajectory/qita -> cleanup |
| Multi-agent recovery | existing authoritative 40-round process-loss suite now publishes real Trajectory facts rather than fabricated candidate records |

## Offline qualification receipt

- required focused repository matrix: `424 passed`;
- full fixed-Python 3.12.7 suite: `2393 passed, 50 skipped` in 329.89 seconds;
- configured single-agent Docker clean-process recovery: passed;
- authoritative multi-agent process-loss: 40 independent rounds passed;
- static quality ratchet: passed with 367 baselined findings (345 active, 22
  vendored/generated), with no new baseline debt;
- stable flake8: passed; stable mypy: 93 source files, no issues;
- package build: `qitos-0.6.0.tar.gz` and wheel built; twine passed both;
- interface/architecture/no-local-path/diff checks: passed;
- credential file/directory permissions: exact `0600`/`0700`;
- modified/untracked source privacy scan: credential values, live endpoints,
  local launch paths, and private home paths absent; and
- no L3 live provider request was issued during any offline check.

The runner's own 16-node offline subprocess is rerun after these bytes are
committed, before live mode is enabled.

## New live round contract

The runner consumes the three local, untracked `qitos.agent` launch configs and
the one private local credential resolver. Shared limits are temperature `0`,
`max_tokens=10240`, timeout `180`, retries `0`, and at most 12 requests per
profile. Provider requests remain host-side; tools run in the attested Docker
environment.

Execution is strictly sequential:

1. GLM (`sii-glm-5-2`, `GLM-5.2-w4a8c8`) must complete the configured coding,
   pause, fresh-process restore, final, Trajectory, qita, privacy, and cleanup
   workflow.
2. Only after GLM passes, DSV (`sii-dsv4`, `dsv4-flash-0731`) must prove the
   same provider-neutral Engine route and restore workflow.
3. Only after DSV passes, Qwen (`sii-qwen3-8-27b`, `Qwen3.8-27B`) must prove
   ordinary text and a typed native-tool capability loss with no false tool
   success.

Primary failure stops the round immediately. It cannot be hidden with added
requests, reruns, prompt switching, or another provider. A failure preserves
the candidate and blocks promotion, push, and every worktree removal.

## Current decision

```text
CONFIG_ARCHITECTURE=candidate_passed
SANDBOX_TRUTH=candidate_passed
ENGINE_REQUEST_PARITY=candidate_passed
OFFLINE_AGENT_RECOVERY=candidate_passed
OFFLINE_MULTI_AGENT=candidate_passed
FULL_OFFLINE_GATE=passed
LIVE_SINGLE_AGENT=not_started
LIVE_RESTORE=not_started
LIVE_PROVIDER_PARITY=not_started
LIVE_MULTI_AGENT=not_started
LIVE_TRAJECTORY=not_started
QITA_LIVE_READ=not_started
G4_LIVE=not_started
S3_STATUS=open_l3_qualification
S4_READY=false
DEFAULT_BRANCH_READY=false
RELEASE_READY=false
```
