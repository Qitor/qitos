# S4 Lane C — safe execution implementation ledger

Status: in progress
Source and strict merge-base: `c4e621d05960a4e2f06cb4864f6a8cb8275ac067`
Branch: `codex/v4-s4-c-safe-execution`
Worktree: `/Users/morinop/Desktop/WhitzardOS-s4-c`

## Scope and invariants

This lane evolves the existing `ToolRegistry -> ActionExecutor -> Env` and
`Session -> DurableWorkRuntime -> WorkGraph` paths in place. It does not add a
second tool result, sandbox architecture, execution loop, checkpoint store, or
multi-agent scheduler. Model-selected file and process operations remain Env
capability calls. Provider requests remain host-side.

The lane never claims hard cancellation of Python threads, cancellation of a
remote HTTP/MCP effect from a client timeout, reliable termination of an
unowned process, external exactly-once effects, VM-grade Docker isolation, or
release readiness.

## Work plan

- [x] Fixed-baseline/worktree preflight and required-document review.
- [x] Initial execution census and CyberGym generic-mechanism comparison.
- [x] Typed sandbox policy, identity, lease, attestation, execution, cleanup,
  and snapshot-component contracts.
- [x] Private-staging Docker implementation and exact-identity cleanup.
- [x] Env-only native ACI: read, list, grep, write, edit, command, test, and
  bounded process control, with canonical/model projection separation.
- [x] Remove nested-Engine/thread-pool multi-agent semantic fallbacks; retain
  one durable adapter path with typed unavailable results.
- [x] MCP parity audit and adapter/conformance coverage.
- [x] Adversarial, process-loss, SQLite/Memory, public-boundary, and Docker
  qualification evidence (Docker kernel probes remain platform-blocked below).
- [x] Producer manifest, fixture digests, and A/B/D handoff.
- [x] Final full-suite and Docker platform recheck executed; exact non-passing
  gates are recorded below rather than promoted to pass.

## Initial execution census

| Surface | Current route | Bypass/gap found | Lane action |
| --- | --- | --- | --- |
| class/function/sync/async tools | `ToolRegistry` -> structural validation -> interceptor -> permission -> revalidation -> `ActionExecutor` -> canonical `ToolResult` | sync deadline uses a non-cancellable Python worker; correctly records `worker_still_running`; legacy registry fallbacks still exist | keep the single executor, test truthfulness |
| native parallel calls | `ActionExecutor.execute_batch` segments by `ToolSpec` and publishes terminal callbacks in completion order | declarative config additionally name-allowlists three read tools | publish spec-derived evidence; leave shared config wiring to A/G5 |
| read/list/grep/write/command | `EnvCodingToolSet` -> runtime `ops` -> Env | incomplete ACI, no edit/test/process-control, weak typed errors/artifacts | replace in place with bounded Env-only tools |
| full legacy coding toolset | `CodingToolSet` | host `Path/open/subprocess/requests`, background thread, nested Engine | retain as compatibility surface, document as non-sandbox ACI; do not route default safe preset through it |
| Env operations | Engine `_env_runtime` and runtime `ops` | HostEnv is inherently unisolated; Docker path validation lacks symlink/TOCTOU atomicity | add capability operations and typed failures |
| Docker | `DockerEnv` + inspect-backed `DockerSandboxBackend` | writable host repository bind mount, free-form flags, no lease/snapshot component, incomplete cleanup identity | typed policy plus private staging and exact labels |
| HTTP | HTTP tools/client owners | timeout cannot prove remote cancellation; some legacy direct `requests` paths | record lifecycle limits; safe ACI has no direct HTTP path |
| MCP | bridge returns `FunctionTool` and normally reaches `ToolRegistry`/executor | standalone bridge owns an event-loop thread adapter; transport results are legacy dicts | canonical result adapter and conformance evidence without a second executor |
| delegate | tool adapter uses `Session.submit_work` when bound | fallback constructs nested `Engine` | remove fallback execution semantics |
| spawn | durable adapter only | no sandbox allocation fact in descriptor | publish sandbox component/allocation contract for A/G5 wiring |
| fan-out | durable adapter uses Session when bound | fallback owns `ThreadPoolExecutor` and nested Engines | remove fallback execution semantics |
| handoff | direct Session uses durable graph; decision-mode handoff still mutates live Engine | model tool can be intercepted before ordinary execution | keep compatibility decision path; tool fallback becomes durable-only |
| join | direct/tool adapters share `Session.submit_work` | terminal child outcome storage remains external to scheduler receipt | retain typed terminal reference and unknown state |

## CyberGym mechanism boundary

