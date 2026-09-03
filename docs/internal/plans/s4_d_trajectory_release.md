# S4 Lane D — Trajectory, qita, evaluation, export, and distribution

Status: Lane D candidate qualified; waiting on the exact S4 A/B/C producers
Source: `c4e621d05960a4e2f06cb4864f6a8cb8275ac067`
Branch: `codex/v4-s4-d-trajectory-release`
Worktree: recorded in the dispatch handoff, never serialized into public evidence

## Non-negotiable readiness state

Until G5 replays and verifies the exact S4 A/B/C producer manifests:

```text
status=waiting_on_a_b_c
schema_frozen=false
default_writer_enabled=false
default_reader_switched=false
publication_ready=false
```

The candidate types remain module-level and unfrozen. Frozen trace v1 remains
the qita default. This lane does not modify an Engine/Session producer, enable a
default, publish a distribution, or use S3 evidence as an S4 producer receipt.

## File leases

```text
Lease owner: S4 Lane D
File(s): qitos/tracing/**, bounded qitos/trace/** compatibility reader changes,
         qitos/qita/**, qitos/evaluate/**, qitos/metric/**,
         trajectory/export/qualification/benchmark scripts, setup/package metadata,
         Lane D tests and tests/fixtures/s4/lane_d/**, this plan
Semantic purpose: candidate data-plane durability, read-only inspection,
                  evaluation/export/privacy/publication and distribution evidence
Expected start/end package: D1 census through D5 G5 handoff
Other lanes blocked or adapter supplied: no producer files are edited; exact
                  event/snapshot field requests are recorded as G5 handoffs
```

High-conflict lease: `setup.py` is touched only for the S4 packaging/extras
inventory and isolated install harness. `qitos/qita/_cli_app.py` is touched only
if a read path cannot be routed through the existing reader seam. README,
README.zh, CHANGELOG, progress, docs/v4, navigation, root/core/engine exports,
Engine events, and snapshot producers remain untouched per dispatch.

## Work plan

- [x] Verify fixed source, clean initial tree, branch, worktree, and exact merge-base.
- [x] Record the exact writer/reader census and canonical/derived/compatibility ADR.
- [x] Complete the candidate identity, ordering, lineage, lifecycle, provider,
      tool/effect, artifact, sandbox, budget, steering, compaction/loss,
      uncertainty, provenance, and integrity vocabulary without freezing it.
- [x] Qualify memory, crash-safe local, and independent third-party-style stores
      for atomic append, flush/close, reopen, partial-tail recovery, corruption,
      digest, index rebuild, bounded queries/replay, concurrency, I/O failure,
      ArtifactRef, and serialization isolation.
- [x] Qualify required/optional sinks and backpressure without Engine-private access.
- [x] Route qita board/session/graph/timeline/item/attempt/ownership/budget/
      sandbox/loss/replay/export/live polling through a read-only reader boundary.
- [x] Add store-independent evaluator input and third-party evaluator/exporter proof.
- [x] Add exact canonical, redacted public, and deliberately lossy exports with
      exhaustive machine-readable loss declarations.
- [x] Add raw/private, redacted/public, safe-diagnostic and publication qualification
      for secrets, paths, endpoints, cycles, depth, and oversized containers.
- [x] Run reproducible repeated storage measurements for both representative sources;
      emit typed not-ready rather than empty success when sources are not qualified.
- [x] Audit extras and run build/twine plus fresh-wheel base/optional and two offline
      consumer smokes using installed stable/extension APIs only.
- [x] Commit S4 Lane D fixtures, producer/readiness/qualification manifests and digests.
- [x] Publish exact G5 regeneration, switch, parity, rollback, and documentation patch
      steps while retaining the independent-lane waiting state.
- [x] Run targeted, full, static, packaging and diff validation and review the diff.

## Source census and ADR

### Writer census at the fixed source

