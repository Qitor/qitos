# Task 14 — sandboxed agent execution

Status: G4-L3 reference contract promoted; S4 task-exclusive staging, stronger
isolation, independent-backend qualification, and public DX remain planned
Depends on: Tasks 03, 09, 12, and 13
Feeds: Task 05 trajectory qualification, S4 developer experience, release gate
Risk: critical — agents execute model-selected code against files, processes,
networks, credentials, and external services

---

## 1. Goal

Give framework users one simple, provider-neutral way to run coding, research,
computer-use, and multi-agent workloads in isolated environments without making
the Engine, tools, Session, or WorkGraph depend on Docker or a cloud vendor.

The beginner path should eventually be this small:

```python
sandbox = DockerSandbox(
    image="python:3.12",
    policy=SandboxPolicy.coding(),
)
session = Engine(agent).session(task, environment=sandbox)
result = session.run()
```

The exact names remain subject to the public-surface review. The architecture is
not: one sandbox contract, one Env adapter, one lifecycle/evidence vocabulary,
and multiple replaceable backends.

## 2. Current repository truth

G4-L3 adds the first framework-owned structural `SandboxBackend` protocol under
`qitos.kit.env.sandbox`. It requires prepare, execute, capability inspection,
cancellation request, cleanup, and durability/safety receipt operations. The
declarative coding path uses an inspect-backed Docker adapter and fails closed
when Docker or a required capability is unavailable; it never falls back to the
host. A third-party adapter can satisfy the same protocol without subclassing
Docker, and the conformance tests exercise that structural replacement point.

The reference Docker launch attests a non-root user, read-only root filesystem,
one writable workspace mount, disabled network, all capabilities dropped,
no-new-privileges, CPU/memory/process bounds, a bounded tmpfs, no credential
environment, host-side provider requests, and container absence after cleanup.
Receipts contain digests and capability facts rather than host paths or secret
values. A partially prepared or later-failing composition must clean up; an
unproven destroy is `sandbox_cleanup_failed`, not success.

`unsafe_host` is the only declarative host-execution spelling. It is explicit,
never default for executable tools, publishes `unisolated_host_execution`, and
rejects Docker-only constraints it cannot enforce. This is a compatibility and
local-development escape hatch, not a sandbox.

The G4-L3 adapter still bind-mounts the selected host workspace and shares the
Docker host kernel. It is not a microVM, distributed scheduler, external-effect
exactly-once mechanism, or Python-thread hard-cancellation guarantee. Private
workspace staging, stronger runtime classes, disk quotas, network allowlists,
and managed backends remain later Task 14 work.

### Historical G4-L2 harness

G4-L2 adds a qualification-only harness around the existing `DockerEnv`. It
creates one uniquely labelled container from canonical AgentConfig, then derives
its receipt from `docker inspect` and real in-container identity, tool,
read/grep/write/test, boundary-denial, rootfs, network, tmpfs, repository-digest,
and cleanup probes. Model-visible operations use one Env-only toolset and have no
HostEnv fallback. The receipt binds config/policy/image/workspace and
Session/Run/WorkItem/Environment identities; cleanup targets only that identity
and proves absence.

This closes the bounded G4-L2 promotion prerequisite only. It does not add the
typed `SandboxSpec`, lease/generation ownership, secret broker, read-only trusted
input/output mount split, egress allowlists, microVM/gVisor backend, snapshot/
fork contract, or the full shared conformance suite below. Therefore it must not
be cited as Task 14 completion or production-grade untrusted-code isolation.

QitOS already has useful foundations:

- `qitos.core.env.Env`, `FileSystemCapability`, `CommandCapability`, and
  `TerminalCapability` define agent-world operations;
- `qitos.kit.env.DockerEnv` attaches to an existing container or creates a
  long-lived container from an image;
- Docker file and command capabilities execute through `docker exec`;
- `DockerEnvScheduler` bounds the number of task containers;
- `EnvSpec(type="docker")` can resolve an existing named container;
- Engine validates required Env operation groups and runs health/setup/teardown;
- Session snapshots already store environment resolver references rather than
  live clients; and