Imported ideas are limited to generic mechanisms: fail-closed Env-only tools,
exact mount-mode attestation, no Docker socket/credential exposure, task-local
tmpfs, initial workspace digest, scoped cleanup, and pre-model capability
proof. Benchmark task vocabulary, vulnerability strategy, scoring, submission,
prompts, and evaluator authority are excluded.

## Patch-ready cross-lane handoff

Lane A/G5 owns config/Session public wiring and shared docs. Lane C will provide
a JSON-safe sandbox snapshot component and fixtures containing logical identity,
backend/policy/image/capability digests, Session/Run/WorkItem/Attempt,
generation/lease, workspace/input digests, quiescence, and cleanup state. Lane
D should consume canonical receipts, never Docker inspect documents or host
paths.

## Native ACI surface

`EnvCodingToolSet` v2 exposes exactly ten strategy-neutral tools: `read_file`,
`list_files`, `grep_file`, `write_file`, `edit_file`, `run_command`,
`run_test`, `start_process`, `poll_process`, and `terminate_process`. The module
imports neither `pathlib` nor `subprocess`; every world interaction resolves a
declared Env operation. Reads retain full canonical content while the model sees
a line-numbered bounded window. Search uses structured ripgrep output. Large
read/search/command/MCP values retain canonical output and publish a
content-addressed `ArtifactRef` plus an explicit loss receipt. Writes and edits
use atomic replace and optional SHA-256 optimistic concurrency. File mutation
and command authority are separate `ToolPermission` bits. Background handles
are Env-owned and generation-fenced.

The shared declarative builder still explicitly allows parallel execution only
for `read_file`, `list_files`, and `grep_file`; changing that config-owned list
is outside this lease. The executor itself publishes real completion order and
derives declaration-order queries for every admitted parallel call.

## Sandbox ADR and threat model

The existing `SandboxBackend` now has typed policy/resource limits, identity,
lease, logical handle, execution/cleanup receipts, a patch-ready allocation,
and an optional snapshot-component codec. The Docker reference accepts only
disabled networking; requested egress allowlists are rejected because DNS
rebinding, redirects, private-address denial, and proxy enforcement are not
implemented. It also rejects input mounts and pause/snapshot/fork claims it
cannot attest.

The reference launch uses a read-only rootfs, numeric non-root user, all
capabilities dropped, no-new-privileges, no host PID/IPC/device authority, no
host mounts, and tmpfs-backed `/tmp`, `/workspace`, and `/results` with CPU,
memory, pids, file-descriptor, workspace, output, command, and wall-time
bounds. Controller-side staging excludes VCS, credential directories, key
files, environment files, and every symlink. Provider calls and credentials
remain host-side. Cleanup is label-scoped to the exact sandbox identity,
verifies absence, and never invokes global prune.

Deterministic tests cover relative/absolute escape, protected paths, symlink
escape, stale-file TOCTOU, unsafe namespaces/devices/privilege, secret
injection, resource declarations, stale process generations, bounded output,
and exact ownership shape. Real kernel enforcement remains a property of the
Docker reference, not structural third-party fakes; Docker is not a VM.

## Lifecycle and effect matrix

| Resource | Owner | Timeout/cancel fact | Recovery/effect rule |
| --- | --- | --- | --- |
| sync/function/thread | ActionExecutor | thread may remain live; no hard cancel | live worker blocks replay |
| async coroutine | ActionExecutor | helper worker may remain live | generation gates late result |
| owned process | Env | TERM/KILL only for the exact handle | stale generations rejected |
| unowned process | external owner | termination is not claimed | unfinished outcome is unknown |
| HTTP/MCP | client/transport owner | local deadline does not prove remote cancel | unknown effect requires reconciliation |
| environment operation | Env | capability-specific | canonical ToolResult carries terminal fact |
| durable child | DurableWorkRuntime | cancel request may leave worker running | WorkGraph retains unknown |

Committed effects are non-retryable and are not replayed. Commit-then-fail is
`reconciliation_required`; unknown is never guessed. Existing tests prove zero
duplicate commits, completion-order callbacks, process-loss recovery, stale
generation suppression, and Memory/SQLite durable work paths.

## Durable work parity and migration

All five model adapters now call `submit_durable_work`, which calls only
`Session.submit_work`; direct Session methods use that same method and the same
`DurableWorkRuntime`. The old delegate nested Engine and fan-out private thread
pool were removed. Their census-visible private method names remain only as
rejecting migration shells and cannot execute work. Missing durable composition returns
`durable_work_runtime_unavailable` instead of changing semantics. Constructor
fields `max_workers` and `per_task_timeout` remain accepted for source
compatibility, but scheduling and admission are runtime-owned.