| Plane | Current producer/writer | Authority classification | Consumers / notes |
|---|---|---|---|
| frozen trace v1 | `qitos/engine/_trace_runtime.py` -> `qitos/trace/writer.py` | compatibility artifact; current default | Writes `manifest.json`, `events.jsonl`, and `steps.jsonl`; qita, debug replay, HF upload, leaderboard, CLI/demo discovery, and legacy evaluation consume these bytes. |
| legacy processor | `qitos/tracing/legacy_processor.py` -> `qitos/trace/writer.py` | derived-to-compatibility adapter | Converts span lifecycle into frozen `TraceEvent`; not a second canonical runtime authority. |
| tool fan-out/delegate trace | `qitos/kit/tool/fanout.py`, `qitos/kit/tool/delegate.py` | compatibility artifact | Direct `TraceEvent` emission exists for old tool adapters. It does not prove durable WorkGraph authority. |
| span tracing | `qitos/tracing/provider.py`, processors, W&B/MLflow/JSON/console processors | derived diagnostic view | Span records are observability data. They must not become runtime/session truth. |
| configured candidate store | `qitos/config/builder.py` -> `TrajectoryStoreEventSink` -> `JsonTrajectoryStore` | unfrozen candidate, opt-in | Existing baseline integration only. It is not the default writer and this lane does not change its config or runtime wiring. |
| candidate durable store | `qitos/tracing/journal_store.py` | unfrozen candidate storage authority for supplied records | One checksummed transaction frame per batch, fsync before receipt, verified digest chain, tail recovery, disposable index. It does not create producer facts. |
| session/checkpoint stores | `qitos/checkpoint/**`, Engine snapshot/session runtime | runtime/session authority, outside trajectory lease | Referenced by ID only. Trajectory never replaces checkpoint or Session state. |
| render event log | `qitos/core/agent_module.py` and benchmark render options | product rendering artifact | `render_events.jsonl` is not trajectory authority. |

The candidate adapter accepts structural runtime/engine/trace/step/span inputs but
never treats a derived stream as canonical merely because it has an event-like
shape. Exact A/B/C producer ownership, occurrence time, monotonic order, IDs,
attempts, lifecycle, effect, sandbox, and work facts must arrive from the owning
producer. Lane D only copies explicit fields; it never parses ID suffixes or
reconstructs missing facts from text.

### Exact fact-source census

| Required fact | Current exact source / reader | Classification and S4 blocker |
|---|---|---|
| Session lifecycle | Session runtime and durable Session head/snapshot | canonical runtime state; exact S4 A receipt absent |
| run lifecycle | RuntimeEvent plus frozen trace manifest/event | runtime event canonical, frozen file compatibility; exact A receipt absent |
| snapshot/checkpoint/head | Session snapshot/checkpoint stores | canonical runtime state referenced by candidate; exact A snapshot wiring receipt absent |
| model request/response | RuntimeEvent model input/output stages | canonical runtime fact; exact B transaction/message ordering receipt absent |
| reasoning/continuation | provider transaction payload when explicitly emitted | canonical only with B ownership; otherwise unknown/loss |
| tool batch/slot/result | runtime tool-stage events | canonical only from C tool execution producer; exact result/ACI receipt absent |
| effects | tool terminal effect plus effect runtime | canonical only from C effect authority; late/outcome-unknown receipt absent |
| artifacts | `ArtifactRef` from producer/artifact store | reference canonical, bytes external; B/C exact artifact ownership absent |
| sandbox attestation/cleanup | sandbox runtime/cleanup producer | canonical only from C; unavailable on this host for Docker E2E and exact C receipt absent |
| context selection/compaction/loss | context/runtime/provider publications | selection facts canonical, projections derived; exact B receipt absent |
| steering | Session/runtime steering event | canonical runtime fact; A/B exact producer receipt absent |
| budgets/usage | runtime budgets and provider usage | canonical if emitted by owning runtime/provider; B usage/failure receipt absent |
| WorkGraph | durable work runtime and Session work operations | canonical runtime state; reader graph is derived; exact C receipt absent |
| ownership/fencing/generation | Session/work durable owner generation | canonical runtime state; exact A/C identity-conflict receipt absent |
| delegate/spawn/fan-out/handoff/join | Session/work runtime operation records | canonical runtime facts; direct old tool trace events are compatibility only |
| cancellation/late/outcome_unknown | work/effect lifecycle producer | canonical only when explicitly emitted; exact C receipt absent |
| trace v1 | `TraceWriter`, trace manifest/events/steps | frozen compatibility source |
| spans | tracing provider/processors | derived diagnostic plane |
| renderer | render hooks/events and render JSONL | derived product view |
| qita | `TrajectoryReader` -> qita payload/read models | derived read-only view; frozen compatibility remains default |
| replay/fork | reader replay plus Session/checkpoint fork runtime | replay derived from records; fork mutation remains Session-owned and out of qita |
| evaluation/metric | bounded `EvaluationView`, `MetricInput`/`MetricReport` | derived judgement with schema/provenance/loss |
| exporters | canonical/public/summary exporters | exact selected view or explicitly lossy derived artifact |
| HF/leaderboard | frozen trace filename/manifest readers | compatibility/deprecated integration candidates |
| package examples | installed coding and research consumer fixtures | distribution consumers, never producer authority |

