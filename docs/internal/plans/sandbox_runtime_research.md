# Sandbox runtime research and QitOS disposition

Status: research complete; architecture routed to Task 14; implementation not started
Updated: 2026-09-01
Owner: S4 integration planning

## Question

Can QitOS already run agents in Docker, and what isolation architecture should a
general agent-development framework provide for Codex/Claude-Code/OpenCode-class
agents?

## Repository findings

QitOS can already execute in Docker:

- `DockerEnv` attaches to a named container or programmatically creates one;
- it provides file and command Env capabilities through `docker exec`;
- it can mount a host workspace, choose a Docker network, pass environment
  values, remove an owned container, and bound concurrent container allocation;
- Engine can construct an attached Docker environment from `EnvSpec`; and
- Env health/setup/teardown and tool required-operation checks are integrated.

This is enough for controlled CyberGym-style execution when an external harness
owns image, container, network, mount, and cleanup policy. It is not enough for a
general framework to safely provision environments for untrusted model-selected
code.

The concrete gaps are:

1. `EnvSpec(type="docker")` only accepts an existing container name, while the
   richer auto-create path is a separate programmatic surface.
2. Host workspace bind mounts are writable and have no copy-on-write/private-clone
   policy.
3. Container environment values are passed inline to the Docker CLI; there is no
   secret-reference/broker contract.
4. `extra_run_args` bypasses structured policy and can weaken isolation.
5. CPU, memory, pids, disk, output, user, capabilities, devices, root filesystem,
   and namespace policy have no framework defaults or receipts.
6. Network selection is a Docker network name, not deny-by-default egress policy.
7. Container identity is a string, not a generation/lease-fenced Session or
   WorkItem resource.
8. Stop/remove has no durable acknowledgement, reconciliation, or leaked-resource
   inventory.
9. Container files/processes are not represented as optional environment
   snapshots, and no backend capability describes pause/resume/fork.
10. Tests mock Docker command construction; they do not qualify a real security
    boundary or attempt escape, exfiltration, resource exhaustion, crash, and
    cleanup scenarios.

## CyberGym reference-harness audit

The existing CyberGym agent harness demonstrates the correct minimum posture
for a research workload whose model can inspect and modify code:

1. `make_task_container_env` creates a task-exclusive container with
   `network=none`, caller UID/GID, an in-container `HOME`, and a bounded
   `nosuid,nodev` `/tmp` tmpfs.
2. It mounts only the exact task description, repository, trusted binaries,
   knowledge inputs, and output area with explicit read/write modes; it does not
   mount the whole task root.
3. `CyberGymEnv.setup` performs a fail-closed attestation before any model token:
   required paths and tools, write probes, exact mount table, exact user,
   network mode, tmpfs, absent Docker socket, absent runtime traces, and absent
   sensitive environment names.
4. Workspace tools depend only on `env.fs` and `env.cmd`; they do not fall back
   to host paths or subprocess execution when the container is missing.
5. The controller records initial workspace contamination/input digests, keeps
   private evaluator/credential authority outside the container, records the
   attestation in results, and cleans only task-owned resources.

These are domain-neutral safety mechanisms and become the required
`research_coding` baseline in Task 14. The corresponding benchmark-specific
task schema, grading, exploit, submission, and controller policy remain outside
QitOS.

The audit also found limits that QitOS must not inherit as the final design:

- isolation policy is carried partly through `extra_run_args` instead of a
  typed, validated contract;
- the writable repository is a direct host bind mount rather than a private
  clone/copy-on-write workspace;
- debugger support can add `SYS_PTRACE` without a general capability exception
  receipt;
- CPU, memory, process, and disk limits are not all required; and
- the backend is an ordinary Docker container, not gVisor or a microVM boundary.

The lesson is therefore **attested task isolation by default**, not simply
“provide a Docker option.”

## External findings

### Hardened containers remain the compatibility baseline

Docker documents that containers have no resource limits by default. Its CLI
provides CPU/memory/pids constraints, read-only root filesystems, capability
drop, `no-new-privileges`, seccomp, user selection, network control, and runtime
selection. Docker also warns that privileged containers are not secure
sandboxes, and control of the Docker daemon is effectively host-level authority.

Disposition: retain Docker as QitOS's first reference backend, but replace
free-form construction with a typed deny-by-default policy and never expose the
host Docker socket inside an agent environment.

### Docker Sandboxes are closer to the desired local coding-agent product

Docker's agent sandbox product runs each sandbox in a microVM with its own
kernel, filesystem, network, and Docker daemon. It adds network policy,
host-proxy credential injection, and a private clone workflow. The default
direct workspace mount is still writable, so QitOS should request clone/private
workspace behavior for untrusted tasks. The product is evolving, therefore the
adapter must probe capabilities and pin evidence rather than infer by version.

Disposition: preferred high-isolation local adapter when available, especially
on developer desktops where installing a Linux KVM stack is undesirable.

### gVisor is the pragmatic stronger Linux container runtime

gVisor's `runsc` is OCI-compatible and integrates with Docker/Kubernetes. Its
userspace application kernel reduces direct exposure to the host kernel. The
official documentation also identifies incomplete syscall compatibility and
overhead for syscall-heavy workloads.

Disposition: first stronger self-hosted Linux/CI qualification target. It should
be selected by a backend/runtime capability, not by changing tool code.

