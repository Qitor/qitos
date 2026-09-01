# ADR: one declarative AgentConfig composition root

Status: accepted for S3 G4-L2 implementation
Updated: 2026-09-01
Owner: G4 integration owner
Fixed integration source: `851f7902f15da670e72f4c04d7453cf37201aee7`
Candidate starting head: `bd0f93328ccb37b66e62855de8ad489916c47e1e`

## Decision

QitOS has one declarative launch configuration named `AgentConfig`. The only
golden path is:

```text
agent.yaml -> strict loader -> AgentConfig -> composition builder
           -> existing model/tools/Env/runtime/session/trace objects
           -> existing AgentModule + Engine
```

`qit run --config agent.yaml` and the Python API consume the same loader,
schema, credential resolver, composition builder, `AgentModule`, and `Engine`.
There is no `V1`, `V2`, `Legacy`, `Next`, provider-specific launch config, or a
second engine/session/environment/tool/checkpoint/trajectory implementation.

`qitos.config` owns parsing, validation, canonical serialization, source and
loss receipts, credential-reference resolution at composition time, and
assembly of existing runtime objects. Runtime behavior remains owned by the
existing modules that implement it.

## Exact-source census before implementation

The census was run from the clean candidate at
`bd0f93328ccb37b66e62855de8ad489916c47e1e` after verifying merge-base
`851f7902f15da670e72f4c04d7453cf37201aee7`.

| Surface | Existing authority | Finding and convergence action |
|---|---|---|
| Config type/loader | `qitos/config/loader.py` | Existing `AgentConfig` is retained and evolved. The loader currently coerces values, ignores unknown fields, expands ambient environment variables, and silently substitutes missing variables with empty strings; all four behaviors become strict or explicitly receipted compatibility behavior. |
| Runtime builder | `qitos/config/builder.py` | Existing `build_model`, `build_run_spec`, and `build_tool_registry` are reused and extended into the sole composition root. Direct provider construction in qualification code is removed. |
| CLI | `qitos/cli.py` | No `run` command exists. Add a thin `run` dispatch to `qitos.config`; do not put launch logic in the CLI. |
| Agent/kernel | `qitos/core/agent_module.py`, `qitos/engine/` | Reuse the existing `AgentModule`, `Engine`, `RuntimeComposition`, session facade, checkpoint stores, and model protocol machinery. |
| Model creation | `qitos/models/provider.py`, `qitos/models/openai.py` | Keep `ModelFactory` and `OpenAICompatibleModel`. A resolved secret may be passed only during composition; no config object or receipt contains it. |
| Tool presets | `qitos/kit/toolset/` | Reuse preset registry builders. Launch composition selects a bounded allowlist; arbitrary imports remain an explicit compatibility path with a receipt. |
| Environments | `qitos/core/env.py`, `qitos/engine/_env_runtime.py`, `qitos/kit/env/` | Reuse the one `Env` passed to every model-visible tool. Add qualification hardening to the existing Docker environment layer; never fall back to `HostEnv` or host subprocess execution. |
| Sessions/checkpoints | `qitos/engine/session_runtime.py`, `qitos/checkpoint/` | Reuse durable session snapshots and resolver-reference persistence. Secrets are re-resolved from logical references after restore and are never snapshotted. |
| Trace/trajectory | `qitos/trace/`, `qitos/tracing/` | Existing trace-v1 compatibility and v2 span planes are unchanged. Launch evidence binds their configured policy and declares loss; this task does not freeze a new trajectory schema. |
| Live qualification | `scripts/qualify_s3_live.py` | Existing runner reads Markdown, depends on three `QITOS_LIVE_*` variables, directly constructs models, accepts hand-authored sandbox booleans, and cannot reach a passed agent workflow. Replace those paths with loaded configs, injected resolvers, executable sandbox attestations, and real workflow receipts. |
| Tests | `tests/test_yaml_config.py`, `tests/test_config_security.py`, `tests/test_s3_live_qualification.py` | Existing tests encode permissive/missing-env behavior and the old runner. Replace/add strict, secret-safe, fake-provider, restore, real-Docker, digest-binding, and reachable-success gates. |
| Official YAML templates | `templates/*/config.yaml` | Twelve method templates exist; nine model-bearing templates reference `${OPENAI_API_KEY}`. Migrate those nine to `credential.ref`. The three orchestration-only templates have no credential field and remain listed as intentionally unchanged. |
| Python examples and benchmark docs | `examples/`, `docs/benchmarks/`, `docs/reference/` | Many still teach ambient environment variables. They are outside the bounded YAML migration for this slice and remain an explicit follow-up list; docs must identify the canonical path and label environment lookup compatibility-only. |

