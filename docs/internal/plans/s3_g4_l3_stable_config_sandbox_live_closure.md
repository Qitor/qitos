# S3 G4-L3 stable config, sandbox truth, and live workflow closure

Status: R1 transport passed live dispatch; deterministic qualification setup repairs pending committed-byte requalification
Updated: 2026-09-02
Owner: G4 integration owner
Fixed baseline: `851f7902f15da670e72f4c04d7453cf37201aee7`
Candidate branch: `codex/v4-s3-g4-convergence`
Starting candidate: `904df84ff3bd601cef6fae2199d66b3867aeaa1d`

## G4-L3-R1 repair checkpoint

The immutable historical round `s3-g4-l3-71564b10447bf692` remains unchanged.
R1 removes the deterministic pre-request blocker through one bounded recursive
JSON materialization owned by the codec/provider execution boundary. It accepts
JSON scalars, finite floats, mappings, lists, and tuples into fresh dict/list
ownership, and rejects non-string keys, non-finite numbers, unsupported objects,
cycles, and depth/node exhaustion without echoing values. The same boundary is
used for provider payload isolation; builder, Engine, and live runner do not own
copies of the thaw algorithm.

EngineResult now carries the safe step/phase/root failure fact. Failed Session
heads persist that fact, and the live receipt records root error, lifecycle
consequence, pause reachability, and whether dispatch occurred. Focused Python
3.12.7 config/model/provider/Session/runner tests pass. This checkpoint is not
offline qualification, live evidence, promotion authority, or an S3 closure;
those gates must be rerun from committed R1 bytes.

Committed R1 head `bd9711d58436c008be81f5bd9d1b6af604b762fb`
passed the complete offline matrix (`2410 passed, 50 skipped`), the 16-node
runner gate, static ratchet, lint, types, build, twine, privacy, Docker, and
cleanup. Fresh immutable round `s3-g4-l3-1f3414e2567ef3f9` then proved the
transport repair with six real GLM requests and native read/grep/write/command
execution. It did not qualify the workflow: the local five-step ceiling stopped
before the final request, the qualification image lacked pytest, and a bounded
large qita projection omitted its metadata container. DSV and Qwen remained at
zero requests. The sanitized receipt is
`s3_g4_l3_r1_live_failure_receipt.json`; the private full receipt remains
outside Git with mode `0600`.

The follow-up keeps the prompt and 12-request ceiling unchanged, raises only
the local step ceiling, uses a locally attested qualification image containing
pytest, preserves bounded qita projection while rebuilding safe minimum
metadata, and maps step exhaustion to `engine_step_budget_exhausted`. A new
round is forbidden until these bytes are committed and every offline gate is
rerun.

## Scope and stop gate

This round repairs the existing G4-L2 candidate in place. It does not create a
second Engine, provider dispatcher, Session store, configuration runtime,
sandbox executor, WorkGraph, ToolResult, ExchangeLog, or Trajectory format.
No live provider request is allowed until the complete offline matrix passes.
Promotion, push, and worktree retirement remain conditional on every live and
repository gate passing.

## Exact-source census

The census was performed from the clean starting candidate after confirming
that its merge-base with the fixed integration source is the fixed source.