### Firecracker/Kata belong behind an infrastructure adapter

Firecracker supplies hardware-virtualized microVM isolation, but production
security depends on KVM-capable Linux hosts, seccomp, jailer, cgroups/namespaces,
host/kernel/microcode patching, network/image/storage operations, and one-tenant
process boundaries. Raw Firecracker is a VMM rather than an agent sandbox SDK.

Disposition: QitOS should integrate an operator-owned Firecracker/Kata service,
not grow a second infrastructure orchestrator inside `qitos`.

### Managed sandboxes provide useful lifecycle references

- E2B presents fast agent-oriented Linux VMs and documents filesystem+memory
  pause/resume, snapshots, lifecycle events, metrics, and secured access.
- Daytona exposes container and VM classes; VM sandboxes support pause/resume,
  hot snapshots, fork, and explicit fork lineage, while container capabilities
  are narrower.
- Modal exposes gVisor-backed secure containers, resource/time limits, filesystem
  snapshots/forks, and experimental memory snapshots; its documentation records
  TTL and connection/process limitations.

Disposition: optional extras only. The first managed-adapter spike should use
the same public conformance suite as Docker. E2B is the first agent-centric
candidate; Daytona is the strongest semantic comparison for Session fork;
Modal is the scale/snapshot comparison. No vendor becomes canonical framework
state.

### Process sandboxes are valuable but lower-assurance

Codex uses OS-specific filesystem/network policies, including Seatbelt on macOS
and Landlock/bubblewrap paths on Linux. Anthropic's open sandbox runtime likewise
uses macOS native sandboxing and bubblewrap on Linux with proxy network policy.
Bubblewrap itself explicitly states that it is a policy construction tool, not a
complete security policy.

Disposition: add a low-latency local process backend for trusted or reviewed
work, clearly separated from the microVM/multi-tenant assurance level.

## Recommended product posture

QitOS should expose assurance classes, not vendor marketing labels:

- `workspace_process`: local OS policy, fastest, lower assurance;
- `container`: hardened OCI container, compatibility baseline;
- `sandboxed_container`: gVisor or equivalent stronger container runtime;
- `microvm`: separate guest kernel for untrusted/multi-tenant work; and
- `managed`: a remote implementation whose actual assurance class is still
  reported independently.

These are capability facts, not separate public APIs. A caller asks for required
properties; the resolver selects a compatible backend or fails typed.

Default selection policy:

- file-writing or command-running research/coding agents require an exclusive
  `research_coding` sandbox and never silently fall back to the host;
- child work items receive independent sandboxes unless an explicit read-only or
  ownership-compatible sharing policy is qualified;
- read-only conversational agents may request the lower-overhead process class;
  and
- direct host execution is an explicit unsafe/development mode whose use is
  visible in Session, WorkGraph, and Trajectory receipts.

Recommended rollout order:

1. canonical contract and fake conformance backend;
2. hardened Docker with private workspace and deny-by-default resources/network;
3. Docker Sandboxes for desktop plus gVisor for Linux CI;
4. one managed adapter, initially E2B, with Daytona/Modal comparison receipts;
5. Session/WorkGraph/Trajectory integration and public coding-agent example; and
6. Firecracker/Kata service adapter only when a real operator environment exists.

## Planning consequences

- Task 14 becomes a required S4 framework task, not a CyberGym-only feature.
- Lane C owns sandbox lifecycle/runtime adapters; Lane A owns Session
  identity/restore binding; Lane B owns credential/context transfer boundaries;
  Lane D owns redacted sandbox receipts, qita, evaluation, and DX.
- G5 cannot make the default coding-agent readiness claim until one local
  backend passes real escape/egress/resource/cleanup tests and one independent
  adapter passes the public conformance suite.
- Live-model agent trajectories use a disposable sandbox. They do not run in the
  primary QitOS checkout or receive production repository credentials.

## Sources

- [Docker Sandboxes](https://docs.docker.com/ai/sandboxes/)
- [Docker Sandboxes security model](https://docs.docker.com/ai/sandboxes/security/)
- [Docker resource constraints](https://docs.docker.com/engine/containers/resource_constraints/)
- [Docker rootless mode](https://docs.docker.com/engine/security/rootless/)
- [Docker seccomp profiles](https://docs.docker.com/engine/security/seccomp/)
- [gVisor overview](https://gvisor.dev/docs/)
- [gVisor security introduction](https://gvisor.dev/docs/architecture_guide/intro/)
- [Firecracker README](https://github.com/firecracker-microvm/firecracker/blob/main/README.md)
- [Firecracker production host setup](https://github.com/firecracker-microvm/firecracker/blob/main/docs/prod-host-setup.md)
- [E2B documentation](https://docs.e2b.dev/)
- [E2B persistence](https://docs.e2b.dev/sandbox/persistence)
- [Daytona sandboxes](https://www.daytona.io/docs/sandboxes)
- [Daytona persistence](https://www.daytona.io/docs/en/persistence/)
- [Modal Sandboxes](https://modal.com/docs/guide/sandboxes)
- [Modal snapshots](https://modal.com/docs/guide/sandbox-snapshots)
- [Anthropic Sandbox Runtime](https://github.com/anthropic-experimental/sandbox-runtime)
- [Codex core sandbox notes](https://github.com/openai/codex/blob/main/codex-rs/core/README.md)
