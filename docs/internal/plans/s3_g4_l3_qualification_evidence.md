# G4-L3 stable config, sandbox, and live-workflow evidence

Status: deterministic gates passed; live provider transport blocked at request ceiling
Updated: 2026-09-02
Fixed baseline: `851f7902f15da670e72f4c04d7453cf37201aee7`
Candidate branch: `codex/v4-s3-g4-convergence`
Starting candidate: `904df84ff3bd601cef6fae2199d66b3867aeaa1d`

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

The runner's own 16-node offline subprocess passed against committed source
`535b26838231fcac97ac944d88961253f008b7bf` before live mode was enabled.

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

## Live failure receipt

Fresh round `s3-g4-l3-71564b10447bf692` bound source
`535b26838231fcac97ac944d88961253f008b7bf`, runner digest
`8155051f92fa969391609433a9e45f5a501d999d6774518eb3b86f97f85e25d7`,
and evidence digest
`2f9d8b089dfaeb6c04fb82093f86eaa956727bd497b59afc7c82f0dd29963ccc`.
The embedded 16-node offline gate, Docker attestation, cleanup, and privacy scan
passed.

GLM stopped before provider dispatch with zero requests. The observed runtime
failure was `CodecCapabilityError: transport options must be JSON-compatible`:
deeply immutable nested request options still contained a `mappingproxy` at the
provider projection boundary. Engine recovery left the Session running rather
than at the qualification pause, so the outer workflow receipt is
`workflow_single_not_paused`. This is an implementation blocker, not provider
capability evidence.

The primary failure stopped the round. DSV is `not_started` with
`primary_dependency_failed`; Qwen is `not_started` with
`parity_dependency_failed`. All three request ledgers are zero. No rerun,
prompt switch, provider substitution, promotion, push, or worktree removal was
performed. The private machine receipt remains outside Git with mode `0600`;
the sanitized immutable failure record is
`s3_g4_l3_live_failure_receipt.json`.

## Current decision

```text
CONFIG_ARCHITECTURE=candidate_passed
SANDBOX_TRUTH=candidate_passed
ENGINE_REQUEST_PARITY=candidate_passed
OFFLINE_AGENT_RECOVERY=candidate_passed
OFFLINE_MULTI_AGENT=candidate_passed
FULL_OFFLINE_GATE=passed
LIVE_SINGLE_AGENT=failed_before_request
LIVE_RESTORE=not_started
LIVE_PROVIDER_PARITY=not_started
LIVE_MULTI_AGENT=not_started
LIVE_TRAJECTORY=not_started
QITA_LIVE_READ=not_started
G4_LIVE=workflow_single_not_paused
S3_STATUS=blocked_live_qualification
S4_READY=false
DEFAULT_BRANCH_READY=false
RELEASE_READY=false
```

## R1 transport round

Round `s3-g4-l3-1f3414e2567ef3f9`, bound to committed source
`bd9711d58436c008be81f5bd9d1b6af604b762fb`, passed its embedded offline,
Docker, cleanup, and privacy gates and issued six real GLM requests. This proves
that nested immutable request options crossed the repaired JSON transport
boundary. GLM executed native parallel read/grep, wrote the fixture, and ran
two commands, but the local five-step ceiling stopped before a final request.
The qualification image also lacked pytest, and qita's bounded projection
omitted the metadata container for the large live trajectory. DSV and Qwen were
not started and used zero requests. This round is immutable failure evidence,
not provider qualification or promotion authority; its sanitized receipt is
`s3_g4_l3_r1_live_failure_receipt.json`.

Round `s3-g4-l3-d6fa110124a7c660` then issued five GLM requests on source
`c332516b62c30637b6d175bdad7c441418f0561b`. A malformed first response was
successfully recovered into native tools and a final answer, but the runner's
literal-step-zero pause policy missed the first successful post-recovery
boundary, so no restorable pause was recorded. The old runner also reported
`runtime_failure` and printed a local traceback instead of the typed
`malformed_structured_response`. DSV and Qwen again remained at zero requests.
This is immutable lifecycle/diagnostic failure evidence in
`s3_g4_l3_r2_live_failure_receipt.json`, not a GLM capability failure.

Round `s3-g4-l3-08e956825bfb8f0f` issued three GLM requests on source
`0a18fe4f81c8ec174d1e075c8311fd8d4b88d3f6`. The coding Session and the
multi-agent parent both reached safe, persisted pauses, proving the recovered
boundary policy. Fan-out then encountered the deterministic local code
`duplicate_fork_operation`: its fixed qualification operation ID collided with
the same global SQLite idempotency key from an earlier Session. The old receipt
projector exposed only `SessionContractError`; the diagnosis comes from the
typed `SessionErrorCode` and durable fork records. The repair binds operation
IDs to the parent Session and centrally projects enum-valued framework codes.
DSV and Qwen used zero requests. The immutable sanitized receipt is
`s3_g4_l3_r3_live_failure_receipt.json`.

## R4 bounded live result

Committed source `0f1435c79288e33e71f41fcc96f0cbda5aba1ffd`
passed the complete fresh repository matrix (`2415 passed, 50 skipped`) and
all auxiliary quality, package, sandbox, permission, privacy, cleanup, and
fake-transport gates. Immutable round `s3-g4-l3-739e066ca1e8172a` also passed
its embedded 16-node offline gate and Docker attestation.

GLM consumed exactly 12/12 requests. Its configured single-agent workflow
passed source edit, pytest, safe pause, clean-process restore, final,
Trajectory, qita, privacy, and cleanup. The separate multi-agent parent reached
a safe pause and produced two context-transfer receipts. The first restored
child executed real tools but ended after five requests with the typed root
`provider_transport_failure`; the second child and join did not start because
no request budget remained. This is provider/transport-class live evidence,
not a new JSON/config/codec defect. DSV and Qwen remained at zero requests in
the required dependency order. The verified private receipt is mode `0600`,
and the sanitized record is `s3_g4_l3_r4_live_failure_receipt.json`.

```text
CONFIG_ARCHITECTURE=passed
JSON_TRANSPORT_BOUNDARY=passed
SANDBOX_TRUTH=passed
ENGINE_REQUEST_PARITY=passed_for_glm
OFFLINE_AGENT_RECOVERY=passed
OFFLINE_MULTI_AGENT=passed
LIVE_SINGLE_AGENT=passed
LIVE_RESTORE=passed
LIVE_PROVIDER_PARITY=not_started
LIVE_MULTI_AGENT=failed_provider_transport
LIVE_TRAJECTORY=passed_for_single_agent
QITA_LIVE_READ=passed_for_single_agent
G4_LIVE=provider_transport_failure
S3_STATUS=blocked_live_qualification
S4_READY=false
DEFAULT_BRANCH_READY=false
RELEASE_READY=false
```