| Flow surface | Existing authority | G4-L3 finding and convergence action |
|---|---|---|
| YAML and Python configuration | `qitos/config/loader.py` | `qitos.agent/v1` is still the canonical public identity and loaded dataclasses remain deeply mutable. Retain `AgentConfig`, change the canonical identity to `qitos.agent`, isolate `/v1` as a reader-only compatibility revision, freeze loaded nested data, and make normalization copy-only. |
| Composition | `qitos/config/builder.py` | `ConfiguredAgent` always installs `ReActTextParser`, host is a normal/default environment, and trajectory settings are ignored. Resolve protocol/parser once before Engine construction, reject mismatches, make executable presets sandbox-first, and compose the existing EventSink/store. |
| Protocol and parser | `qitos/protocols.py`, `qitos/engine/engine.py`, `qitos/engine/_model_runtime.py` | The protocol registry already owns parser factories, but configured launches bypass it and Engine may silently walk fallback parsers. Configured launches will pass one resolved protocol/parser pair to the existing Engine path with fallback disabled by explicit parser selection. |
| Provider request and codec | `qitos/core/request_view.py`, `qitos/models/codec.py`, `qitos/models/provider.py` | Engine already has one `ExchangeLog -> RequestView -> ProviderAdapter -> ProviderCodec` path. Add protocol/tool-use policy facts to RequestView and CodecReport; policy-derived tool choice enters codec options on this path. The live preflight must consume this path instead of calling provider helpers directly. |
| Tool execution | `qitos/engine/_action_runtime.py`, `qitos/kit/toolset/env_coding.py` | The existing ActionExecutor and Env-only coding toolset are canonical. Record successful real execution in Engine state and prevent a required-tool policy from accepting an early text final. |
| Sandbox | `qitos/kit/env/docker_env.py`, `qitos/kit/env/docker_qualification.py`, `qitos/kit/env/host_env.py` | Docker hardening exists only as a qualification harness; host currently accepts Docker-only claims. Add a minimal structural sandbox backend/receipt contract and conformance checks, keep Docker as the one reference backend, name host execution `unsafe_host`, fail closed when Docker is unavailable, and never advertise unobserved host constraints. |
| Session/checkpoint | `qitos/engine/runtime.py`, `qitos/engine/session_runtime.py` | Runtime composition is already snapshotted, but it lacks launch digest and model policy facts. Add JSON-only launch provenance to the existing composition snapshot and reject restore on digest mismatch; do not add a store. |
| Trajectory | `qitos/engine/runtime.py`, `qitos/tracing/sinks.py`, `qitos/tracing/store.py`, `qitos/tracing/adapters.py` | Engine/Session already publish through the S2 EventSink seam, but config never supplies a sink. Compose `JsonTrajectoryStore -> TrajectoryStoreEventSink`, preserve required/optional failure policy, add config-loaded/sandbox-prepared provenance records, and close/flush through composition cleanup. |
| qita | `qitos/qita/reader.py`, `qitos/qita/_cli_app.py` | The read-only candidate-store reader already supports Session/graph/timeline through the public Trajectory reader protocol. Qualification must read the configured store through this seam, never harness-private JSON. |
| Live runner | `scripts/qualify_s3_live.py` | Preflight directly calls model tool helpers and forces `tool_choice=required`; workflow code duplicates policy and allowed a host override. Replace both with config-driven Engine composition, one request ledger per new round/profile, and immutable sanitized evidence. |
| Credentials | `qitos/config/credentials.py` | The local resolver already enforces a regular non-symlink `0600` file, owner checks, external location, and non-writable parent. Keep it as the only live authority and ensure neither sandbox env nor serialized provenance receives resolved values. |

## Work packages

1. Stabilize canonical config identity, deep immutability, deterministic digest,
   compatibility reader, typed diagnostics, and documentation examples.
2. Resolve protocol/parser/codec once and add the four-mode tool-use policy to
   RequestView, CodecReport, Engine enforcement, snapshots, and trace events.
3. Add the structural sandbox backend contract, truthful unsafe-host behavior,
   Docker fail-closed preparation/inspection/cleanup, and conformance tests.
4. Compose the existing candidate Trajectory sink/store and prove qita read-only
   Session/graph/timeline plus stable replay or export.
5. Prove deterministic single-agent and multi-agent clean-process workflows,
   then run all adversarial, static, packaging, privacy, and cleanup gates.
6. Only after package 5 is entirely green, start a new bounded live round in
   GLM -> DSV4 -> Qwen order. Stop immediately on the primary-profile blocker.
7. Only after every acceptance gate passes, commit evidence, fetch, recheck the
   fixed remote, fast-forward the primary checkout, revalidate, push without
   force, verify all three SHAs, and remove only the five named worktrees with
   non-forced `git worktree remove`.

## Deliberate non-claims

This round does not implement a distributed scheduler, external-effect
exactly-once delivery, Python-thread hard cancellation, another sandbox backend,
a frozen/public Trajectory schema, a default-branch change, a release, or a
deployment.