- the tool lifecycle contract distinguishes subprocess, environment operation,
  timeout, cancellation, process loss, stale results, and unknown outcomes.

This is native Docker-backed execution, but it is not yet a production sandbox
contract. In particular, current `DockerEnv` has no safe policy object, typed
resource limits, network allowlist, non-root/read-only defaults, secret broker,
lease/generation identity, snapshot/fork contract, durable cleanup receipt, or
Session/WorkGraph ownership binding. Programmatic auto-create uses a writable
host bind mount when supplied, forwards literal environment values through the
Docker command, permits arbitrary `extra_run_args`, and inherits Docker's
unbounded CPU/memory defaults. `EnvSpec` only attaches by container name and
does not expose the auto-create path.

Therefore QitOS may currently claim **Docker execution support**, but must not
claim **secure execution of untrusted agent code**.

## 2.1 Reference-harness lessons

The CyberGym agent harness provides a concrete, already exercised minimum
boundary for research agents. QitOS should absorb the generic mechanism, not
the benchmark, grading, vulnerability, or submission policy:

- every task receives one exclusive container before the first model request;
- host execution and `HostEnv` fallback are disabled and setup fails closed;
- model-visible read, grep, edit, shell, and debugger operations all use
  `env.fs` or `env.cmd`, with no subprocess or host-filesystem escape hatch;
- networking is `none`, the Docker socket and controller-private data are
  absent, and credentials, evaluator state, sibling tasks, and host traces are
  never mounted;
- mounts are narrow and attested: a read-only task description, writable
  workspace, read-only trusted inputs, an explicitly writable result area, and
  no whole task-root mount;
- the workload runs as the caller's non-root UID/GID, with `HOME` and `/tmp`
  inside a bounded `nosuid,nodev` tmpfs;
- pre-model attestation verifies working directory, tool availability, user,
  network mode, tmpfs, exact mount destination/mode, absent sensitive
  environment names, absent runtime sockets, and no unexpected mount;
- initial workspace state and input digests are recorded so pre-existing output
  cannot masquerade as an agent effect;
- only controller-owned privileged/private actions cross the boundary, using
  narrow result artifacts rather than granting the agent their authority; and
- cleanup is ownership/prefix scoped. Global Docker prune or cleanup of another
  task is never permitted.

This pattern becomes the `research_coding` policy baseline. A framework user
should receive it by default when an agent can modify files or run commands;
host execution is a separately named, explicit lower-assurance opt-out with a
receipt. Read-only conversational agents may select a lighter process sandbox.

The reference harness is not itself the final QitOS sandbox. It still relies on
free-form Docker arguments, directly bind-mounts the writable host repository,
conditionally grants `SYS_PTRACE`, does not require CPU/memory/pids limits, and
uses ordinary container isolation rather than gVisor or a microVM. Task 14 must
preserve its fail-closed boundary while closing these remaining gaps.

## 3. Threat model

The sandbox assumes model-selected commands and repository content may be
malicious. It must contain:

- reads outside declared workspace and approved runtime dependencies;
- writes to host configuration, credentials, Git metadata, or sibling work;
- symlink, path traversal, mount, and time-of-check/time-of-use escapes;
- access to the host Docker daemon or another sandbox;
- privilege escalation, device access, namespace sharing, and dangerous kernel
  interfaces;
- unapproved network egress, private/local endpoint access, DNS rebinding, and
  credential exfiltration;
- fork bombs, process leaks, disk exhaustion, memory exhaustion, CPU starvation,
  and oversized output;
- secret appearance in process arguments, environment dumps, logs, snapshots,
  trajectories, artifacts, or model-visible diagnostics;
- stale sandbox handles mutating a restored or transferred Session owner; and
- abandoned sandboxes surviving task/session/work-item retention policy.

No software sandbox alone proves protection from host hardware vulnerabilities,
side channels, a compromised hypervisor/runtime, or explicitly granted external
effects. Every backend publishes its threat-model limits.

## 4. Canonical architecture

### 4.1 `SandboxSpec`