### Reader and exporter census at the fixed source

| Consumer | Current source | S4 disposition |
|---|---|---|
| qita default | `qitos/qita/reader.py::default_reader` -> `TraceCompatibilityReader` | Remains the qualified default until G5. |
| qita explicit candidate | `candidate_file_reader` / `StoreTrajectoryReader` | Additive opt-in. Persisted records are restored exactly and never resequenced. |
| qita UI/CLI/server | `qitos/qita/data.py`, `_cli_app.py`, `server.py`, `views.py` | Existing payload seam retained; new `ReadOnlyInspection` offers candidate board/session/graph/timeline/item/attempt/ownership/budget/sandbox/loss/replay/export/poll views without mutation methods. |
| work graph inspection | `qitos/tracing/work_graph_reader.py` | Derived read model over any `TrajectoryReader`; absence remains unknown/lossy for historical traces. |
| evaluation | `qitos/evaluate/base.py` | Legacy file loader retained; new bounded `EvaluationView` is selected from a reader by run, Session, or work item and contains no store handle. |
| debug replay | `qitos/debug/replay.py` | Direct frozen-file compatibility consumer; not changed independently. |
| HF publishing | `qitos/hf/hub.py` | Direct frozen-file compatibility consumer; publication requires G5 migration/compatibility decision. |
| leaderboard | `qitos/leaderboard/store.py` | Manifest compatibility consumer; not canonical evidence. |
| CLI/demo discovery | `qitos/cli.py`, `qitos/demo/minimal.py` | Frozen-manifest compatibility consumers; shared files remain untouched. |
| canonical export | `CanonicalTrajectoryExporter` | Exact re-import for the selected privacy view with content digest. |
| public export | canonical exporter + `REDACTED_PUBLIC` / `SAFE_DIAGNOSTIC` projection | Re-importable projected view; projection loss is explicit and publication is separately gated. |
| event summary | `EventSummaryExporter` | Deliberately lossy; declares payload, reasoning, continuation, tool ordering, effects, sandbox, ownership, work graph, artifact, and uncertainty omissions. |

### ADR: one authority, three roles

Decision: retain one candidate `TrajectoryRecord` vocabulary with an explicit
`role` field:

- `canonical_runtime_fact` is accepted only from a producer that owns the fact.
- `derived_view` is query/export/diagnostic material and cannot recover authority.
- `compatibility_artifact` preserves frozen trace v1 facts and carries declared
  lineage/fidelity loss.

Session/checkpoint remains the source of durable runtime state. Artifact bodies
remain in artifact storage and are referenced by `ArtifactRef`; the trajectory
does not duplicate blob bytes. Frozen trace v1 remains the historical contract
and default qita source. Span tracing remains a derived plane. This prevents the
candidate from creating a third state truth while allowing one future data plane
after exact-source qualification.