## Canonical schema and strictness

The YAML root contains `schema`, `agent`, `model`, `tools`, `runtime`, and
`budgets`; optional `context` and `metadata` remain JSON/YAML-safe mappings.
Every mapping has an exact key set. Unknown fields, wrong types, non-finite
numbers, invalid enums, duplicate keys, unsafe YAML tags, and ambiguous scalar
coercions fail closed with a typed configuration error. Defaults are declared
by the schema and appear in canonical serialization.

The canonical serializer is stable-key, JSON-safe, secret-free, and the only
input to configuration digests. It records `schema`, normalized values,
`source` identity, compatibility receipts, and declared loss. It never records
resolved credential values, authorization headers, provider response bodies,
or private host paths in public evidence.

The previous flat YAML shape remains a bounded compatibility adapter for
current experiment callers and method templates during migration. It must
reject unknown fields unless the caller explicitly enables compatibility mode,
and every accepted transformation emits a deterministic receipt. New launch
files use only the canonical nested shape.

## Credential authority

`CredentialRef` is the serializable identity. `CredentialResolver` is a
replaceable boundary used only while composing the model client:

- `LocalCredentialFileResolver` is the live authority. It accepts one fixed
  file outside the repository and verifies regular-file/non-symlink status,
  current ownership, mode `0600`, non-group/world-writable parent, strict YAML
  mapping shape, and the requested reference only.
- `FakeCredentialResolver` is deterministic test authority.
- `EnvironmentCredentialResolver` is compatibility-only, must be selected
  explicitly, and emits a warning/compatibility receipt. Missing variables are
  typed failures, never empty strings.

Secrets do not enter `AgentConfig`, canonical serialization, digests,
snapshots, checkpoints, manifests, exceptions, logs, or public evidence.
Subprocesses and containers receive no implicit credential inheritance.
Restored sessions persist and re-resolve the logical reference.

## Sandbox qualification boundary

G4-L2 adds an executable qualification harness around the existing Docker
environment; it does not claim the complete Task 14 runtime. The harness creates
a fresh labeled container with an explicit image digest, non-root user,
`network=none`, read-only root filesystem, dropped capabilities,
`no-new-privileges`, PID/memory/CPU/file limits, bounded tmpfs, and an explicit
workspace mount. It inspects Docker's actual state and runs capability,
read/write/test, denial, repository-digest, mount, and cleanup probes.

The resulting receipt binds container ID, image/config/policy/workspace
digests, environment/session/run/work-item identities, creation time, probe
results, and cleanup result. No caller-supplied all-true JSON can satisfy this
gate.

## Promotion gate

No real provider request is allowed until all sixteen offline gates pass. No
promotion is allowed until all three configured providers pass preflight and
at least one real tool route plus single-agent and multi-agent clean-process
restore workflows pass with executable evidence. A missing or invalid local
credential, unavailable Docker runtime/image, failed tool/sandbox assertion,
provider failure, workflow failure, source drift, or digest mismatch is a
typed block and preserves every worktree.

Promotion is fast-forward-only from the candidate into
`feat/campaign-absorption`, followed by full revalidation, push, exact remote
verification, and only then removal of the five completed source worktrees.

## Deliberate non-claims

This decision does not add a second kernel, freeze a trajectory schema, claim
the complete Task 14 sandbox/runtime, change the default branch, create a
release, deploy a service, or authorize unbounded model requests.