A strict JSON-safe desired-state document contains:

- backend capability requirement, image/template reference, immutable digest,
  architecture, and setup receipt;
- workspace policy: private clone/copy-on-write, ephemeral empty workspace,
  explicit read-only source, or explicitly unsafe direct mount;
- read/write roots, temporary mounts, maximum artifact transfer, and Git metadata
  policy;
- network default, domain/IP/port allow rules, local/private-address policy,
  inbound-port policy, and model/provider proxy reference;
- CPU, memory, process, disk, file-descriptor, output, idle, command, and
  wall-clock limits;
- user/group, capabilities, devices, privilege, root-filesystem, seccomp,
  AppArmor/SELinux, and runtime-class requirements;
- secret and credential references, never secret values;
- pause/snapshot/fork/retention requirements; and
- labels needed to bind the sandbox to Session, Run, WorkItem, Attempt, owner,
  and generation identities.

Unknown or unsupported required policy fields fail closed. A backend may report
optional capability loss only when the caller explicitly permits it.

### 4.2 `SandboxBackend`

One structural protocol owns:

- capability discovery and policy validation;
- provision/connect/inspect and readiness;
- bounded command execution and file/terminal operations;
- optional pause/resume, filesystem snapshot, memory snapshot, and fork;
- stop/destroy, lease renewal, garbage collection, and reconciliation; and
- redacted lifecycle, resource, network, effect, and cleanup receipts.

Backends return opaque logical references plus generation/lease facts. Live SDK
clients, subprocess handles, Docker clients, sockets, and credentials never enter
canonical snapshots.

### 4.3 `SandboxEnv`

`SandboxEnv` is the only adapter presented to the current Env/tool layer. It maps
file, process, and terminal capabilities onto a `SandboxBackend`. Engine and
coding tools continue to depend on Env capabilities and never branch on Docker,
gVisor, Firecracker, E2B, Daytona, Modal, or another vendor.

The existing `DockerEnv` is migrated behind this adapter and retained only as a
bounded compatibility entry point. It must not become a second lifecycle truth.

### 4.4 Session and WorkGraph binding

Session state and sandbox state are related but distinct:

- a QitOS Session snapshot is the authoritative semantic execution state;
- a sandbox snapshot is an optional environment acceleration/state artifact;
- Session pause is successful only after tool/sandbox quiescence or an explicit
  typed `outcome_unknown` boundary;
- restore resolves a sandbox backend and validates spec, image, workspace,
  capability, owner, and generation digests;
- if memory resume is unavailable, the framework cold-restores from immutable
  image plus workspace/artifact snapshot and resumes from QitOS semantic state;
- Session fork creates a new sandbox when required or explicitly records a safe
  read-only/shared-workspace policy; and
- handoff/delegate/spawn/fan-out allocate sandbox authority through the existing
  parent/child capability and budget intersection. A child never inherits a
  writable workspace, network, secret, or connector implicitly.

## 5. Default security posture

The coding-agent preset is deny-by-default:

- one exclusive sandbox per task or durable child work item; reuse or sharing
  requires an explicit compatible ownership policy;
- private clone or copy-on-write workspace; direct host mount is an explicit
  lower-assurance choice;
- no host home, credential directory, Docker socket, arbitrary mount, host PID,
  host IPC, device, or privileged access;
- non-root workload, read-only root filesystem, writable workspace/tmp only,
  all Linux capabilities dropped unless a typed exception is justified, and
  `no-new-privileges` enabled;
- runtime-default seccomp plus platform MAC policy; stronger runtime requested
  for untrusted or multi-tenant work;
- no inbound port and no network by default; egress allow rules are explicit and
  local/private targets remain denied unless separately authorized;
- secret values remain in a host/provider credential broker where supported;
  environment injection is a declared lower-assurance fallback;
- CPU, memory, process, disk, output, command, idle, and wall-clock limits are
  mandatory; and
- cleanup has a deadline and terminal receipt. An unconfirmed destroy remains an
  operator-visible leak, not success.

