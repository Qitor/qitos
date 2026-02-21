# QitOS Release Plan (TODO + Gap to Public Launch)

## 0) Executive Summary

Current status (based on repo state):
- Core mainline (`AgentModule + Engine`) is in place.
- Examples are practical and model-connected.
- Render/Hook/Trace baseline is usable.
- Test suite is green.

Distance to public release:
- Estimated readiness: **70%**
- Remaining work: **high-impact productization and standardization**, not basic coding.
- Suggested release horizon: **3-5 weeks** with focused execution.


## 1) Release Definition

QitOS is considered publish-ready only when all are true:
1. One canonical runtime story: `AgentModule + Engine`.
2. `Task` and `Env` are first-class core abstractions.
3. At least one public benchmark suite is runnable under `Task`.
4. Reproducibility contract is strict (trace + config + model/task identity).
5. Docs/tutorials are beginner-friendly and research-grade.
6. CI has regression gates for behavior, not only unit tests.


## 2) Priority Roadmap

## P0 (Blockers before release)

- [ ] **Task abstraction in core**
  - Add `qitos/core/task.py`.
  - Define `Task`, `TaskResource`, `TaskBudget`, `EnvSpec`.
  - Support file/dir/url/artifact resources and task-level constraints/success criteria.
  - Add serialization (`to_dict/from_dict`) + schema validation.

- [ ] **Env abstraction in core**
  - Add `qitos/core/env.py`.
  - Define minimal contract: `reset/observe/step/is_terminal/close`.
  - Keep tool-only mode fully backward compatible.

- [ ] **Engine integration for Task + Env**
  - `Engine.run(task: str | Task, **kwargs)` support.
  - Resource mounting/staging into workspace before run.
  - Optional env lifecycle orchestration via engine.
  - Include env outputs in `env_view`, trace, and render events.

- [ ] **Trace reproducibility hardening**
  - Mandatory fields: `task_id`, `task_hash`, `model_name`, `base_url`, `config_hash`, `tool_manifest`.
  - Add strict validator checks and fail-fast behavior for missing required fields.

- [ ] **Security and config hygiene**
  - Remove plaintext secrets from committed configs.
  - Provide `.env.example` and secure key-loading guidance.
  - Add secret-scan check in CI.


## P1 (Strongly recommended for v1.0)

- [ ] **Kit Env implementations**
  - `qitos/kit/env/repo_env.py` (SWE/coding workflows).
  - `qitos/kit/env/browser_env.py` (computer-use workflows).
  - `qitos/kit/env/document_env.py` (epub/pdf workflows).

- [ ] **Task loaders and dataset adapters**
  - YAML/JSON task loader under `qitos/kit/task`.
  - Manifest format for task packs.
  - Support local resource bundle and remote artifact fetch hooks.

- [ ] **Benchmark runner**
  - Add `qitos/bench/runner.py` for dataset-scale execution.
  - Standard outputs: success rate, latency, step count, cost proxy, failure taxonomy.
  - Baseline run artifacts for reproducibility.

- [ ] **Public benchmark suites (initial)**
  - `swe-mini` (patch + verify).
  - `web-task-mini` (research/report).
  - `doc-qa-mini` (epub/pdf QA).
  - `computer-use-mini` (multi-step tool operation).

- [ ] **Render to frontend-ready event contract**
  - Freeze event schema version.
  - Ensure all key nodes (plan/thinking/action/memory/critic/stop) have stable fields.
  - Document schema for future TensorBoardX-like UI.


## P2 (Post-release but should be planned now)

- [ ] **Evaluation plugins**
  - Pluggable evaluator interface for exact match, test-based, LLM-judge.
- [ ] **Multi-agent task support**
  - Parent/child task and shared env patterns.
- [ ] **Distributed/batch execution**
  - Parallel benchmark execution and resumable runs.
- [ ] **Artifact viewer**
  - CLI command to inspect run traces and compare two runs quickly.


## 3) Documentation TODO

- [ ] Add `docs/core/task.md` (Task contract + examples).
- [ ] Add `docs/core/env.md` (Env contract + design rules).
- [ ] Add `docs/howto/task_dataset.md` (how to build task packs).
- [ ] Add `docs/howto/benchmark_runner.md`.
- [ ] Update all tutorials to use `Task` where suitable.
- [ ] Add one “from idea to paper reproduction” walkthrough.


## 4) Testing and CI TODO

- [ ] Unit tests for `Task` validation and serialization.
- [ ] Unit tests for `Env` lifecycle and engine integration.
- [ ] Integration test: `Task + Env + AgentModule` full loop.
- [ ] Snapshot tests for render event schema.
- [ ] Benchmark smoke test in CI (tiny split, fixed seed).
- [ ] Reproducibility check: same task/config -> comparable trace signature.


## 5) Suggested Milestones (3-5 weeks)

Week 1:
- Implement `Task` + `Env` core abstractions.
- Engine `str | Task` compatibility and resource staging.

Week 2:
- Add kit env implementations + task loaders.
- Move examples to Task-based entry points where appropriate.

Week 3:
- Build benchmark runner and first 2 suites (`swe-mini`, `doc-qa-mini`).
- Add strict trace reproducibility fields and validator.

Week 4:
- Complete `web-task-mini` + `computer-use-mini`.
- CI benchmark gate + docs pass.

Week 5 (buffer / polish):
- Security hardening, final docs polish, release packaging.


## 6) Risks and Mitigations

- Risk: Scope creep in env implementations.
  - Mitigation: keep core env interface minimal; move complexity to kit.

- Risk: Benchmarks become non-deterministic due to model variance.
  - Mitigation: record seeds, prompts, model endpoints; use deterministic evaluators when possible.

- Risk: Render schema churn breaks downstream UI.
  - Mitigation: freeze schema version and maintain compatibility adapters.


## 7) Release Decision Checklist

- [ ] P0 all complete.
- [ ] At least 2 benchmark suites pass baseline threshold.
- [ ] Docs cover core + examples + benchmark workflow end-to-end.
- [ ] No plaintext secrets in tracked files.
- [ ] Regression CI green for 7 consecutive days.


## 8) Immediate Next 10 Tasks (Actionable)

1. Add `qitos/core/task.py` with dataclasses + validation.
2. Add `qitos/core/env.py` interface.
3. Update `qitos/core/__init__.py` and `qitos/__init__.py` exports.
4. Integrate `Engine.run(str|Task)` path.
5. Implement resource staging utility for task resources.
6. Add env lifecycle hooks into engine state machine.
7. Add trace required fields for task/env identity.
8. Add `qitos/kit/env/repo_env.py`.
9. Add benchmark runner skeleton and one toy dataset.
10. Add docs for Task/Env and a minimal benchmark tutorial.
