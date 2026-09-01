# S3 G4-L2 live qualification evidence

Status: deterministic/config/sandbox gates passed; live workflow failed
Updated: 2026-09-01
Owner: G4 integration owner
Fixed integration source: `851f7902f15da670e72f4c04d7453cf37201aee7`
Candidate start: `bd0f93328ccb37b66e62855de8ad489916c47e1e`

## Scope and authority

This is the evidence ledger for canonical Agent launch, executable Docker
qualification, the three-provider live preflight, and the required Agent/
Session restore workflows. The sole execution inputs are strict private
`qitos.agent/v1` files; the Markdown matrix is audit context only. Model
construction reuses `ModelFactory`, workflows reuse the existing
`AgentModule + Engine`, restore reuses the existing SQLite checkpoint store,
and every model-visible file or command operation uses the configured Env.

The runner is opt-in and accepts one or more `--config` arguments. It validates
the full source commit, binds the runner bytes and every canonical/source digest,
requires an external private evidence directory, resolves logical credentials
through the local-file resolver, and never treats assistant text as a native
tool call. Configured bounds are 12 requests per profile, 10,240 output tokens
per response, 180 seconds per request, and zero automatic model-layer retries.
Attempted requests are counted even when a provider raises, and reported usage
and latency are preserved without inventing pricing.

## Configuration and privacy receipt

Three private launch files and the credential mapping live under
`<user-config-dir>`, outside Git. The directory is owner-only, launch files and
the credential file are regular non-symlink files with mode `0600`, and the
credential parent is current-user-owned and not group/world writable. The
resolver rejects unknown, missing, empty, duplicate, wrong-type, in-repository,
wrong-owner, symlink, and unsafe-mode inputs with typed failures.

Committed configuration receipts contain schema/config/source/request/endpoint/
credential-reference/sandbox/workspace digests, selected provider/model,
tool/protocol identity, Session/store and Trajectory capabilities, and explicit
omissions. They contain no endpoint, host path, credential-store location,
credential value, Authorization/cookie/token, request header, or raw provider
payload. Restore reloads the same logical config and re-resolves the reference;
no secret or live client is serialized in Session state.

## Executable sandbox receipt

The G4-L2 harness creates one uniquely named and labelled Docker container from
AgentConfig. The qualification receipt is derived from real `docker inspect`
and in-container probes for:

- `network=none`, read-only rootfs, `cap-drop=ALL`, no-new-privileges, non-root
  caller UID/GID, CPU/memory/pids limits, and bounded `/tmp` tmpfs;
- absence of the Docker socket, sensitive environment names, namespace sharing,
  and unexpected mounts;
- one private workspace bind, exact working directory, required tools, Env-only
  read/grep/write/test operations, path-escape denial, rootfs-write denial,
  network denial, and workspace digest stability; and
- config/policy/image/workspace plus Session/Run/WorkItem/Environment identities,
  targeted cleanup, and container absence after cleanup.

The real Docker test and the fake-provider coding workflow through the same Env
both passed locally. This is a bounded release qualification harness, not the
complete Task 14 sandbox: no typed public SandboxSpec, lease/generation broker,
microVM/gVisor backend, managed backend, or full egress/secret conformance claim
is made.

## Authoritative offline gate

The pre-live runner completed all sixteen ordered gates with zero provider
requests, zero reported tokens, and zero retries. Its pytest command covered:

- strict parser, unknown/type rejection, deterministic canonical/sanitized
  serialization, compatibility receipts, and credential safety;
- fake resolver/provider single response, single and parallel native tools,
  continuation, one-Env coding workflow, and reachable `G4_LIVE=passed`;
- twenty-round deterministic Session continuity, fresh-process single restore,
  and clean-process multi-agent/WorkGraph restore without replaying unknown work;
  and
- actual Docker creation/inspect, operation probes, boundary denials,
  repository-digest preservation, identity-bound cleanup, and evidence binding.

Focused post-change checks also passed: 267 configuration/security/credential/
runner/Docker/provider/codec/Session/WorkGraph/tracing/qita/architecture tests,
two CLI launch tests, flake8 for the changed configuration/runner surface, and
mypy for `qitos/config` plus the runner. The final full repository rerun passed
`2374 passed, 50 skipped`; the static ratchet passed with 367 baselined findings
(345 active, 22 vendored/generated), stable flake8 passed, and stable mypy passed
on 93 source files. Build and twine checks passed for both distribution artifacts,
and a 1,310-file scan found zero credential-value, private-endpoint, or private-
launch-path hits.

## Live provider facts

All three private configs were loaded by the canonical loader and each provider
produced four real preflight responses. DSV4 and GLM passed text, one native
tool, three parallel native tools, and continuation. Qwen passed text but
returned no native calls for the single/parallel requests and returned three
calls where continuation required a final response, so its honest typed outcome
is `capability_loss`. This satisfies the provider-capability minimum but does
not by itself qualify an Agent workflow.

The preflight used 12 requests, 3,403 reported input tokens, 905 reported output
tokens, 4,308 reported total tokens, 34,599 ms aggregate latency, and zero
model-layer retries. These are provider-reported preflight facts only; workflow
usage was not reliably emitted after worker failure and is intentionally not
fabricated.

## Workflow failure and stop decision

Neither qualified provider completed the required coding workflow. The first
DSV4 run reached a real parent Env read and declared two distinct children, two
ContextTransfers, fan-out, and all-join, but attempted to restore a still-created
single Session and stopped. A direct DSV4 retry ended in typed model recovery
failure. The generic runner defect was fixed by running the single Session to a
safe pause before restore and by preserving a sanitized typed child-process
failure receipt instead of discarding it.

With that fix, GLM's text-protocol run restored the single Session and two
children in fresh processes and retained distinct lineage, two transfers, and a
join, but the model never routed a real tool, so the receipt remained failed.
Explicitly projecting the already-proven native-tool profiles onto the existing
`json_decision_multi_v1` protocol did not close the gap: DSV4 ended
`unrecoverable_error`; GLM stopped at `budget_steps`, left the disposable source
unchanged, and its tests remained 2 failed / 1 passed.

Across the preflight and bounded diagnostic attempts, observed request counts
were DSV4 9, GLM 13, and Qwen 4. GLM therefore exceeded the configured
12-request qualification budget by one request. No further provider request is
authorized. The immutable preflight receipt remains
[`s3_g4_live_qualification_summary.json`](s3_g4_live_qualification_summary.json);
the sanitized closure facts and private-artifact digests are in
[`s3_g4_live_workflow_failure_receipt.json`](s3_g4_live_workflow_failure_receipt.json).

Privacy, Docker attestation, targeted container cleanup, main-checkout
non-modification, and absence of HostEnv fallback all passed. The private
disposable repository and Session stores are preserved outside Git for audit.
Because the full single-agent workflow, full multi-agent workflow, live qita
inspection, and request budget did not pass together, promotion, push, and every
worktree removal are prohibited.

Current status variables:

```text
S3_STATUS=blocked_live_qualification
G4_DETERMINISTIC=passed
G4_LIVE=workflow_failure
CONFIG_LAUNCH=passed
SANDBOX_ATTESTATION=passed
S4_READY=false
DEFAULT_BRANCH_READY=false
FINAL_STATUS=BLOCKED
```