Provisioning is not complete until a pre-model attestation proves the resolved
policy from runtime facts. A mismatched user, network, mount, tmpfs, image,
workspace digest, secret boundary, runtime socket, or required tool blocks the
first model request. Attestation is persisted as a redacted receipt; configured
intent alone is not execution evidence.

Free-form Docker run arguments are not a security API. The new typed policy
rejects `--privileged`, host namespace sharing, Docker socket mounts, arbitrary
devices, unconfined seccomp, and host-root mounts unless a separately named
unsafe policy is explicitly selected and recorded.

## 6. Backend strategy

| Backend family | Intended role | Strength | Important limit |
|---|---|---|---|
| OS process sandbox | fastest local command isolation using Seatbelt on macOS or bubblewrap/Landlock on Linux | low startup overhead and workspace-focused policy | not a multi-tenant VM boundary; platform behavior differs |
| Hardened Docker | baseline local/CI reference implementation | familiar OCI images, broad compatibility, existing QitOS code | shares a kernel on native Linux; safe flags and daemon boundary are mandatory |
| Docker Sandboxes | preferred high-isolation local coding-agent backend when available | per-sandbox microVM, private Docker daemon, network/credential policy, clone workflow | currently an evolving product surface; capability probing required |
| Docker with gVisor `runsc` | stronger Linux/cluster container isolation | OCI-compatible userspace application kernel and good density | syscall compatibility and syscall-heavy performance trade-offs |
| Kata/Firecracker service | high-assurance self-hosted multi-tenant execution | separate guest kernel/hardware virtualization | KVM/Linux operations, images, networking, snapshots, patching, and jailer are platform responsibilities |
| Managed agent sandbox | optional E2B, Daytona, Modal, or future adapters | fast provisioning plus managed lifecycle/snapshots | external cost, data residency, SDK churn, quotas, and provider-specific capability gaps |

QitOS does not expose separate public architectures for these rows. Conformance
tests determine which optional capabilities each adapter can advertise.

## 7. Delivery packages

### 14A — contract, threat model, and conformance fake

- Freeze the single spec/backend/handle/receipt vocabulary.
- Add a deterministic third-party-style fake backend.
- Define typed capability loss, policy rejection, stale lease, resource limit,
  cleanup failure, and outcome-unknown behavior.
- Add interface-budget and architecture-boundary gates.

### 14B — hardened local execution

- Move existing Docker mechanics behind the canonical backend.
- Replace free-form security configuration with typed policy construction.
- Implement task-exclusive provisioning, private workspace staging,
  digest-pinned images, non-root/read-only defaults, resource limits,
  network-off/allowlist behavior, bounded tmpfs/output, pre-model attestation,
  contamination/input-digest proof, and durable cleanup receipts.
- Enforce that all model-visible file, command, terminal, and debugger tools use
  the sandbox Env; a missing or unhealthy backend fails closed rather than
  silently selecting `HostEnv`.
- Add an OS-process sandbox adapter for low-latency trusted/local use where the
  platform can prove its policy.

### 14C — strong-isolation and remote adapters

- Qualify Docker Sandboxes as the first local microVM adapter if its installed
  capability set satisfies the contract.
- Qualify Docker + gVisor on supported Linux CI/hosts.
- Spike one managed backend against the same tests; E2B is the initial
  agent-oriented candidate, while Daytona is especially relevant to VM
  pause/fork and Modal to gVisor-backed scale and snapshots.
- Keep Firecracker/Kata behind an operator-owned service adapter; do not embed a
  production microVM orchestrator in the framework package.

### 14D — Session, multi-agent, trajectory, and DX closure

- Bind sandbox identity/generation/lease to Session and WorkGraph facts.
- Prove pause, process loss, cold restore, sandbox resume, fork, handoff, child
  cancellation, late result, and cleanup behavior.
- Emit redacted sandbox policy/lifecycle/resource/egress receipts into the
  canonical Trajectory plane and qita inspection.
- Publish one beginner coding-agent example that switches Docker, stronger local,
  and remote backends without changing agent logic.

## 8. Required conformance matrix

Every advertised backend is tested for:

- policy validation and honest capability discovery;
- workspace read/write scope, traversal, symlink, Git metadata, and host-path
  denial;
- network deny, explicit allow, local/private endpoint denial, DNS changes, and
  no silent fallback;
- secret reference use and zero secret value in arguments, environment reports,
  logs, snapshots, trajectories, or diagnostics;
- pre-model attestation of exact user/network/tmpfs/mount/tool/socket policy and
  rejection of unexpected mounts or controller-private inputs;
- proof that all model-visible file/command/debug paths use `SandboxEnv`, with no
  host fallback or process-local bypass;
- CPU, memory, process, disk, output, command, idle, and wall-clock termination;
- non-root/no-new-privileges/capability/device/runtime facts where applicable;
- concurrent exec, timeout, cancellation, worker-still-running, late result, and
  outcome-unknown semantics;
- pause/resume/snapshot/fork only when advertised;
- clean-process resolver restore, stale owner/generation fencing, and no duplicate
  committed effect;
- child sandbox authority intersection and deterministic join behavior;
- destroy, repeated destroy, process/client loss, leaked-resource detection, and
  task-owned garbage-collection receipts without global prune; and
- portability across supported CPU/OS targets without turning unavailable into
  pass.

## 9. Release gates

QitOS may call a backend a sandbox only when:

- its threat model and unsupported matrix are public;
- safe defaults pass executable escape, egress, resource, secret, lifecycle, and
  cleanup tests;
- policy degradation is typed and opt-in;
- the Session/WorkGraph recovery tests preserve ownership and effect truth;
- raw/private and redacted/public trajectory views remain separated; and
- at least one independent adapter written against the public protocol passes
  conformance without accessing Engine or store internals.

Until 14A–14D close, `DockerEnv` remains a useful execution environment, not a
security qualification claim.

## 10. Primary research sources

- [Docker Sandboxes security model](https://docs.docker.com/ai/sandboxes/security/)
- [Docker container run security and resource options](https://docs.docker.com/reference/cli/docker/container/run)
- [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/)
- [gVisor architecture](https://gvisor.dev/docs/)
- [Firecracker design](https://github.com/firecracker-microvm/firecracker/blob/main/docs/design.md)
- [E2B sandbox persistence](https://docs.e2b.dev/sandbox/persistence)
- [Daytona sandbox lifecycle](https://www.daytona.io/docs/sandboxes)
- [Modal Sandboxes](https://modal.com/docs/guide/sandboxes)
- [Anthropic Sandbox Runtime](https://github.com/anthropic-experimental/sandbox-runtime)
- [Codex sandbox implementation notes](https://github.com/openai/codex/blob/main/codex-rs/core/README.md)

## 11. R5 bounded model plane and responsibility boundary

Sandbox receipts and canonical `ToolResult` records remain persistence facts,
not default model input. Built-in read, grep, list, write, and command tools use
bounded allowlisted projections; stdout/stderr and file bodies have character
limits, inventories have count limits, repeated environment observations use a
digest/delta, and every omission has a loss or selection receipt. Host paths,
permission internals, owner generations, and complete artifact bodies are
excluded or redacted. Custom tools may supply their own bounded projection or
artifact reference; the framework context ceiling truncates or rejects an
oversized model view according to declared policy.

These mechanism guarantees do not promise that an Agent chose the right tools,
budget, prompt, or context priorities. The complete boundary is
[`framework-responsibility-boundary.md`](../architecture/framework-responsibility-boundary.md).

## G5 local integration candidate (2026-09-04)

The isolated G5 candidate now wires immutable-source CLI fork, durable SQLite
composition/credential-free inspection, artifact-backed cold Docker workspace
restore, separate child allocation, ownership fencing and checkpoint-derived
child completion/join. Cleanup does not publish source changes; publication is
an explicit permission/effect operation. The candidate has focused regression
evidence, but installed consumers, full platform qualification and final gates
remain open. See [the execution ledger](../internal/plans/s4_g5_convergence_execution.md).
No primary promotion, default Trajectory switch or release is asserted here.
