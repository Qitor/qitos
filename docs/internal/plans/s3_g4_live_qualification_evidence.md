# S3 G4-L2 live qualification evidence

Status: sixteen offline gates passed; bounded live execution pending
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
mypy for `qitos/config` plus the runner. The full repository rerun passed
`2372 passed, 50 skipped`; the static ratchet passed with 367 baselined findings
(345 active, 22 vendored/generated), stable flake8 passed, and stable mypy passed
on 93 source files. Build and twine checks passed for both distribution artifacts,
and a 1,310-file scan found zero credential-value, private-endpoint, or private-
launch-path hits.

## Live and promotion gate

No live provider request had been sent when this checkpoint was written. Live
qualification must load all three exact private configs, run basic/single-tool/
parallel-tool/continuation preflights, produce a real tool-using disposable
Agent workflow and fresh-process Session restore, pass privacy and cleanup, and
stay within each config's request budget. Each failure retains its concrete
type; provider, protocol, capability, timeout, sandbox, workflow, privacy, and
configuration failures are not collapsed into `configuration_blocked`.

Promotion, push, and worktree retirement remain prohibited until the live
receipt, deterministic/full/static/package/privacy gates, fast-forward
preconditions, primary-checkout rerun, and remote identity checks all pass.
The committed JSON summary will be replaced by the final sanitized runner
receipt after execution.

Current status variables:

```text
S3_STATUS=blocked_live_qualification
G4_DETERMINISTIC=passed
G4_LIVE=live_pending
CONFIG_LAUNCH=passed
SANDBOX_ATTESTATION=passed_offline
S4_READY=false
DEFAULT_BRANCH_READY=false
FINAL_STATUS=BLOCKED
```