The sandbox codec is intentionally not registered in A-owned Session wiring.
G5 must allocate one least-authority `SandboxHandle` per child descriptor,
persist `SandboxAllocation.to_dict()`, resolve/re-attest on restore, create a
fresh sandbox on fork, and increment/fence the lease during handoff. No parent
filesystem, network, credential, or artifact authority is implied.

## MCP convergence and migration boundary

MCP schema conversion remains a compatibility adapter. Unknown tools now
default to effectful, exclusive, approval-required authority with file,
command, and network permissions. The bridge returns an async `FunctionTool`
carrying `MCP_REQUEST` lifecycle and canonical `ToolResult`; ActionExecutor
owns awaiting, timeout, effect finalization, artifacts, and terminal callbacks.
The former bridge-local thread pool is gone. Stdio children receive only a
minimal controller environment plus explicitly configured variables.

The repository still implements a 2024-11-05 JSON-RPC subset instead of the
official SDK. Pagination, richer capability negotiation, broader notifications,
and durable Session transport restoration remain migration gaps. Engine owns
connected transport cleanup today; Session snapshot wiring is an A/G5 handoff.

## Qualification and evidence

Deterministic evidence lives in `tests/fixtures/s4/lane_c/`; every fixture
digest is checked by `producer_manifest.json`. Independent package-style
executor, effect-policy, and sandbox-backend examples use public protocols.
The sandbox fake proves structure and lifecycle shape only.

The real Docker run was attempted using local image digest
`430c1255a732f53a93dbfb02dc407b6e5e1782a96fe66b91c04e35d447a2546e`.
After replacing `docker cp` staging (which cannot write through a read-only
rootfs) with a controller-validated tar stream written as the policy UID/GID,
the run reached create, private staging, inspect, file write/readback, and exact
cleanup. The shared Docker control plane then missed the grep `docker exec`
deadline while unrelated containers were active. This remains a typed
`sandbox_qualification_failed` platform blocker, not a pass or skip. A second
full-suite route also timed out in a later command probe. Label-scoped inventory
found zero QitOS sandbox containers afterward. Reproduce with:

```bash
/opt/anaconda3/bin/python -m pytest -q \
  tests/test_docker_qualification.py::test_real_docker_qualification_is_inspect_and_probe_backed -s
docker ps -a --filter label=qitos.sandbox.id \
  --format '{{.ID}} {{.Names}} {{.Label "qitos.sandbox.id"}} {{.Status}}'
```

The adversarial manifest covers every requested case. Controller-level path,
TOCTOU, protected-data, policy-rejection, privacy, output, generation, late
worker, recovery, repeated-cleanup, and leak checks pass deterministically.
Kernel-backed unexpected-mount, endpoint/network, fork/pids, resource-limit,
and sibling-isolation probes remain `platform_blocked`; structural inspection
requirements are evidence contracts, not substitutes for those probes.

## Validation ledger

- Baseline targeted suite: 781 passed.
- Lane C and adjacent contract suite: 170 passed.
- Required `tests/core`: 428 passed; `tests/engine`: 245 passed;
  `tests/mcp`: 58 passed.
- Required flake8 scope passed; required mypy scope passed; `git diff --check`
  passed.
- Full suite: 2446 passed, 99 skipped, 6 failed. Three S3 live-runner unit
  failures were traced to the old `environment_id` identity spelling and fixed;
  their targeted rerun is 3 passed. Remaining observed failures are one
  Docker process-restore preflight, one Docker ACI command probe, and the S3
  Lane C immutable-manifest test whose old hashes intentionally cover the two
  Lane C files changed here.
- `scripts/static_quality.py check` reports nine resolved baseline findings.
  Its own ratchet requires shrinking `quality/static_baseline.json`, but that
  file is explicitly outside this lane's lease; no baseline was edited and no
  failure was masked.

## Public-surface delta

No root, `qitos.core`, or `qitos.engine` export was added. The typed Env and
sandbox contracts are importable from their defining modules; the established
`qitos.kit.env` surface exposes the replaceable sandbox seam. G2 interface
budget and the S1 execution census pass unchanged. Formal graduation of new
sandbox names into frozen interface budgets is an A/G5 decision.

## Patch-ready A/B/D/G5 handoff

- A: register the optional sandbox component codec and re-resolve/re-attest it
  before resume.
- B: decide whether config should admit `poll_process` to its explicit native
  parallel allowlist; mutation and process-start tools remain exclusive.
- D: publish the ACI, Docker limits, typed blocker, and unsupported claims only
  after integration.
- G5: bind `SandboxAllocation` to each child descriptor/context-transfer
  receipt, inject child-local Env authority, fence handoff generations, and
  make cleanup a Session terminal obligation.