Rejected alternatives:

1. Treat spans as canonical: rejected because sampling/processor failure and
   derived timing cannot own Session or effect truth.
2. Promote frozen trace v1 directly: rejected because it lacks durable Session,
   work-item, attempt, ownership, sandbox, provider-transaction, and uncertainty
   fields required by S4.
3. Infer missing IDs/order from names or list position: rejected because it makes
   replay appear stronger than producer evidence.
4. Switch qita or the runtime writer inside Lane D: rejected because A/B/C exact
   producers and G5 parity/rollback evidence are absent.

### Removal candidates and blockers

No surface is removed in Lane D. These are candidates for a later G5/post-G5
deprecation decision, not proof that external users do not exist.

| Candidate | Known consumer | Replacement | Required warning/test | Current blocker |
|---|---|---|---|---|
| direct qita frozen-file parsing | qita CLI/server/data | reader selector backed by canonical store plus `TraceCompatibilityReader` | deprecation warning; golden historical payload parity | exact A/B/C producer intake and G5 default switch absent |
| `evaluate.load_run_artifacts` | evaluators/benchmarks | `evaluation_view_from_reader` | compatibility tests for manifest/events/steps inputs | external consumer inventory unknown |
| `debug/replay.py` direct JSONL reads | debug workflows | `TrajectoryReader.replay` | replay parity and corrupt-history tests | debug package lease and historical UX decision |
| HF hard-coded trace filenames | HF publisher | qualified canonical/public export artifact | clean-wheel publish dry-run, license/privacy gate | publication policy and G5 artifact format decision |
| leaderboard manifest-only ingest | leaderboard | evaluator/export result envelope | legacy submission compatibility fixture | public leaderboard schema decision |
| legacy span processor to TraceWriter | tracing users | explicit diagnostic sink plus compatibility exporter | warning and W&B/MLflow/JSON parity | span API external-use inventory unknown |
| direct tool adapter `TraceEvent` writes | fan-out/delegate adapters | owning C producer emits canonical work/effect facts | WorkGraph lifecycle parity and ownership receipts | exact Lane C producer absent |

### Candidate contract and store qualification summary

The unfrozen record vocabulary covers explicit identity, sequence, timestamps,
monotonic timestamp, Session/run/work/step/phase/agent, snapshot/checkpoint,
exchange/tool/attempt/owner generation/operation/lifecycle/provider transaction/
effect/sandbox, source and parent lineage, producer authority, provenance,
causation/correlation, `ArtifactRef`, privacy view, loss, and digest. Required
new producer fields remain `unknown`/absent rather than synthesized.

`JournalTrajectoryStore` qualifications are executable in
`tests/tracing/test_s4_journal_store.py`: abrupt process exit, reopen, atomic
batch append, final partial-frame recovery and reporting, rejection of complete
corruption and checksum mismatch, two-handle serialized writers, I/O rollback,
bounded queries, replay, index deletion/rebuild, record integrity, and artifact
reference behavior. Its JSON index is never authoritative and is rebuilt from
the verified journal. `MemoryTrajectoryStore` remains the lightweight reference;
`JsonTrajectoryStore` remains the bounded whole-file compatibility candidate.

Required/optional sink failure policy, explicit receipts, flush/close,
backpressure, safe projection, third-party structural conformance, and absence of
Engine-private state are covered by `tests/test_event_sink_conformance.py` and
the Lane D store/evaluator/exporter suites.

## Measurement and distribution evidence

The source fixture is measurement-only and explicitly not runtime-producer
evidence. It contains two deterministic representative shapes expanded to 300
coding/tool records and 400 research/tool records. Three repetitions were run on
CPython 3.12.7, macOS 15.7.3 arm64, zstandard 0.23.0. Results are observations,
not performance or compression claims:

| Source | canonical JSON | gzip | zstd | journal | index | artifact refs / unique |
|---|---:|---:|---:|---:|---:|---:|
| coding/tool | 400,161 B | 16,985 B | 14,425 B | 402,562 B | 3,656 B | 100 / 1 (12,800 B referenced, 128 B unique) |
| research/tool | 504,151 B | 22,111 B | 18,698 B | 507,252 B | 4,862 B | 0 / 0 |

Median observed nanoseconds (memory append / journal append / reopen / query /
replay / index rebuild) were respectively
`79,610,541 / 302,344,625 / 248,629,209 / 316,026,166 / 350,334,083 / 310,419,292`
and
`92,749,625 / 328,332,917 / 348,419,167 / 407,636,875 / 405,725,667 / 348,754,625`.
The harness records all repetitions, platform identity, tracemalloc peak, process
RSS platform units, record counts, zstd availability/version, and emits typed
`not_ready` with no measurements/claims for missing or invalid sources.

Distribution qualification built `qitos-0.6.0-py3-none-any.whl` and the sdist,
passed twine metadata checks, verified candidate files in the wheel, and installed
the wheel into fresh environments for every advertised profile: base, OpenAI,
Anthropic, Gemini, LiteLLM, local, models, qita, Docker, MCP, evaluation, YAML,
benchmarks, W&B, MLflow, cookiecutter, HF, web, dev, and all. The base profile
also ran `qit --help`, `qita --help`, canonical YAML config loading, and two
offline installed-consumer programs. Those programs use public framework APIs
and documented extension modules only; they contain no `qitos._*`/test imports,
do not call a live model, and do not use the repository source path.

Final qualified wheel digest:
`4d9e06daca887c56daaa433edd1412634d3aece5dc200c95d93347bcc4bea09a`.
The sdist digest is
`c9a408cb0e2c8dd36c334258ad077653cff95098818b6ec14dd89df14236ac38`.
G5 must rebuild and record new digests after merging A/B/C rather than reuse
either Lane D artifact.

## G5 exact handoff

The machine-readable companion is
`tests/fixtures/s4/lane_d/g5-switch-rollback-manifest.json`. G5 must execute this
order and stop on any mismatch:

1. Merge exact S4 A/B/C commits and verify every `git show COMMIT:PATH` SHA-256,
   schema, producer authority, consumer test node, and identity-conflict flag
   against `a-b-c-readiness-inventory.json`.
2. Run `qualify_s4_readiness`; an S3 receipt, working-tree file, branch name,
   self-declared fixture, missing test, or wrong digest remains rejected.
3. Regenerate Lane D candidate records from the exact producer commits. Compare
   all explicit identity/order/lineage/lifecycle/provider/tool/effect/artifact/
   sandbox/budget/steering/compaction/loss/uncertainty fields. Missing facts stay
   unknown and block the affected qualification.
4. Repair producer-owned wiring only in its owning lane. Do not teach a Lane D
   adapter to infer a fact that the producer failed to emit.
5. Run store crash/reopen/corruption/concurrency and reader parity suites against
   both golden paths. Verify one authoritative record per fact and no artifact
   body duplication.
6. Make a separate schema-freeze commit only after review. Record schema version,
   migration behavior, exact producers, and compatibility reader lifetime.
7. Enable the candidate writer for the two golden paths behind one reversible
   selector. Verify required sink failures stop the owning run and optional sink
   failures remain explicit loss/receipts.
8. Switch qita through the existing reader selector; retain exactly one bounded
   frozen trace v1 compatibility reader. Run payload, ordering, loss, graph, and
   polling parity before changing the default.
9. Re-run the three-repetition measurement harness with regenerated exact-source
   fixtures. Do not compare unlike hardware/toolchains or promote synthetic
   observations into product claims.
10. Rebuild sdist/wheel, run twine, every extras profile, canonical config, both
    installed consumers, secret/path/endpoint scans, license checks, and
    deterministic transform receipts.
11. Exercise rollback: restore the frozen writer/reader selectors, open the same
    historical trace, open candidate bytes explicitly, and prove no data deletion
    or Session/checkpoint mutation.
12. Apply shared documentation changes only after the switch and rollback pass.
    If any gate fails, revert the selector commit while retaining additive reader
    and compatibility support.

Suggested command skeleton (G5 substitutes exact merged commits and paths):

```bash
pytest -q tests/tracing tests/qita tests/test_event_sink_conformance.py \
  tests/test_trajectory_store_conformance.py \
  tests/test_trajectory_exporter_conformance.py \
  tests/test_evaluator_conformance.py
python scripts/measure_trajectory_store.py \
  --fixture tests/fixtures/s4/lane_d/storage-measurement-manifest.json \
  --repetitions 3
python -m build
python -m twine check dist/*
python scripts/qualify_wheel_distribution.py --wheel dist/QITOS_WHEEL \
  --coding-consumer tests/fixtures/s4/lane_d/installed_coding_consumer.py \
  --research-consumer tests/fixtures/s4/lane_d/installed_research_consumer.py \
  --config tests/fixtures/s4/lane_d/installed-agent.yaml
python scripts/static_quality.py check
pytest -q
```

Rollback trigger codes include producer digest mismatch, identity conflict,
record or journal integrity failure, parity mismatch, undeclared loss, public
payload scan failure, optional-profile install/import failure, or installed
consumer failure. Rollback never deletes journal, trace, artifact, checkpoint, or
Session bytes.

## Patch-ready public documentation drafts

Lane D does not edit shared public files. After G5 succeeds, apply the following
facts with the final frozen version and exact evidence substituted:

**README What's New (EN)**

> QitOS now uses one canonical, durable Trajectory data plane for runtime facts,
> qita inspection, evaluation, and export. Historical trace v1 runs remain
> readable through the compatibility reader. Public exports are redacted,
> content-bound, and carry explicit fidelity loss.

**README 最新进展 (ZH)**

> QitOS 现已使用统一、可持久化的 Trajectory 数据面承载运行事实、qita
> 检查、评测与导出。历史 trace v1 仍可通过兼容读取器访问；公开导出经过
> 脱敏和内容绑定，并显式记录保真度损失。

**CHANGELOG / docs release note (EN)**

> Added the frozen Trajectory schema and durable journal store; routed qita and
> evaluator inputs through the read-only reader contract; added exact, public,
> and explicitly lossy exports plus artifact-level publication qualification.
> The switch retains one bounded trace v1 compatibility reader and a tested
> selector rollback.

**CHANGELOG / docs release note (ZH)**

> 新增冻结版 Trajectory schema 与持久化 journal store；qita 与评测输入统一
> 通过只读 reader contract；新增精确导出、公开脱敏导出、显式有损导出及
> artifact 级发布资格校验。切换后保留一个有边界的 trace v1 兼容读取器，
> 并验证 selector 回滚路径。

These drafts are conditional. They must not be published while the state at the
top of this plan remains `waiting_on_a_b_c`.

## Qualification ledger

- Focused Lane D and existing trajectory/config suites: passed.
- Module-level architecture boundary check: passed after keeping qita imports lazy.
- Targeted flake8 for every changed Python file: passed.
- Targeted mypy for every changed Lane D module: passed.
- Full-package static quality ratchet: passed with 367 baselined findings
  (345 active, 22 vendored/generated); no baseline file changed.
- Full pytest first pass: 2,456 passed, 50 skipped; three discovered regressions
  were repaired. The remaining failure is the pre-existing Docker-qualified S3
  E2E because the configured sandbox backend is unavailable on this host.
- Post-fix pytest with that configured-Docker recovery file excluded: 2,470
  passed, 50 skipped. The only two failures were also Docker-host conditions: a
  real sandbox write probe failure and a later Docker inspect timeout reported as
  sandbox unavailable. All tests outside those Docker probes completed.
- Build, twine, wheel content, 20-profile fresh installs, both installed consumers,
  and repeated storage measurements: passed as described above.
- Exact commit/digest ledger: passed. Final readiness remains waiting on A/B/C.
